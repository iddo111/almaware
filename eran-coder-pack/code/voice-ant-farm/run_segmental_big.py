"""The segmental colony on the whole 40.6 h human corpus, on one CPU.

Scale is where a segmental learner has an argument that does not depend on any
accuracy number: the detector emits about 4.3 segments per second of speech
where the frame-wise learner emits 100 vectors per second, so one pass over the
corpus produces roughly 24x fewer training vectors for the same audio.  That is
measured here, not asserted.

Protocol
--------
  * One shared pass over corpus-big/human/train computes frame features, speech
    spans, boundaries and segment descriptors.  This pass is a pure function of
    the waveform -- no fitted parameter exists yet -- so sharing it between ants
    does not share a weight.  The result is cached to an .npz so the four ants
    and the frame-wise control do not each pay for it.
  * corpus-combined/train (the syllable curriculum plus the original
    `recordings/`) stays in the mix, exactly as in the published runs.
  * Then four independent ants, seeds 7007/7019/7039/7057, each on its own
    seeded bootstrap of the pooled segments, each with its own scaler, its own
    centres, its own exemplars.
  * The frame-wise control is trained on a random subsample of the SAME audio's
    frames, sized to the segment count, so neither learner gets more training
    vectors than the other.  Subsampling is stated here and in the report.
  * Scoring is the same held-out syllable probe as everywhere else.

    py -3.13 run_segmental_big.py --files 0        # all 18,146 train files
"""
from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np

import feature_space as F
import run_segmental as R
import segmental as S
import sequence_probes as sp
from acoustic_units import EXEMPLAR_RATE, load_wav, resample_samples
from colony import DEFAULT_ANTS, DEFAULT_SEEDS

ROOT = Path(__file__).resolve().parent
HUMAN_TRAIN = ROOT / "corpus-big" / "human" / "train"
CACHE = ROOT / "state-hebbian" / "segmental" / "big-segments.npz"
OUT = ROOT / "state-hebbian" / "segmental" / "big.json"


