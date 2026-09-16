#!/usr/bin/env python3
"""Small, fixed-seed Wan2.2 TI2V-5B compatibility canary for DGX Spark."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import socket
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path


PROMPT = (
    "A single small brass robot walks across a quiet sunlit workbench, "
    "cinematic natural light, stable camera, realistic materials, clean background."
)
NEGATIVE_PROMPT = (
    "text, subtitles, watermark, logo, duplicate subject, deformed limbs, "
    "flicker, camera shake, low detail, overexposure"
)
SEED = 20_260_722
WIDTH = 832
HEIGHT = 480
NUM_FRAMES = 17
NUM_INFERENCE_STEPS = 8
GUIDANCE_SCALE = 5.0
FPS = 24


def package_versions(names: list[str]) -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for name in names:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    model_dir = Path(args.model_dir).resolve(strict=True)
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "wan-ti2v-canary.mp4"
    receipt_path = output_dir / "run-receipt.json"

    model_files = [p for p in model_dir.rglob("*") if p.is_file() and ".cache" not in p.parts]
    incomplete = [str(p.relative_to(model_dir)) for p in model_dir.rglob("*.incomplete")]
    config: dict[str, object] = {
        "prompt": PROMPT,
        "negative_prompt": NEGATIVE_PROMPT,
        "seed": SEED,
        "width": WIDTH,
        "height": HEIGHT,
        "num_frames": NUM_FRAMES,
        "num_inference_steps": NUM_INFERENCE_STEPS,
        "guidance_scale": GUIDANCE_SCALE,
        "fps": FPS,
        "model_dir": str(model_dir),
        "model_noncache_file_count": len(model_files),
        "model_noncache_bytes": sum(p.stat().st_size for p in model_files),
        "model_incomplete_files": incomplete,
    }
    (output_dir / "prompt.txt").write_text(PROMPT + "\n", encoding="utf-8")
    write_json(output_dir / "run-config.json", config)

    receipt: dict[str, object] = {
        "status": "starting",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
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
                "sentencepiece",
                "imageio",
                "imageio-ffmpeg",
            ]
        ),
        "config": config,
    }
    write_json(receipt_path, receipt)

    started = time.monotonic()
    try:
        import numpy as np
        import torch
        from diffusers import AutoencoderKLWan, WanPipeline
        from diffusers.utils import export_to_video

        if incomplete:
            raise RuntimeError(f"model directory contains incomplete files: {incomplete[:5]}")
        if not torch.cuda.is_available():
            raise RuntimeError("torch.cuda.is_available() is False")

        device = torch.device("cuda")
        capability = torch.cuda.get_device_capability(device)
        receipt["cuda"] = {
            "torch_cuda_version": torch.version.cuda,
            "device_name": torch.cuda.get_device_name(device),
            "device_capability": list(capability),
        }
        write_json(receipt_path, receipt)

        print(json.dumps({"event": "load_vae", "model_dir": str(model_dir)}), flush=True)
        vae = AutoencoderKLWan.from_pretrained(
            model_dir,
            subfolder="vae",
            torch_dtype=torch.float32,
            local_files_only=True,
        )
        print(json.dumps({"event": "load_pipeline"}), flush=True)
        pipe = WanPipeline.from_pretrained(
            model_dir,
            vae=vae,
            torch_dtype=torch.bfloat16,
            local_files_only=True,
        )
        pipe.to(device)
        pipe.set_progress_bar_config(desc="wan-ti2v-canary")

        generator = torch.Generator(device=device).manual_seed(SEED)
        print(json.dumps({"event": "generate", **config}), flush=True)
        result = pipe(
            prompt=PROMPT,
            negative_prompt=NEGATIVE_PROMPT,
            height=HEIGHT,
            width=WIDTH,
            num_frames=NUM_FRAMES,
            guidance_scale=GUIDANCE_SCALE,
            num_inference_steps=NUM_INFERENCE_STEPS,
            generator=generator,
        )
        frames = result.frames[0]
        if len(frames) != NUM_FRAMES:
            raise RuntimeError(f"expected {NUM_FRAMES} frames, got {len(frames)}")

        frame_arrays = [np.asarray(frame) for frame in frames]
        validation_arrays = []
        validation_scale = "native"
        for frame in frame_arrays:
            values = frame.astype(np.float32, copy=False)
            if (
                np.issubdtype(frame.dtype, np.floating)
                and float(values.min()) >= 0.0
                and float(values.max()) <= 1.0
            ):
                values = values * 255.0
                validation_scale = "normalized-float-0-1-to-0-255"
            validation_arrays.append(values)
        frame_std = [float(frame.std()) for frame in validation_arrays]
        if not all(np.isfinite(value) for value in frame_std):
            raise RuntimeError("non-finite frame statistics")
        if max(frame_std) < 1.0:
            raise RuntimeError(f"frames appear blank: maximum standard deviation={max(frame_std)}")

        export_to_video(frames, str(output_path), fps=FPS)
        digest = hashlib.sha256(output_path.read_bytes()).hexdigest()
        receipt.update(
            status="generated",
            finished_at_utc=datetime.now(timezone.utc).isoformat(),
            elapsed_seconds=round(time.monotonic() - started, 3),
            output_path=str(output_path),
            output_bytes=output_path.stat().st_size,
            output_sha256=digest,
            produced_frames=len(frames),
            validation_scale=validation_scale,
            frame_std_min=min(frame_std),
            frame_std_max=max(frame_std),
        )
        write_json(receipt_path, receipt)
        print(json.dumps(receipt, ensure_ascii=False), flush=True)
        return 0
    except BaseException as exc:
        receipt.update(
            status="failed",
            finished_at_utc=datetime.now(timezone.utc).isoformat(),
            elapsed_seconds=round(time.monotonic() - started, 3),
            error=repr(exc),
            traceback=traceback.format_exc(),
        )
        write_json(receipt_path, receipt)
        print(json.dumps(receipt, ensure_ascii=False), flush=True)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
