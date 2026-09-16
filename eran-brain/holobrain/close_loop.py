"""CLOSING THE HOLOBRAIN IN BOTH DIRECTIONS — and asking whether the space generalises.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

Iddo, 2026-08-30: *"תסגור את ההולובריין לשני הכיוונים: שערן ישמע צליל ויצייר את האות.
ותסתיר אות שלמה מהקשירה ותראה לי אם צורה וצליל עדיין נפגשים בלעדיה."*

`zivug.py` closed one direction: show a SHAPE, get the SOUND — **88.2%** with six
typefaces and a whole recording take held out. Two things were never asked, and both
can fail.

> **2026-09-06, code revision.** That number used to read 87.6% here and in memory, and
> 87.6% is not on disk anywhere: the only artifact that survives, `state/sound2draw.json`,
> says `shape_to_sound_heldout_fonts` = 0.88155, and `state/zivug.json` — which would
> carry zivug.py's own figure — does not exist. The docstring is now quoting the
> artifact. Worse, **both experiments below had never been run**: `state/` held three
> files from 2026-08-30 and neither `letter-holdout.json` nor `pair-holdout.json` was
> among them, while the headline was carried for a week as though they had. A headline
> printed by this file is now STAMPED `[UNFALSIFIED]` until its falsifiers exist.

────────────────────────────────────────────────────────────────────────────────────
1. SOUND -> DRAWING.  He hears a human say a syllable, and his hand draws the letter.
────────────────────────────────────────────────────────────────────────────────────
The path is: a clip from the HELD-OUT TAKE -> the ear head -> a point in the shared
192-d space -> a hand that turns a point into three strokes -> ink -> the eye looks and
says which letter that was. Chance 4.5%.

THE SCRIBE IS NEVER SHOWN A SOUND AND NEVER SHOWN A LABEL. It is trained on the eye
side only: it is handed the shared-space point of a letter image from a TRAINING
typeface and asked to put strokes on paper that look, to the frozen eye, like the thing
that point came from. Loss = 1 - cos(gist(ink(strokes)), gist(image)). Nothing tells it
the letter's name, and nothing tells it that sounds exist. Sound at test time is the
experiment: if the two senses really share one space, a point that arrived through the
EAR is a point the hand can already draw.

Backprop, not MIKO, and I am saying so. `hand_eye.py` measured it: a tremor rule needs
about one trial per PARAMETER, and this map has thousands. Winston's 22x36 table is the
size a tremor can win, and Winston is reported here beside the scribe as the discrete
route — hear, decide which letter, draw the memorised row.

────────────────────────────────────────────────────────────────────────────────────
2. HOLD OUT A WHOLE LETTER.  Never bind shin at all. Do shape and sound still meet?
────────────────────────────────────────────────────────────────────────────────────
This is the question that decides what the 87.6% means. If the space generalises, an
unbound letter's shape still lands on its own syllable. If it does not, the space is
22 memorised pairs — still useful, but not what it would be claimed to be.

The letter is removed from the cross-modal loss entirely: its images never pass through
the eye head during training, and its syllable is never a positive on the ear side of a
pair. The ear's OWN self-supervised loss keeps all 22 syllables, deliberately — a child
hears sounds long before it is shown the letters, and if the held-out syllable had no
ear cluster at all the test would be rigged to fail.

**And a trap this test walks into.** With 21 of 22 pinned, a model can be right about
the 22nd by ELIMINATION — the one syllable nothing else claimed. So the same run is
also asked the two-letter version: hide two letters, and make it choose between just
those two. Chance there is 50%, elimination buys nothing, and only a real
shape-to-sound correspondence can beat it.

    python close_loop.py --mode sound2draw
    python close_loop.py --mode letterout
    python close_loop.py --mode pairout
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


def _addpath(*cands):
    for c in cands:
        if os.path.isdir(c):
            sys.path.insert(0, c)
            return c
    return None


_addpath(os.path.join(HERE, "..", "eye"), os.path.expanduser("~/eran-eye"))
_addpath(os.path.join(HERE, "..", "hand"), os.path.expanduser("~/eran-hand"))
_addpath(os.path.join(HERE, "..", "..", "miko", "model"),
         os.path.expanduser("~/miko/model"), r"D:\CLAUDE\miko\model")
_addpath(os.path.join(HERE, "..", "..", "murphy"), os.path.expanduser("~/murphy"),
         r"D:\CLAUDE\murphy")
sys.path.insert(0, HERE)                     # guards.py lives beside this file

from eye import CH, PATCH, SIZE, Encoder                            # noqa: E402
from hand_eye import Winston, ink, STROKES, POINTS                  # noqa: E402
import guards                                                       # noqa: E402

# ZIV-05: this file makes the STRONGER claims in the chain -- sound->drawing, the letter
# holdout, the pair holdout -- and it did not import murphy at all, against the rule
# quoted in murphy.py itself (Iddo, 2026-08-30: "שאף ריצה לא תדווח בלי פסק שלו").
# The fallback is loud on purpose: a judge who cannot be reached is a hole in the report,
# not an acquittal.
try:
    from murphy import watch                                        # noqa: E402
except Exception:                                                   # noqa: BLE001
    def watch(*_a, **_k):
        print("!! MURPHY IS NOT IMPORTABLE ON THIS BOX. No claim in this run has been "
              "ruled on, and that is a HOLE IN THE REPORT, not a pass.")
        return None

D = 192


# ══════════════════════════════════════════════════════════ the shared space

class Head(nn.Module):
    """Identical to zivug.py's, on purpose — a different head is a different number."""

    def __init__(self, d_in, d=D, hidden=384):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(d_in, hidden), nn.GELU(),
                                 nn.Linear(hidden, hidden), nn.GELU(),
                                 nn.Linear(hidden, d))

    def forward(self, x):
        return F.normalize(self.net(x), dim=-1)


def nt_xent(a, b, tau=0.12, labels=None):
    """ZIV-07: `labels` masks SAME-CLASS clips out of the denominator.

    Identical to zivug.py's, on purpose, including this fix. Without it, batch 128 drawn
    from 22 syllables pushes every anchor away from ~11.6 clips of its own syllable
    (measured: 11.56 of 254 negatives, 4.6%), and at tau=0.12 those are the highest-
    similarity negatives -- the ones the gradient is made of. The loss was fighting the
    objective on every step, in both files and in both terms.
    """
    z = torch.cat([a, b])
    n = a.shape[0]
    sim = (z @ z.T) / tau
    sim.fill_diagonal_(-1e4)
    tgt = torch.cat([torch.arange(n, 2 * n), torch.arange(0, n)]).to(z.device)
    if labels is not None:
        lab = torch.cat([labels, labels])
        same = lab[:, None] == lab[None, :]
        pos = torch.zeros_like(same)
        pos[torch.arange(2 * n, device=z.device), tgt] = True
        sim = sim.masked_fill(same & ~pos, -1e4)
    return F.cross_entropy(sim, tgt)


