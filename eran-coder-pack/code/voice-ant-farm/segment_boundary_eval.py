"""Is the boundary detector finding boundaries, or just finding something?

Three questions, all checkable without a phonetic annotator:

  1. RATE.  How many segments per second does it emit -- on single syllables, on
     the 12 Hebrew words, and on the 40.6 h human corpus?  A detector that emits
     50/s is a frame-wise learner wearing a hat; one that emits 2/s is a voice
     activity detector.  Hebrew speech runs at roughly 12-15 phones/s and 4-6
     syllables/s, so those two numbers bracket the honest target.

  2. PLACEMENT.  Held-out syllables are trimmed to their own speech spans and
     butt-joined into chains, so every junction is a syllable boundary whose
     time is known to the sample.  Precision, recall, F1 and R-value at the
     project's fixed 20 ms tolerance, against three nulls: a uniform grid with
     the same boundary count, uniformly random boundaries with the same count,
     and the incumbent frame codebook's own unit transitions.
     Caveat, stated up front: a butt joint has no coarticulation across it, so
     it is an EASIER boundary than a real one inside connected speech.  Recall
     here is an upper bound.  It is still the only exact ground truth available.

  3. REPEATABILITY.  Augmentation twins are the same base rendering at a
     different tempo, gain, noise and padding.  The manifest records the WSOLA
     tempo factor and the lead padding exactly, so a boundary in one twin maps
     to base-rendering time as (t - pad_lead) / tempo and can be compared with
     its sibling's to the sample.  No annotation needed, and it catches a
     detector that fires on the noise rather than on the speech.

    py -3.13 segment_boundary_eval.py
"""
from __future__ import annotations

import argparse
import json
import math
import time
from itertools import combinations
from pathlib import Path

import numpy as np

import feature_space as F
import run_segmental as R
import segmental as S
import sequence_probes as sp
from acoustic_units import EXEMPLAR_RATE, load_wav, resample_samples
from boundary_repeatability import BOUNDARY_TOLERANCE_SECONDS, _scores, match_boundaries
from colony import DEFAULT_SEEDS

ROOT = Path(__file__).resolve().parent
COMBINED = ROOT / "corpus-combined"
SYLLABLE_MANIFEST = ROOT / "corpus-syllables" / "manifest.json"
HUMAN = ROOT / "corpus-big" / "human" / "heldout"
OUT = ROOT / "state-hebbian" / "segmental" / "boundaries.json"
RATE = F.RATE


def r_value(precision: float, recall: float) -> float:
    """Rasanen's R: F1 rewards over-segmentation, R penalises it.  0.5 is chance-ish,
    1.0 is perfect, and a detector that fires on every frame scores below zero."""
    if precision <= 0.0 or recall <= 0.0:
        return 0.0
    p, r = 100.0 * precision, 100.0 * recall
    os_ = r / p * 100.0 - 100.0
    r1 = math.sqrt((100.0 - r) ** 2 + os_ ** 2)
    r2 = (-os_ + r - 100.0) / math.sqrt(2.0)
    return 1.0 - (abs(r1) + abs(r2)) / 200.0


def boundary_times(edges: np.ndarray, offset_frames: int = 0) -> list[float]:
    """Interior segment edges as seconds, at the centre of the boundary frame."""
    interior = [int(e) for e in edges[1:-1]]
    return [((e + offset_frames) * F.HOP + F.FRAME / 2.0) / RATE for e in interior]


def scored(predicted: list[float], reference: list[float]) -> dict:
    tp, fp, fn, errors = match_boundaries(predicted, reference,
                                          BOUNDARY_TOLERANCE_SECONDS)
    out = _scores(tp, fp, fn)
    out["r_value"] = round(r_value(out["precision"], out["recall"]), 6)
    out["mean_abs_error_ms"] = round(1000.0 * float(np.mean(errors)), 2) if errors else None
    return out


# ---------------------------------------------------------------------------
# 1. rate
# ---------------------------------------------------------------------------

