# -*- coding: utf-8 -*-
"""pitch.py -- BLOCK P: SAI pitchogram features from the vendored repo's sai.py.

Uses carfac.sai.SAI (python/src/carfac/sai.py, the repo's own port) on the
NAP. Documented choices, all frozen in features.FEATURE_SPEC:

* NO NAP DECIMATION. The plan's named contingency (2:1 decimation before
  SAI) was MEASURED and found unnecessary: with the SAI restricted to the
  speech span and to CF >= 140 Hz channels, decim=2 vs decim=1 differ by
  ~1 ms (the Python channel loop dominates, not vector length), and decim=1
  tracks slightly better (render vf 0.88 vs 0.76 at 220 Hz). PITCH_DECIM
  stays a spec'd parameter; 1 is the frozen value.

* SAI GEOMETRY. Past lags only (future_lags=0, so the trigger sits at the
  LAST column; lag = sai_width-1-col). sai_width covers the 60 Hz period;
  20 ms hop (input_segment_width) -> one SAI frame per 20 ms; trigger window
  = the repo constraint's minimum practical value > sai_width; 2 triggers per
  frame (the repo test default).

* SPEECH-SPAN-ONLY. The SAI runs from one buffer-width before the speech span
  to its end (buffer warm-up included), never over leading/trailing silence.
  Deterministic: the span itself is deterministic.

* SALIENCE / VOICING. Per frame: temporal profile = mean over channels of the
  SAI frame; salience = profile(best lag in 60-420 Hz) / profile(lag 0).
  Voiced iff salience >= VOICED_SALIENCE AND profile(lag 0) >= P0_MIN (an
  ABSOLUTE floor -- legal because SPL is calibrated; it stops 0/0 flicker on
  silence). Both numbers were frozen after inspecting real t06 frames, see
  PHASE1-STATUS.md.

* F0. Integer-lag argmax (no parabolic interpolation): at 8 kHz the grid is
  ~1.5% of f0 at 290 Hz -- fine for a feature, documented as quantization.
  f0-slope = least-squares slope of log2(f0) vs time in seconds (octaves/s)
  over voiced in-span frames (0 when fewer than 3).

Output: 16 log-spaced f0 bins x 8 slices (128) + voiced-fraction + median-f0
(Hz) + f0-slope = 131 dims.
"""
from __future__ import annotations

import os
import sys

import numpy as np

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
try:                     # the pip-installed vendored package carries sai too
    from carfac import sai as _sai
except ImportError:      # fall back to the vendored source tree by path
    _SAI_DIR = os.path.join(_ROOT, "vendor", "carfac", "python", "src",
                            "carfac")
    if _SAI_DIR not in sys.path:
        sys.path.insert(0, _SAI_DIR)
    import sai as _sai  # noqa: E402  (the vendored repo's own sai.py)

FS = 16000
HOP10 = 160                # the 10 ms cochleagram hop (frame unit of the span)
PITCH_FMIN, PITCH_FMAX = 60.0, 420.0
PITCH_BINS = 16
PITCH_DECIM = 1            # contingency measured NOT needed (see above)
PITCH_HOP_S = 0.020        # one SAI frame per 20 ms
SAI_TRIGGERS = 2
VOICED_SALIENCE = 0.4      # frozen from measured data: real ah frames
                           # p50 0.87, abba closure p50 0.38, mouth
                           # renders p50 0.42-0.46 (PHASE1-STATUS.md)
P0_MIN = 0.3               # absolute lag-0 floor. MEASURED: voiced real
                           # frames carry p0 1.6-3.6, digital silence
                           # decays to 0.003-0.09 where the RATIO
                           # salience goes meaningless (0.93 on a flat
                           # ghost buffer) -- the floor kills those.
                           # Legal as an absolute: SPL is calibrated.
