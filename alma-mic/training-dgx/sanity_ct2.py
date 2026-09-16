#!/usr/bin/env python3
"""Sanity-check the converted ct2 model on 3 real heldout clips (numbers only)."""
import os, re, sys
sys.path.insert(0, os.path.expanduser("~/lora-iddo"))
os.chdir(os.path.expanduser("~/lora-iddo"))
from train_lora_iddo import load_manifest
import jiwer
from faster_whisper import WhisperModel

_norm = re.compile(r"[^\w\s]", re.UNICODE)


def norm(s):
    return re.sub(r"\s+", " ", _norm.sub("", s.lower())).strip()


_, held = load_manifest("data/voice_corpus")
m = WhisperModel("iddo-lora-run2-ct2", device="cpu", compute_type="int8")
ok = 0
for clip in [r for r in held if r["lang"] == "he"][:3]:
    segs, info = m.transcribe(clip["wav"], language="he", beam_size=1, temperature=0)
    hyp = " ".join(s.text for s in segs).strip()
    ref = clip["text"]
    w = jiwer.wer(norm(ref), norm(hyp)) if norm(ref) else float("nan")
    print(f"[sanity] {os.path.basename(clip['wav'])} hyp_chars={len(hyp)} "
          f"ref_chars={len(ref)} WER_vs_pseudo_ref={w:.4f}", flush=True)
    ok += bool(hyp)
print(f"[sanity] {'OK' if ok == 3 else 'FAILED'} ({ok}/3 non-empty)", flush=True)
sys.exit(0 if ok == 3 else 1)
