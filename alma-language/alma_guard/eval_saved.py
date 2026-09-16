#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Score a SAVED ALMA-GUARD model on a held-out file. Inference only - no training.

    python -m alma_guard.eval_saved                      # fresh.jsonl, binary
    python -m alma_guard.eval_saved --task multi
    python -m alma_guard.eval_saved --file other.jsonl

Exists so a new held-out set can be measured against the *already trained*
weights without retraining - which would both cost fleet time and, worse, quietly
change the model the numbers in RESULTS.md refer to.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from alma_guard import data as D                                    # noqa: E402
from alma_guard import encoding as E                                # noqa: E402
from alma_guard.infer import load_model                             # noqa: E402
from alma_guard.train import label_of, report                       # noqa: E402

HERE = Path(__file__).resolve().parent


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--task", choices=("binary", "multi"), default="binary")
    ap.add_argument("--file", default="")
    ap.add_argument("--json-out", default="")
    ap.add_argument("--show-misses", action="store_true")
    args = ap.parse_args()

    g = load_model(args.task)
    rows = D.load(Path(args.file) if args.file else HERE / "fresh.jsonl")
    truth = [label_of(r, args.task) for r in rows]
    pred = [g.predict(E.features(r["text"], g.hyper.width))[0] for r in rows]
    m = report(f"ALMA-GUARD (saved model_{args.task}.json) on "
               f"{args.file or 'fresh.jsonl'}", rows, truth, pred,
               list(range(len(rows))), args.task)
    if args.show_misses:
        print("  misses:")
        for r, t, p in zip(rows, truth, pred):
            if t != p:
                print(f"    want {t:20s} got {p:20s} [{r['source']}] "
                      f"{r['text'][:70]}")
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(m, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
