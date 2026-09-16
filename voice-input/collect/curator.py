#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
curator.py — the CLEAN owner-gate curator for the 24/7 voice corpus.

The live mic logs EVERY transcription it makes to
    profiles/iddo1/samples.jsonl
24/7. That stream is dirty: it contains other people, TV/music bleed, Whisper
hallucinations, and junk. This curator NEVER touches that file or the live mic.
It only READS it, and distills a growing CLEAN corpus alongside it.

For each sample it:
  1) runs speaker identification (speaker_id.identify) on the wav,
  2) keeps ONLY owner-verified + quality entries:
        - is_owner == True
        - score    >= MIN_SCORE (default 0.70)
        - text length >= MIN_TEXT_LEN (default 4 chars, after strip)
        - NOT a known hallucination (hebrew_stt.is_hallucination)
     into:
        profiles/iddo1/iddo_clean_corpus.jsonl
  3) quarantines everything else (with a reason) into:
        profiles/iddo1/_quarantine.jsonl

It is IDEMPOTENT: every input sample is keyed by its `ts`. A ledger of
already-processed ts values (profiles/iddo1/.curator_state.json) lets reruns
skip work already done, so it is safe on a 30-min Task Scheduler tick or a
--watch loop.

HARD RULE: this script creates NEW files only. It does not write to
samples.jsonl, and does not import or modify the live mic
(voice_input.py / supervisor.py / mic.py / ui_toggle.py / config.json).

────────────────────────────────────────────────────────────────────────────
RUN  (from D:/CLAUDE/voice-input)
    python collect/curator.py                 # one pass over new samples
    python collect/curator.py --watch         # loop forever (default 1800s)
    python collect/curator.py --watch --interval 600
    python collect/curator.py --stats         # just print corpus stats, no work
    python collect/curator.py --reprocess     # ignore ledger, re-curate ALL
    python collect/curator.py --min-score 0.72 --min-text-len 6

VERIFY
    python collect/curator.py --stats
    # corpus file:     profiles/iddo1/iddo_clean_corpus.jsonl
    # quarantine file: profiles/iddo1/_quarantine.jsonl  (each line has a "reason")
────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import os
import sys
import json
import time
import argparse
import logging

# ── BE A GOOD CITIZEN: the live mic ALWAYS wins ──────────────────────────────
# The mic's Whisper STT is the priority workload. Resemblyzer/torch will, by
# default, spawn one CPU thread per core and saturate every core — which starves
# the live mic and can effectively deadlock both. We pin this background curator
# to a SINGLE CPU thread so it sips spare cycles instead of fighting the mic.
# These MUST be set BEFORE torch/numpy import (i.e. before `import speaker_id`).
for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
           "NUMEXPR_NUM_THREADS", "TORCH_NUM_THREADS"):
    os.environ.setdefault(_v, "1")
try:
    import torch  # noqa: F401  (constrain torch's intra/inter-op pools to 1)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
except Exception:
    pass

# Lowest process priority on Windows so the OS scheduler always favors the mic.
try:
    import psutil  # optional
    psutil.Process().nice(psutil.IDLE_PRIORITY_CLASS)
except Exception:
    try:
        if os.name == "nt":
            import ctypes
            # IDLE_PRIORITY_CLASS = 0x00000040
            ctypes.windll.kernel32.SetPriorityClass(
                ctypes.windll.kernel32.GetCurrentProcess(), 0x00000040)
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
VOICE_INPUT = os.path.dirname(HERE)                 # ...\voice-input
HEBREW_VOICE = os.path.join(os.path.dirname(VOICE_INPUT), "hebrew-voice")

# Make speaker_id (voice-input/) and hebrew_stt (hebrew-voice/) importable
# without touching them.
for p in (VOICE_INPUT, HEBREW_VOICE):
    if p not in sys.path:
        sys.path.insert(0, p)

USER = "iddo1"
PROFILE_DIR = os.path.join(VOICE_INPUT, "profiles", USER)

SAMPLES_JSONL = os.path.join(PROFILE_DIR, "samples.jsonl")          # READ-ONLY input
CLEAN_CORPUS = os.path.join(PROFILE_DIR, "iddo_clean_corpus.jsonl")  # grows
QUARANTINE = os.path.join(PROFILE_DIR, "_quarantine.jsonl")         # grows
STATE_PATH = os.path.join(PROFILE_DIR, ".curator_state.json")       # ledger

