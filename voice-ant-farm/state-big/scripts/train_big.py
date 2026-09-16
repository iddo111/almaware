# -*- coding: utf-8 -*-
"""Train the colonies on the big corpus and write acoustic_units-compatible
checkpoints to state-big/<colony>/<ant>/current.json.

Founding rules kept: four ants, seeds 7007/7019/7039/7057, no weights and no
codebook ever shared between ants, the Queen selects and never merges. The only
thing the ants have in common inside a colony is the audio they heard.

Colonies -- this is the experimental design, not just "train on more data":

  all-256            40.6 h, everything human, 16 speaker ids   the headline run
  iddo-13.8h-256     13.8 h, Iddo only                          matched-hours arm A
  multi-13.8h-256    13.8 h, FLEURS + Common Voice, 15 ids      matched-hours arm B
  orig-253s-256      the original 253 s at 256 units            isolates capacity
                                                                from corpus size
  random-frames-256  256 random real frames of the 40.6 h,
                     k-means never run                          isolates the learner

The last two exist because of the prior result that the k-means learner is
inert. Without orig-253s-256 a win could be the jump from 64 to 256 units, and
without random-frames-256 a win could be "any 256 real frames of enough audio".
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
import wave
from pathlib import Path

import numpy as np

ROOT = Path(r"D:\CLAUDE\voice-ant-farm")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from acoustic_units import (CHECKPOINT_FORMAT, FEATURE_SPEC, checkpoint_digest,  # noqa: E402
                            write_json_atomic)
from fastfeat import FRAME, HOP, RATE, frames_of, read_pcm16  # noqa: E402

CORPUS = ROOT / "state-big" / "corpus"
STATE = ROOT / "state-big"
ANTS = ("ant-a", "ant-b", "ant-c", "ant-d")
SEEDS = (7007, 7019, 7039, 7057)
UNITS = 256
MATCH_HOURS = None          # filled from the open-corpus train hours
CHUNK = 262_144


# --- k-means ---------------------------------------------------------------
def assign(x: np.ndarray, centers: np.ndarray, chunk: int = CHUNK) -> np.ndarray:
    """argmin over squared distance, chunked. ||x-c||^2 = ||x||^2 - 2x.c + ||c||^2;
    the ||x||^2 term is constant per row so it is dropped from the argmin."""
    cn = (centers * centers).sum(axis=1)[None, :].astype(np.float32)
    out = np.empty(len(x), dtype=np.int32)
    for s in range(0, len(x), chunk):
        xc = x[s:s + chunk]
        d = cn - 2.0 * (xc @ centers.T)
        out[s:s + chunk] = d.argmin(axis=1)
    return out


def fit_codebook_big(x: np.ndarray, k: int, seed: int, rounds: int = 30,
                     log=None) -> tuple[np.ndarray, dict]:
    """Same algorithm as acoustic_units.fit_codebook, chunked so it survives
    14.6 M frames. Init, round count and the empty-cluster rule are identical;
    the cluster means are accumulated in float64 instead of float32."""
    if len(x) < k:
        raise ValueError(f"need at least {k} frames, got {len(x)}")
    rng = np.random.default_rng(seed)
    centers = x[rng.choice(len(x), k, replace=False)].copy()
    d = x.shape[1]
    info = {"rounds_run": 0, "converged": False}
    for r in range(rounds):
        sums = np.zeros((k, d), dtype=np.float64)
        counts = np.zeros(k, dtype=np.int64)
        for s in range(0, len(x), CHUNK):
            xc = x[s:s + CHUNK]
            ids = assign(xc, centers, chunk=CHUNK)
            counts += np.bincount(ids, minlength=k)
            for j in range(d):
                sums[:, j] += np.bincount(ids, weights=xc[:, j].astype(np.float64),
                                          minlength=k)
        updated = centers.copy()
        nz = counts > 0
        updated[nz] = (sums[nz] / counts[nz, None]).astype(np.float32)
        info["rounds_run"] = r + 1
        info["empty_clusters"] = int((~nz).sum())
        if np.allclose(updated, centers, atol=1e-5):
            centers = updated
            info["converged"] = True
            break
        centers = updated
        if log:
            log(f"      round {r+1}/{rounds} empty={int((~nz).sum())}")
    return centers, info


def quantisation_error(x: np.ndarray, centers: np.ndarray) -> float:
    total, n = 0.0, 0
    for s in range(0, len(x), CHUNK):
        xc = x[s:s + CHUNK]
        ids = assign(xc, centers)
        diff = xc - centers[ids]
        total += float((diff.astype(np.float64) ** 2).sum())
        n += diff.size
    return total / max(n, 1)


# --- exemplars -------------------------------------------------------------
def nearest_frame_per_unit(x: np.ndarray, centers: np.ndarray) -> np.ndarray:
    """Global frame index of the training frame closest to each unit centre."""
    k = len(centers)
    best_d = np.full(k, np.inf, dtype=np.float64)
    best_i = np.zeros(k, dtype=np.int64)
    cn = (centers * centers).sum(axis=1)[None, :].astype(np.float32)
    for s in range(0, len(x), CHUNK):
        xc = x[s:s + CHUNK]
        d = ((xc * xc).sum(axis=1)[:, None] + cn - 2.0 * (xc @ centers.T)).astype(np.float64)
        idx = d.argmin(axis=0)
        val = d[idx, np.arange(k)]
        take = val < best_d
        best_d[take] = val[take]
        best_i[take] = idx[take] + s
    return best_i


def waveform_exemplars(global_idx: np.ndarray, items: list[dict],
                       counts: np.ndarray) -> dict:
    """Pull the raw 25 ms waveform behind each winning frame."""
    starts = np.concatenate([[0], np.cumsum(counts)])
    file_of = np.searchsorted(starts, global_idx, side="right") - 1
    pcm, hashes, frame_idx = [], [], []
    cache: dict[int, np.ndarray] = {}
    for g, fi in zip(global_idx, file_of):
        local = int(g - starts[fi])
        if fi not in cache:
            cache[fi] = read_pcm16(items[fi]["path"])[0]
        V = frames_of(cache[fi])
        raw = V[local].astype(np.float32)
        pcm.append(np.clip(np.rint(raw * 32767), -32768, 32767).astype("<i2").tolist())
        hashes.append(items[fi]["pcm_sha256"])
        frame_idx.append(local)
    return {
        "exemplar_rate": RATE,
        "exemplar_frame_samples": FRAME,
        "exemplar_hop_samples": HOP,
        "exemplars_pcm16": pcm,
        "exemplar_source_hashes": hashes,
        "exemplar_source_frame_indexes": frame_idx,
    }


# --- colony ----------------------------------------------------------------
def subset(items, counts, keep_mask):
    """Frame rows and item list for a subset of files."""
    starts = np.concatenate([[0], np.cumsum(counts)])
    rows = [np.arange(starts[i], starts[i + 1]) for i in np.flatnonzero(keep_mask)]
    idx = np.concatenate(rows) if rows else np.zeros(0, dtype=np.int64)
    sel_items = [items[i] for i in np.flatnonzero(keep_mask)]
    sel_counts = counts[keep_mask]
    return idx, sel_items, sel_counts


def hours_capped_mask(items, predicate, hours, seed=4242):
    """Deterministic random file subset of `predicate` totalling ~`hours`."""
    cand = np.flatnonzero([predicate(i) for i in items])
    rng = np.random.default_rng(seed)
    rng.shuffle(cand)
    budget, keep = hours * 3600.0, []
    for i in cand:
        if budget <= 0:
            break
        keep.append(i)
        budget -= items[i]["duration_s"]
    mask = np.zeros(len(items), dtype=bool)
    mask[keep] = True
    return mask


def build(colony: str, ant: str, seed: int, x: np.ndarray, items: list[dict],
          counts: np.ndarray, held_x: np.ndarray, provenance: dict,
          learner: str = "kmeans") -> dict:
    t0 = time.time()
    log = lambda m: print(m, flush=True)
    if learner == "kmeans":
        centers, info = fit_codebook_big(x, UNITS, seed, log=log)
    elif learner == "random-real-frames":
        rng = np.random.default_rng(seed)
        centers = x[rng.choice(len(x), UNITS, replace=False)].copy()
        info = {"rounds_run": 0, "converged": None, "empty_clusters": 0}
    else:
        raise ValueError(learner)

    baseline = np.repeat(x.mean(axis=0, keepdims=True), UNITS, axis=0)
    before = quantisation_error(held_x, baseline)
    after = quantisation_error(held_x, centers)

    ck = {
        "format_version": CHECKPOINT_FORMAT,
        "architecture": "waveform-acoustic-vector-quantizer-with-exemplars",
        "audio_hash_kind": "sha256(sample_rate_le32+decoded_pcm16le)",
        "feature_spec": FEATURE_SPEC,
        "experiment_namespace": hashlib.sha256(
            json.dumps({"feature_spec": FEATURE_SPEC, "units": UNITS},
                       sort_keys=True).encode()).hexdigest(),
        "corpus_provenance": provenance,
        "colony": colony,
        "learner": learner,
        "learner_info": info,
        "ant": ant,
        "seed": seed,
        "units": UNITS,
        "feature_dim": int(centers.shape[1]),
        "train_frame_count": int(len(x)),
        "heldout_frame_count": int(len(held_x)),
        "train_audio_hashes": sorted({i["pcm_sha256"] for i in items}),
        "heldout_audio_hashes": provenance["heldout_audio_hashes"],
        "heldout_error_before": before,
        "heldout_error_after": after,
        "improved_over_baseline": after < before,
        "improved": after < before,
        "baseline_center": x.mean(axis=0).tolist(),
        "centers": centers.tolist(),
    }
    ck.update(waveform_exemplars(nearest_frame_per_unit(x, centers), items, counts))
    ck["train_seconds"] = round(time.time() - t0, 1)
    ck["checkpoint_sha256"] = checkpoint_digest(ck)
    return ck


def main() -> None:
    items_all = json.loads((CORPUS / "items.json").read_text(encoding="utf-8"))
    train_items = [i for i in items_all if i["split"] == "train"]
    held_items = [i for i in items_all if i["split"] == "heldout"]
    x = np.load(CORPUS / "train_x.npy")
    counts = np.load(CORPUS / "train_counts.npy")
    held_x = np.load(CORPUS / "heldout_x.npy")
    assert counts.sum() == len(x), "frame index out of sync with feature matrix"

    open_hours = sum(i["duration_s"] for i in train_items if i["corpus"] == "open") / 3600
    match = round(open_hours, 3)
    print(f"train {len(train_items):,} files / {len(x):,} frames; "
          f"heldout {len(held_items):,} files / {len(held_x):,} frames; "
          f"matched-hours target = {match} h", flush=True)

    held_hashes = sorted({i["pcm_sha256"] for i in held_items})
    overlap = {i["pcm_sha256"] for i in train_items} & set(held_hashes)
    assert not overlap, f"train/heldout overlap: {len(overlap)}"

    masks = {
        "all-256": np.ones(len(train_items), dtype=bool),
        "iddo-13.8h-256": hours_capped_mask(
            train_items, lambda i: i["corpus"] in ("human-big", "original-253s"), match),
        "multi-13.8h-256": np.array([i["corpus"] == "open" for i in train_items]),
        "orig-253s-256": np.array([i["corpus"] == "original-253s" for i in train_items]),
        "random-frames-256": np.ones(len(train_items), dtype=bool),
    }
    learners = {"random-frames-256": "random-real-frames"}

    only = sys.argv[1:] or list(masks)
    for colony in only:
        mask = masks[colony]
        idx, sel_items, sel_counts = subset(train_items, counts, mask)
        cx = np.ascontiguousarray(x[idx])
        hrs = sum(i["duration_s"] for i in sel_items) / 3600
        spk = sorted({i["speaker"] for i in sel_items})
        provenance = {
            "colony": colony,
            "hours": round(hrs, 4),
            "files": len(sel_items),
            "frames": int(len(cx)),
            "speaker_ids": spk,
            "speaker_id_count": len(spk),
            "speaker_ids_known": sorted({i["speaker"] for i in sel_items if i["speaker_known"]}),
            "sources": sorted({i["corpus"] for i in sel_items}),
            "groups": sorted({i["group"] for i in sel_items}),
            "licences": sorted({i["licence"] for i in sel_items}),
            "sample_rates": [RATE],
            "heldout_hours": round(sum(i["duration_s"] for i in held_items) / 3600, 4),
            "heldout_files": len(held_items),
            "heldout_audio_hashes": held_hashes,
            "synthetic_audio_included": False,
        }
        print(f"\n=== {colony}: {hrs:.3f} h, {len(sel_items):,} files, "
              f"{len(cx):,} frames, {len(spk)} speaker ids ===", flush=True)
        # Resumable: an ant whose checkpoint already exists is left alone, so a
        # killed run can be restarted without redoing finished ants.
        for ant, seed in zip(ANTS, SEEDS):
            if (STATE / colony / ant / "current.json").exists():
                print(f"  {ant} already trained, skipping", flush=True)
                continue
            t = time.time()
            ck = build(colony, ant, seed, cx, sel_items, sel_counts, held_x,
                       provenance, learners.get(colony, "kmeans"))
            out = STATE / colony / ant / "current.json"
            write_json_atomic(out, ck)
            print(f"  {ant} seed={seed} heldout {ck['heldout_error_before']:.4f} -> "
                  f"{ck['heldout_error_after']:.4f}  rounds={ck['learner_info']['rounds_run']}"
                  f"  empty={ck['learner_info'].get('empty_clusters')}"
                  f"  {time.time()-t:.0f}s -> {out}", flush=True)


if __name__ == "__main__":
    main()
