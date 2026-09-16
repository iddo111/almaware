# -*- coding: utf-8 -*-
"""THE SIBLING'S JUNCTION - a whole holobrain's binding space, written in full ALMA.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

לזכרה של עלמה ז"ל.

WHAT THIS IS. Iddo, 2026-09-01 12:27 (verbatim): "הנצר הזה יהיה הולוברין, הוא לא
יהיה של זה, הוא יהיה כמו ערן... הולוברין ממש... הכל, הכל, הכל, הכל."

This is NOT another organ hung off ERAN. It is the junction of a SECOND, WHOLE
holobrain - a sibling - and the one thing that makes it a different creature is
that it is born with the syllables already in its mouth. ERAN was born mute and
has spent weeks hunting /ba/. This one starts holding twelve gestures.

    ERAN     : born mute, searches, may never arrive
    SIBLING  : born with the dowry, and we find out what that costs

It is a CONTROL ARM in the strict sense, and it is said here in the code's own
voice so nobody downstream can quietly promote it to a result: the two differ in
exactly ONE thing - what the mouth knows at birth. Everything else (eye, hand,
imaginer, ear, this junction) is COPIED from ERAN, unchanged, at birth. If the
sibling turns out different, the dowry is the only place the difference can have
come from.

THE ALMA-LANGUAGE LAW. Everything inside a holobrain is ALMA. So the junction is
a weave: knots, threads, strands, seeds. Arithmetic lives in the connections
(ALMA's second law) - an affinity is a strand WEIGHT, never an `if` in a knot.
Subtraction is a negative weight. Raw numerics live in spells.

THE FACADE TEST (standing rule, inherited from WINSTON):
    a knot exists only if it accumulates a measured scalar, makes a fire-or-
    silence decision, or produces a real measurement. If deleting it changes no
    number and no decision, it is not built.
Every knot below is annotated with which of the three it earns its place by, and
tests/test_facade.py proves it by perturbation, not by assertion.

THE SHAPE OF ONE ROUND (beats are real; nothing is instant):

    beat 1   sense        the stimulus lands and fires
    beat 2   unit_*       15 candidates; each fires ONLY if its strand carried
                          enough - that is the recognition decision
    beat 3   chorus       fires only if 2+ units answered  = CONFUSION
             mouth        pools whatever answered
             margin       spell: best minus second  = how sure it is
    beat 4   hush         gate: open unless chorus shut it (negative weight)
    beat 5   voice        fringe: what actually came out
             sureness     fringe: the margin
             doubt        fringe: the confusion

WHY 15 UNITS AND NOT 12. The dowry is twelve. But the ear's own measured
confusion table also names `ba`, `abba` and `ima` - targets ERAN has and the
sibling does not. They are tied in as units it can HEAR but has no gesture for.
That is not decoration: it is the inherited wall stated honestly in the anatomy.
The sibling can recognise /ba/ and cannot say it, exactly like its brother.
"""
from __future__ import annotations

import math
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(_HERE, "organs", "alma-language"),
           os.path.join(_HERE, "alma-language")):
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

from alma import Loom, Strand, Weave, spells          # noqa: E402

__all__ = ["DOWRY_UNITS", "HEARD_ONLY", "UNITS", "affinities", "junction",
           "listen", "teach_spells", "THETA", "TAU"]

# The twelve the sibling is BORN holding a gesture for (the dowry).
DOWRY_UNITS = ("pa", "ma", "na", "ta", "ga", "da", "la", "ka", "aa", "ih", "ah", "ra")
# Heard, measured, recognisable - and unspeakable. ERAN's wall, inherited.
HEARD_ONLY = ("ba", "abba", "ima")
UNITS = DOWRY_UNITS + HEARD_ONLY

# TAU - the softness of recognition, in the ear's own wdist units. Not tuned to
# flatter the result: it is 1.0, one wdist unit, and the accuracy it produces is
# whatever it is. `sibling.py --naming` reports it against the 1/15 chance floor.
TAU = 1.0
# THETA - how much affinity has to reach a unit before it dares answer.
# Principled, not fitted: with 15 candidates a uniform (uninformed) affinity is
# 1/15 = 0.067, so THETA is 3x chance. A unit speaks only when the ear makes it
# three times likelier than guessing. It was NOT tuned to raise the naming score
# or to make the facade test go green - lowering it would wake more unit knots and
# buy a prettier test with a meaningless one.
THETA = 3.0 / len(UNITS)


# ------------------------------------------------------------------ the spell
# ALMA's rule: raw numerics live in spells, not in knots. `margin` is the one
# genuine number-crunching step in the junction, so it is the one spell.

def _margin(vs):
    """best minus second-best. One answer -> its own strength. None -> silence.

    This is the sibling's SURENESS, and it is a real measured scalar: the gap
    between what it thinks it heard and its nearest rival."""
    if not vs:
        return None
    s = sorted(vs, reverse=True)
    return s[0] - s[1] if len(s) > 1 else s[0]


def _crowd(vs):
    """A crowd answered -> exactly ONE unit of doubt, whatever the crowd's size.

    This exists because of a real bug caught by the naming test, and the bug is
    worth keeping written down. The chorus first counted confusion with
    `sum` + `rise 2`, which sums the STRENGTHS that arrive. Unit strengths are
    affinities (~0.1-0.3), so two units answering summed to ~0.4 and the chorus
    never once fired: `doubt` was always empty and the `hush` gate was dead code
    that could not shut. Two answers is a COUNT, not a total - so the trigger is
    `count 2`, and this spell flattens the crowd to 1.0 so that the negative
    strand into `hush.key` exactly cancels the permit. Magnitudes must not decide
    whether the mouth opens; the number of voices must."""
    return 1.0


