"""Train and score the segmental colony against the baselines that matter.

Everything is scored through the SAME probe the frame-wise numbers came from:
`sequence_probes.nn_classify` over unit-histogram cosine and over Levenshtein
distance on the run-length-collapsed unit string, 22 Hebrew syllables, held-out
audio, chance 4.5%.  The two numbers this has to beat are

    trained k-means 256, legacy14 frames ....... 41.9%   (histogram cosine)
    RANDOM REAL FRAMES 256, legacy14 frames .... 40.3%

and beating only the first one would mean nothing, because those two are already
statistically indistinguishable (p = 0.54).

Controls, all through the identical probe:
  * segmental k-means            the learner
  * random real SEGMENTS         the control that matters -- k real segment
                                 descriptors as centres, no Lloyd iterations
  * frame k-means, recommended26 isolates "segments" from "better features"
  * random real frames, recommended26
  * frame k-means, legacy14      reproduces the published 41.9% in this file
  * random real frames, legacy14 reproduces the published 40.3% in this file

Quantisation error is not reported: a prior controlled experiment showed
phase-randomised noise beats structured audio on it.

    py -3.13 run_segmental.py --cv        # selection, train split only
    py -3.13 run_segmental.py             # held-out, read once
"""
from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np

import feature_space as F
import segmental as S
import sequence_probes as sp
from acoustic_units import EXEMPLAR_RATE, load_wav, resample_samples
from colony import DEFAULT_ANTS, DEFAULT_SEEDS
from paired_tests import mcnemar

ROOT = Path(__file__).resolve().parent
COMBINED = ROOT / "corpus-combined"
OUT = ROOT / "state-hebbian" / "segmental"


# ---------------------------------------------------------------------------
# corpus
# ---------------------------------------------------------------------------

def collect(folder: Path, labels: dict, kind: str, sets: tuple[str, ...]) -> list[dict]:
    """One pass over the audio.  The speech span is frozen, from legacy log-energy."""
    items = []
    for path in sorted(folder.glob("*.wav")):
        record = labels.get(path.name)
        if record is None or record.get("item_kind") != kind:
            continue
        audio = load_wav(path)
        samples = resample_samples(audio.samples, audio.rate, EXEMPLAR_RATE)
        first, last = S.speech_span(samples)
        items.append({
            "path": str(path), "name": path.name, "label": record["item_id"],
            "base": record.get("base_rendering_id"), "span": (first, last),
            "f": {name: F.extract(name, samples) for name in sets},
        })
    if not items:
        raise ValueError(f"no {kind} audio in {folder}")
    return items


def view(items: list[dict], name: str) -> list[dict]:
    """The same items presented in one feature space, span-sliced."""
    out = []
    for it in items:
        first, last = it["span"]
        out.append({"path": it["path"], "name": it["name"], "label": it["label"],
                    "base": it["base"], "frames": it["f"][name][first:last],
                    "span": (0, last - first)})
    return out


# ---------------------------------------------------------------------------
# encoders
# ---------------------------------------------------------------------------

class FrameCodebook:
    """Frame-wise control: one unit per frame, no segments.  Same probe."""

    def __init__(self, centers: np.ndarray) -> None:
        self.centers_ = np.asarray(centers, dtype=np.float64)
        self.units = len(self.centers_)

    def encode_features(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray | None]:
        ids, _ = S.assign(np.asarray(x, dtype=np.float64), self.centers_)
        return ids, None


def frame_kmeans(items: list[dict], units: int, seed: int, random_frames: bool
                 ) -> FrameCodebook:
    pool = np.concatenate([it["frames"] for it in items], axis=0)
    rng = np.random.default_rng(seed)
    if random_frames:
        return FrameCodebook(pool[rng.choice(len(pool), units, replace=False)])
    return FrameCodebook(S.kmeans(pool, units, seed)[0])


def encode_items(items: list[dict], encoder) -> dict:
    """Unit strings and duration-weighted unit histograms, exactly as before."""
    k = encoder.units
    sequences, histograms, segments = [], np.zeros((len(items), k)), []
    for i, it in enumerate(items):
        ids, edges = encoder.encode_features(it["frames"])
        sequences.append(sp.collapse(ids))
        segments.append(len(ids) if edges is None else len(edges) - 1)
        counts = np.bincount(ids, minlength=k).astype(np.float64)
        histograms[i] = counts / max(counts.sum(), 1.0)
    return {"sequences": sequences, "histograms": histograms, "segments": segments}


# ---------------------------------------------------------------------------
# scoring: the published probe, unchanged
# ---------------------------------------------------------------------------

