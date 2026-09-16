# -*- coding: utf-8 -*-
"""f1traj.py -- THE F1-TRANSITION RULER.

|F1(first third) - F1(last third)| of the active span, in Hz. How far the
first formant MOVES during the syllable: the locus cue.

Provenance: this is a verbatim lift of the `f1_traj_hz` feature from
D:\CLAUDE\eran-brain\throat-ruler-measure\feats.py, the script that
measured it against Iddo's 136 rulings on 2026-09-01:

    stratified concordance AUC 0.7811 vs his labels (n_pairs 1293)
    shuffled-label floor 0.5022 +- 0.0431
    incumbent wdist, same test, same clips: 0.3605  (backwards)

It is validated as a RANKER over the candidate distribution, NOT as a
maximisation target -- his top-rated clips are not the max-traj clips. That
is why the search uses it only through a BAND fence against his own mouth
(see human_band / band_cost below), never as `-f1_traj`.

SACRED AUDIO LAW: reads wav bytes and measures numbers. Plays nothing.
"""
import numpy as np
import scipy.signal as sig
from scipy.linalg import toeplitz

FS = 16000


def frames(x, n=400, hop=160):
    if len(x) < n:
        x = np.pad(x, (0, n - len(x)))
    idx = np.arange(0, len(x) - n + 1, hop)
    return np.stack([x[i:i + n] for i in idx]), idx


def db(v, eps=1e-12):
    return 20 * np.log10(np.maximum(v, eps))


def lpc_formants(x, order=14, fs=FS):
    if len(x) < order * 3:
        return np.nan, np.nan
    x = x * np.hanning(len(x))
    x = sig.lfilter([1, -0.97], [1], x)
    r = np.correlate(x, x, 'full')[len(x) - 1:len(x) - 1 + order + 1]
    if r[0] <= 0 or len(r) < order + 1:
        return np.nan, np.nan
    r = r.copy()
    r[0] *= 1.0001
    try:
        a = np.linalg.solve(toeplitz(r[:order]), r[1:order + 1])
    except Exception:
        return np.nan, np.nan
    A = np.concatenate([[1.0], -a])
    rts = np.roots(A)
    rts = rts[np.imag(rts) > 0.01]
    if len(rts) == 0:
        return np.nan, np.nan
    f = np.sort(np.angle(rts) * fs / (2 * np.pi))
    f = f[(f > 150) & (f < 5000)]
    f1 = float(f[0]) if len(f) > 0 else np.nan
    f2 = float(f[1]) if len(f) > 1 else np.nan
    return f1, f2


def f1_traj_hz(x):
    """|F1(first third) - F1(last third)| over the active span. nan if unmeasurable."""
    x = np.asarray(x, dtype=np.float64)
    if len(x) < 800:
        return float('nan')
    fr, _ = frames(x)
    e = np.sqrt((fr ** 2).mean(axis=1))
    edb = db(e)
    act = edb > (edb.max() - 35)
    ai = np.where(act)[0]
    if len(ai) < 6:
        return float('nan')
    s0, s1 = ai[0] * 160, min(ai[-1] * 160 + 400, len(x))
    seg = x[s0:s1]
    third = max(len(seg) // 3, 200)
    F1a, _ = lpc_formants(seg[:third])
    F1b, _ = lpc_formants(seg[-third:])
    if F1a != F1a or F1b != F1b:
        return float('nan')
    return float(abs(F1b - F1a))


def band_cost(v, band):
    """Cost of a candidate's f1_traj against HIS OWN mouth's band.

    band = {"lo": p10, "hi": p90, "scale": iqr-ish width}.  Zero inside the
    band, linear outside, in band-widths.  Bounded ABOVE -- so a search that
    minimises it cannot manufacture an F1 swoop that is not speech, which is
    exactly the failure mode the 09-01 measurement warned about.
    Unmeasurable (nan) pays the full-width cost, never zero.
    """
    s = max(float(band["scale"]), 1e-6)
    if v != v:
        return 1.0
    if v < band["lo"]:
        return (band["lo"] - v) / s
    if v > band["hi"]:
        return (v - band["hi"]) / s
    return 0.0
