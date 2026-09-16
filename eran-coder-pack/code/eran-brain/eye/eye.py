"""ERAN'S EYE — an I-JEPA encoder that lands in the ear's gist space.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

Iddo, 2026-08-30: *"תבנה עין... הולובריין - זוכר?"* and then *"עכשיו אפשר לעשות מולטי מודאלי."*

## Why JEPA and not a classifier

A classifier trained on 22 labels learns to answer a question nobody asked ERAN. The
holobrain note is explicit -- **predict the GIST, not the surface** -- so this is
I-JEPA: hide most of the retina, and from what is still visible predict the *embedding*
of the hidden parts. No pixels are reconstructed and no label is used. The labels exist
in this file for one purpose only: to MEASURE afterwards whether letters separated on
their own. A number that trains nothing cannot flatter itself.

## Why 192 dimensions

Not an arbitrary choice. The ear's representation is `legacy192` -- a 192-d L2-normalised
cochlear vector, the block the judge weights x12. The eye emits the same shape into the
same space, so a letter's SHAPE and a letter's SOUND can land in one place. That is the
whole point of the holobrain, and getting the number wrong would quietly make the two
senses live in separate rooms forever.

## Movable, like Colibri

Iddo: *"אפשר לעבור עם חלק מהמוח או כולו כמו קוליברי."* Nothing here pins itself to a host.
`--device` picks cuda or cpu, the checkpoint is a plain state_dict, and the encoder can be
lifted to another box mid-life. The eye is a tier, not a resident.

    python eye.py --data corpus/letters.npz --steps 4000 --device cuda
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "murphy"))
try:                                                            # noqa: E402
    from murphy import watch
except Exception:                                               # noqa: BLE001
    # Murphy rules on runs; he must never be the reason one dies. He is not installed on
    # every box, and an import error in the judge silently costing a night of training on
    # the fleet is precisely the kind of failure he exists to catch.
    def watch(*_a, **_k):
        return None

GIST = 192              # the ear's legacy192. Do not change without changing the ear.
PATCH = 8
SIZE = 64
NP = (SIZE // PATCH) ** 2       # 64 patches
CH = 3                          # ink and paper, from 2026-08-31

# WHY THE EYE HAD TO CHANGE FIRST. Iddo: *"אני רוצה שילמד צבעים לא רק שחור לבן."* The
# hand cannot learn colour while its judge is colourblind -- give Winston a colour output
# and he learns it from noise, because nothing can tell him he was wrong. So colour enters
# the system HERE, in what the eye is shown, and the hand follows.


class Blocks(nn.Module):
    """A small transformer stack. Small on purpose: the subject is one letter."""

    def __init__(self, d, depth, heads):
        super().__init__()
        self.layers = nn.ModuleList([
            nn.TransformerEncoderLayer(d, heads, d * 4, dropout=0.0,
                                       batch_first=True, norm_first=True,
                                       activation="gelu")
            for _ in range(depth)])
        self.norm = nn.LayerNorm(d)

    def forward(self, x):
        for l in self.layers:
            x = l(x)
        return self.norm(x)


class Encoder(nn.Module):
    def __init__(self, d=192, depth=6, heads=6):
        super().__init__()
        self.proj = nn.Linear(PATCH * PATCH * CH, d)
        self.pos = nn.Parameter(torch.zeros(1, NP, d))
        nn.init.trunc_normal_(self.pos, std=0.02)
        self.blocks = Blocks(d, depth, heads)

    def patchify(self, img):                  # (B,64,64,3) -> (B, 64 patches, 8*8*3)
        b = img.shape[0]
        x = img.permute(0, 3, 1, 2)           # channels first, so a patch keeps its colour
        x = x.unfold(2, PATCH, PATCH).unfold(3, PATCH, PATCH)   # (B,3,8,8,P,P)
        x = x.permute(0, 2, 3, 1, 4, 5)                          # (B,8,8,3,P,P)
        return x.reshape(b, NP, CH * PATCH * PATCH)

    def forward(self, img, keep=None):
        x = self.proj(self.patchify(img)) + self.pos
        if keep is not None:
            x = torch.gather(x, 1, keep.unsqueeze(-1).expand(-1, -1, x.shape[-1]))
        return self.blocks(x)

    def pooled(self, img):
        """Pool the patch embeddings, WEIGHTED BY INK -- before normalising.

        The plain mean was wrong for this retina. A letter covers ~4% of the frame, so
        averaging all 64 patches averages sixty patches of blank paper and four of
        letter: the signal is divided by sixteen before it ever leaves the encoder.
        """
        t = self.forward(img)
        w = patch_ink(img).unsqueeze(-1) + 0.02      # floor: never divide by zero
        return (t * w).sum(1) / w.sum(1)

    def gist(self, img):
        """The one vector the rest of ERAN sees. L2-normalised, like the ear's."""
        return F.normalize(self.pooled(img), dim=-1)


