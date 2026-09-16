"""Paired item-level tests for the three comparisons that decide the verdict.

Colony means hide the fact that every codebook is scored on the *same* 132
held-out tokens, so the four ants' errors are correlated and an unpaired
comparison of means overstates the uncertainty. These are exact McNemar tests on
the per-item decisions, one per ant, matched by seed:

  A. combined corpus vs human-only corpus at matched k -- did the curriculum help?
  B. combined corpus vs random real frames at matched k -- did k-means help?
  C. combined corpus vs random Gaussian centres -- is the codebook more than an
     arbitrary partition of the same feature space?
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

import sequence_probes as sp
from acoustic_units import dataset, load_checkpoint
from colony import DEFAULT_ANTS, DEFAULT_SEEDS
from run_knowledge_tests import COMBINED, STATE, Corpus


def mcnemar(a: np.ndarray, b: np.ndarray) -> dict:
    """Exact two-sided McNemar on paired correct/incorrect masks."""
    only_a = int(np.sum(a & ~b))
    only_b = int(np.sum(~a & b))
    n = only_a + only_b
    if n == 0:
        return {"a_only": 0, "b_only": 0, "p_value": 1.0}
    high = max(only_a, only_b)
    tail = sum(math.comb(n, k) for k in range(high, n + 1)) / 2 ** n
    return {"a_only": only_a, "b_only": only_b, "p_value": min(1.0, 2 * tail)}


def correct_mask(corpus: Corpus, centers: np.ndarray, metric: str) -> np.ndarray:
    train = sp.encode_items(corpus.train, centers)
    held = sp.encode_items(corpus.held, centers)
    if metric == "cosine":
        s = sp.cosine_similarity_matrix(held["histograms"], train["histograms"])
    else:
        s = sp.edit_similarity_matrix(held["sequences"], train["sequences"])
    r = sp.nn_classify(s, corpus.y_train, corpus.y_held, corpus.classes)
    return r["predicted"] == r["truth"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="reports/paired-tests.json")
    args = parser.parse_args()
    corpus = Corpus()
    train_x, _ = dataset(COMBINED / "train")
    mean, std = train_x.mean(axis=0), train_x.std(axis=0)

    def trained(colony: str, ant: str) -> np.ndarray:
        return np.asarray(
            load_checkpoint(STATE / colony / ant / "current.json")["centers"],
            dtype=np.float32)

    def real_frames(units: int, seed: int) -> np.ndarray:
        rng = np.random.default_rng(seed)
        return train_x[rng.choice(len(train_x), units, replace=False)].copy()

    def gaussian(units: int, seed: int) -> np.ndarray:
        rng = np.random.default_rng(seed + 100_000)
        return (mean + std * rng.standard_normal((units, train_x.shape[1]))).astype(np.float32)

    comparisons = [
        ("A curriculum: combined-64 vs human-only-64",
         lambda a, s: trained("64", a), lambda a, s: trained("control-human-only-64", a)),
        ("B optimiser: combined-256 vs random-real-frames-256",
         lambda a, s: trained("256", a), lambda a, s: real_frames(256, s)),
        ("B' optimiser: combined-64 vs random-real-frames-64",
         lambda a, s: trained("64", a), lambda a, s: real_frames(64, s)),
        ("C partition: combined-256 vs random-gaussian-centres-256",
         lambda a, s: trained("256", a), lambda a, s: gaussian(256, s)),
        ("D capacity: combined-256 vs combined-64",
         lambda a, s: trained("256", a), lambda a, s: trained("64", a)),
    ]

    report = {"heldout_items": len(corpus.held), "comparisons": []}
    for metric in ("cosine", "edit"):
        for name, left, right in comparisons:
            per_ant, pooled_a, pooled_b = [], [], []
            for ant, seed in zip(DEFAULT_ANTS, DEFAULT_SEEDS):
                a = correct_mask(corpus, left(ant, seed), metric)
                b = correct_mask(corpus, right(ant, seed), metric)
                pooled_a.append(a)
                pooled_b.append(b)
                per_ant.append({
                    "ant": ant, "left_accuracy": float(a.mean()),
                    "right_accuracy": float(b.mean()), **mcnemar(a, b)})
            a, b = np.concatenate(pooled_a), np.concatenate(pooled_b)
            entry = {
                "comparison": name, "metric": metric, "per_ant": per_ant,
                "pooled_left_accuracy": float(a.mean()),
                "pooled_right_accuracy": float(b.mean()),
                "pooled_delta_points": float(100 * (a.mean() - b.mean())),
                "pooled_mcnemar": mcnemar(a, b),
                "ants_where_left_wins": int(sum(
                    1 for p in per_ant if p["left_accuracy"] > p["right_accuracy"])),
            }
            report["comparisons"].append(entry)
            print(f"{metric:<7} {name:<58} "
                  f"{100 * entry['pooled_left_accuracy']:5.1f} vs "
                  f"{100 * entry['pooled_right_accuracy']:5.1f}  "
                  f"delta={entry['pooled_delta_points']:+5.1f}  "
                  f"p={entry['pooled_mcnemar']['p_value']:.4f}  "
                  f"wins={entry['ants_where_left_wins']}/4", flush=True)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
