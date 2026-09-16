"""Does level invariance buy anything the corpus has not already given away?

The syllable corpus randomises gain only over -10 .. -0.5 dB, which is a
narrower range than a microphone, a room, or a different speaker will produce.
This re-scores the held-out split with a wider per-file gain drawn from a fixed
seed, applied to the held-out audio only.  Train is untouched, so this is a
train/test level mismatch of exactly the kind a deployed ant meets.

A feature vector that is level-invariant by construction should not move at all.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import feature_space as F
import sequence_probes as sp
from feature_bakeoff import POOLINGS, collect, featurise
from run_knowledge_tests import COMBINED, descriptors, negative_distance, zscore

SETS = ["legacy14", "legacy14_noenergy", "logmel26", "mfcc13", "mfcc12",
        "mfcc20_mel26", "recommended26"]
JITTERS_DB = [0.0, 10.0, 20.0, 30.0]


def main() -> None:
    labels = sp.load_labels(COMBINED)
    train = collect(COMBINED / "train", labels)
    held = collect(COMBINED / "heldout", labels)
    classes = sorted({it["label"] for it in train})
    original = [it["samples"] for it in held]

    report = {
        "protocol": "per-file gain drawn uniformly from [-range, 0] dB and applied "
                    "to the held-out audio only; train is untouched. Frame "
                    "selection is recomputed from the jittered audio, as it would "
                    "be in deployment.",
        "seed": 7007, "jitters_db": JITTERS_DB, "results": {},
    }
    print(f"{'feature set':<20}" + "".join(f"{f'-{d:.0f}..0 dB':>13}" for d in JITTERS_DB)
          + "   (span top1, held-out)")
    for name in SETS:
        row = {}
        for db in JITTERS_DB:
            rng = np.random.default_rng(7007)
            gains = 10.0 ** (rng.uniform(-db, 0.0, len(held)) / 20.0)
            for it, base, g in zip(held, original, gains):
                it["samples"] = (base * g).astype(np.float32)
                legacy = F.extract("legacy14", it["samples"])
                a, b = sp.speech_span(legacy)
                it["span"] = np.zeros(len(legacy), dtype=bool)
                it["span"][a:b] = True
                keep = max(1, int(round(0.60 * len(legacy))))
                it["loud60"] = np.zeros(len(legacy), dtype=bool)
                it["loud60"][np.argsort(legacy[:, 0], kind="stable")[-keep:]] = True
            featurise(train, name)
            featurise(held, name)
            entry = {}
            for pooling in POOLINGS:
                for group in (train, held):
                    for it in group:
                        it["speech"] = it["_x"][it[pooling]]
                a, b = zscore(descriptors(train), descriptors(held))
                s = negative_distance(a, b)
                y_tr = [it["label"] for it in train]
                y_te = [it["label"] for it in held]
                nn = sp.nn_classify(s, y_tr, y_te, classes)
                pairs = sp.minimal_pair_scores(s, y_tr, y_te)
                entry[pooling] = {
                    "top1": nn["top1"],
                    "minimal_pairs": {p["pair"]: p["accuracy"] for p in pairs},
                    "all_pairs_pooled": sum(p["correct"] for p in pairs)
                                        / sum(p["items"] for p in pairs),
                }
            for group in (train, held):
                for it in group:
                    it.pop("_x", None)
            row[f"{db:.0f}"] = entry
        report["results"][name] = row
        print(f"{name:<20}" + "".join(
            f"{row[f'{d:.0f}']['span']['top1'] * 100:12.1f}%" for d in JITTERS_DB))
    for it, base in zip(held, original):
        it["samples"] = base
    out = Path(__file__).resolve().parent / "gain-robustness.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
