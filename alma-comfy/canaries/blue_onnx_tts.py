#!/usr/bin/env python3
"""Pinned, fail-closed Blue ONNX speech runner for ALMA Studio on DGX4.

This is a command-line production primitive, not a service.  It deliberately
uses the isolated CPU environment and the model-shipped MIT voice style; it
does not accept a voice-cloning reference.

Example (run with the pinned interpreter on DGX4):

    /home/eran4/.venvs/alma-blue-onnx-cpu/bin/python blue_onnx_tts.py \
      --text 'שלום.' --output /absolute/path/line.wav --seed 424242
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


ENGINE_REPO = Path("/home/eran4/alma-studio/blue-tts")
ENGINE_ORIGIN = "https://github.com/maxmelichov/BlueTTS.git"
ENGINE_COMMIT = "f071b9100e15c24575f6e2919312f67057c7b589"

MODEL_REPO = "notmax123/blue-onnx-v2"
MODEL_REVISION = "45dc85f1ac045ea62458a7492c5ae387610ac0af"
MODEL_ROOT = Path("/home/eran4/models/alma-studio/blue-onnx-v2")
MODEL_TREE_SHA256 = "7f2298b5a699f1b94b7f2b6bee9f83a938e7614834ab35424a937c77a4a60afa"

G2P_REPO = "thewh1teagle/renikud"
G2P_REVISION = "b80cab616c972b6a87de86044f50b597ee2c53fd"
G2P_ROOT = Path("/home/eran4/models/alma-studio/renikud")
G2P_TREE_SHA256 = "235009998202fa27cf3ea3fac4a91542b308f7d91ec47a6925b7629f5e5c71b3"

PINNED_PYTHON = Path("/home/eran4/.venvs/alma-blue-onnx-cpu/bin/python")
PINNED_UV = Path("/home/eran4/.local/bin/uv")
PINNED_FFMPEG_PROBE = Path("/usr/bin/ffprobe")
PINNED_PYTHON_VERSION = (3, 12, 3)
PINNED_FREEZE_SHA256 = "beadc4918ba96df756ae8d853db913e720b8c6cdf0bacf813818fbfc1c898e76"

VOICE_RELATIVE_PATH = "voices/female1.json"
VOICE_LICENSE = "MIT (model-shipped preset; no external reference audio)"

# Runtime-critical artifacts only.  Codec/style encoders are not used by this
# fixed preset inference path and therefore are not part of the execution TCB.
PINNED_FILES: dict[str, tuple[Path, str, str]] = {
    "duration_predictor.onnx": (
        MODEL_ROOT / "duration_predictor.onnx",
        "1fb897a3f1c5f4132ffba3e56c5792f8c03783e2f478d825774514da668af161",
        MODEL_REVISION,
    ),
    "text_encoder.onnx": (
        MODEL_ROOT / "text_encoder.onnx",
        "9f80f87093067ee2300343133b0456e36d705eea31f523f9d3dc9f4c5e212db1",
        MODEL_REVISION,
    ),
    "vector_estimator.onnx": (
        MODEL_ROOT / "vector_estimator.onnx",
        "8c333ef2eb0c075136384eaa9608a374230f1b26e8181097467b803078095a5a",
        MODEL_REVISION,
    ),
    "vocoder.onnx": (
        MODEL_ROOT / "vocoder.onnx",
        "f4fbb6f60dec035cd8071883e021ac2cd3eee62630e42174492fd2d1f39976db",
        MODEL_REVISION,
    ),
    "tts.json": (
        MODEL_ROOT / "tts.json",
        "9afc8622ee9a40adff8befdc6bdfcb3c008f8caed9750febe870e53f47a73a0a",
        MODEL_REVISION,
    ),
    "vocab.json": (
        MODEL_ROOT / "vocab.json",
        "9c5ce360977b8b70423a782519bc067681863aae54768105e5aa0fed9f02520d",
        MODEL_REVISION,
    ),
    VOICE_RELATIVE_PATH: (
        MODEL_ROOT / VOICE_RELATIVE_PATH,
        "22e6c98210ca014cfd40bd485152a58c49bfff32265faff8c1c47cb4d60e1872",
        MODEL_REVISION,
    ),
    "renikud/model.onnx": (
        G2P_ROOT / "model.onnx",
        "8b881a3a8f00283d86c6d1feea44d37e09c1ea6609a4de7d820d937e7f3dbbca",
        G2P_REVISION,
    ),
}

SUPPORTED_LANGUAGES = ("he", "en", "es", "de", "it")


class GateError(RuntimeError):
    """Raised when a pinned production invariant is not satisfied."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate one WAV with the pinned DGX4 Blue ONNX runtime."
    )
    parser.add_argument("--text", required=True, help="Exact text to speak.")
    parser.add_argument(
        "--output", required=True, type=Path, help="Absolute .wav output path."
    )
    parser.add_argument(
        "--seed", required=True, type=int, help="Explicit NumPy seed (0..2^32-1)."
    )
    parser.add_argument(
        "--language",
        default="he",
        choices=SUPPORTED_LANGUAGES,
        help="Language code; defaults to Hebrew (he).",
    )
    parser.add_argument("--steps", type=int, default=8, help="Flow steps (1..100).")
    parser.add_argument("--speed", type=float, default=1.0, help="Speech speed (0.5..2.0).")
    parser.add_argument(
        "--cfg-scale", type=float, default=3.0, help="Guidance scale (0.5..10.0)."
    )
    parser.add_argument(
        "--receipt-dir",
        type=Path,
        help="Absolute receipt directory; default is OUTPUT_STEM.receipts.",
    )
    return parser.parse_args(argv)


