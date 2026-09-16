# -*- coding: utf-8 -*-
"""glottis.py -- per-period analytic LF glottal source for MOUTH v2.

The larynx of the new mouth: a Liljencrants-Fant (LF) glottal flow
DERIVATIVE, set up once per period from tenseness, exactly as Pink
Trombone does it. Because the source is the flow derivative, lip
radiation (+6 dB/oct) is already folded in and the tract output needs
no extra differentiator -- Pink Trombone semantics throughout.

PORTED SOURCES (honest list)
============================
* Pink Trombone (IMAGINARY/pink-trombone, MIT), fetched 2026-08-26 from
  raw.githubusercontent.com/IMAGINARY/pink-trombone/master/index.html:
    - Glottis.setupWaveform  -> _lf_params(): Rd = 3(1-tenseness) clipped
      [0.5, 2.7] -> Ra, Rk, Rg -> Ta, Tp, Te -> epsilon, shift, Delta,
      alpha, E0, omega. Line-for-line the same algebra.
    - Glottis.normalizedLFWaveform -> _lf_period(): t<=Te rising
      E0*exp(alpha t)*sin(omega t), t>Te exponential return
      (-exp(-eps(t-Te))+shift)/Delta.
    - Glottis.getNoiseModulator -> the noise_mod array: voiced =
      0.1+0.2*max(0,sin(2 pi t/T)); mod = ten*int*voiced+(1-ten*int)*0.3.
    - aspiration = intensity*(1-sqrt(tenseness))*noise_mod*noise, with
      the slow flutter factor 0.2+0.02*(simplex noise). DEVIATION: PT's
      simplex1(totalTime*1.99) is replaced by sin(2 pi*1.99*t + phase)
      with the phase drawn from the aspiration stream -- we have no
      simplex and a seeded sinusoid is deterministic and twin-portable.
    - loudness = tenseness**0.25 (PT handleTouches).
* D:/CLAUDE/eran-brain/voice/mouth.py aspiration() -- the -6 dB/oct
  one-pole tilt filter, y[n] = (1-c)x[n] + c y[n-1],
  c = exp(-2 pi * 900 / sr). Identical difference equation here.

DETERMINISM CONTRACT (for the future C twin)
============================================
Every noise source has its OWN np.random.Generator(PCG64(seed+1000*k)):

    k=1 jitter      one standard_normal PER PERIOD (draw #m for period m)
    k=2 shimmer     one standard_normal PER PERIOD
    k=3 drift       one standard_normal PER PERIOD (leaky-integrated)
    k=4 vibrato     TWO draws at init, in order: uniform() -> rate in
                    [4.5, 5.5] Hz, uniform() -> phase in [0, 2 pi)
    k=5 aspiration  ONE uniform() at init (flutter phase in [0, 2 pi)),
                    then n_samples standard_normal in one block
    k=6 turbulence  NOT drawn here -- reserved for tract_core.py, which
                    draws n_samples standard_normal in one block

No other draws exist. A C twin that reproduces PCG64 and this draw
order reproduces the waveform bit-for-bit (modulo float assoc).

NOISE PHYSIOLOGY DEFAULTS (per the ERAN 2.0 plan):
jitter 1.2% per period, shimmer 5% per period, slow 1/f-ish drift
clipped +-2% (leaky-integrated white noise, 0.5 Hz pole), vibrato
~5 Hz +-0.2 semitones with seeded rate and phase.

numpy only. No file I/O, no wall clock.
"""
from __future__ import annotations

from typing import NamedTuple, Optional, Sequence

import numpy as np

RD_MIN, RD_MAX = 0.5, 2.7          # PT setupWaveform clip
JITTER_DEFAULT = 0.012             # 1.2 % per-period f0 wobble
SHIMMER_DEFAULT = 0.05             # 5 % per-period amplitude wobble
DRIFT_CLIP = 0.02                  # slow drift never exceeds +-2 %
DRIFT_SIGMA = 0.01                 # ~1 % rms before the clip
DRIFT_POLE_HZ = 0.5                # leaky-integrator cutoff
VIBRATO_SEMITONES = 0.2            # +-0.2 st
VIBRATO_RATE_LO, VIBRATO_RATE_HI = 4.5, 5.5   # "~5 Hz", seeded
ASPIRATION_TILT_HZ = 900.0         # mouth.py aspiration(): -6 dB/oct knee

