"""alma-mic / training / evaluate.py — the exam. Champion and challenger sit the same one.

Measures WER (word error rate) and CER (character error rate) on the FROZEN eval
splits. Runs the CTranslate2 model — the same engine the app dictates with — so the
number we gate on is the number Iddo actually experiences, not a lab proxy that
disappears at conversion time.

  python training/evaluate.py                              # current champion
  python training/evaluate.py --model <ct2_dir> --tag challenger
  python training/evaluate.py --split eval_retain.jsonl

Writes training/evals/<tag>.json so promote.py can compare two runs it did not run.

ON HEBREW SCORING
  Naive WER on Hebrew punishes things nobody cares about: the RTL control marks the
  recogniser prepends, final-letter forms, niqqud, and the maqaf. We normalise those
  away before scoring. We do NOT normalise away real words - normalisation that
  hides errors is just cheating with extra steps.

NO TORCH ON THIS PC. CTranslate2 is not torch; this is allowed to run locally.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
CORPUS = os.path.join(APP, "voice_corpus")
DATASET = os.path.join(HERE, "dataset")
EVALS = os.path.join(HERE, "evals")

RTL_MARKS = dict.fromkeys(map(ord, "‎‏‪‫‬‭‮⁦⁧⁨⁩"))
FINALS = {"ך": "כ", "ם": "מ", "ן": "נ", "ף": "פ", "ץ": "צ"}
PUNCT = re.compile(r"[^\w\s֐-׿]", re.UNICODE)


def normalise(t: str) -> str:
    """Fold away what nobody would call a transcription error."""
    t = (t or "").translate(RTL_MARKS)
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))   # niqqud / accents
    t = PUNCT.sub(" ", t)
    t = "".join(FINALS.get(c, c) for c in t)                    # ך -> כ etc
    return re.sub(r"\s+", " ", t).strip().lower()


def edits(a: list, b: list) -> int:
    """Levenshtein distance, O(min(len)) memory. The whole of WER is this plus a split."""
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def score(refs: list[str], hyps: list[str]) -> dict:
    """Totals PLUS per-utterance (errors, words).

    The per-utterance list is not decoration: promote.py bootstrap-resamples it to
    decide whether a WER improvement is real or noise. Without it the gate refuses
    to open at all - by design, because a gate that compares two point estimates
    lets luck through, and luck deployed repeatedly is a slow slide downwards.
    """
    we = wn = ce = cn = 0
    per = []
    for r, h in zip(refs, hyps):
        rw, hw = normalise(r).split(), normalise(h).split()
        e = edits(rw, hw)
        per.append([e, len(rw)])
        we += e; wn += len(rw)
        rc, hc = list(normalise(r)), list(normalise(h))
        ce += edits(rc, hc); cn += len(rc)
    return {"wer": we / max(wn, 1), "cer": ce / max(cn, 1),
            "word_errors": we, "words": wn, "utterances": len(refs),
            "per_utt": per}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=None,
                    help="CT2 model dir; default = whatever the app is configured to use")
    ap.add_argument("--split", default="eval_voice.jsonl")
    ap.add_argument("--tag", default=None, help="name for the written report")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--beam", type=int, default=5,
                    help="beam for EVAL. Fixed across champion and challenger or the "
                         "comparison is meaningless.")
    a = ap.parse_args()

    # Reuse the app's own CUDA-DLL loader instead of writing a second one. The
    # cuBLAS/cuDNN wheels are not on PATH by default on Windows; stt.py already
    # solved this and its solution is the one that is proven to work here.
    sys.path.insert(0, APP)
    try:
        from stt import _enable_cuda_dlls
        _enable_cuda_dlls()
    except Exception as e:
        print("note: could not preload CUDA dlls (%r) - may fall back to CPU" % (e,))

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("faster-whisper not installed here. Run this where the app runs.")
        return 2

    path = os.path.join(DATASET, a.split)
    if not os.path.exists(path):
        print("no split at %s — run prepare_dataset.py first" % path)
        return 1
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    if a.limit:
        rows = rows[:a.limit]

    model_id = a.model
    if not model_id:
        sys.path.insert(0, APP)
        from config import Config
        c = Config.load() if hasattr(Config, "load") else Config()
        model_id = getattr(c, "lora_dir", "") or getattr(c, "model", "") \
            or "ivrit-ai/whisper-large-v3-turbo-ct2"
    tag = a.tag or os.path.basename(str(model_id).rstrip("/\\")) or "champion"

    print("ALMA-MIC  EVAL")
    print("=" * 72)
    print("model  : %s" % model_id)
    print("split  : %s  (%d utterances)" % (a.split, len(rows)))
    print("beam   : %d   (identical for every model, always)" % a.beam)
    print("-" * 72)

    m = WhisperModel(model_id, device="cuda", compute_type="float16")
    refs, hyps = [], []
    t0 = time.time()
    for i, r in enumerate(rows, 1):
        wav = os.path.join(CORPUS, r["wav"])
        segs, _info = m.transcribe(wav, beam_size=a.beam, temperature=0.0,
                                   language=r.get("lang") or None,
                                   condition_on_previous_text=False)
        hyps.append(" ".join(s.text for s in segs))
        refs.append(r["text"])
        if i % 100 == 0:
            print("   %4d/%d  (%.1f s)" % (i, len(rows), time.time() - t0))

    s = score(refs, hyps)
    # Count how often the model LOOPS. Lower WER with more looping is a worse model
    # to actually dictate with, so the gate tracks this separately from WER.
    sys.path.insert(0, HERE)
    from analyze_corpus import degenerate
    s["degenerate"] = sum(1 for h in hyps if degenerate(h))
    s.update({"model": str(model_id), "split": a.split, "beam": a.beam,
              "tag": tag, "seconds": round(time.time() - t0, 1),
              "when": time.strftime("%Y-%m-%dT%H:%M:%S")})
    print("-" * 72)
    print("WER %.4f    CER %.4f    (%d word errors over %d words, %d utts)"
          % (s["wer"], s["cer"], s["word_errors"], s["words"], s["utterances"]))
    print("repetition collapse in output: %d of %d utterances"
          % (s["degenerate"], s["utterances"]))

    os.makedirs(EVALS, exist_ok=True)
    out = os.path.join(EVALS, "%s__%s.json" % (tag, a.split.replace(".jsonl", "")))
    with open(out, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)
    print("wrote %s" % os.path.relpath(out, APP))

    print()
    print("READ THIS NUMBER HONESTLY: the reference text was written by the model")
    print("itself, so this is agreement-with-itself, not truth. It is a valid")
    print("REGRESSION guard - it will catch a model that got worse - but it cannot")
    print("prove a model got better. For that the references must come from a")
    print("stronger teacher or from Iddo. See training/README.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