HALVE_KEEP = 0.7           # subharmonic halving-climb keep ratio (measured)
PITCH_CF_MIN = 140.0       # channels with CF below this self-ring at pitch-
                           # range periods (measured: spurious profile peaks
                           # at 62/97 Hz on a 290 Hz render came from the
                           # CF 34-130 Hz channels) -- excluded from BLOCK P
                           # only; every other block hears all 65 channels.
PROF_SMOOTH = 3            # 3-tap box smoothing of the lag profile before
                           # peak picking (period jitter splits the peak
                           # between adjacent integer lags otherwise)
N_SLICES = 8


def spec():
    return {
        "fmin": PITCH_FMIN, "fmax": PITCH_FMAX, "bins": PITCH_BINS,
        "decim": PITCH_DECIM, "hop_s": PITCH_HOP_S,
        "triggers": SAI_TRIGGERS, "voiced_salience": VOICED_SALIENCE,
        "p0_min": P0_MIN, "halve_keep": HALVE_KEEP, "future_lags": 0,
        "cf_min": PITCH_CF_MIN, "prof_smooth": PROF_SMOOTH,
    }


def _geometry(fs):
    fs_s = fs // PITCH_DECIM
    hop_s = int(round(fs_s * PITCH_HOP_S))
    lag_max = int(np.ceil(fs_s / PITCH_FMIN))
    sai_width = lag_max + 1
    tww = max(sai_width + 1, hop_s)
    params = _sai.SAIParams(
        num_channels=None,  # filled by caller
        sai_width=sai_width,
        future_lags=0,
        num_triggers_per_frame=SAI_TRIGGERS,
        trigger_window_width=tww,
        input_segment_width=hop_s,
    )
    lmin = max(1, int(np.floor(fs_s / PITCH_FMAX)))
    # The profile is COMPUTED from lmin_ext so that a 350-420 Hz peak does
    # not sit at the array edge where the 3-tap smoother halves it
    # (measured: 350/420 Hz renders read as 149/140 before this). The peak
    # SEARCH stays within [lmin, lmax].
    lmin_ext = max(2, int(np.floor(fs_s / (PITCH_FMAX * 1.5))))
    return fs_s, hop_s, sai_width, params, lmin, lag_max, lmin_ext


def _bin_cols(fs_s, sai_width):
    """Column index sets for the 16 log-spaced f0 bins (lag = width-1-col)."""
    edges = np.geomspace(PITCH_FMIN, PITCH_FMAX, PITCH_BINS + 1)
    out = []
    for k in range(PITCH_BINS):
        f_lo, f_hi = edges[k], edges[k + 1]
        lo_lag = int(np.floor(fs_s / f_hi)) + 1     # exclusive hi-f edge
        hi_lag = int(np.floor(fs_s / f_lo))         # inclusive lo-f edge
        if hi_lag < lo_lag:                          # force >=1 lag per bin
            lo_lag = hi_lag = int(round(fs_s / np.sqrt(f_lo * f_hi)))
        lags = np.arange(lo_lag, hi_lag + 1)
        out.append(sai_width - 1 - lags)
    return out


