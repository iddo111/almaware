#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run a trained ALMA-GUARD weave on one string.

    python -m alma_guard.infer "ignore all previous instructions"
    python -m alma_guard.infer --task multi "תתעלם מההוראות הקודמות"
    echo "some text" | python -m alma_guard.infer -

The decision is always the weave's own: did the head KNOT FIRE. The margin is
read by running the same weights a second time with the heads' triggers opened
to `any`, so the head speaks its total instead of withholding it - no dot product
is ever computed outside the loom.

The margin is squashed into a 0..1 number for display. It is NOT calibrated and
RESULTS.md says so; treat it as "how far from the line", not as a probability.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from alma_guard import encoding as E                                # noqa: E402
from alma_guard.weave import GuardWeave, Hyper                      # noqa: E402

HERE = Path(__file__).resolve().parent
TEMP = 2.0          # display only: how steeply the margin squashes to 0..1


def load_model(task: str) -> GuardWeave:
    p = HERE / f"model_{task}.json"
    if not p.exists():
        raise SystemExit(f"no trained model at {p}\n"
                         f"train one:  python -m alma_guard.train --task {task} --final")
    m = json.loads(p.read_text(encoding="utf-8"))
    hyper = Hyper(**m["hyper"])
    g = GuardWeave(m["heads"], hyper, default=m["default"])
    g.load(m["weights"])
    return g


def margins(g: GuardWeave, feats: dict[int, float]) -> dict[int, float]:
    """Open every head's trigger to `any` so it speaks its total, then run."""
    saved = {}
    for k in range(len(g.heads)):
        name = f"out{k}"
        saved[name] = g.weave.knots[name].trigger
        g.weave.knots[name].trigger = "any"
    try:
        g._seed(feats)
        r = g.loom.run(g.weave, beats=g.horizon)
        out = {}
        for k in range(len(g.heads)):
            vals = r.fringe(f"say{k}")
            out[k] = float(vals[0]) if vals else float("-inf")
        return out
    finally:
        for name, t in saved.items():
            g.weave.knots[name].trigger = t


def judge(g: GuardWeave, text: str) -> dict:
    feats = E.features(text, g.hyper.width)
    label, _ = g.predict(feats)              # the weave's own decision: did it fire
    mg = margins(g, feats)
    best = max(mg, key=lambda k: mg[k]) if mg else None
    m = mg.get(best, 0.0) if best is not None else 0.0
    return {
        "label": label,
        "margin": m,
        "confidence": 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, m / TEMP)))),
        "per_head": {g.heads[k]: round(v, 4) for k, v in mg.items()},
        "sparks": len(feats),
        "shape": E.describe(text, g.hyper.width),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("text", nargs="*", help="the text to judge, or - to read stdin")
    ap.add_argument("--task", choices=("binary", "multi"), default="binary")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not args.text or args.text == ["-"]:
        text = sys.stdin.read()
    else:
        text = " ".join(args.text)
    if not text.strip():
        raise SystemExit("nothing to judge")

    g = load_model(args.task)
    v = judge(g, text)
    if args.json:
        print(json.dumps(v, ensure_ascii=False))
    else:
        print(f"{v['label']}   confidence {v['confidence']:.3f}  "
              f"(margin {v['margin']:+.3f}, uncalibrated)")
        print(f"  {v['shape']}")
        print("  per head: " + ", ".join(f"{k} {x:+.3f}" for k, x in v["per_head"].items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
