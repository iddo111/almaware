#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""THE PERCEPTRON — feature-length score bed.

Derived from music/darwish_psytrance.py (Freygish / Ahava-Rabbah, 145 BPM,
pure numpy, 100% ours). That generator writes one 56-bar piece; a 14-minute
documentary needs about nine of them, and nine identical copies would be
unbearable.

So the piece is rebuilt as a CYCLE: each 56-bar cycle rotates the Freygish
motif, rotates the chord progression, and is given its own density profile, so
the bed moves with the film instead of looping. Cycles are rendered one at a
time (33 MB of float per cycle instead of 3 GB for the whole film) and
cross-faded together.

    python score_perceptron.py <seconds> <out.wav>
"""
import os
import sys
import wave

import numpy as np

SR = 44100
BPM = 145.0
BEAT = 60.0 / BPM
SIX = BEAT / 4.0
BAR = BEAT * 4.0
CYCLE_BARS = 56
CYCLE_S = BAR * CYCLE_BARS          # 92.69 s

ROOT = 41.20                        # E1
SCALE = [0, 1, 4, 5, 7, 8, 10]      # E F G# A B C D  — Ahava-Rabbah


def hz(semi):
    return ROOT * 2 ** (semi / 12.0)


def deg(i, octave=0):
    return hz(SCALE[i % 7] + 12 * (octave + i // 7))


def saw(f, N):
    t = np.arange(N) / SR
    return 2 * (t * f - np.floor(0.5 + t * f))


def sine(f, N):
    return np.sin(2 * np.pi * f * np.arange(N) / SR)


def fft_lp(x, cut, res=1.0):
    N = len(x)
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(N, 1 / SR)
    H = 1.0 / (1.0 + (f / cut) ** 4)
    if res > 1.0:
        H = H + (res - 1.0) * np.exp(-((f - cut) / (cut * 0.25)) ** 2)
    return np.fft.irfft(X * H, N)


def env(dur, a=0.005, d=0.1, r=0.05, sus=0.6):
    N = int(dur * SR)
    e = np.zeros(N)
    ai, di, ri = max(int(a * SR), 1), max(int(d * SR), 1), max(int(r * SR), 1)
    i = 0
    ai = min(ai, N); e[:ai] = np.linspace(0, 1, ai); i = ai
    j = min(i + di, N); e[i:j] = np.linspace(1, sus, j - i); i = j
    hold = max(N - ri - i, 0); e[i:i + hold] = sus; i += hold
    if i < N:
        e[i:] = np.linspace(e[i - 1] if i > 0 else sus, 0, N - i)
    return e


MOTIF = [0, 2, 1, 4, 3, 6, 4, 7, 6, 4, 3, 2, 1, 0, 1, 2]
PROG = [(0, 3, 4), (0, 3, 6), (-1, 2, 3), (0, 3, 4)]

# density per cycle: (kick, bass, lead, hats, perc, pad)
# cycle 0 opens sparse, the middle drives, the last cycles go warm and quiet
PROFILES = [
    (0.35, 0.45, 0.25, 0.30, 0.70, 1.00),   # 0  cold open, history
    (0.55, 0.70, 0.40, 0.55, 0.85, 1.00),   # 1
    (0.60, 0.75, 0.45, 0.60, 0.90, 1.00),   # 2
    (0.50, 0.65, 0.55, 0.55, 0.85, 1.00),   # 3  the machine
    (0.30, 0.35, 0.30, 0.30, 0.60, 1.00),   # 4  the winter
    (0.85, 0.95, 0.85, 0.90, 0.95, 1.00),   # 5  the climb
    (0.75, 0.85, 0.70, 0.80, 0.90, 1.00),   # 6  the cost
    (0.55, 0.65, 0.60, 0.55, 0.80, 1.00),   # 7  the memristor
    (0.40, 0.45, 0.45, 0.40, 0.70, 1.00),   # 8  the Shifra brain
    (0.25, 0.30, 0.35, 0.25, 0.55, 1.00),   # 9  the close
]


def cycle(ci):
    """Render one 56-bar cycle. ci selects motif rotation and density."""
    rng = np.random.default_rng(11 + ci * 101)
    n = int(CYCLE_S * SR)
    prof = PROFILES[ci % len(PROFILES)]
    g_kick, g_bass, g_lead, g_hat, g_perc, g_pad = prof
    rot = (ci * 3) % 16
    motif = MOTIF[rot:] + MOTIF[:rot]
    prog = PROG[ci % len(PROG):] + PROG[:ci % len(PROG)]

    def place(buf, start_s, sig):
        s = int(start_s * SR)
        e = min(s + len(sig), len(buf))
        if s < len(buf):
            buf[s:e] += sig[:e - s]

    # kick
    N = int(0.18 * SR)
    tt = np.arange(N) / SR
    body = np.sin(2 * np.pi * (55 * np.exp(-tt * 28) + 42) * tt) * np.exp(-tt * 16)
    click = fft_lp(rng.standard_normal(N), 5000) * np.exp(-tt * 120) * 0.35
    KICK = (body + click) * 0.9

    out = np.zeros(n)
    kick_env = np.zeros(n)
    for b in range(CYCLE_BARS * 4):
        place(out, b * BEAT, KICK)
        s = int(b * BEAT * SR); e = min(s + len(KICK), n)
        kick_env[s:e] = np.maximum(kick_env[s:e],
                                   np.exp(-np.arange(e - s) / (0.18 * SR)))
    sidechain = 1 - 0.85 * kick_env

    bass = np.zeros(n)
    for b in range(CYCLE_BARS * 4):
        for s16 in (1, 2, 3):
            note = deg(0, 0) if (b % 8) != 7 else deg(6, -1)
            N = int(SIX * 0.95 * SR)
            sg = saw(note, N) + 0.5 * saw(note * 1.005, N)
            sg = fft_lp(sg, 220, res=1.3) * env(SIX * 0.95, a=0.004, d=0.06, sus=0.2, r=0.02)
            place(bass, b * BEAT + s16 * SIX, sg * 0.9)
    bass *= sidechain

    pad = np.zeros(n)
    for bar in range(CYCLE_BARS):
        ch = prog[(bar // 4) % len(prog)]
        N = int(BAR * SR)
        seg = np.zeros(N)
        for d_ in ch:
            f = deg(d_, 2)
            seg += saw(f, N) + saw(f * 1.003, N) + 0.6 * sine(f * 0.5, N)
        seg = fft_lp(seg, 1400) * env(BAR, a=0.35, d=0.4, sus=0.55, r=0.4)
        place(pad, bar * BAR, seg * 0.14)
    pad *= (0.6 + 0.4 * sidechain)

    lead = np.zeros(n)
    for bar in range(CYCLE_BARS):
        for k in range(16):
            f = deg(motif[k], 3)
            N = int(SIX * 0.9 * SR)
            cut = 600 + 2600 * (0.5 + 0.5 * np.sin(bar * 0.5 + k * 0.4 + ci))
            sg = saw(f, N) * 0.7 + saw(f * 0.995, N) * 0.3
            sg = fft_lp(sg, cut, res=2.2) * env(SIX * 0.9, a=0.003, d=0.05, sus=0.25, r=0.03)
            place(lead, bar * BAR + k * SIX, sg * 0.5)
    lead *= sidechain

    hats = np.zeros(n)
    for b in range(CYCLE_BARS * 4):
        N = int(0.05 * SR)
        h = fft_lp(rng.standard_normal(N), 12000)
        h = h - fft_lp(h, 7000)
        h *= np.exp(-np.arange(N) / (0.02 * SR))
        place(hats, b * BEAT + BEAT / 2, h * 0.25)

    perc = np.zeros(n)
    N = int(0.14 * SR); tt = np.arange(N) / SR
    DUM = (np.sin(2 * np.pi * (90 * np.exp(-tt * 22) + 60) * tt) * np.exp(-tt * 16)) * 0.8
    N = int(0.06 * SR); tt = np.arange(N) / SR
    TEK = (fft_lp(rng.standard_normal(N), 9000) * np.exp(-tt * 45)) * 0.5
    for bar in range(CYCLE_BARS):
        for pos, snd in {0: DUM, 1.5: TEK, 2: TEK, 3: DUM, 3.5: TEK}.items():
            place(perc, bar * BAR + pos * BEAT, snd)

    # breakdown late in every cycle so the bed keeps breathing
    brk = np.ones(n)
    s, e = int(44 * BAR * SR), int(48 * BAR * SR)
    brk[s:e] = np.linspace(1, 0.2, e - s)
    e2 = min(e + int(2 * BAR * SR), n)
    brk[e:e2] = np.linspace(0.2, 1, e2 - e)

    mix = (out * g_kick * brk * 0.9 + bass * g_bass * brk + pad * g_pad
           + lead * g_lead + hats * g_hat * brk + perc * g_perc)
    return mix


def reverb(x, dl=0.09, fb=0.3):
    d = int(dl * SR)
    y = x.copy()
    for k in range(1, 4):
        s = d * k
        y[s:] += x[:-s] * (fb ** k)
    return y


def main():
    total_s = float(sys.argv[1]) if len(sys.argv) > 1 else 840.0
    out_path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "perceptron_score.wav")
    xf = int(2.0 * SR)                      # 2 s cross-fade between cycles
    n_total = int(total_s * SR)
    bed = np.zeros(n_total + int(CYCLE_S * SR))
    pos = 0
    ci = 0
    while pos < n_total:
        c = cycle(ci)
        if pos > 0:
            f = np.linspace(0, 1, xf)
            bed[pos:pos + xf] = bed[pos:pos + xf] * (1 - f) + c[:xf] * f
            bed[pos + xf:pos + len(c)] += c[xf:]
        else:
            bed[:len(c)] += c
        print("  cycle %d rendered at %.1fs" % (ci, pos / SR), flush=True)
        pos += len(c) - xf
        ci += 1
    bed = bed[:n_total]

    # global shape: fade in, fade out
    fi = int(6 * SR); fo = int(10 * SR)
    bed[:fi] *= np.linspace(0, 1, fi)
    bed[-fo:] *= np.linspace(1, 0, fo)

    wet = reverb(bed) * 0.25
    L = bed + wet
    R = bed + np.roll(wet, int(0.012 * SR))
    peak = max(np.max(np.abs(L)), np.max(np.abs(R))) + 1e-9
    L = np.tanh(L / peak * 1.4) * 0.95
    R = np.tanh(R / peak * 1.4) * 0.95

    inter = np.empty(len(L) * 2)
    inter[0::2] = L
    inter[1::2] = R
    pcm = (np.clip(inter, -1, 1) * 32767).astype("<i2")
    with wave.open(out_path, "w") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    print("WROTE %s  (%.1fs, %d cycles, %.0f BPM, Freygish/Ahava-Rabbah)"
          % (out_path, len(L) / SR, ci, BPM))


if __name__ == "__main__":
    main()
