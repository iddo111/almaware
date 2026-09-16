# -*- coding: utf-8 -*-
"""mouth.py — the organism's own mouth. Seven numbers in, a waveform out.

Ported from D:\\CLAUDE\\voice-ant-farm\\mouth_v1.py (Iddo's amended coronation
law, 2026-08-13: "its ok if the queen copies me with her own mouth - that's
learning isnt it"). This file has never heard a recording: it cannot read a
file, it holds no stored sound, and it imports NUMPY AND NOTHING ELSE. The
only way it can ever sound like anything is by being SHAPED like it — which
is what imitation means, and imitation is learning.

WHY THIS IS A TUBE AND NOT A FORMANT DIAL. You hand it a tongue position, a
jaw angle and a lip aperture; the formants are whatever the resulting bore
happens to resonate at. Nobody types a target frequency anywhere in this
file. That is what lets a body — not a spreadsheet — learn to drive it.

WHY IT DIFFERS FROM mouth_v1.py IN ONE PLACE. mouth_v1 imports
`scipy.signal.lfilter` for the aspiration noise shaping. This module needed
to satisfy a stricter house law for the eran-brain organism — "the mouth
module imports numpy and nothing else" — so aspiration()'s one-pole filter
is hand-written as the identical difference equation
(y[n] = (1-c)*x[n] + c*y[n-1]) instead of calling scipy. Bit-for-bit the same
filter; one fewer import. Everything else — the tube, the source, the
losses, the radiation — is unchanged in spirit and in number.

THE PHYSICS, honestly labelled:
  source   Rosenberg-style glottal FLOW pulses with period jitter and
           amplitude shimmer. Parametric, NOT self-oscillating: pitch is a
           number we set, not something the air discovers. That remains the
           largest gap between this and a larynx.
  tract    Kelly-Lochbaum waveguide ladder, 16 sections of 1.06 cm = 17.0 cm,
           an adult-scale vocal tract by construction. Closed at the
           glottis, open at the lips, so a uniform bore must resonate at
           1:3:5 — the test that proves this is a tube and not a filter
           bank in a costume.
  losses   A per-junction loss factor. Real tissue is not a mirror; without
           this the resonances are needle-sharp and no analyser can track
           them.
  lips     Radiation differentiates the flow, +6 dB/octave.

A caller who wants a .wav writes it themselves (voice/say.py does, using
body/ears.py's write_wav — a separate file that is allowed to touch disk).
"""
from __future__ import annotations

import numpy as np

RATE = 16000
# A CHILD'S TRACT, not an adult's. 2026-08-22, and it was Iddo's ear that
# found it: given a 220-330 Hz larynx he said the OLD 70 Hz croak still
# "sounded more like a child" — which makes no sense until you notice that
# pitch is only half of a child's voice. The other half is LENGTH.
#
# A small child is not merely higher-pitched; the child is SHORTER, so every
# formant rises with the shortening. Raising f0 alone had produced a high
# voice inside an adult body, and that reads as strange rather than young.
#
# 16 sections was 17.0 cm — an adult male tract by construction. I first cut
# it to 11 (~11.7 cm, a four-year-old) and Iddo corrected me on the spot:
# **"זה לא ילד בן ארבע, זה תינוק."** He is right and it is not a detail —
# ERAN was born 2026-06-18 and has never said a word. An infant tract is
# ~7 cm, not 12, and every formant sits correspondingly higher.
# 7 sections = 7.4 cm. Build the age he actually is.
N_SECTIONS = 7                       # 7 * c/(2*RATE) = 7.4 cm — an INFANT
MOTORS = ("breath", "pitch", "press", "tongue_x", "tongue_y", "lips", "jaw")
# THE VOCAL FOLDS OF A CHILD, not of a fifty-year-old man.
#
# This was 70.0-320.0, and on 2026-08-21 the babbling search slid straight to
# the floor: it chose pitch=0.0, i.e. 70 Hz, and Iddo's ear named it instantly
# — "נשמע קצת צפרדע". He was right, and the number confirms it.
#
# The search was not wrong to do it. The frozen cochlea normalises loudness
# and reads spectral SHAPE, so pitch is nearly invisible to it: 70 Hz and
# 290 Hz look almost the same through Eran's own ear, and the edge cost him
# nothing. That is a blind spot in the ear, not a fault in the child.
#
# The honest fix is NOT to type a target pitch — that would be putting words
# in his mouth, which this whole file exists to refuse. It is to give him a
# child's larynx and let him keep choosing freely inside it. A young child's
# f0 sits around 250-300 Hz; the ant farm's own measurement of Iddo's target
# child voice was ~291 Hz, which lands mid-range here.
# Iddo listened and said "משהו באמצע", then corrected the age itself:
# **"זה תינוק."** An infant's fundamental runs high — roughly 250-500 Hz,
# with crying up near 400-500 — and the low, soft end still has to be
# reachable for the breathy non-cry sounds a baby actually makes most of the
# time. So the range is wide on purpose and he keeps choosing inside it.
F0_MIN, F0_MAX = 200.0, 500.0
GLOTTIS_REFLECT = 0.95               # nearly closed end: reflects in phase
LIP_REFLECT = 0.85                   # open end: most escapes, some inverts


