# -*- coding: utf-8 -*-
"""ALMA-REASON — שקלא וטריא as a computational structure, not a prompt.

B2, the reasoning organ of ALMA-GUARD-NET (the holobrain).

Iddo, 2026-09-11 11:57:
    "ונוסיף בתוך המודל-שלנו-אמבדד קוד לריזונינג לוגיקה שקלא וטריא טהור.
     אני רוצה שהמודל שלנו יהיה ספצ בגמרא ולוגיקה באימון חוץ מהקוד
     וחוץ מהאימון הספציפי."

WHAT IS NEW HERE, AND WHAT IS NOT
---------------------------------
D:\\CLAUDE\\quorum\\shakla.py already runs שקלא וטריא — as *prompted behaviour*.
It hands the four moves (קושיא / תירוץ / ראיה / דחייה) to LLMs as Hebrew
instructions and collects the text they write back. The form lives in the
prompt; nothing in the machine has a shape.

This package is the other thing. Here the form is a **weave** (alma/loom.py):
two seats are two knot clusters, a קושיא is a spark with a negative weight
landing in the opponent's standing-pool, a תירוץ is the same spark landing
positively in one's own, and a דחייה is a `gate` closing because the pool
behind its `key` port went to zero. A conceded seat then genuinely **stops
speaking** for the rest of the run, and its silence changes what the other
seat receives. That is the dialectic as mechanism.

SEPARATE FROM alma_guard/ ON PURPOSE
------------------------------------
`alma_guard` (B1, the security classifier) and `alma_reason` (B2) are two
organs of one holobrain: same substrate, separate weaves, separate datasets,
separate training. This package imports `alma` (the language runtime) and
NOTHING from `alma_guard`. One substrate fact was learned from reading B1's
encoder and is re-derived here in our own words (encoding.py, "presence, not
magnitude") — that is a property of the loom, not a shared pipeline.

LAYOUT
------
    encoding.py   an argument -> presence sparks
    syllogism.py  the exact-ground-truth corpus: all 256 categorical moods
    machloket.py  hand-transcribed Talmudic disputes whose פסק is recorded
    weave.py      THE TOPOLOGY — two seats, standing-pools, gates, rounds
    train.py      three-factor (pain/pleasure) + node perturbation, baselines
"""
__version__ = "0.1.0"