def score(train: list[dict], held: list[dict], classes: list[str], encoder,
          seed: int) -> dict:
    a = encode_items(train, encoder)
    b = encode_items(held, encoder)
    y_train = [it["label"] for it in train]
    y_held = [it["label"] for it in held]
    base_held = [it["base"] for it in held]

    edit = sp.edit_similarity_matrix(b["sequences"], a["sequences"])
    cosine = sp.cosine_similarity_matrix(b["histograms"], a["histograms"])
    nn_edit = sp.nn_classify(edit, y_train, y_held, classes)
    nn_cos = sp.nn_classify(cosine, y_train, y_held, classes)
    frames = float(np.mean([len(it["frames"]) for it in held]))
    seconds = frames * F.HOP_SECONDS
    return {
        "units": int(encoder.units),
        "units_used_heldout": int(len({int(u) for s in b["sequences"] for u in s})),
        "dead_units_heldout": int(encoder.units
                                  - len({int(u) for s in b["sequences"] for u in s})),
        "mean_sequence_length": float(np.mean([len(s) for s in b["sequences"]])),
        "mean_segments_per_item": float(np.mean(b["segments"])),
        "mean_segments_per_second": float(np.mean(b["segments"]) / max(seconds, 1e-9)),
        "top1_cosine": nn_cos["top1"],
        "top5_cosine": nn_cos["top5"],
        "meanlink_top1_cosine": nn_cos["meanlink_top1"],
        "top1_edit": nn_edit["top1"],
        "top5_edit": nn_edit["top5"],
        "meanlink_top1_edit": nn_edit["meanlink_top1"],
        "minimal_pairs_cosine": {p["pair"]: p["accuracy"]
                                 for p in sp.minimal_pair_scores(cosine, y_train, y_held)},
        "minimal_pairs_edit": {p["pair"]: p["accuracy"]
                               for p in sp.minimal_pair_scores(edit, y_train, y_held)},
        "separation_edit": sp.separation(
            sp.edit_similarity_matrix(b["sequences"], b["sequences"]), y_held, base_held),
        "separation_cosine": sp.separation(
            sp.cosine_similarity_matrix(b["histograms"], b["histograms"]),
            y_held, base_held),
        "permutation_null_cosine": sp.permutation_null(cosine, y_train, y_held,
                                                       classes, seed),
        "top_confusions_cosine": sp.top_confusions(nn_cos["confusion"], classes),
        "confusion_cosine": nn_cos["confusion"].tolist(),
        "_correct_cosine": nn_cos["predicted"] == nn_cos["truth"],
        "_correct_edit": nn_edit["predicted"] == nn_edit["truth"],
    }


def folds_of(items: list[dict]) -> list[str]:
    return sorted({it["base"].rsplit("/", 1)[-1] for it in items})


def cross_validate(items: list[dict], classes: list[str], build, seed: int) -> dict:
    """Leave-one-base-rendering-out inside train.  The codebook is refitted per
    fold, so the test fold never contributes a centre or a scaler."""
    top1_cos, top1_edit, pair_hits, pair_total = [], [], {}, {}
    dead, per_item = [], []
    for fold in folds_of(items):
        mask = np.asarray([it["base"].endswith("/" + fold) for it in items])
        if not mask.any() or mask.all():
            continue
        train = [it for it, m in zip(items, mask) if not m]
        test = [it for it, m in zip(items, mask) if m]
        encoder = build(train)
        a, b = encode_items(train, encoder), encode_items(test, encoder)
        y_tr = [it["label"] for it in train]
        y_te = [it["label"] for it in test]
        cosine = sp.cosine_similarity_matrix(b["histograms"], a["histograms"])
        edit = sp.edit_similarity_matrix(b["sequences"], a["sequences"])
        top1_cos.append(sp.nn_classify(cosine, y_tr, y_te, classes)["top1"])
        top1_edit.append(sp.nn_classify(edit, y_tr, y_te, classes)["top1"])
        dead.append(encoder.units - len({int(u) for s in b["sequences"] for u in s}))
        per_item.append(float(np.mean(b["segments"])))
        for p in sp.minimal_pair_scores(cosine, y_tr, y_te):
            pair_hits[p["pair"]] = pair_hits.get(p["pair"], 0) + p["correct"]
            pair_total[p["pair"]] = pair_total.get(p["pair"], 0) + p["items"]
    return {
        "folds": len(top1_cos),
        "top1_cosine": float(np.mean(top1_cos)),
        "top1_cosine_std": float(np.std(top1_cos)),
        "top1_edit": float(np.mean(top1_edit)),
        "minimal_pairs_cosine": {k: pair_hits[k] / pair_total[k] for k in pair_hits},
        "all_pairs_pooled": float(sum(pair_hits.values()) / sum(pair_total.values())),
        "mean_dead_units": float(np.mean(dead)),
        "mean_segments_per_item": float(np.mean(per_item)),
    }