# The three runs that could FALSIFY a headline from this file. ZIV-02: --mode letterout
# and --mode pairout were written, documented at length, and never executed; ZIV-10: the
# scramble control printed to a terminal and was never persisted, so no run record of it
# existed either. A claim whose falsifiers have never been run is printed stamped.
FALSIFIERS = (("letter-holdout.json", "--mode letterout"),
              ("pair-holdout.json", "--mode pairout"),
              ("scramble.json", "--mode scramble"))


def falsification_stamp(out_dir):
    """Empty string when every falsifier has been run; a loud stamp when it has not."""
    missing = [(f, how) for f, how in FALSIFIERS
               if not os.path.exists(os.path.join(out_dir, f))]
    if not missing:
        return ""
    return ("\n      [UNFALSIFIED: %s never run -- %s absent from %s. Until they exist "
            "the honest statement is 'and we do not yet know whether that is a shared "
            "space or 22 memorised pairs'.]"
            % (", ".join(h for _, h in missing), ", ".join(f for f, _ in missing),
               out_dir))


def load_zivug_heads(path, dev, want):
    """The binding zivug.py trained -- instead of a second, different one trained here.

    ZIV-03: `state/zivug.pt` was written by zivug.py and loaded by NOBODY. grep over the
    whole eran-brain tree found exactly two references to that filename, the save and the
    print on the next line. This file threw it away and retrained its own heads at 4000
    steps against zivug.py's 6000 -- same Head class, different budget, no shared
    checkpoint -- so the two files' numbers described two different models and were
    reported as one result. Returns (heads, why) or (None, why-not); the reason is
    printed either way, so which checkpoint produced a number is never a guess.
    """
    if not os.path.exists(path):
        return None, "no checkpoint at %s" % path
    ck = torch.load(path, map_location="cpu")
    if "ear_head" not in ck or "eye_head" not in ck:
        return None, "%s is not a zivug checkpoint" % os.path.basename(path)
    meta = ck.get("meta") or {}
    if not meta:
        return None, ("%s carries no meta (steps/seed/holdout/corpus) -- it predates the "
                      "2026-09-06 revision and cannot be checked against this run"
                      % os.path.basename(path))
    for k in ("holdout_take", "holdout_fonts", "seed"):
        if meta.get(k) != want.get(k):
            return None, ("%s was trained with %s=%r and this run wants %r"
                          % (os.path.basename(path), k, meta.get(k), want.get(k)))
    for k in ("ear", "letters", "eye"):
        if not guards.same_corpus((meta.get("corpus") or {}).get(k), want["corpus"][k]):
            return None, ("the %s in %s is not the %s on disk now"
                          % (k, os.path.basename(path), k))
    ear_h, eye_h = Head(192).to(dev), Head(192).to(dev)
    ear_h.load_state_dict(ck["ear_head"])
    eye_h.load_state_dict(ck["eye_head"])
    ear_h.eval()
    eye_h.eval()
    return (ear_h, eye_h), ("LOADED %s -- trained by zivug.py, %s steps, seed %s, best "
                            "eval at step %s (SHAPE->SOUND %.1f%%)"
                            % (path, meta.get("steps"), meta.get("seed"),
                               meta.get("best_step"),
                               100 * (meta.get("best_shape_to_sound") or 0.0)))


def murphy_verdict(name, metric, baseline, chance, artifact=None, looked_at=False,
                   judge="", steps=None):
    """One claim, one floor, one ruling -- and the ruling is CAPTURED, not printed away.

    ZIV-05: four claims are made in this file and murphy was not imported at all.
    """
    v = watch({"chance": chance, "baseline": baseline, "held_out": True,
               "judge_in_loop": False, "artifact": artifact, "looked_at": looked_at,
               "independent": True, "judge": judge,
               "objective_by": "nt-xent over pairs; the scribe by 1-cos against the "
                               "frozen eye, which never sees a sound or a label",
               "claimed_success": bool(metric > baseline),
               "steps": steps or [{"step": 1, "metric": metric, "terms": {}}]},
              name=name)
    if not isinstance(v, dict):
        return {"fooling": False, "score": None, "metric": metric, "baseline": baseline,
                "note": "murphy did not rule"}
    return {"fooling": bool(v.get("fooling")), "score": v.get("score"),
            "metric": metric, "baseline": baseline,
            "spoke": list(v.get("spoke") or []),
            "undeclared": list(v.get("undeclared") or [])}


def centroids(feat, y, n_cls):
    """Where each class lives. Every class must be present or the ruler has a gap."""
    out = []
    for c in range(n_cls):
        m = y == c
        assert bool(m.any()), "class %d has no keys -- the candidate set is broken" % c
        out.append(feat[m].mean(0))
    return F.normalize(torch.stack(out), dim=-1)


def rank_acc(q, cent, qy, restrict=None):
    """Nearest centroid, and WHERE the right answer came in the ranking.

    The rank matters: 4.5% top-1 with a mean rank of 11.5 is chance, but 4.5% top-1
    with a mean rank of 6 is a space that knows something and cannot say it.
    """
    if q.numel() == 0:
        # ZIV-12: this used to return nan, and letter_holdout() averaged those with
        # np.mean -- so a letter with no held-out images would have poisoned the headline
        # to nan instead of raising. That is the same shape as ERAN's empty-menu
        # starvation on 2026-09-06: a filter that can select nothing, returning a number
        # instead of an error. An empty slice is not data.
        raise guards.Refused(
            "rank_acc was handed an EMPTY query set. Some mask selected nothing -- "
            "probably a letter with no held-out typefaces or a syllable with no clips in "
            "the held-out take. Fix the mask; do not average a nan into a headline.")
    s = q @ cent.T
    if restrict is not None:
        keep = torch.zeros(cent.shape[0], dtype=torch.bool, device=q.device)
        keep[restrict] = True
        s = s.masked_fill(~keep, -1e4)
    order = s.argsort(dim=1, descending=True)
    rank = (order == qy[:, None]).float().argmax(1) + 1
    return (float((rank == 1).float().mean()), float(rank.float().mean()), int(len(qy)))


# ══════════════════════════════════════════════════════════ the world

