# -*- coding: utf-8 -*-
"""carfac_wrap.py -- Ear3Cochlea: patched-JAX CARFAC v2 front end for Ear v3.

Vendored google/carfac @4cdb95ee with our 5-tap AGC spatial-FIR patch
(patches/0001-jax-5tap-agc.patch), installed into ~/ear-v3/venv. JAX-CPU is
the backend of record (NumPy port proven equivalent: corr 1.000000 at 16 kHz,
test_backend_equiv.py).

Documented choices:

* STATE-LEAK PREVENTION. Every call starts from THE SAME state: the
  design-time initial state advanced through 100 ms of silence ONCE at
  init (the pre-roll state is computed one time and cached -- running the
  identical 1600 zero samples per call cost 8-10 ms/call for bit-identical
  output). The AGC therefore starts every clip from the same
  settled-from-silence condition; no clip can hear the previous clip (the
  v1 search exploited exactly such leaks). The pre-roll NAP is never
  returned.

* SHAPE BUCKETING. run_segment_jit recompiles per input length. Clips are
  zero-padded at the END to the next multiple of BUCKET=1000 samples, so a
  whole corpus costs a bounded set of compilations (persistent compile
  cache in .jax-cache). lax.scan is causal: trailing zero-pad cannot change
  earlier outputs, and the pad's output is cut. A given clip always lands
  in the same bucket, so this costs nothing in determinism.

* SPL. One scalar gain (from ear3-calib.json, computed by calib.py) is
  applied to the samples before the cochlea. Convention (frozen): the median
  t06 big-unit speech-span RMS maps to RMS amplitude 0.05, which we DEFINE as
  65 dB SPL equivalent. Applied identically to disk wavs and mouth renders.

* LOUDNESS. The python port @4cdb95ee has no loudness helper (the Matlab
  CARFAC_loudness was not ported), so we define: per-frame loudness = mean
  over channels of half-wave-rectified NAP, mean-pooled over 10 ms
  non-overlapping windows. Simple, deterministic, and the same quantity BLOCK
  S pools -- the dip a /b/ closure makes is exactly what it must show.
"""
from __future__ import annotations

import os

os.environ.setdefault("JAX_PLATFORMS", "cpu")
_CACHE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".jax-cache")
os.environ.setdefault("JAX_COMPILATION_CACHE_DIR", _CACHE_DIR)

import numpy as np  # noqa: E402
import jax  # noqa: E402
import jax.numpy as jnp  # noqa: E402

try:  # persistent compile cache spares re-JIT across processes; optional
    jax.config.update("jax_compilation_cache_dir",
                      os.environ["JAX_COMPILATION_CACHE_DIR"])
except Exception:  # pragma: no cover - cache is a speed aid, never correctness
    pass

from carfac.jax import carfac as cjax  # noqa: E402

FS_DEFAULT = 16000
PREROLL_S = 0.100          # silent pre-roll (run once, state cached)
BUCKET = 1000              # pad clips to a multiple of this
LOUD_HOP = 160             # 10 ms at 16 kHz


class Ear3Cochlea:
    """Fresh-state CARFAC NAP per call. fs-parameterized (bat headroom = pass
    a higher fs later; nothing here hardcodes 16k except the module default)."""

    def __init__(self, fs=FS_DEFAULT, spl_gain=1.0):
        self.fs = int(fs)
        self.preroll = int(round(PREROLL_S * self.fs))
        self.spl_gain = float(spl_gain)
        params = cjax.CarfacDesignParameters(fs=self.fs)
        self.hypers, self.weights, self.state0 = cjax.design_and_init_carfac(
            params)
        try:
            self.n_ch = int(self.hypers.ears[0].car.n_ch)
        except Exception:
            self.n_ch = None  # discovered on first nap() call
        # Per-channel characteristic frequencies. The JAX hypers do not carry
        # pole_freqs, but a0 = cos(2*pi*CF/fs) by CARFAC construction.
        a0 = np.asarray(self.hypers.ears[0].car.a0_coeffs, dtype=np.float64)
        self.channel_cfs = np.arccos(a0) * self.fs / (2.0 * np.pi)
        # THE pre-roll state: state0 advanced through PREROLL_S of silence,
        # once. Every nap() call starts from this exact pytree.
        out = cjax.run_segment_jit(
            jnp.zeros((self.preroll, 1), dtype=jnp.float32),
            self.hypers, self.weights, self.state0)
        jax.block_until_ready(out.state)
        self.state_preroll = out.state

    def nap(self, samples):
        """float samples in [-1,1] -> NAP (n_samples, n_channels) float64.

        SPL gain applied; starts from the cached post-pre-roll state;
        trailing bucket pad run and cut.
        """
        x = np.asarray(samples, dtype=np.float32) * np.float32(self.spl_gain)
        n = int(x.size)
        pad = (-n) % BUCKET
        buf = np.zeros(n + pad, dtype=np.float32)
        buf[:n] = x
        out = cjax.run_segment_jit(
            jnp.asarray(buf[:, None]), self.hypers, self.weights,
            self.state_preroll)
        nap = np.asarray(jax.device_get(out.naps)).astype(np.float64)
        if nap.ndim == 3:
            nap = nap[..., 0]
        if self.n_ch is None:
            self.n_ch = int(nap.shape[1])
        return nap[:n]

    def nap_and_loudness(self, samples):
        nap = self.nap(samples)
        return nap, loudness(nap)


def loudness(nap, hop=LOUD_HOP):
    """Per-frame loudness: mean over channels of HWR NAP, 10 ms mean-pooled."""
    r = np.maximum(np.asarray(nap, dtype=np.float64), 0.0)
    nf = r.shape[0] // hop
    if nf == 0:
        return np.zeros(0)
    return r[:nf * hop].reshape(nf, hop, r.shape[1]).mean(axis=(1, 2))
