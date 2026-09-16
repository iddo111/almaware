#!/usr/bin/env python3
"""Cafe-Claude long-form eval — eran4 only.

File-level WER of the deployed-family student (ivrit-ai/whisper-large-v3-turbo,
with and without the personal LoRA) against the large-v3 TEACHER transcripts,
restricted to the RESERVED eval sessions (2026-06-25, 2026-07-01) which are
permanently excluded from any training pool.

HONEST CAVEATS (also print them): refs are machine output (a stronger model,
but not human gold), and the LoRA was trained toward this teacher's style on
OTHER clips, which biases this metric in the LoRA's favour. Human-verified
gold refs can replace these later. Logs carry numbers and date-stamped file
names only — never transcript text.
"""
from __future__ import annotations
import argparse, glob, json, os, re, subprocess
import numpy as np
import torch

SR = 16000
EVAL_PREFIXES = ("20260625", "20260701")
_norm_re = re.compile(r"[^\w\s]", re.UNICODE)


def norm(s):
    return re.sub(r"\s+", " ", _norm_re.sub("", s.lower())).strip()


def load_audio(path):
    out = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-i", path,
         "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"],
        capture_output=True, check=True).stdout
    return np.frombuffer(out, dtype=np.float32).copy()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", required=True)
    ap.add_argument("--refs", required=True, help="cafe_teacher output dir")
    ap.add_argument("--base", default="ivrit-ai/whisper-large-v3-turbo")
    ap.add_argument("--lora", default="")
    ap.add_argument("--batch", type=int, default=8)
    a = ap.parse_args()
    import jiwer
    from transformers import pipeline, WhisperProcessor, WhisperForConditionalGeneration

    files = sorted(f for f in glob.glob(os.path.join(a.audio, "*"))
                   if os.path.basename(f).startswith(EVAL_PREFIXES)
                   and f.lower().endswith((".wav", ".mp3")))
    refs = {}
    for f in files:
        rp = os.path.join(a.refs, os.path.basename(f) + ".json")
        if os.path.exists(rp):
            with open(rp, encoding="utf-8") as fh:
                d = json.load(fh)
            refs[os.path.basename(f)] = norm(" ".join(c["text"] for c in d["chunks"]))
    files = [f for f in files if refs.get(os.path.basename(f))]
    print(f"[cafe-eval] reserved-date eval files with teacher refs: {len(files)}", flush=True)
    print("[cafe-eval] caveat: refs=teacher machine output (not human gold); "
          "LoRA was distilled toward this teacher = metric biased pro-LoRA", flush=True)
    if not files:
        print("[cafe-eval] DONE (nothing to evaluate)", flush=True)
        return

    audio_cache = {}
    for f in files:
        try:
            audio_cache[f] = load_audio(f)
        except Exception as e:
            print(f"[cafe-eval] DECODE-FAIL {os.path.basename(f)} {type(e).__name__}", flush=True)

    proc = WhisperProcessor.from_pretrained(a.base)

    def run(tag, model_obj):
        pipe = pipeline("automatic-speech-recognition", model=model_obj,
                        tokenizer=proc.tokenizer, feature_extractor=proc.feature_extractor,
                        dtype=torch.bfloat16, device="cuda:0")
        rs, hs = [], []
        for f in files:
            if f not in audio_cache:
                continue
            try:
                res = pipe(audio_cache[f], chunk_length_s=30, batch_size=a.batch,
                           generate_kwargs={"task": "transcribe"})
            except Exception as e:
                print(f"[cafe-eval] {tag} ASR-FAIL {os.path.basename(f)} {type(e).__name__}", flush=True)
                continue
            hyp = norm(res.get("text") or "")
            ref = refs[os.path.basename(f)]
            w = jiwer.wer(ref, hyp) if ref else float("nan")
            print(f"[cafe-eval] {tag} {os.path.basename(f)} WER={w:.4f}", flush=True)
            rs.append(ref); hs.append(hyp)
        if rs:
            print(f"[cafe-eval] {tag} AGGREGATE n={len(rs)} WER={jiwer.wer(rs, hs):.4f}", flush=True)

    base_model = WhisperForConditionalGeneration.from_pretrained(a.base, dtype=torch.bfloat16)
    run("BASE", base_model)
    if a.lora and os.path.isdir(a.lora):
        from peft import PeftModel
        m = WhisperForConditionalGeneration.from_pretrained(a.base, dtype=torch.bfloat16)
        m = PeftModel.from_pretrained(m, a.lora).merge_and_unload()
        run(f"LORA({os.path.basename(a.lora)})", m)
    print("[cafe-eval] DONE", flush=True)


if __name__ == "__main__":
    main()