# ---------------------------------------------------------------------------
# configurations
# ---------------------------------------------------------------------------

def ant_builder(units: int, segmenter: S.Segmenter, descriptor: S.Descriptor,
                seed: int, exemplars: bool = False, whiten: bool = False):
    def build(train_items):
        ant = S.SegmentalAnt("cv", seed, units, segmenter, descriptor, whiten=whiten)
        return ant.fit(train_items, exemplars=exemplars)
    return build


def random_segment_builder(units: int, segmenter: S.Segmenter,
                           descriptor: S.Descriptor, seed: int,
                           whiten: bool = False):
    def build(train_items):
        template = S.SegmentalAnt("cv", seed, units, segmenter, descriptor,
                                  whiten=whiten)
        return S.random_real_segments(template, train_items, seed, exemplars=False)
    return build


def cv_grid() -> list[dict]:
    """The search.  Chosen on CV inside train; held-out is not read here."""
    base_seg = S.Segmenter()
    base_desc = S.Descriptor()
    rows = []

    def add(tag, units=128, **kw):
        seg = S.Segmenter(**{k: v for k, v in kw.items()
                             if k in S.Segmenter.__dataclass_fields__})
        desc = S.Descriptor(**{k: v for k, v in kw.items()
                               if k in S.Descriptor.__dataclass_fields__})
        rows.append({"tag": tag, "units": units, "segmenter": seg, "descriptor": desc})

    for units in (32, 64, 128, 256, 512):
        add(f"k{units}", units)
    for high in (0.5, 0.75, 1.0, 1.5, 2.0):
        add(f"high{high}", 128, high=high, low=min(0.3, high))
    for low in (0.0, 0.3, 0.6, 0.9):
        add(f"low{low}", 128, high=1.0, low=low)
    for window in (2, 3, 5, 7):
        add(f"win{window}", 128, window=window)
    for min_frames in (2, 3, 4, 6, 8):
        add(f"min{min_frames}", 128, min_frames=min_frames)
    for parts in (1, 2, 3, 4, 5):
        add(f"parts{parts}", 128, parts=parts)
    for flag in (True, False):
        add(f"delta{int(flag)}", 128, use_delta=flag)
        add(f"dur{int(flag)}", 128, use_duration=flag)
    for weight in (0.0, 0.5, 1.0, 2.0, 4.0):
        add(f"durw{weight}", 128, duration_weight=weight)
    for smooth in (0, 1, 2):
        add(f"smooth{smooth}", 128, smooth=smooth)
    for max_frames in (12, 20, 30, 50):
        add(f"max{max_frames}", 128, max_frames=max_frames)
    return _unique(rows)


