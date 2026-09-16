"""WINSTON — ERAN'S IMAGINER. One organ, and this is it.

Iddo, 2026-08-31: *"הצייר הוא ווינסטון, הוא המדמה של ערן."* Said after I had split one
thing into three and given his name to a filter. He is right and the split was mine: the
imaginer is ONE faculty. Drawing a letter from memory and painting what is in front of him
are two things the SAME organ does, not two organs.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

Iddo, 2026-08-31 02:00: *"תבנה מודל נוירוני... בתור רשת נוירונים יא דפקט."*

He is right and the correction is mine to own. `alma-draughtsman/winston.py` — the thing
that drew Alma z"l tonight — **is not a neural network.** It is Canny edges, contour
following and a stroke renderer: no weights, no training, it cannot get better and it
cannot learn colour. It looked like a drawing, so it passed. That is exactly the smoke he
has been cutting through all night.

## What this is instead

A network that **looks at a picture and decides how to paint it**:

    image (3xSxS) -> encoder -> N strokes, each with
                                     6 control points   (where the hand goes)
                                     a width            (how hard it presses)
                                     an RGB colour      (what it loaded on the brush)
              -> DIFFERENTIABLE renderer -> a painting -> compared with the original

Because the renderer is differentiable end to end, the loss on the finished painting
reaches all the way back to "where should the third stroke start". Nothing is traced. The
strokes are a **decision the network makes**, and colour is a thing it must choose — which
is the whole point, and the thing the filter could never do.

## The floors, so this cannot flatter itself

Reconstruction error alone always looks impressive, because a canvas the average colour of
the photograph already scores well. So every run reports three numbers:

    BLANK      the best single flat colour           <- must be beaten, or nothing happened
    BLUR       the image at the stroke budget's own grid resolution, upsampled
               <- NOT a ceiling. Measured 2026-08-31: curved strokes beat it 4-7x,
                  because a curve says more than a grid cell. It is the reference for
                  how much the curves are buying.
    PAINTER    what the network actually did

A painter that does not beat BLANK is doing nothing. The BUSY tenth -- error in the most
structured tenth of the pixels, the number that catches a vanished person -- is printed in
the final verdict too, because on 08-31 a run said PASSES while the walking people were
gone. All the numbers are printed every time, whichever way they go.

## The colour upgrade (2026-08-31)

The first trained WINSTON passed his floors and was still ugly, in exact, measured ways:
120 flat-width strokes at 64px painted the Sderot boulevard as one pale tangle (the
walking people gone entirely), and every colour drifted to washed grey-beige -- because
MSE pays a stroke that straddles two colours to choose their average. Three corrections,
each aimed at one measured defect:

    coarse-to-fine   stroke index now means brush size: early strokes get a broad brush
                     (the underpainting), late strokes a fine one (the detail), and
                     training opens the fine strokes gradually. Before this, fat blobs
                     and fine lines fought for the same job and the blobs won.
    colour life      a hinge on region chroma: the painting may not be LESS saturated
                     than the photograph. Only under-saturation is charged -- inventing
                     colour that is not there stays expensive through the MSE. No
                     perceptual network, nothing hidden: one subtraction, one hinge.
    real defaults    400 strokes on a 128px canvas. 120 strokes at 64px is a measured
                     toy: it beat BLANK and lost the people.

## The measure (2026-09-01) -- the part that had no floor at all

The 24/7 gallery run held 69 GB of eran3's GPU for 17.7 hours, wrote nothing (torch.save
sat after a 30,000-step loop), and reported mse 0.07731 against its own BLANK floor of
0.04997 -- worse than one flat colour. Worse than that: `--train` used the same folder as
train AND as test, so that number WAS the ceiling. A run fitted on its own test set,
losing to a flat colour, cannot be rescued by more steps.

So before the learner, the ruler. Every run now prints, on pictures it never trained on:

    FLOOR    every painting scored against SOMEBODY ELSE'S photograph. A painter with a
             near-constant code paints one averaged thing for everyone, and then its own
             score and this one are the same number. That is the disease in one line.
    BORN     what the net scored before this run trained anything.
    REACHED  what it scored after -- on the held-out pictures (`--holdout`, default 0.15).
    CEILING  what it scores when allowed to train on them too (`--cheat`).

MEASURED the same day, 174 pictures, 200 strokes, 96px, 2000 steps, BLANK 0.04464:
BORN 0.30116 -> CEILING 0.01156 (3.9x better than a flat colour). HEADROOM +0.28959, so
the objective is emphatically NOT the bug -- the gallery run was simply nowhere near its
own ceiling and had no way to know. Held out: 0.04424, and the shuffled FLOOR 0.13337 --
a painting fits its own picture 3x better than a stranger's, so the picture is genuinely
being used.

AND THE PICTURE STILL DOES NOT MATCH THE NUMBER. Both were opened and looked at: at 200
strokes they are colour fields in roughly the right places, not paintings, and on
held-out pictures the painter is 4.4x WORSE than BLUR -- worse than simply showing a
14x14 grid of the photograph. Beating BLANK is real and it is not enough. Murphy's
`unlooked` witness exists for exactly this and it fires until somebody looks.

    python winston.py --img <a picture>                # paint one picture
    python winston.py --img <pic> --render 3840        # and hand it over at 4K
    python winston.py --train <folder> --holdout 0.15  # and MEASURE it honestly
"""
from __future__ import annotations

