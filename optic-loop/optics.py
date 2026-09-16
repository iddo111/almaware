"""
optics.py — THE OPTICS BLOCK, and nothing else.

This module is deliberately the only place in the codebase that touches the
signal between "a frame was just captured" and "a frame is about to be shown
again". Everything in here is a software stand-in for a physical component:

    blur          <- a lens / diffraction-limited PSF
    weight        <- a fixed transparency mask, or a Malus-law polariser pair
    threshold     <- the OASLM / saturable absorber (the nonlinearity)
    gain_decay    <- source amplification and per-pass optical loss
    shift_rotate  <- mirror/camera misalignment (physically inevitable)

If Iddo ever builds the real photoconductor+LC sandwich (the OASLM), the
upgrade path is: delete the call to `threshold()` in `apply_optics` and let
real light do it between two physical planes. Nothing else in this repo
should need to change. That is the entire reason this file exists apart from
loop.py — see SIMULATE.md for which parts are physically real and which are
simulated here.

All frames are float32 numpy arrays in [0, 1], any shape (H, W).
"""
from __future__ import annotations

import dataclasses
import numpy as np
import cv2


@dataclasses.dataclass
class OpticsConfig:
    # --- blur: lens / diffraction ---
    blur_ksize: int = 5          # odd, 0 disables
    blur_sigma: float = 1.2

    # --- weight: transparency mask or Malus polariser pair ---
    weight_mode: str = "fixed"   # "none" | "fixed" | "malus"
    malus_theta_deg: float = 20.0  # polariser angle mismatch (uniform, global)

    # --- threshold: the nonlinearity (the OASLM stand-in) ---
    threshold_mode: str = "sigmoid"  # "sigmoid" | "hard" | "off"
    threshold_k: float = 12.0
    threshold_bias: float = 0.5

    # --- gain / decay: source amplification, per-pass loss ---
    gain: float = 1.15
    decay: float = 0.08           # fractional loss per pass, in [0,1)

    # --- shift/rotate: mirror misalignment ---
    shift_dx: float = 0.0
    shift_dy: float = 0.0
    rotate_deg: float = 0.0


def make_fixed_mask(shape: tuple[int, int], seed: int) -> np.ndarray:
    """A smooth, deterministic transparency mask in [0.4, 1.0].

    Stands in for a physical transparency: fixed, spatially-varying
    attenuation that light passes through every single pass. Built by
    heavily blurring seeded noise so it has no pixel-scale structure of
    its own (it should not be mistaken for information the loop is
    computing — it is a fixed piece of "glass").
    """
    rng = np.random.default_rng(seed)
    raw = rng.random(shape, dtype=np.float64).astype(np.float32)
    k = max(3, (min(shape) // 4) | 1)  # odd kernel, scale with image
    smooth = cv2.GaussianBlur(raw, (k, k), 0)
    smooth -= smooth.min()
    smooth /= max(smooth.max(), 1e-6)
    return (0.4 + 0.6 * smooth).astype(np.float32)


def _blur(frame: np.ndarray, cfg: OpticsConfig) -> np.ndarray:
    if cfg.blur_ksize <= 0:
        return frame
    k = cfg.blur_ksize | 1  # force odd
    return cv2.GaussianBlur(frame, (k, k), cfg.blur_sigma)


def _weight(frame: np.ndarray, cfg: OpticsConfig, mask: np.ndarray | None) -> np.ndarray:
    if cfg.weight_mode == "none":
        return frame
    if cfg.weight_mode == "malus":
        theta = np.deg2rad(cfg.malus_theta_deg)
        return frame * (np.cos(theta) ** 2)
    if cfg.weight_mode == "fixed":
        if mask is None:
            raise ValueError("weight_mode='fixed' requires a mask; call make_fixed_mask() first")
        return frame * mask
    raise ValueError(f"unknown weight_mode {cfg.weight_mode!r}")


def _threshold(frame: np.ndarray, cfg: OpticsConfig) -> np.ndarray:
    if cfg.threshold_mode == "off":
        return frame  # linear-optics ablation: identity, no nonlinearity at all
    if cfg.threshold_mode == "hard":
        return (frame > cfg.threshold_bias).astype(np.float32)
    if cfg.threshold_mode == "sigmoid":
        x = cfg.threshold_k * (frame - cfg.threshold_bias)
        return 1.0 / (1.0 + np.exp(-x))
    raise ValueError(f"unknown threshold_mode {cfg.threshold_mode!r}")


def _gain_decay(frame: np.ndarray, cfg: OpticsConfig) -> np.ndarray:
    return frame * cfg.gain * (1.0 - cfg.decay)


def _shift_rotate(frame: np.ndarray, cfg: OpticsConfig) -> np.ndarray:
    if cfg.shift_dx == 0 and cfg.shift_dy == 0 and cfg.rotate_deg == 0:
        return frame
    h, w = frame.shape[:2]
    center = (w / 2.0, h / 2.0)
    M = cv2.getRotationMatrix2D(center, cfg.rotate_deg, 1.0)
    M[0, 2] += cfg.shift_dx
    M[1, 2] += cfg.shift_dy
    return cv2.warpAffine(frame, M, (w, h), borderMode=cv2.BORDER_REPLICATE)


def apply_optics(frame: np.ndarray, cfg: OpticsConfig, mask: np.ndarray | None = None) -> np.ndarray:
    """The one function that stands in for "put light through hardware".

    Order: blur -> weight -> threshold -> gain/decay -> shift/rotate -> clip.
    This ordering matches the physical stack top to bottom (lens first,
    then the mask/polariser, then the OASLM, then whatever the source and
    losses do, then any mechanical misalignment on the way back to the
    sensor/panel).
    """
    out = frame.astype(np.float32, copy=True)
    out = _blur(out, cfg)
    out = _weight(out, cfg, mask)
    out = _threshold(out, cfg)
    out = _gain_decay(out, cfg)
    out = _shift_rotate(out, cfg)
    return np.clip(out, 0.0, 1.0).astype(np.float32)