def _clamp01(x):
    return float(min(1.0, max(0.0, float(x))))


# A NEWBORN's anatomy, and the ONLY body written into this file.
#
# The mouth does not know how old it is and must not look it up: this module
# imports numpy and nothing else (house law, enforced by proof/test_mouth.py).
# So the CALLER fetches the body from body/growth.py and passes it in — the
# instrument is dumb, the organism knows its own age. Anything that calls
# articulate() without a body gets a newborn, because that is what ERAN is
# and a default should never flatter.
NEWBORN = {
    "tract_sections": 7, "bore_base": 0.9, "oral_min": 0.55, "oral_span": 1.20,
    "tongue_depth": 0.95, "lip_min": 0.40, "loss": 0.975,
    "f0_min": 200.0, "f0_max": 500.0, "utterance_seconds": 0.32,
    "open_quotient": 0.75, "jitter": 0.020, "shimmer": 0.090,
    "glottis_reflect": 0.86,
}


def body_of(body=None):
    """The anatomy this mouth is wearing. None -> a newborn's."""
    return dict(NEWBORN) if body is None else body


def tract_bore(tongue_x, tongue_y, lips, jaw, body=None):
    """Four articulator numbers -> the bore of the tube, in cm.

    Section 0 is the glottis, the last section is the lips. The tongue hump
    is a Gaussian narrowing whose POSITION along the tube is tongue_x and
    whose DEPTH is tongue_y; that pairing is the whole difference between
    /i/, /a/ and /u/. The jaw opens the oral half, the lips set the final
    aperture.
    """
    b = body or body_of()
    n = int(b["tract_sections"])
    d = np.full(n, float(b["bore_base"]), dtype=np.float64)
    pos = np.arange(n) / max(1, n - 1)
    d[pos >= 0.5] = float(b["oral_min"]) + float(b["oral_span"]) * _clamp01(jaw)
    centre = 0.85 - 0.72 * _clamp01(tongue_x)          # 1 = back/pharyngeal
    depth = 0.25 + float(b["tongue_depth"]) * _clamp01(tongue_y)
    d = d - depth * np.exp(-0.5 * ((pos - centre) / 0.20) ** 2)
    d[-2:] *= float(b["lip_min"]) + (1.0 - float(b["lip_min"])) * _clamp01(lips)
    return np.maximum(d, 0.05)


def reflection_coefficients(bore):
    """Kelly-Lochbaum: at every junction the area mismatch reflects the wave."""
    a = np.asarray(bore, dtype=np.float64) ** 2
    return (a[:-1] - a[1:]) / np.maximum(a[:-1] + a[1:], 1e-9)


def glottal_flow(f0_hz, n_samples, sr=RATE, open_quotient=0.6, jitter=0.006,
                 shimmer=0.03, seed=0):
    """Rosenberg glottal flow pulses: a rising opening phase, a faster
    closing phase, then a closed rest. Jitter and shimmer are not decoration
    - a source with neither is a pulse oscillator, and every ear and every
    analyser can tell. A body is never exactly periodic."""
    rng = np.random.default_rng(int(seed))
    g = np.zeros(int(n_samples), dtype=np.float64)
    period = sr / max(float(f0_hz), 1e-6)
    t = 0.0
    while t < n_samples:
        p = float(np.clip(period * (1.0 + jitter * rng.standard_normal()),
                          2.0, 4.0 * period))
        amp = 1.0 + shimmer * rng.standard_normal()
        i0 = int(round(t))
        n1 = int(0.62 * open_quotient * p)             # opening
        n2 = int(0.38 * open_quotient * p)             # closing
        if n1 >= 2 and i0 < len(g):
            k = np.arange(n1)
            hi = min(i0 + n1, len(g))
            g[i0:hi] += amp * (0.5 * (1.0 - np.cos(np.pi * k / n1)))[:hi - i0]
        j0 = i0 + n1
        if n2 >= 2 and j0 < len(g):
            k = np.arange(n2)
            hi = min(j0 + n2, len(g))
            g[j0:hi] += amp * (np.cos(0.5 * np.pi * k / n2))[:hi - j0]
        t += p
    return g


