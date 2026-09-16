# -*- coding: utf-8 -*-
"""WINSTON, judged on ITS OWN terms before it is judged on ours.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

`winston_repaint.py` renders at 2400 px, which is the question Iddo asked (is it
sharp?) but NOT the condition WINSTON's own published numbers were measured under.
Those were measured at the training size, with `winston.load` doing the reading.
So this file reproduces exactly that - same loader, same size, same mse - on
photographs from the checkpoint's own training folder, and only then compares.

If WINSTON does not beat a flat colour HERE, on the pictures it trained on, then
the 2400 px result is not a resolution artefact and nothing needs to be softened
in reporting it.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

import numpy as np
import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import winston as Wn                                          # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--folder", required=True)
    ap.add_argument("--size", type=int, default=256)
    ap.add_argument("--chunk", type=int, default=8)
    a = ap.parse_args()

    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    ck = torch.load(a.ckpt, map_location="cpu", weights_only=False)
    grid = int(round((ck["net"]["decide.0.weight"].shape[1] / 256.0) ** 0.5))
    strokes = int(ck["net"]["decide.4.weight"].shape[0] // Wn.PARAMS)
    net = Wn.Painter(strokes, grid=grid).to(dev).eval()
    net.load_state_dict(ck["net"])
    paths = sorted(sum((glob.glob(os.path.join(a.folder, e))
                        for e in ("*.jpg", "*.JPG", "*.png")), []))
    X = torch.as_tensor(np.stack([Wn.load(p, a.size) for p in paths]), device=dev)
    print(f"{a.ckpt}: {strokes} strokes, grid {grid}, "
          f"{len(paths)} pictures at {a.size}px on {dev}", flush=True)

    rows = []
    with torch.no_grad():
        for i, p in enumerate(paths):
            x = X[i:i + 1]
            y = Wn.render(net(x), size=a.size, chunk=a.chunk, n_total=strokes)
            mse = float(((y - x) ** 2).mean())
            flat = x.reshape(-1, 3).mean(0)
            blank = float(((x - flat) ** 2).mean())
            rows.append({"image": os.path.basename(p), "mse": round(mse, 5),
                         "blank": round(blank, 5),
                         "x_vs_blank": round(blank / max(mse, 1e-9), 3)})
            print(f"  {rows[-1]['image']:<26} PAINTER {mse:.5f}  BLANK {blank:.5f}"
                  f"  x{rows[-1]['x_vs_blank']}", flush=True)
    w = sum(1 for r in rows if r["x_vs_blank"] > 1.0)
    print(f"\n{w}/{len(rows)} beat a flat colour. "
          f"median x{np.median([r['x_vs_blank'] for r in rows]):.3f}", flush=True)
    print(json.dumps({"ckpt": a.ckpt, "size": a.size, "rows": rows}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
