"""alma-mic / training / prepare_dataset.py — build train/eval splits that cannot lie.

Runs on the PC (stdlib only). Turns voice_corpus/ into three frozen files:

    dataset/train.jsonl      what the model may learn from
    dataset/eval_voice.jsonl HELD OUT. Iddo's voice. The promotion gate reads this.
    dataset/eval_retain.jsonl HELD OUT. The OLDEST sessions - different room, different
                             mic, different mood. Catches a model that got good at last
                             week and forgot everything before it.

THE ONE RULE
  A file that has ever appeared in an eval split never enters training - not in this
  run, not in any future run. The split is written once, keyed by wav filename, and
  every later run reuses it (dataset/split_lock.json). If the eval set drifts, the
  "never degrades" guarantee is worthless: you would be comparing two models on two
  different exams and calling the difference progress.

DEDUPE
  75 copies of "תודה רבה, תודה רבה." do not teach 75 times more than one copy - they
  just tilt the model toward saying it. Identical transcripts are capped (--max-dup).

    python training/prepare_dataset.py
    python training/prepare_dataset.py --eval-frac 0.08 --max-dup 3
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import wave

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(os.path.dirname(HERE), "voice_corpus")
MANIFEST = os.path.join(CORPUS, "corpus.jsonl")
OUT = os.path.join(HERE, "dataset")
LOCK = os.path.join(OUT, "split_lock.json")

sys.path.insert(0, HERE)
from analyze_corpus import HALLU_RE, degenerate, script_of   # one definition of "junk"


def clean(raw: str) -> str:
    """Strip RTL control marks and collapse whitespace. Never changes words."""
    t = (raw or "").replace("‫", "").replace("‏", "").replace("‬", "")
    return re.sub(r"\s+", " ", t).strip()


def dur(path: str) -> float:
    try:
        with wave.open(path) as w:
            return w.getnframes() / float(w.getframerate() or 16000)
    except Exception:
        return 0.0


def bucket(wav_name: str) -> float:
    """Stable 0..1 hash of the filename - assigns a row to a split deterministically.

    Hash, not random: the same file lands in the same split forever, even if the
    corpus grows or the script is re-run on another machine. No seed to lose.
    """
    h = hashlib.sha256(wav_name.encode("utf-8")).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval-frac", type=float, default=0.08,
                    help="share of utterances held out for the voice eval set")
    ap.add_argument("--retain-frac", type=float, default=0.04,
                    help="share of the OLDEST utterances held out as a forgetting check")
    ap.add_argument("--max-dup", type=int, default=3,
                    help="max copies of an identical transcript kept for training")
    a = ap.parse_args()

    os.makedirs(OUT, exist_ok=True)
    rows = []
    with open(MANIFEST, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                pass

    # ---- filter to usable rows (same rules as analyze_corpus.py) ----
    usable = []
    for r in rows:
        t = clean(r.get("text"))
        wav = r.get("wav") or ""
        p = os.path.join(CORPUS, wav)
        if not t or not os.path.exists(p):
            continue
        d = dur(p)
        if d < 0.35 or (HALLU_RE.match(t) and d < 2.5) or degenerate(t):
            continue
        if len(t) < 2 or len(t) / max(d, 0.01) > 28 or script_of(t) == "none":
            continue
        usable.append({"wav": wav, "text": t, "lang": r.get("lang") or "he",
                       "ts": r.get("ts") or wav[:15], "sec": round(d, 3)})
    usable.sort(key=lambda r: r["ts"])

    # ---- frozen split, reused forever ----
    lock = {}
    if os.path.exists(LOCK):
        with open(LOCK, encoding="utf-8") as f:
            lock = json.load(f)
        print("reusing existing split_lock.json (%d files already assigned)" % len(lock))

    oldest_cut = int(len(usable) * a.retain_frac)
    for i, r in enumerate(usable):
        if r["wav"] in lock:
            continue
        if i < oldest_cut:
            lock[r["wav"]] = "retain"          # earliest sessions = forgetting check
        elif bucket(r["wav"]) < a.eval_frac:
            lock[r["wav"]] = "eval"
        else:
            lock[r["wav"]] = "train"
    with open(LOCK, "w", encoding="utf-8") as f:
        json.dump(lock, f, indent=0)

    # ---- dedupe ONLY the training side; eval keeps its natural distribution ----
    seen: dict[str, int] = {}
    out = {"train": [], "eval": [], "retain": []}
    dropped_dup = 0
    for r in usable:
        split = lock.get(r["wav"], "train")
        if split == "train":
            k = r["text"]
            seen[k] = seen.get(k, 0) + 1
            if seen[k] > a.max_dup:
                dropped_dup += 1
                continue
        out[split].append(r)

    names = {"train": "train.jsonl", "eval": "eval_voice.jsonl",
             "retain": "eval_retain.jsonl"}
    print("ALMA-MIC  DATASET")
    print("=" * 72)
    for k, fn in names.items():
        p = os.path.join(OUT, fn)
        with open(p, "w", encoding="utf-8") as f:
            for r in out[k]:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        secs = sum(r["sec"] for r in out[k])
        he = sum(1 for r in out[k] if script_of(r["text"]) == "he")
        print("  %-16s %5d utts  %6.2f h   he=%d en=%d"
              % (fn, len(out[k]), secs / 3600, he, len(out[k]) - he))
    print("-" * 72)
    print("  dropped as over-duplicated (train only) : %d" % dropped_dup)
    print("  split is LOCKED in %s" % os.path.relpath(LOCK, os.path.dirname(HERE)))
    print()
    print("  eval_voice  = does it hear IDDO better?")
    print("  eval_retain = did it forget how it used to hear him?")
    print("  A challenger must win the first WITHOUT losing the second.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
