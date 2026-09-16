#!/usr/bin/env python3
"""Long-form teacher transcription of the Cafe-Claude recordings — eran4 only.

PRIVACY: these are deeply private recordings of Iddo's own voice. Transcript
text goes ONLY into the per-file json outputs under --out. Logs carry file
names (date stamps), counts and rates — never text. Data stays on eran4/PC.

Resumable: files with an existing output json are skipped.
"""
from __future__ import annotations
import argparse, glob, json, os, subprocess, time
import numpy as np
import torch

SR = 16000


def load_audio(path):
    out = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-i", path,
         "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"],
        capture_output=True, check=True).stdout
    return np.frombuffer(out, dtype=np.float32).copy()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="openai/whisper-large-v3")
    ap.add_argument("--batch", type=int, default=8)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    files = sorted(f for f in glob.glob(os.path.join(a.audio, "*"))
                   if f.lower().endswith((".wav", ".mp3")))
    todo = [f for f in files
            if not os.path.exists(os.path.join(a.out, os.path.basename(f) + ".json"))]
    print(f"[cafe] files={len(files)} todo={len(todo)} model={a.model}", flush=True)

    from transformers import pipeline
    pipe = pipeline("automatic-speech-recognition", model=a.model,
                    dtype=torch.bfloat16, device="cuda:0")
    t0, secs = time.time(), 0.0
    for i, f in enumerate(todo, 1):
        try:
            audio = load_audio(f)
        except Exception as e:
            print(f"[cafe] {i}/{len(todo)} DECODE-FAIL {os.path.basename(f)} {type(e).__name__}", flush=True)
            continue
        dur = len(audio) / SR
        try:
            res = pipe(audio, chunk_length_s=30, batch_size=a.batch,
                       return_timestamps=True, generate_kwargs={"task": "transcribe"})
        except Exception as e:
            print(f"[cafe] {i}/{len(todo)} ASR-FAIL {os.path.basename(f)} {type(e).__name__}", flush=True)
            continue
        chunks = ([{"ts": c.get("timestamp"), "text": (c.get("text") or "").strip()}
                   for c in res.get("chunks", [])]
                  or [{"ts": None, "text": (res.get("text") or "").strip()}])
        with open(os.path.join(a.out, os.path.basename(f) + ".json"), "w", encoding="utf-8") as o:
            json.dump({"file": os.path.basename(f), "dur_s": round(dur, 1),
                       "model": a.model, "chunks": chunks}, o, ensure_ascii=False)
        secs += dur
        rt = secs / max(1e-9, time.time() - t0)
        print(f"[cafe] {i}/{len(todo)} done {os.path.basename(f)} dur={dur/60:.1f}min "
              f"total={secs/3600:.2f}h rate={rt:.1f}x-RT", flush=True)
    print(f"[cafe] DONE files={len(todo)} audio_h={secs/3600:.2f}", flush=True)


if __name__ == "__main__":
    main()
