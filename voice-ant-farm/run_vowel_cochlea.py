"""Does a better cochlea let the ants master the open vowels (ah, aa)?

Iddo's autonomy law (2026-08-11): the ants must learn by themselves, from the
same uncurated environment. What MAY evolve is the organism — its ear. This
run therefore changes exactly one thing: the frame feature vector (the
cochlea). Nothing about the diet changes: the training frame pool is the same
uncurated corpus-combined/train folder, the reference frames are drawn
uniformly at random with the same seeds, and no label ever enters a feature,
a codebook, or a sampling decision.

The new cochlea is `recommended26` (mfcc20_mel26_pd6w4), which was selected in
state-hebbian/feature-selection.json by leave-one-base-out cross-validation
INSIDE the train split only — the held-out split was never read by that
selection. It is not a vowel hack; it is the ear the farm's own prior work
already chose without looking at the answers.

Everything downstream is the published protocol, byte for byte:
  * run_knowledge_tests.Corpus       — same splits, same leak check
  * sequence_probes.speech_span      — frame selection FROZEN from the legacy
                                       log-energy column for every arm, so no
                                       cochlea gets to choose its own frames
  * run_knowledge_tests.score_codebook — same five tests, same metrics
  * codebook kind = random-real-frames — the published champion kind; the
    SAME frame indices are drawn for every arm (same seed, same pool length),
    so each arm holds the same physical 25 ms slices of the same audio and
    only the representation differs. This is a matched control, not a sweep.

Arms:
  baseline-legacy14        the published cochlea; must reproduce
                           reports/syllable-knowledge.json exactly
  vowel-cochlea26          recommended26, unweighted Euclidean
  vowel-cochlea26-scaled   recommended26 / per-dimension std of the ant's own
                           uncurated train pool (the open question flagged in
                           feature_space.variance_scaler: c1 alone holds ~50%
                           of the variance and dominates unweighted k-means
                           geometry the way log-energy dominated legacy14)

Quantisation error is not reported. Labels are a scoring key only.

    py -3.13 run_vowel_cochlea.py
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
from colony import DEFAULT_ANTS, DEFAULT_SEEDS
from run_knowledge_tests import (COMBINED, Corpus, descriptors,
                                 negative_distance, score_codebook, zscore)

OUT = Path("reports/vowel-cochlea-knowledge.json")
COCHLEA = "recommended26"          # == mfcc20_mel26_pd6w4, the CV-selected ear
KEY_SYLLABLES = ("ah", "aa", "za", "ya", "na", "ma", "la", "ra")


def v2_featurise(corpus: Corpus) -> None:
    """Attach recommended26 features to every corpus item.

    The speech span is recomputed from the item's stored legacy frames — the
    identical sp.speech_span call the published run made — so frame selection
    stays frozen and shared across arms.
    """
    t0 = time.time()
    for folder, items in ((COMBINED / "train", corpus.train),
                          (COMBINED / "heldout", corpus.held),
                          (COMBINED / "evaluation", corpus.words)):
        by_name = {it["name"]: it for it in items}
        for path in sorted(folder.glob("*.wav")):
            it = by_name.get(path.name)
            if it is None:
                continue
            audio = load_wav(path)
            samples = resample_samples(audio.samples, audio.rate, EXEMPLAR_RATE)
            x = F.extract(COCHLEA, samples).astype(np.float32)
            if len(x) != len(it["frames"]):
                raise ValueError(f"{path.name}: frame count mismatch "
                                 f"{len(x)} != {len(it['frames'])}")
            a, b = sp.speech_span(it["frames"])   # frozen legacy span
            it["v2_frames"] = x
            it["v2_speech"] = x[a:b]
    missing = [it["name"] for it in corpus.train + corpus.held + corpus.words
               if "v2_speech" not in it]
    if missing:
        raise ValueError(f"no v2 features for {missing[:5]}")
    print(f"v2 featurised in {time.time() - t0:.1f}s", flush=True)


def train_pools() -> tuple[np.ndarray, np.ndarray]:
    """Frame pools over the FULL files of the uncurated train folder.

    Reproduces acoustic_units.dataset exactly (same order, same pcm-hash
    dedup, whole files including room tone) so the random-real-frames draw
    lands on the same physical frames in both feature spaces.
    """
    legacy_frames, v2_frames, hashes = [], [], set()
    from acoustic_units import features as legacy_features
    for path in sorted((COMBINED / "train").glob("*.wav")):
        audio = load_wav(path)
        if audio.pcm_sha256 in hashes:
            continue
        hashes.add(audio.pcm_sha256)
        legacy_frames.append(legacy_features(audio)[0])
        samples = resample_samples(audio.samples, audio.rate, EXEMPLAR_RATE)
        v2_frames.append(F.extract(COCHLEA, samples).astype(np.float32))
    legacy_pool = np.concatenate(legacy_frames)
    v2_pool = np.concatenate(v2_frames)
    if len(legacy_pool) != len(v2_pool):
        raise ValueError("pools disagree on frame count")
    return legacy_pool, v2_pool


def with_speech(corpus: Corpus, key: str):
    """Point every item's 'speech' at the arm's features (restored by caller)."""
    for it in corpus.train + corpus.held + corpus.words:
        it["speech"] = it[key] if key != "legacy" else it["frames"][
            slice(*sp.speech_span(it["frames"]))]


def v2_raw_ceiling(corpus: Corpus) -> dict:
    """No-codebook 1-NN on mean+std of the v2 speech span: the new ceiling."""
    def desc(items):
        return np.asarray([np.concatenate([it["v2_speech"].mean(axis=0),
                                           it["v2_speech"].std(axis=0)])
                           for it in items], dtype=np.float64)
    a, b = zscore(desc(corpus.train), desc(corpus.held))
    nn = sp.nn_classify(negative_distance(a, b), corpus.y_train,
                        corpus.y_held, corpus.classes)
    conf = nn["confusion"]
    per_class = {c: f"{int(conf[i, i])}/{int(conf[i].sum())}"
                 for i, c in enumerate(corpus.classes)}
    return {"note": "mean+std of recommended26 over the frozen speech span, "
                    "train-fitted z-score, 1-NN; the most any codebook on "
                    "this cochlea could keep",
            "syllable_top1": nn["top1"], "syllable_top5": nn["top5"],
            "per_class": per_class}


def per_syllable(scored: dict, classes: list[str]) -> dict:
    conf_edit = np.asarray(scored["test2_nearest_neighbour"]["confusion_edit"])
    conf_cos = np.asarray(scored["test2_nearest_neighbour"]["confusion_cosine"])
    out = {}
    for i, c in enumerate(classes):
        out[c] = {"edit": f"{int(conf_edit[i, i])}/{int(conf_edit[i].sum())}",
                  "cosine": f"{int(conf_cos[i, i])}/{int(conf_cos[i].sum())}"}
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(OUT))
    parser.add_argument("--sizes", default="256,512")
    args = parser.parse_args()
    sizes = tuple(int(s) for s in args.sizes.split(","))

    corpus = Corpus()                     # published featurisation + leak check
    v2_featurise(corpus)
    legacy_pool, v2_pool = train_pools()
    scaler = np.maximum(v2_pool.astype(np.float64).std(axis=0), 1e-6
                        ).astype(np.float32)
    print(f"train frame pool: {len(legacy_pool)} frames "
          f"(legacy dim {legacy_pool.shape[1]}, v2 dim {v2_pool.shape[1]})",
          flush=True)

    arms = [
        {"group": "baseline-legacy14", "speech_key": "legacy",
         "pool": legacy_pool, "scale": None,
         "note": "published cochlea; reproduction check against "
                 "reports/syllable-knowledge.json random-real-frames"},
        {"group": "vowel-cochlea26", "speech_key": "v2_speech",
         "pool": v2_pool, "scale": None,
         "note": f"{COCHLEA}, unweighted Euclidean"},
        {"group": "vowel-cochlea26-scaled", "speech_key": "v2_speech",
         "pool": v2_pool, "scale": scaler,
         "note": f"{COCHLEA} / per-dim std of the ant's own uncurated "
                 "train pool (feature_space.variance_scaler)"},
    ]

    report = {
        "question": "does evolving the ants' cochlea (not their diet) fix the "
                    "open vowels ah and aa",
        "autonomy_law": "Iddo 2026-08-11: learning stays fully autonomous. No "
                        "curated data, no vowel-weighted sampling. Only the "
                        "organism's ear evolves; the environment is untouched.",
        "cochlea_selection_basis": "state-hebbian/feature-selection.json — "
                                   "mean rank over 8 train-only CV columns; "
                                   "held-out split never read by the selection",
        "metric_policy": "discrimination on unseen audio; quantisation error "
                         "is not reported",
        "codebook_kind": "random-real-frames — same seed, same pool length, "
                         "therefore same physical frames drawn for every arm",
        "chance_syllable": 1 / len(corpus.classes),
        "heldout_items": len(corpus.held),
        "train_items": len(corpus.train),
        "word_items": len(corpus.words),
        "classes": corpus.classes,
        "leak_check": corpus.leak_check,
        "v2_raw_ceiling": None,
        "codebooks": [],
    }

    report["v2_raw_ceiling"] = v2_raw_ceiling(corpus)
    print("v2 raw ceiling:", report["v2_raw_ceiling"]["syllable_top1"], flush=True)

    for arm in arms:
        with_speech(corpus, arm["speech_key"])
        if arm["scale"] is not None:
            for it in corpus.train + corpus.held + corpus.words:
                it["speech"] = it["speech"] / arm["scale"]
        for units in sizes:
            for ant, seed in zip(DEFAULT_ANTS, DEFAULT_SEEDS):
                rng = np.random.default_rng(seed)
                idx = rng.choice(len(arm["pool"]), units, replace=False)
                centers = arm["pool"][idx].copy()
                if arm["scale"] is not None:
                    centers = centers / arm["scale"]
                t0 = time.time()
                scored = score_codebook(corpus, centers, seed)
                scored.update({
                    "group": f"{arm['group']}-{units}",
                    "kind": arm["group"], "ant": ant, "seed": seed,
                    "note": arm["note"],
                    "per_syllable": per_syllable(scored, corpus.classes),
                    "seconds": round(time.time() - t0, 1),
                })
                report["codebooks"].append(scored)
                key = {c: scored["per_syllable"][c]["edit"]
                       for c in KEY_SYLLABLES}
                print(f"{scored['group']:<28} {ant} "
                      f"edit@1={scored['test2_nearest_neighbour']['edit']['top1']:.3f} "
                      f"cos@1={scored['test2_nearest_neighbour']['cosine']['top1']:.3f} "
                      f"ah={key['ah']} aa={key['aa']} za={key['za']} "
                      f"ya={key['ya']} na={key['na']} "
                      f"({scored['seconds']}s)", flush=True)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False),
                   encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
