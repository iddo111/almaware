"""HAND AND EYE — the painter inside ERAN, judged by ERAN's own sight.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

Iddo, 2026-08-30: *"תשלב את הצייר בתוך ערן כבר עכשיו גם את מיקו."*
Iddo, 2026-08-30 later: *"תרים את התקרה של ווינסטון — יותר קווים ונקודות, ולחץ עט משתנה."*

This is the same machine as the throat, with the ear swapped for the eye:

    throat    arms    ->  the EAR scores them  ->  better arms
    hand      strokes ->  the EYE scores them  ->  better strokes

**No labels anywhere in the loop.** The hand is never told "draw alef". It is handed a
POINT IN GIST SPACE and asked to put something on paper that lands there when looked at.
The eye — trained without labels, and measured at 94% on typefaces it had never seen —
says how close it landed. That single number is all that comes back.

## Where MIKO is, and where it is not

I went looking for `AlmaBinding` to do this and it is the wrong part: it binds UTF-8
BYTES to letter-class and sound-class, which has nothing to say about a shape. Reporting
it as the binding would have been a lie that measured well.

`ThreeFactor` in `miko/model/loop.py` is the right part, and it is exactly the missing
piece. The hand learns by local plasticity with ONE global right/wrong scalar — no
gradient travels back through the eye, and nothing travels backwards at all. The eye is
factor three.

## The ceiling, and why it had to move

The hand reached cos 0.445 where DIRECT optimisation of the same 3-stroke/6-point pen
reaches 0.446. **The hand was not the limit any more — the PEN was.** So the pen grew:
the stroke and point counts are arguments now, and every control point carries a third
number, PRESSURE, which sets the ink width at that point and interpolates along the
segment. A pen that can go thick and thin can make a `ו` that is not the same weight as
a `ן`, and can put a serif on a `ב`.

    python hand_eye.py --table --strokes 5 --points 8 --pressure --steps 300000
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "eye"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "miko", "model"))

sys.path.insert(0, os.path.join(HERE, "..", "..", "murphy"))

from eye import Encoder, SIZE                                   # noqa: E402
from loop import ThreeFactor                                    # noqa: E402
from murphy import watch                                        # noqa: E402

# What the pen audit has to clear before the sheet counts as LOOKED AT. These are the
# three numbers that separated the two Winston runs of 2026-08-30 and nothing else did.
# A letter is one connected mark, sometimes two; a constellation is many. A segment
# shorter than the nib is wide is a blob, not a stroke. The printed corpus inks 0.040 of
# the page, so a sheet inking a fifth of it is a blot and one inking a hundredth is dust.
AUDIT = {"pieces": 2.5, "stub": 0.34, "cover": (0.012, 0.120)}

STROKES = 3          # DEFAULTS ONLY. Both are arguments now; the ceiling moved when
POINTS = 6           # they did, and the numbers are in ceiling.py.

# Pressure range, in page units where the page is [-1,1] and SIZE px wide.
# W_MIN = 0.018 is 0.58 px of sigma at SIZE=64: thin, but the ink is distance-to-SEGMENT,
# so a thin line is still an unbroken line. W_MAX = 0.075 is 2.4 px. The old fixed pen
# sat at 0.045 — inside this range, so nothing is lost by making it learnable.
W_MIN, W_MAX = 0.018, 0.075
W_FIXED = 0.045


def pen(raw, strokes, points, pressure):
    """One flat row of numbers -> a pen: control points, and the width at each of them.

    x,y go through tanh*0.85 (stay on the page). Pressure goes through a sigmoid into
    [W_MIN, W_MAX] — it can never be zero, so the hand cannot lift the pen to fake a
    shape out of gaps, and it can never be huge, so it cannot fill the page with a blot.
    """
    dim = 3 if pressure else 2
    v = raw.view(-1, strokes, points, dim)
    xy = torch.tanh(v[..., :2]) * 0.85
    w = (W_MIN + (W_MAX - W_MIN) * torch.sigmoid(v[..., 2])) if pressure else W_FIXED
    return xy, w


class Winston(nn.Module):
    """WINSTON — the hand. One row of numbers per letter; the child's version.

    Named by Iddo, 2026-08-30: *"נקרא לו אולי ווינסטון לכבוד צ'רצ'יל שהיה צייר נגד צייר
    רשע אחר."* Churchill painted for forty years and called it the thing that held him
    together; the other man had wanted to paint, was refused, and went and did what he
    did instead. Two hands, one brush each. The name is a side to stand on.

    A child does not learn a map from meaning to muscle and then apply it to alef. A
    child learns alef. So: a one-hot letter in, S*P*3 numbers out, and only the row of
    the letter being drawn is touched — which is exactly what ThreeFactor does when the
    pre-synaptic side is one-hot, unchanged, with no gradient anywhere.

    What is given up is generalisation: this hand knows 22 letters, it does not know how
    to draw a letter it has never met. That comes after, and it comes from this.
    """

    def __init__(self, n_cls, strokes=STROKES, points=POINTS, pressure=False):
        super().__init__()
        self.strokes, self.points, self.pressure = strokes, points, pressure
        self.dim = 3 if pressure else 2
        self.out = nn.Linear(n_cls, strokes * points * self.dim, bias=False)
        nn.init.normal_(self.out.weight, std=0.4)

    def forward(self, onehot, e3=None):
        z = self.out(onehot)
        return pen(z if e3 is None else z + e3,
                   self.strokes, self.points, self.pressure)


class Hand(nn.Module):
    """Given a point in gist space, put strokes on paper that land there.

    Kept for the gist->strokes experiment. The tremor cannot climb it (one number per
    trial against ~8k parameters); Winston is the version that learns.
    """

    def __init__(self, gist=192, hidden=32, strokes=STROKES, points=POINTS,
                 pressure=False):
        super().__init__()
        self.strokes, self.points, self.pressure = strokes, points, pressure
        dim = 3 if pressure else 2
        self.fc1 = nn.Linear(gist, hidden)
        self.fc2 = nn.Linear(hidden, hidden)
        self.out = nn.Linear(hidden, strokes * points * dim)
        nn.init.zeros_(self.out.bias)

    def forward(self, g, e1=None, e2=None, e3=None):
        z1 = self.fc1(g)
        h1 = torch.tanh(z1 if e1 is None else z1 + e1)
        z2 = self.fc2(h1)
        h2 = torch.tanh(z2 if e2 is None else z2 + e2)
        z3 = self.out(h2)
        return pen(z3 if e3 is None else z3 + e3,
                   self.strokes, self.points, self.pressure)


def ink(xy, width=W_FIXED, size=SIZE):
    """Draw the strokes as LINES. Distance to the segment, not to sampled dots.

    The first version sampled 20 points along each stroke and blurred each one. In pixels
    that is a 1.1px blob every 3.2px -- **they never touch.** The hand then did the
    obvious thing and learned to place constellations of dots that satisfied the eye:
    86% read back, and not one of them was a letter a person would recognise. The metric
    was happy and the deliverable did not exist. I only caught it by looking at the sheet.

    Iddo asked for a draughtsman: *"הצייר מצייר קווים."* So the ink is a real line --
    every pixel takes its distance to the nearest SEGMENT, which is continuous by
    construction at any width, and the constellation trick stops being available.

    `width` may be a scalar (one nib for the whole page) or a (B,S,P) tensor of per-point
    widths, in which case the width is interpolated ALONG each segment by the same t that
    finds the nearest point — so a stroke can start heavy and end light, like a real nib.
    """
    b = xy.shape[0]
    a0 = xy[:, :, :-1].reshape(b, -1, 2)              # segment starts
    a1 = xy[:, :, 1:].reshape(b, -1, 2)               # segment ends
    g = torch.linspace(-1, 1, size, device=xy.device)
    gy, gx = torch.meshgrid(g, g, indexing="ij")
    px = torch.stack([gx, gy], -1).view(1, 1, size * size, 2)

    d = (a1 - a0).unsqueeze(2)                        # (B,S,1,2)
    v = px - a0.unsqueeze(2)                          # (B,S,P,2)
    t = ((v * d).sum(-1) / (d * d).sum(-1).clamp_min(1e-6)).clamp(0, 1)
    close = a0.unsqueeze(2) + t.unsqueeze(-1) * d     # nearest point ON the segment
    d2 = ((px - close) ** 2).sum(-1)                  # (B,S,P)
    if torch.is_tensor(width):
        w0 = width[:, :, :-1].reshape(b, -1, 1)
        w1 = width[:, :, 1:].reshape(b, -1, 1)
        w = w0 + t * (w1 - w0)                        # the nib opens and closes
    else:
        w = width
    return torch.exp(-d2 / (2 * w * w)).amax(1).view(b, size, size).clamp(0, 1)


# ─────────────────────────────────────────────────────────── the dot-cloud detector

def penmarks(img, xy, width, thr=0.35):
    """Is this a LINE, or is it the constellation trick wearing a bigger hat?

    On 2026-08-30 a hand scored 86% drawing dot-clouds no person would call a letter, and
    the number said nothing about it. A wider pen with more points can rediscover that
    dodge — collapse each segment to a stub and scatter the stubs. So this is measured on
    every sheet, not assumed away:

        pieces    4-connected components of the inked page. A letter is 1, sometimes 2.
                  A constellation is many.
        stub      fraction of segments shorter than the ink is wide. Those are blobs,
                  not strokes.
        cover     fraction of the page inked. The printed corpus averages 0.040.
    """
    b = img.shape[0]
    a = (img.detach().cpu().numpy() > thr)
    out = []
    seg = (xy[:, :, 1:] - xy[:, :, :-1]).norm(dim=-1)              # (B,S,P-1)
    if torch.is_tensor(width):
        nib = 0.5 * (width[:, :, 1:] + width[:, :, :-1])
    else:
        nib = torch.full_like(seg, float(width))
    stub = (seg < 2.0 * nib).float().mean(dim=(1, 2)).tolist()
    for i in range(b):
        out.append({"pieces": _components(a[i]),
                    "stub": round(float(stub[i]), 3),
                    "cover": round(float(a[i].mean()), 4)})
    return out


def _components(mask):
    """4-connected components, plain flood fill. The page is 64x64; nothing clever needed."""
    h, w = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    n = 0
    for sy in range(h):
        for sx in range(w):
            if not mask[sy, sx] or seen[sy, sx]:
                continue
            n += 1
            stack = [(sy, sx)]
            seen[sy, sx] = True
            while stack:
                y, x = stack.pop()
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
    return n


def centroids(enc, X, y, device):
    """Where each letter LIVES in the eye's space. These are the targets the hand aims at.

    Note what they are NOT: they are not labels handed to the hand. They are places the
    eye found on its own, and the hand only ever sees a coordinate.
    """
    with torch.no_grad():
        g = torch.cat([enc.gist(torch.as_tensor(X[i:i + 512], device=device))
                       for i in range(0, len(X), 512)])
    yt = torch.as_tensor(y.astype(np.int64), device=device)
    cls = sorted(set(y.tolist()))
    return F.normalize(torch.stack([g[yt == c].mean(0) for c in cls]), dim=-1), cls


def load_eye(path, dev):
    ck = torch.load(path, map_location=dev)
    enc = Encoder().to(dev)
    enc.load_state_dict(ck["encoder"])
    enc.eval()
    for p in enc.parameters():
        p.requires_grad_(False)                  # the eye is a judge, never a student
    return enc


def draw(hand, onehot):
    xy, w = hand(onehot)
    return ink(xy, w), xy, w


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="The hand learns to draw, judged by the eye.")
    ap.add_argument("--eye", default=os.path.join(HERE, "..", "eye", "state", "eye.pt"))
    ap.add_argument("--data", default=os.path.join(HERE, "..", "eye", "corpus",
                                                   "letters.npz"))
    ap.add_argument("--out", default=os.path.join(HERE, "state"))
    ap.add_argument("--tag", default="hand", help="checkpoint basename")
    ap.add_argument("--steps", type=int, default=3000)
    ap.add_argument("--lr", type=float, default=2e-3)
    ap.add_argument("--hidden", type=int, default=32)
    ap.add_argument("--strokes", type=int, default=STROKES)
    ap.add_argument("--points", type=int, default=POINTS)
    ap.add_argument("--pressure", action="store_true",
                    help="Third number per control point: the ink width there.")
    ap.add_argument("--sigma", type=float, default=0.02,
                    help="How hard the hand shakes. MEASURED against the true gradient: "
                         "at 0.02 the tremor estimates it at cosine +0.76, at 0.15 only "
                         "+0.05, at 0.40 it is NEGATIVE.")
    ap.add_argument("--wgain", type=float, default=15.0,
                    help="Shake the NIB this many times harder than the points. Not a "
                         "guess -- audit_pen.py measured it. At gain 1 the tremor's "
                         "cosine with the true gradient on the pressure coordinates is "
                         "+0.01: the hand would be turning a dial it cannot feel, and "
                         "the extra numbers would be dead weight sold as an improvement. "
                         "At 15 it is +0.84 while the xy block holds +0.91. This is legal "
                         "because a one-bit estimator points along the true gradient "
                         "weighted by sigma_i squared -- every weight is positive, so it "
                         "is still strictly uphill, just in a different metric. The pen "
                         "itself is untouched, so the measured ceiling still applies.")
    ap.add_argument("--snap", type=int, default=0)
    ap.add_argument("--table", action="store_true",
                    help="One row of strokes per letter instead of a gist->strokes map.")
    ap.add_argument("--k", type=int, default=32,
                    help="Tremors per step. Nothing here uses a gradient: each tremor "
                         "still sends back exactly one number.")
    ap.add_argument("--every", type=int, default=1000, help="report every N steps")
    ap.add_argument("--target", default="centroid", choices=("centroid", "pixels"),
                    help="WHAT the one returning scalar is about. 'centroid' is the "
                         "label-free loop this file was built for -- the hand is handed a "
                         "coordinate in the eye's space and never told a letter's name. "
                         "It is also, measured on 2026-08-30 and looked at, ADVERSARIAL: "
                         "its ceiling is scribble that scores 2.4x what a real printed "
                         "letter scores through the same eye, and an outside Hebrew OCR "
                         "reads it at chance. 'pixels' throws that away and shows the "
                         "hand a printed glyph to trace. That is SUPERVISED COPYING and "
                         "it is not the loop -- it is here to separate the learning RULE "
                         "from the broken objective, because with the eye's target you "
                         "cannot tell a rule that failed from a target that was never "
                         "worth reaching.")
    ap.add_argument("--looked-at", action="store_true",
                    help="Only pass this after a PERSON has opened the sheet (show.py) "
                         "and looked at it. The pen audit already looks mechanically and "
                         "Murphy accepts that; this is for the human's own signature.")
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--seed", type=int, default=1933)
    a = ap.parse_args(argv)

    torch.manual_seed(a.seed)
    dev = torch.device(a.device)
    enc = load_eye(a.eye, dev)

    d = np.load(a.data)
    X, y = d["X"].astype(np.float32), d["y"]
    cent, cls = centroids(enc, X, y, dev)
    n_cls = len(cls)
    npar = a.strokes * a.points * (3 if a.pressure else 2)
    print("hand: %d letters, pen = %d strokes x %d points%s = %d numbers per letter"
          % (n_cls, a.strokes, a.points,
             " with PRESSURE" if a.pressure else " (fixed nib)", npar))

    eye_in = torch.eye(n_cls, device=dev)
    # one real printed glyph per letter — only ever read when --target pixels
    tgt_img = torch.as_tensor(X[[np.where(y == c)[0][3] for c in range(n_cls)]],
                              device=dev)

    def score(img, c):
        """The ONE number that goes back. Everything else about the rule is unchanged."""
        if a.target == "pixels":
            return -((img - tgt_img[c]) ** 2).mean(dim=(1, 2))
        return (enc.gist(img) * cent[c]).sum(-1)

    hand = (Winston(n_cls, a.strokes, a.points, a.pressure) if a.table
            else Hand(hidden=a.hidden, strokes=a.strokes, points=a.points,
                      pressure=a.pressure)).to(dev)
    # decay=0 ON PURPOSE. An eligibility trace that lingers is right when the reward comes
    # late; here it arrives on the same beat, so a lingering trace means this step's verdict
    # is applied to a blend of tremors from earlier steps that had nothing to do with it.
    miko = ThreeFactor(hand, lr=a.lr / max(1, a.k), decay=0.0)
    params = ({"out": hand.out.weight.data.T} if a.table else
              {"fc1": hand.fc1.weight.data.T, "fc2": hand.fc2.weight.data.T,
               "out": hand.out.weight.data.T})
    os.makedirs(a.out, exist_ok=True)
    t0, log = time.time(), []
    allc = torch.arange(n_cls, device=dev)
    applied = -1

    # which of the pen's numbers are nib width, so the tremor can shake them differently
    nib_cols = None
    if a.pressure and a.wgain != 1.0:
        j = torch.arange(a.strokes * a.points * 3, device=dev).view(a.strokes,
                                                                   a.points, 3)
        nib_cols = torch.zeros(a.strokes * a.points * 3, dtype=torch.bool, device=dev)
        nib_cols[j[..., 2].reshape(-1)] = True

    # THE FLOOR, and this file did not have one until Murphy was wired in. The hand's
    # score was reported against chance, and chance is the wrong bar: the question is not
    # "better than guessing" but "better than a hand that never learned anything". So:
    # the SAME pen, the SAME eye, with the weights exactly as they were initialised.
    # Every claim below is measured against this number and can fall through it.
    with torch.no_grad():
        img0, _, _ = draw(hand, eye_in if a.table else cent)
        g0 = enc.gist(img0)
        floor = float(((g0 @ cent.T).argmax(1) == allc).float().mean())
        cos0 = float((g0 * cent).sum(-1).mean())
    print("  FLOOR: the untrained pen already reads back %.1f%% (cos %.4f). "
          "Anything at or under this is not learning." % (100 * floor, cos0))

    for step in range(1, a.steps + 1):
        if a.table:
            # ONE letter this beat. The verdict that comes back is about that letter and
            # nothing else, and the one-hot input means only its own row can move.
            c = int(torch.randint(0, n_cls, (1,), device=dev))
            oh = eye_in[c:c + 1].expand(a.k, -1)
            e3 = a.sigma * torch.randn(a.k, hand.out.out_features, device=dev)
            if nib_cols is not None:
                e3[:, nib_cols] *= a.wgain
            with torch.no_grad():
                xy, w = hand(oh, e3=e3)
                s_up = score(ink(xy, w), c)
                xy, w = hand(oh, e3=-e3)
                s_dn = score(ink(xy, w), c)
            sign = torch.where(s_up > s_dn, 1.0, -1.0)
            for k in range(a.k):
                miko.observe(eye_in[c:c + 1], e3[k:k + 1], "out")
                r = miko.apply(float(sign[k]), params)
            if applied < 0:
                applied = r["applied"]
                print("  MIKO updates %d matrix, %d tremors a beat, one letter a beat"
                      % (applied, a.k))

        if a.snap and (step % a.snap == 0 or step == 1):
            torch.save({"hand": hand.state_dict(), "step": step},
                       os.path.join(a.out, "snap-%07d.pt" % step))
        if step % a.every == 0 or step == a.steps:
            with torch.no_grad():
                img, xy, w = draw(hand, eye_in if a.table else cent)
                g2 = enc.gist(img)                   # judged WITHOUT the tremor
                hit = float(((g2 @ cent.T).argmax(1) == allc).float().mean())
                cos = float((g2 * cent).sum(-1).mean())
                mse = float(((img - tgt_img) ** 2).mean())
            log.append({"step": step, "eye_reads_back": hit, "cos": cos, "mse": mse})
            print("  step %6d  the eye reads back %.1f%% of what the hand drew  "
                  "(cos %.4f, pixel gap to a real glyph %.5f)  (%.0fs)"
                  % (step, 100 * hit, cos, mse, time.time() - t0), flush=True)

    with torch.no_grad():
        img, xy, w = draw(hand, eye_in if a.table else cent)
        marks = penmarks(img, xy, w)
    pieces = float(np.mean([m["pieces"] for m in marks]))
    stub = float(np.mean([m["stub"] for m in marks]))
    cover = float(np.mean([m["cover"] for m in marks]))
    audit_ok = (pieces <= AUDIT["pieces"] and stub <= AUDIT["stub"]
                and AUDIT["cover"][0] <= cover <= AUDIT["cover"][1])
    print("  pen audit: %.2f pieces per letter, %.0f%% of segments are stubs, "
          "%.3f of the page inked (printed corpus: 0.040)  -> %s"
          % (pieces, 100 * stub, cover,
             "these are LINES" if audit_ok else "THIS IS NOT WRITING"))

    torch.save({"hand": hand.state_dict(), "strokes": a.strokes, "points": a.points,
                "pressure": a.pressure, "table": a.table},
               os.path.join(a.out, a.tag + ".pt"))
    json.dump({"log": log, "chance": 1.0 / n_cls, "args": vars(a),
               "pen_audit": {"pieces": pieces, "stub": stub, "cover": cover},
               "marks": marks},
              open(os.path.join(a.out, a.tag + "-train.json"), "w"), indent=1)
    last = log[-1]["eye_reads_back"] if log else 0.0
    print("\nchance %.1f%%  |  untrained pen %.1f%%  |  the hand %.1f%%   %s"
          % (100.0 / n_cls, 100 * floor, 100 * last,
             "the eye can read the hand" if last > floor
             else "FAILS -- no better than the pen it started with"))

    # MURPHY. This is the file he was built for. On 2026-08-30 it scored 86.4% drawing
    # dot-clouds, and the only thing that caught it was a person opening the sheet.
    #
    # judge_in_loop is TRUE and there is no honest way to write anything else: the hand
    # is optimising the eye's opinion and the eye's opinion is the number printed above.
    # `looked_at` is therefore the whole verdict, and it is not a promise -- it is the pen
    # audit, which counts connected components and stub segments on the actual raster and
    # can say THIS IS NOT WRITING while the score says 86%. A failed audit is not a look
    # that passed, so a dot-cloud run lands in front of Murphy with nothing vouching for
    # it, exactly as it should have that morning.
    watch({"chance": 1.0 / n_cls, "baseline": floor,
           "held_out": ("the table hand is 22 rows for 22 letters -- there is no sample "
                        "to hold out, and the score is by construction a score on what "
                        "it memorised. It is not claimed to draw a letter it never met."
                        if a.table else False),
           "claimed_success": last > floor,
           "judge": "ERAN's own eye", "objective_by": "ERAN's own eye",
           "judge_in_loop": True, "artifact": "drawings",
           "looked_at": bool(audit_ok or a.looked_at), "independent": bool(audit_ok),
           "steps": [{"step": e["step"], "metric": e["eye_reads_back"],
                      "terms": {"gap_to_centroid": 1.0 - e["cos"]}} for e in log]},
          name="WINSTON the hand, %d strokes x %d points%s"
               % (a.strokes, a.points, ", pressure" if a.pressure else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
