# -*- coding: utf-8 -*-
"""tract.py -- ERAN gets a MOUTH. Not a tape recorder.

Iddo, 2026-08-23 14:34: "אין טעם ללמד אותו הברות בלי פה ואוזן."

He was right, and the measurement was worse than his suspicion. `voice/voice.py`, in its
own words, "finds the central train snippet and re-sequences those snippets into one wav":
ERAN could not make one sound that was not a recording of somebody else -- and that
somebody else was the synthetic corpus this morning's probe measured as transferring to a
real mouth AT CHANCE. He had an ear and a splicer. Never a mouth.

An organism that cannot act cannot learn to act. That is why nothing moved.

WHAT THIS IS. A Kelly-Lochbaum digital waveguide: the vocal tract as a chain of cylindrical
sections, sound travelling up and down it, reflecting wherever the cross-section changes.
Classical articulatory synthesis, not a neural net, and that is deliberate -- ERAN must OWN
the parameters. His motor command is:

    breath pressure  .  f0  .  the area of every section

Change the areas and the vowel changes. Nothing is memorised, nothing is spliced. Every
sample is generated. When ERAN says "abba" it will be HIS mouth doing it.

WHY A TUBE AND NOT A SAMPLER. A sampler can only replay what it was handed, so its error
signal is "which recording is closest" -- a lookup, not a motor act. A tube has continuous
parameters, so "I aimed here and heard that" has a DIRECTION, and direction is what a
babbling infant actually uses. That is the whole reason the loop can close.

GROWTH IS BUILT IN. Tract length is a function of age (~7 cm newborn -> ~17 cm adult), and
every formant scales as 1/length, which is why a baby's vowels sit so high. Iddo heard that
on 2026-08-22 before he could name it: a high pitch inside an adult tube sounds wrong,
because the two must move together.

THE TEST THIS FILE MUST PASS. A uniform tube resonates at odd multiples of c/4L -- a closed
form, no fitting. If our tube does not put its resonances there, it is not a tract; it is
noise with a filter on it.
"""
from __future__ import annotations

import numpy as np

SR = 16000
OVERSAMPLE = 4             # the waveguide runs at 64 kHz internally -- see below
C_SOUND = 35000.0          # cm/s in warm moist air

# WHY THE TUBE IS OVERSAMPLED, found by measurement on 2026-08-23.
# An impulse fired into the ladder came back at 28 / 56 / 64 / 116 samples for 8 / 15 / 17
# / 30 sections, converging on 4N -- so a wave crosses one section per TWO samples and the
# round trip is 4N, not 2N. At 16 kHz that fixes one section at c/(4*SR) = 0.55 cm, so a
# 17 cm adult tract is only ~31 sections but a 7 cm infant tract is ~13 -- and worse, the
# section count and the audio rate are welded together, so the anatomy cannot be chosen
# independently of the sample rate. Running the ladder at 4x and decimating breaks that
# weld: SECTION_CM below is now a real physical constant, not an artefact of 16 kHz.
SECTION_CM = C_SOUND / (4.0 * SR * OVERSAMPLE)      # cm of tract per ladder section


def tract_length_cm(age_days):
    """~7 cm at birth -> ~17 cm adult. Monotone, saturating, deterministic."""
    return 7.0 + 10.0 * (1.0 - np.exp(-age_days / 2200.0))


def f0_hz(age_days):
    """~440 Hz newborn cry -> ~120 Hz adult male, as the folds lengthen."""
    return 120.0 + 320.0 * np.exp(-age_days / 2600.0)


def n_sections(age_days):
    """Derived from the tract length and the MEASURED round trip, never guessed.

    Before this was measured the code simply used round(length_in_cm) as the section
    count, which quietly made 1 section = 1 cm -- a number with no physics in it. The
    impulse probe showed the real relation, and now the anatomy follows from it.
    """
    return max(4, int(round(tract_length_cm(age_days) / SECTION_CM)))


