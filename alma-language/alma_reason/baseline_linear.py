# -*- coding: utf-8 -*-
"""THE VANILLA CONTROL. A plain linear model on exactly the same features.

    python -m alma_reason.baseline_linear --corpus syllogism --features raw

Why this file exists, in one sentence from someone else's mistake: the sibling
project (ALMA-GUARD-NET, B1) reported the same morning that its weave looked
12 points ahead of a vanilla control until the control was given the same
objective, at which point the gap collapsed to 3 — *"the win was the OBJECTIVE,
not the substrate"*. So the control here gets everything the weave gets: the
identical features, the identical train/test split, the identical
class-balanced diet, and the identical ±1 reward shape.

Two controls, both with no hidden layer at all:

  `perceptron`  the 1958 machine. sign(w·x); on a mistake, w += y·x.
  `logreg`      logistic regression by plain gradient descent.

If a two-layer weave trained by node perturbation cannot beat a perceptron on
this corpus, then the dialectic topology is decoration and the honest thing is
to say so. Reported either way.

There is a second reason to run the perceptron in particular. `encoding.py`
claims the syllogistic rules are not linearly separable even from the
distribution facts, because rule 4 — *a negative premise iff a negative
conclusion* — is a biconditional, an XNOR. A perceptron that cannot reach 100%
on the TRAINING half is that claim measured rather than asserted.
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from .build_dataset import (feature_names, load, stratified_split,  # noqa: E402
                            write as write_dataset, OUT)
from .encoding import SEAT_M, Argument                              # noqa: E402
from .train import Score, baseline_scores, balanced_stream          # noqa: E402


def _score(predict, items: list[Argument]) -> Score:
    s = Score(n=len(items), right=0)
    for a in items:
        got = SEAT_M if predict(a) else "Q"
        s.right += 1 if got == a.winner else 0
        if a.winner == SEAT_M:
            s.tp += got == SEAT_M
            s.fn += got != SEAT_M
        else:
            s.tn += got != SEAT_M
            s.fp += got == SEAT_M
    return s


def _fit(kind: str, tr: list[Argument], names: list[str], seed: int,
         epochs: int, eta: float) -> dict:
    rng = random.Random(seed)
    w = {n: rng.uniform(-0.1, 0.1) for n in names}
    b = 0.0

    def net(a: Argument) -> float:
        return b + sum(w[n] for n in a.features if n in w)

    for _ in range(epochs):
        for a in balanced_stream(tr, rng):      # the SAME diet the weave got
            y = 1.0 if a.winner == SEAT_M else -1.0
            z = net(a)
            if kind == "perceptron":
                if y * z <= 0:                  # Rosenblatt, 1958
                    for n in a.features:
                        if n in w:
                            w[n] += eta * y
                    b += eta * y
            else:                               # logistic, plain GD
                p = 1.0 / (1.0 + pow(2.718281828459045, -z))
                g = ((y + 1) / 2) - p
                for n in a.features:
                    if n in w:
                        w[n] += eta * g
                b += eta * g
    return {"w": w, "b": b, "net": net}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="syllogism")
    ap.add_argument("--features", default="raw")
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--eta", type=float, default=0.05)
    ap.add_argument("--json", default="")
    args = ap.parse_args(argv)

    if not OUT.exists():
        write_dataset()
    fs = args.features if args.corpus == "syllogism" else "machloket"
    items = load(corpus=args.corpus, feature_set=fs)
    names = feature_names(args.corpus, fs)
    tr, te = stratified_split(items)

    print(f"VANILLA CONTROL — {args.corpus}/{fs}: {len(items)} items, "
          f"{len(names)} features, train {len(tr)} / test {len(te)}")
    print(f"same split, same balanced diet, same ±1 target, NO hidden layer.")
    print()
    for name, s in baseline_scores(te).items():
        print("  " + s.line(name))
    print()

    out = {}
    for kind in ("perceptron", "logreg"):
        tests, trains = [], []
        for seed in range(args.seeds):
            m = _fit(kind, tr, names, seed, args.epochs, args.eta)
            pred = lambda a, m=m: m["net"](a) > 0
            st, sr = _score(pred, te), _score(pred, tr)
            tests.append(st.balanced)
            trains.append(sr.balanced)
        out[kind] = {"test_balanced_mean": statistics.mean(tests),
                     "test_balanced_min": min(tests),
                     "test_balanced_max": max(tests),
                     "train_balanced_mean": statistics.mean(trains),
                     "train_balanced_max": max(trains)}
        print(f"  {kind:11s} test balanced mean {statistics.mean(tests)*100:5.1f}% "
              f"(min {min(tests)*100:.1f}, max {max(tests)*100:.1f})   "
              f"TRAIN balanced mean {statistics.mean(trains)*100:5.1f}% "
              f"(max {max(trains)*100:.1f})")

    print()
    print("  The TRAIN column is the separability check. A linear model that")
    print("  cannot fit the training half is being stopped by the task, not by")
    print("  the sample size — which is what encoding.py claims about rule 4")
    print("  being a biconditional.")

    if args.json:
        Path(args.json).write_text(json.dumps(
            {"corpus": args.corpus, "feature_set": fs, "n_train": len(tr),
             "n_test": len(te), "epochs": args.epochs, "eta": args.eta,
             "models": out,
             "baselines": {k: {"balanced": v.balanced, "accuracy": v.accuracy}
                           for k, v in baseline_scores(te).items()}},
            ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  numbers -> {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
