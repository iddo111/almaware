# -*- coding: utf-8 -*-
"""arms_v3.py -- Stage A of the ERAN 2.0 campaign: WHAT is being searched.

The search space is mouth2's GESTURE space (13 dims per keyframe:
8 log2-area spline knots + c_pos + c_area + velum + tenseness + voicing),
not raw 34-tube areas -- nasals, seals and source quality are now
REACHABLE dimensions, which is the entire point of the new mouth.

STAGE A ARMS (plan Phase 3, ~4 days):
  ah-1kf / ih-1kf   16d = 13 keyframe + 3 f0 knots. One held posture,
                    fixed 0.5 s. Q: can the child tract find Iddo's
                    vowels through the NEW ear?
  ba-cv             31d = 2x13 keyframes + 2 durations + 3 f0 knots.
                    Keyframe 1 is fenced to a LABIAL CLOSURE box
                    (c_pos lips, c_area near seal, velum shut);
                    keyframe 2 is a free vowel. The structured /ba/.
  ma-nasal          32d = ba-cv + 1 glide dim. Keyframe 1's velum fence
                    is OPEN [0.15, 0.8] -- THE FIRST NASAL ARM EVER
                    POSSIBLE (the old mouth had no nose). The extra
                    glide dim lets the search shape the murmur release.
  *-free            45d = 3x13 free keyframes + 3 durations + 3 f0.
                    No imposed structure -- can free articulation beat
                    the guided gesture? (ah-free, ba-free, ma-free)
  control-*         SAME boxes, uniform random search, same bookkeeping.
                    If CMA does not clearly beat its twin, nothing was
                    learned and the report must say so in those words.

F0 FENCE -- LOWERED 2026-08-26 to [90, 350] Hz:
  The plan pinned f0 knots to the genome child band [200, 500]. That
  fence was INVERTED against the targets: the Ear-v3 calibration
  measured Iddo's own real /abba/ f0 deciles at 62/72/79/94/139/177/203
  Hz -- corpus (t06) median f0 is 60-90 Hz -- so the search was
  physically forbidden from sounding like its targets. On 2026-08-25 he
  called a flat 220 Hz render "too high" (לא טוב), and on 2026-08-26 he
  rejected a 340 Hz Stage-A candidate outright (רע ברמות). Fence
  lowered to [90, 350]: the ear pitch block covers 60-420 Hz, so
  90-350 is fully observable. F0_LO / F0_HI below are module constants.
  NOTE: mouth2.F0_MIN/F0_MAX clip AGAIN inside say_gesture and were
  lowered to 90/350 in the same change (ORGANS.lock re-pinned).

Total utterance durations are bounded >= 0.2 s so the 8-slice ear
always has a real speech span to slice (the v1 rule, kept).
"""
from __future__ import annotations

import os
import sys

import numpy as np

MOUTH_DIR = os.path.expanduser("~/mouth-v2")
if MOUTH_DIR not in sys.path:
    sys.path.insert(0, MOUTH_DIR)

import mouth2                                    # noqa: E402

# ------------------------------------------------------------------ fences
F0_LO, F0_HI = 90.0, 350.0         # see the F0 FENCE note in the docstring
K_LO = float(np.log2(mouth2.AREA_MIN))           # log2-area knots, -2.737
K_HI = float(np.log2(mouth2.AREA_MAX))           # +2.0
TEN_LO, TEN_HI = mouth2.TEN_MIN, mouth2.TEN_MAX  # 0.25, 0.95
DUR_VOWEL = 0.5                    # fixed hold for the 1-keyframe arms

