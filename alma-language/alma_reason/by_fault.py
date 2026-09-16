# -*- coding: utf-8 -*-
"""WHICH פירכא DOES IT LEARN TO SEE? A breakdown no single accuracy can show.

    python -m alma_reason.by_fault

There are five ways a syllogism can fall, and they are not one skill. An
undistributed middle is visible in the shape of two premises; a quality
mismatch is a biconditional between three propositions. A weave that has
learned to spot the first and is blind to the second has a real and nameable
level of understanding, and one number over the whole corpus hides it
completely.

Reported per fault, on the held-out half, with the count in each bucket beside
it — because "100% on two items" is not a skill either.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from alma import Loom                                              # noqa: E402

from .build_dataset import (feature_names, load, stratified_split,  # noqa: E402
                            write as write_dataset, OUT)
from .train import train                                            # noqa: E402
from .weave import DEFAULT_BEATS, conclude, seed_argument           # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", default="raw")
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--hidden", type=int, default=4)
    ap.add_argument("--sigma", type=float, default=1.0)
    ap.add_argument("--eta", type=float, default=0.03)
    ap.add_argument("--drift-out", type=float, default=0.0)
    ap.add_argument("--json", default="")
    args = ap.parse_args(argv)

    if not OUT.exists():
        write_dataset()
    items = load(corpus="syllogism", feature_set=args.features)
    names = feature_names("syllogism", args.features)
    typical = int(statistics.mean(len(a.features) for a in items)) + 1
    tr, te = stratified_split(items)

    right: dict[str, int] = defaultdict(int)
    total: dict[str, int] = defaultdict(int)
    for seed in range(args.seeds):
        r = train(tr, te, names, seed=seed, rule="perturbation",
                  epochs=args.epochs, hidden=args.hidden, beats=DEFAULT_BEATS,
                  sigma=args.sigma, eta=args.eta, drift_out=args.drift_out,
                  drift_in=0.0, scale=1.0, typical_present=typical)
        w, loom = r["weave"], Loom()
        for a in te:
            seed_argument(w, a)
            c = conclude(loom.run(w, beats=DEFAULT_BEATS, verdict=None),
                         DEFAULT_BEATS)
            bucket = a.meta.get("fault") or "VALID (no פירכא)"
            total[bucket] += 1
            right[bucket] += 1 if c.winner == a.winner else 0

    print(f"syllogism/{args.features}, held-out {len(te)} items x "
          f"{args.seeds} seeds, by why the syllogism falls:")
    print()
    rows = []
    for bucket in sorted(total, key=lambda b: -total[b]):
        acc = right[bucket] / total[bucket]
        n = total[bucket] // args.seeds
        rows.append({"fault": bucket, "n_items": n, "accuracy": acc})
        print(f"  {bucket:24s} {n:3d} items   caught {acc*100:5.1f}%")
    print()
    print("  A bucket with 2 or 3 items in it is a rumour, not a measurement.")
    if args.json:
        Path(args.json).write_text(
            json.dumps({"features": args.features, "seeds": args.seeds,
                        "n_test": len(te), "by_fault": rows},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  numbers -> {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
