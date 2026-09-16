"""HOW HIGH CAN THIS PEN REACH AT ALL — measured before anything is trained.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

Winston reached cos 0.445 with a 3-stroke, 6-point, fixed-width pen. Direct optimisation
of that same pen reaches 0.446. **The learning rule was no longer the limit — the pen
was.** So before growing the rule, grow the pen and MEASURE the new roof.

This is the roof, not a training run: Adam straight onto the control points, with true
gradients through `ink()` and through the frozen eye. Nothing a tremor could ever do
beats it, so it is the honest ceiling of each pen.

Every row also gets the dot-cloud audit, because a ceiling reached by scattering blobs is
not a ceiling worth climbing — that exact trap scored 86% on 2026-08-30 with dot-clouds
no person would call a letter.

    python ceiling.py --steps 2000 --device cuda
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import torch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "eye"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "miko", "model"))

from hand_eye import ink, pen, penmarks, centroids, load_eye     # noqa: E402

GRID = [
    (3, 6, False),      # the control: this must land on 0.446 or the harness is wrong
    (3, 6, True),       # same skeleton, pressure added — what does pressure alone buy?
    (4, 8, False),
    (4, 8, True),
    (5, 8, True),
    (5, 12, True),
    (7, 10, True),
    (3, 20, True),      # few strokes, many points: a smooth curve rather than a polygon
]


def roof(enc, cent, strokes, points, pressure, steps, lr, seed, dev):
    """Adam straight onto the numbers. No network, no rule — just: can the pen get there."""
    torch.manual_seed(seed)
    n = cent.shape[0]
    dim = 3 if pressure else 2
    raw = torch.randn(n, strokes * points * dim, device=dev) * 0.4
    raw.requires_grad_(True)
    opt = torch.optim.Adam([raw], lr=lr)
    # Cosine decay to zero. Without it the first grid run was NOT a ceiling: a 7x10 pen
    # measured BELOW a 5x8 pen, which is impossible for a roof -- the bigger pen contains
    # the smaller one. Non-monotonic capacity is the signature of an unconverged
    # optimiser, and reporting it as a ceiling would have been the whole trap.
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=steps)
    for _ in range(steps):
        xy, w = pen(raw, strokes, points, pressure)
        g = enc.gist(ink(xy, w))
        loss = -(g * cent).sum(-1).mean()
        opt.zero_grad()
        loss.backward()
        opt.step()
        sched.step()
    with torch.no_grad():
        xy, w = pen(raw, strokes, points, pressure)
        img = ink(xy, w)
        g = enc.gist(img)
        cos = float((g * cent).sum(-1).mean())
        hit = float(((g @ cent.T).argmax(1) ==
                     torch.arange(n, device=dev)).float().mean())
        marks = penmarks(img, xy, w)
    return cos, hit, img, marks


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Measure the pen's ceiling before climbing.")
    ap.add_argument("--eye", default=os.path.join(HERE, "..", "eye", "state", "eye.pt"))
    ap.add_argument("--data", default=os.path.join(HERE, "..", "eye", "corpus",
                                                   "letters.npz"))
    ap.add_argument("--steps", type=int, default=2000)
    ap.add_argument("--lr", type=float, default=3e-2)
    ap.add_argument("--seeds", type=int, default=3,
                    help="Adam on 2000 random numbers finds a different local roof each "
                         "time. Best of N, reported with the spread, or the number is a "
                         "coin flip dressed as a measurement.")
    ap.add_argument("--out", default=os.path.join(HERE, "state", "ceiling.json"))
    ap.add_argument("--png", default=os.path.join(HERE, "ceiling.npz"))
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    a = ap.parse_args(argv)

    dev = torch.device(a.device)
    enc = load_eye(a.eye, dev)
    d = np.load(a.data)
    cent, cls = centroids(enc, d["X"].astype(np.float32), d["y"], dev)
    print("ceiling of the pen — %d letters, Adam %d steps, best of %d seeds\n"
          % (len(cls), a.steps, a.seeds))
    print("  strokes points press |    cos    (spread)   eye reads | pieces stub cover")
    print("  " + "-" * 76)

    rows, best_img = [], {}
    for (s, p, pr) in GRID:
        runs = [roof(enc, cent, s, p, pr, a.steps, a.lr, 1933 + 7 * i, dev)
                for i in range(a.seeds)]
        cos, hit, img, marks = max(runs, key=lambda r: r[0])
        spread = max(r[0] for r in runs) - min(r[0] for r in runs)
        pieces = float(np.mean([m["pieces"] for m in marks]))
        stub = float(np.mean([m["stub"] for m in marks]))
        cover = float(np.mean([m["cover"] for m in marks]))
        key = "%dx%d%s" % (s, p, "P" if pr else "")
        rows.append({"strokes": s, "points": p, "pressure": pr, "cos": cos,
                     "spread": spread, "eye_reads_back": hit, "pieces": pieces,
                     "stub": stub, "cover": cover,
                     "numbers_per_letter": s * p * (3 if pr else 2)})
        best_img[key] = img.cpu().numpy()
        print("  %7d %6d %6s | %.4f  (%.4f)   %5.1f%%   | %5.2f  %.2f  %.3f"
              % (s, p, "yes" if pr else "-", cos, spread, 100 * hit,
                 pieces, stub, cover), flush=True)

    base = [r for r in rows if r["strokes"] == 3 and r["points"] == 6
            and not r["pressure"]][0]["cos"]
    top = max(rows, key=lambda r: r["cos"])
    print("\n  the 3x6 fixed-nib control measured %.4f (the record says 0.446)" % base)
    print("  the roof moved to %.4f with %d strokes x %d points%s  (+%.1f%%)"
          % (top["cos"], top["strokes"], top["points"],
             " and pressure" if top["pressure"] else "",
             100 * (top["cos"] - base) / base))
    np.savez_compressed(a.png, **best_img)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump({"rows": rows, "control_3x6": base, "steps": a.steps, "seeds": a.seeds},
              open(a.out, "w"), indent=1)
    print("  drawings of every ceiling -> %s" % a.png)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
