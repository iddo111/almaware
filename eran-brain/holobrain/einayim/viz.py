"""EINAYIM / עֵינַיִם — SHOW THE TRUTH AND THE GUESS SIDE BY SIDE.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

A number in a table can be argued with. A picture of the two depth maps next to
each other cannot. Both are painted with the SAME colour scale — a predicted depth
map stretched to its own min/max always looks right, and that is the oldest lie in
this field.

numpy + Pillow. No matplotlib (not installed on eran3, and not needed).
"""
from __future__ import annotations

import argparse
import json
import os

import numpy as np
from PIL import Image, ImageDraw

# PC courtesy (2026-09-03 scar: renders starved the KESHEV mic): run below normal priority.
try:
    import psutil as _ps
    _ps.Process().nice(_ps.BELOW_NORMAL_PRIORITY_CLASS)
except Exception:
    pass


_ANCH = np.array([[0.19, 0.07, 0.23], [0.21, 0.36, 0.55], [0.15, 0.62, 0.53],
                  [0.62, 0.78, 0.27], [0.99, 0.91, 0.14]])


def ramp(x):
    """A viridis-shaped ramp, hand-rolled. x in 0..1 -> (...,3)."""
    x = np.clip(x, 0.0, 1.0) * (len(_ANCH) - 1)
    i = np.clip(np.floor(x).astype(int), 0, len(_ANCH) - 2)
    f = (x - i)[..., None]
    return _ANCH[i] * (1 - f) + _ANCH[i + 1] * f


def depth_png(d, mask, lo, hi):
    img = ramp((d - lo) / max(hi - lo, 1e-9))
    return np.where(mask[..., None], img, np.array([0.10, 0.10, 0.12]))


def strip(panels, labels, pad=8, bg=(0.97, 0.97, 0.96)):
    h = max(p.shape[0] for p in panels)
    w = sum(p.shape[1] for p in panels) + pad * (len(panels) + 1)
    out = np.tile(np.array(bg), (h + pad * 2 + 16, w, 1))
    x = pad
    for p in panels:
        out[pad:pad + p.shape[0], x:x + p.shape[1]] = p
        x += p.shape[1] + pad
    im = Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8))
    dr = ImageDraw.Draw(im)
    x = pad
    for p, lab in zip(panels, labels):
        dr.text((x + 3, pad + p.shape[0] + 2), lab, fill=(30, 30, 40))
        x += p.shape[1] + pad
    return im


def compare(truth_dir, pred_npz, out_png, view=0, far_factor=3.0):
    import score as SC
    P = np.load(pred_npz, allow_pickle=True)
    idx = list(P["view_index"])
    k = idx.index(view) if view in idx else 0
    S, Hp, Wp = P["depth"].shape
    T = [SC.resample_truth(t, Hp, Wp) for t in SC.load_truth(truth_dir, idx)]

    hit = np.stack([t["mask"] for t in T])
    dta = np.stack([t["depth"] for t in T])
    far = far_factor * float(np.median(dta[hit]))
    valid = np.stack([T[j]["mask"] & (P["depth"][j] > 0) & (T[j]["depth"] <= far)
                      for j in range(S)])
    s = float(np.median(dta[valid] / P["depth"][valid]))

    dt = T[k]["depth"]; dp = s * P["depth"][k]; m = valid[k]
    lo, hi = float(dt[m].min()), float(dt[m].max())
    rgb = np.asarray(Image.open(os.path.join(truth_dir, f"view_{view:02d}.png"))
                     .resize((Wp, Hp), Image.Resampling.BICUBIC), np.float32) / 255.0
    rel = np.where(m, np.abs(dp - dt) / np.maximum(dt, 1e-9), 0.0)
    err = np.where(m[..., None], ramp(np.clip(rel / 0.10, 0, 1)),
                   np.array([0.10, 0.10, 0.12]))

    im = strip([rgb, depth_png(dt, m, lo, hi), depth_png(dp, m, lo, hi), err],
               [f"photo (view {view})", f"TRUTH depth {lo:.2f}-{hi:.2f}",
                f"VGGT depth ({len(idx)} views, x{s:.2f})",
                f"error 0-10%  median {np.median(rel[m])*100:.2f}%"])
    os.makedirs(os.path.dirname(os.path.abspath(out_png)) or ".", exist_ok=True)
    im.save(out_png)
    return {"png": out_png, "median_absrel": float(np.median(rel[m])), "scale": s}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("truth_dir"); ap.add_argument("pred_npz"); ap.add_argument("out_png")
    ap.add_argument("--view", type=int, default=0)
    a = ap.parse_args()
    print(json.dumps(compare(a.truth_dir, a.pred_npz, a.out_png, a.view), indent=1))
