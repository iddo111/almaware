#!/usr/bin/env python3
"""Fixed-seed, offline FLUX.2 Klein FP8 image-generation canary for DGX3."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import socket
import subprocess
import threading
import time
import traceback
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
NUM_INFERENCE_STEPS = 4
GUIDANCE_SCALE = 1.0


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


def file_manifest(root: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file() and ".cache" not in p.parts):
        entries.append(
            {
                "path": path.relative_to(root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return entries


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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transformer-file", required=True)
    parser.add_argument("--components-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    transformer_file = Path(args.transformer_file).resolve(strict=True)
    components_dir = Path(args.components_dir).resolve(strict=True)
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "flux2-klein-fixed-seed.png"
    receipt_path = output_dir / "run-receipt.json"
    telemetry_path = output_dir / "telemetry.jsonl"

    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

    required = [
        "model_index.json",
        "scheduler/scheduler_config.json",
        "text_encoder/config.json",
        "text_encoder/model.safetensors.index.json",
        "tokenizer/tokenizer.json",
        "transformer/config.json",
        "vae/config.json",
        "vae/diffusion_pytorch_model.safetensors",
    ]
    missing = [item for item in required if not (components_dir / item).is_file()]
    incomplete = [
        str(path.relative_to(components_dir))
        for path in components_dir.rglob("*.incomplete")
    ]

    config: dict[str, Any] = {
        "prompt": PROMPT,
        "seed": SEED,
        "width": WIDTH,
        "height": HEIGHT,
        "num_inference_steps": NUM_INFERENCE_STEPS,
        "guidance_scale": GUIDANCE_SCALE,
        "transformer_file": str(transformer_file),
        "components_dir": str(components_dir),
        "offline_only": True,
    }
    (output_dir / "prompt.txt").write_text(PROMPT + "\n", encoding="utf-8")
    write_json(output_dir / "run-config.json", config)

    receipt: dict[str, Any] = {
        "status": "starting",
        "started_at_utc": utc_now(),
        "host": socket.gethostname(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "executable": os.path.realpath(os.sys.executable),
        "packages": package_versions(
            [
                "torch",
                "torchvision",
                "diffusers",
                "transformers",
                "accelerate",
                "safetensors",
                "pillow",
                "numpy",
                "huggingface-hub",
            ]
        ),
        "config": config,
        "missing_required_components": missing,
        "incomplete_component_files": incomplete,
        "system_memory_before": meminfo(),
    }
    write_json(receipt_path, receipt)

    stop = threading.Event()
    collector = threading.Thread(
        target=telemetry_worker,
        args=(telemetry_path, stop),
        name="flux-canary-telemetry",
        daemon=True,
    )
    collector.start()
    started = time.monotonic()
    try:
        import numpy as np
        import torch
        from diffusers import Flux2KleinPipeline, Flux2Transformer2DModel
        from PIL import Image, PngImagePlugin

        if missing:
            raise RuntimeError(f"missing required pipeline components: {missing}")
        if incomplete:
            raise RuntimeError(f"incomplete component downloads: {incomplete}")
        if transformer_file.stat().st_size <= 0:
            raise RuntimeError("transformer file is empty")
        if not torch.cuda.is_available():
            raise RuntimeError("torch.cuda.is_available() is False")

        receipt["cuda"] = {
            "torch_cuda_version": torch.version.cuda,
            "device_name": torch.cuda.get_device_name(0),
            "device_capability": list(torch.cuda.get_device_capability(0)),
        }
        write_json(receipt_path, receipt)

        print(json.dumps({"event": "hash_model_and_components"}), flush=True)
        transformer_sha256 = sha256_file(transformer_file)
        components = file_manifest(components_dir)
        write_json(output_dir / "component-manifest.json", components)
        receipt["transformer"] = {
            "path": str(transformer_file),
            "bytes": transformer_file.stat().st_size,
            "sha256": transformer_sha256,
        }
        receipt["components"] = {
            "noncache_file_count": len(components),
            "noncache_bytes": sum(int(item["bytes"]) for item in components),
            "manifest": "component-manifest.json",
        }
        write_json(receipt_path, receipt)

        torch.cuda.reset_peak_memory_stats()
        print(json.dumps({"event": "load_fp8_transformer"}), flush=True)
        transformer = Flux2Transformer2DModel.from_single_file(
            str(transformer_file),
            config=str(components_dir),
            subfolder="transformer",
            torch_dtype=torch.bfloat16,
            local_files_only=True,
        )
        print(json.dumps({"event": "load_offline_pipeline"}), flush=True)
        pipe = Flux2KleinPipeline.from_pretrained(
            str(components_dir),
            transformer=transformer,
            torch_dtype=torch.bfloat16,
            local_files_only=True,
        )
        pipe.enable_model_cpu_offload()
        pipe.set_progress_bar_config(desc="flux2-klein-canary")

        generator = torch.Generator(device="cuda").manual_seed(SEED)
        print(json.dumps({"event": "generate", **config}), flush=True)
        result = pipe(
            prompt=PROMPT,
            height=HEIGHT,
            width=WIDTH,
            guidance_scale=GUIDANCE_SCALE,
            num_inference_steps=NUM_INFERENCE_STEPS,
            generator=generator,
        )
        if not result.images:
            raise RuntimeError("pipeline returned no images")
        image = result.images[0]
        if image.size != (WIDTH, HEIGHT):
            raise RuntimeError(f"unexpected image dimensions: {image.size}")
        if image.mode != "RGB":
            image = image.convert("RGB")

        png_info = PngImagePlugin.PngInfo()
        png_info.add_text("Software", "ALMA Studio FLUX.2 Klein technical canary")
        png_info.add_text("Model", "black-forest-labs/FLUX.2-klein-4B-fp8")
        png_info.add_text("Seed", str(SEED))
        png_info.add_text("Prompt", PROMPT)
        image.save(output_path, format="PNG", pnginfo=png_info)
        if output_path.stat().st_size <= 0:
            raise RuntimeError("PNG output is empty")

        with Image.open(output_path) as check:
            verify_format = check.format
            verify_size = list(check.size)
            verify_mode = check.mode
            embedded_metadata = dict(check.info)
            check.verify()
        with Image.open(output_path) as decoded:
            decoded.load()
            pixels = np.asarray(decoded, dtype=np.float32)
            decoded_size = list(decoded.size)
            decoded_mode = decoded.mode
        if pixels.size == 0 or not np.isfinite(pixels).all():
            raise RuntimeError("decoded PNG pixels are empty or non-finite")
        pixel_std = float(pixels.std())
        if pixel_std < 1.0 or float(pixels.max()) <= float(pixels.min()):
            raise RuntimeError(f"decoded image appears blank: std={pixel_std}")

        digest = sha256_file(output_path)
        receipt.update(
            status="generated",
            finished_at_utc=utc_now(),
            elapsed_seconds=round(time.monotonic() - started, 3),
            output_path=str(output_path),
            output_bytes=output_path.stat().st_size,
            output_sha256=digest,
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
                "embedded_metadata": embedded_metadata,
            },
            torch_cuda_peak_allocated_bytes=int(torch.cuda.max_memory_allocated()),
            torch_cuda_peak_reserved_bytes=int(torch.cuda.max_memory_reserved()),
            system_memory_after=meminfo(),
            human_visual_review="not-recorded",
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
            human_visual_review="not-recorded",
        )
        write_json(receipt_path, receipt)
        print(json.dumps(receipt, ensure_ascii=False), flush=True)
        raise
    finally:
        stop.set()
        collector.join(timeout=6)


if __name__ == "__main__":
    raise SystemExit(main())
