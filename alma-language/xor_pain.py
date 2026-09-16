#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""כאב ועונג — PAIN AND PLEASURE. An ALMA weave learns XOR with no backpropagation.

    python xor_pain.py

WHY XOR AND NOT SOMETHING IMPRESSIVE
------------------------------------
Because XOR is the exact thing Minsky and Papert proved a perceptron cannot learn
(Perceptrons, 1969) — the proof that ended Rosenblatt's line of work and, with it,
the first age of neural networks. Rosenblatt died two years later. Iddo named both
men tonight, 2026-09-10 00:18, before naming what was missing.

So this is not a toy chosen because it is easy. It is the specific claim being
answered, with the specific thing the 1958 machine did not have.

WHAT IS AND IS NOT GIVEN TO THE WEAVE
-------------------------------------
GIVEN:    the shape — two inputs, four hidden knots that fire on a threshold, one
          output. Every network is given its shape; that is not the cheat.
GIVEN:    the thresholds (`rise`), because in ALMA a trigger is structure, not a weight.
NOT GIVEN: every cord's weight. They start random and small. Nothing is hand-tuned,
          and no line of this file knows what XOR is except `TRUTH` below and the
          one comparison in `world()`.
NOT GIVEN: any gradient. Nothing travels backwards. The loom only moves forward,
          because ALMA's first law says every delay is at least one beat.

THE RULE THAT DOES THE LEARNING (alma/loom.py, step 3 and 3b)
------------------------------------------------------------
    a cord's spark lands, and its knot fires  ->  the cord becomes eligible, positively
    a cord's spark lands, and its knot is silent -> eligible, negatively, at a quarter
    THEN the world answers, once, with one number:
        pleasure (+)  ->  what fired together is pulled TOGETHER
        pain     (-)  ->  what fired together is pulled APART

That reversal is the whole difference. Two-factor Hebb can only agree with itself; it
has no way to be wrong. The third factor is what makes being wrong cost something —
and Iddo's argument for why it may be internal is the right one (2026-09-10 00:46):
"תיזכר בדוגמא ששברתי את הרגל - הכאב הוא מנגנון הלמידה העצמית". Your cortex does not
decide how much your leg hurts. The signal is inside the body and caused by physics,
and the part that is learning cannot switch it off. Here, `world()` is that physics:
it reads only what the weave actually did, and the weave has no cord that reaches it.

WHERE THIS STANDS, 2026-09-10 01:30 — MEASURED, AND IT DOES NOT SOLVE XOR YET
-----------------------------------------------------------------------------
Reported honestly because a number nobody checked is how the last six days were
lost. Across 8 random starts x 300 trials: scores MOVE (2->3, 3->2, 4->2) and the
weights change measurably (total |dw| = 1.58 over 30 trials), but **0/8 starts
reach 4/4**, and at the larger weight scale training makes some starts WORSE.

WHAT IS PROVEN:
  * the third factor is wired and it works — a verdict reaches every eligible cord,
    pain reverses the Hebbian sign, and the weave rewrites itself while it runs.
  * `verdict=None` is v0.2 exactly: all 154 tests pass, byte-identical.
  * at the OUTPUT knot the rule is a correct reward-modulated perceptron.

WHAT IS NOT, AND WHY — this is the real finding, not a tuning problem:
  **The hidden knots have no credit assignment.** The verdict is ONE global scalar,
  so every hidden cord that took part gets the same sign on the same beat. Nothing
  tells h0 "you should have fired" while telling h1 "you should not have". A hidden
  layer cannot differentiate under a rule that cannot address it — which is, exactly,
  Minsky and Papert's objection, and exactly what backpropagation was invented to
  answer. Three-factor Hebb solves the last layer. It does not, alone, solve the ones
  before it.

THE TWO NAMED WAYS FORWARD, neither of which needs anything to travel backwards:
  1. NODE PERTURBATION. Give each hidden knot its own small random jitter each trial
     and let the verdict correlate with THAT. The noise is private to the knot, so the
     credit becomes private too. It is a real gradient estimator and it stays local.
  2. FEEDBACK ALIGNMENT (Lillicrap et al. 2016). A random cord from `out` back to each
     hidden knot. In ALMA a cycle is legal and costs one beat — so "feedback" here is
     not a gradient flowing backwards through the computation, it is a real cord
     carrying a real spark forward in time. The language already permits it.

TWO BUGS THIS FILE FOUND BY BEING RUN, both worth keeping written down:
  * THE MEASUREMENT LIED FIRST. `score()` read whether `out` fired from the verdict
    callback — but with learning off there IS no verdict, so the callback never ran and
    the answer was always "silent". Every configuration scored exactly 2/4. A constant
    result across wildly different settings is the signature of a broken measurement,
    not a failed idea. It now reads `Result.fires`.
  * THE BIAS ARRIVED EARLY. The `one -> out` cord had delay 1 while the path through the
    hidden layer has length 2, so the bias fired `out` on beat 2 — before any thinking
    reached it — and the tray drained. The fix is the language's own third law: the bias
    cord must be the same DISTANCE from the output as the hidden path, delay 2. In VR
    you would have seen it: the rope was too short.

