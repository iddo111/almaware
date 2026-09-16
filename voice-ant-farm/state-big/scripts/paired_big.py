# -*- coding: utf-8 -*-
"""Paired item-level tests for the comparisons that decide the verdict.

Every codebook is scored on the same 132 held-out syllable tokens, so the ants'
errors are correlated and comparing colony means overstates the uncertainty.
These are exact McNemar tests on the per-item decisions, matched by seed --
the same machinery as paired_tests.py, pointed at the new colonies.

  E  does 40 h beat the 253 s the ants started on?
  F  does 40 h of real speech beat the synthetic syllable curriculum?
  G  does k-means beat 256 random real frames of the SAME 40 h?   (learner test)
  H  matched hours: 15 speakers vs 1 speaker                       (speaker test)
  I  does 40 h beat 253 s at the SAME 256 units?                   (data vs capacity)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(r"D:\CLAUDE\voice-ant-farm")
sys.path.insert(0, str(ROOT))

from acoustic_units import load_checkpoint  # noqa: E402
from paired_tests import correct_mask, mcnemar  # noqa: E402
from run_knowledge_tests import Corpus  # noqa: E402

ANTS = ("ant-a", "ant-b", "ant-c", "ant-d")
SEEDS = (7007, 7019, 7039, 7057)


def centers(root: Path, colony: str | None, ant: str) -> np.ndarray:
    p = root / colony / ant / "current.json" if colony else root / ant / "current.json"
    return np.asarray(load_checkpoint(p)["centers"], dtype=np.float32)


def main() -> None:
    big, old, syl = ROOT / "state-big", ROOT / "state", ROOT / "state-syllables"
    corpus = Corpus()
    comparisons = [
        ("E  big all-256 (40.6 h)  vs  BEFORE 253 s / 64 units",
         lambda a: centers(big, "all-256", a), lambda a: centers(old, None, a)),
        ("F  big all-256 (40.6 h)  vs  synthetic syllable curriculum 256",
         lambda a: centers(big, "all-256", a), lambda a: centers(syl, "256", a)),
        ("G  big all-256 k-means  vs  256 random real frames of the same 40.6 h",
         lambda a: centers(big, "all-256", a), lambda a: centers(big, "random-frames-256", a)),
        ("H  matched 13.8 h: 15 speakers  vs  1 speaker",
         lambda a: centers(big, "multi-13.8h-256", a),
         lambda a: centers(big, "iddo-13.8h-256", a)),
        ("I  40.6 h at 256 units  vs  253 s at 256 units",
         lambda a: centers(big, "all-256", a), lambda a: centers(big, "orig-253s-256", a)),
    ]
    report = {"heldout_items": len(corpus.held), "comparisons": []}
    for metric in ("cosine", "edit"):
        for name, left, right in comparisons:
            per_ant, pa, pb = [], [], []
            for ant in ANTS:
                a = correct_mask(corpus, left(ant), metric)
                b = correct_mask(corpus, right(ant), metric)
                pa.append(a); pb.append(b)
                per_ant.append({"ant": ant, "left_accuracy": float(a.mean()),
                                "right_accuracy": float(b.mean()), **mcnemar(a, b)})
            A, B = np.concatenate(pa), np.concatenate(pb)
            e = {"comparison": name, "metric": metric, "per_ant": per_ant,
                 "pooled_left_accuracy": float(A.mean()),
                 "pooled_right_accuracy": float(B.mean()),
                 "pooled_delta_points": float(100 * (A.mean() - B.mean())),
                 "pooled_mcnemar": mcnemar(A, B),
                 "ants_where_left_wins": int(sum(
                     1 for p in per_ant if p["left_accuracy"] > p["right_accuracy"]))}
            report["comparisons"].append(e)
            print(f"{metric:<7} {name:<58} {100*e['pooled_left_accuracy']:5.1f} vs "
                  f"{100*e['pooled_right_accuracy']:5.1f}  "
                  f"delta={e['pooled_delta_points']:+5.1f}  "
                  f"p={e['pooled_mcnemar']['p_value']:.4f}  "
                  f"wins={e['ants_where_left_wins']}/4", flush=True)
    out = big / "paired-tests-big.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