class Predictor(nn.Module):
    """Given the visible context and WHERE a hidden patch is, guess its embedding."""

    def __init__(self, d=192, depth=3, heads=6):
        super().__init__()
        self.mask_tok = nn.Parameter(torch.zeros(1, 1, d))
        nn.init.trunc_normal_(self.mask_tok, std=0.02)
        self.pos = nn.Parameter(torch.zeros(1, NP, d))
        nn.init.trunc_normal_(self.pos, std=0.02)
        self.blocks = Blocks(d, depth, heads)

    def forward(self, ctx, tgt_idx):
        b, n = tgt_idx.shape
        q = self.mask_tok.expand(b, n, -1) + torch.gather(
            self.pos.expand(b, -1, -1), 1,
            tgt_idx.unsqueeze(-1).expand(-1, -1, self.pos.shape[-1]))
        return self.blocks(torch.cat([ctx, q], 1))[:, -n:]


BLOCK = 4          # 4x4 patches = a QUARTER of the retina, 32x32 pixels


def masks(b, n_keep, n_tgt, device, gen, ink=None):
    """Hide one big CONTIGUOUS block over the letter, and predict it from the rest.

    This is the third attempt and the first one that asks a hard question.

    Attempt 1 scattered the hidden patches at random over a retina that is 96% blank:
    prediction loss 0.0007 by step 250, nothing learned.
    Attempt 2 aimed the scattered patches at the ink. Better, but the loss still fell to
    0.002 -- because **an 8x8 patch surrounded by its own neighbours can be guessed by
    local interpolation.** Stroke thickness and greyness are enough. Shape is never
    needed, so shape is never learned. Letters separated 5.6% where raw pixels separate
    66.9%: the encoder was measurably destroying what the image handed it for free.

    So: one contiguous BLOCK x BLOCK block, placed where the ink is densest. Its inner
    patches are two patches away from anything visible, and no amount of local texture
    reaches them. To fill that hole the encoder has to know **what letter this is.**
    That is I-JEPA's actual mechanism, and leaving it out was the whole bug.
    """
    g = SIZE // PATCH                                   # 8 patches across
    r = torch.rand(b, NP, device=device, generator=gen)
    if ink is None:
        order = r.argsort(dim=1)
        return order[:, :n_keep].sort(dim=1).values, order[:, n_keep:n_keep + n_tgt]
    span = g - BLOCK + 1
    k = torch.ones(1, 1, BLOCK, BLOCK, device=device)
    dens = F.conv2d(ink.view(b, 1, g, g), k).view(b, span * span)
    dens = dens + 0.4 * r[:, :span * span]              # jitter, so it is not always the same corner
    pos = dens.argmax(1)
    r0, c0 = pos // span, pos % span
    d = torch.arange(BLOCK, device=device)
    tgt = ((r0[:, None] + d)[:, :, None] * g +
           (c0[:, None] + d)[:, None, :]).reshape(b, BLOCK * BLOCK)
    keep = r.scatter(1, tgt, -1.0).topk(n_keep, dim=1).indices.sort(dim=1).values
    return keep, tgt


