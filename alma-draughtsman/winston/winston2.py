"""WINSTON 2 -- the painter that DESCRIBES instead of remembering.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

## The finding this file answers (2026-09-05)

`winston-forever-v2` paints its own corpus beautifully -- 18x better than a flat colour --
and on a photograph it has never seen it is WORSE than a flat colour. It had not learned
to paint. It had learned 84 photographs.

MEASURED, on the live checkpoint, three ways that agree:

  1. The trunk's feature map before the pool is 256 x 16 x 16 = 65,536 numbers, and a
     leave-one-out linear probe reads an 8x8 thumbnail out of it at R^2 0.9997. The
     description is THERE. `AdaptiveAvgPool2d(1)` then throws away all 256 spatial cells
     and keeps 256 numbers, and the same probe drops to R^2 0.4953.
  2. Spend that SAME budget of 256 numbers on layout instead of channels and the
     description comes back: 64ch x 2x2 -> 0.6017, 16ch x 4x4 -> 0.6548. It was never
     about how many numbers the bottleneck has. It is about the pool.
  3. Behaviourally: shown an unseen photograph, the old painter's painting is CLOSER to
     the corpus photograph whose code is nearest (mse 0.07190) than to the photograph it
     was actually looking at (0.07797). It paints somebody else.

## The fix, and why this shape

Do not pool. Read the strokes out of the feature map WHERE THEY ARE.

The canvas is a pyramid of grids -- 4x4, 8x8, 16x16. Each cell of each grid gets its own
small handful of strokes, predicted by a 1x1 convolution from THAT CELL's feature vector,
and anchored at that cell's centre with a bounded local spread. So:

  * a stroke's position comes from WHERE in the picture it was decided, not from a global
    code. That is the whole difference between describing and recognising.
  * the readout is translation-equivariant and shared across cells, so what the painter
    learns about an edge in one corner it already knows about an edge in the other. This
    is the property that makes an unseen photograph paintable at all.
  * coarse grid -> broad strokes, fine grid -> fine strokes, which is the coarse-to-fine
    ramp winston already had, now grounded in space instead of in stroke index.
  * most of the old net was the 256 -> 12,800 expansion, which is the memory itself.

**The renderer is untouched.** The grid painter emits its anchors in exactly the logit
space `decode` already expects (the tanh and the atanh cancel algebraically), so
`decode`, `composite`, `render` and `render_big` are imported from winston.py and run
bit-for-bit as before. The 4K path, the collapse guard and every floor still apply.

## The honest test

`--holdout N` splits the photographs before training and never lets the painter see the
held-out ones. Every run reports BLANK / PAINTER / BLUR, CHROMA and the BUSY tenth on the
training photographs AND on the held-out ones, and on any `--extra` outsider. A painter
that beats BLANK on its own corpus and loses to it on a held-out photograph has not
learned to paint, and this file exists to say so out loud when that happens.

    python winston2.py --train <folder> --arch grid --holdout 13 --extra sderot_src.jpg
    python winston2.py --train <folder> --arch pool --holdout 13   # the old net, same test
"""
from __future__ import annotations

import argparse
import copy
import glob
import os
import time

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from winston import (PARAMS, POINTS, Painter, busy_error, chroma, collapse_signature,
                     colour_life, detail, floors, load, render, render_big)

ANCHOR_SCALE = 0.95          # decode(): anchor = tanh(raw) * 0.95. We invert exactly this.


