"""KALEIDO — radial stills from the draughtsman engine (knots, strands, sparks, beats).

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

Same engine as `draw.py`, but it stops on a frame and keeps it. Ten moments, ten seeds.
Everything here is OURS: no diffusion, no weights, no upscaler — the picture is curves,
so `--w 8000` costs seconds, not truth.

**This is NOT Winston.** Iddo, 2026-08-30 21:24: *"הפרקטל זה לא ווינסטון"*. Winston is
`winston.py`, the model that draws in lines.

    python kaleido.py --audio ../perceptron-movie/music/anthem_transmission.wav --n 10
"""
from __future__ import annotations

import argparse
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from draw import read_wav_mono, bands, knots, draw_frame  # noqa: E402


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--audio", required=True)
    p.add_argument("--out", default="out/kaleido")
    p.add_argument("--n", type=int, default=10)
    p.add_argument("--w", type=int, default=2400)
    p.add_argument("--h", type=int, default=2400)
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--warm", type=int, default=48, help="frames of trail before the keep")
    p.add_argument("--knots", type=int, default=26)
    p.add_argument("--strokes", type=int, default=44)
    p.add_argument("--seed", type=int, default=1337)
    a = p.parse_args(argv)

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    pcm, sr = read_wav_mono(a.audio)
    total = int(len(pcm) / sr * a.fps)
    bnd = bands(pcm, sr, a.fps, total)

    made = []
    for i in range(a.n):
        seed = a.seed + i * 101
        mirror = 3 + (i % 6)                      # 3..8 wedges: each picture its own symmetry
        # spread the ten moments evenly over the music, skipping the silent head/tail
        f0 = int(total * (0.06 + 0.86 * (i / max(a.n - 1, 1))))
        f0 = max(a.warm, min(f0, total - 2))
        K = knots(a.knots, a.w, a.h, seed)
        canvas = Image.new("RGB", (a.w, a.h), (0, 0, 0))
        for f in range(f0 - a.warm, f0 + 1):      # build the wake, then keep the frame
            canvas = draw_frame(a.w, a.h, K, bnd[f], f / a.fps, seed,
                                a.strokes, mirror, canvas)
        path = "%s_%02d.png" % (a.out, i + 1)
        canvas.save(path)
        made.append(path)
        print("%2d/%d  %s  seed=%d mirror=%d t=%.1fs" %
              (i + 1, a.n, path, seed, mirror, f0 / a.fps), flush=True)
    print("KALEIDO painted %d." % len(made))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
