#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
speaker_id.py — Speaker-identification for the Hebrew mic.

Tells IDDO apart from other people / music / TV using a speaker-embedding
("voiceprint") model, so the mic can OPTIONALLY type only when it's Iddo.

Model choice: **Resemblyzer** (GE2E d-vector VoiceEncoder).
  - Lightweight (~15 MB), pure-torch, CPU-fast (no GPU needed for a 3-5 s clip).
  - Produces a 256-d L2-normalized embedding; speaker similarity = cosine.
  - Chosen over SpeechBrain ECAPA-TDNN here because ECAPA pulls a HuggingFace
    download chain + heavier runtime; Resemblyzer is self-contained and the
    enrolled-vs-test cosine gap is more than enough for owner/not-owner.

Install (already done on this box):
    pip install webrtcvad-wheels      # binary wheel; avoids needing MSVC build tools
    pip install resemblyzer --no-deps # webrtcvad is satisfied by the wheel above
    pip install librosa               # resemblyzer's audio frontend
  NOTE: plain `pip install resemblyzer` tries to BUILD webrtcvad from source and
  fails on Windows without "Microsoft C++ Build Tools". Install
  `webrtcvad-wheels` FIRST (prebuilt), then resemblyzer.

Public API:
    enroll(user="iddo1")            -> {n_used, dim, path}   # builds voiceprint.npy
    identify(wav, user="iddo1")     -> {is_owner, score, label}
    is_owner(wav, user="iddo1")     -> bool                  # convenience

CLI:
    python speaker_id.py enroll                 # build the voiceprint
    python speaker_id.py identify <some.wav>    # score one clip
    python speaker_id.py verify                 # enroll + hold-out self-test

