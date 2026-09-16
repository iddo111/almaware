# -*- coding: utf-8 -*-
"""growth.py — the body matures on its own. Nobody types an anatomy.

Iddo, 2026-08-22: *"תוסיף משהו בקוד של ערן ובשכבה הבסיסית שלו, שיש כיוון
אוטומטי, שכל מיני פרמטרים משתנים עם הגיל — הגדילה."*

WHY THIS FILE EXISTS. On 2026-08-22 I set ERAN's vocal tract to 16 sections,
then to 11, then to 7, each time by typing a number after Iddo listened. That
is a person deciding an anatomy, and it is wrong twice over: it makes me the
body's author, and it freezes the child at whatever age I last guessed. A real
body is not decided. **It grows** — slowly, monotonically, without asking.

So every age-dependent constant of the body now lives here as a FUNCTION OF
AGE, and no caller may hard-code one. Growth is:

  * **automatic** — derived from how much the organism has actually lived,
  * **monotone** — a body never un-grows,
  * **gradual** — Iddo's law of 2026-08-21, "בתינוק אנושי אולי יש שינויים
    באוזן ובפה אבל זה הדרגתי": change by maturation, never by surgery,
  * **deterministic** — the same age always yields the same body, so an
    experiment is reproducible and a measurement is comparable.

WHAT GROWS, and the real physiology behind each number:

  vocal tract length   ~7 cm at birth -> ~17 cm in an adult male. This is why
                       a baby's formants sit so high: every resonance scales
                       as 1/length. Iddo heard exactly this before he could
                       name it — a high pitch inside an adult tube sounds
                       wrong, because the two must move together.
  fundamental (f0)     ~400-500 Hz crying newborn, ~250-300 Hz at four,
                       settling toward adult range much later. The RANGE
                       narrows and falls; the child keeps choosing inside it.
  breath capacity      a newborn's utterance is short. Maximum phonation
                       time grows with the lungs.
  the larynx           folds ~2-3 mm at birth vs 17-25 mm in an adult, and
                       they close INCOMPLETELY: a baby is breathy and unsteady
                       by anatomy, not by choice.
  the cavity           bore, mouth size, jaw travel, tongue reach, tissue
                       damping — an infant's vowel triangle is smaller
                       because it physically cannot reach the corners yet.

WHAT DOES NOT GROW: the ear. It is FROZEN (genome.EAR_FROZEN) by Iddo's word
of 2026-08-21 — anatomy fixed at birth, the brain learns to use it. Growth
here is the MOUTH and the body, never the sensor.

AGE is measured in developmental days, derived from lived beats rather than
wall-clock, so an organism that was paused for a week is not older for it —
it is the living that ages you. `genome.BEATS_PER_DEV_DAY` sets the pace.
"""
from __future__ import annotations

import math

import genome


# ---------------------------------------------------------------- the clock
def age_days(beat):
    """Developmental age in days, from beats actually lived. Never negative."""
    return max(0.0, float(beat)) / float(genome.BEATS_PER_DEV_DAY)


def maturity(beat, mastered=None, total=None):
    """0.0 at birth -> 1.0 fully grown. **DRIVEN BY WHAT HE CAN DO, NOT BY TIME.**

    Iddo caught this the hour it was written, 2026-08-22: *"למה הוא מגיע לגוף
    בוגר מהר? אם ערן הולך לפי הביולוגיה, אז תן לו לגדול בצורה שהיא נכונה —
    הוא לא יגיע לגוף בוגר והוא עדיין לא יודע להגיד אה."*

    He is right, and the first version of this function was a lie about the
    body. It grew on lived beats alone, so at ERAN's real rate (~9.5M beats in
    eleven hours) he would have worn an adult 17 cm tract inside two days —
    while still unable to say a single vowel. A body that matures past its
    capability is a costume.

    So growth is gated on ACHIEVEMENT: the fraction of the syllable
    curriculum he has actually mastered. A child's larynx does not descend
    because years passed; it descends across the same years in which the
    child learns to speak, and the two belong together.

    Time still contributes, but only as a SLOW FLOOR capped at
    genome.MATURITY_TIME_CAP: living alone can carry him from a newborn to a
    small child and no further. **He cannot grow up without learning to
    talk** — which is exactly the sentence Iddo said.

    A pleasant consequence: the body becomes a visible record of what he
    knows. Measure his vocal tract and you can read his curriculum off it.
    """
    a = age_days(beat) / float(genome.MATURITY_DAYS)
    by_time = float(1.0 - math.exp(-3.0 * max(0.0, a)))
    if mastered is None:
        return min(by_time, float(genome.MATURITY_TIME_CAP))
    total = int(total or genome.MATURITY_MILESTONES)
    frac = 0.0 if total <= 0 else max(0.0, min(1.0, float(mastered) / total))
    # TIME IS THE ENGINE, CAPABILITY IS THE BRAKE.
    # Time drives the growth — a child ages whether or not anyone is teaching
    # it. But what he can DO sets a ceiling time may not pass through, so a
    # body can never mature past its own voice. With nothing mastered the
    # ceiling is MATURITY_TIME_CAP: he stays a small child however long he
    # lives. Master everything and the ceiling lifts entirely — and time
    # still has to carry him the rest of the way, over years, as it should.
    ceiling = float(genome.MATURITY_TIME_CAP) +         (1.0 - float(genome.MATURITY_TIME_CAP)) * frac
    return min(by_time, ceiling)