def patch_ink(img):
    """How much of each patch is LETTER rather than paper. (B, NP)

    On a colour page this is no longer "how bright". Ink is darker than paper whatever
    colour either of them is, so the measure is how far each pixel falls below the
    brightest thing in its own image -- which works for black ink on white, and equally
    for vermilion on kraft.
    """
    b = img.shape[0]
    lum = img.mean(-1)                                   # (B,64,64)
    top = lum.reshape(b, -1).amax(1).view(b, 1, 1)
    cover = (top - lum).clamp_min(0) / (top + 1e-6)
    x = cover.unfold(1, PATCH, PATCH).unfold(2, PATCH, PATCH)
    return x.reshape(b, NP, PATCH * PATCH).mean(-1)


def pixel_floor(X, y, device):
    """What nearest-centroid gets on RAW PIXELS. The bar the eye has to clear.

    Measured 66.9% on this corpus. Any encoder scoring below this is destroying
    information that was sitting in the image for free, and calling it a representation
    does not make it one.
    """
    Xt = torch.as_tensor(X.reshape(len(X), -1), device=device)   # colour included
    yt = torch.as_tensor(y.astype(np.int64), device=device)
    g = F.normalize(Xt, dim=-1)
    cls = sorted(set(y.tolist()))
    cent = F.normalize(torch.stack([g[yt == c].mean(0) for c in cls]), dim=-1)
    return float(((g @ cent.T).argmax(1) == yt).float().mean())


def views(img, gen, k=1.0):
    """Two looks at the SAME piece of paper. No label is used or implied.

    A random affine and a little noise -- the difference between glancing at a letter
    twice. What must stay constant across the two is exactly what a letter IS, and what
    changes (where it sits, how big, how tilted, how grainy) is exactly what it is not.
    """
    out = []
    for _ in range(2):
        b = img.shape[0]
        a = (torch.rand(b, 5, device=img.device, generator=gen) - 0.5)
        ang = a[:, 0] * 0.35 * k                              # +-10 degrees at k=1
        sc = 1.0 + a[:, 1] * 0.30 * k
        sh = a[:, 2] * 0.30 * k
        tx, ty = a[:, 3] * 0.30 * k, a[:, 4] * 0.30 * k
        cos, sin = torch.cos(ang) / sc, torch.sin(ang) / sc
        th = torch.stack([torch.stack([cos, -sin + sh, tx], 1),
                          torch.stack([sin, cos, ty], 1)], 1)
        grid = F.affine_grid(th, (b, CH, SIZE, SIZE), align_corners=False)
        v = F.grid_sample(img.permute(0, 3, 1, 2), grid, align_corners=False,
                          padding_mode="border").permute(0, 2, 3, 1)
        # padding_mode="border" and NOT zeros: zeros paints BLACK into the corners, which
        # on a coloured page is a stroke of ink that was never there -- the augmentation
        # would be teaching the eye that every letter has dark edges.
        v = v + 0.06 * k * torch.randn(v.shape, device=v.device, generator=gen)
        out.append(v.clamp(0, 1))
    return out


SHAPE_DIMS = 128        # of the 192. The rest carry colour.


def recolour(img, gen, k=1.0):
    """Same letter, different ink and paper. Destroys colour as an invariant.

    MEASURED, and this is why it exists: trained on colour pairs alone the eye went from
    94.1% on letters to 17.6%, while ink separation climbed to 67.9%. It had found the
    cheapest invariant in the picture. An ink colour is constant over the whole frame and
    survives every geometric augmentation untouched; shape has to be worked for. So the
    shape half of the gist is shown pairs whose COLOUR disagrees, and colour stops being
    an answer.
    """
    b = img.shape[0]
    lum = img.mean(-1, keepdim=True)
    top = lum.reshape(b, -1).amax(1).view(b, 1, 1, 1)
    cover = ((top - lum) / (top + 1e-6)).clamp(0, 1)          # 1 = ink, 0 = paper
    ink = torch.rand(b, 1, 1, 3, device=img.device, generator=gen) * 0.55
    paper = 0.72 + torch.rand(b, 1, 1, 3, device=img.device, generator=gen) * 0.28 * k
    return (cover * ink + (1 - cover) * paper).clamp(0, 1)


