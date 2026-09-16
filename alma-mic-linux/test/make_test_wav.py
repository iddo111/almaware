#!/usr/bin/env python3
"""Synthesize a VAD test WAV (16 kHz mono PCM16):
silence / speech-like harmonic burst / silence / second burst / silence.
Used to exercise the alma-micd VAD + segmentation path on nodes with no mic."""
import math
import random
import struct
import sys
import wave

RATE = 16000
out = sys.argv[1] if len(sys.argv) > 1 else "test_vad.wav"
random.seed(7)
samples = []


def silence(sec, amp=0.0008):
    for _ in range(int(RATE * sec)):
        samples.append(random.gauss(0, amp))


def burst(sec, f0=140.0, amp=0.22):
    n = int(RATE * sec)
    for i in range(n):
        t = i / RATE
        env = min(1.0, i / 800.0, (n - i) / 800.0)
        v = 0.0
        for h in range(1, 7):                       # harmonic stack ~ voiced speech
            v += math.sin(2 * math.pi * f0 * h * t + 0.7 * h) / h
        v *= 0.5 + 0.5 * math.sin(2 * math.pi * 3.1 * t)   # ~3 Hz syllabic AM
        v += random.gauss(0, 0.06)                  # breath noise (raises ZCR)
        samples.append(amp * env * v)


silence(1.0)
burst(2.2)
silence(1.5)
burst(1.4, f0=180)
silence(1.2)

with wave.open(out, "wb") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(RATE)
    w.writeframes(b"".join(
        struct.pack("<h", max(-32767, min(32767, int(s * 32767))))
        for s in samples))
print(f"wrote {out}: {len(samples) / RATE:.1f}s")
