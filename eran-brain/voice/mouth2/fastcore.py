# -*- coding: utf-8 -*-
"""fastcore.py -- ctypes wrapper for voc_eran.c, the fast C twin.

THE REFERENCE IS THE TRUTH. This module prepares EXACTLY the inputs the
reference pipeline (glottis.GlottalSource.render -> tract_core.render)
would consume, hands them to the C core, and returns the 48 kHz
lip/nose signals. Decimation and peak-normalization stay in mouth2.py,
shared verbatim between backends.

THE NOISE CONTRACT (why parity is possible without PCG64 in C)
==============================================================
numpy's PCG64 is not reimplemented in C. All draws are made HERE with
glottis.stream_rng (seed + 1000*k) in the reference's documented order:

  jitter/shimmer/drift  one standard_normal per period -> pre-drawn as
                        blocks of max_p = n//4 + 2 (n_p >= 4 always, so
                        the reference can never consume more). VERIFIED
                        2026-08-26: numpy block draws are bit-identical
                        to repeated scalar draws on the same stream.
  vibrato               uniform() -> rate, uniform() -> phase (2 draws)
  aspiration            uniform() -> flutter phase, then
                        standard_normal(n) in one block
  turbulence            standard_normal(n) in one block

The flutter VECTOR (0.2 + 0.02*sin(2*pi*1.99*t + phase)) is computed
here with the reference's own numpy expression, so it is bit-identical.
Envelope/contour prep is not duplicated either: a GlottalSource is
constructed and its .log_f0/.ten_env/.int_env are read -- the same
arrays the reference integrates over.

All derived scalar constants (one-pole coefficients, round-trip loss)
are computed with the reference's exact expressions and passed in as
doubles, so the C core does no constant derivation of its own.

Build: build.sh (eran2, gcc -O2 -fPIC -ffp-contract=off) / build.ps1
(PC, only if a real gcc exists). -ffp-contract=off is REQUIRED: a fused
multiply-add changes bits and the parity gate is a bit-level diff.
"""
from __future__ import annotations

import ctypes
import os

import numpy as np

import glottis as G
import tract_core as T

_HERE = os.path.dirname(os.path.abspath(__file__))
_LIB_NAMES = ("voc_eran.dll", "libvoc_eran.so", "libvoc_eran.dylib")

_lib = None


def _load():
    global _lib
    if _lib is not None:
        return _lib
    last = None
    for name in _LIB_NAMES:
        p = os.path.join(_HERE, name)
        if os.path.exists(p):
            try:
                _lib_try = ctypes.CDLL(p)
                break
            except OSError as e:            # pragma: no cover
                last = e
    else:
        raise RuntimeError(
            "voc_eran library not found next to fastcore.py (looked for "
            "%s in %s). Build it: ./build.sh (eran2) or build.ps1 (PC). "
            "Last load error: %r" % (", ".join(_LIB_NAMES), _HERE, last))
    if _lib_try.mouth2_abi_version() != 2:
        raise RuntimeError("voc_eran ABI mismatch: rebuild the library")
    d = np.ctypeslib.ndpointer(dtype=np.float64, flags="C_CONTIGUOUS")
    _lib_try.mouth2_render_c.restype = ctypes.c_int
    _lib_try.mouth2_render_c.argtypes = [
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, ctypes.c_int,
        d, d, d,                    # area_track, velum_track, nasal_areas
        d, d, d, d,                 # log_f0, ten_env, int_env, flutter
        d, d, d, ctypes.c_int,      # jit, shm, drf, max_p
        ctypes.c_double, ctypes.c_double,   # vib_rate, vib_phase
        d, d,                       # asp_white, turb_white
        d, ctypes.c_int,            # cst, n_cst
        d, d,                       # lip_out, nose_out
    ]
    _lib = _lib_try
    return _lib


def available():
    try:
        _load()
        return True
    except RuntimeError:
        return False


# constant-vector indices -- MUST mirror the enum in voc_eran.c
_N_CONSTS = 24


