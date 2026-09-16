#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""STEP 1 - THE TEACHER.  Pseudo-label Iddo's segments with ivrit-ai/whisper-large-v3.

This is ref_decode.py (the program that produced keshev-6/state/ref.jsonl on
2026-09-03) with three additions and NO change to the model or the generate
arguments.  That is deliberate: the labels this writes and the references the
judge scores against must come from the IDENTICAL process, or the comparison is
not a comparison.

  added: sha256 of the raw PCM       -> lets the judge prove train/eval disjointness
  added: duration + RMS per clip     -> lets the judge test duration/loudness shortcuts
  added: resumable incremental write -> a 15k-clip run must survive an interruption

THE BIAS, STATED BEFORE ANY NUMBER IS PRODUCED (this is the whole point):
a student trained on this teacher's output will score better against this
teacher's output whether or not it got BETTER.  CER/WER-vs-reference is
therefore INADMISSIBLE as evidence that the fine-tune won.  It is reported
because hiding it would be worse, and it is reported with that label attached.
The admissible evidence is the name table, which never touches the teacher.
"""
from __future__ import annotations
import argparse, hashlib, json, os, sys, time, wave
from pathlib import Path
import numpy as np, torch
from transformers import AutoProcessor, AutoModelForSpeechSeq2Seq

MODEL = os.environ.get("REF_MODEL", "ivrit-ai/whisper-large-v3")


def read_wav(p: str):
    with wave.open(p) as w:
        assert w.getframerate() == 16000 and w.getnchannels() == 1 and w.getsampwidth() == 2
        raw = w.readframes(w.getnframes())
    a = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    return a, raw


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--beams", type=int, default=5)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    files = sorted(str(p) for p in Path(args.src).glob("*.wav"))
    if args.limit:
        files = files[: args.limit]

    done = set()
    outp = Path(args.out)
    if outp.exists():
        for ln in outp.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                done.add(json.loads(ln)["wav"])
        print(f"resume: {len(done)} already labelled", flush=True)
    todo = [f for f in files if os.path.basename(f) not in done]
    print(f"{len(files)} files, {len(todo)} to do", flush=True)
    if not todo:
        return

    print("loading", MODEL, flush=True)
    proc = AutoProcessor.from_pretrained(MODEL)
    model = AutoModelForSpeechSeq2Seq.from_pretrained(MODEL, dtype=torch.float16).to("cuda").eval()

    fh = outp.open("a", encoding="utf-8")
    t0 = time.monotonic()
    for i in range(0, len(todo), args.batch):
        ch = todo[i : i + args.batch]
        ws, raws = [], []
        for f in ch:
            a, r = read_wav(f)
            ws.append(a); raws.append(r)
        inp = proc(ws, sampling_rate=16000, return_tensors="pt").to("cuda")
        with torch.no_grad():
            ids = model.generate(inp.input_features.half(), language="he", task="transcribe",
                                 num_beams=args.beams, max_new_tokens=200)
        for f, r, a, t in zip(ch, raws, ws, proc.batch_decode(ids, skip_special_tokens=True)):
            fh.write(json.dumps({
                "wav": os.path.basename(f),
                "text": t.strip(),
                "sha256": hashlib.sha256(r).hexdigest(),
                "secs": round(len(a) / 16000, 3),
                "rms": round(float(np.sqrt(np.mean(a.astype(np.float64) ** 2))), 6),
            }, ensure_ascii=False) + "\n")
        fh.flush()
        n = i + len(ch)
        if (i // args.batch) % 10 == 0:
            el = time.monotonic() - t0
            rate = n / max(el, 1e-9)
            print(f"  {n}/{len(todo)}  {el:.0f}s  {rate:.1f} clip/s  "
                  f"eta {(len(todo)-n)/max(rate,1e-9)/60:.0f}m", flush=True)
    fh.close()
    print("wrote", args.out, flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
