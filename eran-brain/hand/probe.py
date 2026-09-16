"""IS IT THE PEN, OR IS IT THE EYE? The control that tells them apart.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

The ceiling of the hand's objective was measured and then LOOKED AT, and it is scribble.
Every pen, up to cos 0.589, draws a tangle no person would call a Hebrew letter — while a
REAL printed letter, pushed through the same eye, scores only 0.281 against its own class.
**The drawings beat the letters at being letters.** That is the signature of an
adversarial optimum, not of a hand that cannot draw.

So before anything else is built on top, four objectives on the SAME pen, and the sheet
is looked at each time:

    centroid   maximise cos to the class mean          <- what Winston is trained on
    exemplar   maximise cos to ONE real printed glyph  <- a specific letter, not a mean
    ink        exemplar, plus match how much ink a printed letter puts on the page
    pixels     forget the eye: match the printed glyph PIXEL BY PIXEL

`pixels` is the control that decides the question. If the pen can trace a real alef in
pixel space and it looks like an alef, the pen is fine and the EYE is what cannot be
inverted. If it cannot, the pen is too poor and no judge would have helped.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import torch
import torch.nn.functional as F

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "eye"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "miko", "model"))

from hand_eye import ink, pen, penmarks, centroids, load_eye      # noqa: E402

MODES = ("centroid", "exemplar", "ink", "pixels")


def run(mode, enc, cent, tgt_img, tgt_gist, S, P, steps, lr, seed, dev):
    torch.manual_seed(seed)
    n = cent.shape[0]
    raw = (torch.randn(n, S * P * 3, device=dev) * 0.4).requires_grad_(True)
    opt = torch.optim.Adam([raw], lr=lr)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=steps)
    tgt_cover = tgt_img.mean(dim=(1, 2))
    for _ in range(steps):
        xy, w = pen(raw, S, P, True)
        img = ink(xy, w)
        if mode == "pixels":
            loss = F.mse_loss(img, tgt_img)
        else:
            g = enc.gist(img)
            aim = cent if mode == "centroid" else tgt_gist
            loss = -(g * aim).sum(-1).mean()
            if mode == "ink":
                loss = loss + 3.0 * (img.mean(dim=(1, 2)) - tgt_cover).abs().mean()
        opt.zero_grad()
        loss.backward()
        opt.step()
        sched.step()
    with torch.no_grad():
        xy, w = pen(raw, S, P, True)
        img = ink(xy, w)
        g = enc.gist(img)
        return {"img": img, "cos_centroid": float((g * cent).sum(-1).mean()),
                "cos_exemplar": float((g * tgt_gist).sum(-1).mean()),
                "eye_reads_back": float(((g @ cent.T).argmax(1) ==
                                         torch.arange(n, device=dev)).float().mean()),
                "pixel_mse": float(F.mse_loss(img, tgt_img)),
                "cover": float(img.mean()),
                "marks": penmarks(img, xy, w)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--eye", default=os.path.join(HERE, "..", "eye", "state", "eye.pt"))
    ap.add_argument("--data", default=os.path.join(HERE, "..", "eye", "corpus",
                                                   "letters.npz"))
    ap.add_argument("--strokes", type=int, default=5)
    ap.add_argument("--points", type=int, default=8)
    ap.add_argument("--steps", type=int, default=2500)
    ap.add_argument("--lr", type=float, default=3e-2)
    ap.add_argument("--font", type=int, default=3, help="which printed exemplar to aim at")
    ap.add_argument("--npz", default=os.path.join(HERE, "probe.npz"))
    ap.add_argument("--out", default=os.path.join(HERE, "state", "probe.json"))
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    a = ap.parse_args(argv)

    dev = torch.device(a.device)
    enc = load_eye(a.eye, dev)
    d = np.load(a.data)
    X, y = d["X"].astype(np.float32), d["y"]
    cent, cls = centroids(enc, X, y, dev)
    n = len(cls)
    pick = [np.where(y == c)[0][a.font] for c in range(n)]
    tgt_img = torch.as_tensor(X[pick], device=dev)
    with torch.no_grad():
        tgt_gist = enc.gist(tgt_img)
        own = float((tgt_gist * cent).sum(-1).mean())
        rb = float(((tgt_gist @ cent.T).argmax(1) ==
                    torch.arange(n, device=dev)).float().mean())
    print("THE BAR A REAL PRINTED LETTER CLEARS, through this same eye:")
    print("   printed glyph -> its own class centroid   cos %.4f   read back %.1f%%   "
          "ink %.4f\n" % (own, 100 * rb, float(tgt_img.mean())))
    print("  objective  |  cos to centroid   cos to the real glyph   eye reads | "
          "pixel MSE   ink   pieces")
    print("  " + "-" * 92)

    rows, imgs = {}, {"printed": tgt_img.cpu().numpy()}
    for m in MODES:
        r = run(m, enc, cent, tgt_img, tgt_gist, a.strokes, a.points, a.steps, a.lr,
                1933, dev)
        imgs[m] = r.pop("img").cpu().numpy()
        pieces = float(np.mean([q["pieces"] for q in r["marks"]]))
        r["pieces"] = pieces
        rows[m] = r
        print("  %-10s |    %.4f            %.4f           %5.1f%%  | %.5f  %.4f  %.2f"
              % (m, r["cos_centroid"], r["cos_exemplar"], 100 * r["eye_reads_back"],
                 r["pixel_mse"], r["cover"], pieces), flush=True)

    print("\n  a printed letter scores %.4f against its own centroid." % own)
    for m in MODES:
        if rows[m]["cos_centroid"] > own:
            print("  '%s' scores %.4f -- %.1fx what a REAL LETTER scores. It is not "
                  "drawing a letter, it is drawing what this eye likes."
                  % (m, rows[m]["cos_centroid"], rows[m]["cos_centroid"] / own))
    np.savez_compressed(a.npz, **imgs)
    for m in MODES:
        rows[m].pop("marks", None)
    json.dump({"printed_cos": own, "printed_read_back": rb, "rows": rows},
              open(a.out, "w"), indent=1)
    print("\n  LOOK AT THEM: %s" % a.npz)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