_STREAMS = {"jitter": 1, "shimmer": 2, "drift": 3, "vibrato": 4,
            "aspiration": 5, "turbulence": 6}


def stream_rng(seed: int, name: str) -> np.random.Generator:
    """The one blessed way to make a noise stream. tract_core uses it too."""
    return np.random.Generator(np.random.PCG64(int(seed) + 1000 * _STREAMS[name]))


def cosine_knots(knots: Sequence[float], t01: np.ndarray) -> np.ndarray:
    """3 (or more) knots equally spaced over [0,1], cosine-interpolated.
    Piecewise: between adjacent knots x(u) = a + (b-a)*(1-cos(pi u))/2."""
    k = np.asarray(knots, dtype=float)
    if k.size == 1:
        return np.full_like(np.asarray(t01, float), k[0])
    seg = (k.size - 1) * np.clip(np.asarray(t01, float), 0.0, 1.0)
    i = np.minimum(seg.astype(int), k.size - 2)
    u = seg - i
    w = 0.5 * (1.0 - np.cos(np.pi * u))
    return k[i] * (1.0 - w) + k[i + 1] * w


def one_pole_lowpass(x: np.ndarray, c: float) -> np.ndarray:
    """y[n] = (1-c) x[n] + c y[n-1] -- verbatim from voice/mouth.py
    _one_pole_lowpass (its hand-written scipy-free tilt filter)."""
    x = np.asarray(x, dtype=np.float64)
    y = np.empty_like(x)
    acc = 0.0
    g = 1.0 - c
    for i in range(x.shape[0]):
        acc = g * x[i] + c * acc
        y[i] = acc
    return y


def _lf_params(tenseness: float):
    """PT Glottis.setupWaveform, verbatim algebra. Returns the per-period
    constants (alpha, E0, epsilon, shift, Delta, Te, omega)."""
    Rd = 3.0 * (1.0 - tenseness)
    Rd = min(max(Rd, RD_MIN), RD_MAX)
    Ra = -0.01 + 0.048 * Rd
    Rk = 0.224 + 0.118 * Rd
    Rg = (Rk / 4.0) * (0.5 + 1.2 * Rk) / (0.11 * Rd - Ra * (0.5 + 1.2 * Rk))
    Ta = Ra
    Tp = 1.0 / (2.0 * Rg)
    Te = Tp + Tp * Rk

    epsilon = 1.0 / Ta
    shift = np.exp(-epsilon * (1.0 - Te))
    Delta = 1.0 - shift

    rhs_integral = ((1.0 / epsilon) * (shift - 1.0) + (1.0 - Te) * shift) / Delta
    total_lower = -(Te - Tp) / 2.0 + rhs_integral
    total_upper = -total_lower

    omega = np.pi / Tp
    s = np.sin(omega * Te)
    y = -np.pi * s * total_upper / (Tp * 2.0)
    z = np.log(y)
    alpha = z / (Tp / 2.0 - Te)
    E0 = -1.0 / (s * np.exp(alpha * Te))
    return alpha, E0, epsilon, shift, Delta, Te, omega


def _lf_period(n: int, params) -> np.ndarray:
    """One period of the normalized LF flow derivative, n samples,
    t = (i)/n in [0,1). PT normalizedLFWaveform, vectorized."""
    alpha, E0, epsilon, shift, Delta, Te, omega = params
    t = np.arange(n, dtype=np.float64) / n
    rising = E0 * np.exp(alpha * t) * np.sin(omega * t)
    falling = (-np.exp(-epsilon * (t - Te)) + shift) / Delta
    return np.where(t > Te, falling, rising)


class GlottalOutput(NamedTuple):
    """render()'s result. The plan's API named (voiced_flow,
    aspiration_noise); noise_mod is APPENDED (documented deviation)
    because PT's turbulence is modulated by the same glottal-cycle
    modulator and tract_core needs it."""
    voiced: np.ndarray       # LF flow-derivative pulse train, @ sr
    aspiration: np.ndarray   # tilted, cycle-modulated noise, @ sr
    noise_mod: np.ndarray    # PT getNoiseModulator per sample, @ sr