MEASURED 2026-09-11 (v0.6, `--rule perturbation`, alma/perturb.py) - ON ERAN2, NOT THE PC
------------------------------------------------------------------------------------------
20 starts x 200 trials per cell. Three-factor alone: 0/20 solved, and the 3 starts that began at 3/4
all end at 2/4. Node perturbation on the four hidden knots, a declared 9-cell grid (sigma 0.25/0.5/1.0
x eta 0.02/0.05/0.1): 6 of 180 starts solve XOR [corrected 20:10, first written as 9] (best cells 2/20), and many more end at 3/4 (up to
13/20). Per-knot credit moves the weave off the 2/4 plateau; in this weave, at this budget, it does
not reliably solve XOR. Raw: alma_guard/results_v02/xor/. The SAME rule inside the guard weave
(0/1 presence coding, 8 hidden knots, 200 epochs) solves it 8/8 - but so does three-factor there
(7/8), so that toy does not isolate perturbation. Said plainly, both halves.
"""
import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from alma import Loom, Weave                                        # noqa: E402
from alma.loom import Strand, Thread                                # noqa: E402
from alma.perturb import NodePerturbation                           # noqa: E402

TRUTH = {(0, 0): 0, (0, 1): 1, (1, 0): 1, (1, 1): 0}    # the only place XOR is written

HIDDEN = 4          # four threshold knots; XOR needs at least two, four gives slack
DRIFT = 0.06        # how eligible one landing makes a cord
OUT_BEAT = 4        # inputs land on 1, hidden speak on 2, out speaks on 3; judge on 4


def build(rng, hidden_drift=DRIFT):
    """The shape. Every weight is random; nothing here knows what XOR is.

    `hidden_drift` is the drift of the input -> hidden cords. It is DRIFT for the
    three-factor rule (v0.5) and 0.0 when node perturbation owns that layer
    (v0.6, alma/perturb.py), so the two rules never both act on one cord.
    The random draws happen in the same order either way."""
    w = Weave("xor")
    w.knot("a", verb="pass", trigger="any")
    w.knot("b", verb="pass", trigger="any")
    # A knot that always speaks 1. Without it the pattern (0,0) puts NOTHING into the
    # weave -- 0 times any weight is 0 -- so the weave cannot even tell that a question
    # was asked, and there is nothing for a verdict to land on. Found by running it.
    w.knot("one", verb="pass", trigger="any")
    # Hidden knots: `sum` gathers what lands, `rise T` fires only if it reaches T.
    # Two of them lean low (an OR-ish line) and two lean high (an AND-ish line). The
    # weave is NOT told which is which -- the thresholds only give it two different
    # places to stand, and the verdict decides what each becomes.
    for i in range(HIDDEN):
        w.knot(f"h{i}", verb="sum", trigger=f"rise {0.5 if i < HIDDEN // 2 else 1.5}")
    w.knot("out", verb="sum", trigger="rise 0.0")
    w.knot("say", verb="fringe", trigger="any")

    def cord(drift=DRIFT):
        return Strand(weight=rng.uniform(-1.0, 1.0), delay=1, drift=drift)

    for src in ("a", "b", "one"):
        for i in range(HIDDEN):
            w.threads.append(Thread(src, f"h{i}", "in", [cord(hidden_drift)]))
    for i in range(HIDDEN):
        w.threads.append(Thread(f"h{i}", "out", "in", [cord()]))
    # The output's own bias, at delay 2 -- the SAME distance from `out` as the path
    # through the hidden layer. At delay 1 it arrived a beat early and decided the
    # answer before any thinking got there. Third law: the layout is the program.
    w.threads.append(Thread("one", "out", "in",
                            [Strand(weight=rng.uniform(-1.0, 1.0), delay=2, drift=DRIFT)]))
    w.threads.append(Thread("out", "say", "in", [Strand(weight=1.0, delay=1)]))
    w.run_hint = 8
    return w


def weights(weave):
    return [st for t in weave.threads for st in t.strands]


def present(loom, weave, pattern, learn=True, perturber=None):
    """One trial: seed the pattern, run, see whether `out` spoke, be judged.

    The verdict is a closure over what the weave DID this run. It cannot be reached
    by any cord -- there is no thread into it -- which is the point: the learner
    does not get to decide whether it was right.
    """
    weave.seeds = []
    a, b = pattern
    # -1 / +1, not 0 / 1. A zero spark carries no information through a weight, so a
    # 0-coded input is indistinguishable from an input that was never asked.
    weave.seed("a", 1.0 if a else -1.0, beat=1)
    weave.seed("b", 1.0 if b else -1.0, beat=1)
    weave.seed("one", 1.0, beat=1)
    if learn and perturber is not None:
        perturber.jitter(weave)               # v0.6: private noise into each hidden tray

    spoke = {"fired": False}

    def world(beat, fires_this_beat):
        """The world. It reads only what the weave DID; no cord reaches in here."""
        if fires_this_beat is None:
            # The last word: the run is over. Now, and only now, judge.
            want_fire = TRUTH[pattern] == 1
            # This is the entire error signal of this program: one number, +1 or -1.
            return 1.0 if spoke["fired"] == want_fire else -1.0
        for f in fires_this_beat:
            if f.knot == "out":
                spoke["fired"] = True
        return None                           # never judge mid-episode

    r = loom.run(weave, beats=8, verdict=world if learn else None)
    if learn and r.learned is not None:
        for st, nw in zip(weights(weave), r.learned):
            st.weight = nw                    # the loom keeps the weave pure; we write back
    if learn and perturber is not None:
        fired = any(f.knot == "out" for f in r.fires)
        perturber.credit(weave, r, 1.0 if fired == (TRUTH[pattern] == 1) else -1.0)
    # Read what the RUN did, never what the callback saw: with learning off there is no
    # verdict, so `world` is never called and `spoke` would be a lie. See the header.
    return any(f.knot == "out" for f in r.fires)


def score(loom, weave):
    """Test all four patterns with learning OFF. This is the real output."""
    right = 0
    got = {}
    for p in TRUTH:
        fired = present(loom, weave, p, learn=False)
        got[p] = 1 if fired else 0
        right += 1 if got[p] == TRUTH[p] else 0
    return right, got


def train(seed, trials, verbose=False, rule="three-factor", sigma=0.5, eta=0.05):
    rng = random.Random(seed)
    loom = Loom()
    weave = build(rng, hidden_drift=0.0 if rule == "perturbation" else DRIFT)
    perturber = None
    if rule == "perturbation":
        # its own noise stream, so the presentation order is the same as v0.5's
        perturber = NodePerturbation([f"h{i}" for i in range(HIDDEN)], sigma=sigma,
                                     eta=eta, beat=2, rng=random.Random(seed + 7919))
    before, _ = score(loom, weave)
    order = list(TRUTH)
    for t in range(trials):
        rng.shuffle(order)
        for p in order:
            present(loom, weave, p, learn=True, perturber=perturber)
        if verbose and (t + 1) % 20 == 0:
            s, _ = score(loom, weave)
            print(f"    trial {t+1:4d}   {s}/4")
    after, got = score(loom, weave)
    return before, after, got, weave


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=20, help="independent random starts")
    ap.add_argument("--trials", type=int, default=200, help="passes over the 4 patterns")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--rule", choices=("three-factor", "perturbation"),
                    default="three-factor",
                    help="v0.5 pain-and-pleasure everywhere, or v0.6 node perturbation "
                         "on the hidden layer (alma/perturb.py)")
    ap.add_argument("--sigma", type=float, default=0.5)
    ap.add_argument("--eta", type=float, default=0.05)
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    print("כאב ועונג — PAIN AND PLEASURE")
    print("An ALMA weave learns XOR. No backpropagation. Nothing travels backwards.\n")
    print(f"{HIDDEN} hidden knots, all weights random in [-1,1], drift {DRIFT}.")
    print(f"{args.seeds} independent starts x {args.trials} trials.\n")

    solved = 0
    firsts = []
    for s in range(args.seeds):
        before, after, got, weave = train(s, args.trials, args.verbose and s == 0,
                                          args.rule, args.sigma, args.eta)
        ok = after == 4
        solved += 1 if ok else 0
        if ok:
            firsts.append(s)
        print(f"  seed {s:3d}   before {before}/4   after {after}/4   "
              f"{'SOLVED' if ok else ''}")

    if args.json:
        import json
        Path(args.json).write_text(json.dumps({"rule": args.rule, "sigma": args.sigma,
            "eta": args.eta, "seeds": args.seeds, "trials": args.trials,
            "solved": solved, "solved_seeds": firsts}), encoding="utf-8")
    print(f"\n[{args.rule}] {solved}/{args.seeds} starts learned XOR "
          f"({100.0*solved/max(1,args.seeds):.0f}%)")

    if firsts:
        s = firsts[0]
        _, _, got, weave = train(s, args.trials, False, args.rule, args.sigma, args.eta)
        print(f"\nThe truth table a solved weave (seed {s}) actually speaks:")
        for p in sorted(TRUTH):
            print(f"    {p[0]} xor {p[1]} = {got[p]}   (want {TRUTH[p]})"
                  f"   {'ok' if got[p]==TRUTH[p] else '<-- WRONG'}")
    return 0 if solved else 1


if __name__ == "__main__":
    sys.exit(main())
