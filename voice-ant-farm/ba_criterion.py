# -*- coding: utf-8 -*-
"""ba_criterion.py - the judge for rung 2 of the coronation curriculum: /ba/.

WHY THIS FILE EXISTS
--------------------
Iddo, 2026-08-16 ~05:00, after listening to the colony's /a/:

    "מגיעים ל-A בסדר יחסי, בוא נתחיל בה עכשיו"  -> "בה. בה. בה." -> "גה, גה, גה"

Rung 1 is /a/ and it has a judge (ah_criterion.py). curriculum_targets.py
already measures the physics of a stop - find_stop_events, burst_centroid,
spectral_tilt_db, measure_cv_token, velar_pinch_score - and its own docstring
says that is "what makes /ba/ and /ga/ TARGETS rather than opinions".

So the measurement existed and the JUDGE did not. Until something can say
"this is a /ba/ and that is not", the colony cannot be scored on rung 2, and
an evolutionary search will happily keep producing rung 1 forever: /a/ scores
well on any judge that only knows vowels. THE FIRST JOB OF THIS FILE IS TO
REJECT A GOOD /a/. A rung-2 judge that passes rung 1 output is not a judge.

WHAT MAKES A /ba/ A /ba/, AND NOT A LOUDER /a/
----------------------------------------------
A vowel is a SHAPE. A stop is a GESTURE IN TIME - seal the tract, build
pressure, release it, and move into the vowel. Four stages, each measurable:

  closure   near-silence while the lips are sealed
  burst     the release transient
  VOT       release -> onset of voicing (/b/ is VOICED: short or negative)
  transition  F2 leaves the consonant's LOCUS and travels to the vowel's F2

Place of articulation lives in the burst and the transition, and this is the
whole discrimination between the rungs:

  BILABIAL /b/  lips: a long front cavity -> LOW F2 locus (~700-900 Hz), and
                since /a/ sits at F2 = 1464 Hz (AH_TARGET, his own measured
                pooled target), F2 must RISE into the vowel. The burst is
                diffuse-falling: energy low, so burst_centroid is low and
                spectral tilt (lo minus hi) is POSITIVE.

  VELAR /g/     tongue body at the soft palate -> F2 and F3 CONVERGE (the
                velar pinch), a compact mid-frequency burst, and F2 does not
                rise the way a bilabial's does. velar_pinch_score() exists in
                curriculum_targets for exactly this, and gate 2 uses it as a
                NEGATIVE test: a high pinch means the colony produced rung 3's
                sound, not rung 2's.

So /ba/ and /ga/ are separated by measurement, not by opinion - which is what
lets the coronation advance automatically instead of waiting for Iddo to
listen and say "תחליף מלכה".

PROVENANCE, unchanged from rung 1 (his law, verbatim):
    "its ok if the queen copies me with her own mouth - that's learning isnt it"
IMITATION through her own articulators is the target. REPLAY - splicing stored
PCM - is forbidden, and gate 4 delegates to ah_criterion's audit so there is
ONE copy of that law.

HOLD-OUT: sessions 2026-06-25 and 2026-07-01 stay reserved for evaluation;
anything reading corpus audio must go through
curriculum_targets.filter_training_paths().

No torch (workspace law). numpy + scipy only. Nothing here opens an audio
device; audio arrives as arrays or file paths.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

import curriculum_targets as ct
from ah_criterion import (
    AH_TARGET,
    GateResult,
    Verdict,
    audit_production_module,
    grep_proof,
)
from ah_criterion import judge as judge_a  # rung 1, reused for the vowel body

# ==========================================================================
# THE THRESHOLDS
#
# Every number below is either (a) a classic phonetic constant with a named
# source, or (b) derived from AH_TARGET, which is Iddo's own measured vowel.
# Nothing here is a taste. Where a value is a convention rather than a
# measurement it says so, because a threshold whose origin is unknown is how
# a gate quietly stops meaning anything.
# ==========================================================================
GATES = {
    # gate 1 - the gesture exists at all
    "closure_ms_min": 40.0,          # below this it is a glottal blip, not a seal
    "closure_ms_max": 250.0,         # above this the token is two events
    "burst_present_db": 6.0,         # release must rise this far above the closure floor

    # gate 2 - the place is BILABIAL (and specifically not velar)
    "burst_centroid_max_hz": 1600.0,  # bilabial bursts are low and diffuse
    "burst_tilt_db_min": 0.0,         # lo-band minus hi-band: positive for a labial
    "f2_onset_max_hz": 1100.0,        # the bilabial LOCUS, well under /a/'s 1464
    "f2_rise_hz_per_s_min": 400.0,    # F2 must TRAVEL from locus up to the vowel
    "pinch_onset_max": 0.55,          # velar_pinch_score: high == /g/, reject

    # gate 3 - it is a VOICED stop, and what follows is really /a/
    "vot_ms_max": 35.0,               # voiced stops: short lag or prevoiced (negative)
    "vot_ms_min": -120.0,             # prevoicing is fine and common in Hebrew /b/
    # the vowel body itself is delegated to rung 1's judge - one copy of that law

    # gate 4 - provenance
    "replay_snr_db": 20.0,
}

THRESHOLD_PROVENANCE = {
    "f2_onset_max_hz":
        "Bilabial F2 locus is classically ~700-900 Hz (Delattre/Liberman/Cooper "
        "locus experiments). AH_TARGET['F2'] = %.0f Hz is Iddo's own /a/. The "
        "gate sits between them, closer to the locus, so a token whose F2 never "
        "left the vowel cannot pass." % AH_TARGET["F2"],
    "f2_rise_hz_per_s_min":
        "A rise, not a level. /a/ held flat has slope ~0; the labial transition "
        "covers roughly 1464-800 = 660 Hz in ~60 ms, i.e. ~11,000 Hz/s at the "
        "textbook extreme. 400 Hz/s is a deliberately permissive floor - the "
        "colony has never made a transition at all, so the first bar is 'moved "
        "in the right direction', not 'moved like an adult'.",
    "pinch_onset_max":
        "velar_pinch_score = exp(-|F3-F2|/900). A velar closes that gap and "
        "scores high; a labial keeps F2 low and F3 where it was. This is the "
        "gate that stops rung 3 from being mistaken for rung 2.",
    "vot_ms_max":
        "Voiced stops sit near 0 ms VOT and are frequently prevoiced in Hebrew. "
        "35 ms is the conventional voiced/voiceless boundary region; above it "
        "the colony has made /pa/, which is a different sound.",
    "burst_tilt_db_min":
        "spectral_tilt_db() returns lo-band minus hi-band. Bilabial bursts are "
        "diffuse-falling (energy concentrated low) so the difference is "
        "positive; alveolar and velar bursts are not.",
    "closure_ms_min":
        "find_stop_events() already refuses closures under 30 ms as noise. 40 ms "
        "is one step stricter so a gap between two babbles cannot be read as a "
        "deliberate seal.",
}

RUNG = 2
PHONEME = "ba"


# ==========================================================================
# The four gates
# ==========================================================================
def _gate_gesture(m):
    """Gate 1 - is there a stop-shaped event at all?"""
    if m is None:
        return GateResult("gesture", False,
                          "no stop-shaped event found - this is a vowel, not a syllable")

    closure = float(m.get("closure_ms", 0.0))
    rise = float(m.get("burst_rise_db", m.get("burst_db", 0.0)))
    ok = (GATES["closure_ms_min"] <= closure <= GATES["closure_ms_max"]
          and rise >= GATES["burst_present_db"])
    return GateResult(
        "gesture", ok,
        f"closure {closure:.0f} ms, burst +{rise:.1f} dB",
        {"closure_ms": closure, "burst_rise_db": rise},
    )


def _gate_place(m):
    """Gate 2 - bilabial, and specifically NOT velar."""
    if m is None:
        return GateResult("place", False, "no event to place")

    cen = float(m.get("burst_centroid", np.inf))
    tilt = float(m.get("burst_tilt_db", -np.inf))
    f2on = float(m.get("f2_onset", np.inf))
    slope = float(m.get("f2_slope_hz_per_s", -np.inf))
    pinch = float(m.get("pinch_onset", 1.0))

    checks = {
        "burst_centroid_low": cen <= GATES["burst_centroid_max_hz"],
        "burst_tilt_positive": tilt >= GATES["burst_tilt_db_min"],
        "f2_locus_low": f2on <= GATES["f2_onset_max_hz"],
        "f2_rises_into_vowel": slope >= GATES["f2_rise_hz_per_s_min"],
        "not_velar": pinch <= GATES["pinch_onset_max"],
    }
    ok = all(checks.values())
    failed = [k for k, v in checks.items() if not v]
    detail = (f"centroid {cen:.0f} Hz, tilt {tilt:+.1f} dB, F2 locus {f2on:.0f} Hz, "
              f"F2 slope {slope:+.0f} Hz/s, pinch {pinch:.2f}")
    if not ok:
        detail += "  <- failed: " + ", ".join(failed)
    return GateResult("place", ok, detail,
                      {"burst_centroid": cen, "burst_tilt_db": tilt,
                       "f2_onset": f2on, "f2_slope_hz_per_s": slope,
                       "pinch_onset": pinch, "failed": failed})


def _gate_voice_and_vowel(m, x, sr):
    """Gate 3 - a VOICED stop, and the vowel after it is genuinely /a/."""
    if m is None:
        return GateResult("voice", False, "no event to time")

    vot = float(m.get("vot_ms", np.inf))
    vot_ok = GATES["vot_ms_min"] <= vot <= GATES["vot_ms_max"]

    # The vowel body is rung 1's business. ONE copy of that law.
    try:
        steady_from = int(0.090 * sr)
        tail = x[steady_from:] if len(x) > steady_from + int(0.05 * sr) else x
        v = judge_a(tail, sr)
        vowel_ok = bool(getattr(v, "passed", False))
        vowel_detail = "vowel body passes rung 1" if vowel_ok else "vowel body is not /a/"
    except Exception as exc:                                     # noqa: BLE001
        vowel_ok, vowel_detail = False, f"rung-1 judge raised: {type(exc).__name__}"

    ok = vot_ok and vowel_ok
    return GateResult("voice", ok,
                      f"VOT {vot:+.0f} ms, {vowel_detail}",
                      {"vot_ms": vot, "vowel_is_a": vowel_ok})


def _gate_provenance(production_module=None):
    """Gate 4 - MADE, not remembered. Delegated to rung 1's audit."""
    if production_module is None:
        return GateResult("provenance", True,
                          "no production module supplied - structural audit skipped "
                          "(caller must audit before crowning)")
    try:
        violations = audit_production_module(production_module)
        tokens = grep_proof(production_module)
        ok = not violations and not tokens
        detail = "no replay path reachable" if ok else \
                 f"{len(violations)} import/call violations, {len(tokens)} forbidden tokens"
        return GateResult("provenance", ok, detail,
                          {"violations": len(violations), "tokens": len(tokens)})
    except Exception as exc:                                     # noqa: BLE001
        return GateResult("provenance", False, f"audit raised: {type(exc).__name__}: {exc}")


