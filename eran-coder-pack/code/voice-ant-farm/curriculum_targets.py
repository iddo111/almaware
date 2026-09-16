# -*- coding: utf-8 -*-
"""Acoustic targets for the coronation curriculum: /a/ -> /ba/ -> /ga/.

WHY THIS FILE EXISTS
--------------------
The old coronation crowned a queen on *perception* (held-out syllable
discrimination, cos-top1 = 0.758). Nobody ever tested *production*. Iddo
listened to the production and it is garbage, because synthesize_units() in
acoustic_units.py does not synthesise: it overlap-adds stored raw PCM exemplars
and then lowpasses the mosaic at 2500 Hz.

THE AMENDED LAW (Iddo, 2026-08-13)
----------------------------------
    "its ok if the queen copies me with her own mouth - that's learning isnt it"

He is right. Imitation is how infants acquire speech. The distinction is not
similarity, it is PROVENANCE:

    REPLAY    - splicing stored recorded PCM. A tape recorder. FORBIDDEN.
    IMITATION - reproducing the sound through her OWN articulators. REQUIRED.

Resemblance to Iddo's /a/ is the TARGET, never the crime. So this module
produces ARTICULATORY-SCORABLE ACOUSTIC TARGETS - numbers (formants, durations,
slopes, spectral shapes) - and never exports waveforms. A production path that
can only see this file's output has no recorded audio to splice, so replay is
impossible BY CONSTRUCTION rather than merely detected.

HOLD-OUT, non-negotiable: the Cafe Clod sessions 2026-06-25 and 2026-07-01 are
reserved for evaluation and must never be fitted on. filter_training_paths()
enforces it and is unit-tested.

No torch (workspace law). numpy + scipy only. Audio is read from and written to
FILES only - nothing here opens an audio device.
"""
from __future__ import annotations

import os
import re
import wave
import numpy as np
from scipy.signal import resample_poly

# --------------------------------------------------------------------------
# Hold-out policy
# --------------------------------------------------------------------------
HELDOUT_SESSIONS = ("2026-06-25", "2026-07-01")

_HELDOUT_TOKENS = tuple(
    t
    for s in HELDOUT_SESSIONS
    for t in (s, s.replace("-", ""), s.replace("-", "_"))
)


def heldout_sessions():
    """Sessions reserved for evaluation. Never fitted on."""
    return list(HELDOUT_SESSIONS)


def filter_training_paths(paths):
    """Drop every path belonging to a held-out session."""
    return [p for p in paths if not any(t in str(p) for t in _HELDOUT_TOKENS)]


def is_heldout(path):
    return any(t in str(path) for t in _HELDOUT_TOKENS)


