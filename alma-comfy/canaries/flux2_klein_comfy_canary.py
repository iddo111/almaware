#!/usr/bin/env python3
"""Submit and verify a fixed-seed FLUX.2 Klein canary through local ComfyUI."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import socket
import subprocess
import threading
import time
import traceback
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROMPT = (
    "A small brass exploration robot studying a luminous blue crystal on a clean "
    "wooden workbench, cinematic soft window light, realistic materials, shallow "
    "depth of field, uncluttered background, no text, no logo"
)
SEED = 20_260_722
WIDTH = 512
HEIGHT = 512
STEPS = 4
CFG = 1.0


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def package_versions(names: list[str]) -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for name in names:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def meminfo() -> dict[str, int]:
    values: dict[str, int] = {}
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            key, raw = line.split(":", 1)
            values[key] = int(raw.strip().split()[0]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    return values


def telemetry_worker(path: Path, stop: threading.Event) -> None:
    query = (
        "timestamp,name,utilization.gpu,temperature.gpu,power.draw,"
        "memory.used,memory.total"
    )
    with path.open("a", encoding="utf-8") as stream:
        while not stop.is_set():
            sample: dict[str, Any] = {"captured_at_utc": utc_now(), "meminfo": meminfo()}
            try:
                probe = subprocess.run(
                    [
                        "nvidia-smi",
                        f"--query-gpu={query}",
                        "--format=csv,noheader,nounits",
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                sample["nvidia_smi_rc"] = probe.returncode
                sample["nvidia_smi"] = probe.stdout.strip()
                if probe.stderr.strip():
                    sample["nvidia_smi_stderr"] = probe.stderr.strip()
            except BaseException as exc:
                sample["nvidia_smi_error"] = repr(exc)
            stream.write(json.dumps(sample, ensure_ascii=False) + "\n")
            stream.flush()
            stop.wait(1.0)


def request_json(url: str, payload: dict[str, Any] | None = None, timeout: float = 30) -> Any:
    body = None
    headers: dict[str, str] = {}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {detail}") from exc


def prompt_graph() -> dict[str, Any]:
    return {
        "1": {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": "flux-2-klein-4b-fp8.safetensors",
                "weight_dtype": "default",
            },
        },
        "2": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": "qwen_3_4b.safetensors",
                "type": "flux2",
                "device": "default",
            },
        },
        "3": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": "flux2-vae.safetensors"},
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": PROMPT, "clip": ["2", 0]},
        },
        "5": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "", "clip": ["2", 0]},
        },
        "6": {
            "class_type": "CFGGuider",
            "inputs": {
                "model": ["1", 0],
                "positive": ["4", 0],
                "negative": ["5", 0],
                "cfg": CFG,
            },
        },
        "7": {"class_type": "RandomNoise", "inputs": {"noise_seed": SEED}},
        "8": {
            "class_type": "EmptyFlux2LatentImage",
            "inputs": {"width": WIDTH, "height": HEIGHT, "batch_size": 1},
        },
        "9": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "10": {
            "class_type": "Flux2Scheduler",
            "inputs": {"steps": STEPS, "width": WIDTH, "height": HEIGHT},
        },
        "11": {
            "class_type": "SamplerCustomAdvanced",
            "inputs": {
                "noise": ["7", 0],
                "guider": ["6", 0],
                "sampler": ["9", 0],
                "sigmas": ["10", 0],
                "latent_image": ["8", 0],
            },
        },
        "12": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["11", 0], "vae": ["3", 0]},
        },
        "13": {
            "class_type": "SaveImage",
            "inputs": {
                "images": ["12", 0],
                "filename_prefix": "ALMA_flux2_klein_fixed_seed_20260722",
            },
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server-url", default="http://127.0.0.1:8191")
    parser.add_argument("--comfy-root", required=True)
    parser.add_argument("--server-output-dir", required=True)
    parser.add_argument("--transformer-file", required=True)
    parser.add_argument("--text-encoder-file", required=True)
    parser.add_argument("--vae-file", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    comfy_root = Path(args.comfy_root).resolve(strict=True)
    server_output_dir = Path(args.server_output_dir).resolve(strict=True)
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    telemetry_path = output_dir / "telemetry.jsonl"
    receipt_path = output_dir / "run-receipt.json"
    model_paths = {
        "fp8_transformer": Path(args.transformer_file).resolve(strict=True),
        "qwen3_text_encoder": Path(args.text_encoder_file).resolve(strict=True),
        "flux2_vae": Path(args.vae_file).resolve(strict=True),
    }
    graph = prompt_graph()
    write_json(output_dir / "workflow-api.json", graph)
    (output_dir / "prompt.txt").write_text(PROMPT + "\n", encoding="utf-8")

    try:
        comfy_commit = subprocess.run(
            ["git", "-C", str(comfy_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
    except BaseException as exc:
        comfy_commit = f"unavailable: {exc!r}"
    freeze = subprocess.run(
        [os.sys.executable, "-m", "pip", "freeze"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    (output_dir / "isolated-runtime-freeze.txt").write_text(
        freeze.stdout, encoding="utf-8"
    )

    receipt: dict[str, Any] = {
        "status": "starting",
        "started_at_utc": utc_now(),
        "host": socket.gethostname(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "executable": os.path.realpath(os.sys.executable),
        "pythonpath": os.environ.get("PYTHONPATH", ""),
        "comfy_root": str(comfy_root),
        "comfy_commit": comfy_commit,
        "server_url": args.server_url,
        "packages": package_versions(
            [
                "torch",
                "torchvision",
                "torchaudio",
                "numpy",
                "Pillow",
                "safetensors",
                "comfy-kitchen",
                "comfyui-frontend-package",
            ]
        ),
        "config": {
            "prompt": PROMPT,
            "seed": SEED,
            "width": WIDTH,
            "height": HEIGHT,
            "steps": STEPS,
            "cfg": CFG,
            "sampler": "euler",
        },
        "model_revisions": {
            "black-forest-labs/FLUX.2-klein-4B-fp8": "tree matched before canary",
            "Comfy-Org/z_image_turbo": "d24c4cf2a0cd98a42f23467e27e3d76ee9438b8e",
            "Comfy-Org/flux2-dev": "03d6521e6f6a47396b3f951cbea50f7e6c2f482e",
        },
        "system_memory_before": meminfo(),
        "human_visual_review": "not-recorded",
    }
    write_json(receipt_path, receipt)

    stop = threading.Event()
    collector = threading.Thread(
        target=telemetry_worker,
        args=(telemetry_path, stop),
        name="flux-comfy-telemetry",
        daemon=True,
    )
    collector.start()
    started = time.monotonic()
    try:
        from PIL import Image
        import numpy as np

        model_evidence: dict[str, Any] = {}
        for name, path in model_paths.items():
            if path.stat().st_size <= 0:
                raise RuntimeError(f"model component is empty: {path}")
            model_evidence[name] = {
                "path": str(path),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        receipt["models"] = model_evidence
        write_json(receipt_path, receipt)

        object_info = request_json(f"{args.server_url}/object_info", timeout=30)
        required_nodes = sorted({node["class_type"] for node in graph.values()})
        missing_nodes = [name for name in required_nodes if name not in object_info]
        if missing_nodes:
            raise RuntimeError(f"ComfyUI is missing required nodes: {missing_nodes}")
        model_inputs = {
            "unet": object_info["UNETLoader"]["input"]["required"]["unet_name"][0],
            "clip": object_info["CLIPLoader"]["input"]["required"]["clip_name"][0],
            "vae": object_info["VAELoader"]["input"]["required"]["vae_name"][0],
        }
        expected_models = {
            "unet": "flux-2-klein-4b-fp8.safetensors",
            "clip": "qwen_3_4b.safetensors",
            "vae": "flux2-vae.safetensors",
        }
        absent_models = [
            f"{kind}:{name}"
            for kind, name in expected_models.items()
            if name not in model_inputs[kind]
        ]
        if absent_models:
            raise RuntimeError(f"ComfyUI did not discover model files: {absent_models}")
        receipt["comfy_discovery"] = {
            "required_nodes": required_nodes,
            "model_inputs": model_inputs,
        }
        write_json(receipt_path, receipt)

        response = request_json(
            f"{args.server_url}/prompt",
            {"prompt": graph, "client_id": "alma-flux2-klein-canary"},
            timeout=30,
        )
        write_json(output_dir / "prompt-response.json", response)
        prompt_id = response.get("prompt_id")
        if not prompt_id:
            raise RuntimeError(f"ComfyUI did not return prompt_id: {response}")
        receipt["prompt_id"] = prompt_id
        write_json(receipt_path, receipt)

        deadline = time.monotonic() + 900
        history_item: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            history = request_json(
                f"{args.server_url}/history/{prompt_id}", timeout=30
            )
            if prompt_id in history:
                history_item = history[prompt_id]
                status = history_item.get("status", {})
                if status.get("completed"):
                    break
            time.sleep(1)
        if history_item is None or not history_item.get("status", {}).get("completed"):
            raise RuntimeError("ComfyUI generation did not complete within 900 seconds")
        write_json(output_dir / "history.json", history_item)
        if history_item.get("status", {}).get("status_str") != "success":
            raise RuntimeError(f"ComfyUI history reports failure: {history_item.get('status')}")

        images = history_item.get("outputs", {}).get("13", {}).get("images", [])
        if len(images) != 1:
            raise RuntimeError(f"expected exactly one saved image, got {images}")
        image_info = images[0]
        source = (
            server_output_dir
            / str(image_info.get("subfolder", ""))
            / str(image_info["filename"])
        ).resolve(strict=True)
        if server_output_dir not in source.parents:
            raise RuntimeError(f"ComfyUI output escaped output root: {source}")
        final_path = output_dir / "flux2-klein-fixed-seed.png"
        shutil.copy2(source, final_path)
        if final_path.stat().st_size <= 0:
            raise RuntimeError("PNG output is empty")

        with Image.open(final_path) as check:
            verify_format = check.format
            verify_size = list(check.size)
            verify_mode = check.mode
            embedded_keys = sorted(check.info.keys())
            check.verify()
        with Image.open(final_path) as decoded:
            decoded.load()
            decoded_size = list(decoded.size)
            decoded_mode = decoded.mode
            pixels = np.asarray(decoded, dtype=np.float32)
        if verify_format != "PNG" or decoded_size != [WIDTH, HEIGHT]:
            raise RuntimeError(
                f"unexpected decoded PNG properties: format={verify_format} size={decoded_size}"
            )
        if pixels.size == 0 or not np.isfinite(pixels).all():
            raise RuntimeError("decoded PNG pixels are empty or non-finite")
        pixel_std = float(pixels.std())
        if pixel_std < 1.0 or float(pixels.max()) <= float(pixels.min()):
            raise RuntimeError(f"decoded image appears blank: std={pixel_std}")

        receipt.update(
            status="generated",
            finished_at_utc=utc_now(),
            elapsed_seconds=round(time.monotonic() - started, 3),
            output_path=str(final_path),
            output_bytes=final_path.stat().st_size,
            output_sha256=sha256_file(final_path),
            png={
                "verify_format": verify_format,
                "verify_size": verify_size,
                "verify_mode": verify_mode,
                "decoded_size": decoded_size,
                "decoded_mode": decoded_mode,
                "full_decode": True,
                "pixel_min": float(pixels.min()),
                "pixel_max": float(pixels.max()),
                "pixel_mean": float(pixels.mean()),
                "pixel_std": pixel_std,
                "embedded_metadata_keys": embedded_keys,
            },
            system_memory_after=meminfo(),
        )
        write_json(receipt_path, receipt)
        print(json.dumps(receipt, ensure_ascii=False), flush=True)
        return 0
    except BaseException as exc:
        receipt.update(
            status="failed",
            finished_at_utc=utc_now(),
            elapsed_seconds=round(time.monotonic() - started, 3),
            error=repr(exc),
            traceback=traceback.format_exc(),
            system_memory_after=meminfo(),
        )
        write_json(receipt_path, receipt)
        print(json.dumps(receipt, ensure_ascii=False), flush=True)
        raise
    finally:
        stop.set()
        collector.join(timeout=6)


if __name__ == "__main__":
    raise SystemExit(main())