class World:
    def __init__(self, a, dev):
        self.dev = dev
        d = np.load(a.ear, allow_pickle=True)
        self.V = torch.as_tensor(d["V"].astype(np.float32), device=dev)
        self.ey = torch.as_tensor(d["y"].astype(np.int64), device=dev)
        self.et = torch.as_tensor(d["t"].astype(np.int64), device=dev)
        self.syl = [str(s) for s in d["syllables"]]
        self.n_syl = len(self.syl)
        self.n_take = int(self.et.max()) + 1
        self.hold_take = a.holdout_take
        self.t_tr = self.et != a.holdout_take
        self.t_te = self.et == a.holdout_take

        # ZIV-01: this used to die with a bare `size mismatch for proj.weight`, six days
        # running, with nothing saying which of the two files had moved. eye.pt is a
        # GRAYSCALE encoder and the corpus went to colour on 2026-08-31.
        eye_ck = guards.check_eye_checkpoint(a.eye, a.letters, PATCH, CH)
        # ZIV-14: and this is what the checkpoint does NOT say -- eye.py's --holdout
        # defaults to 0, so "the eye encoder never saw them" was printed against a
        # checkpoint that records no holdout at all.
        self.enc_hold = guards.encoder_holdout(eye_ck)
        self.fp = {"ear": guards.fingerprint(a.ear, "V"),
                   "letters": guards.fingerprint(a.letters, "X"),
                   "eye": guards.fingerprint(a.eye)}
        self.enc = Encoder().to(dev)
        self.enc.load_state_dict(eye_ck["encoder"])
        self.enc.eval()
        for p in self.enc.parameters():
            p.requires_grad_(False)

        L = np.load(a.letters)
        self.LX = torch.as_tensor(L["X"].astype(np.float32), device=dev)
        self.ly = torch.as_tensor(L["y"].astype(np.int64), device=dev)
        self.lf = torch.as_tensor(L["f"].astype(np.int64), device=dev)
        self.n_let = int(self.ly.max()) + 1
        self.f_cut = int(self.lf.max()) + 1 - a.holdout_fonts
        self.l_tr, self.l_te = self.lf < self.f_cut, self.lf >= self.f_cut
        with torch.no_grad():
            self.G = torch.cat([self.enc.gist(self.LX[i:i + 512])
                                for i in range(0, len(self.LX), 512)])

        meta = json.load(open(a.meta, encoding="utf-8"))["letters"]
        self.meta = meta
        self.l2s = torch.as_tensor([self.syl.index(m["syllable"]) for m in meta],
                                   dtype=torch.long, device=dev)
        s2l = torch.zeros(self.n_syl, dtype=torch.long, device=dev)
        s2l[self.l2s] = torch.arange(self.n_let, device=dev)
        self.s2l = s2l
        assert self.n_syl == self.n_let, "one letter, one syllable -- or the map is wrong"

        # rectangular table for sampling: (syllable, take, clip)
        per = len(self.V) // (self.n_syl * self.n_take)
        T = torch.full((self.n_syl, self.n_take, per), -1, dtype=torch.long, device=dev)
        fill = torch.zeros(self.n_syl, self.n_take, dtype=torch.long, device=dev)
        for i in range(len(self.V)):
            c, t = int(self.ey[i]), int(self.et[i])
            T[c, t, fill[c, t]] = i
            fill[c, t] += 1
        assert (T >= 0).all(), "the reference set is not rectangular"
        self.T, self.per = T, per
        self.train_takes = torch.tensor(
            [t for t in range(self.n_take) if t != a.holdout_take], device=dev)

        # the eye's own ruler, built from TRAINING typefaces only.
        self.cent_eye_raw = centroids(self.G[self.l_tr], self.ly[self.l_tr], self.n_let)

    def name(self, c):
        return "%s/%s" % (self.meta[c]["name"], self.meta[c]["syllable"])

    def pick(self, c, gen, exclude=None):
        k = torch.randint(0, len(self.train_takes), c.shape, device=self.dev, generator=gen)
        t = self.train_takes[k]
        if exclude is not None:
            t = torch.where(t == exclude,
                            self.train_takes[(k + 1) % len(self.train_takes)], t)
        r = torch.randint(0, self.per, c.shape, device=self.dev, generator=gen)
        return self.T[c, t, r], t


def train_heads(w, steps=4000, batch=128, lr=1e-3, seed=1933, exclude=(),
                scramble=False, verbose=False):
    """Bind shape to sound. `exclude` letters are NEVER bound — neither side of the pair."""
    dev = w.dev
    torch.manual_seed(seed)
    gen = torch.Generator(device=dev).manual_seed(seed)
    ear_h, eye_h = Head(192).to(dev), Head(192).to(dev)
    opt = torch.optim.AdamW(list(ear_h.parameters()) + list(eye_h.parameters()),
                            lr=lr, weight_decay=0.01)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, lr, total_steps=steps, pct_start=0.2)

    keep = w.l_tr.clone()
    for c in exclude:
        keep &= w.ly != c
    pool = torch.nonzero(keep).squeeze(1)

    l2s = w.l2s
    if scramble:                       # the control: bind every shape to the WRONG sound
        g = torch.Generator(device="cpu").manual_seed(seed + 7)
        p = torch.randperm(w.n_syl, generator=g)
        while bool((p == torch.arange(w.n_syl)).any()):
            p = torch.randperm(w.n_syl, generator=g)
        l2s = p.to(dev)[w.l2s]

    t0 = time.time()
    for step in range(1, steps + 1):
        want = torch.randint(0, w.n_syl, (batch,), device=dev, generator=gen)
        i, ti = w.pick(want, gen)
        j, _ = w.pick(want, gen, exclude=ti)
        l_ear = nt_xent(ear_h(w.V[i]), ear_h(w.V[j]), labels=want)

        li = pool[torch.randint(0, len(pool), (batch,), device=dev, generator=gen)]
        s_of = l2s[w.ly[li]]
        k, _ = w.pick(s_of, gen)
        l_bind = nt_xent(eye_h(w.G[li]), ear_h(w.V[k]), labels=s_of)

        loss = l_ear + l_bind
        opt.zero_grad(set_to_none=True)
        loss.backward()
        opt.step()
        sched.step()
        if verbose and (step % 1000 == 0 or step == steps):
            print("    step %5d  loss %.3f  (%.0fs)" % (step, float(loss),
                                                        time.time() - t0), flush=True)
    ear_h.eval()
    eye_h.eval()
    return ear_h, eye_h


# ══════════════════════════════════════════════════════════ 1. SOUND -> DRAWING

class Scribe(nn.Module):
    """A point in the shared space in, three strokes out. Small, so it cannot cheat.

    36 numbers of output and 3 real strokes: `ink` draws SEGMENTS, not sampled dots, so
    the constellation trick that scored 86% on unreadable dot-clouds is not available.
    """

    def __init__(self, d=D, hidden=256):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(d, hidden), nn.GELU(),
                                 nn.Linear(hidden, hidden), nn.GELU(),
                                 nn.Linear(hidden, STROKES * POINTS * 2))

    def forward(self, z):
        return (torch.tanh(self.net(z)) * 0.85).view(-1, STROKES, POINTS, 2)