def pitch_block(nap, a, b, fs=FS, cf=None):
    """NAP (n_samples, n_ch) + speech span [a, b] in 10 ms frames -> (P, aux).

    P is the 131-d BLOCK P vector; aux = dict(voiced_frac, median_f0,
    f0_slope, n_sai_frames). cf = per-channel CFs; channels below
    PITCH_CF_MIN are excluded from the pitch profile (self-ringing).
    """
    fs_s, hop_s, sai_width, params, lmin, lmax, lmin_ext = _geometry(fs)

    if cf is not None:
        nap = nap[:, np.asarray(cf, dtype=np.float64) >= PITCH_CF_MIN]
    if PITCH_DECIM > 1:
        n2 = nap.shape[0] // PITCH_DECIM
        naps = nap[:n2 * PITCH_DECIM].reshape(
            n2, PITCH_DECIM, nap.shape[1]).mean(axis=1)
    else:
        naps = nap
    params.num_channels = int(naps.shape[1])
    engine = _sai.SAI(params)

    hop10_s = HOP10 // PITCH_DECIM               # 10 ms in decimated samples
    span_start = a * hop10_s
    span_end = (b + 1) * hop10_s
    start = max(0, span_start - engine._buffer_width)
    region = naps[start:span_end]
    nseg = region.shape[0] // hop_s

    t_lo = a * HOP10 / fs
    t_hi = (b + 1) * HOP10 / fs

    bin_cols = _bin_cols(fs_s, sai_width)
    rows, voiced, f0s, times = [], [], [], []
    for i in range(nseg):
        seg = np.ascontiguousarray(region[i * hop_s:(i + 1) * hop_s].T)
        frame = engine.RunSegment(seg)
        t = (start + (i + 1) * hop_s) * PITCH_DECIM / fs   # end-of-segment time
        if t < t_lo or t > t_hi + 1e-9:
            continue
        prof = frame.mean(axis=0)
        p0 = float(prof[sai_width - 1])
        ext = prof[sai_width - 1 - np.arange(lmin_ext, lmax + 1)]
        if PROF_SMOOTH > 1:
            ext = np.convolve(ext, np.ones(PROF_SMOOTH) / PROF_SMOOTH,
                              mode="same")
        vals = ext[lmin - lmin_ext:]                 # search band [lmin,lmax]
        # SUBHARMONIC GUARD (measured need: a 290 Hz render's mean profile
        # peaks at lag 109 = 4x the true period, with 3T and 2T also above
        # or near the true peak -- plain argmax reads period multiples).
        # DIVISOR DESCENT: take the global peak lag L; for every divisor
        # k = 2..L/lmin, look within +-1 sample of L/k; the SMALLEST
        # divisor lag whose value holds >= HALVE_KEEP of the peak value
        # wins. A real 70 Hz croak keeps its 114-sample lag because its
        # subperiod lags carry no comparable peak (measured, see
        # PHASE1-STATUS.md). Voicing salience uses the global peak.
        pv = float(vals.max())
        lag_pk = lmin + int(np.argmax(vals))
        best = lag_pk
        for k in range(2, lag_pk // lmin + 1):
            cand_f = lag_pk / k
            if cand_f < lmin:
                break
            lo = max(lmin, int(np.floor(cand_f)) - 1)
            hi = min(lmax, int(np.ceil(cand_f)) + 1)
            seg = vals[lo - lmin:hi - lmin + 1]
            cand = lo + int(np.argmax(seg))
            if vals[cand - lmin] >= HALVE_KEEP * pv:
                best = cand
        lag_pk = best
        sal = float(pv / (p0 + 1e-12))
        is_voiced = bool(sal >= VOICED_SALIENCE and p0 >= P0_MIN)
        rows.append(np.array([float(prof[c].mean()) / (p0 + 1e-12)
                              for c in bin_cols]))
        voiced.append(is_voiced)
        if is_voiced:
            f0s.append(fs_s / lag_pk)
            times.append(t)

    if rows:
        R = np.stack(rows)
        slices = np.stack([p.mean(axis=0) if len(p) else np.zeros(PITCH_BINS)
                           for p in np.array_split(R, N_SLICES)])
        binvec = slices.ravel()
        voiced_frac = float(np.mean(voiced))
    else:
        binvec = np.zeros(N_SLICES * PITCH_BINS)
        voiced_frac = 0.0

    if f0s:
        median_f0 = float(np.median(f0s))
    else:
        median_f0 = 0.0
    if len(f0s) >= 3 and (times[-1] - times[0]) > 1e-9:
        A = np.vstack([np.asarray(times), np.ones(len(times))]).T
        slope = float(np.linalg.lstsq(A, np.log2(np.asarray(f0s)),
                                      rcond=None)[0][0])
    else:
        slope = 0.0

    P = np.concatenate([binvec, [voiced_frac, median_f0, slope]])
    aux = {"voiced_frac": voiced_frac, "median_f0": median_f0,
           "f0_slope": slope, "n_sai_frames": len(rows)}
    return P, aux