# Quality gates (override on CLI).
MIN_SCORE = 0.70
MIN_TEXT_LEN = 4
DEFAULT_INTERVAL = 1800  # 30 min, matches the Task Scheduler tick

log = logging.getLogger("curator")


# ── lazy imports of the existing, authoritative modules ──────────────────────
_speaker_id = None
_is_hallucination = None
_strip_halluc = None

# Owner-scoring backend (built lazily on first wav). We REUSE speaker_id's
# enrolled voiceprint + threshold, and resemblyzer's pretrained encoder, but
# compute the audio embedding via a librosa-free path (collect/_embed_nolibrosa)
# because librosa hangs on this box (see _embed_nolibrosa.py header). If that
# helper is unavailable we transparently fall back to speaker_id.identify().
_encoder = None
_voiceprint = None
_threshold = None
_embed_mod = None
_use_nolibrosa = True


def _load_helpers():
    """Import speaker_id + hebrew_stt lazily so --stats stays instant and so a
    missing optional dep (resemblyzer) only bites when we actually score."""
    global _speaker_id, _is_hallucination, _strip_halluc
    if _speaker_id is None:
        import speaker_id  # voice-input/speaker_id.py
        _speaker_id = speaker_id
    if _is_hallucination is None:
        try:
            from hebrew_stt import is_hallucination, strip_halluc
            _is_hallucination = is_hallucination
            _strip_halluc = strip_halluc
        except Exception as e:
            # Fail-safe: if hebrew_stt can't load, fall back to a tiny built-in
            # blacklist rather than crashing the whole curator. Better to keep
            # collecting clean owner audio than to halt.
            log.warning("hebrew_stt unavailable (%s); using built-in halluc fallback", e)
            _FALLBACK = {
                "תודה", "תודה רבה", "תודה רבה לך", "להתראות", "שלום", "כתוביות",
                "thank you", "thanks for watching", "you", "bye", "okay", "ok",
                ".", "..", "...", "subscribe", "אמן",
            }

            def _fb_is_halluc(t: str) -> bool:
                c = (t or "").strip().rstrip(".!?, ").strip().lower()
                return (not c) or c in _FALLBACK

            _is_hallucination = _fb_is_halluc
            _strip_halluc = (lambda t: (t or "").strip())
    return _speaker_id, _is_hallucination, _strip_halluc


def _load_scorer():
    """Build the owner scorer once: resemblyzer encoder + speaker_id's enrolled
    voiceprint + threshold + the librosa-free embedder. Falls back to
    speaker_id.identify() if the no-librosa helper can't be imported."""
    global _encoder, _voiceprint, _threshold, _embed_mod, _use_nolibrosa
    sid = _load_helpers()[0]
    if _threshold is None:
        # reuse speaker_id's own threshold/voiceprint loaders (same enrolled model)
        _voiceprint = sid._load_voiceprint(USER)        # noqa: SLF001 (intentional reuse)
        _threshold = sid._threshold(USER)               # noqa: SLF001
    if _encoder is None:
        try:
            import _embed_nolibrosa as emod              # collect/ is on sys.path
            from resemblyzer import VoiceEncoder
            _embed_mod = emod
            _encoder = VoiceEncoder(device="cpu", verbose=False)
            _use_nolibrosa = True
        except Exception as e:
            log.warning("no-librosa embedder unavailable (%s); "
                        "falling back to speaker_id.identify (librosa path)", e)
            _use_nolibrosa = False
    return _use_nolibrosa