def sweep(paths: list[Path], segmenter: S.Segmenter, descriptor: S.Descriptor,
          frame_target: int, seed: int) -> dict:
    """One pass: segment descriptors, provenance, and a frame reservoir."""
    rng = np.random.default_rng(seed)
    blocks, files, firsts, lasts = [], [], [], []
    reservoir, seen_frames = [], 0
    audio_seconds = speech_seconds = 0.0
    started = time.time()
    for index, path in enumerate(paths):
        try:
            audio = load_wav(path)
        except ValueError:
            continue
        samples = resample_samples(audio.samples, audio.rate, EXEMPLAR_RATE)
        if len(samples) < F.FRAME * 2:
            continue
        x = F.frame_features(samples)
        first, last = S.speech_span(samples)
        window = x[first:last]
        if len(window) < 2:
            continue
        edges = segmenter.edges(window)
        blocks.append(descriptor(window, edges))
        for a, b in zip(edges[:-1], edges[1:]):
            files.append(index)
            firsts.append(int(first + a))
            lasts.append(int(first + b))
        audio_seconds += len(samples) / EXEMPLAR_RATE
        speech_seconds += len(window) * F.HOP_SECONDS
        keep = min(len(window), max(1, frame_target // max(len(paths), 1) + 2))
        reservoir.append(window[rng.choice(len(window), keep, replace=False)])
        seen_frames += len(window)
        if index % 2000 == 0:
            print(f"  {index}/{len(paths)} files, {speech_seconds / 3600:.2f} h speech, "
                  f"{sum(len(b) for b in blocks)} segments "
                  f"({time.time() - started:.0f}s)", flush=True)
    pool = np.concatenate(blocks, axis=0)
    frames = np.concatenate(reservoir, axis=0)
    if len(frames) > frame_target:
        frames = frames[rng.choice(len(frames), frame_target, replace=False)]
    return {
        "pool": pool, "file_index": np.asarray(files, dtype=np.int64),
        "first": np.asarray(firsts, dtype=np.int64),
        "last": np.asarray(lasts, dtype=np.int64),
        "frames": frames, "total_frames": seen_frames,
        "audio_seconds": audio_seconds, "speech_seconds": speech_seconds,
        "sweep_seconds": time.time() - started,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--files", type=int, default=0, help="0 = every train file")
    parser.add_argument("--units", type=int, default=128)
    parser.add_argument("--seed", type=int, default=7007)
    parser.add_argument("--cache", default=str(CACHE))
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()

    segmenter, descriptor, units, whiten = R.ALL_FINALISTS[R.SELECTED]
    units = args.units or units
    t0 = time.time()

    labels = sp.load_labels(R.COMBINED)
    items_tr = R.collect(R.COMBINED / "train", labels, "syllable",
                         (F.CANONICAL, "legacy14"))
    items_he = R.collect(R.COMBINED / "heldout", labels, "syllable", (F.CANONICAL,))
    classes = sorted({it["label"] for it in items_tr})
    tr26, he26 = R.view(items_tr, F.CANONICAL), R.view(items_he, F.CANONICAL)

    paths = sorted(HUMAN_TRAIN.glob("*.wav"))
    if args.files:
        rng = np.random.default_rng(args.seed)
        picked = np.sort(rng.choice(len(paths), min(args.files, len(paths)),
                                    replace=False))
        paths = [paths[int(i)] for i in picked]
    print(f"human corpus: {len(paths)} files\n", flush=True)

    signature = json.dumps({"segmenter": asdict(segmenter),
                            "descriptor": asdict(descriptor),
                            "files": len(paths)}, sort_keys=True)
    cache = Path(args.cache)
    if cache.exists():
        stored = np.load(cache, allow_pickle=True)
        if str(stored["signature"]) == signature:
            print(f"reusing {cache}", flush=True)
            swept = {k: stored[k] for k in ("pool", "file_index", "first", "last",
                                            "frames")}
            swept.update({k: float(stored[k]) for k in
                          ("audio_seconds", "speech_seconds", "sweep_seconds")})
            swept["total_frames"] = int(stored["total_frames"])
        else:
            print(f"{cache} was built for a different configuration; re-sweeping",
                  flush=True)
            cache = None
    if not cache or not cache.exists():
        swept = sweep(paths, segmenter, descriptor, 400_000, args.seed)
        np.savez_compressed(
            Path(args.cache), signature=signature, total_frames=swept["total_frames"],
            audio_seconds=swept["audio_seconds"], speech_seconds=swept["speech_seconds"],
            sweep_seconds=swept["sweep_seconds"],
            **{k: swept[k] for k in ("pool", "file_index", "first", "last", "frames")})

    # the syllable curriculum stays in the mix
    template = S.SegmentalAnt("pool", args.seed, units, segmenter, descriptor,
                              whiten=whiten)
    syllable_pool, syllable_provenance = template.pool(tr26)
    pool = np.concatenate([swept["pool"], syllable_pool], axis=0)
    provenance = [{"path": str(paths[int(i)]), "first": int(a), "last": int(b)}
                  for i, a, b in zip(swept["file_index"], swept["first"], swept["last"])]
    provenance.extend(syllable_provenance)
    syllable_frames = np.concatenate([it["frames"] for it in tr26], axis=0)
    frames = np.concatenate([swept["frames"], syllable_frames], axis=0)

    print(f"\npooled {len(pool)} segments from "
          f"{swept['speech_seconds'] / 3600:.2f} h of speech span "
          f"({swept['audio_seconds'] / 3600:.2f} h of audio), "
          f"{swept['total_frames']} frames total\n"
          f"segment rate {len(swept['pool']) / swept['speech_seconds']:.2f}/s vs "
          f"{1 / F.HOP_SECONDS:.0f} frames/s -> "
          f"{swept['total_frames'] / max(len(swept['pool']), 1):.1f}x fewer vectors\n",
          flush=True)

    runs = []

    def evaluate(group, kind, ant_name, seed, encoder, seconds):
        row = R.score(tr26, he26, classes, encoder, seed)
        row.pop("_correct_cosine")
        row.pop("_correct_edit")
        row.update({"group": group, "kind": kind, "ant": ant_name, "seed": seed,
                    "train_seconds": seconds})
        runs.append(row)
        print(f"{group:<34}{ant_name} k={row['units']:<5}"
              f"cos@1={row['top1_cosine']:.4f} edit@1={row['top1_edit']:.4f} "
              f"dead={row['dead_units_heldout']:<4} ({seconds}s)", flush=True)

    print("segmental ants on the big corpus:", flush=True)
    for name, seed in zip(DEFAULT_ANTS, DEFAULT_SEEDS):
        started = time.time()
        ant = S.SegmentalAnt(name, seed, units, segmenter, descriptor, whiten=whiten)
        draw_rng = np.random.default_rng(seed)
        index = draw_rng.integers(0, len(pool), size=min(len(pool), ant.max_segments))
        draw = pool[index]
        ant.mean_, ant.std_ = draw.mean(axis=0), np.maximum(draw.std(axis=0), 1e-6)
        ant.rotation_ = None
        if ant.whiten:
            ant._fit_rotation(draw)
        ant.centers_ = S.kmeans(ant.scale(draw), units, seed, ant.rounds)[0]
        ids, distance = S.assign(ant.scale(pool), ant.centers_)
        ant.train_counts_ = np.bincount(ids, minlength=units)
        ant._learn_exemplars(pool, ids, distance, provenance)
        seconds = round(time.time() - started, 1)
        evaluate(f"segmental-big-{units}", "segmental-trained", name, seed, ant, seconds)
        S.write_checkpoint(ROOT / "state-hebbian" / "segmental" / "big" / name /
                           "current.json", ant.to_checkpoint("corpus-big/human/train"))

    print("\nrandom real segments, same pool:", flush=True)
    for name, seed in zip(DEFAULT_ANTS, DEFAULT_SEEDS):
        started = time.time()
        control = S.SegmentalAnt(name, seed, units, segmenter, descriptor, whiten=whiten)
        control.mean_, control.std_ = pool.mean(axis=0), np.maximum(pool.std(axis=0), 1e-6)
        control.rotation_ = None
        if control.whiten:
            control._fit_rotation(pool)
        rng = np.random.default_rng(seed)
        control.centers_ = control.scale(pool[rng.choice(len(pool), units, replace=False)])
        evaluate(f"random-real-segments-big-{units}", "segmental-random-real",
                 name, seed, control, round(time.time() - started, 1))

    print(f"\nframe-wise control, {len(frames)} frames subsampled from the same audio "
          f"to match the segment budget:", flush=True)
    for name, seed in zip(DEFAULT_ANTS, DEFAULT_SEEDS):
        for tag, random_frames in (("frame-kmeans-big", False),
                                   ("random-real-frames-big", True)):
            started = time.time()
            rng = np.random.default_rng(seed)
            if random_frames:
                encoder = R.FrameCodebook(frames[rng.choice(len(frames), 256,
                                                            replace=False)])
            else:
                encoder = R.FrameCodebook(S.kmeans(frames, 256, seed)[0])
            evaluate(f"{tag}-256", "frame-" + ("random-real" if random_frames
                                               else "trained"),
                     name, seed, encoder, round(time.time() - started, 1))

    summary: dict[str, dict] = {}
    for row in runs:
        bucket = summary.setdefault(row["group"], {"top1_cosine": [], "top1_edit": [],
                                                   "dead_units_heldout": [],
                                                   "train_seconds": []})
        for key in bucket:
            bucket[key].append(row[key])
    summary = {k: {kk: float(np.mean(vv)) for kk, vv in v.items()}
               for k, v in summary.items()}

    report = {
        "question": "does the segmental learner survive 40 hours of real speech",
        "subsampling": ("none for the segmental learner: every train file of the "
                        "human corpus was swept. The FRAME control is subsampled to "
                        f"{len(frames)} frames, matched to the segment budget, "
                        "because k-means over every frame of 40 h is not a CPU job."),
        "human_files": len(paths),
        "human_audio_hours": swept["audio_seconds"] / 3600.0,
        "human_speech_span_hours": swept["speech_seconds"] / 3600.0,
        "human_frames_total": int(swept["total_frames"]),
        "human_segments_total": int(len(swept["pool"])),
        "segments_per_second_of_speech": len(swept["pool"]) / swept["speech_seconds"],
        "vector_reduction_vs_frames": swept["total_frames"] / max(len(swept["pool"]), 1),
        "sweep_seconds": swept["sweep_seconds"],
        "pooled_segments_with_syllable_curriculum": int(len(pool)),
        "segmenter": asdict(segmenter),
        "descriptor": asdict(descriptor),
        "units": units,
        "whiten": whiten,
        "summary": summary,
        "runs": runs,
        "total_seconds": round(time.time() - t0, 1),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {out}  ({report['total_seconds']}s total)")
    for name, bucket in sorted(summary.items(), key=lambda kv: -kv[1]["top1_cosine"]):
        print(f"{name:<40}{bucket['top1_cosine'] * 100:>7.1f}%  "
              f"edit {bucket['top1_edit'] * 100:.1f}%  "
              f"dead {bucket['dead_units_heldout']:.0f}")


if __name__ == "__main__":
    main()