class GlottalSource:
    """Per-period analytic LF source with jitter/shimmer/drift/vibrato.

    f0_knots        3 knots, Hz, cosine-interpolated in LOG-Hz over the
                    utterance.
    tenseness_knots 3 knots in [0.25, 0.95], cosine-interpolated;
                    overridden per-sample by tenseness_env if given.
    intensity_env   optional per-sample envelope in [0,1] (voicing);
                    default: ones with a 15 ms raised-cosine attack.
    """

    def __init__(self, f0_knots, tenseness_knots, seconds, sr, seed,
                 jitter=JITTER_DEFAULT, shimmer=SHIMMER_DEFAULT,
                 intensity_env: Optional[np.ndarray] = None,
                 tenseness_env: Optional[np.ndarray] = None):
        self.sr = int(sr)
        self.n = int(round(float(seconds) * self.sr))
        self.f0_knots = np.asarray(f0_knots, dtype=float)
        self.ten_knots = np.asarray(tenseness_knots, dtype=float)
        self.seed = int(seed)
        self.jitter = float(jitter)
        self.shimmer = float(shimmer)

        t01 = np.arange(self.n) / max(1, self.n - 1)
        if tenseness_env is not None:
            te = np.asarray(tenseness_env, dtype=float)
            if te.size != self.n:
                raise ValueError("tenseness_env length %d != %d" % (te.size, self.n))
            self.ten_env = np.clip(te, 0.05, 0.99)
        else:
            self.ten_env = np.clip(cosine_knots(self.ten_knots, t01), 0.05, 0.99)
        if intensity_env is not None:
            ie = np.asarray(intensity_env, dtype=float)
            if ie.size != self.n:
                raise ValueError("intensity_env length %d != %d" % (ie.size, self.n))
            self.int_env = np.clip(ie, 0.0, 1.0)
        else:
            self.int_env = np.ones(self.n)
            a = min(int(0.015 * self.sr), self.n)     # 15 ms attack
            if a > 1:
                self.int_env[:a] = 0.5 * (1.0 - np.cos(np.pi * np.arange(a) / a))
        # log-Hz f0 contour, per-sample (evaluated at period starts below)
        self.log_f0 = cosine_knots(np.log(self.f0_knots), t01)

    def render(self) -> GlottalOutput:
        n, sr = self.n, self.sr
        rng_j = stream_rng(self.seed, "jitter")
        rng_s = stream_rng(self.seed, "shimmer")
        rng_d = stream_rng(self.seed, "drift")
        rng_v = stream_rng(self.seed, "vibrato")
        rng_a = stream_rng(self.seed, "aspiration")

        # vibrato: 2 draws, documented order (rate then phase)
        vib_rate = VIBRATO_RATE_LO + rng_v.uniform() * (VIBRATO_RATE_HI - VIBRATO_RATE_LO)
        vib_phase = rng_v.uniform() * 2.0 * np.pi
        # aspiration: flutter phase first, then the noise block
        flutter_phase = rng_a.uniform() * 2.0 * np.pi
        asp_white = rng_a.standard_normal(n)

        voiced = np.zeros(n)
        noise_mod = np.zeros(n)

        # drift: leaky-integrated unit-variance state (exact stationary
        # variance via the sqrt(1-a^2) input gain), scaled to DRIFT_SIGMA
        # and clipped at +-DRIFT_CLIP -- "slow 1/f-ish", documented approx.
        drift_state = 0.0

        i = 0
        while i < n:
            t0 = i / sr
            f0_base = float(np.exp(self.log_f0[i]))
            ten = float(self.ten_env[i])

            # per-period draws -- ONE from each stream, this exact order
            g_jit = rng_j.standard_normal()
            g_shm = rng_s.standard_normal()
            g_drf = rng_d.standard_normal()

            period_guess = 1.0 / max(f0_base, 1.0)
            a_d = float(np.exp(-2.0 * np.pi * DRIFT_POLE_HZ * period_guess))
            drift_state = a_d * drift_state + np.sqrt(max(0.0, 1.0 - a_d * a_d)) * g_drf
            drift_fac = float(np.clip(1.0 + DRIFT_SIGMA * drift_state,
                                      1.0 - DRIFT_CLIP, 1.0 + DRIFT_CLIP))
            vib_fac = 2.0 ** ((VIBRATO_SEMITONES / 12.0)
                              * np.sin(2.0 * np.pi * vib_rate * t0 + vib_phase))
            f0 = f0_base * drift_fac * vib_fac * (1.0 + self.jitter * g_jit)
            n_p = max(4, int(round(sr / max(f0, 1.0))))
            n_use = min(n_p, n - i)

            params = _lf_params(ten)
            wave = _lf_period(n_p, params)[:n_use]
            amp = (1.0 + self.shimmer * g_shm) * (ten ** 0.25)   # shimmer * PT loudness
            voiced[i:i + n_use] = amp * wave

            # PT getNoiseModulator, per sample within this period
            t_norm = np.arange(n_use, dtype=np.float64) / n_p
            v_cyc = 0.1 + 0.2 * np.maximum(0.0, np.sin(2.0 * np.pi * t_norm))
            ten_int = self.ten_env[i:i + n_use] * self.int_env[i:i + n_use]
            noise_mod[i:i + n_use] = ten_int * v_cyc + (1.0 - ten_int) * 0.3

            i += n_p

        voiced *= self.int_env

        # aspiration: tilt (mouth.py one-pole), PT scaling + flutter
        c = float(np.exp(-2.0 * np.pi * ASPIRATION_TILT_HZ / sr))
        tilted = one_pole_lowpass(asp_white, c)
        t = np.arange(n) / sr
        flutter = 0.2 + 0.02 * np.sin(2.0 * np.pi * 1.99 * t + flutter_phase)
        aspiration = (self.int_env * (1.0 - np.sqrt(self.ten_env))
                      * noise_mod * flutter * tilted)
        return GlottalOutput(voiced, aspiration, noise_mod)


