"""Train and score the predictive-coding learner against the baselines that matter.

The two numbers this run has to beat are, from reports/syllable-knowledge.json,
mean over the four ants at k=256 on the same 132 held-out syllable tokens:

    trained k-means 256 ......... 41.9%   (cosine over unit histograms, 1-NN)
    random REAL frames 256 ...... 40.3%   (p = 0.54 against it -- the real bar)

Beating k-means without beating random real frames would mean nothing, so both
are recomputed here, from scratch, through the identical code path, rather than
quoted.  Two further controls isolate the feature change from the learner
change:

    kmeans-legacy14      reproduces the published 41.9%
    randframes-legacy14  reproduces the published 40.3%
    kmeans-rec26         same optimiser, new features  -- the feature effect
    randframes-rec26     no optimiser, new features    -- the honest bar
    predictive-rec26     the learner                   -- the learner effect

Downstream of `encode` nothing varies: run-length-collapsed unit strings,
unit histograms, cosine and edit 1-NN, sequence_probes.nn_classify and
sequence_probes.minimal_pair_scores -- the same functions that produced every
other number in this project.  Frame selection is the frozen speech span
computed from the legacy log-energy column, identical for every arm.

Quantisation error is not computed anywhere in this file, on purpose.

    py -3.13 run_predictive.py --cv        # hyperparameters, train split only
    py -3.13 run_predictive.py             # one shot on held-out
    py -3.13 run_predictive.py --big       # 40.6 h corpus, subsampled
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

import feature_space as F
import predictive_units as P
import sequence_probes as sp
from acoustic_units import (EXEMPLAR_RATE, dataset, load_checkpoint, load_wav,
                            resample_samples)
from colony import DEFAULT_ANTS, DEFAULT_SEEDS
from paired_tests import mcnemar

ROOT = Path(__file__).resolve().parent
COMBINED = ROOT / "corpus-combined"
BIG = ROOT / "corpus-big" / "human"
OUT = ROOT / "state-hebbian" / "predictive"
UNITS = 256


# --------------------------------------------------------------------------
# evaluation corpus: frames in every feature space, one frozen speech span
# --------------------------------------------------------------------------

def collect(folder: Path, labels: dict, sets: tuple[str, ...]) -> list[dict]:
    """Featurise the syllable audio once per feature set.

    The speech span is computed from `legacy14`'s log-energy column and reused
    verbatim for every feature set and every arm, so no arm gets to choose its
    own frames.  Same rule as feature_bakeoff.py.
    """
    items = []
    for path in sorted(folder.glob("*.wav")):
        record = labels.get(path.name)
        if record is None or record.get("item_kind") != "syllable":
            continue
        audio = load_wav(path)
        samples = resample_samples(audio.samples, audio.rate, EXEMPLAR_RATE)
        legacy = F.extract("legacy14", samples)
        a, b = sp.speech_span(legacy)
        item = {"name": path.name, "label": record["item_id"],
                "base": record.get("base_rendering_id")}
        for name in sets:
            x = legacy if name == "legacy14" else F.extract(name, samples)
            item[name] = np.asarray(x[a:b], dtype=np.float64)
        items.append(item)
    if not items:
        raise ValueError(f"no syllable audio in {folder}")
    return items


def sequences(items: list[dict], book: P.PredictiveCodebook,
              feature_set: str) -> dict:
    k = book.k
    seqs, hist = [], np.zeros((len(items), k), dtype=np.float64)
    for i, it in enumerate(items):
        ids = book.assign(it[feature_set])
        seqs.append(sp.collapse(ids))
        counts = np.bincount(ids, minlength=k).astype(np.float64)
        hist[i] = counts / max(counts.sum(), 1.0)
    return {"sequences": seqs, "histograms": hist,
            "units_used": int(len({int(u) for s in seqs for u in s}))}


def score(train: list[dict], held: list[dict], book: P.PredictiveCodebook,
          feature_set: str, classes: list[str], seed: int) -> dict:
    a = sequences(train, book, feature_set)
    b = sequences(held, book, feature_set)
    y_train = [it["label"] for it in train]
    y_held = [it["label"] for it in held]
    base_held = [it["base"] for it in held]

    cos = sp.cosine_similarity_matrix(b["histograms"], a["histograms"])
    edit = sp.edit_similarity_matrix(b["sequences"], a["sequences"])
    nn_cos = sp.nn_classify(cos, y_train, y_held, classes)
    nn_edit = sp.nn_classify(edit, y_train, y_held, classes)
    pairs_cos = sp.minimal_pair_scores(cos, y_train, y_held)
    pairs_edit = sp.minimal_pair_scores(edit, y_train, y_held)
    within = sp.separation(sp.cosine_similarity_matrix(b["histograms"],
                                                       b["histograms"]),
                           y_held, base_held)
    return {
        "units": book.k,
        "units_used_heldout": b["units_used"],
        "dead_units_heldout": book.k - b["units_used"],
        "dead_units_train": book.k - a["units_used"],
        "mean_sequence_length": float(np.mean([len(s) for s in b["sequences"]])),
        "cosine": {
            "top1": nn_cos["top1"], "top5": nn_cos["top5"],
            "meanlink_top1": nn_cos["meanlink_top1"],
            "minimal_pairs": {p["pair"]: p["accuracy"] for p in pairs_cos},
            "minimal_pairs_full": pairs_cos,
            "permutation_null_top1": sp.permutation_null(cos, y_train, y_held,
                                                         classes, seed),
            "heldout_pair_auc": within["auc"],
            "heldout_pair_cohens_d": within["cohens_d"],
        },
        "edit": {
            "top1": nn_edit["top1"], "top5": nn_edit["top5"],
            "meanlink_top1": nn_edit["meanlink_top1"],
            "minimal_pairs": {p["pair"]: p["accuracy"] for p in pairs_edit},
        },
        "_correct_cosine": nn_cos["predicted"] == nn_cos["truth"],
        "_correct_edit": nn_edit["predicted"] == nn_edit["truth"],
    }


def cross_validate(train: list[dict], book: P.PredictiveCodebook,
                   feature_set: str, classes: list[str]) -> dict:
    """Leave-one-base-rendering-out inside the train split.  Hyperparameters
    are chosen here; the held-out split is not read during selection."""
    enc = sequences(train, book, feature_set)
    labels = [it["label"] for it in train]
    bases = [it["base"] for it in train]
    folds = sorted({b.rsplit("/", 1)[-1] for b in bases})
    top1, pair_hits, pair_total = [], {}, {}
    for fold in folds:
        test = np.asarray([b.endswith("/" + fold) for b in bases])
        if not test.any() or test.all():
            continue
        tr = np.flatnonzero(~test)
        te = np.flatnonzero(test)
        s = sp.cosine_similarity_matrix(enc["histograms"][te],
                                        enc["histograms"][tr])
        y_tr = [labels[i] for i in tr]
        y_te = [labels[i] for i in te]
        top1.append(sp.nn_classify(s, y_tr, y_te, classes)["top1"])
        for p in sp.minimal_pair_scores(s, y_tr, y_te):
            pair_hits[p["pair"]] = pair_hits.get(p["pair"], 0) + p["correct"]
            pair_total[p["pair"]] = pair_total.get(p["pair"], 0) + p["items"]
    return {
        "folds": len(top1),
        "top1": float(np.mean(top1)),
        "top1_std_over_folds": float(np.std(top1)),
        "minimal_pairs": {k: pair_hits[k] / pair_total[k] for k in pair_hits},
        "all_pairs_pooled": float(sum(pair_hits.values()) / sum(pair_total.values())),
        "dead_units_train": book.k - enc["units_used"],
    }


# --------------------------------------------------------------------------
# arms
# --------------------------------------------------------------------------

def frozen(centers: np.ndarray, feature_set: str) -> P.PredictiveCodebook:
    """Wrap a codebook that was not fitted here (published centres, raw space).

    mean = 0, scale = 1: `assign` is then exactly the legacy
    `acoustic_units.encode`, so the published numbers must come back unchanged.
    """
    centers = np.asarray(centers, dtype=np.float64)
    d = centers.shape[1]
    return P.PredictiveCodebook(
        mean=np.zeros(d), scale=np.ones(d), centers=centers,
        weights=np.zeros((len(centers), d, d + 1)), feature_set=feature_set,
        delta=0, history=[])


def published(arm: str, ant: str, seed: int, units: int) -> P.PredictiveCodebook:
    """The two bars, reproduced rather than quoted.

    `published-kmeans` reads the checkpoint that produced 41.9%.
    `published-randframes` redraws the 40.3% control with the same generator,
    the same corpus loader and the same seed as run_knowledge_tests.py.
    """
    if arm == "published-kmeans":
        path = ROOT / "state-syllables" / str(units) / ant / "current.json"
        checkpoint = load_checkpoint(path)
        return frozen(np.asarray(checkpoint["centers"], dtype=np.float32), "legacy14")
    if arm == "published-randframes":
        global _LEGACY_RAW
        if _LEGACY_RAW is None:
            _LEGACY_RAW = dataset(COMBINED / "train")[0]
        rng = np.random.default_rng(seed)
        picks = rng.choice(len(_LEGACY_RAW), units, replace=False)
        return frozen(_LEGACY_RAW[picks].copy(), "legacy14")
    raise ValueError(arm)


_LEGACY_RAW = None


def build(arm: str, corpora: dict, seed: int, units: int, cfg: dict,
          verbose: bool, ant: str = "") -> tuple[P.PredictiveCodebook, str, float]:
    if arm.startswith("published-"):
        t0 = time.time()
        return published(arm, ant, seed, units), "legacy14", time.time() - t0
    kind, feature_set = arm.rsplit("-", 1)
    corpus = corpora[feature_set]
    t0 = time.time()
    if kind == "predictive":
        book = P.fit(corpus, units, seed, verbose=verbose, **cfg)
    elif kind == "shuffled":
        book = P.fit(corpus, units, seed, verbose=verbose, shuffle_targets=True,
                     **cfg)
    elif kind == "kmeans":
        book = P.fit_kmeans(corpus, units, seed, rounds=cfg.get("rounds", 12),
                            delta=cfg.get("delta", 3),
                            max_pairs=cfg.get("max_pairs"), verbose=verbose)
    elif kind == "randframes":
        book = P.fit_random_frames(corpus, units, seed, delta=cfg.get("delta", 3),
                                   max_pairs=cfg.get("max_pairs"))
    else:
        raise ValueError(f"unknown arm {arm}")
    return book, feature_set, time.time() - t0


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cv", action="store_true",
                        help="leave-one-base-out inside train only; no held-out")
    parser.add_argument("--big", action="store_true",
                        help="train on corpus-big/human (40.6 h, subsampled)")
    parser.add_argument("--arms", default="")
    parser.add_argument("--units", type=int, default=UNITS)
    parser.add_argument("--beta", type=float, default=1.0)
    parser.add_argument("--delta", type=int, default=3)
    parser.add_argument("--rounds", type=int, default=12)
    parser.add_argument("--candidates", type=int, default=8)
    parser.add_argument("--negatives", type=int, default=256)
    parser.add_argument("--tau", type=float, default=1.0)
    parser.add_argument("--ridge", type=float, default=1.0)
    parser.add_argument("--predictor", default="linear",
                        choices=("linear", "constant"))
    parser.add_argument("--max-pairs", type=int, default=None)
    parser.add_argument("--files", type=int, default=None,
                        help="subsample this many training FILES (--big)")
    parser.add_argument("--exemplars", action="store_true",
                        help="also learn one waveform exemplar per unit")
    parser.add_argument("--exemplar-arms", default="predictive",
                        help="comma-separated arm prefixes that get exemplars "
                             "and a saved checkpoint")
    parser.add_argument("--tag", default="")
    parser.add_argument("--out", default="")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    default_arms = ("published-kmeans", "published-randframes",
                    "kmeans-legacy14", "randframes-legacy14",
                    "kmeans-mfcc20_mel26_pd6w4", "randframes-mfcc20_mel26_pd6w4",
                    "shuffled-mfcc20_mel26_pd6w4",
                    "predictive-mfcc20_mel26_pd6w4")
    arms = tuple(a.strip() for a in args.arms.split(",") if a.strip()) or default_arms
    sets = tuple(dict.fromkeys("legacy14" if a.startswith("published-")
                               else a.rsplit("-", 1)[1] for a in arms))
    cfg = {"beta": args.beta, "delta": args.delta, "rounds": args.rounds,
           "candidates": args.candidates, "negatives": args.negatives,
           "tau": args.tau, "ridge": args.ridge, "max_pairs": args.max_pairs,
           "predictor": args.predictor}

    t0 = time.time()
    train_folder = (BIG / "train") if args.big else (COMBINED / "train")
    print(f"training audio: {train_folder}"
          + (f"  (subsampled to {args.files} files)" if args.files else ""),
          flush=True)
    corpora = {}
    for name in sets:
        c = P.load_frames([train_folder], name, limit_files=args.files, seed=104729,
                          progress=True)
        corpora[name] = c
        print(f"  {name:<24} {c.n:>9} frames from {len(c.paths)} files "
              f"({c.seconds / 3600:.2f} h)  {time.time() - t0:.0f}s", flush=True)

    labels = sp.load_labels(COMBINED)
    train = collect(COMBINED / "train", labels, sets)
    held = None if args.cv else collect(COMBINED / "heldout", labels, sets)
    classes = sorted({it["label"] for it in train})
    if held is not None:
        assert {it["name"] for it in train}.isdisjoint({it["name"] for it in held})
        assert {it["base"] for it in train}.isdisjoint({it["base"] for it in held})
    print(f"eval: train={len(train)} heldout={len(held) if held else 0} "
          f"classes={len(classes)} chance={1 / len(classes):.3f}  "
          f"({time.time() - t0:.0f}s)\n", flush=True)

    header = ("arm", "top1", "ba/pa", "da/ta", "8-pair", "dead", "train s")
    print(f"{header[0]:<30}{'ant':<7}{header[1]:>7}{header[2]:>8}{header[3]:>8}"
          f"{header[4]:>8}{header[5]:>6}{header[6]:>9}", flush=True)

    keep = tuple(a.strip() for a in args.exemplar_arms.split(",") if a.strip())
    rows = []
    for arm in arms:
        per_ant = []
        store = args.exemplars and arm.startswith(keep)
        for ant, seed in zip(DEFAULT_ANTS, DEFAULT_SEEDS):
            book, feature_set, seconds = build(arm, corpora, seed, args.units, cfg,
                                               args.verbose, ant)
            if store:
                P.learn_exemplars(book, [train_folder], limit_files=args.files,
                                  seed=104729)
            record = {"ant": ant, "seed": seed, "train_seconds": round(seconds, 1),
                      "history": book.history}
            if args.cv:
                record["cv"] = cross_validate(train, book, feature_set, classes)
                r = record["cv"]
                print(f"{arm:<30}{ant:<7}{r['top1'] * 100:6.1f}%"
                      f"{r['minimal_pairs'].get('ba/pa', 0) * 100:7.1f}%"
                      f"{r['minimal_pairs'].get('da/ta', 0) * 100:7.1f}%"
                      f"{r['all_pairs_pooled'] * 100:7.1f}%"
                      f"{r['dead_units_train']:6d}{seconds:8.1f}s", flush=True)
            else:
                record["heldout"] = score(train, held, book, feature_set, classes,
                                          seed)
                r = record["heldout"]
                print(f"{arm:<30}{ant:<7}{r['cosine']['top1'] * 100:6.1f}%"
                      f"{r['cosine']['minimal_pairs'].get('ba/pa', 0) * 100:7.1f}%"
                      f"{r['cosine']['minimal_pairs'].get('da/ta', 0) * 100:7.1f}%"
                      f"{np.mean(list(r['cosine']['minimal_pairs'].values())) * 100:7.1f}%"
                      f"{r['dead_units_heldout']:6d}{seconds:8.1f}s", flush=True)
            if store:
                P.save(book, OUT / (args.tag or "run") / arm / f"{ant}.json",
                       extra={"arm": arm, "ant": ant, "seed": seed,
                              "units": args.units, "config": cfg})
            per_ant.append(record)
        rows.append({"arm": arm, "units": args.units, "config": cfg,
                     "ants": per_ant})
        summarise(rows[-1], args.cv)
        print("", flush=True)

    if not args.cv:
        pairwise(rows)
    out = Path(args.out) if args.out else (
        OUT / f"predictive-{'cv' if args.cv else 'heldout'}"
              f"{'-big' if args.big else ''}{('-' + args.tag) if args.tag else ''}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "question": "does a predictive-coding objective beat random real frames",
        "bar": {"trained_kmeans_256_published": 0.419,
                "random_real_frames_256_published": 0.403,
                "raw_features_no_codebook_published": 0.538,
                "chance": 1 / len(classes)},
        "protocol": ("frozen speech span from the legacy log-energy column; "
                     "run-length-collapsed unit strings; cosine 1-NN over unit "
                     "histograms; identical downstream code for every arm"),
        "metric_policy": "quantisation error is not computed in this file",
        "training_audio": str(train_folder),
        "training_frames": {k: int(v.n) for k, v in corpora.items()},
        "training_hours": {k: round(v.seconds / 3600, 3) for k, v in corpora.items()},
        "classes": classes,
        "results": rows,
        "total_seconds": round(time.time() - t0, 1),
    }
    out.write_text(json.dumps(strip(payload), indent=2, ensure_ascii=False),
                   encoding="utf-8")
    print(f"wrote {out}  ({time.time() - t0:.0f}s total)")


def summarise(row: dict, cv: bool) -> None:
    key = "cv" if cv else "heldout"
    if cv:
        top1 = [a[key]["top1"] for a in row["ants"]]
        pairs = [a[key]["minimal_pairs"] for a in row["ants"]]
        dead = [a[key]["dead_units_train"] for a in row["ants"]]
    else:
        top1 = [a[key]["cosine"]["top1"] for a in row["ants"]]
        pairs = [a[key]["cosine"]["minimal_pairs"] for a in row["ants"]]
        dead = [a[key]["dead_units_heldout"] for a in row["ants"]]
    row["mean_top1"] = float(np.mean(top1))
    row["std_top1"] = float(np.std(top1))
    row["mean_ba_pa"] = float(np.mean([p.get("ba/pa", 0) for p in pairs]))
    row["mean_da_ta"] = float(np.mean([p.get("da/ta", 0) for p in pairs]))
    row["mean_all_pairs"] = float(np.mean([np.mean(list(p.values())) for p in pairs]))
    row["mean_dead_units"] = float(np.mean(dead))
    row["mean_train_seconds"] = float(np.mean([a["train_seconds"] for a in row["ants"]]))
    print(f"{'  MEAN ' + row['arm']:<37}{row['mean_top1'] * 100:6.1f}%"
          f"{row['mean_ba_pa'] * 100:7.1f}%{row['mean_da_ta'] * 100:7.1f}%"
          f"{row['mean_all_pairs'] * 100:7.1f}%{row['mean_dead_units']:6.0f}"
          f"{row['mean_train_seconds']:8.1f}s", flush=True)


def pairwise(rows: list[dict]) -> None:
    """Exact McNemar on the pooled per-item decisions, ant matched to ant.

    The four ants are scored on the SAME 132 held-out tokens, so an unpaired
    comparison of means overstates the uncertainty.  Pooling the four ants'
    528 decisions is not four independent samples either; both the pooled test
    and the per-ant tests are reported so neither can be quoted alone.
    """
    for row in rows:
        row["_mask"] = np.concatenate([a["heldout"]["_correct_cosine"]
                                       for a in row["ants"]])
    for row in rows:
        row["mcnemar_vs"] = {}
        for other in rows:
            if other is row:
                continue
            pooled = mcnemar(row["_mask"], other["_mask"])
            per_ant = [mcnemar(a["heldout"]["_correct_cosine"],
                               b["heldout"]["_correct_cosine"])
                       for a, b in zip(row["ants"], other["ants"])]
            row["mcnemar_vs"][other["arm"]] = {
                "pooled_528_decisions": pooled,
                "per_ant_p_values": [p["p_value"] for p in per_ant],
            }


def strip(value):
    if isinstance(value, dict):
        return {k: strip(v) for k, v in value.items() if not k.startswith("_")}
    if isinstance(value, list):
        return [strip(v) for v in value]
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    return value


if __name__ == "__main__":
    main()
