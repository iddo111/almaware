"""alma-mic / test_lang.py — HONEST language-ID + transcription bench.

Runs the curated testset.json (real utterances from voice_corpus, hand-bucketed
he / en / mixed by script) through the Transcriber and reports, per bucket:
  - language-ID accuracy (he-only and en-only buckets have a ground-truth language;
    mixed has no single truth, so we report the detected label + probability only)
  - a transcription sample so a human can eyeball quality

This is a SIDE process. It loads its own Transcriber and never touches the live
pipeline. Safe to run while the mic app is up (it just loads a second model copy;
mind GPU memory — pass --cpu to force CPU if needed).

Usage:
  python test_lang.py            # run full testset on the configured model
  python test_lang.py --limit 30 # quick smoke
  python test_lang.py --cpu      # force CPU (don't fight the live app for the GPU)
"""
from __future__ import annotations
import sys, io, json, os, re, time, argparse

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception:
    pass

import numpy as np
import wave

HERE = os.path.dirname(os.path.abspath(__file__))


def load_wav(path: str) -> np.ndarray:
    with wave.open(path, "rb") as w:
        n = w.getnframes()
        pcm = np.frombuffer(w.readframes(n), dtype=np.int16)
    return (pcm.astype(np.float32) / 32768.0)


def script_of(t: str) -> str:
    t = t.replace("‫", "")
    lat = bool(re.search(r"[A-Za-z]", t))
    heb = bool(re.search(r"[֐-׿]", t))
    if lat and heb:
        return "mixed"
    if lat:
        return "en"
    if heb:
        return "he"
    return "other"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--cpu", action="store_true")
    ap.add_argument("--show", type=int, default=6, help="sample transcripts per bucket")
    args = ap.parse_args()

    from config import Config
    from stt import Transcriber
    cfg = Config.load()
    if args.cpu:
        cfg.device = "cpu"
    t = Transcriber(cfg)
    t0 = time.time()
    t.load(log=lambda m: print("  " + m))
    print(f"[model] {t.desc}  ({time.time()-t0:.1f}s)\n")

    testset_path = os.path.join(HERE, "testset.json")
    if not os.path.exists(testset_path):
        sys.exit("test_lang needs testset.json + voice_corpus/ (your own recordings — "
                 "not shipped in the release). Use transcribe_file.py to check STT instead.")
    testset = json.load(open(testset_path, encoding="utf-8"))
    if args.limit:
        # keep the bucket mix when limiting
        buckets = {"he": [], "en": [], "mixed": []}
        for r in testset:
            buckets.get(r["cat"], buckets["he"]).append(r)
        per = max(1, args.limit // 3)
        testset = buckets["he"][:per] + buckets["en"][:per] + buckets["mixed"][:per]

    stats = {b: {"n": 0, "lang_ok": 0, "samples": []} for b in ("he", "en", "mixed")}
    t_run = time.time()
    for r in testset:
        wav = os.path.join(HERE, "voice_corpus", r["wav"])
        if not os.path.exists(wav):
            continue
        audio = load_wav(wav)
        text, lang, info = t.transcribe(audio, return_info=True)
        b = r["cat"]
        if b not in stats:
            continue
        s = stats[b]
        s["n"] += 1
        # ground-truth language only meaningful for he/en buckets
        if b in ("he", "en"):
            if lang == b:
                s["lang_ok"] += 1
        if len(s["samples"]) < args.show:
            s["samples"].append((r["ref"], text, lang,
                                  round(info.get("language_probability", 0.0), 2),
                                  script_of(text)))

    dt = time.time() - t_run
    print("=" * 72)
    print(f"RESULTS  ({sum(s['n'] for s in stats.values())} clips, {dt:.1f}s)")
    print("=" * 72)
    for b in ("he", "en", "mixed"):
        s = stats[b]
        if not s["n"]:
            continue
        if b in ("he", "en"):
            acc = 100.0 * s["lang_ok"] / s["n"]
            print(f"\n[{b}]  lang-ID accuracy: {s['lang_ok']}/{s['n']} = {acc:.0f}%")
        else:
            print(f"\n[{b}]  (no single ground-truth language — showing detected label)")
        for ref, hyp, lang, p, sc in s["samples"]:
            mark = "" if (b == "mixed" or lang == b) else "  <-- MISLABEL"
            print(f"    ref : {ref}")
            print(f"    hyp : {hyp}")
            print(f"    lang: {lang} (p={p}) out-script={sc}{mark}")
            print()


if __name__ == "__main__":
    main()
