# -*- coding: utf-8 -*-
"""KESHEV AUTOTRAIN / evaluate.py -- the number, on the FROZEN set.

> BROKEN WINDOWS LAW: test the REAL output, not a proxy.

THE FROZEN SET
--------------
The reserved Cafe-Claude sessions 2026-06-25 and 2026-07-01 (15 recordings),
permanently excluded from every training pool by prefix, on both sides:
train.py refuses to load them, this file decodes only them. That is what makes
the verdict mean something.

Their reference transcripts are machine output from a STRONGER model (large-v3),
not human gold. That caveat is printed on every run rather than buried, because
a LoRA distilled toward this teacher is flattered by this metric.

TWO WAYS TO GET A NUMBER
------------------------
1. MEASURE IT HERE  (--candidate <dir>): decode the frozen set, compute WER.
2. IMPORT IT        (--import-json <f>): take a number measured elsewhere.
   claude-cli-OPUS-hebacc owns accuracy measurement tonight -- the test set,
   today's WER, the candidate models, the text post-correction pass. This
   pipeline CONSUMES its numbers rather than producing a second, differently
   shaped answer to the same question. Expected shape:
       {"version": str, "wer": float, "evalset": str, "n": int}

Either way the number is recorded against the version in evals.jsonl on eran1,
which is the ONLY evidence the button accepts.

IT NEVER DEPLOYS. It prints a verdict and records a number. The switch is
keshev_model.py, and the last word is Iddo's.
"""
from __future__ import annotations
import argparse, glob, json, os, re, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

EVAL_PREFIXES = ("20260625", "20260701")
_punct = re.compile(r"[^\w\s]", re.UNICODE)
_ws = re.compile(r"\s+")


def norm(s):
    return _ws.sub(" ", _punct.sub("", (s or "").lower())).strip()


def _wer_pure(refs, hyps):
    """Word error rate, word-level Levenshtein. No dependency.

    eran2's system python refuses new packages (PEP 668), and a box running
    live work is not the place to start overriding that with
    --break-system-packages. This is the same arithmetic jiwer does, so where
    both exist they agree."""
    if isinstance(refs, str):
        refs, hyps = [refs], [hyps]
    tot_err = tot_n = 0
    for r, h in zip(refs, hyps):
        a, b = r.split(), h.split()
        prev = list(range(len(b) + 1))
        for i, wa in enumerate(a, 1):
            cur = [i] + [0] * len(b)
            for j, wb in enumerate(b, 1):
                cur[j] = min(prev[j] + 1,            # deletion
                             cur[j - 1] + 1,          # insertion
                             prev[j - 1] + (wa != wb))  # substitution
            prev = cur
        tot_err += prev[-1]
        tot_n += len(a)
    return (tot_err / tot_n) if tot_n else float("nan")


def get_wer():
    """jiwer when it is already installed, the builtin otherwise."""
    try:
        import jiwer
        return jiwer.wer, "jiwer"
    except ImportError:
        return _wer_pure, "builtin"


def load_refs(refs_dir, audio_dir):
    files = sorted(f for f in glob.glob(os.path.join(audio_dir, "*"))
                   if os.path.basename(f).startswith(EVAL_PREFIXES)
                   and f.lower().endswith((".wav", ".mp3")))
    out = []
    for f in files:
        rp = os.path.join(refs_dir, os.path.basename(f) + ".json")
        if not os.path.exists(rp):
            continue
        with open(rp, encoding="utf-8") as fh:
            d = json.load(fh)
        ref = norm(" ".join(c["text"] for c in d.get("chunks", [])))
        if ref:
            out.append((f, ref))
    return out