def _consts(N, M, sr):
    """Every derived scalar, computed with the REFERENCE's expressions."""
    c = np.empty(_N_CONSTS, dtype=np.float64)
    c[0] = float(sr)
    c[1] = G.JITTER_DEFAULT
    c[2] = G.SHIMMER_DEFAULT
    c[3] = G.DRIFT_SIGMA
    c[4] = G.DRIFT_CLIP
    c[5] = G.DRIFT_POLE_HZ
    c[6] = G.VIBRATO_SEMITONES
    c[7] = float(np.exp(-2.0 * np.pi * G.ASPIRATION_TILT_HZ / sr))
    c[8] = float(np.exp(-2.0 * np.pi * T.HF_POLE_HZ / sr))
    c[9] = T.GLOTTAL_REFLECT
    c[10] = T.LIP_REFLECT
    c[11] = T.ROUND_TRIP_GAIN ** (1.0 / (T._RT_PER_SECTION * N))
    c[12] = T.ROUND_TRIP_GAIN ** (1.0 / (T._RT_PER_SECTION * M))
    c[13] = T.AREA_FLOOR
    c[14] = T.AREA_SEAL
    c[15] = T.VELUM_LEAK
    c[16] = T.BURST_GAIN
    c[17] = T.PRESSURE_RATE
    c[18] = T.BURST_DECAY
    c[19] = T.BURST_OPEN_REF
    c[20] = T.TURB_GAIN
    c[21] = float(np.exp(-2.0 * np.pi * T.TURB_LP_HZ / sr))
    c[22] = float(np.exp(-2.0 * np.pi * T.TURB_HP_HZ / sr))
    c[23] = T.DC_POLE
    return c


def render_c(area_track, velum_track, seconds, f0_knots, ten_knots, seed,
             nasal_areas, intensity_env=None, tenseness_env=None):
    """The C-backend twin of mouth2._render's glottis+tract stage.

    Same arguments as the reference path assembles; returns (lip48,
    nose48) float64 at the internal rate. The caller decimates and
    normalizes exactly as for the reference backend."""
    lib = _load()
    sr = T.FS_INTERNAL
    # envelope/contour prep: the reference's own constructor, no rewrite
    src = G.GlottalSource(f0_knots, ten_knots, seconds, sr, seed,
                          intensity_env=intensity_env,
                          tenseness_env=tenseness_env)
    n = src.n
    area_track = np.ascontiguousarray(area_track, dtype=np.float64)
    velum_track = np.ascontiguousarray(velum_track, dtype=np.float64)
    nasal_areas = np.ascontiguousarray(nasal_areas, dtype=np.float64)
    n_blocks, N = area_track.shape
    M = nasal_areas.size
    jn = int(np.clip(round((17.0 / 44.0) * N), 1, N - 2))
    i0c = int(np.ceil(0.30 * N - 0.5))
    block = int(round(T.BLOCK_S * sr))
    n = min(n, n_blocks * block)     # tract_core.render's own truncation

    # ---- the noise contract: draw everything here, documented order ----
    seed = int(seed)
    max_p = n // 4 + 2
    jit = G.stream_rng(seed, "jitter").standard_normal(max_p)
    shm = G.stream_rng(seed, "shimmer").standard_normal(max_p)
    drf = G.stream_rng(seed, "drift").standard_normal(max_p)
    rng_v = G.stream_rng(seed, "vibrato")
    vib_rate = G.VIBRATO_RATE_LO + rng_v.uniform() * (G.VIBRATO_RATE_HI
                                                      - G.VIBRATO_RATE_LO)
    vib_phase = rng_v.uniform() * 2.0 * np.pi
    rng_a = G.stream_rng(seed, "aspiration")
    flutter_phase = rng_a.uniform() * 2.0 * np.pi
    asp_white = rng_a.standard_normal(n)
    turb_white = G.stream_rng(seed, "turbulence").standard_normal(n)
    t = np.arange(n) / sr
    flutter = 0.2 + 0.02 * np.sin(2.0 * np.pi * 1.99 * t + flutter_phase)

    log_f0 = np.ascontiguousarray(src.log_f0[:n], dtype=np.float64)
    ten_env = np.ascontiguousarray(src.ten_env[:n], dtype=np.float64)
    int_env = np.ascontiguousarray(src.int_env[:n], dtype=np.float64)

    lip = np.empty(n, dtype=np.float64)
    nose = np.empty(n, dtype=np.float64)
    rc = lib.mouth2_render_c(
        n, n_blocks, block, N, M, jn, i0c,
        area_track, velum_track, nasal_areas,
        log_f0, ten_env, int_env, np.ascontiguousarray(flutter),
        np.ascontiguousarray(jit), np.ascontiguousarray(shm),
        np.ascontiguousarray(drf), max_p,
        float(vib_rate), float(vib_phase),
        np.ascontiguousarray(asp_white), np.ascontiguousarray(turb_white),
        _consts(N, M, sr), _N_CONSTS,
        lip, nose)
    if rc != 0:
        raise RuntimeError("mouth2_render_c failed with code %d" % rc)
    return lip, nose


if __name__ == "__main__":
    print("fastcore self-check: library %s"
          % ("LOADED" if available() else "NOT BUILT (run build.sh/.ps1)"))
