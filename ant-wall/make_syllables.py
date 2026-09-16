#!/usr/bin/env python3
"""Generate the 22 Hebrew syllables the wall speaks, using the locally cached
facebook/mms-tts-heb.

Each letter of the alphabet becomes one open-vowel syllable (patach): the ant
presses a glowing shape and hears a sound. The letter identity is NEVER given
to an ant as a label or token — only the audio. See wall.py.
"""
from __future__ import annotations

import os
import sys
import wave

import numpy as np

# Windows consoles default to cp1252, which cannot encode Hebrew. Without this a
# successful generation dies on print().
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "syllables")
TARGET_SR = 16000  # match the ants' corpus exactly

# letter, syllable id, vocalised Hebrew the TTS actually reads
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


def resample(x: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    if sr_in == sr_out:
        return x
    n = int(round(x.size * sr_out / sr_in))
    return np.interp(
        np.linspace(0, x.size - 1, n), np.arange(x.size), x
    ).astype(np.float64)


def write_wav16(path: str, x: np.ndarray, sr: int = TARGET_SR) -> None:
    m = np.max(np.abs(x))
    if m > 0:
        x = x / m * 0.92
    pcm = np.clip(x * 32767, -32768, 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def main() -> int:
    os.makedirs(OUT, exist_ok=True)

    import torch
    from transformers import VitsModel, AutoTokenizer

    name = "facebook/mms-tts-heb"
    print(f"loading {name} (cached, offline)")
    tok = AutoTokenizer.from_pretrained(name)
    model = VitsModel.from_pretrained(name)
    model.eval()
    sr_in = model.config.sampling_rate
    print(f"model sample rate {sr_in} -> resampling to {TARGET_SR}")

    for letter, sid, text in ALEPHBET:
        inputs = tok(text, return_tensors="pt")
        with torch.no_grad():
            wav = model(**inputs).waveform[0].cpu().numpy().astype(np.float64)
        wav = resample(wav, sr_in, TARGET_SR)
        path = os.path.join(OUT, f"{sid}.wav")
        write_wav16(path, wav)
        print(f"  {letter}  {sid:4s}  {wav.size / TARGET_SR:.2f}s  -> {path}")

    print(f"\n{len(ALEPHBET)} syllables written to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
