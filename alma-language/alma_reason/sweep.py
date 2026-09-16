# -*- coding: utf-8 -*-
"""Choose the settings WITHOUT looking at the test half. Then look, once.

    python -m alma_reason.sweep --corpus syllogism --features raw

The held-out 30% from `build_dataset.stratified_split` is not touched here at
all. This carves a further 25% off the TRAINING half as a validation set,
sweeps a small declared grid on that, and prints the whole grid — every cell,
not the winner — so there is nothing to cherry-pick after the fact. Then it
retrains the best-on-validation configuration on the full training half and
reports the test half once.

That order matters more than the numbers. A balanced accuracy chosen by trying
settings until the test half looked good is not a measurement of anything.
"""
from __future__ import annotations

import argparse
import itertools
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from .build_dataset import (feature_names, load, stratified_split,  # noqa: E402
                            write as write_dataset, OUT)
from .train import baseline_scores, shuffled, train                 # noqa: E402
from .weave import DEFAULT_BEATS                                    # noqa: E402

# THE GRID DEPENDS ON THE RULE, and that was a correction, not a refinement.
# The first version swept one grid for both rules: eta, sigma, hidden, drift_out,
# with drift_in pinned to 0. For node perturbation that is right — eta and sigma
# ARE its knobs and drift_in belongs to the other rule. For THREE-FACTOR it is
# nonsense: eta and sigma do nothing, and with drift_in pinned at 0 the cell
# drift_out=0 has no plastic cord anywhere in the weave. The sweep duly chose
# that cell (it validated as well as any other, all of them being noise), and
# the three-factor arm reported 51.2% with |dw| = 0.0 on every seed — a rule
# that had not run being scored against a rule that had. The |dw| column is what
# caught it; `train()` now refuses such a configuration outright.
GRIDS = {
    "perturbation": {
        "eta": (0.01, 0.03, 0.08),
        "sigma": (0.3, 0.6, 1.0),
        "hidden": (4, 8),
        "drift_out": (0.0, 0.03),
        "drift_in": (0.0,),
    },
    "three-factor": {
        "drift_in": (0.02, 0.05, 0.10),
        "drift_out": (0.02, 0.05, 0.10),
        "hidden": (4, 8),
        "eta": (0.0,),
        "sigma": (0.0,),
    },
    "none": {"hidden": (4,), "eta": (0.0,), "sigma": (0.0,),
             "drift_in": (0.0,), "drift_out": (0.0,)},
}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="syllogism")
    ap.add_argument("--features", default="raw")
    ap.add_argument("--rule", default="perturbation")
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--final-epochs", type=int, default=0,
                    help="epochs for the final full-train run (default: --epochs)")
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--final-seeds", type=int, default=8)
    ap.add_argument("--beats", type=int, default=DEFAULT_BEATS)
    ap.add_argument("--json", default="")
    args = ap.parse_args(argv)

    if not OUT.exists():
        write_dataset()
    fs = args.features if args.corpus == "syllogism" else "machloket"
    items = load(corpus=args.corpus, feature_set=fs)
    names = feature_names(args.corpus, fs)
    typical = int(statistics.mean(len(a.features) for a in items)) + 1
    train_all, test = stratified_split(items)
    # a second, independent cut of the TRAINING half only
    tr, val = stratified_split(train_all, seed=424242, test_fraction=0.25)

    print(f"{args.corpus}/{fs}  rule={args.rule}  {len(items)} items, "
          f"{len(names)} features")
    print(f"train {len(tr)}   validation {len(val)}   test {len(test)} "
          f"(UNTOUCHED until the last line)")
    print()

    grid = GRIDS[args.rule]
    keys = sorted(grid)
    cells, t0 = [], time.time()
    for combo in itertools.product(*(grid[k] for k in keys)):
        cfg = dict(zip(keys, combo))
        vals, moved = [], []
        for seed in range(args.seeds):
            r = train(tr, val, names, seed=seed, rule=args.rule,
                      epochs=args.epochs, hidden=cfg["hidden"], beats=args.beats,
                      sigma=cfg["sigma"], eta=cfg["eta"],
                      drift_out=cfg["drift_out"], drift_in=cfg["drift_in"],
                      scale=1.0, typical_present=typical)
            vals.append(r["after_test"].balanced)
            moved.append(r["moved"])
        cell = {**cfg, "val_balanced": statistics.mean(vals),
                "val_min": min(vals), "val_max": max(vals),
                "moved": statistics.mean(moved)}
        cells.append(cell)
        # |dw| is printed on every line on purpose. A cell that scores fine with
        # |dw| = 0 has not learned anything; it has been lucky, and it is the
        # only kind of result that looks exactly like success.
        print("  " + "  ".join(f"{k}={cfg[k]}" for k in keys) +
              f"   -> validation balanced {cell['val_balanced']*100:5.1f}% "
              f"(min {cell['val_min']*100:.1f}, max {cell['val_max']*100:.1f})"
              f"   |dw| {cell['moved']:8.1f}")

    cells.sort(key=lambda c: -c["val_balanced"])
    best = cells[0]
    print()
    print("  BEST ON VALIDATION: " + "  ".join(f"{k}={best[k]}" for k in keys) +
          f"   {best['val_balanced']*100:.1f}%")
    print(f"  grid of {len(cells)} cells x {args.seeds} seeds in "
          f"{time.time()-t0:.0f}s")
    print()

    final_epochs = args.final_epochs or args.epochs
    print(f"  retraining on the FULL training half ({len(train_all)} items), "
          f"{args.final_seeds} seeds, {final_epochs} epochs, then the test half:")
    print()
    for name, s in baseline_scores(test).items():
        print("    " + s.line(name))
    print()

    finals, shuffles = [], []
    for seed in range(args.final_seeds):
        r = train(train_all, test, names, seed=seed, rule=args.rule,
                  epochs=final_epochs, hidden=best["hidden"], beats=args.beats,
                  sigma=best["sigma"], eta=best["eta"],
                  drift_out=best["drift_out"], drift_in=best["drift_in"],
                  scale=1.0, typical_present=typical)
        finals.append(r)
        print(f"    seed {seed:2d}   test balanced "
              f"{r['before_test'].balanced*100:5.1f}% -> "
              f"{r['after_test'].balanced*100:5.1f}%   "
              f"raw {r['after_test'].accuracy*100:5.1f}%   "
              f"train {r['after_train'].balanced*100:5.1f}%   "
              f"|dw| {r['moved']:8.1f}")

    print()
    print("    CONTROL — the same weave trained on SHUFFLED verdicts,")
    print("    A DIFFERENT SHUFFLE EACH RUN (one fixed shuffle is not a control:")
    print("    on the 20-item machloket corpus, shuffle seed 99 left 70% of the")
    print("    verdicts where they were, and the 'control' scored 100%):")
    for seed in range(args.final_seeds):
        sh = shuffled(train_all, seed=1000 + seed)
        kept = sum(1 for a, b in zip(train_all, sh) if a.winner == b.winner)
        r = train(sh, test, names, seed=seed, rule=args.rule,
                  epochs=final_epochs, hidden=best["hidden"], beats=args.beats,
                  sigma=best["sigma"], eta=best["eta"],
                  drift_out=best["drift_out"], drift_in=best["drift_in"],
                  scale=1.0, typical_present=typical)
        shuffles.append(r)
        print(f"    seed {seed:2d}   test balanced "
              f"{r['before_test'].balanced*100:5.1f}% -> "
              f"{r['after_test'].balanced*100:5.1f}%"
              f"   (that shuffle kept {kept}/{len(train_all)} verdicts in place)")

    before = [r["before_test"].balanced for r in finals]
    after = [r["after_test"].balanced for r in finals]
    sh_after = [r["after_test"].balanced for r in shuffles]
    print()
    print(f"  UNTRAINED      test balanced  mean {statistics.mean(before)*100:5.1f}%")
    print(f"  TRAINED        test balanced  mean {statistics.mean(after)*100:5.1f}%"
          f"   (min {min(after)*100:.1f}, max {max(after)*100:.1f})")
    print(f"  SHUFFLED-LABEL test balanced  mean "
          f"{statistics.mean(sh_after)*100:5.1f}%   <- must be near chance")

    if args.json:
        Path(args.json).write_text(json.dumps({
            "corpus": args.corpus, "feature_set": fs, "rule": args.rule,
            "n_items": len(items), "n_features": len(names),
            "n_train": len(train_all), "n_val": len(val), "n_test": len(test),
            "epochs": final_epochs, "grid": cells, "best": best,
            "baselines": {k: {"balanced": v.balanced, "accuracy": v.accuracy}
                          for k, v in baseline_scores(test).items()},
            "final": [{"seed": r["seed"],
                       "before_test_balanced": r["before_test"].balanced,
                       "after_test_balanced": r["after_test"].balanced,
                       "after_test_accuracy": r["after_test"].accuracy,
                       "after_train_balanced": r["after_train"].balanced,
                       "moved": r["moved"]} for r in finals],
            "shuffled_control": [r["after_test"].balanced for r in shuffles],
            "untrained_mean": statistics.mean(before),
            "trained_mean": statistics.mean(after),
            "shuffled_mean": statistics.mean(sh_after),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  numbers -> {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
