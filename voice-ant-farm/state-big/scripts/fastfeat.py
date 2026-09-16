# -*- coding: utf-8 -*-
"""Batched re-implementation of acoustic_units.features().

The reference implementation loops one frame at a time in Python. At 253 s that
is fine; at 40.6 h it is 14.6 M frames and would dominate the run. This produces
the identical 14-dim feature (log energy, ZCR, 12 log spectral bands) with the
same 25 ms / 10 ms geometry, computed as whole-array numpy.

verify() checks it against the reference on real files -- if that assert ever
fails, every number downstream is measured on a different feature space than
state/ was, and the comparison is void.
"""
from __future__ import annotations

import sys
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

RATE = 16000
FRAME = 400          # 25 ms
HOP = 160            # 10 ms
NBINS = FRAME // 2 + 1
_SPLITS = np.array_split(np.arange(NBINS), 12)
_BAND_EDGES = np.array([s[0] for s in _SPLITS] + [NBINS])
_WINDOW = np.hanning(FRAME).astype(np.float32)


def read_pcm16(path: str) -> tuple[np.ndarray, int]:
    with wave.open(path, "rb") as w:
        if w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise ValueError(f"{path}: expected mono 16-bit PCM")
        rate = w.getframerate()
        pcm = w.readframes(w.getnframes())
    return np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768, rate


def frames_of(samples: np.ndarray) -> np.ndarray:
    n = 1 + (len(samples) - FRAME) // HOP
    if n <= 0:
        return np.zeros((0, FRAME), dtype=np.float32)
    return np.lib.stride_tricks.sliding_window_view(samples, FRAME)[::HOP][:n]


def features_batch(samples: np.ndarray, chunk: int = 8192) -> np.ndarray:
    V = frames_of(samples)
    if len(V) == 0:
        return np.zeros((0, 14), dtype=np.float32)
    out = np.empty((len(V), 14), dtype=np.float32)
    for s in range(0, len(V), chunk):
        b = V[s:s + chunk] * _WINDOW
        energy = np.log(np.mean(b * b, axis=1).astype(np.float64) + 1e-8)
        sb = np.signbit(b)
        zcr = np.mean(sb[:, 1:] != sb[:, :-1], axis=1)
        spec = np.abs(np.fft.rfft(b, axis=1)).astype(np.float64) + 1e-8
        spec /= spec.sum(axis=1, keepdims=True)
        cum = np.concatenate([np.zeros((len(b), 1)), np.cumsum(spec, axis=1)], axis=1)
        bands = np.log(cum[:, _BAND_EDGES[1:]] - cum[:, _BAND_EDGES[:-1]] + 1e-8)
        out[s:s + chunk, 0] = energy
        out[s:s + chunk, 1] = zcr
        out[s:s + chunk, 2:] = bands
    return out


def verify(paths: list[str], tol: float = 2e-4) -> None:
    """Assert equality with the reference implementation on real audio."""
    from acoustic_units import features, load_wav
    worst = 0.0
    for p in paths:
        ref, _ = features(load_wav(Path(p)))
        got = features_batch(read_pcm16(p)[0])
        assert ref.shape == got.shape, f"{p}: shape {ref.shape} vs {got.shape}"
        d = float(np.abs(ref - got).max())
        worst = max(worst, d)
        assert d < tol, f"{p}: max abs diff {d}"
    print(f"fastfeat verified against acoustic_units.features on {len(paths)} files; "
          f"worst abs diff {worst:.2e}")


if __name__ == "__main__":
    verify(sys.argv[1:])
