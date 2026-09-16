# -*- coding: utf-8 -*-
"""mouth34.py -- ERAN's mouth, on the machine where ERAN actually lives.

WHAT THIS FIXES. Until 2026-08-24 the living organism on eran1 had no mouth at
all. eran-brain/voice/ held exactly one file, voice.py, an ECHO-BABBLE SPLICER
that concatenates snippets of OTHER PEOPLE'S recordings -- honestly labelled as
"NOT synthesis and NOT his own voice yet". The real vocal tract lived on eran2,
in eran-organs/sense_organ.py, wired to nothing: there were zero references to
it anywhere under /home/eran1/eran-brain/. Meanwhile body/ears.py line 279
already carried utterance_from_samples(), whose docstring names "voice/babble.py's
only way in" -- a file that was never shipped. The socket was wired and empty.
This file is the plug.

WHAT IT IS. The synthesiser that produced ERAN's first closed sensorimotor loop
on 2026-08-23 20:29, lifted VERBATIM off eran2 rather than rewritten, because
every number this project has printed about the tract sits on this exact
arithmetic and a "better" recursion would silently make today incomparable with
yesterday. Specifically preserved from eran-organs/sense_organ.py:

  * glottis()            -- lines 93-109, unchanged
  * the all-pole ladder  -- lines 124-136, including the y[t-1::-1][:m] slice
                            fix. y[t-1 : t-m-1 : -1] silently yields an EMPTY
                            slice when t-m-1 == -1, because -1 means "the end"
                            in a slice and not "one before zero"; at t == m the
                            dot product then threw and the organ went SILENT
                            instead of answering. Slice from the front and
                            reverse: correct for every t.
  * lip radiation, the resample to 16 kHz, and the 0.7 peak normalisation.

THE FACTOR OF TWO, kept explicit because it cost a day: a wave crosses one tube
section in TWO ladder steps, so a section is c/(4*fs) long, not c/(2*fs), and
fs = C_SOUND/(4*SECTION_CM) = 17500 Hz. With the other constant every vowel
measured at exactly 2.00x the closed form -- a constant ratio, which is the
signature of a correct system with a wrong constant, never of a broken one.

WHAT IS NEW HERE, and it is deliberately small:

  1. A STABILITY GUARD. An unstable tube must REFUSE, not emit NaN. say()
     returns None rather than handing the ear a waveform full of infinities.
     The first version of this guard was WRONG and proof/test_mouth.py caught
     it on the day it was written: it read `max|root| < 1.0`, but this ladder is
     LOSSLESS by construction and its poles sit ON the unit circle (measured:
     median max|root| = 1.000000 over 200 tubes in the fence). That guard was
     testing floating-point rounding, not physics, and it silently rejected a
     perfectly good tube for an excess of 8.88e-16. See is_stable(). The lesson
     is the general one: a guard nobody measured is a guess with authority.
  2. A VERIFIED FAST PATH. scipy.signal.lfilter([1], A, x) IS the direct-form
     all-pole recursion, so it is used when scipy is present -- but only after
     proof/test_mouth.py measures it against the verbatim loop and shows the
     two agree to floating-point noise. The slow loop stays in this file as the
     reference implementation and the fallback. Speed that is not proven equal
     to the truth is not speed, it is a different animal.
  3. say_sequence(), so the tube can CHANGE SHAPE mid-utterance. A vowel is one
     posture; "abba" is a movement -- /a/ -> lips shut -> burst -> /a/. Nothing
     in voice/, body/ or proof/ on any of the three machines supported a
     sequence of shapes before this. READ THE WARNING ON say_sequence.

SACRED AUDIO LAW: this file only ever RETURNS or WRITES samples. Nothing here
plays aloud, ever, and nothing here calls a text-to-speech engine. ERAN's voice
comes from his own tube driven by parameters his own search chose, or it is not
his voice.
"""
from __future__ import annotations

import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import tract_analytic as TA          # the VERIFIED tube (md5 d0aef821..., eran2)

SR = 16000                            # the corpus rate, and the ear's rate
SECTION_CM = 0.5                      # one tube section
N_SECTIONS = 34                       # an adult 17 cm tract at 0.5 cm a section
TRACT_FS = TA.C_SOUND / (4.0 * SECTION_CM)      # 17500.0 Hz -- THE FACTOR OF TWO
AREA_MIN, AREA_MAX = 0.15, 4.0        # the search fence, from organs/babble.py
GLOTTAL_REFLECT, LIP_REFLECT = 0.9, -0.85       # tract_analytic's terminations
POLE_TOL = 1e-9       # np.roots error on a degree-35 poly; see is_stable()
DIVERGENCE = 1e12     # the source is O(1); anything past this ran away

try:                                  # optional, and never trusted unverified
    from scipy.signal import lfilter as _lfilter
except Exception:                     # pragma: no cover
    _lfilter = None


