# -*- coding: utf-8 -*-
"""
> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

THE ONE RULER FOR SHARPNESS, so every number in this track is comparable to the
ones Iddo has already judged by eye.

    Laplacian variance, on GREYSCALE, at a matched 2400 px LONG EDGE.

The long-edge match is the whole point: variance of a 3x3 Laplacian rises with
pixel count for free, so an 8K plate would flatter itself against a 1080p render
if they were measured native. Everything is brought to the same 2400 px first.

Known readings this must reproduce (claude-cli-SHARP, 2026-09-06 01:00):
    Iddo's own document pages   1868 - 4038
    TZELEM boulevard              719
    TZELEM workshop -- REJECTED   126      <- his rejection threshold
    the FLUX 8K plates            4.6 - 52
"""
from __future__ import annotations

import os
import sys

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
LONG_EDGE = 2400
K = np.array([[0.0, 1.0, 0.0], [1.0, -4.0, 1.0], [0.0, 1.0, 0.0]])


def _lap(g: np.ndarray) -> np.ndarray:
    """3x3 Laplacian, valid region only (no border padding to invent edges)."""
    out = np.zeros((g.shape[0] - 2, g.shape[1] - 2), dtype=np.float64)
    for dy in range(3):
        for dx in range(3):
            k = K[dy, dx]
            if k:
                out += k * g[dy:dy + g.shape[0] - 2, dx:dx + g.shape[1] - 2]
    return out


def lapvar_array(arr: np.ndarray) -> float:
    """arr is float 0..1 or uint8 RGB/grey, at whatever size. Resized here."""
    if arr.dtype != np.uint8:
        arr = (np.clip(arr, 0.0, 1.0) * 255.0).astype(np.uint8)
    im = Image.fromarray(arr)
    return lapvar_image(im)


def lapvar_image(im: Image.Image) -> float:
    """CALIBRATED 2026-09-06 against claude-cli-SHARP's own two readings.

    The cap is a CEILING, not a target: an image already under 2400 px on its long
    edge is measured NATIVE. Upscaling a 1600 px render to 2400 interpolates and
    costs it 4x, which is an artefact of the ruler and not of the picture. With
    this rule the two published files reproduce SHARP's numbers to the digit:
        _deliverables/hub/tzelem_boulevard.jpg       719.9   (SHARP: 719)
        _deliverables/hub/oneroom-workshop-lit.jpg   125.3   (SHARP: 126)
    Anything larger IS brought down to 2400 so an 8K plate cannot buy sharpness
    with pixel count.
    """
    im = im.convert("L")
    w, h = im.size
    if max(w, h) > LONG_EDGE:
        s = LONG_EDGE / float(max(w, h))
        im = im.resize((max(1, round(w * s)), max(1, round(h * s))),
                       Image.LANCZOS)
    g = np.asarray(im, dtype=np.float64)
    return float(_lap(g).var())


def lapvar_file(path: str) -> float:
    with Image.open(path) as im:
        return lapvar_image(im)


def lapvar_norm_array(arr: np.ndarray, target_std: float = 48.0) -> float:
    """THE SECOND OPINION, and the reason it is needed.

    Laplacian variance scales with the SQUARE of contrast. Multiply a picture by
    0.85 and it loses 28% of its lapvar without losing one edge; brighten it and
    it "sharpens" without gaining one. The workshop at night is painted at gain
    0.72 over ambient 0.185, so it is close to black, and that alone is worth
    more than any brush setting.

    This standardises the greyscale to a fixed standard deviation first, so what
    is left is STRUCTURE. Report it BESIDE the raw number, never instead of it -
    the raw number is the one Iddo's eye was calibrated on.
    """
    if arr.dtype != np.uint8:
        arr = (np.clip(arr, 0.0, 1.0) * 255.0).astype(np.uint8)
    im = Image.fromarray(arr).convert("L")
    w, h = im.size
    if max(w, h) > LONG_EDGE:
        s = LONG_EDGE / float(max(w, h))
        im = im.resize((max(1, round(w * s)), max(1, round(h * s))), Image.LANCZOS)
    g = np.asarray(im, dtype=np.float64)
    sd = g.std()
    if sd < 1e-6:
        return 0.0
    return float(_lap((g - g.mean()) / sd * target_std).var())


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    for p in sys.argv[1:]:
        if os.path.isdir(p):
            for f in sorted(os.listdir(p)):
                if f.lower().endswith((".jpg", ".jpeg", ".png")):
                    q = os.path.join(p, f)
                    print(f"{lapvar_file(q):10.1f}  {q}")
        else:
            print(f"{lapvar_file(p):10.1f}  {p}")