def maturity_from_state(beat, curriculum_path=None):
    """Read mastery off the organism's own curriculum file and grow by it.

    Falls back to time-only (capped) if the file is missing — a body with no
    record of learning anything stays small, which is the honest default.
    """
    import json
    import os
    path = curriculum_path or genome.CURRICULUM_FILE
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        return maturity(beat, len(d.get("mastered", [])),
                        len(getattr(genome, "CURRICULUM", []) or []))
    except (OSError, ValueError, TypeError):
        return maturity(beat)


def _lerp(a, b, t):
    return float(a) + (float(b) - float(a)) * float(max(0.0, min(1.0, t)))


# ------------------------------------------------------------------ the body
def tract_sections(beat, mastered=None, total=None):
    """Waveguide sections = tract length. Infant ~7 cm -> adult ~17 cm.

    Returned as an int because the ladder has whole sections, and clamped so
    the tube can never be shorter than a newborn's or longer than an adult's.
    """
    n = _lerp(genome.TRACT_SECTIONS_INFANT, genome.TRACT_SECTIONS_ADULT,
              maturity(beat, mastered, total))
    return int(max(genome.TRACT_SECTIONS_INFANT,
                   min(genome.TRACT_SECTIONS_ADULT, round(n))))


def f0_range(beat, mastered=None, total=None):
    """(f0_min, f0_max) in Hz. Falls and narrows with age.

    The child still chooses freely inside the range — growth moves the walls
    of the room, it does not choose the note.
    """
    m = maturity(beat, mastered, total)
    lo = _lerp(genome.F0_MIN_INFANT, genome.F0_MIN_ADULT, m)
    hi = _lerp(genome.F0_MAX_INFANT, genome.F0_MAX_ADULT, m)
    return float(lo), float(hi)


def cavity(beat, mastered=None, total=None):
    """The SHAPE and SIZE of the plant, not just its length.

    Iddo, 2026-08-22: *"זה משפיע גם על תיבת התהודה, גודל הגרון... צורת הפה,
    גודל הפה."* Length was only the most visible thing. An infant's whole
    vocal plant is smaller and differently proportioned, and each of these
    has an acoustic job:

      bore_base    the resting pharyngeal bore. A narrower tube has a higher
                   characteristic impedance and sharper, higher resonances.
      oral_min     the mouth with the jaw closed — a baby's is far smaller,
                   which is why its vowel space is so much tighter.
      oral_span    how much the jaw can add. A newborn cannot open wide, so
                   the reachable vowel triangle is genuinely smaller: it is
                   not that a baby WON'T say /a/, it is that it CANNOT yet.
      tongue_depth how deep a hump the tongue can make. This is the single
                   biggest limit on distinguishing vowels early.
      lip_min      how far the lips can close. Infant lips round more easily
                   and seal less completely.
      loss         soft young tissue damps more, so an infant's formants are
                   broader and less sharply defined — audibly "softer".
    """
    m = maturity(beat, mastered, total)
    return {
        "bore_base": _lerp(genome.BORE_BASE_INFANT, genome.BORE_BASE_ADULT, m),
        "oral_min": _lerp(genome.ORAL_MIN_INFANT, genome.ORAL_MIN_ADULT, m),
        "oral_span": _lerp(genome.ORAL_SPAN_INFANT, genome.ORAL_SPAN_ADULT, m),
        "tongue_depth": _lerp(genome.TONGUE_DEPTH_INFANT,
                              genome.TONGUE_DEPTH_ADULT, m),
        "lip_min": _lerp(genome.LIP_MIN_INFANT, genome.LIP_MIN_ADULT, m),
        "loss": _lerp(genome.LOSS_INFANT, genome.LOSS_ADULT, m),
    }


