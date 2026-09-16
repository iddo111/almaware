"""Are the ants' confusions acoustically sensible, or arbitrary?

A confusion matrix on its own proves nothing: an ant that guesses uniformly also
produces confusions. What distinguishes a representation that learned something
real is *which* syllables it merges. This module asks three questions.

  1. Do the confusions follow acoustic proximity in the ants' own feature space?
  2. Do they follow phonetic structure -- shared manner, place, voicing?
  3. On the pairs modern Hebrew actually merges, does the ant fail (which would be
     correct behaviour) or succeed (which would mean it is reading a synthesiser
     fingerprint rather than a speech sound)?

The phonetic table below is standard Israeli Hebrew, written down here so a reader
can disagree with it. It is used for scoring only and reaches no ant.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

import sequence_probes as sp
from run_knowledge_tests import Corpus, descriptors, negative_distance, zscore

# item_id -> (manner, place, voicing)
PHONETICS = {
    "ah":  ("vowel-onset", "glottal", "voiced"),
    "ba":  ("stop", "bilabial", "voiced"),
    "ga":  ("stop", "velar", "voiced"),
    "da":  ("stop", "alveolar", "voiced"),
    "ha":  ("fricative", "glottal", "voiceless"),
    "va":  ("fricative", "labiodental", "voiced"),
    "za":  ("fricative", "alveolar", "voiced"),
    "kha": ("fricative", "uvular", "voiceless"),
    "ta":  ("stop", "alveolar", "voiceless"),
    "ya":  ("approximant", "palatal", "voiced"),
    "ka":  ("stop", "velar", "voiceless"),
    "la":  ("approximant", "alveolar", "voiced"),
    "ma":  ("nasal", "bilabial", "voiced"),
    "na":  ("nasal", "alveolar", "voiced"),
    "sa":  ("fricative", "alveolar", "voiceless"),
    "aa":  ("vowel-onset", "pharyngeal", "voiced"),
    "pa":  ("stop", "bilabial", "voiceless"),
    "tsa": ("affricate", "alveolar", "voiceless"),
    "qa":  ("stop", "velar", "voiceless"),
    "ra":  ("approximant", "uvular", "voiced"),
    "sha": ("fricative", "postalveolar", "voiceless"),
    "tha": ("stop", "alveolar", "voiceless"),
}

# Pairs that modern Israeli Hebrew genuinely merges. An ant that separates these
# is not hearing a phoneme contrast; it is hearing something else.
HOMOPHONES = {("ka", "qa"), ("ta", "tha"), ("ah", "aa")}


def feature_overlap(a: str, b: str) -> int:
    return sum(x == y for x, y in zip(PHONETICS[a], PHONETICS[b]))


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    def rank(v):
        order = np.argsort(v, kind="stable")
        r = np.empty(len(v), dtype=np.float64)
        r[order] = np.arange(len(v), dtype=np.float64)
        _, inverse, counts = np.unique(v, return_inverse=True, return_counts=True)
        sums = np.zeros(len(counts))
        np.add.at(sums, inverse, r)
        return (sums / counts)[inverse]
    ra, rb = rank(a), rank(b)
    ra, rb = ra - ra.mean(), rb - rb.mean()
    return float(ra @ rb / max(np.sqrt((ra @ ra) * (rb @ rb)), 1e-12))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default="reports/syllable-knowledge.json")
    parser.add_argument("--colony", default="512")
    parser.add_argument("--out", default="reports/confusion-analysis.json")
    args = parser.parse_args()
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    classes = report["classes"]
    n = len(classes)

    corpus = Corpus()
    items = corpus.train + corpus.held
    x = descriptors(items, "loud")
    x = (x - x.mean(0)) / np.where(x.std(0) < 1e-9, 1.0, x.std(0))
    y = np.asarray([it["label"] for it in items])
    centroids = np.stack([x[y == c].mean(0) for c in classes])
    acoustic = np.sqrt(((centroids[:, None] - centroids[None]) ** 2).sum(-1))

    iu = np.triu_indices(n, k=1)
    pairs = [(classes[a], classes[b]) for a, b in zip(*iu)]
    acoustic_pair = acoustic[iu]
    phonetic_pair = np.asarray([feature_overlap(a, b) for a, b in pairs], float)

    per_colony = {}
    for group in sorted({c["group"] for c in report["codebooks"]}):
        matrices = [np.asarray(c["test2_nearest_neighbour"]["confusion_cosine"])
                    for c in report["codebooks"] if c["group"] == group]
        total = sum(matrices)
        symmetric = total + total.T
        np.fill_diagonal(symmetric, 0)
        errors = symmetric[iu].astype(float)
        weight = errors.sum()
        per_colony[group] = {
            "errors": int(weight),
            "spearman_errors_vs_acoustic_distance": spearman(errors, acoustic_pair),
            "spearman_errors_vs_phonetic_overlap": spearman(errors, phonetic_pair),
            "mean_phonetic_overlap_of_confusions": float(
                (errors * phonetic_pair).sum() / max(weight, 1)),
            "mean_phonetic_overlap_all_pairs": float(phonetic_pair.mean()),
            "mean_acoustic_distance_of_confusions": float(
                (errors * acoustic_pair).sum() / max(weight, 1)),
            "mean_acoustic_distance_all_pairs": float(acoustic_pair.mean()),
            "share_of_errors_on_the_10_closest_pairs": float(
                errors[np.argsort(acoustic_pair)[:10]].sum() / max(weight, 1)),
            "share_of_pairs_that_are_the_10_closest": 10 / len(pairs),
        }

    raw_train, raw_held = zscore(descriptors(corpus.train, "loud"),
                                 descriptors(corpus.held, "loud"))
    raw_similarity = negative_distance(raw_train, raw_held)
    raw_pairs = sp.minimal_pair_scores(raw_similarity, corpus.y_train, corpus.y_held)

    index = {c: i for i, c in enumerate(classes)}
    minimal = []
    for entry in raw_pairs:
        a, b = entry["pair"].split("/")
        ant = {}
        for group in ("64", "256", "512", "baseline-human-only"):
            values = [next(e for e in c["test3_minimal_pairs"]["cosine"]
                           if e["pair"] == entry["pair"])["accuracy"]
                      for c in report["codebooks"] if c["group"] == group]
            if values:
                ant[group] = float(np.mean(values))
        minimal.append({
            "pair": entry["pair"],
            "raw_features_no_codebook_accuracy": entry["accuracy"],
            "ant_accuracy": ant,
            "acoustic_centroid_distance": float(acoustic[index[a], index[b]]),
            "phonetic_feature_overlap": feature_overlap(a, b),
            "merged_in_modern_hebrew": tuple(sorted((a, b))) in {
                tuple(sorted(p)) for p in HOMOPHONES},
        })

    nearest = {c: [classes[j] for j in np.argsort(acoustic[i])[1:4]]
               for i, c in enumerate(classes)}
    closest = sorted(zip(acoustic_pair, [f"{a}/{b}" for a, b in pairs]))[:12]

    out = {
        "note": "confusion structure, judged against the ants' own feature space "
                "and against Hebrew phonetics",
        "phonetics": {k: list(v) for k, v in PHONETICS.items()},
        "merged_in_modern_hebrew": sorted("/".join(sorted(p)) for p in HOMOPHONES),
        "acoustically_nearest_syllables": nearest,
        "closest_pairs": [{"pair": p, "distance": float(d)} for d, p in closest],
        "confusion_structure": per_colony,
        "minimal_pairs": minimal,
    }
    Path(args.out).write_text(json.dumps(out, indent=2), encoding="utf-8")
    for group, value in per_colony.items():
        print(f"{group:<24} rho(errors, acoustic dist)="
              f"{value['spearman_errors_vs_acoustic_distance']:+.3f}  "
              f"rho(errors, phonetic overlap)="
              f"{value['spearman_errors_vs_phonetic_overlap']:+.3f}  "
              f"closest-10 share={value['share_of_errors_on_the_10_closest_pairs']:.3f}")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
