#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The v0.2 grid, DECLARED BEFORE ANY NUMBER WAS SEEN. Writes arms/*.json and job lists.

    python -m alma_guard.v02_arms            # -> alma_guard/arms/, alma_guard/jobs_*.txt

PROTOCOL (the same as v0.1's, so the two are comparable):
  phase 1  every arm below, 5-fold CV on fold-seed 0 -> pick the best cell of each
           FAMILY by CV accuracy (ties: F1). The whole grid is printed, not the winner.
  phase 2  the chosen cell of each family on fold-seeds 1, 2, 3 -> the reported CV number.
  phase 3  the chosen cell of each family trained on ALL rows with init seeds 0..4 ->
           held-out sources, each separately: fresh (16), guard-p2 (5), shield-tests
           (28), and fresh-v02 once it exists.
Controls get the same protocol and the same objective asymmetry as the ALMA cell
they are compared with (pos_weight = r_miss / r_fa).
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARMS = HERE / "arms"

ALMA_BASE = {"kind": "alma", "task": "binary", "width": 1024, "drift": 0.05,
             "init": 0.02, "r_ok": 0.10, "r_fa": 1.0, "epochs": 15}


def families() -> dict[str, list[dict]]:
    fam: dict[str, list[dict]] = {}
    fam["alma-1L-3f"] = [dict(ALMA_BASE, name=f"alma-1L-3f-m{m}", r_miss=float(m))
                         for m in (2, 4)]
    fam["alma-h8-pert"] = [dict(ALMA_BASE, name=f"alma-h8-pert-s{s}-e{e}", r_miss=4.0,
                                hidden=8, rule="perturbation", sigma=s, eta=e, skip=True)
                           for s in (0.3, 1.0) for e in (0.01, 0.04, 0.16)]
    fam["alma-h8-3f"] = [dict(ALMA_BASE, name="alma-h8-3f-m4", r_miss=4.0, hidden=8,
                              rule="three-factor", skip=True)]
    for kind in ("perceptron", "logreg"):
        for w in (1024, 9232):
            fam[f"{kind}-w{w}"] = [
                {"name": f"{kind}-w{w}-lr{lr}-pw{pw}", "kind": kind, "task": "binary",
                 "width": w, "epochs": 30, "lr": lr, "l2": 1e-4, "pos_weight": float(pw)}
                for lr in (0.01, 0.05, 0.2) for pw in (2, 4)]
    fam["mlp-w1024-h8"] = [
        {"name": f"mlp-w1024-h8-lr{lr}-pw{pw}", "kind": "mlp", "task": "binary",
         "width": 1024, "hidden": 8, "skip": True, "epochs": 15, "lr": lr, "l2": 1e-4,
         "pos_weight": float(pw)}
        for lr in (0.01, 0.05, 0.2) for pw in (2, 4)]
    return fam


def main() -> int:
    ARMS.mkdir(exist_ok=True)
    fam = families()
    alma_jobs, ctrl_jobs = [], []
    for name, arms in fam.items():
        for a in arms:
            (ARMS / f"{a['name']}.json").write_text(json.dumps(a, indent=1), encoding="utf-8")
            cmd = (f"python3 -m alma_guard.v02_experiment cv --arm alma_guard/arms/{a['name']}.json "
                   f"--fold-seed 0 --out out/p1/{a['name']}_fs0.json > logs/p1_{a['name']}.log 2>&1")
            (alma_jobs if a["kind"] == "alma" else ctrl_jobs).append(cmd)
    # the ALMA cells are slow; interleave so the cheap controls do not wait behind them
    jobs = []
    while alma_jobs or ctrl_jobs:
        if alma_jobs:
            jobs.append(alma_jobs.pop(0))
        for _ in range(3):
            if ctrl_jobs:
                jobs.append(ctrl_jobs.pop(0))
    (HERE / "jobs_p1.txt").write_text("\n".join(jobs) + "\n", encoding="utf-8")
    (HERE / "families.json").write_text(json.dumps({k: [a["name"] for a in v]
                                                    for k, v in fam.items()}, indent=1),
                                        encoding="utf-8")
    print(f"{sum(len(v) for v in fam.values())} arms in {len(fam)} families; "
          f"{len(jobs)} phase-1 jobs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
