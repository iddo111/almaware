#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""XOR over two feature buckets, inside the GUARD weave. FLEET ONLY (eran2).

    python3 -m alma_guard.v02_toy_xor --out out/toy_xor.json

The unit test `test_perturbation_learns_what_needs_a_hidden_layer` failed on the
PC three times (thresholds straddling zero -> positive; distractors -> none;
r_ok 1.0 -> 0.1). Instead of tuning a unit test by trial and error on the PC,
this measures the whole declared grid once on the fleet, both rules, every cell
printed. Whatever it says is what the unit test is allowed to assert.
"""
from __future__ import annotations

import argparse
import itertools
import json
import random
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from alma_guard.weave import GuardWeave, Hyper                     # noqa: E402

PATTERNS = {(0, 0): {}, (1, 0): {20: 1.0}, (0, 1): {21: 1.0}, (1, 1): {20: 1.0, 21: 1.0}}


def run(rule, seed, hidden, sigma, eta, epochs, drift=0.05):
    rows = [(f, "attack" if a != b else "benign") for (a, b), f in PATTERNS.items()] * 12
    g = GuardWeave(["attack"], Hyper(width=64, hidden=hidden, typical=2, rule=rule,
                                     skip=False, r_ok=0.1, r_miss=1.0, r_fa=1.0,
                                     drift=drift, sigma=sigma, eta=eta, seed=seed))
    rng = random.Random(seed + 1)
    order = list(range(len(rows)))
    for _ in range(epochs):
        rng.shuffle(order)
        for i in order:
            g.present(rows[i][0], rows[i][1], learn=True)
    right = sum(g.predict(f)[0] == ("attack" if a != b else "benign")
                for (a, b), f in PATTERNS.items())
    return right, g.moved


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    cells = []
    t0 = time.time()
    grid = itertools.product((4, 8), (0.3, 1.0, 2.0), (0.05, 0.2, 0.8), (60, 200))
    for hidden, sigma, eta, epochs in grid:
        for rule in ("perturbation",):
            res = [run(rule, s, hidden, sigma, eta, epochs) for s in range(args.seeds)]
            cells.append({"rule": rule, "hidden": hidden, "sigma": sigma, "eta": eta,
                          "epochs": epochs, "right": [r for r, _ in res],
                          "solved": sum(r == 4 for r, _ in res),
                          "mean_right": statistics.mean(r for r, _ in res)})
            print(json.dumps(cells[-1]), flush=True)
    for hidden, epochs in itertools.product((4, 8), (60, 200)):
        res = [run("three-factor", s, hidden, 0.0, 0.0, epochs) for s in range(args.seeds)]
        cells.append({"rule": "three-factor", "hidden": hidden, "epochs": epochs,
                      "right": [r for r, _ in res], "solved": sum(r == 4 for r, _ in res),
                      "mean_right": statistics.mean(r for r, _ in res)})
        print(json.dumps(cells[-1]), flush=True)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps({"cells": cells, "seeds": args.seeds,
                                          "secs": time.time() - t0}, indent=1),
                              encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
