"""Choose the predictive learner's hyperparameters without touching held-out.

Selection protocol, identical in spirit to feature_bakeoff.py --cv: the codebook
is trained on the audio of `corpus-combined/train`, then scored by
leave-one-base-rendering-out over the 396 train items.  A whole vocoder
rendering leaves together, so augmentation twins cannot cross a fold boundary.
The held-out split is not opened by this file.

The sweep is coordinate-wise from one centre rather than a grid, because a grid
over five axes at four ants each is hours of CPU for a number that is going to
be read as "is beta > 0 worth anything".  Every configuration is run on all four
ants with their real seeds, so no row is a single lucky draw.

    py -3.13 sweep_predictive.py
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

import predictive_units as P
import run_predictive as R
import sequence_probes as sp
from colony import DEFAULT_ANTS, DEFAULT_SEEDS

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "state-hebbian" / "predictive" / "sweep.json"
FEATURE = "mfcc20_mel26_pd6w4"

CENTRE = {"beta": 1.0, "delta": 3, "rounds": 12, "candidates": 8,
          "negatives": 256, "tau": 1.0, "ridge": 1.0, "max_pairs": None,
          "predictor": "linear"}

AXES = (
    ("beta", [0.0, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0]),
    ("delta", [1, 2, 3, 5, 8]),
    ("tau", [0.25, 0.5, 1.0, 2.0, 4.0]),
    ("candidates", [4, 8, 16]),
    ("negatives", [64, 256, 1024]),
    ("rounds", [4, 8, 12, 20]),
    ("predictor", ["linear", "constant"]),
)


def run(corpus: P.FrameCorpus, train: list, classes: list[str], units: int,
        cfg: dict) -> dict:
    per_ant = []
    t0 = time.time()
    for ant, seed in zip(DEFAULT_ANTS, DEFAULT_SEEDS):
        book = P.fit(corpus, units, seed, **cfg)
        row = R.cross_validate(train, book, FEATURE, classes)
        row["ant"] = ant
        row["final_infonce_nats"] = book.history[-1]["mean_infonce_nats"]
        row["chance_infonce_nats"] = book.history[-1]["chance_infonce_nats"]
        per_ant.append(row)
    return {
        "config": dict(cfg), "units": units,
        "top1": float(np.mean([r["top1"] for r in per_ant])),
        "top1_std_over_ants": float(np.std([r["top1"] for r in per_ant])),
        "ba_pa": float(np.mean([r["minimal_pairs"].get("ba/pa", 0) for r in per_ant])),
        "da_ta": float(np.mean([r["minimal_pairs"].get("da/ta", 0) for r in per_ant])),
        "all_pairs": float(np.mean([r["all_pairs_pooled"] for r in per_ant])),
        "dead_units": float(np.mean([r["dead_units_train"] for r in per_ant])),
        "infonce_nats": float(np.mean([r["final_infonce_nats"] for r in per_ant])),
        "chance_infonce_nats": per_ant[0]["chance_infonce_nats"],
        "seconds": round(time.time() - t0, 1),
        "ants": per_ant,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--units", type=int, default=256)
    parser.add_argument("--out", default=str(OUT))
    parser.add_argument("--axes", default="", help="comma-separated subset")
    parser.add_argument("--centre", default="{}",
                        help="JSON overriding the centre configuration")
    args = parser.parse_args()

    centre = dict(CENTRE)
    centre.update(json.loads(args.centre))
    wanted = [a.strip() for a in args.axes.split(",") if a.strip()]
    axes = [(a, v) for a, v in AXES if not wanted or a in wanted]

    t0 = time.time()
    corpus = P.load_frames([R.COMBINED / "train"], FEATURE)
    labels = sp.load_labels(R.COMBINED)
    train = R.collect(R.COMBINED / "train", labels, (FEATURE,))
    classes = sorted({it["label"] for it in train})
    print(f"{corpus.n} training frames, {len(train)} CV items, "
          f"{len(classes)} classes, chance {1 / len(classes):.3f} "
          f"({time.time() - t0:.0f}s)\n", flush=True)
    print(f"{'axis':<12}{'value':>8}{'top1':>8}{'sd':>7}{'ba/pa':>8}{'da/ta':>8}"
          f"{'8-pair':>8}{'dead':>6}{'nce':>9}{'s':>7}", flush=True)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    def flush(rows: list) -> None:
        """Rewritten after every row.  A sweep that gets killed half way -- this
        machine is shared and the first attempt was -- must still leave the rows
        it actually measured, not an empty file."""
        best = max(rows, key=lambda r: r["top1"])
        out.write_text(json.dumps({
            "question": "which predictive-coding hyperparameters, chosen without "
                        "reading the held-out split",
            "protocol": "leave-one-base-rendering-out over the 396 train items; "
                        "cosine 1-NN over unit histograms; four ants per row",
            "metric_policy": "quantisation error is not computed in this file",
            "centre": centre,
            "axes_requested": [a for a, _ in axes],
            "complete": False,
            "chance_top1": 1 / len(classes),
            "best_by_cv_top1": {"axis": best["axis"], "value": best["value"],
                                "config": best["config"], "top1": best["top1"]},
            "rows": rows,
        }, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    seen, rows = {}, []
    for axis, values in axes:
        for value in values:
            cfg = dict(centre)
            cfg[axis] = value
            key = json.dumps(cfg, sort_keys=True)
            if key in seen:
                row = dict(seen[key])
            else:
                row = run(corpus, train, classes, args.units, cfg)
                seen[key] = row
            row = dict(row, axis=axis, value=value)
            rows.append(row)
            flush(rows)
            print(f"{axis:<12}{value!s:>8}{row['top1'] * 100:7.1f}%"
                  f"{row['top1_std_over_ants'] * 100:6.1f}"
                  f"{row['ba_pa'] * 100:7.1f}%{row['da_ta'] * 100:7.1f}%"
                  f"{row['all_pairs'] * 100:7.1f}%{row['dead_units']:6.0f}"
                  f"{row['infonce_nats']:9.3f}{row['seconds']:7.0f}", flush=True)
        print("", flush=True)

    payload = json.loads(out.read_text(encoding="utf-8"))
    payload["complete"] = True
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                   encoding="utf-8")
    best = payload["best_by_cv_top1"]
    print(f"best CV top1: {best['axis']}={best['value']}  "
          f"{best['top1'] * 100:.1f}%\nwrote {out}  ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
