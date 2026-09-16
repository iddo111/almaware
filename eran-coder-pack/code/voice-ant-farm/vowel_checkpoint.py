"""Build a sealed, GUI-servable checkpoint for a vowel-cochlea (v2) ant.

The vowel-cochlea ants (reports/vowel-cochlea-knowledge.json) are
random-real-frames codebooks over `recommended26` features. To let the live
dialogue GUI serve one, it must be a full format-3 checkpoint: centers AND one
real waveform exemplar per unit, sealed with the standard digest. Because the
kind is random-real-frames, every center IS a real training frame, so its
exemplar is recovered exactly — the same 25 ms of audio the center was drawn
from, by construction, not by nearest-neighbour search.

Autonomy law: no label, no curation. The pool is the whole uncurated
corpus-combined/train folder, deduplicated by pcm hash, in sorted file order —
byte-identical to acoustic_units.dataset and to the published eval runs.

    py -3.13 vowel_checkpoint.py --ant ant-a --units 512
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

import feature_space as F
from acoustic_units import (EXEMPLAR_RATE, FRAME_SECONDS, HOP_SECONDS,
                            checkpoint_digest, load_checkpoint, load_wav,
                            resample_samples, write_json_atomic)
from colony import DEFAULT_ANTS, DEFAULT_SEEDS

ROOT = Path(__file__).resolve().parent
COMBINED = ROOT / "corpus-combined"
COCHLEA = "recommended26"
FRAME = round(FRAME_SECONDS * EXEMPLAR_RATE)   # 400
HOP = round(HOP_SECONDS * EXEMPLAR_RATE)       # 160

FEATURE_SPEC_V2 = {
    "version": 2,
    "name": COCHLEA,
    "canonical_sample_rate": EXEMPLAR_RATE,
    "frame_seconds": FRAME_SECONDS,
    "hop_seconds": HOP_SECONDS,
    "features": ["c1..c20 of DCT-II over 26-band log-mel (50-8000 Hz, "
                 "pre-emphasis 0.97, relative -80 dB floor)",
                 "d1 of c1..c6 over a +/-40 ms regression window"],
    "scaling": "divide frames AND centers by frame_scaler "
               "(per-dimension std of the ant's own uncurated train pool)",
    "selection_basis": "state-hebbian/feature-selection.json — train-only CV; "
                       "the held-out split was never read by the selection",
}


def feature_spec_for(cochlea: str, scaled: bool) -> dict:
    spec = dict(FEATURE_SPEC_V2)
    spec["name"] = cochlea
    if cochlea != COCHLEA:
        spec["features"] = [f"feature_space.extract('{cochlea}')",
                            F.SETS[cochlea].note]
    if not scaled:
        spec["scaling"] = "none (unweighted Euclidean)"
    return spec


def build_pool(cochlea: str = COCHLEA) -> tuple[np.ndarray, list[dict]]:
    """(pool, files): frames over full files + per-file provenance."""
    frames, files, hashes = [], [], set()
    for path in sorted((COMBINED / "train").glob("*.wav")):
        audio = load_wav(path)
        if audio.pcm_sha256 in hashes:
            continue
        hashes.add(audio.pcm_sha256)
        samples = resample_samples(audio.samples, audio.rate, EXEMPLAR_RATE)
        x = F.extract(cochlea, samples).astype(np.float32)
        files.append({"name": path.name, "pcm_sha256": audio.pcm_sha256,
                      "n_frames": len(x), "samples": samples})
        frames.append(x)
    return np.concatenate(frames), files


def heldout_hashes() -> list[str]:
    out = set()
    for path in sorted((COMBINED / "heldout").glob("*.wav")):
        out.add(load_wav(path).pcm_sha256)
    return sorted(out)


def build(ant: str, units: int, eval_summary: dict | None = None,
          cochlea: str = COCHLEA, scaled: bool = True,
          seed: int | None = None,
          pool_and_files: tuple | None = None) -> dict:
    if seed is None:
        seed = dict(zip(DEFAULT_ANTS, DEFAULT_SEEDS))[ant]
    pool, files = pool_and_files if pool_and_files else build_pool(cochlea)
    scaler = np.maximum(pool.astype(np.float64).std(axis=0), 1e-6
                        ).astype(np.float32)
    if not scaled:
        scaler = np.ones_like(scaler)
    rng = np.random.default_rng(seed)
    idx = rng.choice(len(pool), units, replace=False)
    centers_scaled = (pool[idx] / scaler).astype(np.float32)

    # exact exemplar recovery: global frame index -> (file, local frame)
    starts = np.cumsum([0] + [f["n_frames"] for f in files])
    exemplars, ex_hashes, ex_indexes = [], [], []
    for g in idx:
        k = int(np.searchsorted(starts, g, side="right") - 1)
        local = int(g - starts[k])
        s = files[k]["samples"][local * HOP: local * HOP + FRAME]
        if len(s) != FRAME:                       # tail frame safety
            s = np.pad(s, (0, FRAME - len(s)))
        exemplars.append(np.clip(np.rint(s * 32767), -32768, 32767
                                 ).astype("<i2").tolist())
        ex_hashes.append(files[k]["pcm_sha256"])
        ex_indexes.append(local)

    spec = feature_spec_for(cochlea, scaled)
    checkpoint = {
        "format_version": 3,
        "architecture": "waveform-acoustic-vector-quantizer-with-exemplars",
        "audio_hash_kind": "sha256(sample_rate_le32+decoded_pcm16le)",
        "feature_spec": spec,
        "experiment_namespace": hashlib.sha256(json.dumps(
            {"feature_spec": spec, "units": units},
            sort_keys=True).encode()).hexdigest(),
        "corpus_provenance": {"train": "corpus-combined/train (uncurated, "
                                       "pcm-hash dedup, sorted order)",
                              "sample_rates": [EXEMPLAR_RATE]},
        "ant": ant,
        "seed": seed,
        "units": units,
        "feature_dim": int(centers_scaled.shape[1]),
        "codebook_kind": "random-real-frames (centers are real train frames; "
                         "no Lloyd iterations; no label touched anything)",
        "frame_scaler": scaler.tolist(),
        "train_frame_count": int(len(pool)),
        "train_audio_hashes": sorted(f["pcm_sha256"] for f in files),
        "heldout_audio_hashes": heldout_hashes(),
        "metric_policy": "quantisation error is not recorded here; it does "
                         "not rank ants on the discrimination task",
        "evaluation": eval_summary,
        "centers": centers_scaled.tolist(),
        "exemplar_rate": EXEMPLAR_RATE,
        "exemplar_frame_samples": FRAME,
        "exemplar_hop_samples": HOP,
        "exemplars_pcm16": exemplars,
        "exemplar_source_hashes": ex_hashes,
        "exemplar_source_frame_indexes": ex_indexes,
    }
    checkpoint["checkpoint_sha256"] = checkpoint_digest(checkpoint)
    return checkpoint


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ant", default="ant-a")
    ap.add_argument("--units", type=int, default=512)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    evaluation = {
        "protocol": "reports/vowel-cochlea-knowledge.json + "
                    "reports/vowel-cochlea-paired.json (published heldout "
                    "protocol, baseline reproduced bit-exact first)",
        "group": f"vowel-cochlea26-scaled-{args.units}",
    }
    ckpt = build(args.ant, args.units, evaluation)
    out = Path(args.out) if args.out else (
        ROOT / "state-hebbian" / "vowel-cochlea" /
        f"queen-{args.ant}" / "current.json")
    write_json_atomic(out, ckpt)
    reloaded = load_checkpoint(out)     # proves the seal + shape validation
    print(json.dumps({
        "wrote": str(out),
        "sha256": reloaded["checkpoint_sha256"],
        "units": reloaded["units"],
        "feature_dim": reloaded["feature_dim"],
        "load_checkpoint": "ok",
    }, indent=1))


if __name__ == "__main__":
    main()