def measure(candidate, audio_dir, refs_dir, base, batch):
    import numpy as np, torch
    from transformers import (pipeline, WhisperProcessor,
                              WhisperForConditionalGeneration)

    wer_fn, wer_impl = get_wer()
    pairs = load_refs(refs_dir, audio_dir)
    print("[eval] frozen set: %d recordings | WER impl: %s" % (len(pairs), wer_impl), flush=True)
    print("[eval] CAVEAT: refs are teacher machine output, not human gold.", flush=True)
    if not pairs:
        sys.exit("[eval] the frozen set is empty -- refusing to invent a number.")

    def audio(path):
        raw = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", path,
                              "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
                             capture_output=True, check=True).stdout
        return np.frombuffer(raw, dtype=np.float32).copy()

    proc = WhisperProcessor.from_pretrained(base)
    model = WhisperForConditionalGeneration.from_pretrained(base, dtype=torch.bfloat16)
    if candidate and os.path.isdir(candidate):
        if os.path.exists(os.path.join(candidate, "adapter_config.json")):
            from peft import PeftModel
            model = PeftModel.from_pretrained(model, candidate).merge_and_unload()
            print("[eval] candidate: LoRA adapter merged from %s" % candidate, flush=True)
        else:
            model = WhisperForConditionalGeneration.from_pretrained(
                candidate, dtype=torch.bfloat16)
            print("[eval] candidate: full weights from %s" % candidate, flush=True)
    else:
        print("[eval] candidate: the BASE model (this is the incumbent's number)", flush=True)

    pipe = pipeline("automatic-speech-recognition", model=model,
                    tokenizer=proc.tokenizer, feature_extractor=proc.feature_extractor,
                    dtype=torch.bfloat16, device="cuda:0")
    refs, hyps = [], []
    for f, ref in pairs:
        try:
            res = pipe(audio(f), chunk_length_s=30, batch_size=batch,
                       generate_kwargs={"task": "transcribe"})
        except Exception as exc:
            print("[eval] ASR-FAIL %s %s" % (os.path.basename(f), type(exc).__name__), flush=True)
            continue
        hyp = norm(res.get("text") or "")
        print("[eval] %s WER=%.4f" % (os.path.basename(f), wer_fn(ref, hyp)), flush=True)
        refs.append(ref)
        hyps.append(hyp)
    if not refs:
        sys.exit("[eval] nothing decoded -- no number.")
    wer = float(wer_fn(refs, hyps))
    print("[eval] AGGREGATE n=%d WER=%.4f" % (len(refs), wer), flush=True)
    return wer, len(refs)


def record(version, wer, evalset, n, by):
    here = os.path.dirname(os.path.abspath(__file__))
    r = subprocess.run([sys.executable, os.path.join(here, "keshev_model.py"),
                        "--by", by, "record", version, "--wer", "%.6f" % wer,
                        "--evalset", evalset, "--n", str(n)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    print((r.stdout or "").strip() or (r.stderr or "").strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True, help="the version this number belongs to")
    ap.add_argument("--candidate", default="", help="model dir; empty = base/incumbent")
    ap.add_argument("--audio", default="/home/eran4/lora-iddo/cafe/audio")
    ap.add_argument("--refs", default="/home/eran4/lora-iddo/cafe/transcripts")
    ap.add_argument("--base", default="ivrit-ai/whisper-large-v3-turbo")
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--evalset", default="cafe-reserved")
    ap.add_argument("--import-json", default="",
                    help="take a number measured elsewhere (e.g. by hebacc)")
    ap.add_argument("--compare-to", type=float, default=None,
                    help="the incumbent's WER, to print a verdict")
    ap.add_argument("--by", default=os.environ.get("USER") or "claude-cli-OPUS-hebtrain")
    ap.add_argument("--no-record", action="store_true")
    a = ap.parse_args()

    if a.import_json:
        with open(a.import_json, encoding="utf-8") as fh:
            d = json.load(fh)
        wer, n = float(d["wer"]), int(d.get("n", 0))
        a.evalset = d.get("evalset", a.evalset)
        print("[eval] IMPORTED: %s WER=%.4f on %s (n=%d)"
              % (d.get("version", a.version), wer, a.evalset, n))
    else:
        wer, n = measure(a.candidate, a.audio, a.refs, a.base, a.batch)

    if a.compare_to is not None:
        if wer < a.compare_to:
            print("[eval] VERDICT: BEATS the live model (%.4f < %.4f). ELIGIBLE.\n"
                  "        Eligible is not deployed -- the last word is Iddo's."
                  % (wer, a.compare_to))
        else:
            print("[eval] VERDICT: does NOT beat the live model (%.4f >= %.4f).\n"
                  "        A tie or a loss is a loss. Nothing will be swapped.\n"
                  "        (this is the gate working, not a failure)" % (wer, a.compare_to))

    if not a.no_record:
        record(a.version, wer, a.evalset, n, a.by)
    return 0


if __name__ == "__main__":
    sys.exit(main())