# per-keyframe bounds [13]: k1..k8, c_pos, c_area, velum, tenseness, voicing
KF_OPEN_LO = [K_LO] * 8 + [0.30, 0.20, 0.0, TEN_LO, 0.0]
KF_OPEN_HI = [K_HI] * 8 + [1.00, 2.00, 0.8, TEN_HI, 1.0]
# labial-closure keyframe: constriction at the lips, at/near seal
KF_SEAL_LO = [K_LO] * 8 + [0.85, 0.00, 0.0, TEN_LO, 0.0]
KF_SEAL_HI = [K_HI] * 8 + [1.00, 0.08, 0.15, TEN_HI, 1.0]
# nasal-murmur keyframe: same lip seal, velum OPEN (the nose, at last)
KF_NASAL_LO = [K_LO] * 8 + [0.85, 0.00, 0.15, TEN_LO, 0.0]
KF_NASAL_HI = [K_HI] * 8 + [1.00, 0.08, 0.80, TEN_HI, 1.0]
# ORAL keyframes -- velum SHUT (2026-08-27, Iddo's BAH order).
# MEASURED, not guessed: all 24 judged ba candidates were nearest to the `ma`
# target under our own Ear-v3, while only 31/100 REAL human ba clips are (the
# ear gets human ba right 64% of the time, so the ear is not the fault). The
# winners' own parameters show why -- ba-cv-6 kf2 velum 0.72, ba-cv-7 0.65,
# ba-free-3 0.51: `ba-cv` fenced the velum shut for the LIP CLOSURE only and
# then let KF_OPEN nasalize the whole vowel (velum <= 0.8), and `ba-free` never
# fenced it at all. ERAN was not failing to say BAH -- he was being allowed to
# say it through his nose, and a nasalized /ba/ IS /ma/.
KF_ORAL_LO = [K_LO] * 8 + [0.30, 0.20, 0.0, TEN_LO, 0.0]
KF_ORAL_HI = [K_HI] * 8 + [1.00, 2.00, 0.05, TEN_HI, 1.0]
KF_FREE_ORAL_LO = [K_LO] * 8 + [0.30, 0.00, 0.0, TEN_LO, 0.0]
KF_FREE_ORAL_HI = [K_HI] * 8 + [1.00, 2.00, 0.05, TEN_HI, 1.0]
# free keyframe: the whole documented gesture range
KF_FREE_LO = [K_LO] * 8 + [0.30, 0.00, 0.0, TEN_LO, 0.0]
KF_FREE_HI = [K_HI] * 8 + [1.00, 2.00, 0.8, TEN_HI, 1.0]

TEN_KNOTS = [0.6, 0.6, 0.6]        # utterance contour fixed; per-keyframe
                                   # tenseness (dim 11) is the searched dial


class Arm:
    def __init__(self, name, unit, lo, hi, to_gesture, guided=True):
        self.name = name
        self.unit = unit
        self.lo = np.asarray(lo, dtype=float)
        self.hi = np.asarray(hi, dtype=float)
        self.dim = self.lo.size
        self.to_gesture = to_gesture
        self.guided = guided

    def clip(self, x):
        return np.clip(x, self.lo, self.hi)

    def x0(self, seed):
        """Even seeds start from the geometry vowel preset (tests the
        Story-Bunton prior); odd seeds start uniform random (so the
        prior is tested, not assumed) -- the v1 convention, kept."""
        rng = np.random.default_rng(seed)
        x = rng.uniform(self.lo, self.hi)
        if seed % 2 == 0 and self._preset is not None:
            p = np.clip(self._preset + rng.normal(0, 0.15, self.dim)
                        * (self.hi - self.lo) * 0.5, self.lo, self.hi)
            x = p
        return x

    _preset = None


# ------------------------------------------------------- vector -> gesture

def _g_vowel(x):
    return {"keyframes": [x[:13]],
            "durations": [DUR_VOWEL],
            "f0_knots": list(x[13:16]),
            "tenseness_knots": TEN_KNOTS}


def _g_cv(x):
    """[kf_close 13][kf_vowel 13][t_close][t_vowel][f0 x3] -> 31d"""
    return {"keyframes": [x[:13], x[13:26]],
            "durations": [float(x[26]), float(x[27])],
            "f0_knots": list(x[28:31]),
            "tenseness_knots": TEN_KNOTS}


def _g_cv_glide(x):
    """ba-cv + glide dim at the end -> 32d (ma-nasal)"""
    g = _g_cv(x[:31])
    g["glide"] = float(x[31])
    return g


def _g_free(x):
    """[3 x kf 13][3 durations][f0 x3] -> 45d"""
    return {"keyframes": [x[:13], x[13:26], x[26:39]],
            "durations": [float(x[39]), float(x[40]), float(x[41])],
            "f0_knots": list(x[42:45]),
            "tenseness_knots": TEN_KNOTS}


# ------------------------------------------------------------- the presets

def _kf(knots8, c_pos, c_area, velum, ten, voi):
    return list(knots8) + [c_pos, c_area, velum, ten, voi]


def _preset_vowel(vowel):
    k = mouth2.vowel_knots(vowel)
    return np.array(_kf(k, 0.65, 1.5, 0.05, 0.6, 1.0) + [300.0, 280.0, 245.0])


def _preset_cv(vowel, nasal=False):
    k = mouth2.vowel_knots(vowel)
    velum1 = 0.5 if nasal else 0.05
    kf1 = _kf(k, 0.95, 0.01, velum1, 0.6, 0.3)
    kf2 = _kf(k, 0.65, 1.5, 0.05, 0.6, 1.0)
    x = kf1 + kf2 + [0.12, 0.35] + [300.0, 280.0, 245.0]
    if nasal:
        x = x + [0.35]
    return np.array(x)


