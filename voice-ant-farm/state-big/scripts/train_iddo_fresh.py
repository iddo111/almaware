# -*- coding: utf-8 -*-
"""Train colony iddo-fresh-256: every Iddo-only train file the campaign already
featurised PLUS the raw voice-input / alma-mic captures recorded since the
corpus was built (2026-08-06). Reuses the extracted frame store — only the new
~1.6 h is featurised here.

Honesty notes, in the checkpoint provenance too:
  * The fresh files are raw uningested captures. They pass the same audioqc
    gate as the corpus, but they have NOT been through build_corpus/write_corpus.
    A proper ingest should follow; this colony exists so training does not wait.
  * Fresh files join TRAIN only. The held-out and evaluation sets are byte-for-
    byte the campaign's own, so every number is comparable to RESULTS.md.
  * Hard guards below refuse: pcm duplicates of anything already in the corpus,
    and any fresh file whose calendar-date session is a held-out/evaluation
    session — same-session audio in two splits would inflate every score.
  * Freshness is decided by SESSION DATE, not by content hash. Ingestion
    re-quantised samples (float round-trip), so a raw file's pcm hash never
    matches its corpus copy — hash-dedup silently re-admits ~19 h of already-
    ingested audio as "fresh" (observed 2026-08-09, run aborted). Only sessions
    strictly after the 2026-08-06 corpus build can be proven uningested.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import sys
import time
import wave
from pathlib import Path

import numpy as np

ROOT = Path(r"D:\CLAUDE\voice-ant-farm")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "corpus-big" / "human" / "scripts"))

from acoustic_units import write_json_atomic  # noqa: E402
from audioqc import analyze, verdict  # noqa: E402
from fastfeat import RATE, features_batch, read_pcm16  # noqa: E402
from train_big import ANTS, SEEDS, build, subset  # noqa: E402

CORPUS = ROOT / "state-big" / "corpus"
STATE = ROOT / "state-big"
COLONY = "iddo-fresh-256"
FRESH_MIN_SESSION = "2026-08-07"  # corpus was built 2026-08-06 17:35
FRESH_SOURCES = (
    ("vinput", r"D:\CLAUDE\voice-input\profiles\iddo1\samples"),
    ("almamic", r"D:\CLAUDE\alma-mic\voice_corpus"),
)


def pcm_sha(path: str) -> str | None:
    """Same hash write_corpus recorded in items.json: sha256 of the raw frames
    of a 16 kHz mono PCM16 wav. None for any other format."""
    try:
        with wave.open(path, "rb") as w:
            if (w.getframerate() != RATE or w.getnchannels() != 1
                    or w.getsampwidth() != 2):
                return None
            return hashlib.sha256(w.readframes(w.getnframes())).hexdigest()
    except Exception:
        return None


def session_of(path: str) -> str:
    digits = "".join(ch for ch in os.path.basename(path) if ch.isdigit())
    if len(digits) >= 8 and digits[:4] in ("2025", "2026"):
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    return "unknown"


def collect_fresh(known_hashes: set[str], forbidden_sessions: set[str]) -> tuple[list[dict], list]:
    items, frames, rejects = [], [], {}
    for group, folder in FRESH_SOURCES:
        for path in sorted(glob.glob(os.path.join(folder, "*.wav"))):
            sha = pcm_sha(path)
            if sha is None:
                rejects["bad_format"] = rejects.get("bad_format", 0) + 1
                continue
            if sha in known_hashes:
                rejects["already_in_corpus"] = rejects.get("already_in_corpus", 0) + 1
                continue
            session = session_of(path)
            if session == "unknown" or session < FRESH_MIN_SESSION:
                rejects["not_after_corpus_build"] = \
                    rejects.get("not_after_corpus_build", 0) + 1
                continue
            if session in forbidden_sessions:
                rejects["heldout_eval_session"] = \
                    rejects.get("heldout_eval_session", 0) + 1
                continue
            x, _ = read_pcm16(path)
            m = analyze(x)
            ok, why = verdict(m)
            if not ok:
                rejects[why] = rejects.get(why, 0) + 1
                continue
            f = features_batch(x)
            if len(f) == 0:
                rejects["too_short_for_frames"] = rejects.get("too_short_for_frames", 0) + 1
                continue
            known_hashes.add(sha)          # dedup fresh-vs-fresh too
            items.append({
                "path": path, "split": "train", "corpus": "fresh-raw",
                "group": group, "speaker": "iddo1", "speaker_known": True,
                "session": session, "duration_s": round(len(x) / RATE, 3),
                "pcm_sha256": sha, "licence": "own-recording",
            })
            frames.append(f)
    return items, frames, rejects


def main() -> None:
    items_all = json.loads((CORPUS / "items.json").read_text(encoding="utf-8"))
    train_items = [i for i in items_all if i["split"] == "train"]
    held_items = [i for i in items_all if i["split"] == "heldout"]
    x = np.load(CORPUS / "train_x.npy")
    counts = np.load(CORPUS / "train_counts.npy")
    held_x = np.load(CORPUS / "heldout_x.npy")
    assert counts.sum() == len(x), "frame index out of sync with feature matrix"

    known = {i["pcm_sha256"] for i in items_all}
    forbidden = {i["session"] for i in items_all if i["split"] in ("heldout", "evaluation")}

    mask = np.array([i["corpus"] in ("human-big", "original-253s") for i in train_items])
    idx, sel_items, sel_counts = subset(train_items, counts, mask)
    base_x = np.ascontiguousarray(x[idx])
    print(f"existing iddo train pool: {len(sel_items):,} files / {len(base_x):,} frames",
          flush=True)

    fresh_items, fresh_frames, rejects = collect_fresh(known, forbidden)
    fresh_x = (np.vstack(fresh_frames).astype(np.float32)
               if fresh_frames else np.zeros((0, base_x.shape[1]), dtype=np.float32))
    fresh_counts = np.array([len(f) for f in fresh_frames], dtype=counts.dtype)
    fresh_h = sum(i["duration_s"] for i in fresh_items) / 3600
    print(f"fresh accepted: {len(fresh_items):,} files / {len(fresh_x):,} frames "
          f"/ {fresh_h:.2f} h; rejected: {json.dumps(rejects)}", flush=True)
    if not fresh_items:
        print("nothing fresh survived the gates — refusing to train a colony "
              "identical to the existing pool", flush=True)
        return

    pool_items = sel_items + fresh_items
    pool_counts = np.concatenate([sel_counts, fresh_counts])
    pool_x = np.vstack([base_x, fresh_x])
    assert pool_counts.sum() == len(pool_x), "pool frame index out of sync"

    held_hashes = sorted({i["pcm_sha256"] for i in held_items})
    overlap = {i["pcm_sha256"] for i in pool_items} & set(held_hashes)
    assert not overlap, f"train/heldout pcm overlap: {len(overlap)}"
    bad_sessions = {i["session"] for i in fresh_items} & forbidden
    assert not bad_sessions, f"fresh session in heldout/eval: {bad_sessions}"

    hrs = sum(i["duration_s"] for i in pool_items) / 3600
    provenance = {
        "colony": COLONY,
        "hours": round(hrs, 4),
        "files": len(pool_items),
        "frames": int(len(pool_x)),
        "speaker_ids": ["iddo1"],
        "speaker_id_count": 1,
        "speaker_ids_known": ["iddo1"],
        "sources": sorted({i["corpus"] for i in pool_items}),
        "groups": sorted({i["group"] for i in pool_items}),
        "licences": sorted({i["licence"] for i in pool_items}),
        "sample_rates": [RATE],
        "heldout_hours": round(sum(i["duration_s"] for i in held_items) / 3600, 4),
        "heldout_files": len(held_items),
        "heldout_audio_hashes": held_hashes,
        "synthetic_audio_included": False,
        "fresh_uningested_sources": True,
        "fresh_files": len(fresh_items),
        "fresh_hours": round(fresh_h, 4),
        "fresh_note": "raw voice-input/alma-mic captures, sessions strictly "
                      "after the 2026-08-06 corpus build; audioqc-gated, "
                      "session-guarded, not yet ingested by build_corpus",
    }

    print(f"\n=== {COLONY}: {hrs:.3f} h, {len(pool_items):,} files, "
          f"{len(pool_x):,} frames, 1 speaker ===", flush=True)
    for ant, seed in zip(ANTS, SEEDS):
        out = STATE / COLONY / ant / "current.json"
        if out.exists():
            print(f"  {ant} already trained, skipping", flush=True)
            continue
        t = time.time()
        ck = build(COLONY, ant, seed, pool_x, pool_items, pool_counts, held_x,
                   provenance)
        write_json_atomic(out, ck)
        print(f"  {ant} seed={seed} heldout {ck['heldout_error_before']:.4f} -> "
              f"{ck['heldout_error_after']:.4f}  rounds={ck['learner_info']['rounds_run']}"
              f"  {time.time()-t:.0f}s -> {out}", flush=True)

    shas = [json.loads((STATE / COLONY / a / "current.json").read_text())["checkpoint_sha256"]
            for a in ANTS if (STATE / COLONY / a / "current.json").exists()]
    assert len(shas) == len(set(shas)), "two ants share a checkpoint — forbidden"
    print(f"\ndone: {len(shas)} sealed checkpoints, all distinct", flush=True)


if __name__ == "__main__":
    main()