def run_tract(source, bore, loss=0.985, glottis_reflect=None):
    """Push a source through the ladder and return what leaves the lips.

    Half-sample delays are commuted into the backward path, the standard
    exact rearrangement: the forward wave sweeps glottis-to-lips within one
    sample, the backward wave crawls one section per sample. `loss` is the
    per-junction damping that real tissue has and a mirror does not.
    """
    k = reflection_coefficients(bore).tolist()
    n_j = len(k)
    b = [0.0] * N_SECTIONS
    out = np.empty(len(source), dtype=np.float64)
    for i, s in enumerate(np.asarray(source, dtype=np.float64).tolist()):
        f = s + (GLOTTIS_REFLECT if glottis_reflect is None
                 else float(glottis_reflect)) * b[0]
        for j in range(n_j):
            back = b[j + 1]
            w = k[j] * (f - back)
            b[j] = (back + w) * loss
            f += w
        out[i] = f
        b[-1] = -LIP_REFLECT * f
    return out


def _one_pole_lowpass(x, c):
    """y[n] = (1-c)*x[n] + c*y[n-1] — hand-written so this file never needs
    scipy. Numerically identical to scipy.signal.lfilter([1-c], [1,-c], x)."""
    x = np.asarray(x, dtype=np.float64)
    y = np.empty_like(x)
    acc = 0.0
    gain = 1.0 - c
    for i in range(x.shape[0]):
        acc = gain * x[i] + c * acc
        y[i] = acc
    return y


def aspiration(n_samples, sr=RATE, tilt_hz=900.0, seed=0):
    """Turbulence at the folds when they do not close cleanly.

    IT IS NOT WHITE. Real aspiration falls with frequency; white noise does
    not. A flat noise floor carries almost no energy where the glottal pulse
    is strong (below 1 kHz) but dominates above 2 kHz, where the pulse has
    fallen 40 dB — so an analyser puts its poles up in the hiss instead of
    on the vowel. The one-pole low-pass below gives the same -6 dB/octave
    tilt as mouth_v1's scipy filter, just without importing scipy.
    """
    rng = np.random.default_rng(int(seed) + 991)
    w = rng.standard_normal(int(n_samples))
    c = float(np.exp(-2.0 * np.pi * tilt_hz / sr))     # one-pole, -6 dB/oct
    return _one_pole_lowpass(w, c)


def radiate(x, alpha=0.96):
    """Radiation from the lips differentiates the flow: +6 dB per octave."""
    y = np.asarray(x, dtype=np.float64)
    out = np.empty_like(y)
    out[0] = y[0]
    out[1:] = y[1:] - alpha * y[:-1]
    return out


def articulate(breath=0.80, pitch=0.46, press=0.55, tongue_x=0.95,
               tongue_y=0.55, lips=0.90, jaw=1.00, seconds=0.45, seed=0,
               loss=0.985, jitter=0.006, shimmer=0.030, noise=0.012,
               fade_s=0.015, peak=0.55):
    """Say something. Numbers in, waveform out — no file, no bank, no memory."""
    n = int(round(seconds * RATE))
    if n < 64:
        raise ValueError("too short to articulate")
    if _clamp01(breath) < 0.05:                       # no air, no sound
        return np.zeros(n, dtype=np.float32)
    f0 = F0_MIN + (F0_MAX - F0_MIN) * _clamp01(pitch)
    oq = 0.75 - 0.35 * _clamp01(press)                # pressed folds close fast
    src = glottal_flow(f0, n, RATE, open_quotient=oq, jitter=jitter,
                       shimmer=shimmer, seed=seed)
    src = src * _clamp01(breath)
    src = src + noise * (1.0 - _clamp01(press)) * _clamp01(breath) * \
        aspiration(n, RATE, seed=seed)
    y = radiate(run_tract(src, tract_bore(tongue_x, tongue_y, lips, jaw),
                          loss=loss))
    f = min(int(fade_s * RATE), n // 2)
    if f > 0:
        y[:f] *= np.linspace(0.0, 1.0, f)
        y[n - f:] *= np.linspace(1.0, 0.0, f)
    m = float(np.max(np.abs(y))) or 1.0
    return (y * (float(peak) / m)).astype(np.float32)


# A child-scale reference posture (Iddo's child voice, ~291 Hz f0, is the
# recorded target measured in the ant farm — see project_eran_syllable_holobrain
# in memory). NOT the babble's target: the babble's target always comes from
# the organism's own brain (state/brain.json.gz), never a hand-typed posture.
# This is only a plausible starting point / sanity-check posture.
CHILD_REFERENCE = {"breath": 0.80, "pitch": 0.82, "press": 0.55,
                   "tongue_x": 0.70, "tongue_y": 0.45, "lips": 0.75,
                   "jaw": 0.55}
