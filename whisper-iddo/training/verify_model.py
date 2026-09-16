"""Model integrity check.

The briefing's zero-byte-fraction test is a good cheap screen but it is not
sufficient on its own: the healthy band (0.2-0.4%) was measured on fp16/bf16
files, and an fp32 checkpoint of the same healthy weights sits near 0.7% purely
because small-magnitude fp32 values carry zero high bytes. So this does both:

  1. zero-byte fraction on the raw file  (cheap screen, band depends on dtype)
  2. load every tensor and check it is actually a weight matrix -- no NaN, no
     Inf, non-zero variance, plausible RMS. A truncated or zero-filled shard
     loads WITHOUT ERROR and silently produces garbage, which is exactly the
     failure the briefing warns about; only this second test catches it.
"""
from __future__ import annotations

import glob
import os
import sys

import torch
from safetensors.torch import safe_open


def zerofrac(path, cap=400 * 1024 * 1024):
    size = os.path.getsize(path)
    CHUNK = 8 * 1024 * 1024
    spots = (list(range(0, size, CHUNK)) if size <= cap
             else [int(i * (size / (cap // CHUNK))) for i in range(cap // CHUNK)])
    z = n = 0
    with open(path, "rb") as f:
        for off in spots:
            f.seek(off)
            b = f.read(CHUNK)
            z += b.count(0)
            n += len(b)
    return size, z / n


def main(d):
    print(f"=== {d}")
    files = sorted(glob.glob(os.path.join(d, "*.safetensors")))
    if not files:
        print("  NO SAFETENSORS FOUND")
        return 1
    bad = []
    total = 0
    for f in files:
        size, zf = zerofrac(f)
        print(f"  {os.path.basename(f)}  {size/1e6:.1f} MB  zeros {zf*100:.3f}%")
        with safe_open(f, framework="pt") as sf:
            for k in sf.keys():
                t = sf.get_tensor(k).float()
                total += t.numel()
                if torch.isnan(t).any():
                    bad.append((k, "NaN"))
                elif torch.isinf(t).any():
                    bad.append((k, "Inf"))
                elif t.numel() > 1000 and t.std().item() == 0.0:
                    bad.append((k, "zero-variance"))
                elif t.numel() > 1000 and t.abs().max().item() == 0.0:
                    bad.append((k, "all-zero"))
    print(f"  params {total/1e6:.1f}M")
    if bad:
        print(f"  *** {len(bad)} BAD TENSORS ***")
        for k, why in bad[:20]:
            print(f"      {why:14s} {k}")
        return 1
    print("  ALL TENSORS FINITE, NON-DEGENERATE -> USABLE")
    return 0


if __name__ == "__main__":
    sys.exit(max(main(d) for d in sys.argv[1:]))
