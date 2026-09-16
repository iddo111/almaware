"""Feature sets judged by fixed classifiers.  No codebook, no learner.

The rule of this file: the *only* thing that varies between rows is the frame
feature vector.  Everything downstream is frozen, and is the same code the
existing report used, so the legacy14 row must reproduce the published numbers
exactly (it does: 53.8% / 68.9%).

    frame selection   frozen.  Computed once from the colony's own log-energy
                      column and reused verbatim for every feature set, so no
                      feature set gets to choose its own frames.
                        span    sequence_probes.speech_span
                        loud60  run_knowledge_tests.loudest, top 60% of frames
    descriptor        run_knowledge_tests.descriptors -> [mean, std] over the
                      selected frames
    scaling           run_knowledge_tests.zscore, statistics from train only
    classifier        1-NN, negative Euclidean
    scoring           sequence_probes.nn_classify / minimal_pair_scores

Both poolings are reported for every feature set because the two headline
numbers in circulation come from different ones: the 53.8% ceiling is `span`,
the "raw features separate ba/pa at 100%" is `loud60`.  Quoting one number from
each pooling is how a feature set gets to look better than it is.

Quantisation error is not computed anywhere in this file, on purpose.

    py -3.13 feature_bakeoff.py
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

import feature_space as F
import sequence_probes as sp
from acoustic_units import EXEMPLAR_RATE, load_wav, resample_samples
from paired_tests import mcnemar
from run_knowledge_tests import COMBINED, descriptors, negative_distance, zscore

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "state-hebbian" / "feature-bakeoff.json"
POOLINGS = ("span", "loud60")
LOUD_FRACTION = 0.60


def collect(folder: Path, labels: dict) -> list[dict]:
    """One pass over the audio.  Frame selection is frozen here, from legacy14."""
    items = []
    for path in sorted(folder.glob("*.wav")):
        record = labels.get(path.name)
        if record is None or record.get("item_kind") != "syllable":
            continue
        audio = load_wav(path)
        samples = resample_samples(audio.samples, audio.rate, EXEMPLAR_RATE)
        legacy = F.extract("legacy14", samples)
        a, b = sp.speech_span(legacy)
        span = np.zeros(len(legacy), dtype=bool)
        span[a:b] = True
        keep = max(1, int(round(LOUD_FRACTION * len(legacy))))
        loud = np.zeros(len(legacy), dtype=bool)
        loud[np.argsort(legacy[:, 0], kind="stable")[-keep:]] = True
        items.append({"name": path.name, "label": record["item_id"],
                      "base": record.get("base_rendering_id"),
                      "samples": samples, "span": span, "loud60": loud})
    if not items:
        raise ValueError(f"no syllable audio in {folder}")
    return items


def featurise(items: list[dict], name: str) -> None:
    """CMVN statistics always come from the speech span, never from the pooling."""
    for it in items:
        it["_x"] = F.extract(name, it["samples"], it["span"])


def score(train: list[dict], held: list[dict], classes: list[str],
          pooling: str, seed: int) -> dict:
    for it in train + held:
        it["speech"] = it["_x"][it[pooling]]
    y_train = [it["label"] for it in train]
    y_held = [it["label"] for it in held]
    base_held = [it["base"] for it in held]
    d_train, d_held = zscore(descriptors(train), descriptors(held))
    similarity = negative_distance(d_train, d_held)
    nn = sp.nn_classify(similarity, y_train, y_held, classes)
    pairs = sp.minimal_pair_scores(similarity, y_train, y_held)
    within = sp.separation(negative_distance(d_held, d_held), y_held, base_held)
    return {
        "pooling": pooling,
        "descriptor_dim": int(d_train.shape[1]),
        "top1": nn["top1"],
        "top5": nn["top5"],
        "meanlink_top1": nn["meanlink_top1"],
        "minimal_pairs": {p["pair"]: p["accuracy"] for p in pairs},
        "minimal_pairs_meanlink": {p["pair"]: p["meanlink_accuracy"] for p in pairs},
        "minimal_pairs_full": pairs,
        "heldout_pair_separation_cohens_d": within["cohens_d"],
        "heldout_pair_auc": within["auc"],
        "permutation_null_top1": sp.permutation_null(similarity, y_train, y_held,
                                                     classes, seed),
        "top_confusions": sp.top_confusions(nn["confusion"], classes),
        "confusion": nn["confusion"].tolist(),
        "_correct": nn["predicted"] == nn["truth"],
    }


def cross_validate(train: list[dict], classes: list[str], pooling: str) -> dict:
    """Leave-one-base-rendering-out, INSIDE the train split only.

    Model selection must not look at the held-out split, so this is the number
    that is allowed to choose a feature set.  Six folds of 66 items each, and
    a whole vocoder rendering leaves together so augmentation twins cannot leak
    across the fold boundary.
    """
    for it in train:
        it["speech"] = it["_x"][it[pooling]]
    labels = [it["label"] for it in train]
    bases = [it["base"] for it in train]
    folds = sorted({b.rsplit("/", 1)[-1] for b in bases})
    d = descriptors(train)
    top1, pair_hits, pair_total = [], {}, {}
    for fold in folds:
        test = np.asarray([b.endswith("/" + fold) for b in bases])
        if not test.any() or test.all():
            continue
        a, b = zscore(d[~test], d[test])
        s = negative_distance(a, b)
        y_tr = [l for l, t in zip(labels, test) if not t]
        y_te = [l for l, t in zip(labels, test) if t]
        top1.append(sp.nn_classify(s, y_tr, y_te, classes)["top1"])
        for p in sp.minimal_pair_scores(s, y_tr, y_te):
            pair_hits[p["pair"]] = pair_hits.get(p["pair"], 0) + p["correct"]
            pair_total[p["pair"]] = pair_total.get(p["pair"], 0) + p["items"]
    pairs = {k: pair_hits[k] / pair_total[k] for k in pair_hits}
    return {
        "pooling": pooling, "folds": len(top1),
        "top1": float(np.mean(top1)),
        "top1_per_fold": [float(v) for v in top1],
        "top1_std_over_folds": float(np.std(top1)),
        "minimal_pairs": pairs,
        "minimal_pairs_decisions": {k: int(pair_total[k]) for k in pair_total},
        "all_pairs_pooled": float(sum(pair_hits.values()) / sum(pair_total.values())),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(OUT))
    parser.add_argument("--sets", default="")
    parser.add_argument("--seed", type=int, default=7007)
    parser.add_argument("--cv", action="store_true",
                        help="leave-one-base-out inside train only; no heldout")
    args = parser.parse_args()

    if args.cv:
        labels = sp.load_labels(COMBINED)
        train = collect(COMBINED / "train", labels)
        classes = sorted({it["label"] for it in train})
        print(f"train-only leave-one-base-out, {len(train)} items, "
              f"{len(classes)} classes\n", flush=True)
        print(f"{'feature set':<24}{'dim':>4}  "
              f"{'span top1 (sd)':<18}{'ba/pa':>7}{'da/ta':>7}{'8-pair':>8}   "
              f"{'loud60 top1':<13}{'ba/pa':>7}{'da/ta':>7}{'8-pair':>8}", flush=True)
        rows = []
        for name in [n.strip() for n in args.sets.split(",") if n.strip()] or list(F.SETS):
            featurise(train, name)
            row = {"feature_set": name, "dim": int(F.SETS[name].dim),
                   "note": F.SETS[name].note,
                   "poolings": {p: cross_validate(train, classes, p)
                                for p in POOLINGS}}
            rows.append(row)
            s, l = row["poolings"]["span"], row["poolings"]["loud60"]
            print(f"{name:<24}{row['dim']:>4}  "
                  f"{s['top1'] * 100:6.1f}% ({s['top1_std_over_folds'] * 100:4.1f}) "
                  f"  {s['minimal_pairs'].get('ba/pa', 0) * 100:6.1f}%"
                  f"{s['minimal_pairs'].get('da/ta', 0) * 100:6.1f}%"
                  f"{s['all_pairs_pooled'] * 100:7.1f}%   "
                  f"{l['top1'] * 100:6.1f}%       "
                  f"{l['minimal_pairs'].get('ba/pa', 0) * 100:6.1f}%"
                  f"{l['minimal_pairs'].get('da/ta', 0) * 100:6.1f}%"
                  f"{l['all_pairs_pooled'] * 100:7.1f}%", flush=True)
            for it in train:
                it.pop("_x", None)
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "question": "which feature vector, chosen without touching heldout",
            "protocol": "leave-one-base-rendering-out over the 396 train items; "
                        "the held-out split is not read by this run",
            "chance_top1": 1 / len(classes),
            "results": sorted(rows, key=lambda r: -r["poolings"]["span"]["top1"]),
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nwrote {out}")
        return

    t0 = time.time()
    labels = sp.load_labels(COMBINED)
    train = collect(COMBINED / "train", labels)
    held = collect(COMBINED / "heldout", labels)
    classes = sorted({it["label"] for it in train})
    assert {it["name"] for it in train}.isdisjoint({it["name"] for it in held})
    assert {it["base"] for it in train}.isdisjoint({it["base"] for it in held})
    print(f"train={len(train)} heldout={len(held)} classes={len(classes)} "
          f"chance={1 / len(classes):.3f}  ({time.time() - t0:.1f}s)\n", flush=True)
    print(f"{'feature set':<24}{'dim':>4}  "
          f"{'span: top1  ba/pa  da/ta':<26}  {'loud60: top1  ba/pa  da/ta':<28}",
          flush=True)

    names = [n.strip() for n in args.sets.split(",") if n.strip()] or list(F.SETS)
    rows = []
    for name in names:
        t = time.time()
        featurise(train, name)
        featurise(held, name)
        row = {"feature_set": name, "dim": int(F.SETS[name].dim),
               "note": F.SETS[name].note,
               "poolings": {p: score(train, held, classes, p, args.seed)
                            for p in POOLINGS}}
        row["seconds"] = round(time.time() - t, 1)
        rows.append(row)
        cells = []
        for p in POOLINGS:
            s = row["poolings"][p]
            mp = s["minimal_pairs"]
            cells.append(f"{s['top1'] * 100:5.1f}% {mp.get('ba/pa', 0) * 100:5.1f}% "
                         f"{mp.get('da/ta', 0) * 100:5.1f}%")
        print(f"{name:<24}{row['dim']:>4}  {cells[0]:<26}  {cells[1]:<28} "
              f"({row['seconds']}s)", flush=True)
        for it in train + held:
            it.pop("_x", None)

    baseline = next((r for r in rows if r["feature_set"] == "legacy14"), None)
    reference = ({p: baseline["poolings"][p]["_correct"].copy() for p in POOLINGS}
                 if baseline else None)
    for row in rows:
        for p in POOLINGS:
            mask = row["poolings"][p].pop("_correct")
            if reference is not None:
                row["poolings"][p]["mcnemar_vs_legacy14"] = mcnemar(mask, reference[p])

    report = {
        "question": "which frame feature vector separates Hebrew syllables",
        "classifier": "FIXED per pooling: mean+std over frozen frame selection, "
                      "train-fitted z-score, 1-NN negative Euclidean. Only the "
                      "frame feature vector varies between rows.",
        "frame_selection": "frozen, computed from the legacy log-energy column, "
                           "identical for every feature set",
        "metric_policy": "quantisation error is not computed in this file",
        "chance_top1": 1 / len(classes),
        "chance_minimal_pair": 0.5,
        "heldout_items": len(held),
        "train_items": len(train),
        "classes": classes,
        "results": sorted(rows, key=lambda r: -r["poolings"]["span"]["top1"]),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {out}  ({time.time() - t0:.1f}s total)")


if __name__ == "__main__":
    main()