def rate_on(paths: list[Path], segmenter: S.Segmenter, span: bool = True) -> dict:
    segments, seconds, per_file = 0, 0.0, []
    for path in paths:
        audio = load_wav(path)
        samples = resample_samples(audio.samples, audio.rate, EXEMPLAR_RATE)
        x = F.frame_features(samples)
        first, last = S.speech_span(samples) if span else (0, len(x))
        window = x[first:last]
        if len(window) < 2:
            continue
        edges = segmenter.edges(window)
        segments += len(edges) - 1
        seconds += len(window) * F.HOP_SECONDS
        per_file.append(len(edges) - 1)
    return {
        "files": len(per_file),
        "speech_seconds": round(seconds, 2),
        "segments": int(segments),
        "segments_per_second": round(segments / max(seconds, 1e-9), 3),
        "segments_per_file_mean": round(float(np.mean(per_file)), 3) if per_file else None,
        "mean_segment_ms": round(1000.0 * seconds / max(segments, 1), 2),
    }


# ---------------------------------------------------------------------------
# 2. placement, against exact junctions
# ---------------------------------------------------------------------------

def trimmed(path: Path) -> np.ndarray:
    audio = load_wav(path)
    samples = resample_samples(audio.samples, audio.rate, EXEMPLAR_RATE)
    first, last = S.speech_span(samples)
    return S.segment_waveform(samples, first, last)


def build_chains(paths: list[Path], per_chain: int, seed: int, chains: int
                 ) -> list[tuple[np.ndarray, list[float]]]:
    """Butt-joined syllable chains.  Junction times are exact by construction."""
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(paths))
    cache = {}
    out = []
    for c in range(chains):
        picks = order[(c * per_chain) % len(order):][:per_chain]
        if len(picks) < per_chain:
            picks = rng.choice(len(paths), per_chain, replace=False)
        pieces = []
        for i in picks:
            if int(i) not in cache:
                cache[int(i)] = trimmed(paths[int(i)])
            pieces.append(cache[int(i)])
        junctions, cursor = [], 0
        for piece in pieces[:-1]:
            cursor += len(piece)
            junctions.append(cursor / RATE)
        out.append((np.concatenate(pieces), junctions))
    return out


def greedy_match(predicted: list[float], reference: list[float], tolerance: float
                 ) -> tuple[int, list[float]]:
    """Same rule as boundary_repeatability.match_boundaries, at a free tolerance.

    That function pins the tolerance at 20 ms on purpose, so widening it needs a
    separate implementation rather than an argument.  Used only for the
    sensitivity sweep below: if recall jumps at 40 ms the boundaries are in
    roughly the right place and merely imprecise, which is a different fault
    from missing them.
    """
    predicted, reference = sorted(predicted), sorted(reference)
    i = j = 0
    errors = []
    while i < len(predicted) and j < len(reference):
        delta = predicted[i] - reference[j]
        if abs(delta) <= tolerance + 1e-12:
            errors.append(abs(delta))
            i += 1
            j += 1
        elif delta < -tolerance:
            i += 1
        else:
            j += 1
    return len(errors), errors