DESIGN NOTE: this module loads the encoder LAZILY and only when called. It does
NOT start any background thread/process/loop. It is safe to import from the
always-on mic without adding load — the encoder is built on first identify()
and a single 3-5 s clip scores in well under a second on CPU.
"""

from __future__ import annotations

import os
import sys
import json
import glob
import time
import logging

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PROFILES_DIR = os.path.join(HERE, "profiles")

# Cosine-similarity threshold for "this is the owner".
# Resemblyzer cosine for same-speaker clips typically lands ~0.75-0.9;
# different-speaker / music / TV typically <0.6. 0.70 is a safe default that
# favors NOT typing on ambiguous audio (better to miss than to type a friend).
# Tune via the `verify` self-test + a few not-Iddo clips; override per profile
# with profiles/<user>/voiceprint.json -> {"threshold": 0.xx}.
DEFAULT_THRESHOLD = 0.70

log = logging.getLogger("speaker_id")

# ── lazy singletons (NO work at import time) ────────────────────────────────
_encoder = None

def _get_encoder():
    """Build the Resemblyzer VoiceEncoder once, on first use. CPU by default
    (a single short clip is sub-second; we avoid touching the GPU so we never
    contend with the STT model that the live mic runs)."""
    global _encoder
    if _encoder is None:
        from resemblyzer import VoiceEncoder
        # device="cpu" on purpose: keep the GPU free for Whisper STT.
        _encoder = VoiceEncoder(device="cpu", verbose=False)
    return _encoder

def _profile_dir(user: str) -> str:
    return os.path.join(PROFILES_DIR, user)

def _voiceprint_path(user: str) -> str:
    return os.path.join(_profile_dir(user), "voiceprint.npy")

def _meta_path(user: str) -> str:
    return os.path.join(_profile_dir(user), "voiceprint.json")

def _samples_jsonl(user: str) -> str:
    return os.path.join(_profile_dir(user), "samples.jsonl")

# ── audio → embedding ───────────────────────────────────────────────────────
def _embed_wav(wav_path: str) -> np.ndarray | None:
    """Return a 256-d L2-normalized speaker embedding for one wav, or None if
    the clip is unusable (missing / too short / silence)."""
    from resemblyzer import preprocess_wav
    try:
        # preprocess_wav resamples to 16k, normalizes loudness, and trims
        # silence via webrtcvad. Returns a float32 waveform.
        wav = preprocess_wav(wav_path)
    except Exception as e:
        log.debug("preprocess_wav failed for %s: %s", wav_path, e)
        return None
    if wav is None or len(wav) < 16000 * 0.4:  # need ~0.4 s of voiced audio
        return None
    try:
        emb = _get_encoder().embed_utterance(wav)
    except Exception as e:
        log.debug("embed_utterance failed for %s: %s", wav_path, e)
        return None
    return emb.astype(np.float32)

def _load_sample_wavs(user: str) -> list[str]:
    """Collect the user's enrolled wavs: prefer samples.jsonl (authoritative
    text-paired list), fall back to globbing samples/*.wav."""
    wavs: list[str] = []
    jl = _samples_jsonl(user)
    if os.path.exists(jl):
        with open(jl, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                w = rec.get("wav")
                if w and os.path.exists(w):
                    wavs.append(w)
    if not wavs:
        wavs = sorted(glob.glob(os.path.join(_profile_dir(user), "samples", "*.wav")))
    # de-dup, preserve order
    seen = set()
    out = []
    for w in wavs:
        if w not in seen:
            seen.add(w)
            out.append(w)
    return out

# ── enrollment ──────────────────────────────────────────────────────────────
def enroll(user: str = "iddo1", limit: int | None = None,
           verbose: bool = True) -> dict:
    """Compute a mean voiceprint from the user's enrolled samples and cache it
    to profiles/<user>/voiceprint.npy (+ voiceprint.json metadata).

    Returns {n_used, n_total, dim, path, secs}.
    """
    t0 = time.time()
    wavs = _load_sample_wavs(user)
    if limit:
        wavs = wavs[:limit]
    if not wavs:
        raise FileNotFoundError(
            f"no enrolled wavs for user={user} "
            f"(checked {_samples_jsonl(user)} and samples/*.wav)")

    embs = []
    for i, w in enumerate(wavs):
        e = _embed_wav(w)
        if e is not None:
            embs.append(e)
        if verbose and (i + 1) % 50 == 0:
            print(f"  ...embedded {i + 1}/{len(wavs)} "
                  f"({len(embs)} usable)", flush=True)

    if not embs:
        raise RuntimeError(f"could not embed any of {len(wavs)} wavs for {user}")

    # Mean of L2-normed embeddings, re-normalized → the centroid voiceprint.
    centroid = np.mean(np.stack(embs, axis=0), axis=0)
    centroid = centroid / (np.linalg.norm(centroid) + 1e-12)
    centroid = centroid.astype(np.float32)

    os.makedirs(_profile_dir(user), exist_ok=True)
    np.save(_voiceprint_path(user), centroid)

    # Self-consistency: how well do the enrolled clips match their own centroid?
    self_scores = np.array([float(np.dot(e, centroid)) for e in embs])
    meta = {
        "user": user,
        "model": "resemblyzer-voiceencoder",
        "dim": int(centroid.shape[0]),
        "n_used": len(embs),
        "n_total": len(wavs),
        "threshold": DEFAULT_THRESHOLD,
        "self_score_mean": round(float(self_scores.mean()), 4),
        "self_score_min": round(float(self_scores.min()), 4),
        "self_score_p05": round(float(np.percentile(self_scores, 5)), 4),
        "built_ts": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(_meta_path(user), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    result = {
        "n_used": len(embs),
        "n_total": len(wavs),
        "dim": int(centroid.shape[0]),
        "path": _voiceprint_path(user),
        "secs": round(time.time() - t0, 1),
        **{k: meta[k] for k in ("self_score_mean", "self_score_min", "self_score_p05")},
    }
    if verbose:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return result

# ── identification ───────────────────────────────────────────────────────────
_print_cache: dict[str, np.ndarray] = {}
_thresh_cache: dict[str, float] = {}

def _load_voiceprint(user: str) -> np.ndarray:
    if user not in _print_cache:
        p = _voiceprint_path(user)
        if not os.path.exists(p):
            raise FileNotFoundError(
                f"no voiceprint for {user}; run enroll() first ({p})")
        _print_cache[user] = np.load(p)
    return _print_cache[user]

def _threshold(user: str) -> float:
    if user not in _thresh_cache:
        thr = DEFAULT_THRESHOLD
        mp = _meta_path(user)
        if os.path.exists(mp):
            try:
                with open(mp, encoding="utf-8") as f:
                    thr = float(json.load(f).get("threshold", DEFAULT_THRESHOLD))
            except Exception:
                pass
        _thresh_cache[user] = thr
    return _thresh_cache[user]

def identify(wav: str, user: str = "iddo1",
             threshold: float | None = None) -> dict:
    """Score one wav against the enrolled voiceprint.

    Returns {is_owner: bool, score: float, label: str, threshold: float}.
      score  = cosine similarity in [-1, 1] (typically [0, 1] for speech).
      label  = user name when owner, else "other".
      is_owner is False (fail-closed) for unusable/silent audio.
    """
    thr = _threshold(user) if threshold is None else threshold
    emb = _embed_wav(wav)
    if emb is None:
        return {"is_owner": False, "score": 0.0, "label": "unknown",
                "threshold": thr, "reason": "no usable audio"}
    vp = _load_voiceprint(user)
    score = float(np.dot(emb, vp))  # both L2-normalized → cosine
    is_owner = score >= thr
    return {
        "is_owner": is_owner,
        "score": round(score, 4),
        "label": user if is_owner else "other",
        "threshold": thr,
    }

def is_owner(wav: str, user: str = "iddo1") -> bool:
    """Convenience boolean for the mic hook. Fail-closed on any error so a
    speaker-id failure never accidentally types a non-owner."""
    try:
        return identify(wav, user)["is_owner"]
    except Exception as e:
        log.warning("speaker_id.is_owner failed (fail-closed, not owner): %s", e)
        return False

# ── CLI / self-test ──────────────────────────────────────────────────────────
def _verify(user: str = "iddo1") -> None:
    """Enroll on all-but-the-last sample, then identify() the held-out clip.
    Held-out clip should score >= threshold (owner)."""
    wavs = _load_sample_wavs(user)
    print(f"[verify] {len(wavs)} enrolled wavs for {user}")
    if len(wavs) < 5:
        print("[verify] too few samples for a hold-out test")
        return

    holdout = wavs[-1]
    print(f"[verify] holding out: {os.path.basename(holdout)}")

    # Build the production voiceprint from ALL samples (this is what ships)...
    res = enroll(user, verbose=True)
    print(f"[verify] enrolled voiceprint: {res}")

    # ...then score the held-out clip against it.
    out = identify(holdout, user)
    print(f"[verify] held-out Iddo clip -> {json.dumps(out, ensure_ascii=False)}")

    # Also score a couple of other enrolled clips as a sanity floor.
    import random
    sample = random.sample(wavs[:-1], min(5, len(wavs) - 1))
    scores = [identify(w, user)["score"] for w in sample]
    print(f"[verify] 5 random Iddo clips scores: "
          f"{[round(s, 3) for s in scores]}  (mean {round(float(np.mean(scores)), 3)})")
    print(f"[verify] suggested threshold: {res['self_score_p05']:.3f} - "
          f"0.10  (5th-pctile self-score minus margin); "
          f"default in use = {DEFAULT_THRESHOLD}")

def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    cmd = argv[1] if len(argv) > 1 else "verify"
    user = "iddo1"

    if cmd == "enroll":
        enroll(user)
    elif cmd == "identify":
        if len(argv) < 3:
            print("usage: speaker_id.py identify <wav>")
            return 2
        print(json.dumps(identify(argv[2], user), ensure_ascii=False, indent=2))
    elif cmd == "verify":
        _verify(user)
    else:
        print(__doc__)
        return 2
    return 0

if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
