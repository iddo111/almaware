"""ALMA DRAUGHTSMAN — the hand that draws in strokes, not pixels.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

Iddo, 2026-08-28, pointing at a psytrance video: *"התמונות הפסיכודליות המשתנות — זה אפשר
נגיד להפיק עם המנוע שלנו לפי המוזיקה."*

Yes. And this is the one place a hand-written renderer genuinely beats diffusion:

- **Resolution-free.** The drawing is curves. 1080p, 4K, 8K, a wall poster — same file, same
  code, no upscaler, no hallucinated detail. `--w 7680` costs time, not truth.
- **Locked to the music, frame-exact.** Every stroke's position comes from the audio at that
  frame. Diffusion cannot hit a beat; this cannot miss one.
- **Deterministic.** Same seed + same wav = the same film, forever. It can be tested.

## What it is, in ALMA's own words (SPEC.md §1)

A **weave**: knots joined by strands, sparks travelling over beats.
Here the music's beat IS the beat — not a metaphor, the same clock.

    knot    a centre of drawing, placed once, deterministic
    strand  a cord between two knots; its WEIGHT is how strongly it is drawn
    spark   a band of the music's energy, injected at a knot and travelling out
    beat    one frame

Low band feeds the inner knots, high band the outer ones, so bass moves the big slow
shapes and the hats flicker at the rim — which is what the eye reads as "the music".

Usage:
    python draw.py --audio ../perceptron-movie/music/perceptron_score.wav \\
                   --out out/alma_4k.mp4 --w 3840 --h 2160 --fps 30 --start 60 --dur 20
"""
from __future__ import annotations

import argparse
import math
import os
import subprocess
import sys
import wave

import numpy as np
from PIL import Image, ImageDraw


# ------------------------------------------------------------------ the ear

def read_wav_mono(path: str) -> tuple[np.ndarray, int]:
    w = wave.open(path, "rb")
    sr, ch, n = w.getframerate(), w.getnchannels(), w.getnframes()
    a = np.frombuffer(w.readframes(n), dtype="<i2").astype(np.float32) / 32768.0
    if ch > 1:
        a = a.reshape(-1, ch).mean(1)
    return a, sr


def bands(a: np.ndarray, sr: int, fps: int, n_frames: int) -> np.ndarray:
    """Per-frame [bass, mid, high, onset], each normalised to roughly 0..1.

    A plain FFT per frame. No model, no training — the music is already the signal.
    """
    hop = sr / fps
    win = int(sr * 0.046)                      # ~46 ms, 2 frames of slack at 24-30 fps
    out = np.zeros((n_frames, 4), dtype=np.float32)
    freqs = np.fft.rfftfreq(win, 1.0 / sr)
    m_bass = freqs < 200
    m_mid = (freqs >= 200) & (freqs < 2000)
    m_high = freqs >= 2000
    prev = 0.0
    for i in range(n_frames):
        s = int(i * hop)
        seg = a[s:s + win]
        if len(seg) < win:
            seg = np.pad(seg, (0, win - len(seg)))
        mag = np.abs(np.fft.rfft(seg * np.hanning(win)))
        b, m, h = mag[m_bass].mean(), mag[m_mid].mean(), mag[m_high].mean()
        tot = float(mag.mean())
        out[i] = (b, m, h, max(0.0, tot - prev))   # onset = rise in total energy
        prev = tot
    # normalise each column by its own 97th percentile: the loudest 3% may clip, and
    # a peak-normalised column would let one crash flatten the whole film.
    for c in range(4):
        p = np.percentile(out[:, c], 97) or 1.0
        out[:, c] = np.clip(out[:, c] / p, 0.0, 1.6)
    # smooth bass and mid a little; leave high and onset sharp, they are the flicker
    for c in (0, 1):
        k = np.array([0.15, 0.7, 0.15], dtype=np.float32)
        out[:, c] = np.convolve(out[:, c], k, mode="same")
    return out


# ------------------------------------------------------------------ the hand

def palette(t: float, energy: float) -> tuple:
    """Luminous ink on dark ground. Hue walks slowly; energy makes it burn."""
    hue = (t * 0.035) % 1.0
    import colorsys
    r, g, b = colorsys.hsv_to_rgb(hue, 0.55 - 0.25 * energy, min(1.0, 0.45 + 0.75 * energy))
    return int(r * 255), int(g * 255), int(b * 255)


def knots(n: int, w: int, h: int, seed: int) -> np.ndarray:
    """Placed once, deterministically. The layout IS the program (SPEC.md §2, law 3)."""
    rng = np.random.RandomState(seed)
    ang = np.linspace(0, 2 * math.pi, n, endpoint=False) + rng.uniform(0, 0.6, n)
    rad = np.linspace(0.07, 0.44, n) * min(w, h)
    rad = rad * rng.uniform(0.85, 1.15, n)
    return np.stack([w / 2 + np.cos(ang) * rad, h / 2 + np.sin(ang) * rad], 1)