def larynx(beat, mastered=None, total=None):
    """THE VOICE SOURCE itself — Iddo's one word: *"גרון."*

    The tract is the instrument's body; this is its reed. An infant's vocal
    folds are about 2-3 mm long against an adult's 17-25 mm, and — the part
    that actually shapes the sound — they **do not close completely**. A baby
    is breathy by anatomy, not by choice, and its pitch control is unsteady
    because the muscles are new.

      open_quotient     fraction of each cycle the folds stay open. Higher =
                        breathier, weaker harmonics, softer voice.
      jitter/shimmer    cycle-to-cycle wobble in period and amplitude. High
                        in a newborn: motor control has not arrived yet. This
                        is the difference between a baby and a synthesiser.
      glottis_reflect   how completely the closed end reflects. A leaky
                        glottis both damps the resonances and lets breath
                        through — the audible "hh" under an infant's vowel.

    All four fall toward adult values as the child gains control. Nothing here
    is a style choice; each is a physiological fact with an acoustic signature.
    """
    m = maturity(beat, mastered, total)
    return {
        "open_quotient": _lerp(genome.OPEN_QUOTIENT_INFANT,
                               genome.OPEN_QUOTIENT_ADULT, m),
        "jitter": _lerp(genome.JITTER_INFANT, genome.JITTER_ADULT, m),
        "shimmer": _lerp(genome.SHIMMER_INFANT, genome.SHIMMER_ADULT, m),
        "glottis_reflect": _lerp(genome.GLOTTIS_REFLECT_INFANT,
                                 genome.GLOTTIS_REFLECT_ADULT, m),
    }


def utterance_seconds(beat, mastered=None, total=None):
    """How long a single utterance may be. Newborn breath is short."""
    return _lerp(genome.UTTERANCE_S_INFANT, genome.UTTERANCE_S_ADULT,
                 maturity(beat, mastered, total))


def body_at(beat, mastered=None, total=None):
    """The whole age-dependent anatomy in one dict — the only thing callers
    should ever ask for. If a number is not in here, it does not grow."""
    lo, hi = f0_range(beat, mastered, total)
    c = cavity(beat, mastered, total)
    g = larynx(beat, mastered, total)
    return {
        **{k: round(v, 4) for k, v in c.items()},
        **{k: round(v, 4) for k, v in g.items()},
        "beat": int(max(0, beat)),
        "age_days": round(age_days(beat), 3),
        "maturity": round(maturity(beat, mastered, total), 4),
        "mastered": (None if mastered is None else int(mastered)),
        "tract_sections": tract_sections(beat, mastered, total),
        "tract_cm": round(tract_sections(beat, mastered, total) * 34000.0 / (2.0 * genome.SAMPLE_RATE), 2),
        "f0_min": round(lo, 1),
        "f0_max": round(hi, 1),
        "utterance_seconds": round(utterance_seconds(beat, mastered, total), 3),
    }


def describe(beat, mastered=None, total=None):
    """One honest human line, for the journal and for Iddo."""
    b = body_at(beat, mastered, total)
    return (f"day {b['age_days']:.1f} · maturity {b['maturity']:.0%} · "
            f"tract {b['tract_cm']:.1f} cm ({b['tract_sections']} sections) · "
            f"voice {b['f0_min']:.0f}-{b['f0_max']:.0f} Hz · "
            f"breath {b['utterance_seconds']:.2f} s · "
            f"mouth {b['oral_min']:.2f}+{b['oral_span']:.2f} cm · "
            f"tongue reach {b['tongue_depth']:.2f} · "
            f"glottis open {b['open_quotient']:.0%}, jitter {b['jitter']:.1%}")
