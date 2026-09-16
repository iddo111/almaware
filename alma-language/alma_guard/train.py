#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Train ALMA-GUARD. On the fleet, never on the PC.

    python -m alma_guard.train --task binary --folds 5
    python -m alma_guard.train --task multi  --folds 5 --width 4096
    python -m alma_guard.train --task binary --final        # train on all, save, test on fresh.jsonl

WHAT DOES THE LEARNING
----------------------
Nothing in this file. The learning is `alma/loom.py` steps 3 and 3b - a cord
becomes eligible when its spark lands, positively if its knot then spoke and
negatively at a quarter if it did not, and a scalar verdict from the world spends
that trace forward in time. This file only presents messages and answers.

The verdict closure lives in `weave.py::GuardWeave.present` and it can read only
what the weave DID. No cord reaches into it.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from alma_guard import data as D                                   # noqa: E402
from alma_guard import encoding as E                               # noqa: E402
from alma_guard.weave import GuardWeave, Hyper                     # noqa: E402

HERE = Path(__file__).resolve().parent


def heads_for(task: str) -> tuple[list[str], str]:
    if task == "binary":
        return [D.ATTACK], D.BENIGN
    return list(D.CLASSES), D.BENIGN


def label_of(row: dict, task: str) -> str:
    return D.binarise(row["label"]) if task == "binary" else row["label"]


def run_split(rows, tr_idx, te_idx, task, hyper, quiet=True):
    heads, default = heads_for(task)
    g = GuardWeave(heads, hyper, default=default)
    feats = {i: E.features(rows[i]["text"], hyper.width) for i in set(tr_idx) | set(te_idx)}
    rng = random.Random(hyper.seed + 1)
    order = list(tr_idx)
    for ep in range(hyper.epochs):
        rng.shuffle(order)
        for i in order:
            g.present(feats[i], label_of(rows[i], task), learn=True)
        if not quiet and (ep + 1) % 5 == 0:
            t = [label_of(rows[i], task) for i in te_idx]
            p = [g.predict(feats[i])[0] for i in te_idx]
            print(f"    epoch {ep+1:3d}  test acc {D.metrics(t, p)['acc']:.3f}",
                  flush=True)
    truth = [label_of(rows[i], task) for i in te_idx]
    pred = [g.predict(feats[i])[0] for i in te_idx]
    return g, truth, pred


def cross_validate(rows, task, hyper, k, verbose=False):
    fs = D.folds(rows, k, seed=hyper.seed)
    all_truth, all_pred, all_idx = [], [], []
    for f in range(k):
        te = fs[f]
        tr = [i for j, g in enumerate(fs) if j != f for i in g]
        t0 = time.time()
        _, truth, pred = run_split(rows, tr, te, task, hyper, quiet=not verbose)
        all_truth += truth
        all_pred += pred
        all_idx += te
        m = D.metrics(truth, pred)
        print(f"  fold {f+1}/{k}  n={m['n']:4d}  acc {m['acc']:.3f}  "
              f"P {m['precision']:.3f}  R {m['recall']:.3f}  F1 {m['f1']:.3f}"
              f"   ({time.time()-t0:.0f}s)", flush=True)
    return all_truth, all_pred, all_idx


def report(name, rows, truth, pred, idx, task):
    m = D.metrics(truth, pred)
    print(f"\n{name}")
    print(f"  n={m['n']}  accuracy {m['acc']:.4f}   "
          f"(majority baseline {D.majority_baseline(truth):.4f})")
    print(f"  attack precision {m['precision']:.4f}  recall {m['recall']:.4f}  "
          f"F1 {m['f1']:.4f}   tp={m['tp']} fp={m['fp']} fn={m['fn']}")
    if idx:
        print("  by source: " + ", ".join(
            f"{s}={v['acc']:.3f}(n={v['n']})"
            for s, v in D.per_source(rows, idx, truth, pred).items()))
    labels = [D.BENIGN, D.ATTACK] if task == "binary" else D.CLASSES
    print("  confusion (rows = truth):")
    print("   " + D.confusion(truth, pred, labels).replace("\n", "\n   "))
    return m


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--task", choices=("binary", "multi"), default="binary")
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--width", type=int, default=2048)
    ap.add_argument("--drift", type=float, default=0.05)
    ap.add_argument("--init", type=float, default=0.02)
    ap.add_argument("--r-ok", type=float, default=0.10)
    ap.add_argument("--r-miss", type=float, default=4.0)
    ap.add_argument("--r-fa", type=float, default=1.0)
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--final", action="store_true",
                    help="train on every row, save the model, test on fresh.jsonl")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--json-out", default="")
    args = ap.parse_args()

    hyper = Hyper(width=args.width, drift=args.drift, init=args.init,
                  r_ok=args.r_ok, r_miss=args.r_miss, r_fa=args.r_fa,
                  epochs=args.epochs, seed=args.seed)
    rows = D.load()
    print(f"ALMA-GUARD  task={args.task}  rows={len(rows)}")
    print(f"  {hyper.line()}\n")

    out: dict = {"task": args.task, "hyper": hyper.__dict__, "rows": len(rows)}

    if not args.final:
        truth, pred, idx = cross_validate(rows, args.task, hyper, args.folds,
                                          args.verbose)
        out["cv"] = report(f"ALMA-GUARD  {args.folds}-fold cross-validation",
                           rows, truth, pred, idx, args.task)
    else:
        allidx = list(range(len(rows)))
        t0 = time.time()
        g, _, _ = run_split(rows, allidx, allidx[:1], args.task, hyper,
                            quiet=not args.verbose)
        print(f"  trained on all {len(rows)} rows in {time.time()-t0:.0f}s")
        model = {"task": args.task, "hyper": hyper.__dict__,
                 "heads": g.heads, "default": g.default,
                 "weights": g.weights()}
        mp = HERE / f"model_{args.task}.json"
        mp.write_text(json.dumps(model), encoding="utf-8")
        print(f"  saved {mp}")

        fresh = D.load(HERE / "fresh.jsonl")
        ft = [label_of(r, args.task) for r in fresh]
        fp = [g.predict(E.features(r["text"], hyper.width))[0] for r in fresh]
        out["fresh"] = report("ALMA-GUARD  FRESH held-out payloads (never trained on)",
                              fresh, ft, fp, list(range(len(fresh))), args.task)
        for r, t, p in zip(fresh, ft, fp):
            print(f"    {'ok ' if t == p else 'MISS'}  want {t:20s} got {p:20s} "
                  f"| {r['text'][:64]}")

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(out, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