def _preset_free(vowel):
    k = mouth2.vowel_knots(vowel)
    kf_v = _kf(k, 0.65, 1.5, 0.05, 0.6, 1.0)
    kf_c = _kf(k, 0.95, 0.01, 0.05, 0.6, 0.3)
    return np.array(kf_v + kf_c + kf_v + [0.20, 0.10, 0.25]
                    + [300.0, 280.0, 245.0])


# ------------------------------------------------------------------ get()

def _mk(name, unit, lo, hi, fn, preset):
    a = Arm(name, unit, lo, hi, fn, guided=not name.startswith("control"))
    # A preset shorter than the arm is a dimension that was added to lo/hi and to
    # the gesture builder but never to the seed vector. That happened on
    # 2026-08-27 when `ba` gained its glide dim: 13 workers died in x0() on
    # "operands could not be broadcast together with shapes (31,) (32,)".
    # Padding here, rather than at each call site, means the next dimension
    # anyone adds cannot reproduce it. New dims start at the middle of their own
    # fence -- CMA then has room in both directions instead of starting on an edge.
    if preset is not None and len(preset) < len(lo):
        k = len(preset)
        preset = list(preset) + [(lo[i] + hi[i]) / 2.0 for i in range(k, len(lo))]
    a._preset = preset
    return a


# Release speed for a STOP (2026-08-27, Iddo: "תשנה את הפה").
# THE ASYMMETRY THIS FIXES: `ma-nasal` was given a searched glide dim so it could
# "shape the murmur release" (this file's own comment, line 20). `ba-cv` never got
# one -- so the single unit whose entire identity IS a fast release was the only
# one forbidden to control release speed. It sat at the fixed default 0.35.
#
# What that cost: mouth2.say_sequence glides LINEARLY from the previous posture
# over the first `glide` of the segment. With a ba-cv vowel segment of 0.17-0.50 s,
# a 0.35 glide spreads the lip release over 60-175 ms. A human /b/ burst is 5-15 ms.
# The mouth could not release fast; it could only ramp. That is why 25 independent
# arms and ~7.5M evaluations all stalled in the 4.6-6.4 band and none ever reached
# the real-clip mean of 3.911 -- the gap was not in the search, it was a control the
# search was never handed.
#
# 0.02 of a 0.50 s segment is 10 ms: human plosive speed. The old 0.35 stays inside
# the range, so this only ADDS reachable behaviour, it removes none.
GLIDE_BA_LO = 0.02
GLIDE_BA_HI = 0.35


# Burst strength, `ba` only (2026-08-28). Iddo heard it before any metric did:
# "חסר המון פיצוץ בהתחלה", and "יש מן אנפוף". Measured on his best clip against the
# three human targets: burst sharpness 8.4 dB vs 23.5 and 26.3 -- three times too
# weak. Those two remarks are probably one defect: what separates /b/ from /m/ to an
# ear IS the sharpness of the release, so a soft release sounds nasal even with the
# nose fully shut.
#
# Third time today that the fault was a hardcoded constant where a dial belongs
# (velum fence, then glide, now this). BURST_GAIN sat at 2.2 and the vent time
# constant at 3 ms -- while tract_core's own comment says "real bursts run 5-25 ms".
# fastcore already passed both to C per call; they were simply always filled from
# the module constant. Now `ba` may search them. `ma`, `ah`, `ih` pass nothing and
# are bit-identical.
GLIDE_BA_LO, GLIDE_BA_HI = 0.02, 0.35
# 2026-08-28 07:13, Iddo: "אתה יכול להיפטר מהגבולות אם זה לא עוזר לנו.
# גבולות באו לעזור לנו, לא ההפך." Applied per fence, not wholesale:
#
# GAIN ceiling REMOVED in practice (12 -> 60). Within five hours every arm was
# pinned at 12.00 of 12 -- the fence was binding, and it had no anchor to begin
# with: `bamp = GAIN * pressure * g_open`, pressure is already capped at 1.0, and
# 2.2 was a number copied from another project. Nor is a ceiling needed: the clip
# is normalised to peak 0.7, so an over-loud burst crushes the vowel behind it and
# the ear penalises that by itself. The brake already lives inside the objective.
#
# TAU widened 20 -> 30 ms, past the 5-25 ms that tract_core documents for real
# stop bursts, so the physical range sits inside the fence instead of on its edge.
#
# The VELUM fence STAYS. It is not an invention -- /b/ is an oral stop and above
# velum 0.05 the synth accumulates no pressure at all, so without it 43% of the
# search cannot burst by construction. It helps, so by his own rule it stays.
BURST_GAIN_LO, BURST_GAIN_HI = 1.0, 60.0
BURST_TAU_LO, BURST_TAU_HI = 0.002, 0.030


def _burst_from(x):
    """Last two dims are always (gain, tau_s); glide is the one before them."""
    return {"gain": float(x[-2]), "tau_s": float(x[-1])}