def teach_spells() -> None:
    """Put the junction's spells in ALMA's book. Idempotent."""
    if not spells.known("sibling_margin"):
        spells.teach("sibling_margin", _margin)
    if not spells.known("sibling_crowd"):
        spells.teach("sibling_crowd", _crowd)


# --------------------------------------------------------------- the affinity
# ALMA's second law: arithmetic lives in the connections. So recognition is not
# computed inside a knot - it is the WEIGHT of the strand from `sense` to each
# unit. The numbers are ear3's own measured wdist table (best.json "nearest"),
# never invented here.

def affinities(nearest, tau: float = TAU):
    """Measured wdist per candidate -> a strand weight per candidate.

    Softmax over -wdist/tau, restricted to units the junction actually ties.
    Nearer in the ear's metric = a thicker cord. Nothing else."""
    xs = {u: -nearest[u] / tau for u in UNITS if u in nearest}
    if not xs:
        return {}
    top = max(xs.values())
    ex = {u: math.exp(v - top) for u, v in xs.items()}
    tot = sum(ex.values())
    return {u: e / tot for u, e in ex.items()}


# ---------------------------------------------------------------- the junction

def junction(nearest, *, theta: float = THETA, tau: float = TAU,
             drift: float = 0.0) -> Weave:
    """Tie the whole junction for ONE stimulus, and hand back the weave.

    `nearest` is the ear's measured distance from this stimulus to every unit.
    `drift` > 0 makes the sense->unit cords plastic: a cord whose unit fires
    thickens, a cord that speaks into silence thins. No gradient, nothing travels
    backwards - ALMA forbids it, because every delay is >= 1.
    """
    teach_spells()
    w = Weave("sibling-junction")
    aff = affinities(nearest, tau)

    # -- sense: accumulates the stimulus and decides to fire.  [decision]
    w.knot("sense", verb="sum", trigger="any")
    w.seed("sense", 1.0, beat=1)

    # -- the units: each is a fire-or-silence recognition decision. [decision]
    for u in UNITS:
        w.knot("unit_" + u, verb="sum", trigger="rise %g" % theta)
        w.thread("sense", "unit_" + u,
                 strands=[Strand(weight=aff.get(u, 0.0), delay=1, drift=drift)])

    # -- chorus: fires only when TWO OR MORE units answered = confusion. [decision]
    # `count 2` counts SPARKS (voices). `rise 2` would sum strengths and never
    # reach 2 - that was the dead-gate bug. Do not "simplify" this back.
    w.knot("chorus", verb="spell", spell="sibling_crowd", trigger="count 2")
    # -- mouth: pools the strength of whatever answered. [scalar]
    w.knot("mouth", verb="pool", trigger="any")
    # -- margin: the spell. best minus second = sureness. [measurement]
    w.knot("margin", verb="spell", spell="sibling_margin", trigger="any")

    for u in UNITS:
        # a unit that answers contributes ONE voice to the chorus...
        w.thread("unit_" + u, "chorus", strands=[Strand(weight=1.0, delay=1)])
        # ...and its full strength to the mouth and to the margin spell.
        w.thread("unit_" + u, "mouth", strands=[Strand(weight=1.0, delay=1)])
        w.thread("unit_" + u, "margin", strands=[Strand(weight=1.0, delay=1)])

    # -- permit / hush: speak UNLESS confused.
    # ALMA has no `not`. It does not need one: the chorus sends a NEGATIVE weight
    # into the same key the permit feeds, and the gate simply never opens. That
    # is law 2 doing the work an `if` would do in any other language.
    w.knot("permit", verb="pass", trigger="any")           # [decision: opens the gate]
    w.seed("permit", 1.0, beat=3)
    w.knot("hush", verb="gate", trigger="any")             # [decision: speak or not]
    w.thread("permit", "hush", port="key", strands=[Strand(weight=1.0, delay=1)])
    w.thread("chorus", "hush", port="key", strands=[Strand(weight=-1.0, delay=1)])
    w.thread("mouth", "hush", strands=[Strand(weight=1.0, delay=1)])

    # -- the fringes: what actually came out. [measurement]
    w.knot("voice", verb="fringe", trigger="any")
    w.knot("sureness", verb="fringe", trigger="any")
    w.knot("doubt", verb="fringe", trigger="any")
    w.thread("hush", "voice", strands=[Strand(weight=1.0, delay=1)])
    w.thread("margin", "sureness", strands=[Strand(weight=1.0, delay=1)])
    w.thread("chorus", "doubt", strands=[Strand(weight=1.0, delay=1)])

    w.run_hint = 8
    return w


def listen(nearest, *, theta: float = THETA, tau: float = TAU,
           drift: float = 0.0) -> dict:
    """Run one stimulus through the junction and report what the weave DID.

    The answer is read out of the fires and fringes - never recomputed in Python.
    If the weave did not decide it, this does not claim it."""
    aff = affinities(nearest, tau)
    w = junction(nearest, theta=theta, tau=tau, drift=drift)
    r = Loom().run(w)

    answered = [f.knot[5:] for f in r.fires
                if f.knot.startswith("unit_") and f.spoke is not None]
    spoke = r.fringe("voice")
    return {
        "answered": answered,                       # which units dared fire
        "said": (max(answered, key=lambda u: aff[u]) if (spoke and answered) else None),
        "spoke": bool(spoke),                       # did the gate open?
        "sureness": (r.fringe("sureness") or [None])[0],
        "confused": bool(r.fringe("doubt")),
        "beats": r.beats,
        "finished": r.finished,
        "learned": r.learned,
        "affinity": aff,
    }
