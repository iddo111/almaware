# -*- coding: utf-8 -*-
"""The ants' eye — a deterministic numpy retina (the visual cochlea).

Same philosophy as feature_space.py for sound: a sight-frame is a pure
function of pixels. No label, no learning, no state — two ants that never
share weights still agree on what a glimpse *is*. Learning happens only in
the sight-codebook (random real glimpses, the farm's honest kind) and in the
Hebbian binding (holobrain.py), never in the eye itself.

Feature vector, 50 dims per 48x48 grayscale image:
    36  6x6 mean-pooled ink map (ink = darkness on white paper)
     8  gradient-orientation histogram (unsigned, magnitude-weighted)
     4  ink projection profiles: row/column centroid + spread
     2  ink density, bounding-box aspect
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

SIDE = 48
GRID = 6
ORI_BINS = 8
DIM = GRID * GRID + ORI_BINS + 4 + 2   # 50


def load_image(path: Path) -> np.ndarray:
    """Any image file -> float32 (SIDE, SIDE) in [0, 1], white background."""
    from PIL import Image
    with Image.open(path) as im:
        g = im.convert("L").resize((SIDE, SIDE), Image.BILINEAR)
        return np.asarray(g, dtype=np.float32) / 255.0


def glimpse(image: np.ndarray) -> np.ndarray:
    """(SIDE, SIDE) grayscale in [0, 1] -> (DIM,) float32 sight-frame."""
    if image.shape != (SIDE, SIDE):
        raise ValueError(f"retina expects {SIDE}x{SIDE}, got {image.shape}")
    ink = 1.0 - image                                   # dark strokes = ink

    # 6x6 mean-pooled ink map
    block = SIDE // GRID
    pooled = ink.reshape(GRID, block, GRID, block).mean(axis=(1, 3))

    # unsigned gradient-orientation histogram, magnitude-weighted
    gy, gx = np.gradient(ink)
    mag = np.hypot(gx, gy)
    ori = np.mod(np.arctan2(gy, gx), np.pi)            # [0, pi)
    bins = np.minimum((ori / np.pi * ORI_BINS).astype(int), ORI_BINS - 1)
    hist = np.zeros(ORI_BINS)
    np.add.at(hist, bins.ravel(), mag.ravel())
    hist /= max(hist.sum(), 1e-9)

    # projection profiles: where the ink sits and how spread it is
    total = max(ink.sum(), 1e-9)
    rows = ink.sum(axis=1) / total
    cols = ink.sum(axis=0) / total
    axis = np.arange(SIDE) / SIDE
    r_mu, c_mu = float(rows @ axis), float(cols @ axis)
    r_sd = float(np.sqrt(rows @ (axis - r_mu) ** 2))
    c_sd = float(np.sqrt(cols @ (axis - c_mu) ** 2))

    # density + bounding-box aspect
    density = float(ink.mean())
    on = ink > 0.15
    if on.any():
        ys, xs = np.nonzero(on)
        h = ys.max() - ys.min() + 1
        w = xs.max() - xs.min() + 1
        aspect = float(np.clip(h / max(w, 1), 0.25, 4.0)) / 4.0
    else:
        aspect = 0.25
    return np.concatenate([
        pooled.ravel(), hist, [r_mu, r_sd, c_mu, c_sd], [density, aspect],
    ]).astype(np.float32)


def glimpse_file(path: Path) -> np.ndarray:
    return glimpse(load_image(path))


def sight_codebook(train_glimpses: np.ndarray, k: int = 64,
                   seed: int = 7007) -> tuple[np.ndarray, np.ndarray]:
    """Random real glimpses (the farm's honest codebook kind) + scaler.

    Returns (centers_scaled, scaler). Encode a glimpse with
    acoustic_units.encode(g / scaler, centers_scaled).
    """
    x = np.asarray(train_glimpses, dtype=np.float32)
    scaler = np.maximum(x.astype(np.float64).std(axis=0), 1e-6
                        ).astype(np.float32)
    rng = np.random.default_rng(seed)
    centers = (x[rng.choice(len(x), k, replace=False)] / scaler
               ).astype(np.float32)
    return centers, scaler
