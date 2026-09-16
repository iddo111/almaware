"""Shared fixture for the voice-ant-farm code-revision proofs (2026-09-06).

Every proof runs against a code directory given on the command line, so the
SAME script can be run against the pre-revision backup and against the fixed
tree. Read-only with respect to the live farm: it builds its own tiny corpus
in a temp directory and never touches recordings/, state/ or fire/.
"""
from __future__ import annotations

import json
import math
import sys
import wave
from pathlib import Path


def use_code(argv: list[str]) -> Path:
    if len(argv) < 2:
        raise SystemExit("usage: proof_<id>.py <code-directory>")
    code = Path(argv[1]).resolve()
    if not (code / "acoustic_units.py").exists():
        raise SystemExit(f"no acoustic_units.py in {code}")
    sys.path.insert(0, str(code))
    return code


def write_tone(path: Path, seed: int, seconds: float = 0.8, rate: int = 16_000) -> None:
    """A short, distinct pseudo-speech waveform. Deterministic, no numpy needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    count = int(seconds * rate)
    state = seed * 2_654_435_761 % 2**32
    samples = bytearray()
    formants = [180 + 37 * (seed % 7), 620 + 91 * (seed % 5), 1500 + 130 * (seed % 3)]
    for index in range(count):
        t = index / rate
        state = (1_103_515_245 * state + 12_345) % 2**31
        noise = (state / 2**31 - 0.5) * 0.06
        envelope = 0.35 + 0.3 * math.sin(2 * math.pi * (2.0 + seed % 3) * t)
        value = envelope * sum(
            math.sin(2 * math.pi * f * t + seed * 0.7 * (n + 1)) / (n + 2)
            for n, f in enumerate(formants)
        ) + noise
        pcm = max(-32768, min(32767, int(value * 9000)))
        samples += int(pcm).to_bytes(2, "little", signed=True)
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(rate)
        stream.writeframes(bytes(samples))


def build_project(root: Path, train: int = 6, heldout: int = 3, evaluation: int = 3) -> Path:
    """A complete, manifest-validated miniature of the real project layout."""
    import corpus
    recordings = root / "recordings"
    seed = 1
    for split, count in (("train", train), ("heldout", heldout), ("evaluation", evaluation)):
        for index in range(count):
            write_tone(recordings / split / f"{split}-{index:03d}.wav", seed)
            seed += 1
    manifest = corpus.build_manifest(
        recordings, "proof-speaker",
        {"train": "s-train", "heldout": "s-heldout", "evaluation": "s-eval"},
    )
    manifest_path = recordings / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    corpus.validate_manifest(manifest_path, recordings)
    (root / "state").mkdir(exist_ok=True)
    (root / "fire").mkdir(exist_ok=True)
    return recordings


def report(defect: str, checks: list[tuple[str, bool, str]]) -> int:
    ok = all(passed for _name, passed, _detail in checks)
    print(f"=== {defect} : {'PASS' if ok else 'FAIL'} ===")
    for name, passed, detail in checks:
        print(f"  [{'ok' if passed else 'XX'}] {name}: {detail}")
    return 0 if ok else 1
