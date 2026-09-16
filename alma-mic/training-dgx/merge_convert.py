#!/usr/bin/env python3
"""Merge the personal LoRA into the base and convert to CTranslate2 — eran4 only.

base ivrit-ai/whisper-large-v3-turbo + lora_r16_run2 -> merged HF dir -> ct2
float16 (same spec as the deployed ivrit ct2 model). Then a sanity transcription
of one heldout clip with faster-whisper: prints WER vs the corpus ref and
char count — never the text itself.
"""
from __future__ import annotations
import argparse, json, os, re, subprocess, sys
import torch

_norm_re = re.compile(r"[^\w\s]", re.UNICODE)


def norm(s):
    return re.sub(r"\s+", " ", _norm_re.sub("", s.lower())).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="ivrit-ai/whisper-large-v3-turbo")
    ap.add_argument("--lora", required=True)
    ap.add_argument("--merged", required=True)
    ap.add_argument("--ct2", required=True)
    ap.add_argument("--data", required=True, help="voice_corpus dir for the sanity clip")
    a = ap.parse_args()

    from transformers import WhisperForConditionalGeneration, WhisperProcessor
    from peft import PeftModel

    print(f"[merge] loading base {a.base}", flush=True)
    model = WhisperForConditionalGeneration.from_pretrained(a.base)
    model = PeftModel.from_pretrained(model, a.lora)
    model = model.merge_and_unload()
    os.makedirs(a.merged, exist_ok=True)
    model.save_pretrained(a.merged, safe_serialization=True)
    proc = WhisperProcessor.from_pretrained(a.base)
    proc.save_pretrained(a.merged)
    print(f"[merge] merged model saved -> {a.merged}", flush=True)

    print("[ct2] converting (float16, matching deployed spec)", flush=True)
    subprocess.run([os.path.join(os.path.dirname(sys.executable), "ct2-transformers-converter"),
                    "--model", a.merged, "--output_dir", a.ct2,
                    "--quantization", "float16", "--force"], check=True)
    size = sum(os.path.getsize(os.path.join(dp, f))
               for dp, _, fs in os.walk(a.ct2) for f in fs)
    print(f"[ct2] converted -> {a.ct2} ({size/1e9:.2f} GB)", flush=True)

    # sanity: transcribe one real heldout clip (idx%20==0 rule -> first sorted wav)
    from train_lora_iddo import load_manifest
    _, held = load_manifest(a.data)
    clip = next(r for r in held if r["lang"] == "he")
    import jiwer
    from faster_whisper import WhisperModel
    m = WhisperModel(a.ct2, device="cpu", compute_type="int8")  # same as PC CPU path
    segs, info = m.transcribe(clip["wav"], language="he", beam_size=1, temperature=0)
    hyp = " ".join(s.text for s in segs).strip()
    ref = clip["text"]
    w = jiwer.wer(norm(ref), norm(hyp)) if norm(ref) else float("nan")
    print(f"[sanity] clip={os.path.basename(clip['wav'])} lang=he "
          f"hyp_chars={len(hyp)} ref_chars={len(ref)} WER_vs_pseudo_ref={w:.4f}", flush=True)
    if not hyp:
        print("[sanity] FAILED: empty transcription", flush=True)
        sys.exit(1)
    print("[sanity] OK — model transcribes", flush=True)
    print("[merge_convert] DONE", flush=True)


if __name__ == "__main__":
    main()