if __name__ == "__main__":
    print("GLOTTIS self-check")
    print("=" * 60)
    src = GlottalSource([280.0, 280.0, 250.0], [0.6, 0.6, 0.6],
                        seconds=0.5, sr=48000, seed=0)
    v, a, m = src.render()
    v2, a2, m2 = GlottalSource([280.0, 280.0, 250.0], [0.6, 0.6, 0.6],
                               seconds=0.5, sr=48000, seed=0).render()
    det = (np.array_equal(v, v2) and np.array_equal(a, a2)
           and np.array_equal(m, m2))
    print("determinism (same seed, fresh object): %s" % ("PASS" if det else "FAIL"))
    v3 = GlottalSource([280.0, 280.0, 250.0], [0.6, 0.6, 0.6],
                       seconds=0.5, sr=48000, seed=1).render().voiced
    print("different seed differs: %s"
          % ("PASS" if not np.array_equal(v, v3) else "FAIL"))
    # period sanity: zero crossings of the pulse train ~ f0
    neg_peaks = np.where((v[1:-1] < v[:-2]) & (v[1:-1] < v[2:])
                         & (v[1:-1] < -0.3 * np.abs(v).max()))[0]
    if neg_peaks.size > 3:
        periods = np.diff(neg_peaks)
        periods = periods[periods > 20]
        f0_measured = 48000.0 / np.median(periods)
        print("median measured f0: %.1f Hz (asked 280->250, jitter 1.2%%)"
              % f0_measured)
    print("voiced peak %.3f  aspiration rms %.4f  mod range [%.2f, %.2f]"
          % (np.abs(v).max(), np.sqrt(np.mean(a ** 2)), m.min(), m.max()))
    # LF sanity at fixed tenseness: waveform min should be ~ -loudness (Ee=1)
    p = _lf_params(0.6)
    w = _lf_period(200, p)
    print("LF period (ten=0.6): min %.3f (want ~-1, Ee-normalized), "
          "Te=%.3f, mean %.4f" % (w.min(), p[5], w.mean()))
    print("done.")