def images_in(folder: str):
    """Every photograph in the folder -- CASE-INSENSITIVELY.

    SCAR, measured 2026-09-05: winston.py globs "*.jpg", "*.jpeg", "*.png". On Linux that
    is case-sensitive, so the 9 files named "*.JPG" in trainset-iddo-alma-v2 were silently
    dropped and the "93 photograph" corpus that has been training since 09-02 is 84. Nine
    of Iddo's family photographs have never been seen by the running painter. Fixed here;
    the eran4 file is deliberately NOT edited while it is mid-cycle."""
    seen, out = set(), []
    for p in sorted(glob.glob(os.path.join(folder, "**", "*"), recursive=True)):
        if os.path.splitext(p)[1].lower() in (".jpg", ".jpeg", ".png") and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def plan_grids(strokes: int, grids=(4, 8, 16)):
    """How many strokes each grid cell gets, so the total covers `strokes`.

    An equal share per scale, rounded to whole strokes per cell, with the finest grid
    absorbing the remainder. Ordered coarse first, because decode() reads stroke index as
    brush size (2.6 -> 0.55) and compositing is back to front: the broad underpainting
    must be laid down first and lie underneath, exactly as on a real easel."""
    share = max(1, strokes // len(grids))
    plan = [[g, max(1, int(round(share / (g * g))))] for g in grids]
    while sum(g * g * k for g, k in plan) < strokes:      # never short-change the budget
        plan[-1][1] += 1
    return [(g, k) for g, k in plan]


class PainterGrid(nn.Module):
    """Look at the picture; say how to paint it -- one patch at a time.

    The trunk is winston's own encoder with the pool removed, so the comparison against
    the old net is a comparison of the READOUT and nothing else."""

    def __init__(self, strokes: int = 800, d: int = 256, grids=(4, 8, 16), seed: int = 1933):
        super().__init__()
        self.n = strokes
        self.plan = plan_grids(strokes, grids)
        self.see = nn.Sequential(
            nn.Conv2d(3, 32, 4, 2, 1), nn.GELU(),
            nn.Conv2d(32, 64, 4, 2, 1), nn.GELU(),
            nn.Conv2d(64, 128, 4, 2, 1), nn.GELU(),
            nn.Conv2d(128, 256, 4, 2, 1), nn.GELU())
        # LOCAL + GLOBAL at every grid. Measured 2026-09-05: at a 128px canvas the trunk's
        # last map is 8x8, so pooling it up to the 16x16 grid handed the fine strokes a
        # blurred copy of the coarse features and the finest scale was decorative. Each
        # grid now reads BOTH the stage-3 map (twice the resolution, smaller receptive
        # field: where the edge actually is) and the stage-4 map (the context), pooled to
        # that grid. Resolution-independent, so a checkpoint routes the same way at 128px
        # and at 4K.
        self.neck = nn.Sequential(nn.Conv2d(128 + 256, d, 1), nn.GELU(),
                                  nn.Conv2d(d, d, 1), nn.GELU())
        self.heads = nn.ModuleList([nn.Conv2d(d, k * PARAMS, 1) for _, k in self.plan])
        for h in self.heads:                 # start every stroke AT its cell centre, grey:
            nn.init.zeros_(h.bias)           # a coarse mosaic of the photograph, then learn
            h.weight.data.mul_(0.1)

        # where each stroke lives, and how far from home it may wander
        gen = torch.Generator().manual_seed(seed)
        cells, spreads = [], []
        for g, k in self.plan:
            c = (torch.arange(g, dtype=torch.float32) + 0.5) / g * 2 - 1
            cy, cx = torch.meshgrid(c, c, indexing="ij")
            xy = torch.stack([cx.reshape(-1), cy.reshape(-1)], -1)        # (g*g, 2)
            # k COMPLETE PASSES over the grid, each pass in its own shuffled cell order --
            # not k copies of each cell in turn. Two reasons, both measured concerns:
            #   * the budget is truncated to exactly `strokes` at the end, and a partial
            #     final pass then costs some cells a repeat, never their only stroke. Cell-
            #     major ordering left 22% of the finest cells with no stroke at all.
            #   * decode() ramps brush width across stroke index, so a raster order would
            #     make every scale band systematically broader at the top-left. Shuffled
            #     within a pass, that variation is spatial noise instead of a gradient.
            xy = torch.cat([xy[torch.randperm(g * g, generator=gen)] for _ in range(k)])
            cells.append(xy)
            spreads.append(torch.full((xy.shape[0],), 1.2 / g))
        self.register_buffer("cell", torch.cat(cells)[:strokes])
        self.register_buffer("spread", torch.cat(spreads)[:strokes])

    def forward(self, img):                          # img (B,H,W,3), square
        z = img.permute(0, 3, 1, 2)
        c = self.see[4:6](self.see[2:4](self.see[0:2](z)))           # stage 3: /8, 128ch
        e = self.see[6:8](c)                                        # stage 4: /16, 256ch
        b, outs = img.shape[0], []
        for (g, k), head in zip(self.plan, self.heads):
            f = self.neck(torch.cat([F.adaptive_avg_pool2d(c, g),
                                     F.adaptive_avg_pool2d(e, g)], 1))
            o = head(f)                                              # (B, k*PARAMS, g, g)
            o = o.view(b, k, PARAMS, g * g).permute(0, 3, 1, 2)      # (B, g*g, k, PARAMS)
            outs.append(o.reshape(b, g * g * k, PARAMS))
        p = torch.cat(outs, 1)[:, :self.n]
        # Anchor the stroke to its own cell. decode() will compute tanh(raw)*0.95, so we
        # hand it the exact atanh of the anchor we want: the two cancel, the gradient is
        # d(anchor)/d(head) = spread * (1 - tanh^2), and NOTHING in the renderer changes.
        want = (self.cell + torch.tanh(p[..., :2]) * self.spread[:, None]).clamp(-0.94, 0.94)
        raw = torch.atanh(want / ANCHOR_SCALE)
        return torch.cat([raw, p[..., 2:]], -1)


def build(arch: str, strokes: int, grids):
    return PainterGrid(strokes, grids=grids) if arch == "grid" else Painter(strokes)


def augment(x):
    """Flip, zoom and shift the training photograph. Input and target move together --
    the painter paints what it is shown, so this is not label noise, it is more pictures.

    Why it belongs with the grid readout and not with the pool. 78 photographs is a tiny
    corpus and the pooled net answered that by memorising them. A translation-equivariant
    readout can actually USE a shifted copy: the same patch appearing in a different cell
    is a new example for weights that are shared across cells. Under a global average pool
    a shifted copy is nearly the same code, so it teaches almost nothing. Measured
    separately in the A/B, so the readout and the augmentation are never confused."""
    b = x.shape[0]
    z = x.permute(0, 3, 1, 2)
    dev = x.device
    flip = torch.where(torch.rand(b, device=dev) < 0.5, -1.0, 1.0)
    s = 0.70 + 0.30 * torch.rand(b, device=dev)                 # keep 70-100% of the frame
    t = (1 - s).unsqueeze(1) * (2 * torch.rand(b, 2, device=dev) - 1)
    th = torch.zeros(b, 2, 3, device=dev)
    th[:, 0, 0] = s * flip
    th[:, 1, 1] = s
    th[:, :, 2] = t
    grid = F.affine_grid(th, z.shape, align_corners=False)
    return F.grid_sample(z, grid, mode="bilinear", padding_mode="reflection",
                         align_corners=False).permute(0, 2, 3, 1)


@torch.no_grad()
def report(tag, net, X, strokes, size, chunk):
    """The floors, on this set of photographs, whichever way they go."""
    if len(X) == 0:
        return None
    blank, blur, side = floors(X, strokes, size)
    Y = torch.cat([render(net(X[i:i + 8]), size=size, chunk=chunk)
                   for i in range(0, len(X), 8)])
    P = torch.cat([net(X[i:i + 8]) for i in range(0, len(X), 8)])
    mse = float(F.mse_loss(Y, X))
    flat = X.mean(dim=(1, 2), keepdim=True).expand_as(X)
    bz, bzb = busy_error(Y, X, detail(X)), busy_error(flat, X, detail(X))
    cs, cp = chroma(X), chroma(Y)
    pin = float((P[..., POINTS * 2 + 1:].abs() > 8).float().mean())
    print("  [%s] n=%d  BLANK %.5f | PAINTER %.5f | BLUR %.5f   (x%.2f vs BLANK, "
          "x%.2f vs BLUR)" % (tag, len(X), blank, mse, blur, blank / max(mse, 1e-9),
                              blur / max(mse, 1e-9)))
    print("  [%s] CHROMA source %.3f | painted %.3f (x%.2f) | colour logits pinned %.1f%%"
          % (tag, cs, cp, cp / max(cs, 1e-3), 100 * pin))
    print("  [%s] BUSY tenth: PAINTER %.5f vs BLANK %.5f   %s"
          % (tag, bz, bzb, "<- subject kept" if bz < bzb else "<- THE SUBJECT WAS SOLD"))
    print("  [%s] %s" % (tag, "PASSES: beats a flat colour." if mse < blank else
                         "FAILS: worse than one flat colour. Smearing, not painting."))
    return {"blank": blank, "painter": mse, "blur": blur, "busy": bz, "busy_blank": bzb,
            "chroma_src": cs, "chroma_paint": cp, "pinned": pin, "n": len(X)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="A painter that must beat a flat colour on a "
                                             "photograph it has never seen.")
    ap.add_argument("--train", required=True, help="folder of photographs")
    ap.add_argument("--arch", default="grid", choices=("grid", "pool"),
                    help="grid = spatial readout (the fix); pool = the old global-average "
                         "bottleneck, for an honest A/B under an identical protocol.")
    ap.add_argument("--grids", default="4,8,16", help="stroke pyramid, coarse first")
    ap.add_argument("--holdout", type=int, default=0,
                    help="photographs held back and NEVER trained on. The acceptance test.")
    ap.add_argument("--extra", default="", help="outsider image(s), comma separated")
    ap.add_argument("--out", default="out")
    ap.add_argument("--strokes", type=int, default=800)
    ap.add_argument("--size", type=int, default=256)
    ap.add_argument("--steps", type=int, default=2000)
    ap.add_argument("--lr", type=float, default=5e-4)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--chunk", type=int, default=16)
    ap.add_argument("--detail-w", type=float, default=3.0)
    ap.add_argument("--colour-w", type=float, default=2.5)
    ap.add_argument("--logit-cap", type=float, default=12.0)
    ap.add_argument("--guard", action="store_true")
    ap.add_argument("--guard-every", type=int, default=100)
    ap.add_argument("--recompute", action="store_true")
    ap.add_argument("--aug", action="store_true",
                    help="flip/zoom/shift the training photographs. 78 pictures is a tiny "
                         "corpus; this is more pictures, not a different task.")
    ap.add_argument("--resume", default="")
    ap.add_argument("--render", type=int, default=0)
    ap.add_argument("--seed", type=int, default=1933)
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    a = ap.parse_args(argv)

    dev = torch.device(a.device)
    torch.manual_seed(a.seed)
    grids = tuple(int(t) for t in a.grids.split(","))

    paths = images_in(a.train)
    if not paths:
        print("no photographs found")
        return 2
    rng = np.random.RandomState(a.seed)                 # the SAME split for every arch
    idx = rng.permutation(len(paths))
    hold = [paths[i] for i in idx[:a.holdout]]
    keep = [paths[i] for i in idx[a.holdout:]]
    print("photographs: %d total -> %d train, %d HELD OUT (never seen)"
          % (len(paths), len(keep), len(hold)))
    for h in hold:
        print("    held out: %s" % os.path.basename(h))

    X = torch.as_tensor(np.stack([load(p, a.size) for p in keep]), device=dev)
    H = (torch.as_tensor(np.stack([load(p, a.size) for p in hold]), device=dev)
         if hold else torch.zeros(0, a.size, a.size, 3, device=dev))
    extras = [e for e in a.extra.split(",") if e.strip()]
    E = (torch.as_tensor(np.stack([load(e, a.size) for e in extras]), device=dev)
         if extras else torch.zeros(0, a.size, a.size, 3, device=dev))

    net = build(a.arch, a.strokes, grids).to(dev)
    npar = sum(p.numel() for p in net.parameters())
    print("arch %s: %d strokes, %.2fM parameters%s, aug %s"
          % (a.arch, a.strokes, npar / 1e6,
             ", pyramid " + str(net.plan) if a.arch == "grid" else "",
             "ON" if a.aug else "off"))
    if a.resume and os.path.isfile(a.resume):
        ck = torch.load(a.resume, map_location=dev, weights_only=False)
        net.load_state_dict(ck["net"])
        print("  resumed from %s" % a.resume)

    blank, blur, side = floors(X, a.strokes, a.size)
    print("  train BLANK %.5f   BLUR %.5f (%dx%d grid)" % (blank, blur, side, side))

    opt = torch.optim.AdamW(net.parameters(), lr=a.lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, a.lr, total_steps=a.steps, pct_start=0.15)
    t0, rollbacks, snap_step, was_painting = time.time(), 0, 0, False
    snap = {"net": {k: v.detach().clone() for k, v in net.state_dict().items()},
            "opt": copy.deepcopy(opt.state_dict())}

    for step in range(1, a.steps + 1):
        i = torch.randint(0, len(X), (min(a.batch, len(X)),), device=dev)
        x = augment(X[i]) if a.aug else X[i]
        soft = max(1.0, 6.0 * (1 - step / a.steps) ** 2 + 1.0)
        n_act = max(1, min(a.strokes, int(round(
            a.strokes * (0.3 + 0.7 * step / (0.55 * a.steps))))))
        p = net(x)
        y = render(p[:, :n_act], size=a.size, soft=soft, chunk=a.chunk,
                   n_total=a.strokes, recompute=a.recompute)
        w = detail(x)
        loss = (F.mse_loss(y, x) + a.detail_w * (((y - x) ** 2) * w).mean()
                + a.colour_w * (n_act / a.strokes) * colour_life(y, x))
        if a.logit_cap > 0:
            loss = loss + 1e-2 * (F.relu(p.abs() - a.logit_cap) ** 2).mean()
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(net.parameters(), 1.0)
        opt.step()
        sched.step()

        if a.guard and (step % a.guard_every == 0 or step == a.steps):
            with torch.no_grad():
                xg = X[:16]
                pg = net(xg)
                yg = render(pg, size=a.size, chunk=a.chunk)
                dead, why, _, _ = collapse_signature(pg, yg, xg, blank, was_painting)
                if not dead and float(F.mse_loss(yg, xg)) < blank:
                    was_painting = True
            if dead:
                rollbacks += 1
                print("  GUARD step %5d: COLLAPSE (%s) -> rollback to %d, lr halved (#%d)"
                      % (step, why, snap_step, rollbacks), flush=True)
                net.load_state_dict(snap["net"])
                opt.load_state_dict(snap["opt"])
                for g_ in opt.param_groups:
                    for key in ("lr", "max_lr", "initial_lr", "min_lr"):
                        if key in g_:
                            g_[key] = g_[key] * 0.5
            else:
                snap = {"net": {k: v.detach().clone() for k, v in net.state_dict().items()},
                        "opt": copy.deepcopy(opt.state_dict())}
                snap_step = step

        if step % max(1, a.steps // 10) == 0 or step == a.steps:
            with torch.no_grad():
                tr = float(F.mse_loss(render(net(X[:16]), size=a.size, chunk=a.chunk), X[:16]))
                ho = (float(F.mse_loss(render(net(H[:16]), size=a.size, chunk=a.chunk), H[:16]))
                      if len(H) else float("nan"))
            print("  step %5d  train mse %.5f   HELD-OUT mse %.5f   (%.0fs)"
                  % (step, tr, ho, time.time() - t0), flush=True)

    os.makedirs(a.out, exist_ok=True)
    net.eval()
    print("\n================ THE HONEST TEST ================")
    r_tr = report("TRAIN   ", net, X, a.strokes, a.size, a.chunk)
    r_ho = report("HELD-OUT", net, H, a.strokes, a.size, a.chunk)
    for k, e in enumerate(extras):
        report("OUTSIDER %s" % os.path.basename(e)[:18], net, E[k:k + 1], a.strokes,
               a.size, a.chunk)
    if r_ho:
        print("\nVERDICT: held-out PAINTER %.5f vs BLANK %.5f -> %s"
              % (r_ho["painter"], r_ho["blank"],
                 "GENERALISES (x%.2f better than a flat colour)"
                 % (r_ho["blank"] / r_ho["painter"]) if r_ho["painter"] < r_ho["blank"] else
                 "DOES NOT GENERALISE. It is still remembering, not painting."))
    if a.guard:
        print("GUARD: %d rollback(s)" % rollbacks)

    from PIL import Image
    with torch.no_grad():
        for tag, S in (("train", X), ("heldout", H)):
            if len(S) == 0:
                continue
            Y = render(net(S[:6]), size=a.size, chunk=a.chunk)
            for k in range(min(6, len(S))):
                pair = np.concatenate([S[k].cpu().numpy(), Y[k].cpu().numpy()], axis=1)
                Image.fromarray((pair * 255).astype(np.uint8)).save(
                    os.path.join(a.out, "%s-%02d.png" % (tag, k)))
    torch.save({"net": net.state_dict(), "strokes": a.strokes, "size": a.size,
                "arch": a.arch, "grids": grids,
                "holdout": [os.path.basename(h) for h in hold]},
               os.path.join(a.out, "painter.pt"))
    if a.render and len(H):
        with torch.no_grad():
            big = render_big(net(H[:1]), a.render, chunk=max(4, a.chunk // 4))[0].cpu().numpy()
        Image.fromarray((big * 255).astype(np.uint8)).save(
            os.path.join(a.out, "heldout-%dpx.png" % a.render))
    print("-> %s" % a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
