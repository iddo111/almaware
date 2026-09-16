# -*- coding: utf-8 -*-
"""midi_lean.py — rung (a) of the lean tokenizer for Darwish-ALMA.

WHY THIS FILE EXISTS
--------------------
Iddo's spec, 2026-08-14: a much SMALLER model trained on the whole Darwish
corpus with a "very lean midi tokenization", running in parallel to the 271.7M
audio brain. Same corpus, radically different representation.

THE ARGUMENT FOR IT, WHICH IS NOT "SMALLER IS NICE"
---------------------------------------------------
Audio tokens spend hundreds of tokens per second describing TIMBRE. A track
becomes so long in tokens that a model with a normal context window never sees
a whole track, so it can only ever learn texture. This representation spends
about NINE tokens per second describing STRUCTURE — where the kick lands, what
the bass is doing, where the bar turns over. The same 106 hours collapses from
billions of tokens to a few million, and at that size a small model can hold an
ENTIRE SET in context and learn FORM: the build, the drop, the breakdown.

That is the whole reason to do this. Not size — reach.

THE HONEST LIMIT, STATED BEFORE ANY CODE RUNS
---------------------------------------------
There is no MIDI for these sets. They are stereo mixdowns of dense psytrance,
which is the hardest case in the world for automatic transcription: the kick
and the bass occupy the same octave by design, leads are layered and drenched
in FX, and everything is sidechained to the kick.

So this file does NOT attempt full polyphonic transcription. Iddo's own spec
lays out a ladder and says do not promise rung (c). This is rung (a):

    (a)  percussion grid + bass f0 + tempo/key       <-- THIS FILE
    (b)  + monophonic lead melody
    (c)  full polyphonic transcription               <-- not promised, not tried

Rung (a) is chosen because psytrance's skeleton IS its grid and its bassline.
A 4/4 kick on every beat and a 16th-note rolling bass is not a lossy summary of
the genre — it is close to the genre's actual score. What is lost is timbre,
FX, and the leads, and that loss is stated here rather than discovered later.

WHAT A TOKEN IS
---------------
One token per 16th note. Each token packs two things:

    drums   3 bits — kick (40-120 Hz), body/clap (200-2k), hat (6-12 kHz)
    bass    0 = silent, else 1-12 = scale degree relative to the track's key

    token = drums * 13 + bass          ->  vocabulary 0..103

Plus four structural tokens: BAR, PHRASE (every 16 bars), BOS, EOS. Vocabulary
stays at 108. The key and tempo ride in the header, not in every token, because
repeating them 30,000 times is exactly the waste this representation exists to
avoid.

Degrees are relative to the estimated key, so a set in F# and a set in A that
play the same riff produce the SAME tokens. The model learns the riff, not the
transposition.

numpy + scipy + ffmpeg. No torch here — this is a tokenizer, not a model.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from scipy.signal import butter, sosfiltfilt

SR = 22050
HOP = 256                      # 11.6 ms — fine enough to place a 16th at 200 BPM
VOCAB_STEP = 104               # 8 drum combos x 13 bass values
TOK_BAR, TOK_PHRASE, TOK_BOS, TOK_EOS = 104, 105, 106, 107
VOCAB = 108

PITCH_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


# ---------------------------------------------------------------- decoding

def decode(path, sr=SR):
    """mp3 -> mono float32 via ffmpeg. No decoder library, no surprises."""
    cmd = ["ffmpeg", "-v", "quiet", "-i", str(path),
           "-f", "f32le", "-ac", "1", "-ar", str(sr), "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype="<f4").astype(np.float64)


def _band(x, lo, hi, sr=SR, order=4):
    nyq = sr / 2.0
    lo = max(lo / nyq, 1e-4)
    hi = min(hi / nyq, 0.999)
    sos = butter(order, [lo, hi], btype="band", output="sos")
    return sosfiltfilt(sos, x)


def _env(x, hop=HOP):
    """Short-time energy envelope, one value per hop."""
    n = len(x) // hop
    if n == 0:
        return np.zeros(0)
    return np.sqrt(np.mean(x[:n * hop].reshape(n, hop) ** 2, axis=1) + 1e-12)


# ---------------------------------------------------------------- tempo

def tempo_and_grid(x, sr=SR, hop=HOP, bpm_lo=120.0, bpm_hi=160.0):
    """Find BPM from the kick band, then lay a 16th-note grid on it.

    Psytrance sits in a narrow tempo band and its kick is on every beat, which
    is why the cheapest possible estimator works here and would not work on
    music in general. The band is a stated assumption, not a universal.
    """
    kick = _band(x, 40.0, 120.0, sr)
    env = _env(kick, hop)
    if len(env) < 100:
        raise RuntimeError("clip too short for a tempo estimate")

    d = np.diff(env, prepend=env[0])
    d[d < 0] = 0.0                                   # onsets only
    d = d - d.mean()

    fps = sr / hop
    lags = np.arange(int(fps * 60.0 / bpm_hi), int(fps * 60.0 / bpm_lo) + 1)
    ac = np.array([np.dot(d[:-l], d[l:]) for l in lags])
    beat_lag = float(lags[int(np.argmax(ac))])
    bpm = 60.0 * fps / beat_lag

    # phase: where the strongest kick sits inside one beat
    fold = np.zeros(int(round(beat_lag)))
    for i, v in enumerate(d):
        fold[i % len(fold)] += max(v, 0.0)
    phase = int(np.argmax(fold))

    step = beat_lag / 4.0                            # 16th notes
    grid = np.arange(phase, len(env) - 1, step)
    return bpm, grid.astype(np.float64), env


# ---------------------------------------------------------------- key

def estimate_key(x, sr=SR):
    """Chroma over the bass band -> the pitch class the track leans on.

    Psytrance basslines are relentlessly rooted, so the most common bass pitch
    class is the key far more reliably than it would be in other music.
    """
    b = _band(x, 45.0, 260.0, sr)
    n = len(b) // 4096
    if n < 4:
        return 0
    hist = np.zeros(12)
    for i in range(n):
        seg = b[i * 4096:(i + 1) * 4096]
        f0 = _f0(seg, sr)
        if f0 > 0:
            midi = 69 + 12 * np.log2(f0 / 440.0)
            hist[int(round(midi)) % 12] += 1
    return int(np.argmax(hist)) if hist.sum() else 0


def _f0(seg, sr=SR, fmin=35.0, fmax=260.0):
    """Autocorrelation f0 on a short bass segment. 0 if unvoiced."""
    seg = seg - seg.mean()
    if np.sqrt(np.mean(seg ** 2)) < 1e-4:
        return 0.0
    ac = np.correlate(seg, seg, mode="full")[len(seg) - 1:]
    if ac[0] <= 0:
        return 0.0
    ac = ac / ac[0]
    lo, hi = int(sr / fmax), min(int(sr / fmin), len(ac) - 1)
    if hi <= lo:
        return 0.0
    lag = lo + int(np.argmax(ac[lo:hi]))
    return float(sr / lag) if ac[lag] > 0.3 else 0.0


# ---------------------------------------------------------------- tokenizing

def tokenize(path, verbose=False):
    x = decode(path)
    if len(x) < SR * 5:
        raise RuntimeError("clip under 5 s")

    bpm, grid, _ = tempo_and_grid(x)
    key = estimate_key(x)

    kick_e = _env(_band(x, 40.0, 120.0), HOP)
    body_e = _env(_band(x, 200.0, 2000.0), HOP)
    hat_e = _env(_band(x, 6000.0, 11000.0), HOP)
    bass = _band(x, 45.0, 260.0)

    def thr(e):
        return float(np.percentile(e, 65))

    tk, tb, th = thr(kick_e), thr(body_e), thr(hat_e)
    win = int(HOP * 3)

    toks = [TOK_BOS]
    for i, g in enumerate(grid):
        f = int(round(g))
        if f >= len(kick_e):
            break
        drums = ((1 if kick_e[f] > tk else 0)
                 | (2 if body_e[f] > tb else 0)
                 | (4 if hat_e[f] > th else 0))

        s0 = f * HOP
        seg = bass[s0:s0 + win]
        deg = 0
        if len(seg) == win:
            f0 = _f0(seg)
            if f0 > 0:
                midi = 69 + 12 * np.log2(f0 / 440.0)
                deg = int(round(midi) - key) % 12 + 1     # 1..12, 0 means rest

        toks.append(drums * 13 + deg)
        if i % 16 == 15:
            toks.append(TOK_BAR)
        if i % 256 == 255:
            toks.append(TOK_PHRASE)
    toks.append(TOK_EOS)

    return {
        "path": str(path),
        "bpm": round(bpm, 2),
        "key": PITCH_NAMES[key],
        "key_pc": key,
        "seconds": round(len(x) / SR, 1),
        "n_tokens": len(toks),
        "tokens_per_second": round(len(toks) / (len(x) / SR), 2),
        "vocab": VOCAB,
        "rung": "a — percussion grid + bass degree + tempo/key. "
                "No leads, no timbre, no polyphony. Stated, not discovered.",
        "tokens": toks,
    }


def main():
    ap = argparse.ArgumentParser(description="lean MIDI-ish tokenizer, rung (a)")
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--out", default=None, help="write .json per input here")
    ap.add_argument("--head", type=int, default=48, help="tokens to print")
    a = ap.parse_args()

    outdir = Path(a.out) if a.out else None
    if outdir:
        outdir.mkdir(parents=True, exist_ok=True)

    for p in a.paths:
        try:
            r = tokenize(p)
        except Exception as exc:                              # noqa: BLE001
            print(f"FAIL {Path(p).name}: {type(exc).__name__}: {exc}")
            continue
        print(f"{Path(p).name[:60]:60s} {r['bpm']:6.1f} bpm  key {r['key']:2s}  "
              f"{r['seconds']:7.1f}s  {r['n_tokens']:7d} tok  "
              f"{r['tokens_per_second']:5.2f} tok/s")
        if a.head:
            print("   ", r["tokens"][:a.head])
        if outdir:
            q = dict(r)
            (outdir / (Path(p).stem + ".json")).write_text(
                json.dumps(q, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
