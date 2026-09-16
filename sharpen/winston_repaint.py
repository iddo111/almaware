# -*- coding: utf-8 -*-
"""
> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

WINSTON AS A RE-PAINTER, MEASURED ON THE SAME RULER AS EVERYTHING ELSE.

Iddo, 2026-09-06: "nir'e li WINSTON ya'ase et ze yafe me'od."

WHAT WINSTON IS AND IS NOT, before a single picture is made. Measured 2026-09-05
by another agent and not disputed here: `winston-forever-v2` beats a flat colour
by 18x on a photograph from its own corpus, LOSES to a flat colour on one it has
never seen, and scores x0.90 / x0.82 out of distribution on a street scene. It
MEMORISED 84 photographs. It cannot invent a picture it has not seen.

But it was never a generator. It is a RE-PAINTER: hand it an image and it emits
strokes for THAT image. So the only fair question is the one this file asks -
given a picture, does WINSTON's repaint come out SHARPER than what it was given?
The answer is a number on the same Laplacian ruler, whatever it turns out to be.

Runs where torch is: eran1 (idle, 107 GB free). NEVER on eran4, where
`winston-forever-v2` has been training unbroken since 2026-09-02.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np
import torch
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import winston as Wn                                       # noqa: E402


def lapvar(im: Image.Image, cap: int = 2400) -> float:
    """The one ruler. Identical to D:/CLAUDE/sharpen/sharpness.py."""
    im = im.convert("L")
    w, h = im.size
    if max(w, h) > cap:
        s = cap / float(max(w, h))
        im = im.resize((max(1, round(w * s)), max(1, round(h * s))), Image.LANCZOS)
    g = np.asarray(im, dtype=np.float64)
    lap = (-4.0 * g[1:-1, 1:-1] + g[:-2, 1:-1] + g[2:, 1:-1]
           + g[1:-1, :-2] + g[1:-1, 2:])
    return float(lap.var())


def square(path: str, size: int) -> Image.Image:
    """The SAME centre crop `winston.load` takes, so source and repaint compare."""
    im = Image.open(path).convert("RGB")
    s = min(im.size)
    im = im.crop(((im.width - s) // 2, (im.height - s) // 2,
                  (im.width + s) // 2, (im.height + s) // 2))
    return im.resize((size, size), Image.LANCZOS)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--render", type=int, default=2400)
    ap.add_argument("--size", type=int, default=256)
    ap.add_argument("--grid", type=int, default=4)
    ap.add_argument("--strokes", type=int, default=0)
    ap.add_argument("--tile", type=int, default=384)
    ap.add_argument("--chunk", type=int, default=16)
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("images", nargs="+")
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    dev = torch.device(a.device)
    ck = torch.load(a.ckpt, map_location="cpu", weights_only=False)
    strokes = a.strokes or int(ck.get("strokes", 800))
    # the checkpoint does not always carry `grid`, and guessing it wrong is a
    # silent load failure. Read it off the first linear layer: 256*grid*grid.
    w0 = ck["net"]["decide.0.weight"].shape[1]
    grid = int(round((w0 / 256.0) ** 0.5))
    strokes = int(ck["net"]["decide.4.weight"].shape[0] // Wn.PARAMS)
    net = Wn.Painter(strokes, grid=grid).to(dev).eval()
    net.load_state_dict(ck["net"])
    print(f"checkpoint {a.ckpt}: {strokes} strokes, grid {grid}, "
          f"step {ck.get('step','?')}, device {dev}", flush=True)

    rows = []
    for p in a.images:
        name = os.path.splitext(os.path.basename(p))[0]
        t0 = time.time()
        src_small = square(p, a.size)
        x = torch.as_tensor(np.asarray(src_small, dtype=np.float32)[None] / 255.0,
                            device=dev)
        with torch.no_grad():
            par = net(x)
            big = Wn.render_big(par, size=a.render, tile=a.tile, chunk=a.chunk,
                                device=dev)
        out = (np.clip(big[0].float().cpu().numpy(), 0, 1) * 255).astype(np.uint8)
        rep = Image.fromarray(out)
        rep_path = os.path.join(a.out, f"{name}-winston{a.render}.png")
        rep.save(rep_path)

        # the SAME square, at the SAME size, is what the repaint must be judged against
        src_big = square(p, a.render)
        src_path = os.path.join(a.out, f"{name}-source{a.render}.png")
        src_big.save(src_path)

        mse = float(((np.asarray(src_big, np.float32) / 255.0
                      - np.asarray(rep, np.float32) / 255.0) ** 2).mean())
        flat = np.asarray(src_big, np.float32).reshape(-1, 3).mean(0) / 255.0
        blank = float(((np.asarray(src_big, np.float32) / 255.0 - flat) ** 2).mean())
        r = {"image": p, "source_lapvar": round(lapvar(src_big), 1),
             "winston_lapvar": round(lapvar(rep), 1),
             "mse_vs_source": round(mse, 5), "blank_mse": round(blank, 5),
             "x_vs_blank": round(blank / max(mse, 1e-9), 3),
             "render_px": a.render, "seconds": round(time.time() - t0, 1),
             "out": rep_path}
        rows.append(r)
        print(f"  {name:<28} source {r['source_lapvar']:8.1f} -> WINSTON "
              f"{r['winston_lapvar']:8.1f}   mse {mse:.5f} vs blank {blank:.5f} "
              f"(x{r['x_vs_blank']})  {r['seconds']}s", flush=True)

    with open(os.path.join(a.out, "winston-repaint.json"), "w",
              encoding="utf-8") as f:
        json.dump({"ckpt": a.ckpt, "strokes": strokes, "grid": grid,
                   "rows": rows}, f, indent=2, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