def scramble(img, gen):
    """Same page, shape wrecked. Destroys SHAPE as an invariant, leaving the pigment.

    The mirror of recolour(). Chop the retina into tiles and shuffle them: every colour
    that was on the page is still on the page, and the letter is gone. What survives is
    exactly what the colour half of the gist should be about.
    """
    b, g = img.shape[0], 8
    t = img.reshape(b, g, SIZE // g, g, SIZE // g, CH).permute(0, 1, 3, 2, 4, 5)
    t = t.reshape(b, g * g, SIZE // g, SIZE // g, CH)
    idx = torch.rand(b, g * g, device=img.device, generator=gen).argsort(1)
    t = torch.gather(t, 1, idx.view(b, g * g, 1, 1, 1).expand(-1, -1, SIZE // g,
                                                              SIZE // g, CH))
    t = t.reshape(b, g, g, SIZE // g, SIZE // g, CH).permute(0, 1, 3, 2, 4, 5)
    return t.reshape(b, SIZE, SIZE, CH)


def ink_colour(img, frac: float = 0.15):
    """What colour is the ink on this page? Read off the pixels, with no label.

    The darkest `frac` of the picture IS the ink -- that is what ink means. So the colour
    half of the gist gets a target it can regress to, computed from the image itself.

    WHY REGRESSION AND NOT CONTRAST, measured: trained contrastively the colour half
    scored 20.2% where raw pixels score 27.9% -- **worse than no encoder.** The cause is
    arithmetic, not tuning: there are 12 inks and the batch is 128, so about ten images in
    every batch share an ink, and a contrastive loss labels all of them NEGATIVE. It was
    pushing apart the very things it was being asked to call the same. A regression target
    has no negatives to get wrong.
    """
    b = img.shape[0]
    lum = img.mean(-1).reshape(b, -1)
    k = max(8, int(frac * lum.shape[1]))
    idx = lum.topk(k, dim=1, largest=False).indices             # the darkest pixels
    flat = img.reshape(b, -1, CH)
    return torch.gather(flat, 1, idx.unsqueeze(-1).expand(-1, -1, CH)).mean(1)


def nt_xent(g1, g2, tau=0.15):
    """The same letter twice must land in the same place; different paper must not.

    Chosen after the JEPA objective failed three times with a measured cause each time.
    This is not a retreat to something easier -- it is the SAME rule ERAN's ear already
    lives by: one syllable said twice has to arrive at one point in the gist space. The
    eye is now asked the visual form of the identical question, and still never told
    what a letter is.
    """
    z = torch.cat([g1, g2])
    n = g1.shape[0]
    sim = (z @ z.T) / tau
    sim.fill_diagonal_(-1e4)
    tgt = torch.cat([torch.arange(n, 2 * n), torch.arange(0, n)]).to(z.device)
    return F.cross_entropy(sim, tgt)


def evaluate(enc, X, y, device, dims=None):
    """Did letters separate BY THEMSELVES? Nearest-class-centroid in gist space.

    This never touches a gradient. It is the honest question asked of an encoder that
    was never told what a letter is: if shape carries identity, samples of one letter
    should sit closer to their own mean than to any other.
    """
    enc.eval()
    with torch.no_grad():
        g = []
        for i in range(0, len(X), 512):
            v = enc.gist(torch.as_tensor(X[i:i + 512], device=device))
            g.append(F.normalize(v[:, dims], dim=-1) if dims is not None else v)
        g = torch.cat(g)
    yt = torch.as_tensor(y.astype(np.int64), device=device)
    cls = sorted(set(y.tolist()))
    cent = F.normalize(torch.stack([g[yt == c].mean(0) for c in cls]), dim=-1)
    pred = (g @ cent.T).argmax(1)
    enc.train()
    return float((pred == yt).float().mean())


def _fingerprint(path):
    """Which corpus these weights were fitted to. Size + first-MB sha256 + X's shape.

    Without it a checkpoint and a corpus can drift apart in silence, which is exactly
    what happened between 2026-08-30 and 08-31 and left the whole holobrain chain
    unrunnable for six days with no message.
    """
    try:
        st = os.stat(path)
        h = hashlib.sha256()
        with open(path, "rb") as f:
            h.update(f.read(1024 * 1024))
        with np.load(path) as d:
            shape = [int(x) for x in d["X"].shape]
        return {"file": os.path.basename(path), "bytes": int(st.st_size),
                "sha256_first_mb": h.hexdigest(), "shape": shape}
    except Exception as e:                                           # noqa: BLE001
        return {"file": str(path), "error": repr(e)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Train ERAN's eye (I-JEPA on letters).")
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--data", default=os.path.join(here, "corpus", "letters.npz"))
    ap.add_argument("--out", default=os.path.join(here, "state"))
    ap.add_argument("--steps", type=int, default=4000)
    ap.add_argument("--batch", type=int, default=128)
    ap.add_argument("--lr", type=float, default=1.5e-3)
    ap.add_argument("--keep", type=int, default=24, help="visible patches of 64")
    ap.add_argument("--tgt", type=int, default=16, help="patches to predict")
    ap.add_argument("--ema", type=float, default=0.996)
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--holdout", type=int, default=0,
                    help="reserve this many FONTS. The eye never trains on them, and the "
                         "score you are shown is measured only on those. Any other number "
                         "is measured on what it memorised.")
    ap.add_argument("--aug", type=float, default=1.0,
                    help="how hard the two views differ. Too much destroys the letter; "
                         "too little and the eye learns where it sat on the page.")
    ap.add_argument("--mode", default="jepa", choices=["jepa", "invariance"],
                    help="jepa: predict hidden blocks. invariance: two views, one place.")
    ap.add_argument("--seed", type=int, default=1933)
    a = ap.parse_args(argv)

    torch.manual_seed(a.seed)
    dev = torch.device(a.device)
    gen = torch.Generator(device=dev).manual_seed(a.seed)
    d = np.load(a.data)
    X, y = d["X"].astype(np.float32), d["y"]
    # THE SECOND QUESTION, and it is the one that makes this honest. Adding colour could
    # buy ink recognition at the cost of letter recognition -- an eye that reads pigment
    # and forgets shape would still post a fine-looking number. Both are measured, every
    # time, against their own chance level and their own raw-pixel floor.
    ink_y = d["c"] if "c" in d else None
    Xe, ye = X, y                                     # what the score is measured on
    if a.holdout:
        f = d["f"]
        cut = int(f.max()) + 1 - a.holdout
        tr, te = f < cut, f >= cut
        X, y, Xe, ye = X[tr], y[tr], X[te], y[te]
        if ink_y is not None:
            ink_tr, ink_y = ink_y[tr], ink_y
        print("holdout: %d faces trained on (%d images), %d faces NEVER SEEN (%d images)"
              % (cut, tr.sum(), a.holdout, te.sum()))
    print("eye: %d images, %d letters, device %s" % (len(X), len(set(y.tolist())), dev))
    floor = pixel_floor(Xe, ye, dev)
    print("     LETTER: chance %.1f%%  |  raw pixels %.1f%%  <- the bar"
          % (100.0 / len(set(y.tolist())), 100 * floor))
    if ink_y is not None:
        ink_e = ink_y[te] if a.holdout else ink_y
        ink_floor = pixel_floor(Xe, ink_e, dev)
        print("     INK:    chance %.1f%%  |  raw pixels %.1f%%  <- colour has its own bar"
              % (100.0 / len(set(ink_y.tolist())), 100 * ink_floor))

    enc = Encoder().to(dev)
    # A tiny read-out head, so the gist stays the gist and does not become an RGB triple.
    colour_head = nn.Sequential(nn.Linear(GIST - SHAPE_DIMS, 64), nn.GELU(),
                                nn.Linear(64, CH)).to(dev)
    tgt_enc = Encoder().to(dev)
    tgt_enc.load_state_dict(enc.state_dict())
    for p in tgt_enc.parameters():
        p.requires_grad_(False)
    pred = Predictor().to(dev)

    opt = torch.optim.AdamW(list(enc.parameters()) + list(pred.parameters())
                            + list(colour_head.parameters()), lr=a.lr, weight_decay=0.04)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, a.lr, total_steps=a.steps,
                                                pct_start=0.15)
    Xt = torch.as_tensor(X, device=dev)
    os.makedirs(a.out, exist_ok=True)
    t0 = time.time()
    log = []

    for step in range(1, a.steps + 1):
        idx = torch.randint(0, len(Xt), (a.batch,), device=dev, generator=gen)
        img = Xt[idx]
        if a.mode == "invariance":
            v1, v2 = views(img, gen, a.aug)
            # SHAPE half: two views that also disagree on colour, so only shape survives.
            s1 = enc.gist(recolour(v1, gen))[:, :SHAPE_DIMS]
            s2 = enc.gist(recolour(v2, gen))[:, :SHAPE_DIMS]
            l_shape = nt_xent(F.normalize(s1, dim=-1), F.normalize(s2, dim=-1))
            # COLOUR half: predict the ink itself. Shape is destroyed first, so the
            # answer cannot come from the letter; the target is read off the pixels.
            sc = scramble(v1, gen)
            l_col = F.mse_loss(colour_head(enc.gist(sc)[:, SHAPE_DIMS:]),
                               ink_colour(sc)) * 8.0
            pred_loss = l_shape + l_col
            var_loss = torch.zeros((), device=dev)
            loss = pred_loss
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(enc.parameters(), 1.0)
            opt.step()
            sched.step()
            if step % 250 == 0 or step == a.steps:
                acc = evaluate(enc, Xe, ye, dev, dims=slice(0, SHAPE_DIMS))
                iacc = (evaluate(enc, Xe, ink_e, dev, dims=slice(SHAPE_DIMS, None))
                        if ink_y is not None else 0.0)
                log.append({"step": step, "pred": float(pred_loss),
                            "letter_sep": acc, "ink_sep": iacc})
                print("  step %5d  nt-xent %.4f  letters %.1f%%   ink %.1f%%   (%.0fs)"
                      % (step, float(pred_loss), 100 * acc, 100 * iacc,
                         time.time() - t0), flush=True)
            continue
        keep, tgt = masks(a.batch, a.keep, a.tgt, dev, gen, ink=patch_ink(img))
        with torch.no_grad():
            full = tgt_enc(img)
            want = torch.gather(full, 1, tgt.unsqueeze(-1).expand(-1, -1, full.shape[-1]))
            want = F.layer_norm(want, (want.shape[-1],))
        got = pred(enc(img, keep), tgt)
        pred_loss = F.smooth_l1_loss(got, want)
        # Anti-collapse, corrected. The first version of this line asked for
        # `std * sqrt(batch) >= 1` on the L2-NORMALISED gist -- and a unit vector in 192
        # dimensions has components of size ~1/sqrt(192)=0.07, so that hinge could never
        # be satisfied by any encoder that exists. It sat wide open at 0.18 for all 9000
        # steps and drove the outputs to maximum entropy: mean pairwise cosine 0.001,
        # i.e. random orthogonal directions. Letters separated 5.8% where RAW PIXELS
        # separate 66.9%. The cure for the collapse was worse than the collapse.
        # VICReg's variance term belongs on the UNNORMALISED features, target std 1.
        h = enc.pooled(img)
        std = torch.sqrt(h.var(dim=0) + 1e-4)
        var_loss = F.relu(1.0 - std).mean()
        loss = pred_loss + 0.1 * var_loss

        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(list(enc.parameters()) + list(pred.parameters()), 1.0)
        opt.step()
        sched.step()
        with torch.no_grad():                       # the target encoder trails, slowly
            m = a.ema + (1 - a.ema) * (step / a.steps)
            for q, k in zip(enc.parameters(), tgt_enc.parameters()):
                k.mul_(m).add_(q.detach(), alpha=1 - m)

        if step % 250 == 0 or step == a.steps:
            acc = evaluate(enc, Xe, ye, dev)
            log.append({"step": step, "pred": float(pred_loss),
                        "var": float(var_loss), "letter_sep": acc})
            print("  step %5d  pred %.4f  var %.4f  letters separate %.1f%%  (%.0fs)"
                  % (step, float(pred_loss), float(var_loss), 100 * acc,
                     time.time() - t0), flush=True)

    # ZIV-14, 2026-09-06: eye.pt used to store exactly encoder/gist_dim/size/patch/note.
    # Downstream, close_loop.py printed "typefaces N-M (the eye ENCODER and the binding
    # never saw them)" -- a claim about THIS checkpoint that this checkpoint had no way
    # to support: --holdout defaults to 0, which trains on every face. And the corpus it
    # was trained on was overwritten on 2026-08-31, so even the font indices could not be
    # checked afterwards. Both facts now travel WITH the weights.
    if not a.holdout:
        print("!! --holdout is 0: this eye trains on ALL typefaces. Nothing downstream "
              "may claim the ENCODER never saw a held-out face, and eye.pt will say so.")
    torch.save({"encoder": enc.state_dict(), "gist_dim": GIST, "size": SIZE,
                "patch": PATCH, "channels": CH, "holdout": int(a.holdout),
                "corpus": _fingerprint(a.data), "args": vars(a),
                "trained_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "note": "L2-normalised gist, shares the ear's legacy192 space"},
               os.path.join(a.out, "eye.pt"))
    json.dump({"log": log, "args": vars(a), "chance": 1.0 / len(set(y.tolist()))},
              open(os.path.join(a.out, "eye-train.json"), "w"), indent=1)
    print("\nsaved %s" % os.path.join(a.out, "eye.pt"))
    last = log[-1]["letter_sep"] if log else 0.0
    print("chance %.1f%%  |  raw pixels %.1f%%  |  the eye %.1f%%   %s"
          % (100.0 / len(set(y.tolist())), 100 * floor, 100 * last,
             "PASSES" if last > floor else "FAILS -- worse than no encoder at all"))

    # MURPHY. Iddo, 2026-08-30: *"שאף ריצה לא תדווח בלי פסק שלו."* Three of the four
    # self-fooling runs of that day were THIS script, and all three are in his acceptance
    # test. He now reads every run of it before anyone else does.
    #
    # judge_in_loop is FALSE here and the reason matters: `evaluate` scores by
    # nearest-class-centroid against the LETTER LABELS, and no label ever touches a
    # gradient in this file. The ruler is outside the thing being measured. That is the
    # opposite of what the hand does, and it is why the hand needs the circularity
    # witness and the eye does not.
    watch({"chance": 1.0 / len(set(y.tolist())), "baseline": floor,
           "held_out": bool(a.holdout), "claimed_success": last > floor,
           "judge_in_loop": False, "objective_by": a.mode,
           "judge": "nearest-class-centroid on labels that train nothing",
           "artifact": None, "looked_at": False, "independent": True,
           "steps": [{"step": e["step"], "metric": e["letter_sep"],
                      "terms": {"pred": e["pred"], "var": e["var"]}} for e in log]},
          name="ERAN's eye, mode=%s, holdout=%d faces" % (a.mode, a.holdout))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
