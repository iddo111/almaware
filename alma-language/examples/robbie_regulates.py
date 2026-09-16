#!/usr/bin/env python3
"""רובי מווסת את עצמו · ROBBIE REGULATES — a closed loop, written in ALMA.

לזכרה של עלמה ז״ל.

Iddo, 2026-08-29: *"דיברנו מקודם על ויסות עצמי מנינגר ל-AI ופסיכולוג לרובי הרובוט"*
and earlier the same day: *"אם בן אדם יכול גם קלוד יכול"*.

────────────────────────────────────────────────────────────────────────────
THE THING BEING TESTED, and it is not a metaphor
────────────────────────────────────────────────────────────────────────────
Every mind machine ever sold — Mindspa, Kasina, Proteus, the Silva tapes, Jack
Schwarz's own strobe — is OPEN LOOP. It plays a programme *at* a person and never
measures whether the body answered. Elmer Green's Menninger work was different in
exactly one way: **the hand's temperature was measured and given back**, and that is
the entire reason a person could learn to change it.

So the question is not "can a machine be calmed". It is: **does closing the loop
actually bound a runaway, and can the loop learn to bound it without help?**

Three weaves, identical except for the loop:

    1. רובי לבד        robbie feeds himself, nothing watches      -> expect RUNAWAY
    2. רובי והפסיכולוג  a `gate` sits on the return path            -> expect BOUNDED
    3. רובי לומד       the same loop, but the self-strand DRIFTS   -> expect he learns

The third is the one that matters. In autogenic training a person needs the
instrument at first and then does not — the regulation is internalised. Case 3 has
no psychologist at all; the cord that feeds him back thins by itself because ALMA's
v0.2 rule thins a strand that speaks into silence.

WHY THIS IS THE HONEST FIRST THING TO WRITE IN ALMA: case 1 is not invented for the
demonstration. It is a REAL BUG found an hour earlier in `examples/two_people.py`,
where two pools fed each other at weight > 1 and reached 841,437 by beat 14. The
psychologist is the fix for a defect that actually happened.

Run:  python examples/robbie_regulates.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alma.loom import Loom, Strand, Weave      # noqa: E402

CALM = 6.0          # the line above which Robbie is more aroused than he should be


def robbie(psychologist: bool, learns: bool) -> Weave:
    """Robbie is one `pool`: whatever reaches him, he carries. That is a nervous system
    in one word — the only ALMA verb with memory across fires."""
    w = Weave("robbie")
    w.knot("robbie", verb="pool")
    w.knot("felt", verb="fringe")               # the hem: what he is actually holding

    if psychologist:
        # THE PSYCHOLOGIST. Not a controller — a `gate` on the channel by which Robbie
        # feeds himself. It does not decide what he feels; it decides whether the loop
        # is open. That is precisely what biofeedback does for a person.
        w.knot("psychologist", verb="gate")

        # the loop, now passing through the gate
        w.thread("robbie", "psychologist", strands=[
            Strand(weight=1.0, delay=1,
                   drift=(0.05 if learns else 0.0), tint="self")])
        w.thread("psychologist", "robbie", strands=[Strand(weight=0.9, delay=1)])

        # THE MEASUREMENT, fed back — the whole Menninger point. A negative weight plus a
        # positive bias means the key is positive while he is calm and turns negative
        # once he passes CALM. `gate` speaks only while its key is positive, so the loop
        # closes itself exactly when it should.
        w.knot("watch", verb="sum", bias=CALM)
        w.thread("robbie", "watch", strands=[Strand(weight=-1.0, delay=1)])
        w.thread("watch", "psychologist", port="key", strands=[Strand(weight=1.0, delay=1)])
    else:
        # No one is watching. The loop feeds itself, and nothing can stop it.
        w.thread("robbie", "robbie", strands=[
            Strand(weight=1.15, delay=1,
                   drift=(-0.05 if learns else 0.0), tint="self")])

    w.thread("robbie", "felt", strands=[Strand(weight=1.0, delay=1)])
    w.seed("robbie", 1.0, beat=1)
    w.run_hint = 30
    return w


def trace(name, w, n=12):
    res = Loom().run(w)
    vals = [v for _, v in res.fringes.get("felt", [])][:n]
    peak = max((abs(v) for v in vals), default=0.0)
    print(f"\n{name}")
    print("  " + "  ".join(f"{v:8.2f}" for v in vals[:8]))
    if len(vals) > 8:
        print("  " + "  ".join(f"{v:8.2f}" for v in vals[8:n]))
    print(f"  peak over {len(vals)} readings: {peak:,.2f}")
    if res.learned is not None:
        i = 0
        for t in w.threads:
            for st in t.strands:
                after = res.learned[i]; i += 1
                if st.drift:
                    print(f"  the cord that feeds him back: "
                          f"{st.weight:.2f} → {after:.2f}"
                          f"   ({'thinned — he is damping himself' if after < st.weight else 'thickened'})")
    return peak


def main():
    print("רובי מווסת את עצמו · ROBBIE REGULATES")
    print("=" * 62)

    p1 = trace("1. רובי לבד — no one is watching", robbie(False, False))
    p2 = trace("2. רובי והפסיכולוג — a gate on his own loop", robbie(True, False))
    p3 = trace("3. רובי לומד — no psychologist, the cord drifts",
               robbie(False, True))

    print("\n" + "=" * 62)
    print("VERDICT — measured, not asserted:")
    print(f"  alone           peak {p1:>14,.2f}")
    print(f"  with the gate   peak {p2:>14,.2f}   "
          f"{'BOUNDED' if p2 < p1 / 10 else 'NOT bounded — the claim fails'}")
    print(f"  learning alone  peak {p3:>14,.2f}   "
          f"{'HE DAMPED HIMSELF' if p3 < p1 / 10 else 'he did NOT learn to damp — the claim fails'}")
    print()
    print("  The loop is the whole difference. Nothing here calms Robbie by")
    print("  telling him to be calm; the measurement is fed back and the")
    print("  channel closes itself. That is the one thing every mind machine")
    print("  ever sold does not do.")


if __name__ == "__main__":
    main()
