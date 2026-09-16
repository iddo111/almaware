# -*- coding: utf-8 -*-
"""fastseq.py -- mouth34.say_sequence, made fast, and NEVER trusted unverified.

mouth34.say_sequence renders a moving tube with a pure-Python sample loop: an
order-35 dot product 17,500 times a second of audio. Correct, and the TRUTH --
but a 48-hour population search lives or dies on evaluations per second.

THE FAST PATH. scipy.signal.lfilter([1], A, x) IS the direct-form all-pole
recursion, and scipy.signal.lfiltic([1], A, y_history) builds exactly the
initial conditions that continue a recursion from past OUTPUTS. So each 1 ms
coefficient block (same block size, same mid-block coefficient choice as the
reference) is filtered in C, with the y-history carried across block
boundaries precisely the way the reference loop carries it.

THE CONTRACT, in the project's own words (mouth34.py): "Speed that is not
proven equal to the truth is not speed, it is a different animal." verify()
renders random trajectories through BOTH paths and demands float-noise
agreement; sanity0.py runs it before any worker is launched, and run_worker.py
refuses the fast path if the verdict file says it failed.
"""
from __future__ import annotations

import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import mouth34                                   # noqa: E402

try:
    from scipy.signal import lfilter as _lfilter, lfiltic as _lfiltic
except Exception:                                # pragma: no cover
    _lfilter = None
    _lfiltic = None

HAVE_SCIPY = _lfilter is not None


def say_sequence_fast(keyframes, f0=220.0, seed=0, glide_frac=0.35,
                      glottal_reflect=mouth34.GLOTTAL_REFLECT,
                      lip_reflect=mouth34.LIP_REFLECT, sr=mouth34.SR):
    """Same trajectory, same blocks, same refusals as mouth34.say_sequence."""
    if not HAVE_SCIPY:
        return mouth34.say_sequence(keyframes, f0=f0, seed=seed,
                                    glide_frac=glide_frac,
                                    glottal_reflect=glottal_reflect,
                                    lip_reflect=lip_reflect, sr=sr)
    frames = [(np.asarray(a, dtype=float), float(s)) for a, s in keyframes]
    if not frames:
        return None
    total = sum(s for _, s in frames)
    if total <= 0:
        return None
    n_total = int(mouth34.TRACT_FS * total)
    if n_total < 8:
        return None
    src = mouth34.glottis(n_total, f0, sr=mouth34.TRACT_FS,
                          rng=np.random.default_rng(seed))

    # Per-sample area trajectory -- verbatim construction from the reference.
    traj = np.zeros((n_total, frames[0][0].size))
    prev = frames[0][0]
    t0 = 0
    for areas, secs in frames:
        n = min(max(1, int(mouth34.TRACT_FS * secs)), n_total - t0)
        if n <= 0:
            break
        g = max(1, int(n * glide_frac))
        w = np.clip(np.arange(n) / float(g), 0.0, 1.0)[:, None]
        traj[t0:t0 + n] = prev[None, :] * (1 - w) + areas[None, :] * w
        prev = areas
        t0 += n
    if t0 < n_total:
        traj[t0:] = prev

    block = max(1, int(mouth34.TRACT_FS * 0.001))
    y = np.zeros(n_total)
    b_num = np.array([1.0])
    order = None
    for b0 in range(0, n_total, block):
        b1 = min(n_total, b0 + block)
        A = mouth34.coefficients(traj[(b0 + b1) // 2],
                                 glottal_reflect, lip_reflect)
        if A is None:
            return None
        if order is None:
            order = A.size - 1
        m = min(order, b0)
        if m:
            zi = _lfiltic(b_num, A, y[b0 - 1::-1][:m])
        else:
            zi = np.zeros(order)
        y[b0:b1], _ = _lfilter(b_num, A, src[b0:b1], zi=zi)
    if not np.all(np.isfinite(y)) or float(np.max(np.abs(y))) > mouth34.DIVERGENCE:
        return None
    return mouth34._finish(y, total, sr)


def verify(n_traj=5, seed=123):
    """Fast path vs the verbatim reference on random trajectories.

    Returns dict(ok, max_abs_diff, speedup). ok demands agreement to float
    noise relative to the waveform's own scale (peak 0.7 after _finish).
    """
    import time
    rng = np.random.default_rng(seed)
    worst = 0.0
    t_ref = t_fast = 0.0
    for _ in range(n_traj):
        v = rng.uniform(0.4, 3.0, mouth34.N_SECTIONS)
        kf = [(v, 0.15),
              (mouth34.closed_lips(v, 4, float(rng.uniform(0.01, 0.1))),
               float(rng.uniform(0.04, 0.12))),
              (np.clip(v + rng.normal(0, 0.2, v.size),
                       mouth34.AREA_MIN, mouth34.AREA_MAX), 0.15)]
        t0 = time.perf_counter()
        yr = mouth34.say_sequence(kf, f0=220.0, seed=0)
        t_ref += time.perf_counter() - t0
        t0 = time.perf_counter()
        yf = say_sequence_fast(kf, f0=220.0, seed=0)
        t_fast += time.perf_counter() - t0
        if (yr is None) != (yf is None):
            return {"ok": False, "max_abs_diff": float("inf"),
                    "speedup": 0.0, "why": "refusal mismatch"}
        if yr is None:
            continue
        worst = max(worst, float(np.max(np.abs(yr - yf))))
    return {"ok": bool(worst < 1e-6), "max_abs_diff": worst,
            "speedup": (t_ref / t_fast) if t_fast > 0 else float("inf")}
