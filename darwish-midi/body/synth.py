"""synth.py — our own tiny instrument. 22050 Hz mono 16-bit WAV, stdlib only.

Primitive on purpose: kick = falling sine, hat = noise tick, body = shaped
noise, bass = square wave, everything ducked against the kick (sidechain feel).
"""
import math
import random
import struct

import genome
from midi_out import bass_note

SR = 22050


def render(path, tokens, bpm=140, seed=genome.SEED):
    rng = random.Random(seed)
    step_s = 60.0 / bpm / 4.0
    step_n = int(SR * step_s)
    steps = [t for t in tokens if t not in genome.STRUCTURAL]
    total = len(steps) * step_n + SR
    buf = [0.0] * total
    pos = 0
    for tok in steps:
        drums, bass = divmod(tok, genome.DRUM_BASE)
        kick = (drums >> 0) & 1
        body = (drums >> 1) & 1
        hat = (drums >> 2) & 1
        if kick:
            for i in range(int(0.12 * SR)):
                f = 150.0 * math.exp(-i / (0.03 * SR)) + 45.0
                env = math.exp(-i / (0.04 * SR))
                buf[pos + i] += 0.9 * env * math.sin(2 * math.pi * f * i / SR)
        if body:
            for i in range(int(0.05 * SR)):
                env = math.exp(-i / (0.012 * SR))
                buf[pos + i] += 0.35 * env * (rng.random() * 2 - 1)
        if hat:
            for i in range(int(0.03 * SR)):
                env = math.exp(-i / (0.006 * SR))
                buf[pos + i] += 0.22 * env * (rng.random() * 2 - 1)
        if bass > 0:
            f = 440.0 * 2 ** ((bass_note(bass) - 69) / 12.0)
            period = SR / f
            for i in range(int(step_n * 0.9)):
                duck = 0.35 + 0.65 * min(1.0, i / (0.09 * SR)) if kick else 1.0
                sq = 0.5 if (i % period) < period / 2 else -0.5
                buf[pos + i] += 0.5 * duck * sq
        pos += step_n
    peak = max(1e-9, max(abs(x) for x in buf))
    norm = 0.9 / peak
    with open(path, "wb") as f:
        data = b"".join(struct.pack("<h", int(max(-1, min(1, x * norm)) * 32767))
                        for x in buf)
        f.write(b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE")
        f.write(b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, SR, SR * 2, 2, 16))
        f.write(b"data" + struct.pack("<I", len(data)) + data)
    return len(buf) / SR
