#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""THE VANILLA CONTROL. Standing rule, [[feedback_all_models_innovations]]:

    Iddo, 2026-07-02: "וגם תאמן מודל וונילה להשוות"
    - and if ours loses, say so.

Same rows. Same folds. Same features, bit for bit (`alma_guard.data`,
`alma_guard.encoding`). The ONLY thing that differs is what learns.

TWO CONTROLS, because "vanilla" can mean two honest things:

  perceptron   Rosenblatt 1958. Exactly parameter-matched to the weave - one
               weight per feature bucket plus a bias, per head - and the same
               family of update (an error-driven change to the weights of the
               features that were present). This is the sharp comparison: it
               isolates what the third factor and the eligibility trace add,
               because everything else is the same.
  logreg       Logistic regression by SGD with L2. Same parameter count, but a
               real gradient on a real loss. This is the "what would anyone
               normally do" bar, and it is the one ALMA has to be measured
               against honestly rather than the one it is likely to beat.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from alma_guard import data as D                                   # noqa: E402
from alma_guard import encoding as E                               # noqa: E402
from alma_guard.train import heads_for, label_of, report           # noqa: E402

HERE = Path(__file__).resolve().parent


class Linear:
    """One-vs-rest linear heads over sparse binary features. No numpy needed."""

    def __init__(self, heads: list[str], width: int, default: str, seed: int = 0):
        self.heads = list(heads)
        self.width = width
        self.default = default
        rng = random.Random(seed)
        self.w = [[rng.uniform(-0.02, 0.02) for _ in range(width)] for _ in heads]
        self.b = [rng.uniform(-0.02, 0.02) for _ in heads]

    def score(self, feats: dict[int, float], k: int) -> float:
        wk = self.w[k]
        return self.b[k] + sum(wk[i] for i in feats if 0 <= i < self.width)

    def predict(self, feats: dict[int, float]) -> str:
        best, bs = None, 0.0
        for k in range(len(self.heads)):
            s = self.score(feats, k)
            if s >= 0.0 and (best is None or s > bs):
                best, bs = k, s
        return self.default if best is None else self.heads[best]

    # ---- Rosenblatt 1958: update only on a mistake, only the present features
    #
    # `pos_weight` is the FAIRNESS KNOB. ALMA-GUARD is trained with asymmetric
    # pain (r_miss=4 vs r_fa=1: missing an attack hurts four times as much as a
    # false alarm), so comparing its recall against an unweighted control would
    # be comparing an objective, not a substrate. With pos_weight=4 the control
    # is told the same thing about the world. Reported both ways in RESULTS.md.
    def fit_perceptron(self, feats, labels, epochs, lr, seed=0, pos_weight=1.0):
        rng = random.Random(seed + 7)
        order = list(range(len(feats)))
        for _ in range(epochs):
            rng.shuffle(order)
            for j in order:
                f, y = feats[j], labels[j]
                for k, name in enumerate(self.heads):
                    want = 1.0 if y == name else 0.0
                    got = 1.0 if self.score(f, k) >= 0.0 else 0.0
                    if got == want:
                        continue
                    d = lr * (want - got) * (pos_weight if want else 1.0)
                    wk = self.w[k]
                    for i in f:
                        if 0 <= i < self.width:
                            wk[i] += d
                    self.b[k] += d

    # ---- logistic regression by SGD with L2
    def fit_logreg(self, feats, labels, epochs, lr, l2, seed=0, pos_weight=1.0):
        rng = random.Random(seed + 11)
        order = list(range(len(feats)))
        for ep in range(epochs):
            rng.shuffle(order)
            step = lr / (1.0 + ep * 0.1)
            for j in order:
                f, y = feats[j], labels[j]
                for k, name in enumerate(self.heads):
                    want = 1.0 if y == name else 0.0
                    z = self.score(f, k)
                    p = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))
                    g = step * (want - p) * (pos_weight if want else 1.0)
                    wk = self.w[k]
                    for i in f:
                        if 0 <= i < self.width:
                            wk[i] += g - step * l2 * wk[i]
                    self.b[k] += g


def cross_validate(rows, task, kind, width, epochs, lr, l2, k, seed, pos_weight=1.0):
    heads, default = heads_for(task)
    fs = D.folds(rows, k, seed=seed)
    feats = [E.features(r["text"], width) for r in rows]
    labels = [label_of(r, task) for r in rows]
    truth, pred, idx = [], [], []
    for f in range(k):
        te = fs[f]
        tr = [i for j, g in enumerate(fs) if j != f for i in g]
        m = Linear(heads, width, default, seed=seed)
        tf = [feats[i] for i in tr]
        tl = [labels[i] for i in tr]
        if kind == "perceptron":
            m.fit_perceptron(tf, tl, epochs, lr, seed, pos_weight)
        else:
            m.fit_logreg(tf, tl, epochs, lr, l2, seed, pos_weight)
        t = [labels[i] for i in te]
        p = [m.predict(feats[i]) for i in te]
        truth += t
        pred += p
        idx += te
        mm = D.metrics(t, p)
        print(f"  fold {f+1}/{k}  n={mm['n']:4d}  acc {mm['acc']:.3f}  "
              f"P {mm['precision']:.3f}  R {mm['recall']:.3f}  F1 {mm['f1']:.3f}",
              flush=True)
    return truth, pred, idx


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--task", choices=("binary", "multi"), default="binary")
    ap.add_argument("--kind", choices=("perceptron", "logreg", "both"), default="both")
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--width", type=int, default=2048)
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--lr", type=float, default=0.05)
    ap.add_argument("--l2", type=float, default=1e-4)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--pos-weight", type=float, default=1.0,
                    help="weight on the positive class, to match ALMA's r_miss/r_fa")
    ap.add_argument("--fresh", action="store_true",
                    help="also train on all rows and test on fresh.jsonl")
    ap.add_argument("--json-out", default="")
    args = ap.parse_args()

    rows = D.load()
    kinds = ("perceptron", "logreg") if args.kind == "both" else (args.kind,)
    out: dict = {"task": args.task, "rows": len(rows), "width": args.width}

    for kind in kinds:
        print(f"\nVANILLA CONTROL: {kind}   task={args.task}  width={args.width}  "
              f"epochs={args.epochs}  lr={args.lr}  pos_weight={args.pos_weight}"
              + (f"  l2={args.l2}" if kind == "logreg" else ""))
        truth, pred, idx = cross_validate(rows, args.task, kind, args.width,
                                          args.epochs, args.lr, args.l2,
                                          args.folds, args.seed, args.pos_weight)
        out[kind] = report(f"VANILLA {kind}  {args.folds}-fold cross-validation",
                           rows, truth, pred, idx, args.task)

        if args.fresh:
            heads, default = heads_for(args.task)
            m = Linear(heads, args.width, default, seed=args.seed)
            feats = [E.features(r["text"], args.width) for r in rows]
            labels = [label_of(r, args.task) for r in rows]
            if kind == "perceptron":
                m.fit_perceptron(feats, labels, args.epochs, args.lr, args.seed,
                                 args.pos_weight)
            else:
                m.fit_logreg(feats, labels, args.epochs, args.lr, args.l2,
                             args.seed, args.pos_weight)
            fresh = D.load(HERE / "fresh.jsonl")
            ft = [label_of(r, args.task) for r in fresh]
            fp = [m.predict(E.features(r["text"], args.width)) for r in fresh]
            out[kind + "_fresh"] = report(
                f"VANILLA {kind}  FRESH held-out payloads", fresh, ft, fp,
                list(range(len(fresh))), args.task)

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(out, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