def tolerance_sweep(chains, segmenter: S.Segmenter, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    predictions, truth, nulls = [], [], []
    for audio, junctions in chains:
        edges = segmenter.edges(F.frame_features(audio))
        times = boundary_times(edges)
        predictions.append(times)
        truth.append(junctions)
        nulls.append(sorted(float(v) for v in
                            rng.uniform(0.0, len(audio) / RATE, max(len(times), 1))))
    out = {}
    for milliseconds in (10, 20, 30, 40, 60):
        tolerance = milliseconds / 1000.0
        hit = sum(greedy_match(p, t, tolerance)[0] for p, t in zip(predictions, truth))
        null = sum(greedy_match(p, t, tolerance)[0] for p, t in zip(nulls, truth))
        total = sum(len(t) for t in truth)
        emitted = sum(len(p) for p in predictions)
        out[f"{milliseconds}ms"] = {
            "recall": round(hit / total, 4),
            "precision": round(hit / emitted, 4),
            "random_null_recall": round(null / total, 4),
            "recall_over_null": round(hit / max(null, 1), 3),
        }
    return out


def placement(chains, segmenter: S.Segmenter, frame_codebook) -> dict:
    detectors = {"segmenter": [], "uniform_grid": [], "random_uniform": [],
                 "frame_codebook_transitions": []}
    truth = []
    rng = np.random.default_rng(7007)
    for audio, junctions in chains:
        x = F.frame_features(audio)
        edges = segmenter.edges(x)
        mine = boundary_times(edges)
        detectors["segmenter"].append(mine)
        truth.append(junctions)
        duration = len(audio) / RATE
        n = max(len(mine), 1)
        detectors["uniform_grid"].append(
            [duration * (i + 1) / (n + 1) for i in range(n)])
        detectors["random_uniform"].append(
            sorted(float(v) for v in rng.uniform(0.0, duration, n)))
        ids, _ = frame_codebook.encode_features(x)
        change = np.flatnonzero(ids[1:] != ids[:-1]) + 1
        detectors["frame_codebook_transitions"].append(
            [(int(t) * F.HOP + F.FRAME / 2.0) / RATE for t in change])
    out = {}
    for name, predictions in detectors.items():
        tp = fp = fn = 0
        errors = []
        for predicted, reference in zip(predictions, truth):
            a, b, c, e = match_boundaries(predicted, reference,
                                          BOUNDARY_TOLERANCE_SECONDS)
            tp, fp, fn = tp + a, fp + b, fn + c
            errors.extend(e)
        row = _scores(tp, fp, fn)
        row["r_value"] = round(r_value(row["precision"], row["recall"]), 6)
        row["mean_abs_error_ms"] = (round(1000.0 * float(np.mean(errors)), 2)
                                    if errors else None)
        row["predicted_per_chain"] = round(float(np.mean([len(p) for p in predictions])), 2)
        row["reference_per_chain"] = round(float(np.mean([len(t) for t in truth])), 2)
        out[name] = row
    return out


# ---------------------------------------------------------------------------
# 3. repeatability across augmentation twins
# ---------------------------------------------------------------------------

def manifest_index() -> dict:
    entries = json.loads(SYLLABLE_MANIFEST.read_text(encoding="utf-8"))["entries"]
    return {Path(e["path"]).name: e for e in entries}


def twin_repeatability(paths: list[Path], segmenter: S.Segmenter, seed: int) -> dict:
    """Two renderings of one base utterance, mapped back to base-rendering time.

    t_base = (t_file - pad_lead) / tempo, both recorded exactly in the manifest,
    so this needs no annotation and no alignment search.  The null is the same
    number of boundaries placed uniformly at random over the same span.
    """
    index = manifest_index()
    groups: dict[str, list[tuple[str, list[float], float]]] = {}
    for path in paths:
        entry = index.get(path.name)
        if entry is None or entry["item_kind"] != "syllable":
            continue
        audio = load_wav(path)
        samples = resample_samples(audio.samples, audio.rate, EXEMPLAR_RATE)
        x = F.frame_features(samples)
        first, last = S.speech_span(samples)
        window = x[first:last]
        if len(window) < 2:
            continue
        edges = segmenter.edges(window)
        pad = entry["augmentation"]["pad_lead_ms"] / 1000.0
        tempo = entry["augmentation"]["tempo_wsola"]
        times = [(t - pad) / tempo for t in boundary_times(edges, first)]
        extent = ((len(x) * F.HOP_SECONDS) - pad) / tempo
        groups.setdefault(entry["base_rendering_id"], []).append(
            (path.name, times, extent))
    rng = np.random.default_rng(seed)
    tp = fp = fn = 0
    null_tp = null_fp = null_fn = 0
    errors, pairs = [], 0
    for members in groups.values():
        for (_, left, extent_l), (_, right, extent_r) in combinations(members, 2):
            a, b, c, e = match_boundaries(left, right, BOUNDARY_TOLERANCE_SECONDS)
            tp, fp, fn = tp + a, fp + b, fn + c
            errors.extend(e)
            pairs += 1
            fake = sorted(float(v) for v in rng.uniform(0.0, max(extent_l, 1e-6),
                                                        len(left)))
            a, b, c, _ = match_boundaries(fake, right, BOUNDARY_TOLERANCE_SECONDS)
            null_tp, null_fp, null_fn = null_tp + a, null_fp + b, null_fn + c
    result = _scores(tp, fp, fn)
    result["mean_abs_error_ms"] = (round(1000.0 * float(np.mean(errors)), 2)
                                   if errors else None)
    result["twin_pairs"] = pairs
    result["base_renderings"] = len(groups)
    result["null_random_same_count"] = _scores(null_tp, null_fp, null_fn)
    return result


# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(OUT))
    parser.add_argument("--config", default="",
                        help="JSON Segmenter kwargs; default is the selected one")
    parser.add_argument("--human-files", type=int, default=400)
    parser.add_argument("--chains", type=int, default=48)
    parser.add_argument("--per-chain", type=int, default=8)
    parser.add_argument("--seed", type=int, default=7007)
    args = parser.parse_args()

    segmenter = (S.Segmenter(**json.loads(args.config)) if args.config
                 else R.ALL_FINALISTS[R.SELECTED][0])
    t0 = time.time()
    labels = sp.load_labels(COMBINED)
    held = [p for p in sorted((COMBINED / "heldout").glob("*.wav"))
            if labels.get(p.name, {}).get("item_kind") == "syllable"]
    words = [p for p in sorted((COMBINED / "evaluation").glob("*.wav"))
             if labels.get(p.name, {}).get("item_kind") == "word"]
    human = sorted(HUMAN.glob("*.wav"))
    if len(human) > args.human_files:
        rng = np.random.default_rng(args.seed)
        human = [human[int(i)] for i in
                 np.sort(rng.choice(len(human), args.human_files, replace=False))]

    print(f"segmenter {segmenter}\n", flush=True)
    rates = {
        "heldout_syllables": rate_on(held, segmenter),
        "words": rate_on(words, segmenter),
        f"human_corpus_sample_{len(human)}_files": rate_on(human, segmenter),
    }
    for name, row in rates.items():
        print(f"{name:<38}{row['segments_per_second']:>8.2f} seg/s   "
              f"{row['mean_segment_ms']:>7.1f} ms/seg   "
              f"{row['segments_per_file_mean']:>6.2f} seg/file", flush=True)

    train_items = R.collect(COMBINED / "train", labels, "syllable", (F.CANONICAL,))
    frame_codebook = R.frame_kmeans(R.view(train_items, F.CANONICAL), 256,
                                    args.seed, False)
    chains = build_chains(held, args.per_chain, args.seed, args.chains)
    place = placement(chains, segmenter, frame_codebook)
    print(f"\nplacement on {args.chains} chains of {args.per_chain} trimmed "
          f"held-out syllables, {int(BOUNDARY_TOLERANCE_SECONDS * 1000)} ms tolerance",
          flush=True)
    print(f"{'detector':<34}{'prec':>8}{'recall':>8}{'F1':>8}{'R-val':>8}"
          f"{'pred/chain':>12}{'err ms':>8}", flush=True)
    for name, row in place.items():
        print(f"{name:<34}{row['precision'] * 100:>7.1f}%{row['recall'] * 100:>7.1f}%"
              f"{row['f1'] * 100:>7.1f}%{row['r_value']:>8.3f}"
              f"{row['predicted_per_chain']:>12.1f}"
              f"{(row['mean_abs_error_ms'] or 0):>8.1f}", flush=True)

    sweep = tolerance_sweep(chains, segmenter, args.seed)
    print(f"\ntolerance sensitivity (same chains)\n{'tol':<8}{'recall':>9}{'prec':>9}"
          f"{'null recall':>13}{'x null':>8}", flush=True)
    for name, row in sweep.items():
        print(f"{name:<8}{row['recall'] * 100:>8.1f}%{row['precision'] * 100:>8.1f}%"
              f"{row['random_null_recall'] * 100:>12.1f}%{row['recall_over_null']:>8.2f}",
              flush=True)

    twins = twin_repeatability(held, segmenter, args.seed)
    print(f"\nrepeatability over {twins['twin_pairs']} augmentation-twin pairs: "
          f"F1={twins['f1'] * 100:.1f}%  (random null "
          f"{twins['null_random_same_count']['f1'] * 100:.1f}%)  "
          f"mean |error| {twins['mean_abs_error_ms']} ms", flush=True)

    report = {
        "question": "how often does the detector fire, and does it fire in the "
                    "right places",
        "tolerance_seconds": BOUNDARY_TOLERANCE_SECONDS,
        "segmenter": segmenter.__dict__,
        "caveat": "chain junctions have no coarticulation across them, so chain "
                  "recall is an upper bound on recall inside connected speech",
        "rates": rates,
        "placement_on_syllable_chains": place,
        "placement_tolerance_sweep": sweep,
        "twin_repeatability": twins,
        "seconds": round(time.time() - t0, 1),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {out}  ({report['seconds']}s)")


if __name__ == "__main__":
    main()
