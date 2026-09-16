"""Do the ants actually know the syllables? Five tests, all on unseen audio.

Nothing here trains anything. It reads the codebooks that were already written to
state-syllables/, encodes held-out audio the codebooks never saw, and asks whether
the resulting unit strings carry syllable identity. Quantisation error is not
reported: it is not evidence, and the prior noise-beats-speech result is why.

Controls run through the identical code path:
  * an ant trained only on the original human recordings (no curriculum),
  * codebooks of random centres, never fitted to anything,
  * codebooks of random real frames (k-means round zero, no Lloyd iterations),
  * the raw 14-dim features with no codebook at all (the ceiling),
  * duration alone (the cue that would be embarrassing to be measuring),
  * and a label-permutation null for the empirical floor.
"""
from __future__ import annotations

import argparse
import io
import json
import time
from pathlib import Path

import numpy as np

import sequence_probes as sp
from acoustic_units import dataset, load_checkpoint
from colony import DEFAULT_ANTS, DEFAULT_SEEDS

COMBINED = Path("corpus-combined")
SYLLABLE_MANIFEST = Path("corpus-syllables/manifest.json")
STATE = Path("state-syllables")
CONTROL_COLONY = "control-human-only-64"


def word_map() -> tuple[dict[str, list[str]], dict[str, str]]:
    """Word -> its letters' syllable ids, from corpus provenance (scoring only)."""
    manifest = json.loads(io.open(SYLLABLE_MANIFEST, encoding="utf-8").read())
    glyphs, spellings = {}, {}
    for entry in manifest["entries"]:
        if entry["item_kind"] == "syllable":
            glyphs[entry["glyph"]] = entry["item_id"]
        elif entry["item_kind"] == "word":
            spellings[entry["item_id"]] = entry["hebrew"]
    return ({w: sp.word_constituents(h, glyphs) for w, h in spellings.items()}, glyphs)


def descriptors(items: list[dict], key: str = "speech") -> np.ndarray:
    return np.asarray([
        np.concatenate([it[key].mean(axis=0), it[key].std(axis=0)])
        for it in items
    ], dtype=np.float64)


def loudest(x: np.ndarray, fraction: float = 0.60) -> np.ndarray:
    keep = max(1, int(round(fraction * len(x))))
    order = np.argsort(x[:, 0], kind="stable")[-keep:]
    return x[np.sort(order)]