def _g_cv_glide_ba(x):
    """ba-cv + glide + burst gain + burst tau -> 34d"""
    g = _g_cv(x)
    g["glide"] = float(x[-3])
    g["burst"] = _burst_from(x)
    return g


def _g_free_glide(x):
    """ba-free + glide + burst gain + burst tau -> 48d"""
    g = _g_free(x)
    g["glide"] = float(x[-3])
    g["burst"] = _burst_from(x)
    return g


def get(name):
    base = name.replace("control-", "")
    if base in ("ah-1kf", "ih-1kf"):
        vowel = "a" if base.startswith("ah") else "i"
        lo = KF_OPEN_LO + [F0_LO] * 3
        hi = KF_OPEN_HI + [F0_HI] * 3
        return _mk(name, base[:2], lo, hi, _g_vowel, _preset_vowel(vowel))
    if base == "ba-cv":
        seal_hi = list(KF_SEAL_HI); seal_hi[10] = 0.04      # under the 0.05 threshold
        # 2026-08-28 08:00, Iddo after listening: "להגדיל גם את הפרץ וגם את ה-AH
        # אחריו ושיהיה יותר ארוך". MEASURED against the three human clips on the
        # listen page: they run 0.32 / 1.32 / 1.38 s and ERAN was 0.55 s. The vowel
        # segment was capped at 0.50 s, so max total was 0.68 s -- HALF the human
        # length, and the cap was mine. Vowel 0.17-1.10 s puts the human range
        # inside the fence instead of beyond it.
        #
        # NOT touched: vowel tenseness [0.25,0.95] and voicing [0,1] are already
        # wide open. His vowel measures 5x quieter than a human's, but that is the
        # objective not rewarding loudness -- not a fence. No dial is invented where
        # the search is already free.
        lo = KF_SEAL_LO + KF_ORAL_LO + [0.03, 0.17] + [F0_LO] * 3 + [GLIDE_BA_LO, BURST_GAIN_LO, BURST_TAU_LO]
        hi = seal_hi + KF_ORAL_HI + [0.18, 1.10] + [F0_HI] * 3 + [GLIDE_BA_HI, BURST_GAIN_HI, BURST_TAU_HI]
        return _mk(name, "ba", lo, hi, _g_cv_glide_ba, _preset_cv("a"))
    if base == "ma-nasal":
        lo = KF_NASAL_LO + KF_OPEN_LO + [0.08, 0.17] + [F0_LO] * 3 + [0.15]
        hi = KF_NASAL_HI + KF_OPEN_HI + [0.30, 0.50] + [F0_HI] * 3 + [0.60]
        return _mk(name, "ma", lo, hi, _g_cv_glide, _preset_cv("a", nasal=True))
    if base in ("ah-free", "ba-free", "ma-free"):
        unit = base.split("-")[0]
        vowel = "a"                # all three units carry /a/; ih-free none
        # /b/ is an ORAL stop: fence its nose in every keyframe. /m/ and /ah/
        # keep the documented range -- ma must nasalize, and ah measures 0.939
        # AUC against Iddo's ear exactly as it is. Do not "fix" what works.
        oral = base.startswith("ba")
        klo = (KF_FREE_ORAL_LO if oral else KF_FREE_LO) * 3
        khi = (KF_FREE_ORAL_HI if oral else KF_FREE_HI) * 3
        lo = klo + [0.07, 0.07, 0.07] + [F0_LO] * 3
        hi = khi + [0.35, 0.35, 0.35] + [F0_HI] * 3
        if oral:                      # only /b/ gets the fast-release dim
            lo = lo + [GLIDE_BA_LO, BURST_GAIN_LO, BURST_TAU_LO]
            hi = hi + [GLIDE_BA_HI, BURST_GAIN_HI, BURST_TAU_HI]
            return _mk(name, unit, lo, hi, _g_free_glide, _preset_free(vowel))
        return _mk(name, unit, lo, hi, _g_free, _preset_free(vowel))
    raise SystemExit("unknown arm %r" % name)


GUIDED = ("ah-1kf", "ih-1kf", "ba-cv", "ma-nasal",
          "ah-free", "ba-free", "ma-free")
CONTROLS = ("control-ah-1kf", "control-ih-1kf", "control-ba-cv",
            "control-ma-nasal", "control-ba-free")
ALL = GUIDED + CONTROLS


if __name__ == "__main__":
    for n in ALL:
        a = get(n)
        g = a.to_gesture(a.clip(a.x0(0)))
        tot = sum(g["durations"])
        print("%-18s unit=%-4s dim=%2d guided=%d kfs=%d total=%.2fs"
              % (a.name, a.unit, a.dim, a.guided, len(g["keyframes"]), tot))
        assert tot >= 0.2, "total duration under the 0.2 s ear floor"