def _score_owner(wav: str) -> dict:
    """Return {is_owner, score, threshold} for one wav. Mirrors
    speaker_id.identify()'s contract but uses the librosa-free embedder."""
    sid = _speaker_id
    if not _load_scorer() or _use_nolibrosa is False:
        # fallback: original speaker_id path (only if no-librosa import failed)
        return sid.identify(wav, USER)

    import numpy as np
    import soundfile as sf
    try:
        y, sr = sf.read(wav, dtype="float32")
    except Exception as e:
        return {"is_owner": False, "score": 0.0, "threshold": _threshold,
                "reason": f"read_fail:{e}"}
    if getattr(y, "ndim", 1) > 1:
        y = y.mean(axis=1)
    if sr != _embed_mod.SR:
        # mic wavs are 16k; on the rare off-rate clip, fall back rather than
        # pull in a resampler (keep this path librosa-free + dependency-light).
        return sid.identify(wav, USER)
    y = _embed_mod.normalize_volume(y)
    emb = _embed_mod.embed_utterance(_encoder, y)
    if emb is None:
        return {"is_owner": False, "score": 0.0, "threshold": _threshold,
                "reason": "no usable audio"}
    score = float(np.dot(emb, _voiceprint))     # both L2-normed -> cosine
    return {"is_owner": score >= _threshold, "score": round(score, 4),
            "threshold": _threshold}


# ── state ledger ─────────────────────────────────────────────────────────────
def _load_state() -> dict:
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, encoding="utf-8") as f:
                st = json.load(f)
            st.setdefault("processed_ts", [])
            st.setdefault("kept", 0)
            st.setdefault("quarantined", 0)
            return st
        except Exception as e:
            log.warning("state file unreadable (%s); starting fresh", e)
    return {"processed_ts": [], "kept": 0, "quarantined": 0, "last_run": None}


def _save_state(st: dict) -> None:
    st["last_run"] = time.strftime("%Y-%m-%d %H:%M:%S")
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_PATH)  # atomic on Windows + POSIX


