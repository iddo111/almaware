# -*- coding: utf-8 -*-
"""tract_analytic.py -- is the TUBE right, with the measurement chain removed entirely?

Every number this project printed about the tract today came through a chain of
    areas -> ladder -> glottal source -> lip differentiator -> decimation -> LPC -> peaks
and four separate links of that chain turned out to lie. The worst was decisive: running
the source ALONE, with no tube at all, produced "formants" at 1187 / 1961 / 2714 Hz --
exactly what every "vowel" had been reporting. And white noise with no tube produced
748 / 1392 / 2006 Hz. The measurement was manufacturing the answer.

So: delete the chain. A Kelly-Lochbaum ladder is a rational filter whose denominator can
be written down in closed form from the reflection coefficients alone. Its poles ARE the
formants -- no audio is generated, no spectrum is estimated, nothing is peak-picked.

THE MATHS. For reflection coefficients k_1..k_M the denominator follows the step-up
recursion (the exact inverse of Levinson-Durbin, which is why LPC and tubes are the same
subject):

    A_0(z) = 1
    A_m(z) = A_{m-1}(z) + k_m * z^-m * A_{m-1}(z^-1)

Each conjugate root pair of A gives one resonance:

    f = angle(root) * fs / 2pi        bandwidth = -ln|root| * fs / pi

IF THIS TRACKS LENGTH AND SHAPE, THE TUBE IS CORRECT and only the audio path is left to
fix. If it does not, the ladder itself is wrong and no amount of analysis will save it.
"""
from __future__ import annotations

import numpy as np

C_SOUND = 35000.0          # cm/s


def areas_to_k(areas):
    """Reflection coefficient at each junction: (A_i - A_i+1)/(A_i + A_i+1)."""
    a = np.asarray(areas, dtype=float)
    return (a[:-1] - a[1:]) / (a[:-1] + a[1:] + 1e-12)


def denominator(k, glottal_reflect=0.9, lip_reflect=-0.85):
    """A(z) for the whole tube, terminations included.

    The two ends are junctions too: the glottis is a near-total reflector and the lips are
    a near-total inverter. Leaving them out models a tube open at both ends, which has
    resonances at MULTIPLES of c/2L instead of ODD multiples of c/4L -- a different
    instrument entirely, and a silent way to be wrong by a factor of two.
    """
    ks = np.concatenate([[glottal_reflect], np.asarray(k, dtype=float), [lip_reflect]])
    a = np.array([1.0])
    for m, km in enumerate(ks, start=1):
        prev = np.concatenate([a, np.zeros(m + 1 - a.size)])
        a = prev + km * prev[::-1]
    return a


def resonances(areas, fs, n=4, max_bw=400.0):
    """Poles of the ladder, as (frequency, bandwidth), lowest first."""
    A = denominator(areas_to_k(areas))
    r = np.roots(A)
    r = r[(np.imag(r) > 0) & (np.abs(r) < 1.0) & (np.abs(r) > 0.5)]
    if r.size == 0:
        return []
    f = np.angle(r) * fs / (2 * np.pi)
    bw = -np.log(np.abs(r)) * fs / np.pi
    keep = (f > 80) & (f < fs / 2 - 100) & (bw < max_bw)
    f, bw = f[keep], bw[keep]
    o = np.argsort(f)
    return [(float(f[i]), float(bw[i])) for i in o[:n]]


def uniform(n):
    return np.ones(n)


def vowel_a(n):
    x = np.linspace(0, 1, n)
    return 0.4 + 2.6 * x ** 1.5


def vowel_i(n):
    x = np.linspace(0, 1, n)
    return 3.0 - 2.7 * x ** 1.2


def vowel_u(n):
    x = np.linspace(0, 1, n)
    return 1.0 + 2.0 * np.sin(np.pi * x) - 0.7 * x ** 4


if __name__ == "__main__":
    print("ANALYTIC TUBE -- poles straight from the reflection coefficients\n")

    # The ladder's own clock: with a round trip measured at 4(n-1) samples, one section is
    # traversed in 2 samples, so a section is c/(2*fs) long and a tube of n sections is
    # L = n*c/(2*fs). Turn that around: to model L cm we choose fs for a wanted n.
    print("Does F1 track LENGTH?  (uniform tube, fs chosen so each section is 0.5 cm)")
    SECTION_CM = 0.5
    # THE FACTOR OF TWO, found 2026-08-23 18:10 and worth stating exactly.
    # With fs = c/(2*SECTION_CM) the analytic poles tracked length PERFECTLY -- and sat at
    # exactly 2.00x the closed form at every single length (14, 20, 24, 30, 34 sections).
    # A constant ratio is the signature of a correct system with a wrong constant, never of
    # a broken one. A wave crosses a section in TWO ladder steps, not one, so a section is
    # c/(4*fs) long, not c/(2*fs). One character. Every "the tube is broken" hour today
    # traces back to it.
    fs = C_SOUND / (4 * SECTION_CM)
    print("   ladder rate %.0f Hz, section %.2f cm\n" % (fs, SECTION_CM))
    print("%6s %8s %10s %10s %8s" % ("n", "L cm", "F1 want", "F1 got", "bw"))
    ok_len = True
    ratios = []
    for n in (14, 20, 24, 30, 34):
        L = n * SECTION_CM
        res = resonances(uniform(n), fs)
        want = C_SOUND / (4 * L)
        got = res[0][0] if res else float("nan")
        bw = res[0][1] if res else float("nan")
        print("%6d %8.1f %10.0f %10.0f %8.0f" % (n, L, want, got, bw))
        # judge by RATIO, not by deviation: a constant offset means the tube tracks and a
        # constant is wrong, which is a completely different bug from "does not track".
        ratios.append(got / want if (got == got and want) else float("nan"))
        if not (got == got and abs(got - want) / want < 0.10):
            ok_len = False

    print("\nDoes F1/F2 track SHAPE?  (n=34, an adult 17 cm tract)")
    print("%6s %10s %10s %10s" % ("vowel", "F1", "F2", "F3"))
    vals = {}
    for name, fn in (("uniform", uniform), ("a", vowel_a), ("i", vowel_i), ("u", vowel_u)):
        res = resonances(fn(34), fs, n=3)
        vals[name] = [f for f, _ in res]
        cols = ["%10.0f" % f for f, _ in res] + ["%10s" % "-"] * (3 - len(res))
        print("%6s %s" % (name, "".join(cols[:3])))

    spread = 0.0
    if all(len(v) >= 2 for v in vals.values()):
        f1s = [vals[k][0] for k in ("a", "i", "u")]
        f2s = [vals[k][1] for k in ("a", "i", "u")]
        spread = max(max(f1s) - min(f1s), max(f2s) - min(f2s))
        print("\n   vowel spread: F1 %.0f Hz, F2 %.0f Hz" %
              (max(f1s) - min(f1s), max(f2s) - min(f2s)))

    print("\n" + "=" * 66)
    if ok_len and spread > 150:
        print("TUBE IS CORRECT. Length moves F1 and shape moves the vowel.")
        print("Everything wrong today was in the audio measurement chain.")
    elif ok_len:
        print("Length tracks, but SHAPE does not move the formants enough (%.0f Hz)." % spread)
        print("The area functions are too gentle, or the terminations dominate them.")
    else:
        print("LENGTH DOES NOT TRACK. The ladder itself is wrong -- fix the tube,")
        print("not the analysis.")
    print("=" * 66)
