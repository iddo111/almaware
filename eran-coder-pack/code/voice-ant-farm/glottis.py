# -*- coding: utf-8 -*-
"""glottis.py - the queen's own mouth.

A source-filter vocal tract: a glottal pulse train driven through a cascade of
formant resonators and out through the lips. Nothing in this file has ever heard
a recording. It cannot open a file, it cannot be handed a waveform bank, and it
holds no stored samples - the only way it can sound like Iddo's /a/ is by being
SHAPED like Iddo's /a/, which is what imitation means.

That is the whole point of the amended coronation law (Iddo, 2026-08-13):

    "its ok if the queen copies me with her own mouth - that's learning isnt it"

Copying with her own mouth is learning. Splicing a recording is a tape recorder.
This module is the mouth. ah_criterion.audit_production_module() is the proof,
and it is run against this file by the test suite on every run.

The articulatory parameters are: f0 (how fast the vocal folds beat), the open
quotient (how the folds open and close), the formant frequencies and bandwidths
(the shape of the tube above them), jitter and shimmer (that the body is alive
and not a signal generator). Five numbers and a length. No audio.

No torch. numpy + scipy.signal only. No audio device is opened; this returns an
array and nothing else.
"""
from __future__ import annotations

import numpy as np
from scipy.signal import lfilter

# Default bandwidths, Hz. Wider for the higher formants, as in a real tract.
DEFAULT_BANDWIDTHS_HZ = (80.0, 100.0, 150.0, 250.0, 300.0)
# The upper formants are not part of the /a/ target but a real tract has them,
# and leaving them out invites the analyser to put spurious poles up there.
DEFAULT_UPPER_FORMANTS_HZ = (3400.0, 4500.0)


def glottal_pulse_train(f0_hz, n_samples, sr, open_quotient=0.6,
                        jitter=0.005, shimmer=0.03, seed=0):
    """Rosenberg glottal FLOW pulses at f0, with period jitter and amplitude
    shimmer. Jitter and shimmer are what separate a living larynx from an
    oscillator - without them this is a sine bank, and the judge says so."""
    rng = np.random.default_rng(seed)
    g = np.zeros(int(n_samples), dtype=np.float64)
    t = 0.0
    period = sr / float(f0_hz)
    while t < n_samples:
        p = period * (1.0 + jitter * rng.standard_normal())
        p = float(np.clip(p, 2.0, 4.0 * period))
        amp = 1.0 + shimmer * rng.standard_normal()
        n1 = int(open_quotient * 0.62 * p)          # opening phase
        n2 = int(open_quotient * 0.38 * p)          # closing phase
        i0 = int(round(t))
        if n1 >= 2:
            k = np.arange(n1)
            seg = 0.5 * (1.0 - np.cos(np.pi * k / n1))
            hi = min(i0 + n1, len(g))
            g[i0:hi] += amp * seg[:hi - i0]
        if n2 >= 2:
            k = np.arange(n2)
            seg = np.cos(0.5 * np.pi * k / n2)
            j0 = i0 + n1
            hi = min(j0 + n2, len(g))
            if j0 < len(g):
                g[j0:hi] += amp * seg[:hi - j0]
        t += p
    return g


def _resonator_coeffs(f_hz, bw_hz, sr):
    """One two-pole resonator: a single cavity of the tube."""
    r = float(np.exp(-np.pi * bw_hz / sr))
    theta = 2.0 * np.pi * f_hz / sr
    a1 = -2.0 * r * np.cos(theta)
    a2 = r * r
    b0 = 1.0 + a1 + a2                               # unity gain at DC
    return b0, a1, a2


def formant_cascade(x, formants_hz, bandwidths_hz, sr, formants_hz_end=None):
    """Run the source through the tube. If formants_hz_end is given the tube
    CHANGES SHAPE over the utterance - which is how a sweep is produced, and a
    sweep is not a vowel."""
    y = np.asarray(x, dtype=np.float64)
    if formants_hz_end is None:
        for f, bw in zip(formants_hz, bandwidths_hz):
            b0, a1, a2 = _resonator_coeffs(f, bw, sr)
            y = lfilter([b0], [1.0, a1, a2], y)
        return y
    n = len(y)
    ramp = np.linspace(0.0, 1.0, n)
    for f0_, f1_, bw in zip(formants_hz, formants_hz_end, bandwidths_hz):
        track = f0_ + (f1_ - f0_) * ramp
        out = np.zeros(n)
        z1 = z2 = 0.0
        for i in range(n):                            # time-varying tube
            b0, a1, a2 = _resonator_coeffs(track[i], bw, sr)
            v = b0 * y[i] - a1 * z1 - a2 * z2
            out[i] = v
            z2, z1 = z1, v
        y = out
    return y


def lip_radiation(x, alpha=0.98):
    """Radiation from the lips differentiates the flow. +6 dB/octave."""
    return lfilter([1.0, -float(alpha)], [1.0], np.asarray(x, dtype=np.float64))


def articulate_vowel(f0_hz=186.0, formants_hz=(689.0, 1464.0, 2600.0),
                     bandwidths_hz=None, duration_s=0.40, sr=16000,
                     open_quotient=0.6, jitter=0.005, shimmer=0.03,
                     fade_s=0.015, peak=0.5, seed=0, formants_hz_end=None,
                     include_upper_formants=True):
    """Produce a vowel. Articulatory parameters in, waveform out, no audio ever
    read. This is the reference implementation of an ACHIEVABLE rung-1 queen:
    ah_criterion's own test suite crowns the output of this function."""
    n = int(round(duration_s * sr))
    if n < 64:
        raise ValueError("duration too short to articulate")
    fs = list(formants_hz)
    fe = list(formants_hz_end) if formants_hz_end is not None else None
    if include_upper_formants:
        fs = fs + [f for f in DEFAULT_UPPER_FORMANTS_HZ if f > max(fs)]
        if fe is not None:
            fe = fe + [f for f in DEFAULT_UPPER_FORMANTS_HZ if f > max(fe)]
            fe = fe[:len(fs)] + fs[len(fe):]
    bws = list(bandwidths_hz) if bandwidths_hz is not None else \
        list(DEFAULT_BANDWIDTHS_HZ)
    while len(bws) < len(fs):
        bws.append(bws[-1])
    bws = bws[:len(fs)]

    src = glottal_pulse_train(f0_hz, n, sr, open_quotient=open_quotient,
                              jitter=jitter, shimmer=shimmer, seed=seed)
    y = formant_cascade(src, fs, bws, sr, formants_hz_end=fe)
    y = lip_radiation(y)

    f = min(int(fade_s * sr), n // 2)
    if f > 0:
        y[:f] *= np.linspace(0.0, 1.0, f)
        y[n - f:] *= np.linspace(1.0, 0.0, f)
    m = float(np.max(np.abs(y))) or 1.0
    return (y * (peak / m)).astype(np.float32)
