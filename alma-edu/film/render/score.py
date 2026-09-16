#!/usr/bin/env python3
"""An original, quiet score for the ALMIDO film. Written here, not sampled.

Nothing copyrighted goes near this film, and the anthems already in
perceptron-movie/music are vocal psytrance — wrong room entirely. This is a slow
warm bed: a low drone, a five-note motif that keeps returning the way the alef-bet
walk does, and a lot of air.
"""
from __future__ import annotations

import argparse
import math
import wave
from pathlib import Path

import numpy as np

SR = 48000
KEY = 146.83  # D3


def env(n: int, attack: float, release: float) -> np.ndarray:
    a = max(1, int(attack * SR))
    r = max(1, int(release * SR))
    e = np.ones(n)
    a = min(a, n)
    e[:a] = np.linspace(0, 1, a) ** 1.6
    r = min(r, n - a) if n - a > 0 else 0
    if r:
        e[n - r:] = np.linspace(1, 0, r) ** 1.8
    return e


def voice(freq: float, dur: float, amp: float, attack=0.9, release=2.2,
          detune=0.004) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n) / SR
    sig = np.zeros(n)
    # a few partials, each slightly detuned so it breathes instead of buzzing
    for k, w in ((1, 1.0), (2, 0.32), (3, 0.14), (4, 0.06), (6, 0.03)):
        for d in (-detune, 0.0, detune):
            sig += w * np.sin(2 * math.pi * freq * k * (1 + d) * t)
    sig /= 3.0
    vib = 1 + 0.0025 * np.sin(2 * math.pi * 0.7 * t)
    return sig * vib * env(n, attack, release) * amp


def reverb(x: np.ndarray, decay=2.6, mix=0.42) -> np.ndarray:
    """FFT convolution — a direct np.convolve here is 125k taps over 4M samples
    and simply never returns."""
    n = int(decay * SR)
    rng = np.random.default_rng(7)
    ir = rng.standard_normal(n) * np.exp(-np.linspace(0, 7, n))
    ir[: int(0.02 * SR)] = 0
    ir /= np.abs(ir).sum() / 6
    size = 1 << int(np.ceil(np.log2(len(x) + len(ir) - 1)))
    wet = np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(ir, size), size)[: len(x)]
    return (1 - mix) * x + mix * wet


def build(total: float) -> np.ndarray:
    n = int(total * SR)
    out = np.zeros(n + SR * 4)

    def put(sig: np.ndarray, at: float) -> None:
        i = int(at * SR)
        if i >= len(out):
            return
        sig = sig[: len(out) - i]
        out[i:i + len(sig)] += sig

    # the drone — a fifth, held under the whole film
    put(voice(KEY / 2, total, 0.10, attack=6.0, release=8.0), 0.0)
    put(voice(KEY / 2 * 1.5, total, 0.055, attack=9.0, release=8.0), 2.0)

    # the motif: five notes, a major pentatonic walk that keeps coming back
    steps = [0, 2, 4, 7, 9]
    motif = [KEY * 2 * 2 ** (s / 12) for s in steps]
    t = 2.0
    i = 0
    while t < total - 5:
        f = motif[i % len(motif)]
        put(voice(f, 5.0, 0.055 if i % 5 else 0.075, attack=0.6, release=3.4), t)
        # a soft answer a fifth below, one beat later — the room echoing back
        if i % 5 == 4:
            put(voice(f / 1.5, 6.0, 0.045, attack=1.2, release=4.0), t + 1.6)
        t += 3.1
        i += 1

    # warm pad chords, very slow
    for at, root in ((0.0, 0), (18.0, 5), (36.0, 3), (54.0, 7), (72.0, 0)):
        if at > total:
            break
        for iv in (0, 4, 7, 11):
            put(voice(KEY * 2 ** ((root + iv) / 12), 22.0, 0.032,
                      attack=5.0, release=9.0), at)

    out = out[:n]
    # air: a whisper of filtered noise so the silence is not digital silence
    rng = np.random.default_rng(3)
    air = rng.standard_normal(n)
    k = np.ones(220) / 220
    air = np.convolve(air, k, mode="same") * 0.0055
    out = out + air

    out = reverb(out)
    out *= env(n, 3.0, 5.0)
    peak = np.abs(out).max()
    return (out / peak * 0.5) if peak else out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=86.0)
    ap.add_argument("--out", default=str(Path(__file__).with_name("score_almido.wav")))
    a = ap.parse_args()
    mono = build(a.seconds)
    # a gentle stereo spread: delay one side by 11 ms
    d = int(0.011 * SR)
    left = mono
    right = np.concatenate([np.zeros(d), mono[:-d]]) * 0.96
    st = np.stack([left, right], axis=1)
    pcm = (np.clip(st, -1, 1) * 32767).astype("<i2")
    with wave.open(a.out, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    print(a.out, f"{a.seconds:.1f}s")


if __name__ == "__main__":
    main()
