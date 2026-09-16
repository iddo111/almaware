#!/usr/bin/env python3
"""Teacher relabeling for the ALMA-MIC personal LoRA — DGX (eran4) only.

Transcribes the TRAIN POOL of Iddo's voice corpus with the stronger
openai/whisper-large-v3 (full) so LoRA training becomes real distillation
instead of echoing the deployed ivrit model's own outputs.

- Uses the exact same deterministic split as train_lora_iddo.py (imported),
  so the permanent 628-clip heldout is NEVER teacher-labeled here and eval
  references stay untouched.
- PRIVACY: transcript text goes ONLY into the output jsonl, never stdout/logs.
- Resumable: already-labeled wavs in the output file are skipped.
"""
from __future__ import annotations
import argparse, json, os, time
import soundfile as sf
import torch
from train_lora_iddo import load_manifest, MIN_SEC, MAX_SEC


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--teacher", default="openai/whisper-large-v3")
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--pool", choices=["train", "heldout"], default="train",
                    help="heldout = label the permanent eval split (teacher-reference eval only, NEVER training)")
    a = ap.parse_args()
    from transformers import WhisperProcessor, WhisperForConditionalGeneration

    tr, held = load_manifest(a.data)
    train_pool = tr if a.pool == "train" else held
    done = set()
    if os.path.exists(a.out):
        with open(a.out, encoding="utf-8") as f:
            for line in f:
                try:
                    done.add(os.path.basename(json.loads(line)["wav"]))
                except Exception:
                    pass
    todo = [r for r in train_pool if os.path.basename(r["wav"]) not in done]
    print(f"[teacher] pool={len(train_pool)} already={len(done)} todo={len(todo)} "
          f"model={a.teacher} batch={a.batch}", flush=True)

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    proc = WhisperProcessor.from_pretrained(a.teacher)
    model = WhisperForConditionalGeneration.from_pretrained(
        a.teacher, dtype=torch.bfloat16).to(dev).eval()

    t0, n, bad = time.time(), 0, 0
    with open(a.out, "a", encoding="utf-8") as out, torch.no_grad():
        for lang in ("he", "en"):
            rows = [r for r in todo if r["lang"] == lang]
            for i in range(0, len(rows), a.batch):
                feats, keep = [], []
                for r in rows[i:i + a.batch]:
                    try:
                        audio, sr = sf.read(r["wav"], dtype="float32")
                    except Exception:
                        bad += 1
                        continue
                    if audio.ndim > 1:
                        audio = audio.mean(axis=1)
                    if sr != 16000 or not (MIN_SEC <= len(audio) / sr <= MAX_SEC):
                        bad += 1
                        continue
                    feats.append(audio)
                    keep.append(r)
                if not feats:
                    continue
                x = proc.feature_extractor(feats, sampling_rate=16000,
                                           return_tensors="pt").input_features.to(dev, torch.bfloat16)
                ids = model.generate(input_features=x, language=lang,
                                     task="transcribe", max_new_tokens=200)
                for r, t in zip(keep, proc.batch_decode(ids, skip_special_tokens=True)):
                    out.write(json.dumps({"wav": os.path.basename(r["wav"]),
                                          "text": t.strip(), "lang": lang},
                                         ensure_ascii=False) + "\n")
                n += len(keep)
                if (i // a.batch) % 25 == 0:
                    out.flush()
                    print(f"[teacher] lang={lang} {n}/{len(todo)} "
                          f"{n / max(1e-9, time.time() - t0):.2f} clips/s skipped={bad}", flush=True)
    print(f"[teacher] DONE wrote={n} skipped={bad} -> {a.out}", flush=True)


if __name__ == "__main__":
    main()
