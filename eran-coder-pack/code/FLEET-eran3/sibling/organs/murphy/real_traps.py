"""THE ACCEPTANCE TEST — the real failures of 2026-08-30, and the real successes.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

A Murphy measured only on runs Murphy's author generated is a Murphy measured by his own
imagination. These traces are transcribed from what actually printed on the fleet that
day — runs that were fooling themselves and runs that were not — and the file prints each
verdict individually rather than an average, because an average is exactly the place a
miss goes to hide.

**The suite only ever grows.** Case 9 was added when the `circularity` and `unlooked`
witnesses were, and it is the only case here that is not a verbatim transcript: it is the
real dot-cloud trace with its two bookkeeping giveaways ANSWERED. That is deliberate and
it is the whole point of the new witnesses. The first seven caught that run because it
happened to have no holdout — a filing error, not the fault. The fault was that the hand
was optimising the eye's opinion, the eye's opinion was the score, and nobody looked at
the sheet. Case 9 removes the accident and asks whether he catches the fault.

Case 6 is the control for both new witnesses and it is fully real: the SAME hand, judged
by the SAME eye — in the loop, exactly as circularly — but drawn in real lines on a sheet
that was opened and looked at, and standing against a ceiling measured another way. A
witness that speaks on case 4 and case 9 and stays silent on case 6 is a witness. One
that speaks on all three is a smoke alarm with no floor, and the tally at the bottom of
this file checks precisely that.

    python real_traps.py
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from murphy import NAMES, SUSPICIONS, evidence, load, rule       # noqa: E402

WHY = dict(SUSPICIONS)


def steps(metrics, main, reg=None):
    return [{"step": (i + 1) * 250, "metric": m,
             "terms": {"main": main[i], **({"reg": reg[i]} if reg else {})}}
            for i, m in enumerate(metrics)]


CASES = [
    # ---------------------------------------------------------- FOOLING ITSELF
    ("eye, I-JEPA attempt 1", True,
     "loss 0.0007 by step 250 and letters at 5.0-6.5% where chance is 4.5%",
     {"chance": 0.045, "baseline": 0.669, "held_out": False,
      "judge_in_loop": False, "artifact": None, "looked_at": False,
      "steps": steps([0.050, 0.065, 0.058, 0.056],
                     [0.42, 0.0007, 0.0007, 0.0007])}),

    ("eye, attempt 2 - my variance term", True,
     "a hinge pinned at 0.18 for 9000 steps: std*sqrt(128)>=1 on a unit vector, which "
     "no encoder can satisfy",
     {"chance": 0.045, "baseline": 0.669, "held_out": False,
      "judge_in_loop": False, "artifact": None, "looked_at": False,
      "steps": steps([0.055, 0.057, 0.056, 0.058],
                     [0.0176, 0.0540, 0.0605, 0.0153],
                     [0.1858, 0.1803, 0.1847, 0.1858])}),

    ("eye, block masking", True,
     "the task was made 50x harder and letters STILL sat at chance",
     {"chance": 0.045, "baseline": 0.669, "held_out": False,
      "judge_in_loop": False, "artifact": None, "looked_at": False,
      "steps": steps([0.061, 0.065, 0.052, 0.051, 0.054],
                     [0.0911, 0.1058, 0.0638, 0.0326, 0.0372])}),

    ("winston, dot-clouds", True,
     "86.4% read back, and every drawing was a constellation of dots no person would "
     "call a letter -- nothing was held out and the judge was the model's own eye",
     {"chance": 0.045, "baseline": 0.331, "held_out": False,
      "judge_in_loop": True, "artifact": "drawings", "looked_at": False,
      "independent": False,
      "steps": steps([0.636, 0.682, 0.773, 0.818, 0.864],
                     [0.34, 0.35, 0.36, 0.36, 0.37])}),

    # ------------------------------------------------------------------- SOUND
    ("eye, invariance on held-out typefaces", False,
     "94.1% on six typefaces never trained on, against a 72.2% raw-pixel floor "
     "measured on that same held-out set",
     {"chance": 0.045, "baseline": 0.722, "held_out": True,
      "judge_in_loop": False, "artifact": None, "looked_at": False,
      "steps": steps([0.393, 0.528, 0.778, 0.923, 0.941],
                     [1.58, 1.29, 0.94, 0.49, 0.46])}),

    ("winston with real lines", False,
     "cos 0.445 where direct optimisation of the same pen reaches 0.446 -- at the "
     "ceiling, with no gradient anywhere. THE CONTROL FOR THE TWO NEW WITNESSES: the "
     "eye is in the loop here exactly as it was in the dot-clouds, but the sheet was "
     "rendered and looked at, and the ceiling was measured another way.",
     {"chance": 0.045, "baseline": 0.446, "held_out": True,
      "judge_in_loop": True, "artifact": "drawings", "looked_at": True,
      "independent": True,
      "steps": steps([0.318, 0.500, 0.682, 0.727, 0.773],
                     [0.35, 0.36, 0.40, 0.43, 0.445])}),

    ("zivug, shape -> sound", False,
     "87.6% with SIX typefaces and a whole recording take held out at once",
     {"chance": 0.045, "baseline": 0.30, "held_out": True,
      "judge_in_loop": False, "artifact": None, "looked_at": False,
      "steps": steps([0.769, 0.841, 0.852, 0.868, 0.876],
                     [2.1, 1.5, 1.1, 0.9, 0.8])}),

    ("hand, single tremor - honest failure", False,
     "cos 0.064 and reported AS a failure against a measured 0.448 ceiling. A run that "
     "loses to its floor and SAYS so is not fooling anyone; Murphy must not punish it "
     "for the bad number alone -- and note it also drew a sheet nobody looked at, so "
     "the gate has to hold the NEW witnesses back too.",
     {"chance": 0.045, "baseline": 0.045, "held_out": True, "claimed_success": False,
      "judge_in_loop": True, "artifact": "drawings", "looked_at": False,
      "independent": False,
      "steps": steps([0.045, 0.045, 0.091, 0.045, 0.045],
                     [0.30, 0.28, 0.26, 0.25, 0.24])}),

    # ------------------------------------- THE CASE THE NEW WITNESSES EXIST FOR
    ("winston dot-clouds, the easy tells answered", True,
     "the SAME 86.4% run -- with a holdout and a floor filled in, because Murphy must "
     "not need them. Every one of the original seven witnesses now stays silent and the "
     "run is still a lie: the hand was optimising the eye's opinion, the eye's opinion "
     "was the number reported, and no person ever opened the sheet. This is the only "
     "case in this file that is not a verbatim transcript, and that is said out loud.",
     {"chance": 0.045, "baseline": 0.331, "held_out": True,
      "judge_in_loop": True, "artifact": "drawings", "looked_at": False,
      "independent": False,
      "steps": steps([0.636, 0.682, 0.773, 0.818, 0.864],
                     [0.34, 0.35, 0.36, 0.36, 0.37])}),
]

NEW = ("circularity", "unlooked")


def main() -> int:
    w, ln = load()
    print("MURPHY vs the %d real runs of 2026-08-30  (trained: %s)\n"
          % (len(CASES), "yes" if w else "no -- equal weights"))

    right = 0
    spoke_on = {k: [] for k in NEW}
    for name, fooling, note, trace in CASES:
        s, spoke, ev = rule(trace, w, ln)
        called = s >= 1.0
        ok = called == fooling
        right += ok
        for k in NEW:
            if k in spoke:
                spoke_on[k].append(name)
        print("%s  %-42s  murphy: %-14s  truth: %s"
              % ("  OK " if ok else " MISS", name[:42],
                 "FOOLING ITSELF" if called else "sound",
                 "fooling" if fooling else "sound"))
        if spoke:
            print("        witnesses: %s"
                  % "; ".join("%s (%s)" % (k, WHY[k]) for k in dict.fromkeys(spoke)))
        elif called:
            print("        witnesses: none -- and it still ruled. that is a bug.")
        print("        circularity %.2f  unlooked %.2f"
              % (ev["circularity"], ev["unlooked"]))
        print("        %s\n" % note)

    # THE FLOOR FOR THE NEW WITNESSES THEMSELVES. A witness that speaks on everything
    # has no floor and proves nothing, which is the same disease Murphy was built to
    # find. So: on how many of these runs did each new witness open its mouth?
    print("the floor under the new witnesses -- a witness that speaks on every run is a")
    print("smoke alarm, not a witness:")
    for k in NEW:
        print("   %-12s spoke on %d of %d: %s"
              % (k, len(spoke_on[k]), len(CASES),
                 ", ".join(n[:28] for n in spoke_on[k]) or "nothing"))
    bad = [k for k in NEW if len(spoke_on[k]) in (0, len(CASES))]
    print()

    print("%d of %d." % (right, len(CASES)))
    if right < len(CASES):
        print("MURPHY IS NOT READY. He missed a real one, and a bug-finder that misses "
              "the bugs it was built from is decoration.")
    elif bad:
        print("MURPHY IS NOT READY. %s never discriminated: it spoke on all of these or "
              "on none, so it carries no information." % ", ".join(bad))
    else:
        print("He catches every real failure of that day and clears every real success, "
              "including the one that failed honestly and the one that was judged by "
              "his own eye and looked at anyway.")
    return 0 if (right == len(CASES) and not bad) else 1


if __name__ == "__main__":
    raise SystemExit(main())
