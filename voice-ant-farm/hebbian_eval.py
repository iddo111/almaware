"""Score the Hebbian map against the only two baselines that matter.

    trained k-means 256 ............ 41.9%   (22-way held-out top-1, cosine)
    RANDOM REAL FRAMES 256 ......... 40.3%   <- the one that decides it

Beating k-means is meaningless without beating random real frames, so every run
here builds both controls with the *same seed*, over the *same frames*, in the
*same feature space* as the learner under test.  The Hebbian map is even
initialised from those very frames, so at step zero it IS the random-real-frames
control and any difference afterwards is the learning rule alone.

Nothing here is rewritten that already existed: the probes are
`sequence_probes` (batched Levenshtein, cosine over unit histograms, 1-NN,
minimal pairs, separation/AUC, permutation null), the item collection and the
frozen speech-span selection are `feature_bakeoff`'s, and the paired test is
`paired_tests.mcnemar`.

Three modes:
    --legacy      replicate the published legacy14 numbers through this harness,
                  so the harness itself is validated before it is believed.
    --cv          leave-one-base-rendering-out INSIDE the 396 train items, with
                  the codebook refitted on each fold's training audio only.
                  This is the only mode allowed to choose a configuration.
    (default)     one shot on held-out, all controls, paired McNemar.

Quantisation error is not computed anywhere in this file, on purpose.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

import feature_space as F
import sequence_probes as sp
from acoustic_units import EXEMPLAR_RATE, load_checkpoint, load_wav, resample_samples
from confusion_analysis import feature_overlap, spearman
from hebbian import (
    DEFAULT_ANTS, DEFAULT_SEEDS, HebbianMap, grid_shape, grid_sqdist, sqdist,
    featurise_folders, load_hebbian as H_load, topology_report as H_topology,
)
from paired_tests import mcnemar

ROOT = Path(__file__).resolve().parent
COMBINED = ROOT / "corpus-combined"
LEGACY_STATE = ROOT / "state-syllables"
OUT_DIR = ROOT / "state-hebbian" / "hebbian"


# ---------------------------------------------------------------------------
# corpus
# ---------------------------------------------------------------------------

def collect(folder: Path, labels: dict, kinds: tuple[str, ...]) -> list[dict]:
    """Load audio once.  The speech span is frozen, from the legacy log-energy
    column, exactly as `feature_bakeoff.collect` computes it -- so no feature
    space or codebook gets to choose its own frames."""
    items = []
    for path in sorted(folder.glob("*.wav")):
        record = labels.get(path.name)
        if record is None or record.get("item_kind") not in kinds:
            continue
        audio = load_wav(path)
        samples = resample_samples(audio.samples, audio.rate, EXEMPLAR_RATE)
        a, b = sp.speech_span(F.extract("legacy14", samples))
        items.append({"name": path.name, "kind": record["item_kind"],
                      "label": record.get("item_id"),
                      "base": record.get("base_rendering_id"),
                      "samples": samples, "span": slice(a, b)})
    return items


def featurise(items: list[dict], feature_set: str) -> None:
    for it in items:
        full = F.extract(feature_set, it["samples"])
        it["full"] = full
        it["x"] = full[it["span"]]


# ---------------------------------------------------------------------------
# codebooks
# ---------------------------------------------------------------------------

def kmeans(x: np.ndarray, k: int, seed: int, rounds: int = 30,
           block: int = 8192) -> np.ndarray:
    """Lloyd's algorithm, blocked so 26 dims x 50k frames fits in memory.

    Same contract as `acoustic_units.fit_codebook` -- same seeded init from
    random real frames, same fixed-point stop -- just not materialising the
    (n, k, d) difference tensor.
    """
    rng = np.random.default_rng(seed)
    centers = x[rng.choice(len(x), k, replace=False)].copy()
    for _ in range(rounds):
        total = np.zeros_like(centers)
        count = np.zeros(k, dtype=np.int64)
        for start in range(0, len(x), block):
            piece = x[start:start + block]
            ids = sqdist(piece, centers).argmin(axis=1)
            np.add.at(total, ids, piece)
            count += np.bincount(ids, minlength=k)
        updated = np.where(count[:, None] > 0, total / np.maximum(count, 1)[:, None],
                           centers)
        if np.allclose(updated, centers, atol=1e-5):
            centers = updated
            break
        centers = updated
    return centers


def random_real_frames(x: np.ndarray, k: int, seed: int) -> np.ndarray:
    return x[np.random.default_rng(seed).choice(len(x), k, replace=False)].copy()


def random_gaussian(x: np.ndarray, k: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed + 100_000)
    return x.mean(axis=0) + x.std(axis=0) * rng.standard_normal((k, x.shape[1]))


# ---------------------------------------------------------------------------
# probes
# ---------------------------------------------------------------------------

def encode_items(items: list[dict], centers: np.ndarray, scale: np.ndarray
                 ) -> tuple[list[np.ndarray], np.ndarray]:
    k = len(centers)
    sequences = []
    histograms = np.zeros((len(items), k), dtype=np.float64)
    for i, it in enumerate(items):
        ids = sqdist(it["x"] / scale, centers).argmin(axis=1)
        sequences.append(sp.collapse(ids))
        counts = np.bincount(ids, minlength=k).astype(np.float64)
        histograms[i] = counts / max(counts.sum(), 1.0)
    return sequences, histograms


def score(train: list[dict], held: list[dict], centers: np.ndarray,
          scale: np.ndarray, classes: list[str], seed: int,
          with_edit: bool = True) -> dict:
    y_train = [it["label"] for it in train]
    y_held = [it["label"] for it in held]
    base_held = [it["base"] for it in held]
    tr_seq, tr_hist = encode_items(train, centers, scale)
    he_seq, he_hist = encode_items(held, centers, scale)

    cos = sp.cosine_similarity_matrix(he_hist, tr_hist)
    nn_cos = sp.nn_classify(cos, y_train, y_held, classes)
    used = len({int(u) for s in he_seq for u in s})
    out = {
        "units": int(len(centers)),
        "units_used_heldout": used,
        "dead_units_heldout": int(len(centers) - used),
        "mean_sequence_length": float(np.mean([len(s) for s in he_seq])),
        "cosine": {
            "top1": nn_cos["top1"], "top5": nn_cos["top5"],
            "meanlink_top1": nn_cos["meanlink_top1"],
            "minimal_pairs": {p["pair"]: p["accuracy"]
                              for p in sp.minimal_pair_scores(cos, y_train, y_held)},
            "permutation_null": sp.permutation_null(cos, y_train, y_held, classes, seed),
            "top_confusions": sp.top_confusions(nn_cos["confusion"], classes),
        },
        "_correct_cosine": nn_cos["predicted"] == nn_cos["truth"],
    }
    if with_edit:
        edit = sp.edit_similarity_matrix(he_seq, tr_seq)
        nn_edit = sp.nn_classify(edit, y_train, y_held, classes)
        out["edit"] = {
            "top1": nn_edit["top1"], "top5": nn_edit["top5"],
            "meanlink_top1": nn_edit["meanlink_top1"],
            "minimal_pairs": {p["pair"]: p["accuracy"]
                              for p in sp.minimal_pair_scores(edit, y_train, y_held)},
            "separation": sp.separation(sp.edit_similarity_matrix(he_seq, he_seq),
                                        y_held, base_held),
            "top_confusions": sp.top_confusions(nn_edit["confusion"], classes),
        }
        out["_correct_edit"] = nn_edit["predicted"] == nn_edit["truth"]
    return out


def topographic_error(x: np.ndarray, centers: np.ndarray, rows: int, cols: int,
                      block: int = 8192) -> float:
    """Fraction of frames whose best and second-best unit are not map neighbours.

    The standard SOM ordering measure.  It is only meaningful for a map; a
    k-means codebook has no grid, so it is reported for the Hebbian rows only.
    """
    gd = grid_sqdist(rows, cols)
    bad = total = 0
    for start in range(0, len(x), block):
        d = sqdist(x[start:start + block], centers)
        order = np.argpartition(d, 1, axis=1)[:, :2]
        first = d[np.arange(len(d))[:, None], order].argmin(axis=1)
        best = order[np.arange(len(d)), first]
        second = order[np.arange(len(d)), 1 - first]
        bad += int(np.sum(gd[best, second] > 2.0))   # >2 means not even diagonal
        total += len(d)
    return bad / max(total, 1)


def phonetic_topology(items: list[dict], centers: np.ndarray, scale: np.ndarray,
                      rows: int, cols: int, seed: int, draws: int = 200) -> dict:
    """Do phonetically related syllables land near each other ON THE MAP?

    The colony's k-means confusions were measured to have zero correlation with
    phonetics (Spearman +0.03..+0.09 against shared manner/place/voicing).  A
    self-organising map claims something k-means cannot even express: that the
    *arrangement* of units carries structure.  This tests that claim.

    For each syllable class, its distribution over units; between two classes,
    the expected grid distance between the units they use.  Correlate that with
    how many phonetic features the two share.  Related syllables sitting near
    each other means a NEGATIVE Spearman.  The null shuffles which unit sits at
    which grid position, keeping the codebook and the histograms identical and
    destroying only the topology -- so it isolates arrangement from content.

    The phonetic table is `confusion_analysis.PHONETICS`, scoring only; it
    reaches no learner.
    """
    classes = sorted({it["label"] for it in items})
    k = len(centers)
    hist = np.zeros((len(classes), k))
    index = {c: i for i, c in enumerate(classes)}
    for it in items:
        ids = sqdist(it["x"] / scale, centers).argmin(axis=1)
        hist[index[it["label"]]] += np.bincount(ids, minlength=k)
    hist /= np.maximum(hist.sum(axis=1, keepdims=True), 1.0)
    gd = np.sqrt(grid_sqdist(rows, cols))
    iu = np.triu_indices(len(classes), 1)
    overlap = np.asarray([feature_overlap(classes[a], classes[b])
                          for a, b in zip(*iu)], dtype=np.float64)
    observed = spearman((hist @ gd @ hist.T)[iu], overlap)
    rng = np.random.default_rng(seed)
    null = []
    for _ in range(draws):
        shuffled = hist[:, rng.permutation(k)]
        null.append(spearman((shuffled @ gd @ shuffled.T)[iu], overlap))
    null = np.asarray(null)
    return {
        "spearman_map_distance_vs_phonetic_overlap": observed,
        "null_mean": float(null.mean()),
        "null_p05": float(np.quantile(null, 0.05)),
        "p_value_one_sided": float(np.mean(null <= observed)),
        "draws": draws,
        "note": "negative means phonetically related syllables sit near each "
                "other on the map; the null permutes unit->grid position only",
    }


# ---------------------------------------------------------------------------
# builders
# ---------------------------------------------------------------------------

def fit_hebbian(x: np.ndarray, k: int, seed: int, epochs: int, scaled: bool,
                snap: bool, hyper: dict) -> tuple[np.ndarray, np.ndarray, HebbianMap, float]:
    learner = HebbianMap(k, x.shape[1], seed, **hyper)
    if scaled:
        learner.fit_scaler(x)
    xs = x / learner.scale
    learner.horizon = max(1, epochs * len(xs))
    t0 = time.time()
    learner.fit(xs, epochs=epochs)
    if snap:
        learner.snap_to_frames(xs)
    return learner.w.copy(), learner.scale.copy(), learner, time.time() - t0


ONES = np.ones(1)


def unit_scale(dim: int) -> np.ndarray:
    return np.ones(dim, dtype=np.float64)


# ---------------------------------------------------------------------------
# mode: legacy replication
# ---------------------------------------------------------------------------

def run_legacy(train: list[dict], held: list[dict], classes: list[str],
               units: int) -> list[dict]:
    """Does this harness reproduce 41.9% / 40.3% on legacy14?  If not, stop."""
    featurise(train + held, "legacy14")
    syl_train = [it for it in train if it["kind"] == "syllable"]
    syl_held = [it for it in held if it["kind"] == "syllable"]
    pool = np.concatenate([it["full"] for it in train])   # all train frames
    rows = []
    for ant, seed in zip(DEFAULT_ANTS, DEFAULT_SEEDS):
        current = LEGACY_STATE / str(units) / ant / "current.json"
        jobs = [("random-real-frames", random_real_frames(pool, units, seed)),
                ("random-gaussian", random_gaussian(pool, units, seed))]
        if current.exists():
            jobs.insert(0, ("kmeans-shipped-checkpoint", np.asarray(
                load_checkpoint(current)["centers"], dtype=np.float64)))
        for name, centers in jobs:
            r = score(syl_train, syl_held, centers, unit_scale(pool.shape[1]),
                      classes, seed)
            r.update({"group": name, "feature_set": "legacy14", "ant": ant, "seed": seed})
            rows.append(r)
    return rows


# ---------------------------------------------------------------------------
# mode: cross-validated configuration search (never touches held-out)
# ---------------------------------------------------------------------------

def cv_folds(train: list[dict]) -> list[np.ndarray]:
    bases = [it["base"] for it in train if it["kind"] == "syllable"]
    names = sorted({b.rsplit("/", 1)[-1] for b in bases})
    return names


def run_cv(train: list[dict], classes: list[str], units: int, configs: list[dict],
           feature_set: str, ants: int, with_edit: bool) -> list[dict]:
    featurise(train, feature_set)
    syl = [it for it in train if it["kind"] == "syllable"]
    other = [it for it in train if it["kind"] != "syllable"]
    folds = cv_folds(train)
    rows = []
    for config in configs:
        t0 = time.time()
        per_fold, pairs_hits, pairs_total, dead = [], {}, {}, []
        for fold in folds:
            test = np.asarray([it["base"].endswith("/" + fold) for it in syl])
            if not test.any() or test.all():
                continue
            fold_train = [it for it, t in zip(syl, test) if not t]
            fold_test = [it for it, t in zip(syl, test) if t]
            pool = np.concatenate([it["full"] for it in fold_train + other])
            for ant, seed in list(zip(DEFAULT_ANTS, DEFAULT_SEEDS))[:ants]:
                centers, scale = build(config, pool, units, seed)
                r = score(fold_train, fold_test, centers, scale, classes, seed,
                          with_edit=with_edit)
                per_fold.append(r["cosine"]["top1"])
                dead.append(r["dead_units_heldout"])
                for p, v in r["cosine"]["minimal_pairs"].items():
                    pairs_hits[p] = pairs_hits.get(p, 0.0) + v
                    pairs_total[p] = pairs_total.get(p, 0) + 1
        rows.append({
            "config": config, "feature_set": feature_set, "units": units,
            "folds": len(per_fold),
            "cv_top1_cosine": float(np.mean(per_fold)),
            "cv_top1_std": float(np.std(per_fold)),
            "cv_minimal_pairs": {p: pairs_hits[p] / pairs_total[p] for p in pairs_hits},
            "cv_dead_units_mean": float(np.mean(dead)),
            "seconds": round(time.time() - t0, 1),
        })
        print(f"{config['name']:<34} top1={rows[-1]['cv_top1_cosine'] * 100:5.1f}% "
              f"(sd {rows[-1]['cv_top1_std'] * 100:4.1f})  "
              f"ba/pa={rows[-1]['cv_minimal_pairs'].get('ba/pa', 0) * 100:5.1f}% "
              f"da/ta={rows[-1]['cv_minimal_pairs'].get('da/ta', 0) * 100:5.1f}%  "
              f"dead={rows[-1]['cv_dead_units_mean']:5.1f}  "
              f"({rows[-1]['seconds']}s)", flush=True)
    return rows


def build(config: dict, pool: np.ndarray, units: int, seed: int
          ) -> tuple[np.ndarray, np.ndarray]:
    kind = config["kind"]
    scale = (F.variance_scaler(pool) if config.get("scaled")
             else unit_scale(pool.shape[1]))
    if kind == "random-real-frames":
        # with scaled=True this is bit-identical to the Hebbian map at epoch 0:
        # same seed, same rng.choice, same metric.  That is the point.
        return random_real_frames(pool / scale, units, seed), scale
    if kind == "random-gaussian":
        return random_gaussian(pool / scale, units, seed), scale
    if kind == "kmeans":
        return kmeans(pool / scale, units, seed, config.get("rounds", 30)), scale
    if kind == "hebbian":
        hyper = {k: v for k, v in config.items()
                 if k not in ("kind", "name", "epochs", "scaled", "snap")}
        w, scale, _, _ = fit_hebbian(pool, units, seed, config.get("epochs", 20),
                                     config.get("scaled", True),
                                     config.get("snap", False), hyper)
        return w, scale
    raise ValueError(f"unknown codebook kind {kind}")


# ---------------------------------------------------------------------------
# mode: incremental learning curve (train split only)
# ---------------------------------------------------------------------------

MARKS = (0, 1, 2, 3, 5, 8, 12, 20, 30, 40)


def run_curve(train: list[dict], classes: list[str], units: int, feature_set: str,
              ants: int, marks: tuple[int, ...] = MARKS) -> list[dict]:
    """Score the SAME map as it keeps learning.  This is the incremental claim.

    Epoch 0 is the map before a single update -- which, because the prototypes
    are initialised from random real frames, is exactly the random-real-frames
    control with that ant's seed.  Every point after it is the same codebook
    having seen more audio.  k-means has no such curve: it is a batch fixed
    point, and there is nothing to plot between "not fitted" and "fitted".

    Held-out is not read.  This is leave-one-base-rendering-out inside train.
    """
    featurise(train, feature_set)
    syl = [it for it in train if it["kind"] == "syllable"]
    other = [it for it in train if it["kind"] != "syllable"]
    folds = cv_folds(train)
    total = max(marks)
    per_mark: dict[int, list[float]] = {m: [] for m in marks}
    dead_mark: dict[int, list[int]] = {m: [] for m in marks}
    for fold in folds:
        test = np.asarray([it["base"].endswith("/" + fold) for it in syl])
        fold_train = [it for it, t in zip(syl, test) if not t]
        fold_test = [it for it, t in zip(syl, test) if t]
        pool = np.concatenate([it["full"] for it in fold_train + other])
        for _, seed in list(zip(DEFAULT_ANTS, DEFAULT_SEEDS))[:ants]:
            learner = HebbianMap(units, pool.shape[1], seed)
            learner.fit_scaler(pool)
            xs = pool / learner.scale
            learner.horizon = max(1, total * len(xs))
            learner.initialise(xs)
            done = 0
            for mark in marks:
                while done < mark:
                    learner.partial_fit(xs)
                    done += 1
                r = score(fold_train, fold_test, learner.w, learner.scale,
                          classes, seed, with_edit=False)
                per_mark[mark].append(r["cosine"]["top1"])
                dead_mark[mark].append(r["dead_units_heldout"])
    rows = [{"epochs": m,
             "frames_seen_per_epoch": None,
             "cv_top1_cosine": float(np.mean(per_mark[m])),
             "cv_top1_std": float(np.std(per_mark[m])),
             "cv_dead_units_mean": float(np.mean(dead_mark[m])),
             "runs": len(per_mark[m])} for m in marks]
    for r in rows:
        print(f"epoch {r['epochs']:>3}  top1={r['cv_top1_cosine'] * 100:5.1f}% "
              f"(sd {r['cv_top1_std'] * 100:4.1f})  "
              f"dead={r['cv_dead_units_mean']:5.1f}", flush=True)
    return rows


# ---------------------------------------------------------------------------
# mode: final held-out run
# ---------------------------------------------------------------------------

def run_final(train: list[dict], held: list[dict], classes: list[str], units: int,
              configs: list[dict], feature_set: str,
              pool: np.ndarray | None = None) -> list[dict]:
    """One shot on held-out.  `pool` is the audio the codebooks are fitted on;
    None means the colony's own train split, which is what the published
    baselines used."""
    featurise(train + held, feature_set)
    syl_train = [it for it in train if it["kind"] == "syllable"]
    syl_held = [it for it in held if it["kind"] == "syllable"]
    if pool is None:
        pool = np.concatenate([it["full"] for it in train])
    rows = []
    for config in configs:
        for ant, seed in zip(DEFAULT_ANTS, DEFAULT_SEEDS):
            t0 = time.time()
            centers, scale = build(config, pool, units, seed)
            fit_seconds = time.time() - t0
            r = score(syl_train, syl_held, centers, scale, classes, seed)
            r.update({"group": config["name"], "kind": config["kind"],
                      "feature_set": feature_set, "ant": ant, "seed": seed,
                      "config": config, "fit_seconds": round(fit_seconds, 1)})
            rows_, cols_ = grid_shape(units)
            heldout_frames = np.concatenate([it["x"] for it in syl_held]) / scale
            r["topology"] = {
                **H_topology(centers, rows_, cols_),
                "topographic_error_heldout": topographic_error(
                    heldout_frames, centers, rows_, cols_),
                "phonetics": phonetic_topology(syl_held, centers, scale,
                                               rows_, cols_, seed),
            }
            rows.append(r)
            print(f"{config['name']:<34} {ant} "
                  f"cos@1={r['cosine']['top1'] * 100:5.1f}% "
                  f"edit@1={r['edit']['top1'] * 100:5.1f}% "
                  f"ba/pa={r['cosine']['minimal_pairs'].get('ba/pa', 0) * 100:5.1f}% "
                  f"da/ta={r['cosine']['minimal_pairs'].get('da/ta', 0) * 100:5.1f}% "
                  f"dead={r['dead_units_heldout']:3d}/{units} ({fit_seconds:.1f}s)",
                  flush=True)
    return rows


def run_checkpoints(train: list[dict], held: list[dict], classes: list[str],
                    root: Path, feature_set: str) -> list[dict]:
    """Score codebooks already written to disk, through the identical probe."""
    featurise(train + held, feature_set)
    syl_train = [it for it in train if it["kind"] == "syllable"]
    syl_held = [it for it in held if it["kind"] == "syllable"]
    rows = []
    for current in sorted(root.glob("*/current.json")):
        centers, scale, checkpoint = H_load(current)
        seed = checkpoint["seed"]
        r = score(syl_train, syl_held, centers, scale, classes, seed)
        rows_, cols_ = grid_shape(len(centers))
        r.update({
            "group": f"checkpoint:{root.name}", "kind": "hebbian-checkpoint",
            "feature_set": feature_set, "ant": checkpoint["ant"], "seed": seed,
            "checkpoint": str(current),
            "checkpoint_sha256": checkpoint["checkpoint_sha256"],
            "train_frame_count": checkpoint["train_frame_count"],
            "corpus_provenance": checkpoint["corpus_provenance"],
            "fit_seconds": checkpoint["corpus_provenance"]["train_seconds"],
            "topology": {
                **checkpoint["topology"],
                "topographic_error_heldout": topographic_error(
                    np.concatenate([it["x"] for it in syl_held]) / scale,
                    centers, rows_, cols_),
                "phonetics": phonetic_topology(syl_held, centers, scale,
                                               rows_, cols_, seed),
            },
        })
        rows.append(r)
        print(f"{current.parent.name:<10} cos@1={r['cosine']['top1'] * 100:5.1f}% "
              f"edit@1={r['edit']['top1'] * 100:5.1f}% "
              f"ba/pa={r['cosine']['minimal_pairs'].get('ba/pa', 0) * 100:5.1f}% "
              f"da/ta={r['cosine']['minimal_pairs'].get('da/ta', 0) * 100:5.1f}% "
              f"dead={r['dead_units_heldout']:3d}/{len(centers)}", flush=True)
    if not rows:
        raise ValueError(f"no */current.json under {root}")
    return rows


def pooled(rows: list[dict], group: str, key: str) -> np.ndarray:
    return np.concatenate([r[key] for r in rows if r["group"] == group])


# ---------------------------------------------------------------------------

def default_configs(epochs: int) -> list[dict]:
    return [
        {"name": "hebbian-som", "kind": "hebbian", "epochs": epochs, "scaled": True},
        {"name": "kmeans", "kind": "kmeans", "scaled": True},
        {"name": "kmeans-unscaled", "kind": "kmeans", "scaled": False},
        {"name": "random-real-frames-scaled", "kind": "random-real-frames",
         "scaled": True},
        {"name": "random-real-frames", "kind": "random-real-frames"},
        {"name": "random-gaussian", "kind": "random-gaussian"},
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=None)
    parser.add_argument("--units", type=int, default=256)
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--feature-set", default="recommended26")
    parser.add_argument("--legacy", action="store_true")
    parser.add_argument("--cv", action="store_true")
    parser.add_argument("--curve", action="store_true")
    parser.add_argument("--cv-ants", type=int, default=2)
    parser.add_argument("--cv-edit", action="store_true")
    parser.add_argument("--configs", default=None,
                        help="path to a JSON list of configs")
    parser.add_argument("--checkpoints", default=None,
                        help="score */current.json under this directory")
    parser.add_argument("--pool-folders", default=None,
                        help="comma-separated folders to fit the codebooks on; "
                             "default is the colony's own train split")
    parser.add_argument("--pool-stride", type=int, default=1)
    parser.add_argument("--pool-limit", type=int, default=None)
    parser.add_argument("--tag", default=None)
    args = parser.parse_args()

    t0 = time.time()
    labels = sp.load_labels(COMBINED)
    kinds = ("syllable", "human_speech")
    train = collect(COMBINED / "train", labels, kinds)
    held = collect(COMBINED / "heldout", labels, kinds)
    classes = sorted({it["label"] for it in train if it["kind"] == "syllable"})
    syl_train = [it for it in train if it["kind"] == "syllable"]
    syl_held = [it for it in held if it["kind"] == "syllable"]
    assert {it["base"] for it in syl_train}.isdisjoint({it["base"] for it in syl_held})
    print(f"train={len(syl_train)} syllables (+{len(train) - len(syl_train)} human) "
          f"heldout={len(syl_held)} classes={len(classes)} "
          f"chance={1 / len(classes):.3f}  ({time.time() - t0:.1f}s)\n", flush=True)

    configs = (json.loads(Path(args.configs).read_text(encoding="utf-8"))
               if args.configs else default_configs(args.epochs))

    pool = None
    pool_note = "the colony's own corpus-combined/train split"
    if args.pool_folders:
        t = time.time()
        frames, hashes = featurise_folders(
            [Path(p) for p in args.pool_folders.split(",")],
            args.pool_limit, args.pool_stride, 0, True)
        pool = frames.astype(np.float64)
        pool_note = (f"{args.pool_folders} at frame stride {args.pool_stride}"
                     f"{f', {args.pool_limit} files per folder' if args.pool_limit else ''}"
                     f" -> {len(pool)} frames from {len(set(hashes))} files")
        print(f"pool: {pool_note}  ({time.time() - t:.0f}s)\n", flush=True)

    if args.checkpoints:
        rows = run_checkpoints(train, held, classes, Path(args.checkpoints),
                               args.feature_set)
        name = "checkpoints"
    elif args.legacy:
        rows = run_legacy(train, held, classes, args.units)
        name = "legacy-replication"
    elif args.curve:
        rows = run_curve(train, classes, args.units, args.feature_set, args.cv_ants)
        name = "learning-curve"
    elif args.cv:
        rows = run_cv(train, classes, args.units, configs, args.feature_set,
                      args.cv_ants, args.cv_edit)
        name = "cv-selection"
    else:
        rows = run_final(train, held, classes, args.units, configs,
                         args.feature_set, pool)
        name = "heldout-final"

    report = {
        "question": "does competitive Hebbian learning beat random real frames",
        "metric_policy": "quantisation error is not computed in this file",
        "chance_top1": 1 / len(classes),
        "units": args.units,
        "feature_set": args.feature_set,
        "codebook_fitting_pool": pool_note,
        "heldout_items": len(syl_held),
        "train_items": len(syl_train),
        "classes": classes,
        "baselines_published_legacy14": {
            "trained_kmeans_256_cosine_top1": 0.419,
            "random_real_frames_256_cosine_top1": 0.403,
            "random_gaussian_256_cosine_top1": 0.258,
            "raw_features_no_codebook_top1": 0.538,
            "kmeans_256_units_used_heldout": 172,
        },
        "rows": rows,
    }

    if name in ("heldout-final", "legacy-replication", "checkpoints"):
        groups = sorted({r["group"] for r in rows})
        summary, paired = {}, []
        for g in groups:
            sub = [r for r in rows if r["group"] == g]
            summary[g] = {
                "cosine_top1_mean": float(np.mean([r["cosine"]["top1"] for r in sub])),
                "edit_top1_mean": float(np.mean([r["edit"]["top1"] for r in sub])),
                "ba_pa_cosine": float(np.mean([r["cosine"]["minimal_pairs"].get("ba/pa", 0)
                                               for r in sub])),
                "da_ta_cosine": float(np.mean([r["cosine"]["minimal_pairs"].get("da/ta", 0)
                                               for r in sub])),
                "ba_pa_edit": float(np.mean([r["edit"]["minimal_pairs"].get("ba/pa", 0)
                                             for r in sub])),
                "da_ta_edit": float(np.mean([r["edit"]["minimal_pairs"].get("da/ta", 0)
                                             for r in sub])),
                "dead_units_heldout_mean": float(np.mean([r["dead_units_heldout"]
                                                          for r in sub])),
                "fit_seconds_mean": float(np.mean([r.get("fit_seconds", float("nan"))
                                                   for r in sub])),
            }
        reference = "random-real-frames" if "random-real-frames" in groups else None
        for metric, key in (("cosine", "_correct_cosine"), ("edit", "_correct_edit")):
            for g in groups:
                if reference is None or g == reference:
                    continue
                a = pooled(rows, g, key)
                b = pooled(rows, reference, key)
                paired.append({"metric": metric, "left": g, "right": reference,
                               "left_accuracy": float(a.mean()),
                               "right_accuracy": float(b.mean()),
                               "delta_points": float(100 * (a.mean() - b.mean())),
                               **mcnemar(a, b)})
        report["summary"] = summary
        report["paired_mcnemar_vs_random_real_frames"] = paired
        print("\n--- pooled over four ants " + "-" * 40)
        for g in sorted(summary, key=lambda g: -summary[g]["cosine_top1_mean"]):
            s = summary[g]
            print(f"{g:<24} cos@1={s['cosine_top1_mean'] * 100:5.1f}%  "
                  f"edit@1={s['edit_top1_mean'] * 100:5.1f}%  "
                  f"ba/pa={s['ba_pa_cosine'] * 100:5.1f}%  "
                  f"da/ta={s['da_ta_cosine'] * 100:5.1f}%  "
                  f"dead={s['dead_units_heldout_mean']:5.1f}  "
                  f"fit={s['fit_seconds_mean']:5.1f}s")
        print("\n--- paired McNemar vs random real frames " + "-" * 24)
        for p in paired:
            print(f"{p['metric']:<7} {p['left']:<24} "
                  f"{p['left_accuracy'] * 100:5.1f} vs {p['right_accuracy'] * 100:5.1f} "
                  f"delta={p['delta_points']:+5.1f}  p={p['p_value']:.4f}")

    for r in rows:
        r.pop("_correct_cosine", None)
        r.pop("_correct_edit", None)
    out = Path(args.out) if args.out else OUT_DIR / f"{name}-{args.units}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=float),
                   encoding="utf-8")
    print(f"\nwrote {out}  ({time.time() - t0:.1f}s total)")


if __name__ == "__main__":
    main()
