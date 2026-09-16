# -*- coding: utf-8 -*-
"""mouth_v1.py - an ARTICULATORY mouth that cannot replay, only articulate.

לזכרה של עלמה ז״ל

Seven numbers in, a waveform out. Nothing else. This file has never heard a
recording: it cannot read a file, it holds no stored sound, and it imports
nothing but numpy. The only way it can sound like Iddo's /a/ is by being SHAPED
like Iddo's /a/ - which is what imitation means, and imitation is learning.

    "its ok if the queen copies me with her own mouth - that's learning isnt it"
                                                        - Iddo, 2026-08-13

WHY THIS EXISTS ALONGSIDE glottis.py. glottis.py is a source-FILTER mouth: you
hand it F1 and F2 directly, so hitting the /a/ target is a matter of typing the
target in. This one is a TUBE. You hand it a tongue position, a jaw angle and a
lip aperture, and the formants are whatever the resulting bore happens to
resonate at. Nobody types 689 Hz anywhere in this file. That is the version a
colony can learn to drive and a body can later be built to match.

WHY IT IS NOT head_sim.py, which is also a tube and older. head_sim carries a
write_wav() helper, so `import wave` sits in its call graph, and the provenance
audit - correctly, bluntly - refuses it. A mouth may not carry a file writer.
This module carries none; a caller who wants a .wav writes it themselves.

THE PHYSICS, honestly labelled:
  source   Rosenberg-style glottal FLOW pulses with period jitter and amplitude
           shimmer. Parametric, NOT self-oscillating: pitch is a number we set,
           not something the air discovers. That remains the largest gap between
           this and a larynx.
  tract    Kelly-Lochbaum waveguide ladder, 16 sections of 1.06 cm = 17.0 cm,
           an adult vocal tract by construction. Closed at the glottis, open at
           the lips, so a uniform bore must resonate at 1:3:5 - the test that
           proves this is a tube and not a filter bank in a costume.
  losses   A per-junction loss factor. Real tissue is not a mirror; without this
           the resonances are needle-sharp and no analyser can track them.
  lips     Radiation differentiates the flow, +6 dB/octave.
"""
from __future__ import annotations

import numpy as np
from scipy.signal import lfilter

RATE = 16000
N_SECTIONS = 16                      # 16 * c/(2*RATE) = 17.0 cm of tube
MOTORS = ("breath", "pitch", "press", "tongue_x", "tongue_y", "lips", "jaw")
F0_MIN, F0_MAX = 70.0, 320.0
GLOTTIS_REFLECT = 0.95               # nearly closed end: reflects in phase
LIP_REFLECT = 0.85                   # open end: most escapes, some inverts


def _clamp01(x):
    return float(min(1.0, max(0.0, float(x))))


def tract_bore(tongue_x, tongue_y, lips, jaw):
    """Four articulator numbers -> the bore of the tube, in cm.

    Section 0 is the glottis, the last section is the lips. The tongue hump is a
    Gaussian narrowing whose POSITION along the tube is tongue_x and whose DEPTH
    is tongue_y; that pairing is the whole difference between /i/, /a/ and /u/.
    The jaw opens the oral half, the lips set the final aperture.

    RANGES, and why they are not head_sim's - with a correction I owe the record.
    My first reason for widening them was WRONG: I measured head_sim's tube
    through the white-noise bug described in aspiration() and concluded its
    ranges could not reach /a/. They can. Driven properly, head_sim's own
    geometry hits the target dead on - Mahalanobis 0.00 at F1 689 / F2 1464,
    6 seeds out of 6. Nothing about the tube or its ranges was ever the problem.

    The ranges here are wider for a DIFFERENT and measured reason. This module
    adds per-junction damping and lip radiation, which head_sim has neither of;
    that moves the optimum and narrows the basin around it. Re-searched on
    head_sim's exact ranges, this tube reaches Mahalanobis 0.37 but holds it for
    only 2 seeds in 6. On the ranges below it reaches 0.23 and holds for 6 in 6.
    An unconstrained optimisation over all 16 bores lands on a 0.33-0.49 cm
    pharynx flaring into a 2.7-3.2 cm mouth, so opening the jaw to 3.4 cm is
    also the anatomically right direction. Wider, because it is steadier.
    """
    d = np.full(N_SECTIONS, 1.8, dtype=np.float64)
    pos = np.arange(N_SECTIONS) / (N_SECTIONS - 1)
    d[pos >= 0.5] = 1.00 + 2.40 * _clamp01(jaw)        # oral cavity, 1.0-3.4 cm
    centre = 0.85 - 0.72 * _clamp01(tongue_x)          # 1 = back/pharyngeal
    depth = 0.25 + 1.55 * _clamp01(tongue_y)
    d = d - depth * np.exp(-0.5 * ((pos - centre) / 0.20) ** 2)
    d[-2:] *= 0.25 + 0.75 * _clamp01(lips)
    return np.maximum(d, 0.05)