import argparse
import glob
import io
import os
import time

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

SIZE = 64
POINTS = 6            # control points per stroke -- a stroke is a curve, not a segment
PARAMS = POINTS * 2 + 1 + 3      # xy per point, width, rgb
MAX_REACH = 0.16                 # how far one step of a stroke may travel, in [-1,1] space


def load(path: str, size: int = SIZE) -> np.ndarray:
    """Read an image to (size,size,3) in [0,1]. PIL, not cv2 -- cv2.imread cannot open a
    filename containing Hebrew on Windows and returns None with a misleading error, and
    every photograph in this workspace lives under a Hebrew folder name."""
    from PIL import Image
    im = Image.open(path).convert("RGB")
    s = min(im.size)
    im = im.crop(((im.width - s) // 2, (im.height - s) // 2,
                  (im.width + s) // 2, (im.height + s) // 2)).resize((size, size),
                                                                     Image.LANCZOS)
    return np.asarray(im, np.float32) / 255.0


def decode(p, n_total: int = 0):
    """Stroke parameters -> geometry. ONE decoder shared by the small and the big
    renderer, so the painting Iddo sees at 4K is EXACTLY the strokes the loss saw.

    A STROKE IS A MARK, NOT A BEAM. With the points free to sit anywhere the painter
    learned to lay single strokes clear across the canvas -- one long dark slash covers a
    great many high-detail pixels cheaply, so weighting the loss by detail made the
    number better and the picture WORSE. A stroke gets an anchor and a bounded reach.

    COARSE-TO-FINE (2026-08-31): stroke index now means brush size. At a flat width
    budget the 120-stroke run was one tangled pale mass -- fat blobs and fine lines
    fought for the same job and the blobs won. So the first strokes get a broad brush
    (up to ~0.29 of the canvas: underpainting), the last a fine one (down to 0.007:
    detail), on a linear ramp. Compositing is back to front, so broad lies under fine
    exactly as on a real easel. `n_total` is the FULL budget -- pass it when rendering
    a truncated prefix during training, so a stroke keeps its own brush."""
    b, n, _ = p.shape
    nt = n_total or n
    raw = p[..., :POINTS * 2].view(b, n, POINTS, 2)
    anchor = torch.tanh(raw[:, :, :1]) * 0.95
    reach = torch.tanh(raw[:, :, 1:]) * MAX_REACH
    xy = torch.cat([anchor, anchor + torch.cumsum(reach, dim=2)], dim=2).clamp(-0.99, 0.99)
    wmul = torch.linspace(2.6, 0.55, nt, device=p.device)[:n]
    w = (0.012 + 0.10 * torch.sigmoid(p[..., POINTS * 2])) * wmul
    col = torch.sigmoid(p[..., POINTS * 2 + 1:])
    return xy, w, col


def composite(xy, w, col, px, soft: float = 1.0, chunk: int = 64):
    """Alpha-over all strokes onto white paper, back to front, WITHOUT the per-stroke
    Python loop the first version had (n kernel launches per painting). The same
    compositing has a closed form:

        pixel = sum_i col_i * A_i * prod_{j>i}(1 - A_j)  +  white * prod_j(1 - A_j)

    so each chunk is one cumprod and one sum, and a running transmittance carries the
    product across chunks (walked back to front, because later strokes lie on top).
    Identical mathematics, not an approximation -- and still CHUNKED, which is what makes
    a real resolution possible at all: the first version built the distance field for
    every stroke at once and died at 63 GB on a 512px canvas. Iddo looked at the 64x64
    output and said *"המקור רע, תן רזולוציה נורמלית"* -- he was right.
    Returns (B, n_px, 3)."""
    b, n = w.shape
    npx = px.shape[2]
    out = torch.zeros(b, npx, 3, device=px.device)
    T = torch.ones(b, npx, 1, device=px.device)      # transmittance of the strokes above
    for c0 in reversed(range(0, n, chunk)):
        c1 = min(n, c0 + chunk)
        sub = xy[:, c0:c1]
        m = c1 - c0
        a0 = sub[:, :, :-1].reshape(b, m * (POINTS - 1), 2)
        a1 = sub[:, :, 1:].reshape(b, m * (POINTS - 1), 2)
        d = (a1 - a0).unsqueeze(2)
        v = px - a0.unsqueeze(2)
        t = ((v * d).sum(-1) / (d * d).sum(-1).clamp_min(1e-6)).clamp(0, 1)
        near = a0.unsqueeze(2) + t.unsqueeze(-1) * d
        d2 = ((px - near) ** 2).sum(-1).view(b, m, POINTS - 1, npx).amin(2)
        alpha = torch.exp(-d2 / (2 * (w[:, c0:c1].unsqueeze(-1) ** 2) * soft))
        cp = torch.cumprod((1 - alpha).flip(1), dim=1)
        t_within = torch.cat([torch.ones_like(cp[:, :1]), cp[:, :-1]], dim=1).flip(1)
        out = out + (col[:, c0:c1].unsqueeze(2) * (alpha * t_within).unsqueeze(-1)).sum(1) * T
        T = T * cp[:, -1].unsqueeze(-1)
    return out + T                                   # white paper shows through what is left


def render(p, size: int = SIZE, soft: float = 1.0, chunk: int = 64, n_total: int = 0):
    """Lay the strokes down. Differentiable, painted BACK TO FRONT like a real hand."""
    b = p.shape[0]
    xy, w, col = decode(p, n_total)
    g = torch.linspace(-1, 1, size, device=p.device)
    gy, gx = torch.meshgrid(g, g, indexing="ij")
    px = torch.stack([gx, gy], -1).view(1, 1, size * size, 2)
    return composite(xy, w, col, px, soft=soft, chunk=chunk).view(b, size, size, 3)


@torch.no_grad()
def render_big(p, size: int, tile: int = 512, chunk: int = 24, device=None):
    """The same strokes, at any size. **This is the whole point of painting in vectors.**

    Iddo asked for 4K. A stroke is a curve, not a grid of pixels, so 4K is not an upscale
    of anything -- the identical parameters are simply evaluated on a finer lattice, and
    the line is exactly as sharp as the lattice allows. Nothing is invented and no
    upscaler is involved. That is what `resolution-free` means and it is why the painter
    was built this way.

    Training still happens small, because the LOSS needs every pixel in memory at once.
    Rendering does not: it goes tile by tile, so 4K costs time and not memory.
    """
    b = p.shape[0]
    dev = device or p.device
    xy, w, col = decode(p.to(dev))

    out = torch.ones(b, size, size, 3, device=dev)
    g = torch.linspace(-1, 1, size, device=dev)
    for y0 in range(0, size, tile):
        y1 = min(size, y0 + tile)
        for x0 in range(0, size, tile):
            x1 = min(size, x0 + tile)
            gy, gx = torch.meshgrid(g[y0:y1], g[x0:x1], indexing="ij")
            px = torch.stack([gx, gy], -1).reshape(1, 1, -1, 2)
            canvas = composite(xy, w, col, px, chunk=chunk)
            out[:, y0:y1, x0:x1] = canvas.view(b, y1 - y0, x1 - x0, 3)
    return out


class Painter(nn.Module):
    """Look at the picture; say how to paint it. A real encoder, real weights, trained."""

    def __init__(self, strokes: int = 120, d: int = 256, grid: int = 4):
        """`grid` is the side of the spatial code. MEASURED 2026-09-01 on the 174
        pictures of the gallery run: with the old `AdaptiveAvgPool2d(1)` the whole
        256x12x12 map was averaged down to 256 numbers, and the picture-to-picture
        variance that survived was 0.0333 with 92.7% of it in ONE direction -- mean
        pairwise cosine 0.9752, and two pictures literally indistinguishable at 0.9999.
        The decoder was asked to emit 174 different 12,800-number stroke sets from a code
        that is very nearly a constant. `grid=1` reproduces that net exactly and is kept
        as the control; `grid=4` keeps 16 cells of layout, which is where a stroke's
        PLACE lives."""
        super().__init__()
        self.n = strokes
        self.grid = grid
        self.see = nn.Sequential(
            nn.Conv2d(3, 32, 4, 2, 1), nn.GELU(),       # 64 -> 32
            nn.Conv2d(32, 64, 4, 2, 1), nn.GELU(),      # 32 -> 16
            nn.Conv2d(64, 128, 4, 2, 1), nn.GELU(),     # 16 -> 8
            nn.Conv2d(128, 256, 4, 2, 1), nn.GELU(),    # 8 -> 4
            nn.AdaptiveAvgPool2d(grid), nn.Flatten())
        self.decide = nn.Sequential(nn.Linear(256 * grid * grid, d), nn.GELU(),
                                    nn.Linear(d, d), nn.GELU(),
                                    nn.Linear(d, strokes * PARAMS))

    def forward(self, img):                      # img (B,H,W,3), any square H=W
        h = self.see(img.permute(0, 3, 1, 2))
        return self.decide(h).view(-1, self.n, PARAMS)


def detail(x, k: int = 5):
    """Where the picture is BUSY. Returns a weight map with mean 1. (B,H,W,1)

    THE REASON THIS EXISTS, measured on the first run: the painter scored mse 0.00568 --
    beating a flat colour by 7x and the resolution ceiling by 2.6x -- and **the girl in the
    photograph was gone.** A face is about 3% of the pixels; a wall is 40%. Under plain
    MSE, erasing the person costs almost nothing and smoothing the wall correctly earns a
    lot, so selling her for the wall was the CORRECT move under the loss I wrote.
    The failure was in the metric, not the model.

    So error is weighted by how much structure is there. A painter may still simplify a
    wall. It may no longer buy the wall with a face.
    """
    g = x.mean(-1, keepdim=True).permute(0, 3, 1, 2)
    dx = F.pad(g[:, :, :, 1:] - g[:, :, :, :-1], (0, 1))
    dy = F.pad(g[:, :, 1:, :] - g[:, :, :-1, :], (0, 0, 0, 1))
    e = (dx.abs() + dy.abs())
    e = F.avg_pool2d(F.pad(e, (k // 2,) * 4, mode="replicate"), k, 1)
    e = e.permute(0, 2, 3, 1)
    return e / e.mean(dim=(1, 2, 3), keepdim=True).clamp_min(1e-6)


def busy_error(y, x, w):
    """Error in the busiest tenth of the picture -- the number that catches a vanished
    person. A painting can be excellent everywhere flat and still have lost its subject."""
    b = x.shape[0]
    flat = w.reshape(b, -1)
    cut = flat.quantile(0.90, dim=1, keepdim=True)
    m = (flat >= cut).float().view(b, x.shape[1], x.shape[2], 1)
    return float((((y - x) ** 2) * m).sum() / (m.sum() * x.shape[-1]).clamp_min(1))


def colour_life(y, x, k: int = 8):
    """How much LESS alive the painting's colour is than the photograph's.

    MEASURED motivation (2026-08-31): under plain MSE every stroke that straddles two
    colours is paid to choose their average, so both diagnostic runs drifted to washed
    grey-beige -- greens muted, highlights greyed. The number was minimised and the
    picture was dead. The correction: per-pixel chroma (max minus min of RGB), averaged
    over k x k regions, and only UNDER-saturation is charged -- colour the photograph
    does not have stays expensive through the MSE. No perceptual network, nothing
    hidden: one subtraction, one hinge."""
    def sat(z):
        return (z.max(-1).values - z.min(-1).values).unsqueeze(1)
    return F.relu(F.avg_pool2d(sat(x), k) - F.avg_pool2d(sat(y), k)).mean()


def floors(x, strokes: int, size: int = SIZE):
    """The floors, computed on the same picture, every run. BLANK must be beaten; BLUR is
    the same budget spent on a square grid -- curves were measured to beat it 4-7x, so a
    painter that does NOT clearly beat BLUR is wasting its curves."""
    flat = x.mean(dim=(1, 2), keepdim=True).expand_as(x)
    blank = float(F.mse_loss(flat, x))
    side = max(2, int(round(strokes ** 0.5)))          # the budget's own resolution
    small = F.interpolate(x.permute(0, 3, 1, 2), size=(side, side), mode="area")
    blur = F.interpolate(small, size=(size, size), mode="bilinear",
                         align_corners=False).permute(0, 2, 3, 1)
    return blank, float(F.mse_loss(blur, x)), side


def split(n: int, holdout: float, dev: float = 0.0, seed: int = 1933):
    """A REAL held-out split, and the reason it had to be added.

    MEASURED 2026-09-01: `--train` used the same folder as train AND test. The run was
    therefore its own ceiling -- fitted on the test -- and after 13.4 hours that ceiling
    stood at mse 0.07731 against its own BLANK floor of 0.04997: the best the recipe
    could possibly do was 1.5x WORSE than painting each picture one flat colour. By the
    night's law that is not a slow learner, it is a broken objective, and no amount of
    further training could ever have shown it. A number with nothing held out has nothing
    to fall through."""
    idx = np.random.default_rng(seed).permutation(n)
    k = int(round(n * holdout))
    if n < 4 or k < 1:
        return idx, idx[:0], idx[:0]
    d = int(round(n * dev)) if n >= 8 else 0
    return idx[k + d:], idx[k:k + d], idx[:k]      # train, DEV, test


@torch.no_grad()
def paint(net, X, size: int, chunk: int, bs: int = 8):
    """Paint a whole set in batches. One `render` over 174 pictures at 192px is 60+ GB."""
    return torch.cat([render(net(X[i:i + bs]), size=size, chunk=chunk)
                      for i in range(0, len(X), bs)]) if len(X) else X


@torch.no_grad()
def gauge(net, X, size: int, chunk: int):
    """The score, and THE FLOOR THE SCORE HAS TO FALL THROUGH.

    `shuf` is the night's shuffled control in the only form it can take for a painter:
    every painting is scored against SOMEBODY ELSE'S photograph. A painter that is
    genuinely looking scores far better on its own picture than on a stranger's. A
    painter whose code is a near-constant paints one averaged thing for everybody, and
    then `mse` and `shuf` are the same number -- the disease visible in one line every
    round, instead of after 55 hours."""
    if len(X) == 0:
        return float("nan"), float("nan"), float("nan")
    Y = paint(net, X, size, chunk)
    m = float(F.mse_loss(Y, X))
    shuf = float("nan")
    if len(X) > 1:
        roll = torch.roll(torch.arange(len(X), device=X.device), 1)
        shuf = float(F.mse_loss(Y, X[roll]))
    return m, shuf, busy_error(Y, X, detail(X))


def skill(mse: float, blank: float) -> float:
    """mse -> higher-is-better, on the scale Murphy's lines were calibrated for: the
    fraction of the flat-colour error the painting removed. 0 = a flat colour did as
    well. Negative = worse than a flat colour, which is where the gallery run sat."""
    return float("nan") if blank <= 0 else 1.0 - mse / blank


def murphy_load():
    """Import the LIVE Murphy -- never a copy sitting next to the script.

    2026-09-01: in the SIBLING plant Murphy had been copied in and never imported once,
    so nothing he would have caught was ever caught. A copy that does not run is worse
    than no Murphy, because it looks like oversight. This resolves to the real file and
    prints which one; if none is found the run says so in place of a ruling rather than
    quietly reporting without one."""
    import importlib.util
    here = os.path.dirname(os.path.abspath(__file__))
    for c in (os.environ.get("MURPHY_PY", ""),
              os.path.join(here, "murphy", "murphy.py"),
              os.path.expanduser("~/nezer-src/murphy/murphy.py"),
              os.path.expanduser("~/sibling-src/murphy/murphy.py")):
        if c and os.path.isfile(c):
            try:
                spec = importlib.util.spec_from_file_location("murphy", c)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                return mod, os.path.abspath(c)
            except Exception as e:                              # noqa: BLE001
                print("  MURPHY at %s would not load: %s" % (c, e))
    return None, ""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="A network that learns to paint.")
    ap.add_argument("--img", help="one picture to learn to paint")
    ap.add_argument("--train", help="a folder of pictures instead")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(
        os.path.abspath(__file__)), "out"))
    ap.add_argument("--strokes", type=int, default=400,
                    help="120 was measured to be a toy: the walking people vanished. "
                         "400 painted a recognisable boulevard.")
    ap.add_argument("--render", type=int, default=0, metavar="PX",
                    help="Render the finished painting at this side length, e.g. 3840. "
                         "Costs nothing in quality: the strokes are curves, so a larger "
                         "canvas is a finer evaluation, never an upscale.")
    ap.add_argument("--chunk", type=int, default=64, metavar="N",
                    help="strokes composited at once. Memory is chunk x points x size^2, "
                         "so LOWER this (8, 4) to afford more strokes or a bigger canvas. "
                         "The gradient is identical -- only the peak memory changes.")
    ap.add_argument("--size", type=int, default=128,
                    help="canvas side the LOSS sees. 64 was a toy (the strokes only ever "
                         "learned 64px of content); render size is separate and free.")
    ap.add_argument("--steps", type=int, default=3000)
    ap.add_argument("--lr", type=float, default=2e-3)
    ap.add_argument("--detail-w", type=float, default=3.0,
                    help="how much more an error costs where the picture is busy. 0 gives "
                         "back plain MSE, which is what erased the girl.")
    ap.add_argument("--colour-w", type=float, default=1.5,
                    help="weight of the colour-life hinge. 0 gives back the metric that "
                         "washed everything grey-beige.")
    ap.add_argument("--resume", default="",
                    help="painter.pt to continue from (2026-09-01, Iddo: אימון 24/7). "
                         "Strokes must match; training never has to start over again.")
    ap.add_argument("--holdout", type=float, default=0.15, metavar="FRAC",
                    help="fraction of the pictures NEVER trained on. The gallery run had "
                         "none: it was its own ceiling, and it lost to a flat colour.")
    ap.add_argument("--dev", type=float, default=0.15, metavar="FRAC",
                    help="a THIRD split, for a caller that has to decide whether to keep "
                         "a training cycle. Deciding that on the held-out set fits the "
                         "held-out set by selection, and then the reported number is not "
                         "a report any more. DEV is what a loop may choose on; the "
                         "held-out number is only ever printed.")
    ap.add_argument("--grid", type=int, default=4, metavar="G",
                    help="side of the spatial code. 1 = the old global-average encoder, "
                         "kept as the control.")
    ap.add_argument("--cheat", action="store_true",
                    help="train ON the held-out pictures too. What it then reports is the "
                         "CEILING -- the best this recipe could ever score. If the ceiling "
                         "does not beat BLANK, the objective is the bug.")
    ap.add_argument("--looked", action="store_true",
                    help="a person actually opened the output and looked at it. Murphy "
                         "asks; do not pass this unless it is true.")
    ap.add_argument("--seed", type=int, default=1933, metavar="N",
                    help="the seed for the WEIGHTS and the batch order. The train/dev/"
                         "test split is NOT drawn from it and never moves, so dev cannot "
                         "leak into train by reshuffling. A 24/7 loop must vary this per "
                         "cycle: with it pinned, a resumed cycle repeats the previous one "
                         "step for step and an unattended loop runs the same failing "
                         "round forever -- which is exactly the bit-identical-output "
                         "disease found in the SIBLING tree the same night.")
    ap.add_argument("--tag", default="", help="name for the Murphy ruling")
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    a = ap.parse_args(argv)

    dev = torch.device(a.device)
    torch.manual_seed(a.seed)
    if a.train:
        paths = sorted(sum((glob.glob(os.path.join(a.train, "**", e), recursive=True)
                            for e in ("*.jpg", "*.jpeg", "*.png")), []))[:400]
    else:
        paths = [a.img]
    if not paths:
        print("no pictures found")
        return 2
    X = torch.as_tensor(np.stack([load(p, a.size) for p in paths]), device=dev)
    tr, dv, va = split(len(X), a.holdout, a.dev)
    Xva = X[torch.as_tensor(np.asarray(va), device=dev)] if len(va) else X[:0]
    Xdv = X[torch.as_tensor(np.asarray(dv), device=dev)] if len(dv) else X[:0]
    pool = np.arange(len(X)) if a.cheat else tr
    Xtr = X[torch.as_tensor(np.asarray(pool), device=dev)]
    G = Xva if len(Xva) else Xtr             # what every number below is measured on
    print("painter: %d picture(s) -> %d trained on, %d dev, %d HELD OUT%s; %d strokes, "
          "%d params each, grid %d, device %s"
          % (len(X), len(Xtr), len(Xdv), len(Xva),
             "  (--cheat: the held-out are IN the training pool, so what is reported "
             "below is a CEILING)" if a.cheat else "",
             a.strokes, PARAMS, a.grid, dev))
    if not len(Xva):
        print("  !! NOTHING HELD OUT. Whatever this run reports is memory, not evidence.")

    blank, blur, side = floors(G, a.strokes, a.size)
    print("  BLANK (best flat colour)          mse %.5f   <- beat this or nothing happened"
          % blank)
    print("  BLUR  (%dx%d grid, same budget)      mse %.5f   <- curves should beat this; "
          "measured 4-7x" % (side, side, blur))

    net = Painter(a.strokes, grid=a.grid).to(dev)
    if a.resume and os.path.isfile(a.resume):
        ck = torch.load(a.resume, map_location=dev, weights_only=False)
        if int(ck.get("grid", 1)) != a.grid:
            print("  !! checkpoint grid %s != --grid %d; NOT resuming (different encoder)"
                  % (ck.get("grid", 1), a.grid))
        else:
            net.load_state_dict(ck["net"])
            print("  resumed from %s (strokes %d, step %s)"
                  % (a.resume, ck.get("strokes", -1), ck.get("step", "?")), flush=True)
    born, born_shuf, _ = gauge(net, G, a.size, a.chunk)
    print("  BORN  (this net before this run)   mse %.5f   skill %+.3f" % (born,
                                                                          skill(born, blank)))
    print("  FLOOR (its paintings vs the WRONG picture)  mse %.5f   skill %+.3f"
          % (born_shuf, skill(born_shuf, blank)))
    opt = torch.optim.AdamW(net.parameters(), lr=a.lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, a.lr, total_steps=a.steps,
                                                pct_start=0.15)
    t0 = time.time()
    trace_steps = []
    best = {"loss": float("inf"), "state": None, "step": 0}
    run_loss, run_n = 0.0, 0
    for step in range(1, a.steps + 1):
        i = torch.randint(0, len(Xtr), (min(16, len(Xtr)),), device=dev)
        x = Xtr[i]
        # soft edges early, crisp later: a hard line has almost no gradient anywhere
        # except on the line itself, so a fresh network never finds out which way to move.
        soft = max(1.0, 6.0 * (1 - step / a.steps) ** 2 + 1.0)
        # coarse-to-fine: begin with the broad third of the budget (the underpainting),
        # let the finer strokes join on a ramp, everyone in by 55% of training. A stroke
        # keeps its own brush width throughout -- n_total pins the ramp to the FULL budget.
        n_act = max(1, min(a.strokes, int(round(
            a.strokes * (0.3 + 0.7 * step / (0.55 * a.steps))))))
        y = render(net(x)[:, :n_act], size=a.size, soft=soft, chunk=a.chunk,
                   n_total=a.strokes)
        w = detail(x)
        # The colour hinge joins WITH the fine strokes, not before. Measured 2026-08-31:
        # ramp alone converged (0.00484), hinge alone converged (0.00534), together they
        # diverged and froze (0.13434 -- worse than a flat colour). During the
        # underpainting phase the broad strokes are the only lever, the hinge drives their
        # colours to saturated extremes, the sigmoids pin, and the painter dies with zero
        # gradient. Scaled by the ramp, the demand for colour arrives when the brushes
        # that can afford it do.
        terms = {"mse": F.mse_loss(y, x),
                 "detail": a.detail_w * (((y - x) ** 2) * w).mean(),
                 "colour": a.colour_w * (n_act / a.strokes) * colour_life(y, x)}
        loss = terms["mse"] + terms["detail"] + terms["colour"]
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(net.parameters(), 1.0)
        opt.step()
        sched.step()
        run_loss += float(loss.detach())
        run_n += 1
        if step % max(1, a.steps // 10) == 0 or step == a.steps:
            m, sh, bz = gauge(net, G, a.size, a.chunk)
            trace_steps.append({"step": step, "metric": skill(m, blank),
                                "terms": {k: float(v.detach()) for k, v in terms.items()}})
            print("  step %5d  HELD-OUT %.5f (skill %+.3f)  FLOOR %.5f  BUSY %.5f  "
                  "loss %.5f  (%.0fs)"
                  % (step, m, skill(m, blank), sh, bz, float(loss.detach()), time.time() - t0),
                  flush=True)
            # SAVE NOW, not at the end. The gallery run held 69 GB of GPU for 17.7
            # hours and wrote nothing, because `torch.save` sat after a 30,000-step loop.
            # A run that cannot be interrupted has no results until it finishes, and that
            # one never did.
            #
            # And keep the BEST state, not the last. On eran4 at 17:00 on 2026-09-01 the
            # boulevard run sat at mse 0.02736 at step 6000 -- 3.2x better than its BLANK
            # floor -- and at step 7200 it was 0.21028 and never came back. Saving only
            # the final weights throws a good painter away because of what happened
            # afterwards. Selection is by the TRAINING loss, so the held-out number
            # stays a report and never becomes something that was fitted.
            avg = run_loss / max(run_n, 1)
            run_loss, run_n = 0.0, 0
            os.makedirs(a.out, exist_ok=True)
            torch.save({"net": net.state_dict(), "strokes": a.strokes, "size": a.size,
                        "grid": a.grid, "step": step, "held_out_mse": m},
                       os.path.join(a.out, "painter-last.pt"))
            if avg < best["loss"]:
                best = {"loss": avg, "step": step,
                        "state": {k: v.detach().clone() for k, v in
                                  net.state_dict().items()}}
                torch.save({"net": best["state"], "strokes": a.strokes, "size": a.size,
                            "grid": a.grid, "step": step, "held_out_mse": m,
                            "train_loss": avg}, os.path.join(a.out, "painter.pt"))
            elif avg > 3.0 * best["loss"]:
                print("       ^ TRAINING LOSS BLEW UP (%.5f vs best %.5f at step %d). "
                      "painter.pt still holds the good state." % (avg, best["loss"],
                                                                  best["step"]),
                      flush=True)

    from PIL import Image
    os.makedirs(a.out, exist_ok=True)
    if best["state"] is not None and best["step"] != a.steps:
        net.load_state_dict(best["state"])
        print("\n  restored the best state of this run: step %d (mean training loss "
              "%.5f). Everything below is measured on THAT painter, not on whatever the "
              "last step happened to leave behind." % (best["step"], best["loss"]))
    final, final_shuf, final_busy = gauge(net, G, a.size, a.chunk)
    with torch.no_grad():
        y = paint(net, G[:8], a.size, a.chunk)
        blank_busy = busy_error(G.mean(dim=(1, 2), keepdim=True).expand_as(G), G, detail(G))
    for k in range(min(8, len(G))):
        pair = np.concatenate([G[k].cpu().numpy(), y[k].cpu().numpy()], axis=1)
        Image.fromarray((pair * 255).astype(np.uint8)).save(
            os.path.join(a.out, "paint-%02d.png" % k))
    torch.save({"net": net.state_dict(), "strokes": a.strokes, "size": a.size,
                "grid": a.grid, "step": best["step"] or a.steps, "held_out_mse": final,
                "train_loss": best["loss"]}, os.path.join(a.out, "painter.pt"))
    if a.render:
        with torch.no_grad():
            big = render_big(net(X[:1]), a.render, chunk=max(4, a.chunk // 4))[0].cpu().numpy()
        Image.fromarray((big * 255).astype(np.uint8)).save(
            os.path.join(a.out, "painting-%dpx.png" % a.render))
        print("rendered %dx%d from the same strokes, no upscaler -> %s"
              % (a.render, a.render, os.path.join(a.out, "painting-%dpx.png" % a.render)))
    what = ("CEILING (this run FIT these pictures)" if a.cheat else
            "REACHED (held out)                 " if len(Xva) else
            "REACHED (NOTHING was held out)     ")
    print("\n" + "=" * 76)
    print("THE FOUR NUMBERS  (mse over %d %s picture(s); lower is better)"
          % (len(G), "training" if (a.cheat or not len(Xva)) else "HELD-OUT"))
    print("  FLOOR    paintings scored against the WRONG picture  %.5f" % final_shuf)
    print("  BORN     before this run trained anything            %.5f" % born)
    print("  %s                 %.5f" % (what, final))
    print("  HEADROOM born - reached                              %+.5f" % (born - final))
    print("  BLANK    one flat colour per picture                 %.5f" % blank)
    print("  BLUR     %dx%d grid, same stroke budget                %.5f"
          % (side, side, blur))
    if len(Xdv):
        dev_mse = gauge(net, Xdv, a.size, a.chunk)[0]
        print("  DEV      %d pictures a caller MAY choose on            %.5f"
              % (len(Xdv), dev_mse))
    g1 = final < blank
    g2 = None if final_shuf != final_shuf else (final_shuf - final) > 0.1 * blank
    print("  gate 1  beats a flat colour?      %s   (%.5f vs BLANK %.5f)"
          % ("YES" if g1 else "NO ", final, blank))
    print("  gate 2  uses the PICTURE at all?  %s   (own %.5f vs stranger %.5f, gap %+.5f)"
          % ("--" if g2 is None else ("YES" if g2 else "NO "), final, final_shuf,
             final_shuf - final))
    print("BUSY tenth: PAINTER %.5f vs BLANK %.5f   <- the number that catches a "
          "vanished person" % (final_busy, blank_busy))
    if not g1:
        print(" FAILS: worse than one flat colour. It is not painting, it is smearing.")
    if final_busy >= blank_busy:
        print(" BUT the busy tenth is no better than a flat colour: the SUBJECT was sold. "
              "That is the 08-31 failure mode; do not call this a painting.")
    print("-> %s  (original | painted, side by side)" % a.out)

    # ---- Murphy rules on it. Every run, from the LIVE file, never a copy. ------------
    mu, mu_path = murphy_load()
    if mu is None:
        print("\n!! MURPHY DID NOT RUN -- murphy.py was not found. This run is UNJUDGED.")
    else:
        print("\n  (murphy: %s)" % mu_path)
        mu.watch({"chance": skill(final_shuf, blank),   # the shuffled floor, in skill
                  "baseline": 0.0,                      # a flat colour IS skill 0
                  "held_out": bool(len(Xva)) and not a.cheat,
                  "judge_in_loop": False,     # the ruler is mse against the photograph
                  "independent": bool(len(Xva)) and not a.cheat,
                  "artifact": "paintings",
                  "looked_at": bool(a.looked),
                  "claimed_success": bool(g1),
                  "steps": trace_steps},
                 name=a.tag or ("winston %d pics, %d strokes, grid %d"
                                % (len(X), a.strokes, a.grid)))
    return 0 if g1 else 1


if __name__ == "__main__":
    raise SystemExit(main())