# --------------------------------------------------------------------------
# Audio I/O (files only)
# --------------------------------------------------------------------------
def read_wav_mono16k(path, target_sr=16000, max_seconds=None):
    """Read a wav, downmix to mono, resample to target_sr. Returns float32 [-1,1]."""
    with wave.open(str(path)) as w:
        sr = w.getframerate()
        ch = w.getnchannels()
        sw = w.getsampwidth()
        n = w.getnframes()
        if max_seconds is not None:
            n = min(n, int(max_seconds * sr))
        raw = w.readframes(n)
    if sw == 2:
        x = np.frombuffer(raw, "<i2").astype(np.float32) / 32768.0
    elif sw == 4:
        x = np.frombuffer(raw, "<i4").astype(np.float32) / 2147483648.0
    elif sw == 1:
        x = (np.frombuffer(raw, "u1").astype(np.float32) - 128.0) / 128.0
    else:
        raise ValueError(f"unsupported sample width {sw}")
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    if sr != target_sr:
        g = np.gcd(int(sr), int(target_sr))
        x = resample_poly(x, target_sr // g, sr // g).astype(np.float32)
    return np.ascontiguousarray(x, dtype=np.float32)


# --------------------------------------------------------------------------
# LPC formants
# --------------------------------------------------------------------------
def lpc_order_for(sr):
    """Standard rule: 2 + sr/1000 poles (=> 18 at 16 kHz)."""
    return int(round(2 + sr / 1000.0))


def _levinson(r, order):
    a = np.zeros(order + 1)
    a[0] = 1.0
    e = r[0]
    if e <= 0:
        return None
    for i in range(1, order + 1):
        acc = r[i] + (np.dot(a[1:i], r[i - 1:0:-1]) if i > 1 else 0.0)
        k = -acc / e
        a_new = a.copy()
        for j in range(1, i):
            a_new[j] = a[j] + k * a[i - j]
        a_new[i] = k
        a = a_new
        e *= (1.0 - k * k)
        if e <= 0:
            return None
    return a


def lpc_formants(frame, sr, order=None, fmin=90.0, fmax=5000.0, max_bw=400.0):
    """Formant frequencies (Hz, ascending) from one frame, or None.

    Pre-emphasis -> Hamming -> autocorrelation LPC -> polynomial roots ->
    keep poles in [fmin, fmax] with bandwidth < max_bw.
    """
    x = np.asarray(frame, dtype=np.float64)
    if x.size < 32 or not np.all(np.isfinite(x)):
        return None
    x = x - x.mean()
    if np.dot(x, x) <= 1e-12:
        return None
    x = np.append(x[0], x[1:] - 0.97 * x[:-1])          # pre-emphasis
    x = x * np.hamming(x.size)                           # taper
    if order is None:
        order = lpc_order_for(sr)
    r = np.correlate(x, x, "full")[x.size - 1: x.size + order]
    if r.size < order + 1 or r[0] <= 1e-12:
        return None
    a = _levinson(r / r[0], order)
    if a is None:
        return None
    try:
        rts = np.roots(a)
    except Exception:
        return None
    rts = rts[np.imag(rts) > 1e-6]
    if rts.size == 0:
        return None
    f = np.angle(rts) * sr / (2.0 * np.pi)
    bw = -0.5 * (sr / (2.0 * np.pi)) * np.log(np.abs(rts) + 1e-12)
    keep = (f >= fmin) & (f <= fmax) & (bw < max_bw) & (bw > 0)
    f = np.sort(f[keep])
    return f if f.size >= 1 else None


# --------------------------------------------------------------------------
# Formant tracking at a resampled ceiling (the accurate path)
# --------------------------------------------------------------------------
# Measured on synthetic tracts of known pole placement (see
# test_curriculum_targets.py). Plain order-18 LPC at 16 kHz is accurate for
# low-f0 (male) voices but mislocates F2 of female/child /a/ by 16-33%, because
# /a/ has F1 and F2 close together and a high f0 leaves too few harmonics
# between them. Resampling to 2*ceiling and using order 2*n_formants - the
# standard Praat configuration - brings every case to <= 3.3%:
#
#   config                          male /a/   female /a/   child /a/
#   16 kHz, order 18                 0.8/0.5    5.4/16.3    (F2 lost)
#   11 kHz, order 10 (ADOPTED)       1.7/0.8    2.2/0.5      3.0/1.3
FORMANT_CEILING_HZ = 5500.0
FORMANT_N = 5


def formant_track(x, sr, ceiling=FORMANT_CEILING_HZ, n_formants=FORMANT_N,
                  win_s=0.025, hop_s=0.010, min_voicing=0.45,
                  energy_pct=50.0, max_frames=None):
    """Voiced-frame formant track. Returns list of dicts: t, f1, f2, f3, f0, voicing.

    Resamples to 2*ceiling and uses LPC order 2*n_formants (Praat convention).
    """
    tsr = int(round(2 * ceiling))
    g = np.gcd(int(sr), tsr)
    y = resample_poly(np.asarray(x, dtype=np.float64), tsr // g, sr // g)
    win = int(win_s * tsr)
    hop = int(hop_s * tsr)
    if y.size < win:
        return []
    n = 1 + (y.size - win) // hop
    V = np.lib.stride_tricks.sliding_window_view(y, win)[::hop][:n]
    e = np.sum(V ** 2, axis=1)
    if e.size == 0:
        return []
    ethr = max(np.percentile(e, energy_pct), 1e-9)
    order = int(2 * n_formants)
    out = []
    for i in np.flatnonzero(e >= ethr):
        fr = V[i]
        v = voicing_strength(fr, tsr)
        if v < min_voicing:
            continue
        f = lpc_formants(fr, tsr, order=order, fmax=ceiling - 100.0)
        if f is None or f.size < 2:
            continue
        out.append({
            "t": float(i * hop / tsr),
            "f1": float(f[0]),
            "f2": float(f[1]),
            "f3": float(f[2]) if f.size >= 3 else float("nan"),
            "f0": estimate_f0(fr, tsr),
            "voicing": float(v),
            "rms": float(np.sqrt(np.mean(fr ** 2))),
        })
        if max_frames and len(out) >= max_frames:
            break
    return out


# --------------------------------------------------------------------------
# Voicing / f0
# --------------------------------------------------------------------------
def _norm_autocorr(frame, sr, fmin=80.0, fmax=500.0):
    x = np.asarray(frame, dtype=np.float64)
    x = x - x.mean()
    e0 = np.dot(x, x)
    if e0 <= 1e-12:
        return None, None
    ac = np.correlate(x, x, "full")[x.size - 1:]
    lo = max(2, int(sr / fmax))
    hi = min(x.size // 2, int(sr / fmin))
    if hi <= lo + 1:
        return None, None
    seg = ac[lo:hi] / e0
    return seg, lo


def voicing_strength(frame, sr):
    """Peak normalised autocorrelation in the f0 band. ~1 periodic, ~0 noise."""
    seg, lo = _norm_autocorr(frame, sr)
    if seg is None or seg.size == 0:
        return 0.0
    return float(max(0.0, seg.max()))


def estimate_f0(frame, sr):
    """f0 in Hz from the autocorrelation peak (parabolic-interpolated), or None."""
    seg, lo = _norm_autocorr(frame, sr)
    if seg is None or seg.size == 0:
        return None
    k = int(np.argmax(seg))
    if seg[k] < 0.30:
        return None
    lag = lo + k
    if 0 < k < seg.size - 1:                              # parabolic refine
        y0, y1, y2 = seg[k - 1], seg[k], seg[k + 1]
        den = (y0 - 2 * y1 + y2)
        if abs(den) > 1e-12:
            lag = lo + k + 0.5 * (y0 - y2) / den
    return float(sr / lag) if lag > 0 else None


def voiced_steady_frames(x, sr, win_s=0.025, hop_s=0.010,
                         min_voicing=0.45, energy_pct=60.0, max_frames=None):
    """Yield (index, frame) for voiced, above-median-energy frames."""
    win = int(win_s * sr)
    hop = int(hop_s * sr)
    if x.size < win:
        return []
    n = 1 + (x.size - win) // hop
    V = np.lib.stride_tricks.sliding_window_view(x, win)[::hop][:n]
    e = np.sum(V.astype(np.float64) ** 2, axis=1)
    if e.size == 0:
        return []
    thr = np.percentile(e, energy_pct)
    out = []
    for i in np.flatnonzero(e >= max(thr, 1e-9)):
        fr = V[i].astype(np.float64)
        if voicing_strength(fr, sr) >= min_voicing:
            out.append((int(i), fr))
            if max_frames and len(out) >= max_frames:
                break
    return out


# --------------------------------------------------------------------------
# Stops: closure, burst, transitions
# --------------------------------------------------------------------------
def frame_energy_db(x, sr, win_s=0.010, hop_s=0.0025):
    win = int(win_s * sr)
    hop = int(hop_s * sr)
    if x.size < win:
        return np.array([]), hop
    n = 1 + (x.size - win) // hop
    V = np.lib.stride_tricks.sliding_window_view(x, win)[::hop][:n]
    p = np.mean(V.astype(np.float64) ** 2, axis=1)
    return 10.0 * np.log10(p + 1e-20), hop


def find_stop_events(x, sr, min_closure_ms=40.0, max_closure_ms=300.0,
                     silence_rel_db=35.0, burst_rise_db=10.0):
    """Locate [silent closure -> burst] seams: the signature of a stop consonant.

    Returns dicts with burst_s, closure_ms, burst_rise_db, voiced_after.
    """
    edb, hop = frame_energy_db(x, sr)
    if edb.size == 0:
        return []
    ref = float(np.percentile(edb, 95))
    thr = ref - silence_rel_db
    quiet = edb < thr
    events = []
    i = 0
    n = quiet.size
    while i < n:
        if not quiet[i]:
            i += 1
            continue
        j = i
        while j < n and quiet[j]:
            j += 1
        dur_ms = (j - i) * hop / sr * 1000.0
        if min_closure_ms <= dur_ms <= max_closure_ms and j < n:
            k = j
            while k < n and edb[k] < thr + burst_rise_db:
                k += 1
            if k < n:
                burst_s = j * hop / sr
                rise = float(edb[k] - np.median(edb[i:j]))
                seg0 = int(burst_s * sr)
                tail = x[seg0: seg0 + int(0.120 * sr)]
                voiced_after = False
                if tail.size >= int(0.025 * sr):
                    vs = [voicing_strength(tail[t:t + int(0.025 * sr)], sr)
                          for t in range(0, tail.size - int(0.025 * sr), int(0.010 * sr))]
                    voiced_after = bool(vs) and max(vs) > 0.45
                events.append({
                    "burst_s": float(burst_s),
                    "closure_ms": float(dur_ms),
                    "burst_rise_db": rise,
                    "voiced_after": voiced_after,
                })
        i = j + 1
    return events


def burst_centroid(seg, sr, fmin=200.0, fmax=8000.0):
    """Spectral centroid (Hz) of a burst. Bilabial low, velar mid, alveolar high."""
    x = np.asarray(seg, dtype=np.float64)
    if x.size < 16:
        return float("nan")
    x = (x - x.mean()) * np.hamming(x.size)
    X = np.abs(np.fft.rfft(x, n=max(512, 1 << int(np.ceil(np.log2(x.size))))))
    f = np.fft.rfftfreq(max(512, 1 << int(np.ceil(np.log2(x.size)))), 1.0 / sr)
    m = (f >= fmin) & (f <= fmax)
    if not m.any() or X[m].sum() <= 0:
        return float("nan")
    return float((f[m] * X[m]).sum() / X[m].sum())


def spectral_tilt_db(seg, sr, lo_band=(200.0, 1500.0), hi_band=(3000.0, 8000.0)):
    """Energy(low) - Energy(high) in dB. Positive = diffuse-falling (bilabial)."""
    x = np.asarray(seg, dtype=np.float64)
    if x.size < 16:
        return float("nan")
    x = (x - x.mean()) * np.hamming(x.size)
    nfft = max(512, 1 << int(np.ceil(np.log2(x.size))))
    P = np.abs(np.fft.rfft(x, n=nfft)) ** 2
    f = np.fft.rfftfreq(nfft, 1.0 / sr)
    lo = P[(f >= lo_band[0]) & (f <= lo_band[1])].sum()
    hi = P[(f >= hi_band[0]) & (f <= hi_band[1])].sum()
    return float(10.0 * np.log10((lo + 1e-20) / (hi + 1e-20)))


def measure_cv_token(x, sr, search_s=0.60, onset_win_s=0.015, steady_from_s=0.090,
                     steady_to_s=0.200, transition_s=0.060,
                     win_s=0.020, hop_s=0.005, min_voicing=0.40):
    """Measure one stop+vowel token: closure, burst, VOT, F2 locus and transition.

    This is what makes /ba/ and /ga/ TARGETS rather than opinions. A stop is not
    a spectrum, it is a GESTURE in time: close the tract, build pressure,
    release it, and move to the vowel. Each of those stages is measurable:

      closure_ms        silence while the tract is sealed
      burst_centroid    where the release energy sits (bilabial low, velar mid)
      burst_tilt_db     low-band minus high-band energy (bilabial positive)
      vot_ms            release -> onset of voicing
      f2_onset          F2 at voicing onset == the consonant's F2 LOCUS
      f2_steady         F2 in the vowel body
      f2_slope_hz_per_s the transition: bilabial rises, velar falls into /a/
      pinch_onset       exp(-|F3-F2|/900) at onset - the velar pinch

    Returns None if no stop-shaped event is present.
    """
    x = np.asarray(x, dtype=np.float64)
    ev = find_stop_events(x[:int(search_s * sr)] if x.size > int(search_s * sr) else x,
                          sr, min_closure_ms=30.0)
    if not ev:
        return None
    e = max(ev, key=lambda d: d["burst_rise_db"])
    b0 = int(e["burst_s"] * sr)
    burst = x[b0: b0 + int(0.015 * sr)]
    if burst.size < 32:
        return None

    # Formant transitions last only 40-70 ms, so a 25 ms / 10 ms grid measures
    # its FIRST point after the transition is already over, and the fast
    # spectral change also drags the voicing score below threshold. A 20 ms /
    # 5 ms grid is needed to see the locus at all.
    tail = x[b0:]
    tr = formant_track(tail, sr, min_voicing=min_voicing, energy_pct=25.0,
                       win_s=win_s, hop_s=hop_s)
    if len(tr) < 3:
        return None

    vot_ms = float(tr[0]["t"] * 1000.0) if tr else None
    t0 = tr[0]["t"]
    onset = [r for r in tr if r["t"] - t0 <= onset_win_s]
    steady = [r for r in tr if steady_from_s <= (r["t"] - t0) <= steady_to_s]
    trans = [r for r in tr if (r["t"] - t0) <= transition_s]
    if not onset or not trans:
        return None

    f2_onset = float(np.median([r["f2"] for r in onset]))
    f3_onset = float(np.nanmedian([r["f3"] for r in onset]))
    f1_onset = float(np.median([r["f1"] for r in onset]))
    f2_steady = float(np.median([r["f2"] for r in steady])) if steady else float(
        np.median([r["f2"] for r in tr[len(tr) // 2:]]))
    f1_steady = float(np.median([r["f1"] for r in steady])) if steady else float(
        np.median([r["f1"] for r in tr[len(tr) // 2:]]))
    ts = np.array([r["t"] for r in trans])
    f2s = np.array([r["f2"] for r in trans])
    if ts.size >= 2 and np.ptp(ts) > 1e-6:
        A = np.vstack([ts, np.ones_like(ts)]).T
        slope = float(np.linalg.lstsq(A, f2s, rcond=None)[0][0])
    else:
        slope = float("nan")

    return {
        "closure_ms": float(e["closure_ms"]),
        "burst_rise_db": float(e["burst_rise_db"]),
        "burst_centroid_hz": burst_centroid(burst, sr),
        "burst_tilt_db": spectral_tilt_db(burst, sr),
        "vot_ms": vot_ms,
        "f1_onset": f1_onset,
        "f2_onset": f2_onset,
        "f3_onset": f3_onset,
        "f1_steady": f1_steady,
        "f2_steady": f2_steady,
        "f2_slope_hz_per_s": slope,
        "f2_excursion_hz": float(f2_steady - f2_onset),
        "pinch_onset": velar_pinch_score(f2_onset, f3_onset),
        "n_frames": len(tr),
    }


def velar_pinch_score(f2, f3, tau=900.0):
    """How 'pinched' F2/F3 are at release. 1.0 = touching, ->0 = far apart.

    The velar pinch is THE defining cue of /g/: F2 and F3 converge at the
    release because the velar constriction couples the two cavities.
    """
    if f2 is None or f3 is None or not np.isfinite(f2) or not np.isfinite(f3):
        return float("nan")
    return float(np.exp(-abs(float(f3) - float(f2)) / tau))


def f2_transition_slope(f2_track, hop_s=0.010):
    """Least-squares slope of F2 in Hz/second. Positive = rising into the vowel."""
    y = np.asarray([v for v in f2_track if v is not None and np.isfinite(v)],
                   dtype=np.float64)
    if y.size < 2:
        return float("nan")
    t = np.arange(y.size, dtype=np.float64) * hop_s
    A = np.vstack([t, np.ones_like(t)]).T
    slope, _ = np.linalg.lstsq(A, y, rcond=None)[0]
    return float(slope)


# --------------------------------------------------------------------------
# Vowel-space clustering (own EM, no sklearn dependency)
# --------------------------------------------------------------------------
def estimate_a_target(F1, F2, F0=None, top_f1_pct=80.0, seed=7):
    """Estimate the /a/ target from unlabelled running speech.

    We have no forced phone alignment, so /a/ cannot be looked up by label. It
    can still be located by definition: /a/ is the maximally OPEN vowel, so it
    occupies the high-F1 corner of the speaker's vowel space, and among
    high-F1 frames it is the BACK/low-F2 lobe (the high-F2 lobe there is /e/ and
    other front vowels).

    So: (1) keep physiologically possible frames, (2) take the top-F1 quantile -
    the open corner, (3) split that corner into two components and keep the
    lower-F2 one. Both bugs this replaces came from skipping a step: without (1)
    the answer was the artifact cluster at F1=1191 Hz, without (3) it was the
    front-vowel lobe at F2=2243 Hz.

    Returns a dict with centroid, full covariance, spread and counts.
    """
    F1 = np.asarray(F1, dtype=np.float64).ravel()
    F2 = np.asarray(F2, dtype=np.float64).ravel()
    m = valid_vowel_mask(F1, F2)
    a, b = F1[m], F2[m]
    n_input = int(a.size)
    if n_input < 50:
        raise ValueError(f"too few valid vowel frames: {n_input}")
    thr = np.percentile(a, top_f1_pct)
    sel = a >= thr
    A, B = a[sel], b[sel]
    if A.size < 40:
        raise ValueError(f"open-corner subset too small: {A.size}")
    X = np.column_stack([A, B])
    w, mu, cov, P = _gmm_em(X, 2, seed=seed)
    j = int(np.argmin(mu[:, 1]))                      # lower-F2 lobe == /a/
    n_eff = float(P[:, j].sum())
    out = {
        "F1": float(mu[j][0]),
        "F2": float(mu[j][1]),
        "cov": [[float(cov[j][0, 0]), float(cov[j][0, 1])],
                [float(cov[j][1, 0]), float(cov[j][1, 1])]],
        "sd_F1": float(np.sqrt(cov[j][0, 0])),
        "sd_F2": float(np.sqrt(cov[j][1, 1])),
        "corr_F1F2": float(cov[j][0, 1] / np.sqrt(cov[j][0, 0] * cov[j][1, 1] + 1e-12)),
        "n_effective": float(n_eff),
        "n_input": n_input,
        "n_open_corner": int(A.size),
        "top_f1_pct": float(top_f1_pct),
        "f1_threshold_hz": float(thr),
    }
    if F0 is not None:
        F0 = np.asarray(F0, dtype=np.float64).ravel()[m][sel]
        d = X - mu[j]
        try:
            md = np.einsum("ij,jk,ik->i", d, np.linalg.inv(cov[j]), d)
            f0s = F0[(md < 4.0) & np.isfinite(F0)]
        except np.linalg.LinAlgError:
            f0s = F0[np.isfinite(F0)]
        if f0s.size:
            out["f0_median"] = float(np.median(f0s))
            out["f0_p10_p90"] = [float(np.percentile(f0s, 10)),
                                 float(np.percentile(f0s, 90))]
    return out


def _gmm_em(X, k, seed=0, iters=200, tol=1e-6):
    rng = np.random.default_rng(seed)
    n, d = X.shape
    qs = np.linspace(5, 95, k)
    mu = np.stack([np.percentile(X, q, axis=0) for q in qs])
    mu = mu + rng.normal(0, 1e-3, mu.shape)
    gcov = np.cov(X.T) + np.eye(d) * 1e-6
    cov = np.stack([gcov.copy() for _ in range(k)])
    w = np.full(k, 1.0 / k)
    reg = np.eye(d) * (np.trace(gcov) / d) * 1e-4
    prev = -np.inf
    R = np.zeros((n, k))
    for _ in range(iters):
        for j in range(k):                                 # E-step
            try:
                L = np.linalg.cholesky(cov[j] + reg)
            except np.linalg.LinAlgError:
                cov[j] = gcov.copy()
                L = np.linalg.cholesky(cov[j] + reg)
            diff = np.linalg.solve(L, (X - mu[j]).T)
            logdet = 2.0 * np.log(np.diag(L)).sum()
            R[:, j] = (np.log(w[j] + 1e-300) - 0.5 * (diff ** 2).sum(axis=0)
                       - 0.5 * logdet - 0.5 * d * np.log(2 * np.pi))
        m = R.max(axis=1, keepdims=True)
        ll = float((m.ravel() + np.log(np.exp(R - m).sum(axis=1))).sum())
        P = np.exp(R - m)
        P /= P.sum(axis=1, keepdims=True)
        Nk = P.sum(axis=0) + 1e-12                          # M-step
        w = Nk / n
        mu = (P.T @ X) / Nk[:, None]
        for j in range(k):
            dX = X - mu[j]
            cov[j] = (P[:, j][:, None] * dX).T @ dX / Nk[j] + reg
        if abs(ll - prev) < tol * max(1.0, abs(ll)):
            break
        prev = ll
    return w, mu, cov, P


# Physiological limits of the human vowel space. These are INSTRUMENT VALIDITY
# bounds, not a target: they say which (F1,F2) pairs could have come from a
# human vocal tract at all. A frame reporting F1 = 1400 Hz has not found a
# strange vowel - it has DROPPED F1 (pole outside the keep-range, or bandwidth
# over the limit) and slid F2 into its slot. Left unfiltered, those artifacts
# form the highest-F1 cluster in the space and hijack the /a/ estimate: the
# first run of this pipeline reported /a/ at F1 = 1191 Hz for exactly this
# reason.
F1_RANGE_HZ = (250.0, 1100.0)
F2_RANGE_HZ = (700.0, 3200.0)
MIN_F2_MINUS_F1_HZ = 150.0


def valid_vowel_mask(F1, F2):
    """Boolean mask of (F1,F2) pairs a human vocal tract could actually produce."""
    F1 = np.asarray(F1, dtype=np.float64).ravel()
    F2 = np.asarray(F2, dtype=np.float64).ravel()
    return (np.isfinite(F1) & np.isfinite(F2)
            & (F1 >= F1_RANGE_HZ[0]) & (F1 <= F1_RANGE_HZ[1])
            & (F2 >= F2_RANGE_HZ[0]) & (F2 <= F2_RANGE_HZ[1])
            & ((F2 - F1) >= MIN_F2_MINUS_F1_HZ))


def pick_a_cluster(F1, F2, n_components=5, seed=0, min_weight=0.05):
    """Fit a GMM to the vowel space and return the /a/ component.

    /a/ is the maximally open vowel: it is the HIGHEST-F1 corner of any vowel
    space. We do not assume where it is - we fit the space and take the
    highest-F1 component carrying real mass. Frames outside the physiological
    vowel space are dropped first (see valid_vowel_mask), because otherwise the
    'highest F1' component is the measurement-artifact cluster, not /a/.

    Returns (mean[F1,F2], covariance 2x2, n_effective).
    """
    F1 = np.asarray(F1, dtype=np.float64).ravel()
    F2 = np.asarray(F2, dtype=np.float64).ravel()
    if F1.size == 0 or F2.size == 0:
        raise ValueError("empty formant arrays - nothing to cluster")
    if F1.size != F2.size:
        raise ValueError("F1/F2 length mismatch")
    ok = valid_vowel_mask(F1, F2)
    X = np.column_stack([F1[ok], F2[ok]])
    if X.shape[0] < 10:
        raise ValueError(f"too few points to cluster: {X.shape[0]}")
    k = int(min(n_components, max(1, X.shape[0] // 20)))
    w, mu, cov, P = _gmm_em(X, k, seed=seed)
    cand = [j for j in range(k) if w[j] >= min_weight] or list(range(k))
    j = max(cand, key=lambda t: mu[t][0])
    n_eff = float(P[:, j].sum())
    return mu[j], cov[j], n_eff
