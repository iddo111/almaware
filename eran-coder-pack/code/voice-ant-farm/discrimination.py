"""Discrimination probes for acoustic codebooks (pure numpy).

Quantisation error is NOT a success metric here: a prior controlled experiment
showed that k-means distortion rewards a codebook whose centres cover a broader
feature cloud, so lower distortion does not mean better speech representation.
These probes instead ask a question distortion cannot answer:

    does the codebook keep two different syllables apart?

Every probe reads audio only. Syllable identity is used exclusively as a scoring
key, loaded from the corpus label map, and never enters a checkpoint or a feature.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from acoustic_units import encode, error, features, load_wav


LOUD_FRACTION = 0.60  # keep the loudest 60% of frames so pad length cannot be a cue


def loud_frames(x: np.ndarray, fraction: float = LOUD_FRACTION) -> np.ndarray:
    """Keep the loudest frames of an utterance (column 0 is log energy)."""
    keep = max(1, int(round(fraction * len(x))))
    order = np.argsort(x[:, 0], kind="stable")[-keep:]
    return x[np.sort(order)]


def collect(folder: Path, labels: dict, kind: str) -> list[dict]:
    """Featurise a folder once; label lookup is provenance only."""
    items = []
    for path in sorted(folder.glob("*.wav")):
        record = labels.get(path.name)
        if record is None or record.get("item_kind") != kind:
            continue
        x, _ = features(load_wav(path))
        items.append({
            "name": path.name,
            "label": record["item_id"],
            "base": record.get("base_rendering_id"),
            "loud": loud_frames(x),
        })
    if not items:
        raise ValueError(f"no {kind} audio in {folder}")
    return items


def raw_descriptor(items: list[dict]) -> np.ndarray:
    return np.asarray(
        [np.concatenate([it["loud"].mean(axis=0), it["loud"].std(axis=0)]) for it in items],
        dtype=np.float64,
    )


def unit_descriptor(items: list[dict], centers: np.ndarray) -> np.ndarray:
    k = len(centers)
    rows = []
    for it in items:
        ids = encode(it["loud"], centers)
        counts = np.bincount(ids, minlength=k).astype(np.float64)
        rows.append(counts / counts.sum())
    return np.asarray(rows, dtype=np.float64)


def quantised_descriptor(items: list[dict], centers: np.ndarray) -> np.ndarray:
    """Replace every frame by its centre, then take the same mean+std descriptor.

    This is the raw-feature probe run through the codebook bottleneck, so it is
    directly comparable to the no-codebook reference: the gap is exactly the
    discriminative information the quantiser destroyed.
    """
    rows = []
    for it in items:
        q = centers[encode(it["loud"], centers)]
        rows.append(np.concatenate([q.mean(axis=0), q.std(axis=0)]))
    return np.asarray(rows, dtype=np.float64)


def _normalise(v: np.ndarray) -> np.ndarray:
    return v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-12)


def distances(train: np.ndarray, test: np.ndarray, metric: str) -> np.ndarray:
    if metric == "cosine":
        a, b = _normalise(test), _normalise(train)
        return 1.0 - a @ b.T
    return np.sqrt(np.maximum(
        ((test[:, None, :] - train[None, :, :]) ** 2).sum(axis=2), 0.0
    ))


def nn_probe(
    train_x: np.ndarray, train_y: list[str], test_x: np.ndarray, test_y: list[str],
    metric: str, top_n: int = 5,
) -> dict:
    """1-NN classification; a class is ranked by its nearest training example."""
    classes = sorted(set(train_y))
    index = {c: i for i, c in enumerate(classes)}
    train_ids = np.asarray([index[y] for y in train_y])
    d = distances(train_x, test_x, metric)
    per_class = np.full((len(test_x), len(classes)), np.inf)
    for c in range(len(classes)):
        member = train_ids == c
        if member.any():
            per_class[:, c] = d[:, member].min(axis=1)
    ranking = np.argsort(per_class, axis=1, kind="stable")
    truth = np.asarray([index[y] for y in test_y])
    top1 = float(np.mean(ranking[:, 0] == truth))
    topn = float(np.mean([truth[i] in ranking[i, :top_n] for i in range(len(truth))]))
    centroids = np.stack([train_x[train_ids == c].mean(axis=0) for c in range(len(classes))])
    cd = distances(centroids, test_x, metric)
    centroid_top1 = float(np.mean(cd.argmin(axis=1) == truth))
    return {
        "classes": len(classes),
        "chance": 1.0 / len(classes),
        "top1": top1,
        f"top{top_n}": topn,
        "centroid_top1": centroid_top1,
        "test_items": len(test_y),
        "train_items": len(train_y),
    }


def zscore(train_x: np.ndarray, test_x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    mean, std = train_x.mean(axis=0), train_x.std(axis=0)
    std = np.where(std < 1e-9, 1.0, std)
    return (train_x - mean) / std, (test_x - mean) / std


def frame_agreement(items: list[dict], centers: np.ndarray) -> dict:
    """Frame-level mutual information between unit id and syllable identity.

    Purity and raw MI rise mechanically with cluster count; NMI divides by the
    unit entropy, so it is the comparable number across codebook sizes.
    """
    classes = sorted({it["label"] for it in items})
    index = {c: i for i, c in enumerate(classes)}
    table = np.zeros((len(classes), len(centers)), dtype=np.float64)
    for it in items:
        ids = encode(it["loud"], centers)
        np.add.at(table[index[it["label"]]], ids, 1.0)
    total = table.sum()
    p = table / total
    p_label = p.sum(axis=1, keepdims=True)
    p_unit = p.sum(axis=0, keepdims=True)
    with np.errstate(divide="ignore", invalid="ignore"):
        term = np.where(p > 0, p * np.log2(p / np.maximum(p_label * p_unit, 1e-300)), 0.0)
    mi = float(term.sum())
    h_label = float(-(p_label * np.log2(np.maximum(p_label, 1e-300))).sum())
    h_unit = float(-(p_unit * np.log2(np.maximum(p_unit, 1e-300))).sum())
    purity = float(table.max(axis=0).sum() / total)
    return {
        "frames": int(total),
        "mutual_information_bits": mi,
        "label_entropy_bits": h_label,
        "unit_entropy_bits": h_unit,
        "nmi_sqrt": mi / math.sqrt(max(h_label * h_unit, 1e-300)),
        "unit_purity": purity,
        "units_used": int((table.sum(axis=0) > 0).sum()),
    }


def leave_one_base_out(items: list[dict], descriptor: np.ndarray, metric: str) -> dict:
    """Rotate whole base renderings out, so augmentation twins cannot leak."""
    labels = [it["label"] for it in items]
    bases = sorted({it["base"] for it in items})
    folds = sorted({b.rsplit("/", 1)[-1] for b in bases})
    scores, top5, centroid = [], [], []
    for fold in folds:
        test = np.asarray([it["base"].endswith("/" + fold) for it in items])
        if not test.any() or test.all():
            continue
        result = nn_probe(
            descriptor[~test], [l for l, t in zip(labels, test) if not t],
            descriptor[test], [l for l, t in zip(labels, test) if t], metric,
        )
        scores.append(result["top1"])
        top5.append(result["top5"])
        centroid.append(result["centroid_top1"])
    classes = len(set(labels))
    return {
        "classes": classes,
        "chance": 1.0 / classes,
        "folds": len(scores),
        "top1": float(np.mean(scores)),
        "top5": float(np.mean(top5)),
        "centroid_top1": float(np.mean(centroid)),
        "items": len(items),
    }


def split_quantisation_error(folder: Path, labels: dict, centers: np.ndarray,
                             baseline_center: np.ndarray) -> dict:
    """Held-out distortion, reported separately for human and synthetic audio."""
    out = {}
    baseline = np.repeat(np.asarray(baseline_center, np.float32)[None, :], len(centers), axis=0)
    for kind in ("human_speech", "syllable"):
        frames = []
        for path in sorted(folder.glob("*.wav")):
            record = labels.get(path.name)
            if record is None or record.get("item_kind") != kind:
                continue
            frames.append(features(load_wav(path))[0])
        if not frames:
            continue
        x = np.concatenate(frames)
        out[kind] = {
            "frames": int(len(x)),
            "error_before": error(x, baseline),
            "error_after": error(x, centers),
        }
    return out


def load_labels(root: Path) -> dict:
    return json.loads((root / "labels.json").read_text(encoding="utf-8"))["labels"]