def glottal_pulse(n, f0, sr=SR, oq=0.6, jitter=0.01, rng=None):
    """Rosenberg-style glottal flow derivative. Deliberately not a sawtooth.

    A sawtooth carries energy at every harmonic forever and sounds like a buzzer. Real
    folds open slowly and slam shut, so the spectrum rolls off. `oq` is the open quotient;
    `jitter` is the cycle-to-cycle wobble without which a voice sounds dead.
    """
    rng = rng or np.random.default_rng(0)
    out = np.zeros(n, dtype=np.float64)
    i = 0
    while i < n:
        period = int(sr / max(40.0, f0 * (1.0 + rng.normal(0, jitter))))
        if period < 4:
            break
        op = max(2, int(period * oq))
        a = np.arange(op) / op
        pulse = np.zeros(period)
        pulse[:op] = 3 * a ** 2 - 2 * a ** 3                # smooth opening
        pulse = -np.diff(np.concatenate([[0.0], pulse]))    # the DERIVATIVE is the source
        k = min(period, n - i)
        out[i:i + k] = pulse[:k]
        i += period
    return out


class Tract:
    """Kelly-Lochbaum ladder. `areas` IS the motor command."""

    def __init__(self, areas, length_cm, sr=SR, round_trip_gain=0.72):
        self.areas = np.asarray(areas, dtype=np.float64)
        self.n = len(self.areas)
        self.length_cm = float(length_cm)
        self.sr = sr
        # DAMPING IS PER ROUND TRIP, NOT PER SAMPLE -- measured 2026-08-23.
        # A fixed per-sample loss of 0.995 looks harmless until the tube is long: at 124
        # sections the round trip is 496 samples and 0.995**496 = 0.084, so the wave was
        # dead before it came back and every long tract reported the SAME F1 (~1190 Hz)
        # regardless of its length. Real tract losses are per unit LENGTH, so the total
        # attenuation around one trip is what should be held constant, and the per-sample
        # figure must follow from the geometry.
        self.loss = round_trip_gain ** (1.0 / max(1, 4 * self.n))
        a1, a2 = self.areas[:-1], self.areas[1:]
        self.k = (a1 - a2) / (a1 + a2 + 1e-12)      # reflection at each junction
        self.fwd = np.zeros(self.n)
        self.bwd = np.zeros(self.n)

    def speak(self, source, lip_reflect=-0.85, glottal_reflect=0.9):
        f = self.fwd.copy()
        b = self.bwd.copy()
        k = self.k
        n = self.n
        y = np.empty(source.size)
        for t in range(source.size):
            f[0] = source[t] + glottal_reflect * b[0]
            nf = np.empty(n)
            nb = np.empty(n)
            nf[0] = f[0]
            for i in range(n - 1):
                w = k[i] * (f[i] + b[i + 1])
                nf[i + 1] = f[i] - w
                nb[i] = b[i + 1] + w
            y[t] = nf[-1] * (1.0 - lip_reflect)
            nb[-1] = lip_reflect * nf[-1]
            f = nf * self.loss
            b = nb * self.loss
        self.fwd, self.bwd = f, b
        y = np.concatenate([[y[0]], np.diff(y)])     # lip radiation differentiates
        m = np.max(np.abs(y))
        return (y / m * 0.7) if m > 0 else y


def uniform(n):
    return np.ones(n)


def vowel_a(n):
    x = np.linspace(0, 1, n)
    return 0.4 + 2.6 * x ** 1.5          # narrow at the back, open at the front


def vowel_i(n):
    x = np.linspace(0, 1, n)
    return 3.0 - 2.7 * x ** 1.2          # open at the back, narrow at the front


def vowel_u(n):
    x = np.linspace(0, 1, n)
    return 1.0 + 2.0 * np.sin(np.pi * x) - 0.7 * x ** 4     # constricted at the lips


def say(shape_fn, age_days=200.0, seconds=0.5, seed=0):
    """Synthesise at SR*OVERSAMPLE inside the tube, then decimate to SR."""
    L = tract_length_cm(age_days)
    n = n_sections(age_days)
    hi = SR * OVERSAMPLE
    tr = Tract(shape_fn(n), L, sr=hi)
    src = glottal_pulse(int(hi * seconds), f0_hz(age_days), sr=hi,
                        rng=np.random.default_rng(seed))
    y = tr.speak(src)
    # anti-alias before decimating: a moving average is a crude but honest low-pass, and
    # decimating without one would fold everything above 8 kHz back into the formants we
    # are trying to measure.
    k = np.ones(OVERSAMPLE * 2) / (OVERSAMPLE * 2)
    y = np.convolve(y, k, mode="same")[::OVERSAMPLE]
    m = np.max(np.abs(y))
    return ((y / m * 0.7) if m > 0 else y), L, f0_hz(age_days), n