# ----------------------------------------------------------------- the source

def glottis(n, f0, sr=TRACT_FS, oq=0.6, jitter=0.012, rng=None):
    """Rosenberg-style glottal flow derivative. VERBATIM from sense_organ.py."""
    rng = rng if rng is not None else np.random.default_rng(0)
    out = np.zeros(n)
    i = 0
    while i < n:
        p = int(sr / max(50.0, f0 * (1.0 + rng.normal(0, jitter))))
        if p < 4:
            break
        op = max(2, int(p * oq))
        a = np.arange(op) / op
        g = np.zeros(p)
        g[:op] = 3 * a ** 2 - 2 * a ** 3
        g = -np.diff(np.concatenate([[0.0], g]))
        k = min(p, n - i)
        out[i:i + k] = g[:k]
        i += p
    return out


# ------------------------------------------------------------------ the ladder

def allpole_reference(src, A):
    """y[n] = x[n] - sum_i A[i] y[n-i]. The verbatim loop. Slow, and the TRUTH."""
    y = np.zeros(src.size)
    order = A.size - 1
    for t in range(src.size):
        acc = src[t]
        m = min(order, t)
        if m:
            acc -= float(np.dot(A[1:m + 1], y[t - 1::-1][:m]))
        y[t] = acc
    return y


def allpole(src, A):
    """The same filter, fast when scipy is here. proof/test_mouth.py checks it."""
    if _lfilter is not None:
        return np.asarray(_lfilter(np.array([1.0]), np.asarray(A, dtype=float),
                                   np.asarray(src, dtype=float)), dtype=float)
    return allpole_reference(src, A)


def coefficients(areas, glottal_reflect=GLOTTAL_REFLECT, lip_reflect=LIP_REFLECT):
    """areas -> A(z). Raises nothing; returns None if the tube is not physical."""
    a = np.asarray(areas, dtype=float)
    if a.ndim != 1 or a.size < 3 or not np.all(np.isfinite(a)) or np.any(a <= 0):
        return None
    A = TA.denominator(TA.areas_to_k(a), glottal_reflect, lip_reflect)
    return A if np.all(np.isfinite(A)) else None


def is_stable(A):
    """No pole meaningfully OUTSIDE the unit circle. Note the word meaningfully.

    THE LADDER IS LOSSLESS BY CONSTRUCTION, so its poles sit essentially ON the
    unit circle. There is no loss term anywhere in tract_analytic.denominator --
    the only damping is the two terminations, and 0.9 / -0.85 are near-total
    reflectors. Measured over 200 random tubes inside the fence [0.15, 4.0] on
    2026-08-24: median max|root| = 1.000000, minimum 0.999930.

    So a guard written as `max|root| < 1.0` does not test stability, it tests
    ROUNDING. np.roots on this degree-35 polynomial carries ~1e-13 of error, and
    exactly 1 tube in those 200 came back at 1.000000000 -- an excess of
    8.88e-16 over the line -- while being minimum-phase in exact arithmetic
    (worst |k| anywhere, terminations included, was 0.924 < 1) and rendering a
    perfectly bounded waveform (peak 6.8e2, first half 6.2e2, last half 6.8e2:
    a resonance, not a divergence). The strict guard would have silently deleted
    physical tubes from the search and biased it in a direction nobody would
    ever have seen from the outside. proof/test_mouth.py caught it; the tolerance
    below is the fix, and say() additionally refuses on BEHAVIOUR -- a waveform
    that actually runs away -- which is the check that cannot be fooled by
    numerics in either direction.
    """
    if A is None:
        return False
    r = np.roots(A)
    return bool(r.size == 0 or float(np.max(np.abs(r))) <= 1.0 + POLE_TOL)


def max_k_interior(areas):
    """The largest interior reflection coefficient -- how EXTREME the shape is.

    A vowel gesture keeps this small (a uniform-ish tube sits near 0.11). A lip
    closure is a geometric extreme: driving the last four areas to 0.02 takes it
    to 0.967. Useful for telling a posture from a stop without listening.
    """
    a = np.asarray(areas, dtype=float)
    return float(np.max(np.abs(TA.areas_to_k(a)))) if a.size > 1 else 0.0


# ------------------------------------------------------------------- the mouth

def _finish(y, seconds, sr):
    """Lip radiation, resample to the ear's rate, normalise. Shared by both says."""
    y = np.concatenate([[y[0]], np.diff(y)])          # lip radiation
    n_out = max(1, int(seconds * sr))
    idx = np.linspace(0, y.size - 1, n_out)
    y = np.interp(idx, np.arange(y.size), y)
    m = float(np.max(np.abs(y)))
    y = (y / m * 0.7) if m > 0 else y
    return y.astype(np.float32)


