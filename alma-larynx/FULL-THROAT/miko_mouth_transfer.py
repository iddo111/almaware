# -*- coding: utf-8 -*-
"""miko_mouth_transfer.py — the corrected experiment.

WHY THIS FILE EXISTS: the first run (miko_mouth.py, 2026-08-30 05:22) gave
random the win on 7 of 8 seeds at error 0.000. That is not evidence against
ThreeFactor — it is evidence that I MEASURED THE WRONG THING. Because every arm
kept a posture only if the ear liked it, the "random" arm was never random: it
was a random-mutation HILL CLIMBER, and in five smooth dimensions with a
reachable target, hill climbing simply solves the problem. There was nothing
left for a learner to contribute.

    (This is the exact failure PLAN.md already records once:
     "Iddo's correction stands: I measured the wrong thing.")

WHAT ACTUALLY MATTERS, AND WHAT IDDO ASKED FOR
----------------------------------------------
"אין לי בעיה לפתור את החידה אות אות" — letter by letter. The question is not
whether ONE posture can be found. Hill climbing finds one posture. The question
is whether the FIFTEENTH letter is cheaper than the first.

A hill climber cannot transfer — it has no memory between targets, by
construction. A learner that has built a proprioception→motor map should need
fewer trials each time. So the measurement is:

    TRIALS TO REACH THE TARGET, as a function of which target it is.

    flat   -> nothing was learned, and the hardware only needs a hill climber
    falling -> the map transferred, and proprioception is buying something real

Same body, same controls, same accept rule in every arm — only the question
changed.

    python miko_mouth_transfer.py
"""
from __future__ import annotations

import sys
import numpy as np
import torch

sys.path.insert(0, r"D:\CLAUDE\miko\model")
sys.path.insert(0, r"D:\CLAUDE\alma-larynx")
sys.path.insert(0, r"D:\CLAUDE\alma-larynx\FULL-THROAT")

from loop import ThreeFactor
from miko_mouth import (N_STATION, N_PROP, Mouth, err, formants,
                        proprioception)

TARGETS = 15         # the "letters", one after another
TRIALS = 50          # attempts allowed per target
THRESH = 0.10        # log-frequency distance the ear calls "that is the sound"
SEEDS = 6


def run(arm: str, seed: int) -> list[int]:
    rng = np.random.default_rng(seed)
    torch.manual_seed(seed)
    net = Mouth()
    tf = ThreeFactor(net, lr=6e-3, decay=0.85)
    params = {"W1": net.W1.data, "W2": net.W2.data}
    cost = []

    for k in range(TARGETS):
        target = formants(rng.uniform(0.1, 0.9, N_STATION))
        m = rng.uniform(0.2, 0.8, N_STATION)
        baseline = err(m, target)
        used = TRIALS                          # censored at TRIALS if never reached
        for t in range(TRIALS):
            if baseline <= THRESH:
                used = t
                break
            p = proprioception(m, rng)
            pt = torch.tensor(p, dtype=torch.float32).unsqueeze(0)
            with torch.no_grad():
                delta, h = net(pt)
            step = (rng.normal(0, 0.12, N_STATION) if arm == "random"
                    else delta.numpy()[0] * 0.12)
            cand = np.clip(m + step + rng.normal(0, 0.03, N_STATION), 0, 1)
            e = err(cand, target)

            if arm != "random":
                tf.observe(pt, h, "W1")
                tf.observe(h, delta, "W2")
                if arm == "miko":
                    signal = 1.0 if e < baseline else -1.0
                elif arm == "shuffled":
                    signal = 1.0 if rng.random() < 0.5 else -1.0
                else:
                    signal = 0.0
                tf.apply(signal, params)

            if e < baseline:
                m, baseline = cand, e
        cost.append(used)
    return cost


def main():
    arms = ["miko", "shuffled", "random"]
    out = {a: [] for a in arms}
    for seed in range(SEEDS):
        for a in arms:
            out[a].append(run(a, seed))
        print("  seed %d done" % seed, flush=True)

    print()
    print("DOES THE FIFTEENTH LETTER COST LESS THAN THE FIRST?")
    print("=" * 78)
    print("%d seeds  ·  %d targets in a row  ·  %d trials allowed each  ·  "
          "threshold %.2f" % (SEEDS, TARGETS, TRIALS, THRESH))
    print("-" * 78)
    print("%-10s %s" % ("arm", "  ".join("t%02d" % (k + 1) for k in range(TARGETS))))
    for a in arms:
        M = np.array(out[a])                       # seeds x targets
        med = np.median(M, axis=0)
        print("%-10s %s" % (a, "  ".join("%3.0f" % v for v in med)))
    print("-" * 78)
    print("%-10s %10s %10s %10s   %s" %
          ("arm", "first 5", "last 5", "change", "verdict"))
    for a in arms:
        M = np.array(out[a], dtype=float)
        first = M[:, :5].mean()
        last = M[:, -5:].mean()
        drop = (first - last) / first * 100 if first else 0.0
        verdict = ("LEARNED - later letters cost less" if drop > 15 else
                   "flat - nothing transferred" if abs(drop) <= 15 else
                   "GOT WORSE")
        print("%-10s %10.1f %10.1f %9.1f%%   %s" % (a, first, last, drop, verdict))
    print("=" * 78)
    np.save("miko_transfer.npy", np.array([out[a] for a in arms]))
    print("saved -> miko_transfer.npy")


if __name__ == "__main__":
    main()
