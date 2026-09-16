#!/usr/bin/env python3
"""Runs ON a DGX box.  PNG frames -> Real-ESRGAN x4 -> exact 3840x2160 -> mp4.

Kept on the box on purpose: a 4x frame is 6144x3456, and pushing 1552 of those
over the wire to assemble on the PC would cost more than the render did.  Only
the finished per-shot 4K mp4 travels.

Usage:  upscale_dgx.py <shot_id> [<shot_id> ...]
"""
from __future__ import annotations

import subprocess
import time
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from spandrel import ModelLoader

HOME = Path.home()
SRC = HOME / "comfy" / "output" / "almido"
DST = HOME / "almido_4k"
MODEL = HOME / "comfy" / "models" / "upscale_models" / "RealESRGAN_x4plus.pth"
OUT_W, OUT_H = 3840, 2160
FPS = 24

DEV = "cuda" if torch.cuda.is_available() else "cpu"
DTYPE = torch.float16 if DEV == "cuda" else torch.float32  # 4.65 vs 8.97 s/frame
_model = None


def model():
    global _model
    if _model is None:
        _model = ModelLoader().load_from_file(str(MODEL)).eval().to(DEV)
        _model = _model.model.to(DTYPE)
    return _model


@torch.inference_mode()
def frame_bytes(img: Image.Image) -> bytes:
    """PNG -> ESRGAN x4 -> exact 3840x2160 -> raw rgb24, all on the GPU.

    Doing the downscale with PIL instead costs a 254 MB device->host copy and a
    21 MP LANCZOS resize per frame on the ARM cores; measured, that turned a
    4.6 s/frame job into one that had not finished a single shot in ten minutes.
    """
    t = torch.from_numpy(np.asarray(img, dtype=np.uint8))
    t = t.permute(2, 0, 1).unsqueeze(0).to(DEV).to(DTYPE).div_(255.0)
    big = model()(t).clamp_(0, 1)

    _, _, h, w = big.shape
    s = max(OUT_W / w, OUT_H / h)
    nw, nh = max(OUT_W, round(w * s)), max(OUT_H, round(h * s))
    big = torch.nn.functional.interpolate(
        big.float(), size=(nh, nw), mode="bicubic",
        align_corners=False, antialias=True).clamp_(0, 1)
    top, left = (nh - OUT_H) // 2, (nw - OUT_W) // 2
    big = big[:, :, top:top + OUT_H, left:left + OUT_W]

    out = big.mul_(255).round_().to(torch.uint8).squeeze(0).permute(1, 2, 0)
    return out.contiguous().cpu().numpy().tobytes()


def do_shot(spec: str) -> None:
    shot, _, limit = spec.partition(":")
    frames = sorted((SRC / shot).glob("*.png"))
    if limit:
        frames = frames[: int(limit)]
    if not frames:
        print(f"  !! {shot}: no frames", flush=True)
        return
    DST.mkdir(exist_ok=True)
    dest = DST / f"{shot}.mp4"
    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{OUT_W}x{OUT_H}", "-r", str(FPS), "-i", "pipe:0",
         "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "16",
         "-pix_fmt", "yuv420p", str(dest)],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    t0 = time.time()
    for i, f in enumerate(frames):
        ff.stdin.write(frame_bytes(Image.open(f).convert("RGB")))
        if i % 12 == 0:
            el = time.time() - t0
            print(f"    {shot} {i}/{len(frames)}  {el/max(1,i):.2f}s/frame", flush=True)
    ff.stdin.close()
    ff.wait()
    print(f"  [4k] {shot}: {len(frames)} frames -> {dest}", flush=True)


if __name__ == "__main__":
    for s in sys.argv[1:]:
        do_shot(s)
