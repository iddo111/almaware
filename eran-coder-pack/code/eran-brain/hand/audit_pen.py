"""Can the tremor SEE the new coordinate? Measure it; do not assume it.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

The sigma curve on record — cosine +0.76 with the true gradient at 0.02, +0.05 at 0.15,
NEGATIVE at 0.40 — was measured on a pen whose every number was an x or a y. Pressure is
a different animal: it goes through a sigmoid into a 0.057-wide window, so the same shake
that moves a point by 0.02 of a page moves the nib by 0.0003. If that is below the noise,
the hand will learn the shape and never learn the pressure, and the extra numbers will be
dead weight sold as an improvement.

So the cosine is measured SEPARATELY for the xy coordinates and the pressure ones. Two
numbers, because they can disagree.
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import torch
import torch.nn.functional as F

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "eye"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "miko", "model"))

from hand_eye import Winston, ink, centroids, load_eye            # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--eye", default=os.path.join(HERE, "..", "eye", "state", "eye.pt"))
    ap.add_argument("--data", default=os.path.join(HERE, "..", "eye", "corpus",
                                                   "letters.npz"))
    ap.add_argument("--strokes", type=int, default=5)
    ap.add_argument("--points", type=int, default=8)
    ap.add_argument("--k", type=int, default=2000)
    ap.add_argument("--wgain", type=float, default=1.0,
                    help="Shake the nib HARDER than the points. The one-bit "
                         "estimator points along the true gradient weighted by "
                         "sigma_i squared, so a bigger shake on one coordinate "
                         "is a legitimate preconditioner -- still strictly "
                         "uphill -- and it leaves the PEN untouched, so the "
                         "measured ceiling stays valid.")
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    a = ap.parse_args(argv)

    dev = torch.device(a.device)
    torch.manual_seed(1933)
    enc = load_eye(a.eye, dev)
    d = np.load(a.data)
    cent, cls = centroids(enc, d["X"].astype(np.float32), d["y"], dev)
    n = len(cls)
    hand = Winston(n, a.strokes, a.points, pressure=True).to(dev)
    eye_in = torch.eye(n, device=dev)
    S, P = a.strokes, a.points
    dim = 3

    # which output columns are xy, which are pressure
    idx = torch.arange(S * P * dim, device=dev).view(S, P, dim)
    is_w = torch.zeros(S * P * dim, dtype=torch.bool, device=dev)
    is_w[idx[..., 2].reshape(-1)] = True

    c = 1                                             # one letter; the rule is per-letter
    oh = eye_in[c:c + 1]
    xy, w = hand(oh)
    sc = (enc.gist(ink(xy, w)) * cent[c]).sum()
    g_true = torch.autograd.grad(sc, hand.out.weight)[0][:, c]     # (out,)
    print("wgain %.1f — the nib is shaken that many times harder than the points" % a.wgain)
    print("pen %dx%d with pressure — %d numbers, %d of them nib width"
          % (S, P, S * P * dim, int(is_w.sum())))
    print("true gradient norm: xy %.3e   pressure %.3e"
          % (g_true[~is_w].norm(), g_true[is_w].norm()))
    print("\n  sigma |  cosine all   cosine xy   cosine pressure   (%d tremors)" % a.k)
    for sigma in (0.005, 0.01, 0.02, 0.05, 0.1, 0.2):
        acc = torch.zeros_like(g_true)
        B = 200
        for _ in range(a.k // B):
            e3 = sigma * torch.randn(B, hand.out.out_features, device=dev)
            e3[:, is_w] *= a.wgain
            with torch.no_grad():
                xy, w = hand(oh.expand(B, -1), e3=e3)
                su = (enc.gist(ink(xy, w)) * cent[c]).sum(-1)
                xy, w = hand(oh.expand(B, -1), e3=-e3)
                sd = (enc.gist(ink(xy, w)) * cent[c]).sum(-1)
                sign = torch.where(su > sd, 1.0, -1.0)
                acc += (sign.unsqueeze(1) * e3).sum(0)
        cos_all = float(F.cosine_similarity(acc, g_true, dim=0))
        cos_xy = float(F.cosine_similarity(acc[~is_w], g_true[~is_w], dim=0))
        cos_w = float(F.cosine_similarity(acc[is_w], g_true[is_w], dim=0))
        print("  %.3f | %+.4f      %+.4f     %+.4f" % (sigma, cos_all, cos_xy, cos_w),
              flush=True)
    print("\nA pressure cosine near zero means the extra numbers are DEAD — the hand "
          "would be shaking a dial it cannot feel.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