def zscore(train: np.ndarray, test: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    mean, std = train.mean(axis=0), train.std(axis=0)
    std = np.where(std < 1e-9, 1.0, std)
    return (train - mean) / std, (test - mean) / std


def negative_distance(train: np.ndarray, test: np.ndarray) -> np.ndarray:
    return -np.sqrt(np.maximum(
        ((test[:, None, :] - train[None, :, :]) ** 2).sum(axis=2), 0.0))


class Corpus:
    def __init__(self) -> None:
        labels = sp.load_labels(COMBINED)
        t0 = time.time()
        self.train = sp.collect(COMBINED / "train", labels, "syllable")
        self.held = sp.collect(COMBINED / "heldout", labels, "syllable")
        self.words = sp.collect(COMBINED / "evaluation", labels, "word")
        self.classes = sorted({it["label"] for it in self.train})
        self.word_classes = sorted({it["label"] for it in self.words})
        self.y_train = [it["label"] for it in self.train]
        self.y_held = [it["label"] for it in self.held]
        self.base_held = [it["base"] for it in self.held]
        self.y_words = [it["label"] for it in self.words]
        self.base_words = [it["base"] for it in self.words]
        self.constituents, _ = word_map()
        for it in self.train + self.held + self.words:
            it["loud"] = loudest(it["frames"])
        train_bases = {it["base"] for it in self.train}
        held_bases = {it["base"] for it in self.held}
        self.leak_check = {
            "shared_base_renderings_train_heldout": sorted(train_bases & held_bases),
            "shared_file_names": sorted({it["name"] for it in self.train}
                                        & {it["name"] for it in self.held}),
            "identical_speech_spans": int(sum(
                1 for a in self.held for b in self.train
                if a["speech"].shape == b["speech"].shape
                and np.array_equal(a["speech"], b["speech"]))),
        }
        if any(self.leak_check.values()):
            raise ValueError(f"held-out set is not disjoint: {self.leak_check}")
        self.featurise_seconds = round(time.time() - t0, 1)
        print(f"featurised train={len(self.train)} heldout={len(self.held)} "
              f"words={len(self.words)} in {self.featurise_seconds}s", flush=True)


def score_codebook(corpus: Corpus, centers: np.ndarray, seed: int,
                   with_words: bool = True) -> dict:
    train = sp.encode_items(corpus.train, centers)
    held = sp.encode_items(corpus.held, centers)

    edit_held = sp.edit_similarity_matrix(held["sequences"], train["sequences"])
    edit_pairs = sp.edit_similarity_matrix(held["sequences"], held["sequences"])
    cosine_held = sp.cosine_similarity_matrix(held["histograms"], train["histograms"])
    cosine_pairs = sp.cosine_similarity_matrix(held["histograms"], held["histograms"])

    nn_edit = sp.nn_classify(edit_held, corpus.y_train, corpus.y_held, corpus.classes)
    nn_cos = sp.nn_classify(cosine_held, corpus.y_train, corpus.y_held, corpus.classes)

    result = {
        "units": int(len(centers)),
        "units_used_heldout": int(len({int(u) for s in held["sequences"] for u in s})),
        "mean_sequence_length": float(np.mean([len(s) for s in held["sequences"]])),
        "test1_separation": {
            "edit": sp.separation(edit_pairs, corpus.y_held, corpus.base_held),
            "cosine": sp.separation(cosine_pairs, corpus.y_held, corpus.base_held),
        },
        "test2_nearest_neighbour": {
            "edit": {k: v for k, v in nn_edit.items()
                     if k not in ("confusion", "predicted", "meanlink_predicted",
                                  "truth")},
            "cosine": {k: v for k, v in nn_cos.items()
                       if k not in ("confusion", "predicted", "meanlink_predicted",
                                    "truth")},
            "confusion_edit": nn_edit["confusion"].tolist(),
            "confusion_cosine": nn_cos["confusion"].tolist(),
            "top_confusions_edit": sp.top_confusions(nn_edit["confusion"], corpus.classes),
            "top_confusions_cosine": sp.top_confusions(nn_cos["confusion"], corpus.classes),
            "permutation_null_edit": sp.permutation_null(
                edit_held, corpus.y_train, corpus.y_held, corpus.classes, seed),
            "per_class_accuracy_cosine": {
                c: float(nn_cos["confusion"][i, i] / max(nn_cos["confusion"][i].sum(), 1))
                for i, c in enumerate(corpus.classes)},
        },
        "test3_minimal_pairs": {
            "edit": sp.minimal_pair_scores(edit_held, corpus.y_train, corpus.y_held),
            "cosine": sp.minimal_pair_scores(cosine_held, corpus.y_train, corpus.y_held),
        },
    }
    if with_words:
        words = sp.encode_items(corpus.words, centers)
        result["test4_words"] = {
            "constituent_recall_edit": sp.constituent_recall(
                words["sequences"], corpus.y_words,
                train["sequences"], corpus.y_train,
                corpus.constituents, corpus.classes),
            "identification_edit": {
                k: (v.tolist() if isinstance(v, np.ndarray) else v)
                for k, v in sp.leave_one_base_out(
                    sp.edit_similarity_matrix(words["sequences"], words["sequences"]),
                    corpus.y_words, corpus.base_words, corpus.word_classes).items()},
            "identification_cosine": {
                k: (v.tolist() if isinstance(v, np.ndarray) else v)
                for k, v in sp.leave_one_base_out(
                    sp.cosine_similarity_matrix(words["histograms"], words["histograms"]),
                    corpus.y_words, corpus.base_words, corpus.word_classes).items()},
        }
    return result


def references(corpus: Corpus) -> dict:
    """No-codebook ceiling, duration-only floor, and the sequence-free baseline."""
    raw_train, raw_held = zscore(descriptors(corpus.train), descriptors(corpus.held))
    raw = sp.nn_classify(negative_distance(raw_train, raw_held),
                         corpus.y_train, corpus.y_held, corpus.classes)
    duration_train = np.asarray([[len(it["speech"])] for it in corpus.train], float)
    duration_held = np.asarray([[len(it["speech"])] for it in corpus.held], float)
    duration = sp.nn_classify(negative_distance(duration_train, duration_held),
                              corpus.y_train, corpus.y_held, corpus.classes)
    raw_words = descriptors(corpus.words)
    raw_words = zscore(raw_words, raw_words)[0]
    word_raw = sp.leave_one_base_out(
        negative_distance(raw_words, raw_words),
        corpus.y_words, corpus.base_words, corpus.word_classes)
    loud_train, loud_held = zscore(descriptors(corpus.train, "loud"),
                                   descriptors(corpus.held, "loud"))
    loud = sp.nn_classify(negative_distance(loud_train, loud_held),
                          corpus.y_train, corpus.y_held, corpus.classes)
    return {
        "raw_features_no_codebook": {
            "note": "mean+std of the ants' own 14-dim frames over the speech span; "
                    "the most any codebook built on this feature spec could keep",
            "syllable_top1": raw["top1"], "syllable_top5": raw["top5"],
            "word_top1": word_raw["top1"], "word_top5": word_raw["top5"],
        },
        "raw_features_loudest_60_percent": {
            "note": "same features, the earlier report's pooling; kept for continuity",
            "syllable_top1": loud["top1"], "syllable_top5": loud["top5"],
        },
        "duration_only": {
            "note": "1-NN on the number of speech frames alone; if a probe scores "
                    "near this, it is measuring how long the sound is",
            "syllable_top1": duration["top1"], "syllable_top5": duration["top5"],
        },
    }


def collect_codebooks(corpus: Corpus, sizes: tuple[int, ...]) -> list[dict]:
    jobs = []
    for name in sorted(p.name for p in STATE.iterdir() if p.is_dir()):
        for ant in DEFAULT_ANTS:
            current = STATE / name / ant / "current.json"
            if not current.exists():
                continue
            checkpoint = load_checkpoint(current)
            jobs.append({
                "group": name if name != CONTROL_COLONY else "baseline-human-only",
                "kind": "trained-ant" if name != CONTROL_COLONY else "baseline-human-only",
                "ant": ant, "seed": checkpoint["seed"],
                "centers": np.asarray(checkpoint["centers"], dtype=np.float32),
                "checkpoint_sha256": checkpoint["checkpoint_sha256"],
            })
    train_x, _ = dataset(COMBINED / "train")
    mean, std = train_x.mean(axis=0), train_x.std(axis=0)
    for units in sizes:
        for ant, seed in zip(DEFAULT_ANTS, DEFAULT_SEEDS):
            rng = np.random.default_rng(seed + 100_000)
            jobs.append({
                "group": f"random-centres-{units}", "kind": "random-centres",
                "ant": ant, "seed": seed,
                "centers": (mean + std * rng.standard_normal((units, train_x.shape[1]))
                            ).astype(np.float32),
                "checkpoint_sha256": None,
            })
            rng = np.random.default_rng(seed)
            jobs.append({
                "group": f"random-real-frames-{units}", "kind": "random-real-frames",
                "ant": ant, "seed": seed,
                "centers": train_x[rng.choice(len(train_x), units, replace=False)].copy(),
                "checkpoint_sha256": None,
            })
    return jobs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="reports/syllable-knowledge.json")
    parser.add_argument("--sizes", default="64,128,256,512")
    args = parser.parse_args()
    sizes = tuple(int(s) for s in args.sizes.split(","))

    corpus = Corpus()
    report = {
        "question": "do the ants produce a consistent, distinct unit string per syllable",
        "metric_policy": "discrimination on unseen audio; quantisation error is not "
                         "reported because it does not rank ants on this task",
        "chance_syllable": 1 / len(corpus.classes),
        "chance_word": 1 / len(corpus.word_classes),
        "heldout_items": len(corpus.held),
        "train_items": len(corpus.train),
        "word_items": len(corpus.words),
        "classes": corpus.classes,
        "word_classes": corpus.word_classes,
        "constituents": corpus.constituents,
        "leak_check": corpus.leak_check,
        "references": references(corpus),
        "codebooks": [],
    }
    print(json.dumps(report["references"], indent=2), flush=True)

    for job in collect_codebooks(corpus, sizes):
        t0 = time.time()
        scored = score_codebook(corpus, job["centers"], job["seed"])
        scored.update({k: job[k] for k in ("group", "kind", "ant", "seed",
                                           "checkpoint_sha256")})
        scored["seconds"] = round(time.time() - t0, 1)
        report["codebooks"].append(scored)
        print(f"{job['group']:<26} {job['ant']} k={scored['units']:<4} "
              f"edit@1={scored['test2_nearest_neighbour']['edit']['top1']:.3f} "
              f"cos@1={scored['test2_nearest_neighbour']['cosine']['top1']:.3f} "
              f"sep={scored['test1_separation']['edit']['separation']:.3f} "
              f"word@1={scored['test4_words']['identification_edit']['top1']:.3f} "
              f"({scored['seconds']}s)", flush=True)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
