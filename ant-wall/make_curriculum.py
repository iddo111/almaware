#!/usr/bin/env python3
"""Build the syllable curriculum + word test set as proper corpus material.

Why variants at all: `make_syllables.py` emits ONE rendering per syllable. A
codebook trained on one rendering of "ba" learns that waveform, not the
syllable -- there is no within-class variation for it to quotient out. This
script produces many renderings per syllable, from two independent sources of
variation:

  1. VITS prosody. facebook/mms-tts-heb exposes noise_scale (flow sampling
     temperature), noise_scale_duration (stochastic duration predictor) and
     speaking_rate. Re-seeding torch alone already changes the rendering
     *including its length*, because the duration predictor is stochastic.
     These are genuinely different utterances, not filtered copies.
  2. Signal augmentation (augment.py): pitch-preserving WSOLA tempo, gain,
     additive room tone at 20-30 dB SNR, onset/offset padding.

TRAIN and HELD-OUT never share a base rendering and never share an
augmentation seed -- the seed ranges are disjoint by construction and the
manifest records base_pcm_sha256 so the disjointness is checkable after the
fact rather than merely asserted.

Words are generated with the same voice and the same acoustic treatment, and
kept strictly out of training. Matched treatment is the point: if the words
were clean and the syllables noisy, a word test would measure the recording
condition rather than the phonetics.

    python make_curriculum.py
    python make_curriculum.py --out D:/CLAUDE/voice-ant-farm/corpus-syllables
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import wave

import numpy as np

from augment import SR, apply_augmentation, draw_plan, rms

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUT = r"D:\CLAUDE\voice-ant-farm\corpus-syllables"
MODEL = "facebook/mms-tts-heb"

# Base peak level. Matches make_syllables.write_wav16 so a curriculum file and
# a wall syllable sit at the same reference level before augmentation.
BASE_PEAK = 0.92

# Kept byte-identical to make_syllables.ALEPHBET so the two stay in step.
# NOTE: the mms-tts-heb tokenizer has a 33-symbol vocabulary containing no
# niqqud -- it strips every vowel point, so "בָּה" reaches the model as "בה".
# The vocalisation below is documentation of intent, not model input, and the
# realised vowel is whatever the model inferred from the bare consonants.
# All 22 still map to distinct token sequences (verified, no collisions).
ALEPHBET = [
    ("א", "ah",  "אָה"),
    ("ב", "ba",  "בָּה"),
    ("ג", "ga",  "גָה"),
    ("ד", "da",  "דָה"),
    ("ה", "ha",  "הָה"),
    ("ו", "va",  "וָה"),
    ("ז", "za",  "זָה"),
    ("ח", "kha", "חָה"),
    ("ט", "ta",  "טָה"),
    ("י", "ya",  "יָה"),
    ("כ", "ka",  "כָּה"),
    ("ל", "la",  "לָה"),
    ("מ", "ma",  "מָה"),
    ("נ", "na",  "נָה"),
    ("ס", "sa",  "סָה"),
    ("ע", "aa",  "עָה"),
    ("פ", "pa",  "פָּה"),
    ("צ", "tsa", "צָה"),
    ("ק", "qa",  "קָה"),
    ("ר", "ra",  "רָה"),
    ("ש", "sha", "שָׁה"),
    ("ת", "tha", "תָה"),
]

# word id, Hebrew, vocalised, gloss. Every word is built from consonants the
# 22-syllable inventory already covers.
WORDS = [
    ("shalom", "שלום", "שָׁלוֹם", "peace/hello"),
    ("aba",    "אבא",  "אַבָּא",   "father"),
    ("ima",    "אמא",  "אִמָּא",   "mother"),
    ("mayim",  "מים",  "מַיִם",   "water"),
    ("lechem", "לחם",  "לֶחֶם",   "bread"),
    ("bayit",  "בית",  "בַּיִת",   "house"),
    ("yeled",  "ילד",  "יֶלֶד",   "boy/child"),
    ("gadol",  "גדול", "גָּדוֹל",  "big"),
    ("tov",    "טוב",  "טוֹב",    "good"),
    ("yom",    "יום",  "יוֹם",    "day"),
    ("rosh",   "ראש",  "רֹאשׁ",   "head"),
    ("yad",    "יד",   "יָד",     "hand"),
]

# Disjoint seed ranges. Nothing else in this file is allowed to overlap them,
# and verify.py re-checks the disjointness from the written manifest.
SEED_RANGES = {
    "train_base":     (200_000, 299_999),
    "heldout_base":   (400_000, 499_999),
    "words_base":     (600_000, 699_999),
    "train_aug":      (300_000, 399_999),
    "heldout_aug":    (500_000, 599_999),
    "words_aug":      (700_000, 799_999),
}

# VITS prosody grids. speaking_rate is the model's own rate control (HF VITS
# uses length_scale = 1/speaking_rate on the predicted durations), so it
# retimes the utterance without touching pitch at all.
TRAIN_PROSODY = [
    {"speaking_rate": 1.00, "noise_scale": 0.667, "noise_scale_duration": 0.80},
    {"speaking_rate": 0.90, "noise_scale": 0.55,  "noise_scale_duration": 0.90},
    {"speaking_rate": 1.10, "noise_scale": 0.78,  "noise_scale_duration": 0.70},
    {"speaking_rate": 0.95, "noise_scale": 0.70,  "noise_scale_duration": 0.85},
    {"speaking_rate": 1.05, "noise_scale": 0.60,  "noise_scale_duration": 0.75},
    {"speaking_rate": 1.00, "noise_scale": 0.72,  "noise_scale_duration": 0.88},
]
HELDOUT_PROSODY = [
    {"speaking_rate": 0.93, "noise_scale": 0.62,  "noise_scale_duration": 0.82},
    {"speaking_rate": 1.07, "noise_scale": 0.74,  "noise_scale_duration": 0.78},
]
WORD_PROSODY = [
    {"speaking_rate": 1.00, "noise_scale": 0.667, "noise_scale_duration": 0.80},
    {"speaking_rate": 0.92, "noise_scale": 0.58,  "noise_scale_duration": 0.86},
    {"speaking_rate": 1.08, "noise_scale": 0.75,  "noise_scale_duration": 0.74},
    {"speaking_rate": 1.00, "noise_scale": 0.65,  "noise_scale_duration": 0.80},
]

AUGS_PER_BASE = {"train": 3, "heldout": 3, "words": 2}


def write_wav16(path: str, x: np.ndarray, sr: int = SR) -> tuple[bytes, int]:
    """Write PCM16 mono WITHOUT normalising, and hand back the exact bytes.

    make_syllables.write_wav16 peak-normalises every file. Doing that here
    would silently undo the gain augmentation -- every "quiet" variant would
    come back out at 0.92 -- so normalisation happens once, on the base
    rendering, and never again.
    """
    pcm = np.clip(np.round(x * 32767.0), -32768, 32767).astype(np.int16)
    raw = pcm.tobytes()
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(raw)
    return raw, pcm.size


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def stats(x: np.ndarray) -> dict:
    peak = float(np.max(np.abs(x))) if x.size else 0.0
    r = rms(x)
    return {
        "rms": round(r, 6),
        "rms_dbfs": round(20.0 * np.log10(r + 1e-12), 2),
        "peak": round(peak, 6),
        "peak_dbfs": round(20.0 * np.log10(peak + 1e-12), 2),
    }


def render(model, tok, text: str, seed: int, prosody: dict) -> np.ndarray:
    """One VITS rendering. Peak-normalised to BASE_PEAK, nothing else applied."""
    import torch

    model.speaking_rate = prosody["speaking_rate"]
    model.noise_scale = prosody["noise_scale"]
    model.noise_scale_duration = prosody["noise_scale_duration"]
    torch.manual_seed(seed)
    with torch.no_grad():
        wav = model(**tok(text, return_tensors="pt")).waveform[0].cpu().numpy()
    wav = wav.astype(np.float64)
    m = float(np.max(np.abs(wav)))
    if m > 0:
        wav = wav / m * BASE_PEAK
    return wav


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=DEFAULT_OUT)
    args = ap.parse_args()

    out = os.path.abspath(args.out)
    for sub in ("train", "heldout", "words"):
        os.makedirs(os.path.join(out, sub), exist_ok=True)

    import torch
    from transformers import VitsModel, AutoTokenizer

    print(f"loading {MODEL} (cached, offline)")
    tok = AutoTokenizer.from_pretrained(MODEL)
    model = VitsModel.from_pretrained(MODEL)
    model.eval()
    assert model.config.sampling_rate == SR, (
        f"model is {model.config.sampling_rate} Hz, corpus is {SR} Hz")
    print(f"model sampling_rate {model.config.sampling_rate} Hz (no resampling needed)")

    entries: list[dict] = []
    base_index: list[dict] = []

    def build(split: str, item_id: str, text: str, vocalised: str,
              prosody_grid: list[dict], base_seed_origin: int,
              aug_seed_origin: int, item_idx: int, extra: dict) -> None:
        n_aug = AUGS_PER_BASE[split]
        for k, prosody in enumerate(prosody_grid):
            base_seed = base_seed_origin + item_idx * 100 + k
            lo, hi = SEED_RANGES[f"{split}_base"]
            assert lo <= base_seed <= hi, f"base seed {base_seed} escaped {split} range"

            base = render(model, tok, text, base_seed, prosody)
            base_pcm = np.clip(np.round(base * 32767.0), -32768, 32767).astype(np.int16)
            base_sha = hashlib.sha256(base_pcm.tobytes()).hexdigest()
            base_rid = f"{item_id}/{split}/b{k:02d}"
            base_index.append({
                "base_rendering_id": base_rid,
                "split": split,
                "item_id": item_id,
                "torch_seed": base_seed,
                "vits": dict(prosody),
                "base_sample_count": int(base.size),
                "base_duration_s": round(base.size / SR, 4),
                "base_pcm_sha256": base_sha,
            })

            for j in range(n_aug):
                aug_seed = aug_seed_origin + item_idx * 1000 + k * 10 + j
                alo, ahi = SEED_RANGES[f"{split}_aug"]
                assert alo <= aug_seed <= ahi, f"aug seed {aug_seed} escaped range"
                # j==0 keeps the model's own timing so every base rendering is
                # represented untimestretched somewhere in the split.
                plan = draw_plan(aug_seed, allow_tempo=(j != 0))
                y = apply_augmentation(base, plan)

                name = f"{item_id}_{split[0]}{k:02d}_{j}.wav"
                path = os.path.join(out, split, name)
                _raw, n = write_wav16(path, y)
                st = stats(y)
                assert st["peak"] < 0.999, f"{name} clipped at {st['peak']}"
                entry = {
                    "path": f"{split}/{name}",
                    "split": split,
                    "item_id": item_id,
                    "item_kind": "word" if split == "words" else "syllable",
                    "base_rendering_id": base_rid,
                    "base_torch_seed": base_seed,
                    "base_pcm_sha256": base_sha,
                    "vits": dict(prosody),
                    "augmentation": {
                        "tempo_wsola": round(plan["tempo"], 5),
                        "gain_db": round(plan["gain_db"], 3),
                        "snr_db": round(plan["snr_db"], 3),
                        "pad_lead_ms": round(plan["pad_lead_ms"], 2),
                        "pad_tail_ms": round(plan["pad_tail_ms"], 2),
                        "noise_colour": plan["noise_colour"],
                        "noise_seed": plan["noise_seed"],
                    },
                    "aug_seed": aug_seed,
                    "sample_rate": SR,
                    "sample_count": int(n),
                    "duration_s": round(n / SR, 4),
                    "channels": 1,
                    "sample_width_bytes": 2,
                    **st,
                }
                entry.update(extra)
                entry["file_sha256"] = sha256_file(path)
                entries.append(entry)

    for i, (glyph, sid, vocalised) in enumerate(ALEPHBET):
        build("train", sid, vocalised, vocalised, TRAIN_PROSODY,
              SEED_RANGES["train_base"][0], SEED_RANGES["train_aug"][0], i,
              {"glyph": glyph, "vocalised": vocalised})
        build("heldout", sid, vocalised, vocalised, HELDOUT_PROSODY,
              SEED_RANGES["heldout_base"][0], SEED_RANGES["heldout_aug"][0], i,
              {"glyph": glyph, "vocalised": vocalised})
        n = sum(1 for e in entries if e["item_id"] == sid)
        print(f"  {glyph}  {sid:4s}  {n} variants")

    for i, (wid, plain, vocalised, gloss) in enumerate(WORDS):
        build("words", wid, vocalised, vocalised, WORD_PROSODY,
              SEED_RANGES["words_base"][0], SEED_RANGES["words_aug"][0], i,
              {"hebrew": plain, "vocalised": vocalised, "gloss": gloss})
        n = sum(1 for e in entries if e["item_id"] == wid)
        print(f"  {plain}  {wid:7s}  {n} renderings  ({gloss})")

    # Provenance check, done here rather than trusted: no base rendering may
    # appear in two splits, by id or by audio content.
    by_split: dict[str, set] = {}
    for b in base_index:
        by_split.setdefault(b["split"], set()).add(b["base_pcm_sha256"])
    overlaps = {}
    names = sorted(by_split)
    for a in range(len(names)):
        for b in range(a + 1, len(names)):
            shared = by_split[names[a]] & by_split[names[b]]
            if shared:
                overlaps[f"{names[a]}|{names[b]}"] = sorted(shared)
    assert not overlaps, f"base renderings shared across splits: {overlaps}"

    totals = {}
    for split in ("train", "heldout", "words"):
        sel = [e for e in entries if e["split"] == split]
        totals[split] = {
            "files": len(sel),
            "seconds": round(sum(e["duration_s"] for e in sel), 2),
            "items": len({e["item_id"] for e in sel}),
            "base_renderings": len({e["base_rendering_id"] for e in sel}),
        }

    manifest = {
        "format_version": 1,
        "architecture": "private-waveform-only-corpus",
        "learning_tokens": "waveform-features-only",
        "source": {
            "model": MODEL,
            "model_sampling_rate": SR,
            "tokenizer_vocab_size": len(tok.get_vocab()),
            "tokenizer_strips_niqqud": True,
            "tokenizer_note": (
                "mms-tts-heb has a 33-symbol vocabulary with no niqqud; the "
                "vocalised strings recorded here are stripped to bare "
                "consonants before synthesis. All 22 syllables still map to "
                "distinct token sequences."
            ),
            "generator": os.path.abspath(__file__),
            "augmenter": os.path.join(HERE, "augment.py"),
            "torch": torch.__version__,
            "numpy": np.__version__,
        },
        "labels_are_provenance_only": True,
        "label_policy": (
            "item_id/glyph/hebrew/gloss are provenance and evaluation keys. "
            "They must never be fed to an ant as a token or feature; the wall "
            "returns audio only."
        ),
        "seed_ranges": {k: list(v) for k, v in SEED_RANGES.items()},
        "split_disjointness": {
            "base_renderings_shared_across_splits": 0,
            "method": "sha256 of the un-augmented base PCM16, compared pairwise",
        },
        "augmentation_spec": {
            "tempo_wsola": [0.90, 1.10],
            "tempo_method": "WSOLA overlap-add, pitch and formants preserved",
            "gain_db": [-10.0, -0.5],
            "snr_db": [20.0, 30.0],
            "pad_lead_ms": [10.0, 80.0],
            "pad_tail_ms": [10.0, 80.0],
            "noise_colour": ["pink", "white"],
            "excluded": ["pitch shift", "reversal", "spectral warping",
                         "resample-based speed change"],
        },
        "totals": totals,
        "base_renderings": base_index,
        "entries": entries,
    }
    mpath = os.path.join(out, "manifest.json")
    with open(mpath, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)

    print(f"\nwrote {len(entries)} files to {out}")
    for split, t in totals.items():
        print(f"  {split:8s} {t['files']:4d} files  {t['seconds']:8.2f} s  "
              f"{t['items']} items  {t['base_renderings']} base renderings")
    print(f"manifest -> {mpath}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