def draw_frame(w, h, K, bnd, t, seed, strokes, mirror, canvas, fade=0.80):
    """Draw one beat onto the persistent canvas.

    Three things separate a plot from a psychedelic visual, and the first pass had none
    of them:
      * TRAILS   — the canvas is faded, not cleared, so motion leaves a wake.
      * MIRROR   — one wedge is drawn and rotated `mirror` times. Radial symmetry is
                   what the eye reads as "kaleidoscope"; it costs nothing to add.
      * WEIGHT   — the first pass drew hairlines at alpha 45 on black. Invisible.
    """
    bass, mid, high, onset = (float(x) for x in bnd)
    # fade toward black: the wake. More energy = shorter wake, so drops feel sharp.
    canvas = canvas.point(lambda v, k=fade - 0.13 * onset: int(v * k))
    d = ImageDraw.Draw(canvas, "RGBA")
    n = len(K)
    s = min(w, h)
    cx0, cy0 = w / 2.0, h / 2.0
    for m in range(mirror):
        rot = 2 * math.pi * m / mirror
        cs, sn = math.cos(rot), math.sin(rot)
        for i in range(n):
            a, b = K[i], K[(i + 1 + int(1 + 2 * bass)) % n]
            f = i / max(n - 1, 1)
            spark = bass * (1 - f) + high * f          # bass inside, hats at the rim
            mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
            vx, vy = mx - cx0, my - cy0
            L = math.hypot(vx, vy) or 1.0
            bow = (0.10 + 0.60 * mid + 0.55 * onset) * s * 0.30
            ccx, ccy = mx + vx / L * bow, my + vy / L * bow
            col = palette(t + f * 2.0 + m * 0.04, spark)
            wid = max(2, int((0.6 + 2.6 * spark) * s / 900))
            pts = []
            for k in range(strokes + 1):
                u = k / strokes
                x = (1 - u) ** 2 * a[0] + 2 * (1 - u) * u * ccx + u ** 2 * b[0]
                y = (1 - u) ** 2 * a[1] + 2 * (1 - u) * u * ccy + u ** 2 * b[1]
                j = (0.6 + 2.2 * high) * s * 0.0022     # the hand's tremor, seeded
                x += math.sin(u * 9.0 + t * 2.3 + i) * j
                y += math.cos(u * 7.0 + t * 1.9 + i) * j
                dx, dy = x - cx0, y - cy0               # rotate into this wedge
                pts.append((cx0 + dx * cs - dy * sn, cy0 + dx * sn + dy * cs))
            d.line(pts, fill=col + (int(90 + 150 * min(1.0, spark)),),
                   width=wid, joint="curve")
    r = (0.03 + 0.13 * bass + 0.06 * onset) * s
    d.ellipse([cx0 - r, cy0 - r, cx0 + r, cy0 + r],
              outline=palette(t, bass) + (230,), width=max(2, int(s / 420)))
    return canvas


# ------------------------------------------------------------------ the film

def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="ALMA draughtsman — audio-reactive vector film")
    p.add_argument("--audio", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--w", type=int, default=3840)
    p.add_argument("--h", type=int, default=2160)
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--start", type=float, default=0.0)
    p.add_argument("--dur", type=float, default=20.0)
    p.add_argument("--knots", type=int, default=26)
    p.add_argument("--strokes", type=int, default=44, help="points per curve")
    p.add_argument("--seed", type=int, default=1337)
    p.add_argument("--mirror", type=int, default=6, help="radial symmetry")
    p.add_argument("--fade", type=float, default=0.80, help="trail: 1 = never fades")
    a = p.parse_args(argv)

    audio, sr = read_wav_mono(a.audio)
    s0 = int(a.start * sr)
    audio = audio[s0:s0 + int(a.dur * sr)]
    n_frames = int(a.dur * a.fps)
    print("audio %.1fs @ %d Hz -> %d frames at %dx%d" % (a.dur, sr, n_frames, a.w, a.h))
    B = bands(audio, sr, a.fps, n_frames)
    K = knots(a.knots, a.w, a.h, a.seed)
    canvas = Image.new("RGB", (a.w, a.h), (5, 4, 9))

    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", "%dx%d" % (a.w, a.h), "-r", str(a.fps), "-i", "-",
           "-ss", "%.3f" % a.start, "-t", "%.3f" % a.dur, "-i", a.audio,
           "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", a.out]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(n_frames):
        canvas = draw_frame(a.w, a.h, K, B[i], i / a.fps, a.seed,
                            a.strokes, a.mirror, canvas, a.fade)
        proc.stdin.write(canvas.tobytes())
        if i % max(1, n_frames // 10) == 0:
            print("  %3d%%" % (100 * i // n_frames), flush=True)
    proc.stdin.close()
    rc = proc.wait()
    print("FINAL:", a.out, "rc=%d" % rc)
    return rc


if __name__ == "__main__":
    sys.exit(main())