def reflection_coefficients(bore):
    """Kelly-Lochbaum: at every junction the area mismatch reflects the wave."""
    a = np.asarray(bore, dtype=np.float64) ** 2
    return (a[:-1] - a[1:]) / np.maximum(a[:-1] + a[1:], 1e-9)


def glottal_flow(f0_hz, n_samples, sr=RATE, open_quotient=0.6, jitter=0.006,
                 shimmer=0.03, seed=0):
    """Rosenberg glottal flow pulses: a rising opening phase, a faster closing
    phase, then a closed rest. Jitter and shimmer are not decoration - a source
    with neither is a pulse oscillator, and every ear and every analyser can
    tell. A body is never exactly periodic."""
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


def run_tract(source, bore, loss=0.985):
    """Push a source through the ladder and return what leaves the lips.

    Half-sample delays are commuted into the backward path, the standard exact
    rearrangement: the forward wave sweeps glottis-to-lips within one sample,
    the backward wave crawls one section per sample. `loss` is the per-junction
    damping that real tissue has and a mirror does not.
    """
    k = reflection_coefficients(bore).tolist()
    n_j = len(k)
    b = [0.0] * N_SECTIONS
    out = np.empty(len(source), dtype=np.float64)
    for i, s in enumerate(np.asarray(source, dtype=np.float64).tolist()):
        f = s + GLOTTIS_REFLECT * b[0]
        for j in range(n_j):
            back = b[j + 1]
            w = k[j] * (f - back)
            b[j] = (back + w) * loss
            f += w
        out[i] = f
        b[-1] = -LIP_REFLECT * f
    return out


def aspiration(n_samples, sr=RATE, tilt_hz=900.0, seed=0):
    """Turbulence at the folds when they do not close cleanly.

    IT IS NOT WHITE, and that detail cost me the first working version. Real
    aspiration falls with frequency; white noise does not. A flat noise floor
    carries almost no energy where the glottal pulse is strong (below 1 kHz) but
    dominates above 2 kHz, where the pulse has fallen 40 dB - so every analyser
    puts its poles up in the hiss instead of on the vowel. Measured on this
    tube: with white noise at gain 0.02 the judge read F1/F2 as 888/2707 Hz;
    with the same tube and the noise shaped and quieter it read 680/1044, within
    2% of the tube's own impulse-response resonances (658/1094). Same tube, same
    vowel, 1600 Hz of difference in what an analyser saw. head_sim.py injects
    white noise at gain 0.05 and shows the same signature.
    """
    rng = np.random.default_rng(int(seed) + 991)
    w = rng.standard_normal(int(n_samples))
    c = float(np.exp(-2.0 * np.pi * tilt_hz / sr))     # one-pole, -6 dB/oct
    return lfilter([1.0 - c], [1.0, -c], w)


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
    """Say something. Numbers in, waveform out - no file, no bank, no memory."""
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


# Articulator settings found by searching THIS tube against ah_criterion's
# gate 1. No formant frequency is typed anywhere in this file - these are a
# tongue, a jaw and a pair of lips, and the vowel is what the bore does.
AH = {"breath": 0.80, "pitch": 0.46, "press": 0.64, "tongue_x": 1.00,
      "tongue_y": 0.30, "lips": 1.00, "jaw": 0.41}
EE = {"breath": 0.80, "pitch": 0.46, "press": 0.60, "tongue_x": 0.35,
      "tongue_y": 0.95, "lips": 1.00, "jaw": 0.60}
