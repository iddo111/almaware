"""Build every evaluation set, once, and freeze them to disk.

WHY THE EVAL DESIGN LOOKS LIKE THIS
-----------------------------------
The in-domain labels are machine-generated (a prior agent proved it: the mic app
saves its own Whisper output as "training data"). That creates a trap that would
silently invalidate this whole project if left unaddressed:

    the reference text WAS produced by whisper-large-v3-turbo, so the untuned
    openai turbo agrees with it by construction and scores an artificially low
    WER. Any fine-tune that genuinely improves the audio->text mapping will move
    AWAY from that reference and its WER will go UP.

So a single in-domain WER number is not just noisy here, it points the wrong way.
Four sets are built instead, and they are read together:

  iddo_tierA   PRIMARY in-domain. 335 held-out utterances whose text two
               INDEPENDENT decoders agreed on. Uncorrelated failure modes mean
               agreement is strong evidence of correctness. Closest thing to
               ground truth that exists without Iddo's time.
  iddo_eval    All 1,682 held-out. Reported for completeness and BIASED TOWARD
               THE UNTUNED OPENAI TURBO. Read as "agreement with the old
               labeller", never as accuracy.
  fleurs_he    General Hebrew, other speakers, HUMAN transcripts. Truth anchor
  fleurs_en    General English, other speakers, HUMAN transcripts.  and the
               catastrophic-forgetting alarm. Nothing about these is machine
               labelled, so a regression here is real and unarguable.
  iddo_en      His own English utterances (code-switch / technical terms guard).
"""
from __future__ import annotations

import json
import os
import random
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import PackedAudio, normalise, script_of  # noqa: E402

ROOT = os.path.expanduser("~/whisper-iddo")
OUT = os.path.join(ROOT, "evalsets")
os.makedirs(OUT, exist_ok=True)
random.seed(1234)


def dump(name, items):
    p = os.path.join(OUT, name + ".jsonl")
    with open(p, "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    secs = sum(i["dur"] for i in items)
    langs = {}
    for i in items:
        langs[i.get("lang", "?")] = langs.get(i.get("lang", "?"), 0) + 1
    print(f"{name:14s} {len(items):5d} utts  {secs/60:6.1f} min  {langs}")
    return p


def main():
    pk = PackedAudio(ROOT)

    ev = pk.split("eval")
    rt = pk.split("retain")

    def pack_row(r, src):
        return {"id": r["id"], "off": r["off"], "n": r["n"], "dur": r["dur"],
                "text": normalise(r["text"]), "lang": r["lang"], "tier": r["tier"],
                "session": r["session"], "set": src}

    # --- PRIMARY: two-decoder-agreement labels, held out ---------------------
    tierA = [pack_row(r, "eval") for r in ev if r["tier"] == "A"] + \
            [pack_row(r, "retain") for r in rt if r["tier"] == "A"]
    dump("iddo_tierA", tierA)

    # --- full held-out (biased toward untuned openai turbo) ------------------
    dump("iddo_eval", [pack_row(r, "eval") for r in ev])

    # --- fast stratified subset for the per-epoch loop -----------------------
    by = {}
    for r in ev:
        by.setdefault((r["lang"], r["tier"]), []).append(r)
    fast = []
    for k, v in by.items():
        random.shuffle(v)
        fast += v[:max(1, int(len(v) * 0.36))]
    dump("iddo_fast", [pack_row(r, "eval") for r in fast])

    # --- his English only: code-switch / technical-term guard ---------------
    dump("iddo_en", [pack_row(r, "eval") for r in ev if r["lang"] in ("en", "mixed")])

    # --- retain split (held-out sessions, tier-A heavy) ---------------------
    dump("retain", [pack_row(r, "retain") for r in rt])

    # --- FLEURS: HUMAN labels, other speakers, both languages ---------------
    import io

    import librosa
    import soundfile as sf
    from datasets import Audio, load_dataset

    for cfg, name, cap in (("he_il", "fleurs_he", 300), ("en_us", "fleurs_en", 200)):
        print(f"loading FLEURS {cfg} ...", flush=True)
        ds = load_dataset("google/fleurs", cfg, split="test", streaming=True)
        # decode=False: hand back raw bytes and let soundfile do it. The datasets
        # decoder wants torchcodec, which has no wheel for this aarch64 / torch
        # 2.13 combination, and pulling one in would risk the fleet's torch.
        ds = ds.cast_column("audio", Audio(decode=False))
        rows, wav = [], []
        off = 0
        for ex in ds:
            a = ex["audio"]
            raw = a["bytes"] if a.get("bytes") else open(a["path"], "rb").read()
            arr, sr = sf.read(io.BytesIO(raw), dtype="float32", always_2d=False)
            if arr.ndim > 1:
                arr = arr.mean(axis=1)
            arr = np.asarray(arr, dtype=np.float32)
            if sr != 16000:
                arr = librosa.resample(arr, orig_sr=sr, target_sr=16000)
            if len(arr) < 16000 or len(arr) > 30 * 16000:
                continue
            pcm = np.clip(arr * 32768.0, -32768, 32767).astype(np.int16)
            wav.append(pcm)
            rows.append({"id": len(rows), "off": off * 2, "n": len(pcm),
                         "dur": len(pcm) / 16000.0,
                         "text": normalise(ex["transcription"]),
                         "lang": "he" if cfg == "he_il" else "en",
                         "tier": "HUMAN", "session": f"fleurs-{cfg}", "set": name})
            off += len(pcm)
            if len(rows) >= cap:
                break
        blob = np.concatenate(wav)
        blob.tofile(os.path.join(OUT, name + ".bin"))
        dump(name, rows)

    print("\nevalsets written to", OUT)


if __name__ == "__main__":
    main()
