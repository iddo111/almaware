#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gate.py -- THE HUMAN GATE. His taps are the truth, not a suggestion.

Iddo, 2026-09-12: "give the training a JUDGE, with him as a judge too, so the
training loop closes." This file is the "him as a judge too" half. It is the
only file in this slice that decides whether judge.py's numbers are ALLOWED
to steer which checkpoint gets kept.

THE RULE, STATED ONCE SO IT CANNOT DRIFT
------------------------------------------
The judge may steer checkpoint selection ONLY WHILE it agrees with Iddo on
the clips he has already rated. Agreement is computed and logged every run,
against darwish_ratings.csv (the taste_server.py ledger, his real taps: good
= iddo_pct 100, bad = iddo_pct 0, skip = blank/ignored) matched by filename to
judged_log.jsonl (every score judge.py has produced). When they disagree --
or when there is not yet enough overlap to tell -- checkpoint selection falls
back to held-out loss, and this file's own log says so in plain words. This
is the exact shape of miko/teacher/judge.py's --calibrate (same kappa
formula, same PASS/FAIL framing, same refusal-on-no-data behaviour) applied
to music instead of search relevance -- "one idea in this house, not two."

    python gate.py --calibrate            # run it, print + log the verdict
    python gate.py --status               # just show the last verdict
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

import common

RELEVANT_AT = 50.0   # judge overall_score_0to100 >= this counts as "judge says good"


def _rated_rows():
    """His real taps from darwish_ratings.csv: (basename, iddo_label) for every
    row where he actually pressed good or bad (skip/blank is not a verdict)."""
    out = {}
    if not common.RATINGS_CSV.exists():
        return out
    with open(common.RATINGS_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            pct = (row.get("iddo_pct") or "").strip()
            fname = (row.get("file") or "").strip()
            if pct in ("0", "100") and fname:
                out[os.path.basename(fname).lower()] = 1 if pct == "100" else 0
    return out


def _judged_rows():
    """Every (basename, latest judge score) judge.py has ever produced."""
    out = {}
    for r in common.read_jsonl(common.JUDGED_LOG):
        f = r.get("file")
        s = r.get("overall_score_0to100")
        if f and s is not None:
            out[os.path.basename(f).lower()] = s   # last write for a name wins
    return out


def calibrate(min_kappa=0.40, min_acc=0.70) -> dict:
    rated = _rated_rows()
    judged = _judged_rows()
    if not rated:
        result = {
            "status": "NO_DATA", "n_overlap": 0,
            "verdict": "BENCHED -- Iddo has not rated any clip yet. Checkpoint "
                       "selection falls back to held-out loss only until he does.",
            "steer_allowed": False,
        }
        common.append_jsonl(common.GATE_LOG, dict(result, ts=common.now()))
        Path(common.GATE_STATUS).write_text(json.dumps(result, ensure_ascii=False, indent=1),
                                            encoding="utf-8")
        return result
    keys = [k for k in rated if k in judged]
    if not keys:
        result = {
            "status": "NO_OVERLAP", "n_overlap": 0,
            "n_rated": len(rated), "n_judged": len(judged),
            "verdict": "BENCHED -- he has rated %d clip(s) and the judge has scored %d, "
                       "but not the SAME ones yet. Score the files he already rated "
                       "(or wait for the next ones he rates to also pass through "
                       "judge.py) before this gate can say anything." % (len(rated), len(judged)),
            "steer_allowed": False,
        }
        common.append_jsonl(common.GATE_LOG, dict(result, ts=common.now()))
        Path(common.GATE_STATUS).write_text(json.dumps(result, ensure_ascii=False, indent=1),
                                            encoding="utf-8")
        return result
    iddo = [rated[k] for k in keys]
    judge_bin = [1 if judged[k] >= RELEVANT_AT else 0 for k in keys]
    acc = sum(1 for x, y in zip(iddo, judge_bin) if x == y) / len(keys)
    k = common.kappa(iddo, judge_bin)
    ok = (k == k) and (k >= min_kappa) and (acc >= min_acc)
    result = {
        "status": "PASS" if ok else "FAIL",
        "n_overlap": len(keys), "accuracy": round(acc, 4),
        "kappa": round(k, 4) if k == k else None,
        "min_kappa": min_kappa, "min_acc": min_acc,
        "overlap_files": keys,
        "steer_allowed": ok,
        "verdict": ("STEERING -- the judge agrees with Iddo on %d overlapping clip(s) "
                    "(accuracy %.2f, kappa %s); it MAY steer checkpoint selection."
                    % (len(keys), acc, ("%.2f" % k) if k == k else "undefined")) if ok else
                   ("BENCHED -- the judge disagrees with Iddo on %d overlapping clip(s) "
                    "(accuracy %.2f, kappa %s, need >=%.2f/%.2f); training keeps going but "
                    "checkpoint selection falls back to held-out loss only."
                    % (len(keys), acc, ("%.2f" % k) if k == k else "undefined", min_acc, min_kappa)),
    }
    common.append_jsonl(common.GATE_LOG, dict(result, ts=common.now()))
    Path(common.GATE_STATUS).write_text(json.dumps(result, ensure_ascii=False, indent=1),
                                        encoding="utf-8")
    return result


def current_status() -> dict:
    if common.GATE_STATUS.exists():
        try:
            return json.loads(common.GATE_STATUS.read_text(encoding="utf-8"))
        except Exception:
            pass
    return calibrate()


def main() -> int:
    common.utf8()
    common.lower_priority()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--calibrate", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--min-kappa", type=float, default=0.40)
    ap.add_argument("--min-acc", type=float, default=0.70)
    a = ap.parse_args()
    if a.status and not a.calibrate:
        result = current_status()
    else:
        result = calibrate(a.min_kappa, a.min_acc)
    print(json.dumps(result, ensure_ascii=False, indent=1))
    print()
    print(result.get("verdict", ""))
    return 0 if result.get("steer_allowed") or result.get("status") in ("NO_DATA", "NO_OVERLAP") else 1


if __name__ == "__main__":
    sys.exit(main())