def say(areas, f0=220.0, seconds=0.6, seed=0,
        glottal_reflect=GLOTTAL_REFLECT, lip_reflect=LIP_REFLECT, sr=SR):
    """One posture, held. float32 @ sr, or None if the tube will not stand up.

    f0 is a FENCED ARGUMENT and is never searched. Six hill climbs on 2026-08-24
    chose 125, 192, 235, 244, 101 and 191 Hz with no convergence whatsoever: the
    ear is level-free and pools 8 slices, so the objective does not constrain
    pitch AT ALL, and a free f0 reproduces the frog. voice/mouth.py's own comment
    records how that went -- the search chose 70 Hz, Iddo said it sounded like a
    frog, and then he corrected the ANATOMY rather than the number: he said it is
    a baby. A baby is 200-500 Hz. The default here is the bottom of that range.
    """
    A = coefficients(areas, glottal_reflect, lip_reflect)
    if A is None or not is_stable(A):
        return None
    n = int(TRACT_FS * seconds)
    if n < 8:
        return None
    src = glottis(n, f0, sr=TRACT_FS, rng=np.random.default_rng(seed))
    y = allpole(src, A)
    if not np.all(np.isfinite(y)) or float(np.max(np.abs(y))) > DIVERGENCE:
        return None
    return _finish(y, seconds, sr)


def say_sequence(keyframes, f0=220.0, seed=0, glide_frac=0.35,
                 glottal_reflect=GLOTTAL_REFLECT, lip_reflect=LIP_REFLECT, sr=SR):
    """A MOVEMENT: [(areas, seconds), ...] with the filter recomputed as it moves.

    The tract interpolates linearly from one posture toward the next over the
    first `glide_frac` of each segment and then holds -- crude coarticulation,
    but it is a real moving tube rather than a concatenation of separate sounds,
    and the ladder state y carries across the boundary, so a closure and its
    release are one continuous filter and not a splice.

    READ THIS BEFORE YOU BELIEVE ANY NUMBER THIS FUNCTION PRODUCES. The frozen
    192-d cochlea this project runs on CANNOT HEAR A STOP CONSONANT. body/ears.py
    line 197 divides every frame's spectrum by its own sum -- `spectrum =
    spectrum / spectrum.sum(axis=1, keepdims=True)`, one line before the bands
    are formed -- so all energy information is destroyed by construction, and a
    stop consonant IS a silence and a burst. So this renderer can MAKE a gesture
    the ear cannot SCORE: it is here so the mouth is ready, not because hill
    climbing through this ear will find "abba". Fixing that is an ear change, it
    is Iddo's word alone because it is anatomy, and it must not be attempted
    while the nightly tournament can still write into state/.
    """
    frames = [(np.asarray(a, dtype=float), float(s)) for a, s in keyframes]
    if not frames:
        return None
    total = sum(s for _, s in frames)
    if total <= 0:
        return None

    n_total = int(TRACT_FS * total)
    if n_total < 8:
        return None
    src = glottis(n_total, f0, sr=TRACT_FS, rng=np.random.default_rng(seed))

    # Per-sample area trajectory: glide toward each posture, then hold.
    traj = np.zeros((n_total, frames[0][0].size))
    prev = frames[0][0]
    t0 = 0
    for areas, secs in frames:
        n = min(max(1, int(TRACT_FS * secs)), n_total - t0)
        if n <= 0:
            break
        g = max(1, int(n * glide_frac))
        w = np.clip(np.arange(n) / float(g), 0.0, 1.0)[:, None]
        traj[t0:t0 + n] = prev[None, :] * (1 - w) + areas[None, :] * w
        prev = areas
        t0 += n
    if t0 < n_total:
        traj[t0:] = prev

    # Recompute the ladder as the shape moves. Coefficients change slowly, so
    # they are refreshed on a 1 ms block and held -- 1 ms of tube is far shorter
    # than any articulator can move, and it keeps this affordable.
    block = max(1, int(TRACT_FS * 0.001))
    y = np.zeros(n_total)
    order = None
    for b0 in range(0, n_total, block):
        b1 = min(n_total, b0 + block)
        A = coefficients(traj[(b0 + b1) // 2], glottal_reflect, lip_reflect)
        if A is None:
            return None
        if order is None:
            order = A.size - 1
        for t in range(b0, b1):
            acc = src[t]
            m = min(order, t)
            if m:
                acc -= float(np.dot(A[1:m + 1], y[t - 1::-1][:m]))
            y[t] = acc
    if not np.all(np.isfinite(y)) or float(np.max(np.abs(y))) > DIVERGENCE:
        return None
    return _finish(y, total, sr)


# ---------------------------------------------------------------- the postures

def uniform(n=N_SECTIONS):
    return np.ones(n)


def closed_lips(areas, n_closed=4, area=0.02):
    """The same tract with the last n_closed sections shut. A stop, geometrically."""
    a = np.array(areas, dtype=float)
    a[-n_closed:] = area
    return a