@torch.no_grad()
def cross_modal_gap(w, ear_h, eye_h):
    """How far a SOUND lands from the SHAPE it is bound to — on BOTH distributions.

    The scribe is trained on eye-side points and tested on ear-side points, so the noise
    it is trained through has to be at least as wide as the gap between the two. Guessing
    that width is how a pathway quietly fails: jitter 0.15 in 192 dimensions has a norm of
    2.08 against a unit vector — it does not blur the point, it erases it.

    ZIV-08, 2026-09-06: this returned the TRAINING gap only, and the noise was derived
    from it — while the gap the scribe must actually cross at test time is to HELD-OUT-
    TAKE ear points, which is wider. Measured on the ear side alone: mean cosine to the
    own-syllable training centroid is 0.9088 for training clips and 0.8932 for the
    held-out take, which through this file's own formula is jitter 0.0331 vs 0.0363 —
    the derived noise was ~30% narrower than the gap it was meant to span. The file's own
    docstring warned that guessing this width "is how a pathway quietly fails", and it
    was derived from the friendly side. Both are returned now; the caller takes the
    WIDER gap (the SMALLER cosine).
    """
    cent_ear = centroids(ear_h(w.V[w.t_tr]), w.ey[w.t_tr], w.n_syl)
    Z = eye_h(w.G[w.l_tr])
    cross = float((Z * cent_ear[w.l2s[w.ly[w.l_tr]]]).sum(-1).mean())
    cent_eye = centroids(Z, w.ly[w.l_tr], w.n_let)
    within = float((Z * cent_eye[w.ly[w.l_tr]]).sum(-1).mean())
    # the distribution the scribe will actually meet: a HELD-OUT-take sound, against the
    # eye-side centroid it has to land on.
    Ze = ear_h(w.V[w.t_te])
    cross_te = float((Ze * cent_eye[w.s2l[w.ey[w.t_te]]]).sum(-1).mean())
    return cross, within, cross_te


def train_scribe(w, eye_h, steps=4000, batch=64, lr=2e-3, jitter=0.05, seed=1933,
                 hidden=256, proto_k=0, verbose=True):
    """Three strokes cannot reproduce a particular typeface's glyph, and asking for that
    is asking for a shape nobody can draw. `proto_k` aims instead at the average of a
    point's k nearest neighbours IN THE EYE'S OWN SPACE — a prototype the eye found by
    itself. No label is used to build it; the neighbours are whatever the eye put nearby.
    """
    dev = w.dev
    torch.manual_seed(seed + 1)
    gen = torch.Generator(device=dev).manual_seed(seed + 1)
    scribe = Scribe(hidden=hidden).to(dev)
    opt = torch.optim.AdamW(scribe.parameters(), lr=lr, weight_decay=0.0)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, lr, total_steps=steps, pct_start=0.2)
    pool = torch.nonzero(w.l_tr).squeeze(1)          # TRAINING typefaces only
    with torch.no_grad():
        Z = eye_h(w.G)                               # the shared-space address of a shape
        tgt = w.G.clone()
        if proto_k:
            Gp = w.G[pool]
            nb = (Gp @ Gp.T).topk(proto_k, dim=1).indices
            proto = F.normalize(Gp[nb].mean(1), dim=-1)
            tgt = tgt.clone()
            tgt[pool] = proto
            purity = float((w.ly[pool][nb] == w.ly[pool][:, None]).float().mean())
            if verbose:
                print("    prototype target: %d nearest neighbours in the eye's own "
                      "space; %.1f%% of them happen to be the same letter (no label was "
                      "used to pick them)" % (proto_k, 100 * purity))
    t0 = time.time()
    for step in range(1, steps + 1):
        i = pool[torch.randint(0, len(pool), (batch,), device=dev, generator=gen)]
        z = F.normalize(Z[i] + jitter * torch.randn(
            batch, D, device=dev, generator=gen), dim=-1)
        g = w.enc.gist(guards.ink_to_eye(ink(scribe(z)), CH))
        loss = 1.0 - (g * tgt[i]).sum(-1).mean()
        opt.zero_grad(set_to_none=True)
        loss.backward()
        opt.step()
        sched.step()
        if verbose and (step % 1000 == 0 or step == steps):
            print("    scribe step %5d  1-cos %.4f  (%.0fs)"
                  % (step, float(loss.detach()), time.time() - t0), flush=True)
    scribe.eval()
    return scribe


@torch.no_grad()
def read_back(w, points):
    """Ink the strokes, look with the frozen eye, name the letter. The eye is the judge."""
    # ZIV-16: the hand draws one channel; the eye reads CH. This seam has been broken
    # since the corpus went to colour on 2026-08-31 and nothing said so, because the
    # chain never got past loading the encoder.
    g = w.enc.gist(guards.ink_to_eye(ink(points), CH))
    return (g @ w.cent_eye_raw.T).argmax(1), g


def _components(mask):
    """4-connected components, plain flood fill. 64x64; nothing clever is needed."""
    h, wd = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    n = 0
    for sy in range(h):
        for sx in range(wd):
            if not mask[sy, sx] or seen[sy, sx]:
                continue
            n += 1
            stack = [(sy, sx)]
            seen[sy, sx] = True
            while stack:
                y, x = stack.pop()
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < h and 0 <= nx < wd and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
    return n


def pen_check(sheet, thr=0.35):
    """Is it a LINE, or the dot-cloud trick again?

    On 2026-08-30 a hand scored 86% drawing constellations no person would call a letter
    and the number said nothing about it. A drawing that reads back at 90% with fourteen
    disconnected pieces is that failure wearing a different hat, so this is measured on
    every sheet rather than assumed away. The printed corpus covers ~4% of the page.
    """
    a = sheet > thr
    pieces = [_components(a[i]) for i in range(len(a))]
    return {"pieces_mean": float(np.mean(pieces)), "pieces_max": int(np.max(pieces)),
            "one_or_two_pieces": float(np.mean([p <= 2 for p in pieces])),
            "cover_mean": float(a.mean())}