def _append_jsonl(path: str, rec: dict) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _read_samples() -> list[dict]:
    """Read the live samples.jsonl (READ-ONLY). Tolerant of partial last lines
    (the mic may be mid-append while we read)."""
    out: list[dict] = []
    if not os.path.exists(SAMPLES_JSONL):
        return out
    with open(SAMPLES_JSONL, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                # likely a half-written final line; skip, we'll get it next tick
                continue
            if isinstance(rec, dict) and rec.get("ts"):
                out.append(rec)
    return out


# ── the gate ─────────────────────────────────────────────────────────────────
def _judge(rec: dict, min_score: float, min_text_len: int) -> tuple[bool, dict]:
    """Decide keep/quarantine for one sample. Returns (keep, enriched_record).

    Order is cheapest-first so we don't waste a speaker-id embed on text we'd
    reject anyway (text checks are free; the wav embed is the expensive step).
    """
    _, is_hallucination, strip_halluc = _load_helpers()

    raw_text = (rec.get("text") or "")
    wav = rec.get("wav") or ""
    ts = rec.get("ts")

    # 1) text exists + long enough (after peeling appended hallucination tails)
    text = strip_halluc(raw_text).strip()
    if len(text) < min_text_len:
        return False, {"ts": ts, "wav": wav, "text": raw_text,
                       "reason": f"text_too_short(<{min_text_len})"}

    # 2) not a known hallucination phrase / attractor / filler loop
    if is_hallucination(text) or is_hallucination(raw_text):
        return False, {"ts": ts, "wav": wav, "text": raw_text,
                       "reason": "hallucination"}

    # 3) wav must exist to be verifiable
    if not wav or not os.path.exists(wav):
        return False, {"ts": ts, "wav": wav, "text": raw_text,
                       "reason": "wav_missing"}

    # 4) owner gate — the heart of it (expensive; runs last)
    try:
        ident = _score_owner(wav)
    except Exception as e:
        # fail-closed: do NOT keep audio we couldn't verify; quarantine so a
        # later rerun (with deps fixed) can reconsider it.
        return False, {"ts": ts, "wav": wav, "text": raw_text,
                       "reason": f"identify_error:{e}"}

    score = float(ident.get("score", 0.0))
    is_own = bool(ident.get("is_owner", False))
    thr = float(ident.get("threshold", min_score))

    if not is_own:
        return False, {"ts": ts, "wav": wav, "text": raw_text,
                       "reason": "not_owner", "score": score, "threshold": thr}
    if score < min_score:
        return False, {"ts": ts, "wav": wav, "text": raw_text,
                       "reason": f"score_below_min({min_score})",
                       "score": score, "threshold": thr}

    # KEEP — owner-verified, quality, non-hallucinated.
    keep_rec = {
        "ts": ts,
        "wav": wav,
        "text": text,                         # cleaned text (halluc tails peeled)
        "raw_text": raw_text,                 # preserve original for traceability
        "confidence": rec.get("confidence"),
        "speaker_score": round(score, 4),
        "speaker_threshold": thr,
        "curated_ts": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    return True, keep_rec


# ── one pass ─────────────────────────────────────────────────────────────────
def run_once(min_score: float = MIN_SCORE, min_text_len: int = MIN_TEXT_LEN,
             reprocess: bool = False) -> dict:
    """Curate every not-yet-processed sample. Idempotent via the ts ledger."""
    os.makedirs(PROFILE_DIR, exist_ok=True)
    st = {"processed_ts": [], "kept": 0, "quarantined": 0, "last_run": None} \
        if reprocess else _load_state()
    done = set(st["processed_ts"])

    samples = _read_samples()
    new = [r for r in samples if r.get("ts") not in done]

    t0 = time.time()
    kept = quarantined = 0
    for rec in new:
        ts = rec.get("ts")
        try:
            keep, out = _judge(rec, min_score, min_text_len)
        except Exception as e:
            log.warning("judge crashed on ts=%s (%s); quarantining", ts, e)
            keep, out = False, {"ts": ts, "wav": rec.get("wav"),
                                "text": rec.get("text"), "reason": f"crash:{e}"}
        if keep:
            _append_jsonl(CLEAN_CORPUS, out)
            kept += 1
        else:
            _append_jsonl(QUARANTINE, out)
            quarantined += 1
        done.add(ts)

    st["processed_ts"] = sorted(done)
    st["kept"] = st.get("kept", 0) + kept
    st["quarantined"] = st.get("quarantined", 0) + quarantined
    _save_state(st)

    result = {
        "scanned": len(samples),
        "new_this_run": len(new),
        "kept_this_run": kept,
        "quarantined_this_run": quarantined,
        "corpus_total": st["kept"],
        "quarantine_total": st["quarantined"],
        "secs": round(time.time() - t0, 1),
        "min_score": min_score,
        "min_text_len": min_text_len,
    }
    log.info(json.dumps(result, ensure_ascii=False))
    return result


def stats() -> dict:
    """Cheap, dependency-free summary of the corpus (no embedding work)."""
    def _count(path):
        if not os.path.exists(path):
            return 0
        n = 0
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    n += 1
        return n

    st = _load_state()
    out = {
        "samples_jsonl_lines": _count(SAMPLES_JSONL),
        "clean_corpus_lines": _count(CLEAN_CORPUS),
        "quarantine_lines": _count(QUARANTINE),
        "processed_ts": len(st.get("processed_ts", [])),
        "last_run": st.get("last_run"),
        "clean_corpus_path": CLEAN_CORPUS,
        "quarantine_path": QUARANTINE,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return out


def watch(interval: int, min_score: float, min_text_len: int) -> None:
    log.info("curator --watch: every %ss; corpus=%s", interval, CLEAN_CORPUS)
    while True:
        try:
            run_once(min_score, min_text_len)
        except KeyboardInterrupt:
            log.info("curator stopped by user")
            return
        except Exception as e:
            log.exception("curator pass failed (will retry next tick): %s", e)
        time.sleep(interval)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Clean owner-gate curator for the 24/7 voice corpus")
    ap.add_argument("--watch", action="store_true", help="loop forever")
    ap.add_argument("--interval", type=int, default=DEFAULT_INTERVAL,
                    help=f"--watch loop seconds (default {DEFAULT_INTERVAL})")
    ap.add_argument("--stats", action="store_true", help="print corpus stats and exit")
    ap.add_argument("--reprocess", action="store_true",
                    help="ignore the ledger and re-curate ALL samples (rebuilds nothing; appends)")
    ap.add_argument("--min-score", type=float, default=MIN_SCORE)
    ap.add_argument("--min-text-len", type=int, default=MIN_TEXT_LEN)
    args = ap.parse_args(argv[1:])

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                        datefmt="%H:%M:%S")

    if args.stats:
        stats()
        return 0
    if args.watch:
        watch(args.interval, args.min_score, args.min_text_len)
        return 0
    run_once(args.min_score, args.min_text_len, reprocess=args.reprocess)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