def sha256_file(path: Path, chunk_bytes: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(chunk_bytes), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def run_checked(command: list[str], *, cwd: Path | None = None) -> str:
    result = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise GateError(f"command failed ({result.returncode}): {command[0]}: {detail}")
    # uv writes its successful environment summary to stderr; preserve that in
    # receipts while keeping normal command stdout authoritative when present.
    return result.stdout if result.stdout else result.stderr


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def require(condition: bool, message: str) -> None:
    if not condition:
        raise GateError(message)


def metadata_revision(root: Path, relative_path: str) -> str:
    metadata = root / ".cache" / "huggingface" / "download" / f"{relative_path}.metadata"
    require(metadata.is_file(), f"missing Hugging Face metadata: {metadata}")
    lines = metadata.read_text(encoding="utf-8").splitlines()
    require(bool(lines), f"empty Hugging Face metadata: {metadata}")
    return lines[0].strip()


def validate_cli(args: argparse.Namespace) -> tuple[Path, Path]:
    output = args.output.expanduser()
    require(output.is_absolute(), "--output must be absolute")
    require(output.suffix.lower() == ".wav", "--output must end in .wav")
    require(output.parent.is_dir(), f"output parent does not exist: {output.parent}")
    require(not output.exists(), f"refusing to overwrite output: {output}")
    require(bool(args.text.strip()), "--text cannot be blank")
    require(len(args.text) <= 5000, "--text exceeds the 5000-character production limit")
    require(0 <= args.seed <= 0xFFFFFFFF, "--seed must be between 0 and 2^32-1")
    require(1 <= args.steps <= 100, "--steps must be between 1 and 100")
    require(0.5 <= args.speed <= 2.0, "--speed must be between 0.5 and 2.0")
    require(0.5 <= args.cfg_scale <= 10.0, "--cfg-scale must be between 0.5 and 10.0")

    receipt_dir = (
        args.receipt_dir.expanduser()
        if args.receipt_dir
        else output.with_suffix("").with_name(output.stem + ".receipts")
    )
    require(receipt_dir.is_absolute(), "--receipt-dir must be absolute")
    require(receipt_dir.parent.is_dir(), f"receipt parent does not exist: {receipt_dir.parent}")
    require(not receipt_dir.exists(), f"refusing to overwrite receipt directory: {receipt_dir}")
    require(receipt_dir != output.parent, "receipt directory cannot equal the output parent")
    return output, receipt_dir


def validate_runtime(receipt_dir: Path) -> dict[str, Any]:
    checks: list[str] = []
    require(Path(sys.executable).resolve() == PINNED_PYTHON.resolve(), f"wrong interpreter: {sys.executable}")
    require(sys.version_info[:3] == PINNED_PYTHON_VERSION, f"wrong Python version: {platform.python_version()}")
    checks.append("pinned-python")

    require(PINNED_UV.is_file(), f"missing pinned uv executable: {PINNED_UV}")
    freeze_raw = run_checked(
        [str(PINNED_UV), "pip", "freeze", "--python", str(PINNED_PYTHON)]
    )
    freeze = "\n".join(sorted(line.strip() for line in freeze_raw.splitlines() if line.strip())) + "\n"
    require(
        sha256_text(freeze) == PINNED_FREEZE_SHA256,
        "isolated environment freeze hash drifted",
    )
    (receipt_dir / "environment.freeze.txt").write_text(freeze, encoding="utf-8")
    check_text = run_checked(
        [str(PINNED_UV), "pip", "check", "--python", str(PINNED_PYTHON)]
    )
    (receipt_dir / "environment.check.txt").write_text(check_text, encoding="utf-8")
    checks.append("pinned-environment-freeze-and-check")

    require(ENGINE_REPO.is_dir(), f"missing official source checkout: {ENGINE_REPO}")
    origin = run_checked(["git", "remote", "get-url", "origin"], cwd=ENGINE_REPO).strip()
    commit = run_checked(["git", "rev-parse", "HEAD"], cwd=ENGINE_REPO).strip()
    status = run_checked(["git", "status", "--porcelain"], cwd=ENGINE_REPO)
    require(origin == ENGINE_ORIGIN, f"official source origin drifted: {origin}")
    require(commit == ENGINE_COMMIT, f"official source commit drifted: {commit}")
    require(not status.strip(), "official source checkout is dirty")
    source_detail = run_checked(
        ["git", "show", "-s", "--format=%H%n%cI%n%s", "HEAD"], cwd=ENGINE_REPO
    )
    (receipt_dir / "runtime-source-revision.txt").write_text(source_detail, encoding="utf-8")
    (receipt_dir / "runtime-source-status.txt").write_text(status, encoding="utf-8")
    checks.append("official-source-origin-commit-clean")

    model_tree = MODEL_ROOT / ".cache" / "huggingface" / "trees" / f"{MODEL_REVISION}.json"
    g2p_tree = G2P_ROOT / ".cache" / "huggingface" / "trees" / f"{G2P_REVISION}.json"
    require(model_tree.is_file(), f"missing pinned model tree: {model_tree}")
    require(g2p_tree.is_file(), f"missing pinned G2P tree: {g2p_tree}")
    require(sha256_file(model_tree) == MODEL_TREE_SHA256, "pinned model tree metadata drifted")
    require(sha256_file(g2p_tree) == G2P_TREE_SHA256, "pinned G2P tree metadata drifted")
    checks.append("pinned-huggingface-tree-metadata")

    model_sums: list[str] = []
    for label, (path, expected_sha256, revision) in PINNED_FILES.items():
        require(path.is_file(), f"missing runtime artifact: {path}")
        actual_sha256 = sha256_file(path)
        require(actual_sha256 == expected_sha256, f"SHA-256 drift for {label}")
        if label == "renikud/model.onnx":
            actual_revision = metadata_revision(G2P_ROOT, "model.onnx")
        else:
            actual_revision = metadata_revision(MODEL_ROOT, label)
        require(actual_revision == revision, f"revision drift for {label}: {actual_revision}")
        model_sums.append(f"{actual_sha256}  {path}")
    (receipt_dir / "MODEL_SHA256SUMS").write_text("\n".join(model_sums) + "\n", encoding="utf-8")
    checks.append("pinned-model-g2p-revisions-and-sha256")

    require(PINNED_FFMPEG_PROBE.is_file(), f"missing ffprobe: {PINNED_FFMPEG_PROBE}")
    return {
        "checks": checks,
        "environment_freeze_sha256": PINNED_FREEZE_SHA256,
        "engine_origin": origin,
        "engine_commit": commit,
        "model_revision": MODEL_REVISION,
        "g2p_revision": G2P_REVISION,
    }


def load_engine() -> tuple[Any, Any, Any, str]:
    source_root = (ENGINE_REPO / "src").resolve()
    sys.path.insert(0, str(source_root))
    import blue_onnx  # type: ignore
    import numpy as np  # type: ignore
    import soundfile as sf  # type: ignore

    imported = Path(blue_onnx.__file__).resolve()
    expected = (source_root / "blue_onnx" / "__init__.py").resolve()
    require(imported == expected, f"Blue ONNX import did not resolve to pinned source: {imported}")
    return blue_onnx, np, sf, str(imported)


def probe_and_validate(path: Path, expected_duration: float) -> dict[str, Any]:
    raw = run_checked(
        [
            str(PINNED_FFMPEG_PROBE),
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ]
    )
    probe = json.loads(raw)
    streams = [entry for entry in probe.get("streams", []) if entry.get("codec_type") == "audio"]
    require(len(streams) == 1, "ffprobe did not find exactly one audio stream")
    stream = streams[0]
    require(stream.get("codec_name") == "pcm_s24le", f"unexpected codec: {stream.get('codec_name')}")
    require(int(stream.get("sample_rate", 0)) == 44100, "unexpected sample rate")
    require(int(stream.get("channels", 0)) == 1, "unexpected channel count")
    bits = int(stream.get("bits_per_raw_sample") or stream.get("bits_per_sample") or 0)
    require(bits == 24, f"unexpected PCM depth: {bits}")
    duration = float(stream.get("duration") or probe.get("format", {}).get("duration") or 0.0)
    require(duration > 0.1, "ffprobe duration is too short")
    require(abs(duration - expected_duration) <= 0.05, "ffprobe duration disagrees with generated samples")
    require(int(probe.get("format", {}).get("size", 0)) > 44, "WAV is empty")
    return probe


def evidence_sums(receipt_dir: Path, output: Path) -> None:
    names = [
        "environment.freeze.txt",
        "environment.check.txt",
        "runtime-source-revision.txt",
        "runtime-source-status.txt",
        "MODEL_SHA256SUMS",
        "metrics.json",
        "ffprobe.json",
        "provenance.json",
        "WAV_SHA256SUM",
        "exit_code",
    ]
    lines = [f"{sha256_file(receipt_dir / name)}  {receipt_dir / name}" for name in names if (receipt_dir / name).is_file()]
    if output.is_file():
        lines.append(f"{sha256_file(output)}  {output}")
    (receipt_dir / "EVIDENCE_SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")


def synthesize(args: argparse.Namespace, output: Path, receipt_dir: Path) -> dict[str, Any]:
    gate = validate_runtime(receipt_dir)
    blue_onnx, np, sf, imported_module = load_engine()

    np.random.seed(args.seed)
    load_started = time.perf_counter()
    tts = blue_onnx.load_text_to_speech(str(MODEL_ROOT), use_gpu=False)
    # Never depend on cwd discovery for Hebrew G2P: inject the exact pinned file.
    tts.g2p = blue_onnx.TextProcessor(str(G2P_ROOT / "model.onnx"))
    style = blue_onnx.load_voice_style([str(MODEL_ROOT / VOICE_RELATIVE_PATH)])
    load_seconds = time.perf_counter() - load_started

    generation_started = time.perf_counter()
    waveform, predicted_duration = tts(
        args.text,
        lang=args.language,
        style=style,
        total_step=args.steps,
        speed=args.speed,
        cfg_scale=args.cfg_scale,
    )
    generation_seconds = time.perf_counter() - generation_started

    audio = np.asarray(waveform, dtype=np.float32).reshape(-1)
    require(audio.size > 1000, "generated waveform has too few samples")
    require(bool(np.isfinite(audio).all()), "generated waveform contains non-finite samples")
    peak = float(np.max(np.abs(audio)))
    rms = float(np.sqrt(np.mean(np.square(audio.astype(np.float64)))))
    non_silent = float(np.mean(np.abs(audio) > 1.0e-4))
    clipping = float(np.mean(np.abs(audio) >= 0.999))
    require(peak > 1.0e-4 and rms > 1.0e-5, "generated waveform is silent")
    require(non_silent >= 0.01, "generated waveform is effectively silent")
    require(peak <= 1.0, f"generated waveform exceeds full scale: {peak}")
    require(clipping <= 1.0e-6, f"generated waveform clips: fraction={clipping}")

    sample_rate = int(tts.sample_rate)
    require(sample_rate == 44100, f"model sample rate drifted: {sample_rate}")
    duration = float(audio.size / sample_rate)
    staging = receipt_dir / ".artifact.staging.wav"
    sf.write(str(staging), audio, sample_rate, subtype="PCM_24", format="WAV")
    probe = probe_and_validate(staging, duration)
    probe.get("format", {})["filename"] = str(output)
    write_json(receipt_dir / "ffprobe.json", probe)

    artifact_sha256 = sha256_file(staging)
    predicted = float(np.asarray(predicted_duration).reshape(-1)[0])
    metrics = {
        "status": "generated_not_human_reviewed",
        "human_review": "not-recorded",
        "engine": "blue-onnx",
        "engine_source_commit": ENGINE_COMMIT,
        "runtime_module": imported_module,
        "engine_license": "MIT",
        "model_repo": MODEL_REPO,
        "model_revision": MODEL_REVISION,
        "model_license": "MIT",
        "g2p_repo": G2P_REPO,
        "g2p_revision": G2P_REVISION,
        "g2p_license": "CC-BY-4.0",
        "voice_asset": str(MODEL_ROOT / VOICE_RELATIVE_PATH),
        "voice_license": VOICE_LICENSE,
        "voice_reference_used": False,
        "text": args.text,
        "language": args.language,
        "seed": args.seed,
        "seed_mechanism": "numpy.random.seed",
        "total_step": args.steps,
        "speed": args.speed,
        "cfg_scale": args.cfg_scale,
        "python": platform.python_version(),
        "architecture": platform.machine(),
        "numpy": importlib.metadata.version("numpy"),
        "onnxruntime": importlib.metadata.version("onnxruntime"),
        "providers": ["CPUExecutionProvider"],
        "sample_rate": sample_rate,
        "channels": 1,
        "sample_format": "pcm_s24le",
        "samples": int(audio.size),
        "duration_seconds": duration,
        "predicted_duration_seconds": predicted,
        "load_seconds": load_seconds,
        "generation_seconds": generation_seconds,
        "realtime_factor": generation_seconds / duration,
        "finite": True,
        "peak_abs": peak,
        "rms": rms,
        "non_silent_fraction_abs_gt_1e-4": non_silent,
        "clipping_fraction_abs_ge_0_999": clipping,
        "wav": str(output),
        "wav_sha256": artifact_sha256,
        "g2p_weights": str(G2P_ROOT / "model.onnx"),
    }
    write_json(receipt_dir / "metrics.json", metrics)

    provenance = {
        "status": "technical-pass-human-review-pending",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "node": "DGX4",
        "engine": "blue-onnx",
        "engine_source_origin": ENGINE_ORIGIN,
        "engine_source_commit": ENGINE_COMMIT,
        "model": MODEL_REPO,
        "model_revision": MODEL_REVISION,
        "g2p": G2P_REPO,
        "g2p_revision": G2P_REVISION,
        "language": args.language,
        "seed": args.seed,
        "artifact": str(output),
        "artifact_sha256": artifact_sha256,
        "duration_seconds": duration,
        "sample_rate": sample_rate,
        "channels": 1,
        "sample_format": "pcm_s24le",
        "technical_gates": gate["checks"]
        + ["artifact-nonempty", "sha256-match", "ffprobe-pass", "finite-samples", "non-silent", "no-clipping"],
        "voice_reference_used": False,
        "voice_rights_basis": VOICE_LICENSE,
        "human_review": "not-recorded",
        "source_metrics": "metrics.json",
    }
    write_json(receipt_dir / "provenance.json", provenance)

    shutil.move(str(staging), str(output))
    require(sha256_file(output) == artifact_sha256, "artifact hash changed during final move")
    (receipt_dir / "WAV_SHA256SUM").write_text(f"{artifact_sha256}  {output}\n", encoding="utf-8")
    return provenance


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        output, receipt_dir = validate_cli(args)
    except GateError as error:
        print(f"FAIL-CLOSED: {error}", file=sys.stderr)
        return 2

    receipt_dir.mkdir(mode=0o750)
    try:
        provenance = synthesize(args, output, receipt_dir)
        (receipt_dir / "exit_code").write_text("0\n", encoding="utf-8")
        evidence_sums(receipt_dir, output)
        print(json.dumps(provenance, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as error:
        staging = receipt_dir / ".artifact.staging.wav"
        if staging.is_file():
            staging.unlink()
        failure = {
            "status": "failed-closed",
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "node": "DGX4",
            "engine": "blue-onnx",
            "model_revision": MODEL_REVISION,
            "g2p_revision": G2P_REVISION,
            "output_not_published": not output.exists(),
            "error_type": type(error).__name__,
            "error": str(error),
            "human_review": "not-recorded",
        }
        write_json(receipt_dir / "provenance.json", failure)
        (receipt_dir / "exit_code").write_text("1\n", encoding="utf-8")
        evidence_sums(receipt_dir, output)
        print(f"FAIL-CLOSED: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
