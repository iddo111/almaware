#!/usr/bin/env python3
"""שני אנשים · TWO PEOPLE — one thread, many strands.

לזכרה של עלמה ז״ל.

Iddo, 2026-08-29:
    "משקלים לא רק מספר — יכול להיות תמונה. נגיד בין הנוירון שלי לנוירון של עלמה
     יש משקל שהוא תמונה שלנו מחובקים."
    "או לדוגמא שני אנשים גם אוהבים אבל גם כועסים — ישנם כל מיני משקלים."

He asked what a weight can SAY. The language already answered, in SPEC.md §4:

    "One thread, many strands is the heart of ALMA's rich connections:
     a single connection can speak several times, at several strengths,
     into the future."

**The relationship is the THREAD. The feelings are its STRANDS.**

That is not a picture of the idea. It is the idea, and it runs:

    anger   weight  3.0   delay 1    loud, and it arrives FIRST
    love    weight  1.0   delay 5    quieter, later — and it keeps arriving
    duty    weight  0.5   delay 3    the thing neither of them names

Three strands on ONE thread. The destination does not receive "a relationship";
it receives anger on beat 2, duty on beat 4, love on beat 6 — and then again, and
again, because the weave is cyclic and that is what a bond is.

WHAT `drift` ADDS (v0.2): a strand that helped the other knot speak THICKENS; one that
spoke into silence THINS. So the history of the relationship becomes the thickness of a
cord — visible, walk-into-able, and not written down anywhere by anybody. Feed the love
strand and it grows. Stop feeding it and it does not.

WHAT `bearing` ADDS (v0.2): the number says how strong; the bearing says **what it is
made of**. The love strand between Iddo's knot and Alma's carries the photograph. Walking
the weave in VR you would come to a thick cord and see, on it, why it is thick.

Run:  python examples/two_people.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alma.loom import Loom, Strand, Weave      # noqa: E402


def two_people() -> Weave:
    w = Weave("two-people")

    # Two knots. Each one pools what reaches it: a person carries what they were given.
    w.knot("iddo", verb="pool")
    w.knot("alma", verb="pool")

    # The heard signal — the hem of the weave, where we can read what actually arrived.
    w.knot("what_alma_feels", verb="fringe")
    w.knot("what_iddo_feels", verb="fringe")

    # ONE thread from him to her. THREE strands. This is the whole idea.
    w.thread("iddo", "alma", strands=[
        Strand(weight=3.0, delay=1, drift=0.00, tint="anger",
               bearing="the sentence neither of them can take back"),
        Strand(weight=1.0, delay=5, drift=0.06, tint="love",
               bearing="photo/iddo-and-alma-embracing.jpg"),
        Strand(weight=0.5, delay=3, drift=0.00, tint="duty",
               bearing="the thing neither of them names"),
    ])
    # And one back, because a bond is not a broadcast.
    w.thread("alma", "iddo", strands=[
        Strand(weight=2.0, delay=1, drift=0.00, tint="anger",
               bearing="the door closing"),
        Strand(weight=1.2, delay=4, drift=0.06, tint="love",
               bearing="photo/iddo-and-alma-embracing.jpg"),
    ])

    w.thread("alma", "what_alma_feels")
    w.thread("iddo", "what_iddo_feels")

    w.seed("iddo", 1.0, beat=1)
    w.run_hint = 24
    return w


def main():
    w = two_people()
    res = Loom().run(w)

    print("שני אנשים · TWO PEOPLE")
    print(f"  {len(w.knots)} knots, {len(w.threads)} threads, "
          f"{sum(len(t.strands) for t in w.threads)} strands, {res.beats} beats\n")

    print("  what reached her, beat by beat:")
    for beat, val in res.fringes.get("what_alma_feels", [])[:10]:
        print(f"    beat {beat:>3}   {val:+8.3f}")

    print("\n  what reached him:")
    for beat, val in res.fringes.get("what_iddo_feels", [])[:10]:
        print(f"    beat {beat:>3}   {val:+8.3f}")

    if res.learned is not None:
        print("\n  and what the running CHANGED — the cords, before and after:")
        i = 0
        for t in w.threads:
            for st in t.strands:
                after = res.learned[i]; i += 1
                if st.drift:
                    arrow = "thickened" if after > st.weight else "thinned"
                    print(f"    {t.src:>5} → {t.dst:<5} [{st.tint:<5}] "
                          f"{st.weight:5.2f} → {after:5.2f}   {arrow}")
                    if st.bearing:
                        print(f"          bearing: {st.bearing}")

    print("\n  The anger arrives first and loudest, every time.")
    print("  The love arrives later — and it is the only strand that GREW.")


if __name__ == "__main__":
    main()