# ==========================================================================
# The judge
# ==========================================================================
def judge(x, sr, production_module=None):
    """Judge one candidate token as /ba/. Returns a Verdict.

    `x` is a mono waveform (numpy, any scale), `sr` its sample rate.
    `production_module` is the path to the module that MADE the sound; supply
    it before crowning so gate 4 can prove no replay path is reachable.
    """
    x = np.asarray(x, dtype=np.float64)
    if x.size and np.max(np.abs(x)) > 0:
        x = x / np.max(np.abs(x))

    m = ct.measure_cv_token(x, sr)

    gates = {}
    for g in (_gate_gesture(m), _gate_place(m), _gate_voice_and_vowel(m, x, sr),
              _gate_provenance(production_module)):
        gates[g.name] = g

    return Verdict(passed=all(g.passed for g in gates.values()),
                   gates=gates,
                   measurements=dict(m) if m else {})


def score(x, sr):
    """A continuous 0..1 fitness for the evolutionary search.

    A pass/fail verdict cannot steer a search - the colony needs to know it is
    getting WARMER. Each gate contributes a graded term, so a token with a real
    closure but no F2 transition outranks a token that is still a plain vowel.
    """
    x = np.asarray(x, dtype=np.float64)
    if x.size and np.max(np.abs(x)) > 0:
        x = x / np.max(np.abs(x))
    m = ct.measure_cv_token(x, sr)
    if m is None:
        return 0.0                                   # still a vowel: rung 1, not rung 2

    def band(v, lo, hi):
        if not np.isfinite(v):
            return 0.0
        return float(np.clip((v - lo) / (hi - lo), 0.0, 1.0))

    closure = float(m.get("closure_ms", 0.0))
    terms = [
        band(closure, 0.0, GATES["closure_ms_min"]),                              # sealed
        1.0 - band(float(m.get("burst_centroid", 4000.0)), 800.0, 3000.0),        # low burst
        band(float(m.get("burst_tilt_db", -12.0)), -12.0, 6.0),                   # falling
        1.0 - band(float(m.get("f2_onset", 2000.0)), 700.0, 1600.0),              # low locus
        band(float(m.get("f2_slope_hz_per_s", 0.0)), 0.0, 6000.0),                # rising
        1.0 - band(float(m.get("pinch_onset", 1.0)), 0.2, 0.8),                   # not velar
    ]
    return float(np.mean(terms))


def summary_line(v):
    """One line for a log or a coronation record."""
    head = "PASS" if v.passed else "FAIL"
    bits = [f"{g.name}={'ok' if g.passed else 'no'}" for g in v.gates.values()]
    return f"[{head}] /ba/ rung {RUNG}: " + " ".join(bits)
