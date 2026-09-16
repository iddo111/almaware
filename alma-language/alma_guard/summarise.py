#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Collect every sweep result in out/ into one table. Sorted by accuracy, honestly."""
import glob
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")


def show(fs, arm):
    rows = []
    for f in sorted(fs):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        name = f.split("/")[-1].replace(".json", "")
        task = d.get("task", "?")
        if arm == "alma":
            m = d.get("cv")
            if not m:
                continue
            h = d.get("hyper", {})
            tag = (f"w{h.get('width')} e{h.get('epochs')} d{h.get('drift')} "
                   f"miss{h.get('r_miss')}")
            rows.append((m["acc"], name, "alma-guard", task, m, tag))
        else:
            for k in ("perceptron", "logreg"):
                if k in d:
                    rows.append((d[k]["acc"], name, k, task,
                                 d[k], f"w{d.get('width')}"))
    rows.sort(reverse=True)
    for acc, name, kind, task, m, tag in rows:
        print(f"{name:16s} {kind:11s} {task:6s} acc {m['acc']:.4f}  "
              f"P {m['precision']:.4f}  R {m['recall']:.4f}  F1 {m['f1']:.4f}  "
              f"fp={m['fp']:3d} fn={m['fn']:3d}   {tag}")


print("=== ALMA-GUARD ===")
show([f for f in glob.glob("out/*.json") if "/v" not in f and "_v" not in f], "alma")
print("\n=== VANILLA CONTROLS ===")
show([f for f in glob.glob("out/*.json") if "/v" in f or "_v" in f], "vanilla")