def sound_to_drawing(w, a):
    dev = w.dev
    print("\n" + "=" * 78)
    print("1. SOUND -> DRAWING     he hears a human, and his hand draws the letter")
    print("=" * 78)
    print("HOLDOUTS, named:  ear take %d (never trained on, %d clips)  |  typefaces "
          "%d-%d (the BINDING never saw them; the ENCODER's own holdout is %s)"
          % (w.hold_take, int(w.t_te.sum()), w.f_cut, int(w.lf.max()),
             ("%d faces, recorded in eye.pt" % w.enc_hold) if w.enc_hold is not None
             else "UNKNOWN -- eye.pt records none, so that half is NOT established"))

    # ZIV-03: use the binding zivug.py trained, when it is the same experiment. One model
    # producing all the numbers, or an explicit line saying why not.
    want = {"holdout_take": a.holdout_take, "holdout_fonts": a.holdout_fonts,
            "seed": a.seed, "corpus": w.fp}
    heads, why = ((None, "--retrain-heads was passed") if a.retrain_heads
                  else load_zivug_heads(a.zivug, dev, want))
    if heads is None:
        print("  binding: TRAINED HERE, %d steps, seed %d  (%s)" % (a.steps, a.seed, why))
        ear_h, eye_h = train_heads(w, steps=a.steps, seed=a.seed, verbose=True)
        binding = "close_loop.py, %d steps, seed %d" % (a.steps, a.seed)
    else:
        ear_h, eye_h = heads
        print("  binding: %s" % why)
        binding = why
    with torch.no_grad():
        E_tr = ear_h(w.V[w.t_tr])
        cent_ear = centroids(E_tr, w.ey[w.t_tr], w.n_syl)
        cross = rank_acc(eye_h(w.G[w.l_te]), cent_ear, w.l2s[w.ly[w.l_te]])
        # the floor zivug.py measures and this file quoted chance against: what the two
        # senses retrieve across each other with NO binding at all.
        raw = F.normalize(w.V, dim=-1)
        cross_floor = rank_acc(F.normalize(w.G[w.l_te], dim=-1),
                               centroids(raw[w.t_tr], w.ey[w.t_tr], w.n_syl),
                               w.l2s[w.ly[w.l_te]])[0]
    print("  the forward direction still stands: SHAPE->SOUND %.1f%% on held-out "
          "typefaces (chance %.1f%%, no-binding floor %.1f%%)%s"
          % (100 * cross[0], 100.0 / w.n_syl, 100 * cross_floor,
             falsification_stamp(a.out)))

    c_cross, c_within, c_cross_te = cross_modal_gap(w, ear_h, eye_h)
    jitter = a.jitter
    if jitter < 0:      # match the noise to the gap the scribe will actually have to cross
        c_use = min(c_cross, c_cross_te)          # the WIDER gap, not the friendlier one
        jitter = min(0.20, float(np.sqrt(max(1.0 / max(c_use, 1e-3) ** 2 - 1, 0) / D)))
    print("  the gap the scribe must cross: on TRAINING data a shape sits at cos %.3f "
          "from its own sound's centre and cos %.3f from its own shape's centre;\n"
          "  on the HELD-OUT TAKE -- the distribution the scribe actually meets -- a "
          "sound sits at cos %.3f from the shape's centre it must land on"
          "\n  -> training the scribe through noise of sigma %.3f (cos %.2f), taken "
          "from the WIDER of the two"
          % (c_cross, c_within, c_cross_te, jitter,
             1.0 / np.sqrt(1.0 + jitter * jitter * D)))
    scribe = train_scribe(w, eye_h, steps=a.scribe_steps, seed=a.seed, jitter=jitter,
                          hidden=a.scribe_hidden, proto_k=a.proto_k)

    res = {}
    with torch.no_grad():
        # --- the pathway's own ceiling: feed it SHAPES, not sounds ------------------
        for tag, msk in (("shape_train_fonts", w.l_tr), ("shape_heldout_fonts", w.l_te)):
            idx = torch.nonzero(msk).squeeze(1)
            hit = 0
            for s in range(0, len(idx), 512):
                b = idx[s:s + 512]
                hit += int((read_back(w, scribe(eye_h(w.G[b])))[0] == w.ly[b]).sum())
            res[tag] = hit / len(idx)

        # --- the real thing: a HELD-OUT TAKE's sound, per clip ----------------------
        zs = ear_h(w.V[w.t_te])
        true_letter = w.s2l[w.ey[w.t_te]]
        drew, _ = read_back(w, scribe(zs))
        res["sound_heldout_take_perclip"] = float((drew == true_letter).float().mean())
        res["n_clips"] = int(w.t_te.sum())

        # --- and once per syllable, the three clips averaged ------------------------
        zc = F.normalize(torch.stack([zs[w.ey[w.t_te] == c].mean(0)
                                      for c in range(w.n_syl)]), dim=-1)
        pts = scribe(zc)
        drew_c, _ = read_back(w, pts)
        want_c = w.s2l[torch.arange(w.n_syl, device=dev)]
        res["sound_heldout_take_persyllable"] = float((drew_c == want_c).float().mean())

        # --- FLOOR 1: the same scribe, fed noise. What does the eye read then? ------
        rnd = F.normalize(torch.randn(200, D, device=dev), dim=-1)
        rdrew, _ = read_back(w, scribe(rnd))
        res["floor_random_points"] = float(
            (rdrew == torch.randint(0, w.n_let, (200,), device=dev)).float().mean())
        res["floor_random_points_distinct"] = int(len(set(rdrew.tolist())))

        # --- FLOOR 2: shuffle which sound belongs to which letter ------------------
        gsh = torch.Generator(device="cpu").manual_seed(a.seed + 3)
        sh = torch.randperm(w.n_syl, generator=gsh).to(dev)
        res["floor_shuffled_pairing"] = float((drew == sh[w.ey[w.t_te]]).float().mean())

        # --- the DISCRETE route, for comparison: decide, then draw Winston's row ----
        # ZIV-11: a missing hand.pt used to make three keys simply not appear in `res`,
        # with no warning -- a missing organ reading as a shorter report.
        win = None
        if a.no_hand:
            res["winston"] = "SKIPPED: --no-hand was passed"
            print("\n  WINSTON: SKIPPED ON PURPOSE (--no-hand). The discrete route is "
                  "not measured in this run.")
        elif not os.path.exists(a.hand):
            raise guards.Refused(
                "WINSTON's hand is missing: %s does not exist.\n"
                "  The discrete route -- hear, decide, draw the memorised row -- cannot "
                "be measured without it, and dropping three keys out of `res` silently "
                "is how a claim disappears with nobody noticing. Pass --no-hand to run "
                "the continuous route deliberately." % a.hand)
        else:
            hand = Winston(w.n_let).to(dev)
            hand.load_state_dict(torch.load(a.hand, map_location=dev)["hand"])
            hand.eval()
            wp = hand(torch.eye(w.n_let, device=dev))[0]
            res["winston_alone_readback"] = float(
                (read_back(w, wp)[0] == torch.arange(w.n_let, device=dev)).float().mean())
            cent_eye_shared = centroids(eye_h(w.G[w.l_tr]), w.ly[w.l_tr], w.n_let)
            chosen = (zs @ cent_eye_shared.T).argmax(1)
            res["sound_picks_letter"] = float((chosen == true_letter).float().mean())
            res["sound_winston_drawing"] = float(
                (read_back(w, wp[chosen])[0] == true_letter).float().mean())
            res["winston"] = "measured"
            win = True

    print("\n  --- what the eye reads back from what the hand drew ---")
    print("  chance                                                   %.1f%%"
          % (100.0 / w.n_let))
    print("  scribe fed a SHAPE, training typefaces                    %.1f%%"
          % (100 * res["shape_train_fonts"]))
    print("  scribe fed a SHAPE, HELD-OUT typefaces                    %.1f%%   "
          "<- the pathway's ceiling" % (100 * res["shape_heldout_fonts"]))
    print("  SCRIBE FED A SOUND, HELD-OUT TAKE %d, per clip (n=%d)      %.1f%%"
          % (w.hold_take, res["n_clips"], 100 * res["sound_heldout_take_perclip"]))
    print("  SCRIBE FED A SOUND, HELD-OUT TAKE %d, per syllable (n=22)  %.1f%%"
          % (w.hold_take, 100 * res["sound_heldout_take_persyllable"]))
    print("  floor: the same scribe fed RANDOM points                  %.1f%%  "
          "(%d distinct letters drawn)"
          % (100 * res["floor_random_points"], res["floor_random_points_distinct"]))
    print("  floor: sound->drawing scored against a SHUFFLED pairing   %.1f%%"
          % (100 * res["floor_shuffled_pairing"]))
    if win:
        print("\n  --- the discrete route: hear, decide, draw the memorised row ---")
        print("  Winston's 22 rows alone, read back by the eye             %.1f%%"
              % (100 * res["winston_alone_readback"]))
        print("  sound -> which letter (no drawing)                        %.1f%%"
              % (100 * res["sound_picks_letter"]))
        print("  sound -> Winston draws -> the eye reads                   %.1f%%"
              % (100 * res["sound_winston_drawing"]))

    # keep the actual pictures. A number about a drawing that nobody looked at is the
    # 2026-08-30 dot-cloud all over again.
    os.makedirs(a.out, exist_ok=True)
    with torch.no_grad():
        sheet = ink(pts).cpu().numpy()
        # ROW i IS SYLLABLE i, NOT LETTER i. The first sheet was saved with a
        # letter-indexed reference glyph beside a syllable-indexed drawing, so from the
        # second row on every picture sat next to the wrong letter and one cell read
        # "pa -> pa" as a mistake. The accuracy was right and the picture was a lie.
        ref = torch.stack([w.LX[(w.ly == int(want_c[i])) & w.l_te][0]
                           for i in range(w.n_syl)])
    res["pen"] = pen_check(sheet)
    print("\n  --- and is it a LINE? the 22 sound-driven drawings ---")
    print("  connected pieces per drawing: mean %.1f, worst %d; %.0f%% are one or two "
          "pieces; page covered %.3f (the printed corpus covers ~0.040)"
          % (res["pen"]["pieces_mean"], res["pen"]["pieces_max"],
             100 * res["pen"]["one_or_two_pieces"], res["pen"]["cover_mean"]))
    np.savez_compressed(os.path.join(a.out, "sound-drawings.npz"),
                        drawn=sheet, ref=ref.cpu().numpy(),
                        read=drew_c.cpu().numpy(), want=want_c.cpu().numpy(),
                        heard=np.array(w.syl),
                        drew=np.array([w.meta[int(c)]["syllable"] for c in drew_c]),
                        names=np.array([w.name(c) for c in range(w.n_let)]))
    res["chance"] = 1.0 / w.n_let
    res["shape_to_sound_heldout_fonts"] = cross[0]
    res["shape_to_sound_no_binding_floor"] = cross_floor
    res["binding"] = binding
    res["cross_modal_cos"] = c_cross
    res["within_modal_cos"] = c_within
    res["cross_modal_cos_heldout_take"] = c_cross_te
    res["jitter"] = jitter
    res["encoder_holdout"] = w.enc_hold
    res["corpus"] = w.fp
    res["unfalsified"] = falsification_stamp(a.out) != ""
    # ZIV-08's other half: c_cross and c_within equal to four decimals is what a COLLAPSED
    # space looks like, and the run that produced state/sound2draw.json had 0.95005 vs
    # 0.95023 with 200 random points drawing only 6 distinct letters. Both signals were
    # computed and neither triggered anything.
    res["collapse_warning"] = bool(
        abs(c_cross - c_within) < 0.005
        or res.get("floor_random_points_distinct", w.n_let) < max(2, w.n_let // 3))
    if res["collapse_warning"]:
        print("\n  !! COLLAPSE WARNING: cross %.5f vs within %.5f, and %d of %d distinct "
              "letters from 200 random points. The shape space may have fallen onto the "
              "sound space -- do not quote a number from this run without saying so."
              % (c_cross, c_within, res.get("floor_random_points_distinct", -1), w.n_let))
    res["murphy"] = {
        "shape_to_sound": murphy_verdict(
            "SHAPE -> SOUND on held-out typefaces (floor: no binding at all)",
            cross[0], cross_floor, 1.0 / w.n_syl,
            judge="class identity on held-out faces; the map is in the corpus"),
        "sound_to_drawing": murphy_verdict(
            "SOUND -> DRAWING, held-out take (floor: the SHUFFLED pairing)",
            res["sound_heldout_take_perclip"], res["floor_shuffled_pairing"],
            1.0 / w.n_let, artifact=os.path.join(a.out, "sound-drawings.npz"),
            looked_at=True,
            judge="the frozen eye names the letter; pen_check counts the strokes")}
    res["holdout_take"] = w.hold_take
    res["holdout_fonts_from"] = w.f_cut
    res["steps"] = a.steps
    res["scribe_steps"] = a.scribe_steps
    res["proto_k"] = a.proto_k
    json.dump(res, open(os.path.join(a.out, "sound2draw.json"), "w"), indent=1)
    torch.save({"scribe": scribe.state_dict(), "ear_head": ear_h.state_dict(),
                "eye_head": eye_h.state_dict()}, os.path.join(a.out, "scribe.pt"))
    print("\n  saved the actual drawings -> %s"
          % os.path.join(a.out, "sound-drawings.npz"))
    return res


# ══════════════════════════════════════════════════════════ 2. HOLD OUT A LETTER

@torch.no_grad()
def probe(w, ear_h, eye_h, letters, restrict=None):
    """For each held-out letter: does its SHAPE find its SOUND, and the reverse?"""
    dev = w.dev
    E_tr = ear_h(w.V[w.t_tr])
    cent_ear = centroids(E_tr, w.ey[w.t_tr], w.n_syl)
    cent_eye = centroids(eye_h(w.G[w.l_tr]), w.ly[w.l_tr], w.n_let)
    r_syl = None if restrict is None else w.l2s[torch.tensor(restrict, device=dev)]
    r_let = None if restrict is None else torch.tensor(restrict, device=dev)
    out = {}
    for c in letters:
        m = w.l_te & (w.ly == c)                     # HELD-OUT typefaces of that letter
        sh = rank_acc(eye_h(w.G[m]), cent_ear,
                      w.l2s[w.ly[m]], restrict=r_syl)
        s = w.l2s[c]
        mk = w.t_te & (w.ey == s)                    # HELD-OUT take of that syllable
        so = rank_acc(ear_h(w.V[mk]), cent_eye,
                      w.s2l[w.ey[mk]], restrict=r_let)
        out[c] = {"shape_to_sound": sh, "sound_to_shape": so}
    # the same run's BOUND letters, so we can see the run itself worked
    bound = torch.ones(w.n_let, dtype=torch.bool, device=dev)
    bound[torch.tensor(list(letters), device=dev)] = False
    mb = w.l_te & bound[w.ly]
    out["bound"] = rank_acc(eye_h(w.G[mb]), cent_ear, w.l2s[w.ly[mb]])
    return out


def letter_holdout(w, a):
    print("\n" + "=" * 78)
    print("2. A WHOLE LETTER HELD OUT OF THE BINDING     22 runs, one per letter")
    print("=" * 78)
    print("HOLDOUTS, named:  ear take %d  |  typefaces %d-%d  |  and in each run ONE "
          "LETTER is never bound at all" % (w.hold_take, w.f_cut, int(w.lf.max())))
    print("chance %.1f%%   mean rank at chance %.1f\n" % (100.0 / w.n_syl,
                                                          (w.n_syl + 1) / 2))
    rows, t0 = [], time.time()
    for c in range(w.n_let):
        ear_h, eye_h = train_heads(w, steps=a.steps, seed=a.seed, exclude=(c,))
        p = probe(w, ear_h, eye_h, [c])
        sh, so, bd = p[c]["shape_to_sound"], p[c]["sound_to_shape"], p["bound"]
        rows.append({"letter": c, "name": w.name(c),
                     "shape_to_sound": sh[0], "shape_rank": sh[1], "n_shape": sh[2],
                     "sound_to_shape": so[0], "sound_rank": so[1], "n_sound": so[2],
                     "bound_21_shape_to_sound": bd[0]})
        print("  %-12s UNBOUND  shape->sound %5.1f%% (rank %4.1f, n=%3d)   "
              "sound->shape %5.1f%% (rank %4.1f, n=%d)   |  the 21 bound: %.1f%%  (%.0fs)"
              % (w.name(c), 100 * sh[0], sh[1], sh[2], 100 * so[0], so[1], so[2],
                 100 * bd[0], time.time() - t0), flush=True)

    # ZIV-12: rank_acc now raises on an empty query set, so a nan cannot reach here --
    # this assert is the second lock, and it names the row instead of printing "nan%".
    bad = [r["name"] for r in rows
           if any(np.isnan(r[k]) for k in ("shape_to_sound", "sound_to_shape"))]
    assert not bad, "these letters produced nan and must not be averaged: %s" % bad
    sh = float(np.mean([r["shape_to_sound"] for r in rows]))
    so = float(np.mean([r["sound_to_shape"] for r in rows]))
    shr = float(np.mean([r["shape_rank"] for r in rows]))
    sor = float(np.mean([r["sound_rank"] for r in rows]))
    bd = float(np.mean([r["bound_21_shape_to_sound"] for r in rows]))
    top1 = sum(1 for r in rows if r["shape_to_sound"] > 0.5)
    print("\n  " + "-" * 74)
    print("  THE UNBOUND LETTER, averaged over all 22 runs")
    print("    shape -> sound   %.1f%%   mean rank %.1f / %d      (chance %.1f%%, "
          "rank %.1f)" % (100 * sh, shr, w.n_syl, 100.0 / w.n_syl, (w.n_syl + 1) / 2))
    print("    sound -> shape   %.1f%%   mean rank %.1f / %d" % (100 * so, sor, w.n_let))
    print("    letters where the unbound shape mostly found its own sound: %d of 22"
          % top1)
    print("  THE 21 BOUND LETTERS in the same runs, held-out typefaces: %.1f%%"
          % (100 * bd))
    os.makedirs(a.out, exist_ok=True)
    json.dump({"rows": rows, "mean_shape_to_sound": sh, "mean_sound_to_shape": so,
               "mean_shape_rank": shr, "mean_sound_rank": sor, "bound_21": bd,
               "chance": 1.0 / w.n_syl, "chance_rank": (w.n_syl + 1) / 2,
               "holdout_take": w.hold_take, "holdout_fonts_from": w.f_cut,
               "steps": a.steps,
               "murphy": murphy_verdict(
                   "THE UNBOUND LETTER, shape -> sound over 22 runs (floor: chance -- "
                   "the letter was never bound)", sh, 1.0 / w.n_syl, 1.0 / w.n_syl,
                   judge="class identity on a letter excluded from the binding")},
              open(os.path.join(a.out, "letter-holdout.json"), "w"), indent=1)
    return rows


def pair_holdout(w, a):
    """Two letters hidden, and the choice is between just those two. Chance 50%.

    This is the control that kills the elimination story. With one letter hidden a model
    can be right by exclusion — 21 syllables are spoken for, so the leftover shape falls
    into the leftover hole. With two hidden and only those two on offer, exclusion says
    nothing and the only way to win is to actually know which shape goes with which sound.
    """
    print("\n" + "=" * 78)
    print("2b. TWO LETTERS HELD OUT, AND ONLY THOSE TWO ON OFFER    chance 50.0%")
    print("=" * 78)
    g = np.random.default_rng(a.seed)
    pairs = []
    while len(pairs) < a.pairs:
        i, j = sorted(g.choice(w.n_let, 2, replace=False).tolist())
        if (i, j) not in pairs:
            pairs.append((i, j))
    rows, t0 = [], time.time()
    for (i, j) in pairs:
        ear_h, eye_h = train_heads(w, steps=a.steps, seed=a.seed, exclude=(i, j))
        p = probe(w, ear_h, eye_h, [i, j], restrict=[i, j])
        acc = [p[i]["shape_to_sound"][0], p[j]["shape_to_sound"][0]]
        n = [p[i]["shape_to_sound"][2], p[j]["shape_to_sound"][2]]
        rows.append({"pair": [i, j], "names": [w.name(i), w.name(j)],
                     "two_way": acc, "n": n, "bound_20": p["bound"][0]})
        print("  %-12s vs %-12s  two-way %5.1f%% / %5.1f%%  (n=%d/%d)   |  the 20 "
              "bound: %.1f%%  (%.0fs)"
              % (w.name(i), w.name(j), 100 * acc[0], 100 * acc[1], n[0], n[1],
                 100 * p["bound"][0], time.time() - t0), flush=True)
    flat = [x for r in rows for x in r["two_way"]]
    m = float(np.mean(flat))
    se = float(np.std(flat) / max(1, np.sqrt(len(flat))))
    print("\n  TWO-WAY, both unbound letters, %d pairs: %.1f%% +- %.1f%%   "
          "(chance 50.0%%)" % (len(rows), 100 * m, 100 * se))
    os.makedirs(a.out, exist_ok=True)
    json.dump({"rows": rows, "mean_two_way": m, "sem": se, "chance": 0.5,
               "pairs": len(rows), "steps": a.steps,
               "murphy": murphy_verdict(
                   "TWO HIDDEN LETTERS, choose between just those two (floor: 50%)",
                   m, 0.5, 0.5,
                   judge="two-way choice; elimination buys nothing here")},
              open(os.path.join(a.out, "pair-holdout.json"), "w"), indent=1)
    return rows


def scramble_control(w, a):
    """Bind every shape to the WRONG sound. If this is not at chance, something leaks."""
    print("\n" + "=" * 78)
    print("CONTROL: every letter bound to a DERANGED syllable")
    print("=" * 78)
    ear_h, eye_h = train_heads(w, steps=a.steps, seed=a.seed, scramble=True)
    with torch.no_grad():
        cent_ear = centroids(ear_h(w.V[w.t_tr]), w.ey[w.t_tr], w.n_syl)
        r = rank_acc(eye_h(w.G[w.l_te]), cent_ear, w.l2s[w.ly[w.l_te]])
    # ZIV-10: this used to print and vanish. main() discarded the return value, no json
    # was written, and the ONE test that would catch a leak left no record to compare
    # across runs and nothing a watchdog could read. The bar is DERIVED, not picked: three
    # binomial standard errors above chance for the number of held-out images actually
    # scored.
    n_q = int(w.l_te.sum())
    chance = 1.0 / w.n_syl
    bar = chance + 3.0 * float(np.sqrt(chance * (1 - chance) / max(n_q, 1)))
    leaked = bool(r[0] > bar)
    print("  SHAPE->TRUE SOUND after a deranged binding: %.1f%%  (chance %.1f%%, "
          "mean rank %.1f, n=%d)" % (100 * r[0], 100 * chance, r[1], n_q))
    print("  bar = chance + 3 binomial SE = %.1f%%  ->  %s"
          % (100 * bar, "LEAK -- something is getting through that is not the binding"
             if leaked else "clean: it fell to chance, as a control must"))
    out = {"shape_to_true_sound": r[0], "mean_rank": r[1], "n": n_q, "chance": chance,
           "bar_3se": bar, "leaked": leaked, "seed": a.seed, "steps": a.steps,
           "holdout_take": w.hold_take, "holdout_fonts_from": w.f_cut,
           "when": time.strftime("%Y-%m-%d %H:%M:%S")}
    os.makedirs(a.out, exist_ok=True)
    json.dump(out, open(os.path.join(a.out, "scramble.json"), "w"), indent=1)
    print("  saved %s" % os.path.join(a.out, "scramble.json"))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Close the holobrain in both directions.")
    ap.add_argument("--mode", default="sound2draw",
                    choices=["sound2draw", "letterout", "pairout", "scramble", "all"])
    ap.add_argument("--ear", default=os.path.join(HERE, "ear-human.npz"))
    ap.add_argument("--eye", default=os.path.join(HERE, "..", "eye", "state", "eye.pt"))
    ap.add_argument("--hand", default=os.path.join(HERE, "..", "hand", "state", "hand.pt"))
    ap.add_argument("--letters", default=os.path.join(HERE, "..", "eye", "corpus",
                                                      "letters.npz"))
    ap.add_argument("--meta", default=os.path.join(HERE, "..", "eye", "corpus",
                                                   "letters.json"))
    ap.add_argument("--out", default=os.path.join(HERE, "state"))
    ap.add_argument("--steps", type=int, default=4000)
    ap.add_argument("--scribe-steps", type=int, default=12000)
    ap.add_argument("--scribe-hidden", type=int, default=256)
    ap.add_argument("--proto-k", type=int, default=0,
                    help="Aim at the mean of the k nearest neighbours in the EYE's own "
                         "space instead of one particular glyph. 0 = off.")
    ap.add_argument("--jitter", type=float, default=-1.0,
                    help="Noise the scribe is trained through. -1 = set it from the "
                         "MEASURED cross-modal gap instead of guessing.")
    ap.add_argument("--pairs", type=int, default=24)
    ap.add_argument("--holdout-fonts", type=int, default=6)
    ap.add_argument("--holdout-take", type=int, default=5)
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--seed", type=int, default=1933)
    ap.add_argument("--zivug", default=os.path.join(HERE, "state", "zivug.pt"),
                    help="The binding zivug.py trained. Loaded when it matches this "
                         "run, so one model produces all the numbers (ZIV-03).")
    ap.add_argument("--retrain-heads", action="store_true",
                    help="Train a fresh binding here even when zivug.pt matches.")
    ap.add_argument("--no-hand", action="store_true",
                    help="Run without WINSTON on purpose. Without this flag a missing "
                         "hand.pt is a REFUSAL, not a silently shorter report.")
    ap.add_argument("--i-know-this-is-the-PC", dest="on_pc", action="store_true",
                    help="Override the fleet-hostname guard. For a few-second smoke "
                         "test only -- training on the PC is forbidden.")
    a = ap.parse_args(argv)

    # ZIV-13: the same guard nezer.py carries and the scripts it copies did not. --mode
    # letterout is 22 full retrains and --mode pairout is 24; --device already resolves
    # to cpu on the PC, so the default was the failure mode, not a protection.
    guards.refuse_on_pc(a.on_pc, "close_loop.py --mode %s" % a.mode)

    dev = torch.device(a.device)
    w = World(a, dev)
    print("world: %d clips / %d syllables / %d takes  |  %d letter images / %d "
          "typefaces  |  device %s"
          % (len(w.V), w.n_syl, w.n_take, len(w.G), int(w.lf.max()) + 1, dev))

    # ZIV-10: the leakage control runs FIRST when everything runs, and it is a GATE.
    # If a deranged binding still finds the true sound, nothing after it means anything.
    verdicts = {}
    if a.mode in ("scramble", "all"):
        sc = scramble_control(w, a)
        verdicts["scramble"] = sc
        if sc["leaked"] and a.mode == "all":
            raise guards.Refused(
                "THE LEAKAGE CONTROL DID NOT FALL TO CHANCE (%.1f%% against a %.1f%% "
                "bar). Something reaches the true sound that is not the binding, so no "
                "headline from this run may be published. Find the leak first."
                % (100 * sc["shape_to_true_sound"], 100 * sc["bar_3se"]))
    if a.mode in ("sound2draw", "all"):
        verdicts["sound2draw"] = sound_to_drawing(w, a).get("murphy")
    if a.mode in ("letterout", "all"):
        letter_holdout(w, a)
    if a.mode in ("pairout", "all"):
        pair_holdout(w, a)

    # ZIV-05: a FOOLING ruling costs the run its exit code. It used to cost nothing.
    fooling = [k for k, v in (verdicts.get("sound2draw") or {}).items()
               if isinstance(v, dict) and v.get("fooling")]
    if fooling:
        print("\nMURPHY RULED FOOLING on: %s -- this run exits 2." % ", ".join(fooling))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