def _unique(rows: list[dict]) -> list[dict]:
    seen, unique = set(), []
    for row in rows:
        key = (row["units"], row["segmenter"], row["descriptor"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique


def cv_grid2() -> list[dict]:
    """Second pass: resolution and codebook size together.

    Grid 1 said the two things that move the number are how many segments per
    second the detector emits and how many units there are to spend on them, and
    that they interact -- `high2.0` wins by emitting FEWER segments and `max12`
    wins by emitting MORE.  With 66 items per fold a 5-point difference is one
    standard error, so grid 1 cannot separate them and this grid crosses them.
    """
    rows = []
    for max_frames in (8, 10, 12, 16, 30):
        for high in (1.0, 1.5, 2.0):
            for units in (128, 256, 512):
                rows.append({
                    "tag": f"m{max_frames}h{high}k{units}", "units": units,
                    "segmenter": S.Segmenter(high=high, low=0.3, smooth=2,
                                             min_frames=4, max_frames=max_frames),
                    "descriptor": S.Descriptor(parts=3, duration_weight=2.0)})
    for min_frames in (2, 3):
        for max_frames in (8, 12):
            for units in (256, 512):
                rows.append({
                    "tag": f"n{min_frames}m{max_frames}k{units}", "units": units,
                    "segmenter": S.Segmenter(high=1.0, low=0.3, smooth=2,
                                             min_frames=min_frames,
                                             max_frames=max_frames),
                    "descriptor": S.Descriptor(parts=3, duration_weight=2.0)})
    return _unique(rows)


# ---------------------------------------------------------------------------
# entry points
# ---------------------------------------------------------------------------

def _seg(high, max_frames):
    return S.Segmenter(high=high, low=0.3, smooth=2, min_frames=4, max_frames=max_frames)


_D = S.Descriptor(3, True, True, 2.0)

FINALISTS = {
    # tag: (segmenter, descriptor, units, whiten)
    "seg-m30h2.0-k128": (_seg(2.0, 30), _D, 128, False),
    "seg-m30h1.5-k256": (_seg(1.5, 30), _D, 256, False),
    "seg-m10h1.5-k256": (_seg(1.5, 10), _D, 256, False),
    "seg-m10h1.0-k256": (_seg(1.0, 10), _D, 256, False),
    "seg-m10h1.0-k128": (_seg(1.0, 10), _D, 128, False),
    "seg-default-k128": (S.Segmenter(), S.Descriptor(), 128, False),
}

FINALISTS2 = {
    "segw-m30h2.0-k128": (_seg(2.0, 30), _D, 128, True),
    "segw-m30h2.0-k256": (_seg(2.0, 30), _D, 256, True),
    "segw-m30h2.0-k64": (_seg(2.0, 30), _D, 64, True),
    "segw-m10h1.0-k256": (_seg(1.0, 10), _D, 256, True),
    "segw-m10h1.0-k512": (_seg(1.0, 10), _D, 512, True),
    "segw-m16h1.5-k256": (_seg(1.5, 16), _D, 256, True),
    "segw-p5-m30h2.0-k128": (_seg(2.0, 30), S.Descriptor(5, True, True, 2.0), 128, True),
    "segw-p1-m30h2.0-k128": (_seg(2.0, 30), S.Descriptor(1, True, True, 2.0), 128, True),
    "seg-m30h2.0-k64": (_seg(2.0, 30), _D, 64, False),
    "seg-m30h2.0-k256": (_seg(2.0, 30), _D, 256, False),
}

ALL_FINALISTS = {**FINALISTS, **FINALISTS2}

# Chosen on CV alone; see state-hebbian/segmental/cv-finals1.json and cv-finals2.json.
SELECTED = "seg-m30h2.0-k128"


def run_finals(args) -> None:
    """Every finalist re-run under all four ant seeds, so the number that chooses
    the configuration is 4 x 396 = 1584 CV decisions and not 396.

    The grid-2 winner beat the plateau by 5 points on 396 decisions, which is two
    standard errors on the argmax of ~100 configurations -- i.e. exactly what
    selection noise looks like.  This is the check.  Held-out is still untouched.
    """
    labels = sp.load_labels(COMBINED)
    items = collect(COMBINED / "train", labels, "syllable", (F.CANONICAL, "legacy14"))
    classes = sorted({it["label"] for it in items})
    canonical, legacy = view(items, F.CANONICAL), view(items, "legacy14")
    print(f"finals: {len(items)} train items, 4 seeds each, held-out untouched\n",
          flush=True)
    print(f"{'config':<26}{'k':>5}{'segs/it':>9}{'cos top1':>11}{'(sd over seeds)':>17}"
          f"{'edit top1':>11}{'ba/pa':>8}{'da/ta':>8}{'dead':>7}", flush=True)
    rows = []

    def run(tag, build_for_seed, source, units, kind):
        per_seed = [cross_validate(source, classes, build_for_seed(s), s)
                    for s in DEFAULT_SEEDS]
        row = {"tag": tag, "kind": kind, "units": units,
               "top1_cosine": float(np.mean([r["top1_cosine"] for r in per_seed])),
               "top1_cosine_sd_over_seeds": float(np.std([r["top1_cosine"]
                                                          for r in per_seed])),
               "top1_edit": float(np.mean([r["top1_edit"] for r in per_seed])),
               "ba_pa": float(np.mean([r["minimal_pairs_cosine"].get("ba/pa", 0)
                                       for r in per_seed])),
               "da_ta": float(np.mean([r["minimal_pairs_cosine"].get("da/ta", 0)
                                       for r in per_seed])),
               "all_pairs_pooled": float(np.mean([r["all_pairs_pooled"]
                                                  for r in per_seed])),
               "mean_dead_units": float(np.mean([r["mean_dead_units"] for r in per_seed])),
               "segments_per_item": float(np.mean([r["mean_segments_per_item"]
                                                   for r in per_seed])),
               "per_seed": per_seed}
        rows.append(row)
        print(f"{tag:<26}{units:>5}{row['segments_per_item']:>9.2f}"
              f"{row['top1_cosine'] * 100:>10.1f}%{row['top1_cosine_sd_over_seeds'] * 100:>16.1f}"
              f"{row['top1_edit'] * 100:>10.1f}%{row['ba_pa'] * 100:>7.1f}%"
              f"{row['da_ta'] * 100:>7.1f}%{row['mean_dead_units']:>7.0f}", flush=True)

    for tag, (segmenter, descriptor, units, whiten) in (
            FINALISTS if args.grid == 1 else FINALISTS2).items():
        run(tag, lambda s, sg=segmenter, d=descriptor, u=units, w=whiten:
            ant_builder(u, sg, d, s, whiten=w), canonical, units,
            "segmental-trained")
        run(tag.replace("seg", "randseg", 1),
            lambda s, sg=segmenter, d=descriptor, u=units, w=whiten:
            random_segment_builder(u, sg, d, s, whiten=w), canonical, units,
            "segmental-random-real")
    for tag, source, name, random_frames in (
            ("frame-km-r26", canonical, F.CANONICAL, False),
            ("frame-rand-r26", canonical, F.CANONICAL, True),
            ("frame-km-legacy14", legacy, "legacy14", False),
            ("frame-rand-legacy14", legacy, "legacy14", True)):
        for units in (128, 256):
            run(f"{tag}-{units}",
                lambda s, u=units, rf=random_frames:
                (lambda tr: frame_kmeans(tr, u, s, rf)), source, units,
                "frame-" + ("random-real" if random_frames else "trained"))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "question": "which segmental configuration, decided on 1584 CV decisions",
        "protocol": "leave-one-base-rendering-out inside train, codebook refitted "
                    "per fold, repeated under all four ant seeds; heldout not read",
        "chance_top1": 1 / len(classes),
        "results": sorted(rows, key=lambda r: -r["top1_cosine"]),
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {out}")


def run_ablation(args) -> None:
    """What is the segment representation actually made of?

    The brief makes two specific claims: that a syllable is a TRAJECTORY, and
    that DURATION carries information the frame-wise design throws away.  Both
    are testable by deleting the corresponding block from the descriptor and
    changing nothing else.  Four seeds, CV inside train, held-out untouched.
    """
    labels = sp.load_labels(COMBINED)
    items = collect(COMBINED / "train", labels, "syllable", (F.CANONICAL,))
    classes = sorted({it["label"] for it in items})
    canonical = view(items, F.CANONICAL)
    segmenter, _, units, whiten = ALL_FINALISTS[args.config]
    variants = {
        "selected (parts=3, delta, duration x2)": S.Descriptor(3, True, True, 2.0),
        "duration weight 1 instead of 2": S.Descriptor(3, True, True, 1.0),
        "NO duration": S.Descriptor(3, True, False, 1.0),
        "NO trajectory (parts=1)": S.Descriptor(1, True, True, 2.0),
        "NO trajectory, NO duration": S.Descriptor(1, True, False, 1.0),
        "NO delta block": S.Descriptor(3, False, True, 2.0),
        "duration ONLY (parts=1, no cepstra is impossible; parts=1+dur)":
            S.Descriptor(1, False, True, 2.0),
        "parts=5": S.Descriptor(5, True, True, 2.0),
    }
    print(f"ablation of {args.config}, k={units}, four seeds, CV inside train\n",
          flush=True)
    print(f"{'descriptor':<58}{'dim':>5}{'cos top1':>11}{'sd':>7}{'edit':>9}", flush=True)
    rows = []
    for name, descriptor in variants.items():
        per_seed = [cross_validate(canonical, classes,
                                   ant_builder(units, segmenter, descriptor, s,
                                               whiten=whiten), s)
                    for s in DEFAULT_SEEDS]
        row = {"variant": name, "descriptor": asdict(descriptor),
               "dim": descriptor.dim,
               "top1_cosine": float(np.mean([r["top1_cosine"] for r in per_seed])),
               "sd_over_seeds": float(np.std([r["top1_cosine"] for r in per_seed])),
               "top1_edit": float(np.mean([r["top1_edit"] for r in per_seed])),
               "all_pairs_pooled": float(np.mean([r["all_pairs_pooled"]
                                                  for r in per_seed]))}
        rows.append(row)
        print(f"{name:<58}{descriptor.dim:>5}{row['top1_cosine'] * 100:>10.1f}%"
              f"{row['sd_over_seeds'] * 100:>7.1f}{row['top1_edit'] * 100:>8.1f}%",
              flush=True)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "question": "which part of the segment descriptor is doing the work",
        "protocol": "leave-one-base-out inside train, four seeds, heldout untouched",
        "config": args.config, "units": units,
        "chance_top1": 1 / len(classes),
        "results": rows,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {out}")


def run_cv(args) -> None:
    labels = sp.load_labels(COMBINED)
    t0 = time.time()
    items = collect(COMBINED / "train", labels, "syllable", (F.CANONICAL, "legacy14"))
    classes = sorted({it["label"] for it in items})
    canonical = view(items, F.CANONICAL)
    legacy = view(items, "legacy14")
    print(f"train-only leave-one-base-out: {len(items)} items, {len(classes)} classes, "
          f"featurised in {time.time() - t0:.1f}s\n", flush=True)
    print(f"{'config':<14}{'k':>5}{'segs/item':>11}{'dead':>7}"
          f"{'cos top1':>10}{'(sd)':>8}{'edit top1':>11}{'ba/pa':>8}{'da/ta':>8}"
          f"{'8-pair':>8}", flush=True)

    rows = []
    for row in (cv_grid() if args.grid == 1 else cv_grid2()):
        started = time.time()
        result = cross_validate(canonical, classes,
                                ant_builder(row["units"], row["segmenter"],
                                            row["descriptor"], args.seed), args.seed)
        rows.append({"tag": row["tag"], "units": row["units"],
                     "segmenter": asdict(row["segmenter"]),
                     "descriptor": asdict(row["descriptor"]),
                     "seconds": round(time.time() - started, 1), **result})
        mp = result["minimal_pairs_cosine"]
        print(f"{row['tag']:<14}{row['units']:>5}{result['mean_segments_per_item']:>11.2f}"
              f"{result['mean_dead_units']:>7.0f}"
              f"{result['top1_cosine'] * 100:>9.1f}%{result['top1_cosine_std'] * 100:>7.1f}"
              f"{result['top1_edit'] * 100:>10.1f}%"
              f"{mp.get('ba/pa', 0) * 100:>7.1f}%{mp.get('da/ta', 0) * 100:>7.1f}%"
              f"{result['all_pairs_pooled'] * 100:>7.1f}%", flush=True)

    for tag, name, random_frames in (("frame-km-r26", F.CANONICAL, False),
                                     ("frame-rand-r26", F.CANONICAL, True),
                                     ("frame-km-legacy", "legacy14", False),
                                     ("frame-rand-legacy", "legacy14", True)):
        source = canonical if name == F.CANONICAL else legacy
        for units in (128, 256):
            def build(train_items, units=units, random_frames=random_frames):
                return frame_kmeans(train_items, units, args.seed, random_frames)
            result = cross_validate(source, classes, build, args.seed)
            rows.append({"tag": f"{tag}-{units}", "units": units,
                         "segmenter": None, "descriptor": None, **result})
            mp = result["minimal_pairs_cosine"]
            print(f"{tag + '-' + str(units):<14}{units:>5}"
                  f"{result['mean_segments_per_item']:>11.2f}"
                  f"{result['mean_dead_units']:>7.0f}"
                  f"{result['top1_cosine'] * 100:>9.1f}%"
                  f"{result['top1_cosine_std'] * 100:>7.1f}"
                  f"{result['top1_edit'] * 100:>10.1f}%"
                  f"{mp.get('ba/pa', 0) * 100:>7.1f}%{mp.get('da/ta', 0) * 100:>7.1f}%"
                  f"{result['all_pairs_pooled'] * 100:>7.1f}%", flush=True)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "question": "segmental hyper-parameters, chosen without touching heldout",
        "protocol": "leave-one-base-rendering-out over the train split; the codebook "
                    "is refitted inside every fold; the held-out split is not read",
        "chance_top1": 1 / len(classes),
        "results": sorted(rows, key=lambda r: -r["top1_cosine"]),
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {out}")


def run_heldout(args) -> None:
    t0 = time.time()
    labels = sp.load_labels(COMBINED)
    items_tr = collect(COMBINED / "train", labels, "syllable", (F.CANONICAL, "legacy14"))
    items_he = collect(COMBINED / "heldout", labels, "syllable",
                       (F.CANONICAL, "legacy14"))
    classes = sorted({it["label"] for it in items_tr})
    assert {it["name"] for it in items_tr}.isdisjoint({it["name"] for it in items_he})
    assert {it["base"] for it in items_tr}.isdisjoint({it["base"] for it in items_he})
    tr26, he26 = view(items_tr, F.CANONICAL), view(items_he, F.CANONICAL)
    tr14, he14 = view(items_tr, "legacy14"), view(items_he, "legacy14")
    print(f"train={len(items_tr)} heldout={len(items_he)} classes={len(classes)} "
          f"chance={1 / len(classes):.4f}  featurised in {time.time() - t0:.1f}s\n",
          flush=True)

    segmenter, descriptor, units, whiten = ALL_FINALISTS[args.config]
    if args.segmenter:
        segmenter = S.Segmenter(**json.loads(args.segmenter))
    if args.descriptor:
        descriptor = S.Descriptor(**json.loads(args.descriptor))
    if args.units:
        units = args.units
    print(f"selected {args.config}: k={units} whiten={whiten}\n"
          f"  segmenter  {asdict(segmenter)}\n  descriptor {asdict(descriptor)}\n",
          flush=True)

    groups: list[dict] = []

    def add(group: str, kind: str, ant_name: str, seed: int, encoder,
            seconds: float, legacy: bool = False):
        result = score(tr14 if legacy else tr26, he14 if legacy else he26,
                       classes, encoder, seed)
        result.update({"group": group, "kind": kind, "ant": ant_name, "seed": seed,
                       "train_seconds": seconds})
        groups.append(result)
        print(f"{group:<38}{ant_name} k={result['units']:<5}"
              f"cos@1={result['top1_cosine']:.4f} edit@1={result['top1_edit']:.4f} "
              f"dead={result['dead_units_heldout']:<4} "
              f"segs/item={result['mean_segments_per_item']:.2f} ({seconds}s)",
              flush=True)

    print("segmental k-means (the learner):", flush=True)
    for name, seed in zip(DEFAULT_ANTS, DEFAULT_SEEDS):
        started = time.time()
        ant = S.SegmentalAnt(name, seed, units, segmenter, descriptor, whiten=whiten)
        ant.fit(tr26, exemplars=True)
        seconds = round(time.time() - started, 1)
        add(f"segmental-kmeans-{units}", "segmental-trained", name, seed, ant, seconds)
        S.write_checkpoint(OUT / name / "current.json",
                           ant.to_checkpoint("corpus-combined/train"))

    print("\nrandom real segments (the control that matters):", flush=True)
    for name, seed in zip(DEFAULT_ANTS, DEFAULT_SEEDS):
        started = time.time()
        template = S.SegmentalAnt(name, seed, units, segmenter, descriptor, whiten=whiten)
        control = S.random_real_segments(template, tr26, seed, exemplars=False)
        add(f"random-real-segments-{units}", "segmental-random-real", name, seed,
            control, round(time.time() - started, 1))

    print("\nframe-wise controls:", flush=True)
    for tag, legacy in (("recommended26", False), ("legacy14", True)):
        for random_frames in (False, True):
            for k in sorted({units, 256}):
                for ant_name, seed in zip(DEFAULT_ANTS, DEFAULT_SEEDS):
                    started = time.time()
                    encoder = frame_kmeans(tr14 if legacy else tr26, k, seed,
                                           random_frames)
                    prefix = "random-real-frames" if random_frames else "frame-kmeans"
                    add(f"{prefix}-{tag}-{k}",
                        "frame-" + ("random-real" if random_frames else "trained"),
                        ant_name, seed, encoder, round(time.time() - started, 1),
                        legacy=legacy)

    references = {
        "random_real_segments": f"random-real-segments-{units}",
        "random_real_frames_legacy14_256": "random-real-frames-legacy14-256",
        "frame_kmeans_legacy14_256": "frame-kmeans-legacy14-256",
        "frame_kmeans_recommended26_256": "frame-kmeans-recommended26-256",
    }
    banks = {label: {row["ant"]: row["_correct_cosine"].copy()
                     for row in groups if row["group"] == group}
             for label, group in references.items()}
    masks: dict[str, dict[str, np.ndarray]] = {}
    for row in groups:
        mask = row.pop("_correct_cosine")
        row.pop("_correct_edit")
        masks.setdefault(row["group"], {})[row["ant"]] = mask
        row["mcnemar_cosine"] = {
            label: mcnemar(mask, bank[row["ant"]])
            for label, bank in banks.items() if row["ant"] in bank}

    # The verdict, pooled over the four ants.  Each ant scores the SAME 132
    # held-out items, so the four decision vectors are correlated and a pooled
    # exact test is anti-conservative; the per-ant p-values in `runs` are the
    # conservative reading, and the properly powered comparison is the 1584-
    # decision cross-validation that chose the configuration.
    verdict = {}
    subject = masks[f"segmental-kmeans-{units}"]
    for label, group in references.items():
        if group not in masks:
            continue
        a = np.concatenate([subject[ant] for ant in DEFAULT_ANTS])
        b = np.concatenate([masks[group][ant] for ant in DEFAULT_ANTS])
        verdict[label] = {
            "segmental_top1": float(a.mean()), "reference_top1": float(b.mean()),
            "delta": float(a.mean() - b.mean()),
            "pooled_mcnemar": mcnemar(a, b),
            "pooled_decisions": int(len(a)),
        }

    summary: dict[str, dict] = {}
    for row in groups:
        bucket = summary.setdefault(row["group"], {
            "kind": row["kind"], "units": row["units"], "ants": 0,
            "top1_cosine": [], "top1_edit": [], "dead_units_heldout": [],
            "segments_per_item": [], "segments_per_second": [], "train_seconds": [],
            "ba_pa_cosine": [], "da_ta_cosine": [], "ba_pa_edit": [], "da_ta_edit": []})
        bucket["ants"] += 1
        bucket["top1_cosine"].append(row["top1_cosine"])
        bucket["top1_edit"].append(row["top1_edit"])
        bucket["dead_units_heldout"].append(row["dead_units_heldout"])
        bucket["segments_per_item"].append(row["mean_segments_per_item"])
        bucket["segments_per_second"].append(row["mean_segments_per_second"])
        bucket["train_seconds"].append(row["train_seconds"])
        bucket["ba_pa_cosine"].append(row["minimal_pairs_cosine"].get("ba/pa"))
        bucket["da_ta_cosine"].append(row["minimal_pairs_cosine"].get("da/ta"))
        bucket["ba_pa_edit"].append(row["minimal_pairs_edit"].get("ba/pa"))
        bucket["da_ta_edit"].append(row["minimal_pairs_edit"].get("da/ta"))
    for name, bucket in summary.items():
        for key in list(bucket):
            if isinstance(bucket[key], list):
                bucket[key] = float(np.mean(bucket[key]))

    report = {
        "question": "does quantising SEGMENTS beat quantising frames",
        "probe": "identical to run_knowledge_tests: 1-NN over unit-histogram cosine "
                 "and over Levenshtein on the collapsed unit string, 22 classes",
        "metric_policy": "quantisation error is not reported",
        "published_baselines": {
            "trained_kmeans_256_legacy14_cosine_top1": 0.4186,
            "random_real_frames_256_legacy14_cosine_top1": 0.4034,
            "raw_features_no_codebook_top1": 0.5379,
            "chance": 1 / len(classes),
        },
        "selected_config": args.config,
        "selected_on": "leave-one-base-out CV inside the train split only "
                       "(state-hebbian/segmental/cv-finals1.json), 4 seeds",
        "segmenter": asdict(segmenter),
        "descriptor": asdict(descriptor),
        "units": units,
        "whiten": whiten,
        "heldout_items": len(items_he),
        "train_items": len(items_tr),
        "classes": classes,
        "verdict_vs_references_pooled": verdict,
        "verdict_caveat": "the four ants score the same 132 items, so the pooled "
                          "exact test is anti-conservative; per-ant p-values are in "
                          "`runs`, and the powered comparison is cv-finals1.json",
        "summary": summary,
        "runs": groups,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {out}  ({time.time() - t0:.1f}s total)")
    print(f"\nverdict, segmental vs each reference, pooled over four ants:")
    for label, row in verdict.items():
        print(f"  vs {label:<34}{row['segmental_top1'] * 100:>6.1f}% vs "
              f"{row['reference_top1'] * 100:>5.1f}%  delta {row['delta'] * 100:+5.1f} "
              f"p={row['pooled_mcnemar']['p_value']:.2e}", flush=True)
    print(f"\n{'group':<40}{'cos top1':>10}{'edit top1':>11}{'dead':>7}{'segs/s':>9}")
    for name, bucket in sorted(summary.items(), key=lambda kv: -kv[1]["top1_cosine"]):
        print(f"{name:<40}{bucket['top1_cosine'] * 100:>9.1f}%"
              f"{bucket['top1_edit'] * 100:>10.1f}%"
              f"{bucket['dead_units_heldout']:>7.0f}"
              f"{bucket['segments_per_second']:>9.2f}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cv", action="store_true")
    parser.add_argument("--finals", action="store_true")
    parser.add_argument("--ablate", action="store_true")
    parser.add_argument("--grid", type=int, default=1)
    parser.add_argument("--units", type=int, default=0)
    parser.add_argument("--config", default=SELECTED, choices=sorted(ALL_FINALISTS))
    parser.add_argument("--seed", type=int, default=7007)
    parser.add_argument("--segmenter", default="")
    parser.add_argument("--descriptor", default="")
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    if not args.out:
        args.out = str(OUT / ("ablation.json" if args.ablate else
                              f"cv-finals{args.grid}.json" if args.finals else
                              f"cv-grid{args.grid}.json" if args.cv else "heldout.json"))
    (run_ablation if args.ablate else run_finals if args.finals
     else run_cv if args.cv else run_heldout)(args)


if __name__ == "__main__":
    main()
