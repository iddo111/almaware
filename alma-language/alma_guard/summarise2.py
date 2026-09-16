#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mean and range across the CONFIRMATION fold-seeds (1,2,3).

Hyperparameters were chosen on fold-seed 0 and are reported on 1/2/3, so the
number in RESULTS.md was not selected on the rows it is reported against.
"""
import glob
import json
import statistics
import sys

sys.stdout.reconfigure(encoding="utf-8")

groups: dict[str, list[dict]] = {}
for f in sorted(glob.glob("out2/*.json")):
    name = f.split("/")[-1].replace(".json", "")
    if "_s" not in name:
        continue
    base = name.rsplit("_s", 1)[0]
    d = json.load(open(f, encoding="utf-8"))
    if "cv" in d:
        groups.setdefault(base + " [alma-guard]", []).append(d["cv"])
    for k in ("perceptron", "logreg"):
        if k in d:
            groups.setdefault(f"{base} [{k}]", []).append(d[k])


def agg(vals):
    return f"{statistics.mean(vals):.4f} ({min(vals):.4f}-{max(vals):.4f})"


print(f"{'config':30s} {'n':>3s}  {'accuracy':22s} {'precision':22s} "
      f"{'recall':22s} {'F1':22s}")
for name in sorted(groups):
    ms = groups[name]
    print(f"{name:30s} {len(ms):3d}  "
          f"{agg([m['acc'] for m in ms]):22s} "
          f"{agg([m['precision'] for m in ms]):22s} "
          f"{agg([m['recall'] for m in ms]):22s} "
          f"{agg([m['f1'] for m in ms]):22s}")