def formants(y, sr=SR, n_peaks=3, order=None):
    """Formants by LPC, which is what this measurement is actually for.

    Three analyses were tried here and the first two lied, so both failures are recorded:

    (a) peak-picking the raw log spectrum -- lip radiation differentiates, tilting the
        spectrum up ~6 dB/octave, so "the tallest peaks" were always the HIGHEST
        FREQUENCIES. Every tract length and every vowel reported ~3.7 kHz.

    (b) peak-picking the de-tilted spectrum -- better, but with no minimum separation
        enforced the three "formants" came back 15 Hz apart: three bins of ONE hill.

    LPC has neither failure mode by construction. It fits an all-pole filter -- which is
    exactly what a lossless tube IS -- and each conjugate root pair is one resonance, with
    its own centre frequency and bandwidth. The poles cannot collide into one peak and the
    source tilt is not part of the model.
    """
    y = np.asarray(y, dtype=np.float64)
    if y.size < 256:
        return []
    order = order or int(2 + sr / 1000)            # the usual rule: 2 + fs/1000
    x = y * np.hamming(y.size)
    x = np.concatenate([[x[0]], x[1:] - 0.97 * x[:-1]])    # pre-emphasis
    r = np.correlate(x, x, mode="full")[x.size - 1:x.size + order]
    if r[0] <= 0:
        return []
    # Yule-Walker by direct solve rather than a hand-rolled Levinson-Durbin.
    # The hand-rolled recursion was the third thing in this function to be wrong: it put
    # F1 of a 15-section tube at 1280 Hz where the closed form says 533. A Toeplitz solve
    # is two lines, has no index arithmetic to get wrong, and at order 18 costs nothing.
    R = np.array([[r[abs(i - j)] for j in range(order)] for i in range(order)])
    try:
        coef = np.linalg.solve(R + np.eye(order) * 1e-9 * r[0], r[1:order + 1])
    except np.linalg.LinAlgError:
        return []
    a = np.concatenate([[1.0], -coef])
    rts = np.roots(a)
    rts = rts[np.imag(rts) > 0]
    if rts.size == 0:
        return []
    freqs = np.angle(rts) * sr / (2 * np.pi)
    bws = -0.5 * (sr / (2 * np.pi)) * np.log(np.abs(rts))
    # A REAL formant is narrow: bandwidth 50-150 Hz in natural speech, and a resonance in
    # a lossy tube is not much wider. The first threshold here was 700 Hz, which let LPC's
    # weak junk poles through -- measured 2026-08-23: pure white noise WITH NO TUBE AT ALL
    # reported confident "formants" at 748 / 1392 / 2006 Hz. Every vowel number this file
    # printed before this line was fixed was that junk. Poles must also sit near the unit
    # circle; a resonance that decays in a few samples is not a resonance.
    keep = (freqs > 120) & (freqs < sr / 2 - 200) & (bws < 220) & (np.abs(rts) > 0.90)
    freqs = np.sort(freqs[keep])
    return [float(v) for v in freqs[:n_peaks]]


if __name__ == "__main__":
    print("ERAN'S MOUTH -- a tube, not a tape recorder\n")
    print("growth:")
    for d in (0, 200, 1000, 4000, 12000):
        print("  age %6d d : tract %5.2f cm . f0 %5.1f Hz . %2d sections"
              % (d, tract_length_cm(d), f0_hz(d), n_sections(d)))

    print("\nPROOF: a uniform tube must resonate at odd multiples of c/4L (closed form)")
    print("%6s %7s %9s %8s %9s %8s" % ("age", "L cm", "F1 want", "F1 got", "F2 want", "F2 got"))
    ok = True
    for d in (200, 4000, 12000):
        y, L, f0, n = say(uniform, age_days=d, seconds=0.6)
        got = formants(y)
        w1 = C_SOUND / (4 * L)
        g1 = got[0] if got else float("nan")
        g2 = got[1] if len(got) > 1 else float("nan")
        print("%6d %7.2f %9.0f %8.0f %9.0f %8.0f" % (d, L, w1, g1, 3 * w1, g2))
        if not (abs(g1 - w1) / w1 < 0.30):
            ok = False

    print("\nvowels from the SAME tube -- only the areas differ:")
    for name, fn in (("a", vowel_a), ("i", vowel_i), ("u", vowel_u)):
        y, L, f0, n = say(fn, age_days=4000, seconds=0.6)
        fm = formants(y)
        print("  /%s/  formants %s" % (name, ["%.0f" % v for v in fm]))

    print("\n%s" % ("TUBE VERIFIED against the closed form." if ok else
                    "TUBE FAILED the closed form -- this is not a vocal tract yet."))
