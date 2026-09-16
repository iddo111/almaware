"""GADAL — is the gap threshold just "pick a width" wearing a new coat?

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

The first full run on the MOREH decisions target halted growth on condition C -- the
train/val gap brake -- in 66 of 66 runs, and stopped at a mean width of 2.5 while the
fixed-size sweep's best held-out width was 48. So the whole policy came down to one
number, `gap_max`, which nobody measured.

Tuning gap_max until the answer looks good would be exactly the hindsight this track was
built to remove. So instead: sweep it, and PRINT THE CURVE. If held-out accuracy is flat
in gap_max, the brake is harmless and the mechanism is doing the work. If it is steep,
then "pick a width" has simply become "pick a gap threshold" and the honest report says
so in those words.

gap_max = inf disables condition C entirely, leaving A, B and D.
"""
from __future__ import annotations

import math
import os
import sys
import time

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..", "moreh")))

import bench_moreh as B                            # noqa: E402
from grow import Gardener                          # noqa: E402

GAPS = (0.15, 0.30, 0.60, 1.2, 3.0, 10.0, math.inf)


def main(target="decisions", seeds=3):
    B._be_polite()
    D = B.load(target)
    X, Y, M, g, H = D["X"], D["Y"], D["M"], D["g"], D["heads"]
    groups = np.unique(g)
    print(f"target {target}  gap_max sweep over {len(groups)} folds x {seeds} seeds")
    print(f"  {'gap_max':>8} {'test':>8} {'+-':>7} {'width':>7} {'grows':>6} {'epochs':>7} "
          f"{'halt reasons'}")
    t0 = time.time()
    for gm in GAPS:
        te, ws, ep, gr, why = [], [], [], [], {}
        for seed in range(seeds):
            for held in groups:
                rng = np.random.default_rng(1000 * seed + int(held))
                tem = g == held
                rest = np.array([u for u in groups if u != held])
                va = np.isin(g, rng.choice(rest, size=5, replace=False))
                tr = ~tem & ~va
                if target == "amounts":
                    Yz, _, _ = B.standardise(Y, M, tr)
                    Ms = M * B.certify(Y, M, g, tr)[None, :]
                else:
                    Yz, Ms = Y, M
                gd = Gardener(X.shape[1], Yz.shape[1], seed=seed, max_epochs=6000,
                              max_width=128, gap_max=gm)
                net, _ = gd.fit(X[tr], Yz[tr], Ms[tr], X[va], Yz[va], Ms[va], groups_tr=g[tr])
                te.append(B.score(net.forward(X[tem]), Yz[tem], Ms[tem], H))
                ws.append(net.widths[-1])
                ep.append(gd.log[-1]["epoch"])
                gr.append(sum(1 for r in gd.log if r["kind"] == "grow"))
                r = next((r["reason"] for r in gd.log if r["kind"] == "halt_growth"), "none")
                why[r] = why.get(r, 0) + 1
        m, c = B._ci(te)
        print(f"  {gm:>8} {m:>8.4f} {c:>7.4f} {np.mean(ws):>7.1f} {np.mean(gr):>6.1f} "
              f"{np.mean(ep):>7.0f} {why}")
    print(f"  ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "decisions",
         int(sys.argv[2]) if len(sys.argv) > 2 else 3)
