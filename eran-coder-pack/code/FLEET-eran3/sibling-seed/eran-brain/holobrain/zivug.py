"""THE ZIVUG — shape, sound and hand into one place.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

Iddo, 2026-08-30: *"תזוויג הכל להולובריין מלא"* and *"מודל ווינסטון הוא חלק מההולובריין."*

## Why the ear has to be rebuilt first, and it is not a detour

Measured today on the judge's own frozen cochlea, over the 396 human reference clips:

    two humans, SAME syllable, different takes   0.575
    two humans, DIFFERENT syllables              0.881
    ------------------------------------------------
    the entire syllable signal                   0.306

**The within-syllable spread is 1.9x the whole between-syllable signal.** So a search
that minimises raw distance to one human clip spends most of its effort matching THAT
PERSON'S VOICE. ERAN was not being taught to say /ba/; he was being taught to imitate
one throat. That is the barrier, and it is in the ruler.

The cure is the rule that made the eye work this morning, said in the other sense:

    the eye    the same LETTER in a different typeface -> the same place
    the ear    the same SYLLABLE in a different mouth  -> the same place

Never a label, in either. Only *these two are the same thing*.

## What is supervision here and what is not

The cross-modal step pairs a letter's SHAPE with its syllable's SOUND. That pairing is
not a label — it is the correspondence a child is given by the world: you see the letter
while you hear it said. Nothing is ever told "this is alef". What is told is "these two
arrived together", which is what a shared space is made of.

## The three questions, each with a floor it can fail against

    ear      leave-one-TAKE-out, 22 ways     the frozen ear's own 79.55% is the bar
    zivug    show a SHAPE, get the SOUND     chance 4.5%
    winston  show HIS DRAWING, get the SOUND chance 4.5% -- the loop closed end to end

    python zivug.py --ear ear-human.npz --eye ../eye/state/eye.pt
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
sys.path.insert(0, os.path.join(HERE, "..", "hand"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "miko", "model"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "murphy"))

from murphy import watch                                             # noqa: E402

D = 192              # one space, the ear's own width. Both senses land here.


class Head(nn.Module):
    """A small projection. Small on purpose -- it must not become a second brain."""

    def __init__(self, d_in, d=D, hidden=384):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(d_in, hidden), nn.GELU(),
                                 nn.Linear(hidden, hidden), nn.GELU(),
                                 nn.Linear(hidden, d))

    def forward(self, x):
        return F.normalize(self.net(x), dim=-1)


def nt_xent(a, b, tau=0.12):
    """These two are the same thing; everything else in the batch is not."""
    z = torch.cat([a, b])
    n = a.shape[0]
    sim = (z @ z.T) / tau
    sim.fill_diagonal_(-1e4)
    tgt = torch.cat([torch.arange(n, 2 * n), torch.arange(0, n)]).to(z.device)
    return F.cross_entropy(sim, tgt)


def retrieval(q, keys, qy, ky):
    """Show one thing, ask for the other. Nearest key, and whether it was the right one."""
    cent = F.normalize(torch.stack([keys[ky == c].mean(0) for c in sorted(set(
        ky.tolist()))]), dim=-1)
    return float(((q @ cent.T).argmax(1) == qy).float().mean())


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Bind shape, sound and hand into one space.")
    ap.add_argument("--ear", default=os.path.join(HERE, "ear-human.npz"))
    ap.add_argument("--eye", default=os.path.join(HERE, "..", "eye", "state", "eye.pt"))
    ap.add_argument("--hand", default=os.path.join(HERE, "..", "hand", "state", "hand.pt"))
    ap.add_argument("--letters", default=os.path.join(HERE, "..", "eye", "corpus",
                                                      "letters.npz"))
    ap.add_argument("--meta", default=os.path.join(HERE, "..", "eye", "corpus",
                                                   "letters.json"))
    ap.add_argument("--out", default=os.path.join(HERE, "state"))
    ap.add_argument("--steps", type=int, default=6000)
    ap.add_argument("--batch", type=int, default=128)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--holdout-fonts", type=int, default=6,
                    help="Typefaces the eye's half of the binding never trains on.")
    ap.add_argument("--holdout-take", type=int, default=5,
                    help="This TAKE is never trained on. Every number reported is measured "
                         "on it alone -- otherwise the score is memory, not hearing.")
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--seed", type=int, default=1933)
    a = ap.parse_args(argv)

    torch.manual_seed(a.seed)
    dev = torch.device(a.device)
    gen = torch.Generator(device=dev).manual_seed(a.seed)

    # ---------------------------------------------------------------- the ear
    d = np.load(a.ear, allow_pickle=True)
    V = torch.as_tensor(d["V"].astype(np.float32), device=dev)
    ey = torch.as_tensor(d["y"].astype(np.int64), device=dev)
    et = torch.as_tensor(d["t"].astype(np.int64), device=dev)
    syllables = [str(s) for s in d["syllables"]]
    tr, te = et != a.holdout_take, et == a.holdout_take
    print("ear: %d clips, %d syllables, %d takes -- take %d held out (%d clips)"
          % (len(V), len(syllables), int(et.max()) + 1, a.holdout_take, int(te.sum())))

    # the floor: what the frozen ear does with no learning at all
    raw = F.normalize(V, dim=-1)
    ear_floor = retrieval(raw[te], raw[tr], ey[te], ey[tr])
    print("  frozen cochlea, raw distance, held-out take: %.1f%%   (chance %.1f%%)"
          % (100 * ear_floor, 100 / len(syllables)))

    # ---------------------------------------------------------------- the eye
    from eye import Encoder                                          # noqa: E402
    enc = Encoder().to(dev)
    enc.load_state_dict(torch.load(a.eye, map_location=dev)["encoder"])
    enc.eval()
    for p in enc.parameters():
        p.requires_grad_(False)
    L = np.load(a.letters)
    LX = torch.as_tensor(L["X"].astype(np.float32), device=dev)
    ly = torch.as_tensor(L["y"].astype(np.int64), device=dev)
    # HOLD OUT TYPEFACES TOO. The ear takes were held out from the start and the shape
    # side was not, so the first run reported SHAPE->SOUND on letters the eye had already
    # looked at. A held-out half is not a held-out experiment.
    lf = torch.as_tensor(L["f"].astype(np.int64), device=dev)
    f_cut = int(lf.max()) + 1 - a.holdout_fonts
    l_tr, l_te = lf < f_cut, lf >= f_cut
    with torch.no_grad():
        G = torch.cat([enc.gist(LX[i:i + 512]) for i in range(0, len(LX), 512)])

    # letter index -> syllable index. The one place the two senses are told they meet.
    meta = json.load(open(a.meta, encoding="utf-8"))["letters"]
    l2s = torch.as_tensor([syllables.index(m["syllable"]) for m in meta],
                          dtype=torch.long, device=dev)
    print("eye: %d images, %d letters, all %d syllables matched by name; "
          "%d typefaces trained on, %d held out (%d images)"
          % (len(G), int(ly.max()) + 1, len(set(l2s.tolist())), f_cut,
             a.holdout_fonts, int(l_te.sum())))

    # THE FLOOR FOR SHAPE->SOUND, which this file reported against chance alone. Chance is
    # the wrong bar. The question is what the two senses already retrieve across each other
    # with NO binding at all -- a raw eye gist against a raw cochlea vector, both
    # L2-normalised, no head, no training, nothing learned. They are both 192-d and they
    # are in unrelated spaces, so this should land near chance; the point is that it is
    # MEASURED on the same held-out typefaces and could have come back high.
    cross_floor = retrieval(G[l_te], raw[tr], l2s[ly[l_te]], ey[tr])
    print("  no binding at all, raw gist -> raw cochlea, held-out faces: %.1f%%   "
          "(chance %.1f%%)" % (100 * cross_floor, 100 / len(syllables)))

    ear_h, eye_h = Head(192).to(dev), Head(192).to(dev)
    opt = torch.optim.AdamW(list(ear_h.parameters()) + list(eye_h.parameters()),
                            lr=a.lr, weight_decay=0.01)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, a.lr, total_steps=a.steps,
                                                pct_start=0.2)
    # The corpus is perfectly rectangular -- 22 syllables x 6 takes x 3 clips -- so the
    # positive pair can be picked with pure tensor maths. The first version did it with a
    # python loop over the batch and 128 boolean masks per step, and the run simply never
    # reached its first print.
    n_syl, n_take = len(syllables), int(et.max()) + 1
    per = len(V) // (n_syl * n_take)
    T = torch.full((n_syl, n_take, per), -1, dtype=torch.long, device=dev)
    fill = torch.zeros(n_syl, n_take, dtype=torch.long, device=dev)
    for i in range(len(V)):
        c, t = int(ey[i]), int(et[i])
        T[c, t, fill[c, t]] = i
        fill[c, t] += 1
    assert (T >= 0).all(), "the reference set is not rectangular -- fix before trusting it"
    train_takes = torch.tensor([t for t in range(n_take) if t != a.holdout_take],
                               device=dev)

    def pick(c, exclude=None):
        """A random training clip of syllable c, optionally from a different take."""
        k = torch.randint(0, len(train_takes), c.shape, device=dev, generator=gen)
        t = train_takes[k]
        if exclude is not None:                    # walk one take forward if it collided
            t = torch.where(t == exclude, train_takes[(k + 1) % len(train_takes)], t)
        r = torch.randint(0, per, c.shape, device=dev, generator=gen)
        return T[c, t, r], t

    idx_tr = torch.nonzero(tr).squeeze(1)
    t0, log = time.time(), []
    os.makedirs(a.out, exist_ok=True)

    for step in range(1, a.steps + 1):
        # 1. THE EAR, on its own: the same syllable from two different takes.
        want = torch.randint(0, n_syl, (a.batch,), device=dev, generator=gen)
        i, ti = pick(want)
        j, _ = pick(want, exclude=ti)              # same syllable, a DIFFERENT mouth
        l_ear = nt_xent(ear_h(V[i]), ear_h(V[j]))

        # 2. THE ZIVUG: a letter's shape and its syllable's sound, arriving together.
        li = torch.nonzero(l_tr).squeeze(1)[torch.randint(
            0, int(l_tr.sum()), (a.batch,), device=dev, generator=gen)]
        s_of = l2s[ly[li]]
        k, _ = pick(s_of)
        l_bind = nt_xent(eye_h(G[li]), ear_h(V[k]))

        loss = l_ear + l_bind
        opt.zero_grad(set_to_none=True)
        loss.backward()
        opt.step()
        sched.step()

        if step % 500 == 0 or step == a.steps:
            with torch.no_grad():
                ear_h.eval(); eye_h.eval()
                E_te, E_tr = ear_h(V[te]), ear_h(V[tr])
                hear = retrieval(E_te, E_tr, ey[te], ey[tr])
                cross = retrieval(eye_h(G[l_te]), E_tr, l2s[ly[l_te]], ey[tr])
                ear_h.train(); eye_h.train()
            log.append({"step": step, "hear": hear, "shape_to_sound": cross})
            print("  step %5d  ear %.1f%%   SHAPE->SOUND %.1f%%   (%.0fs)"
                  % (step, 100 * hear, 100 * cross, time.time() - t0), flush=True)

    # -------------------------------------------------------------- WINSTON
    # The loop closed end to end: his own hand draws, his own eye looks, and the sound
    # of the letter comes back out. If this is at chance the holobrain is a diagram.
    win = None
    if os.path.exists(a.hand):
        from hand_eye import Winston, ink                            # noqa: E402
        n_l = int(ly.max()) + 1
        hand = Winston(n_l).to(dev)
        hand.load_state_dict(torch.load(a.hand, map_location=dev)["hand"])
        with torch.no_grad():
            drawn = ink(hand(torch.eye(n_l, device=dev))[0])
            win = retrieval(eye_h(enc.gist(drawn)), ear_h(V[tr]), l2s[torch.arange(
                n_l, device=dev)], ey[tr])
        print("\nWINSTON DRAWS -> the eye looks -> the SOUND comes back: %.1f%%   "
              "(chance %.1f%%)" % (100 * win, 100 / len(syllables)))

    torch.save({"ear_head": ear_h.state_dict(), "eye_head": eye_h.state_dict(),
                "syllables": syllables, "dim": D}, os.path.join(a.out, "zivug.pt"))
    json.dump({"log": log, "winston": win, "chance": 1.0 / len(syllables),
               "ear_floor": ear_floor, "cross_floor": cross_floor,
               "args": vars(a)}, open(os.path.join(a.out, "zivug.json"), "w"), indent=1)
    print("saved %s" % os.path.join(a.out, "zivug.pt"))

    # MURPHY, twice, because this file makes two separate claims with two separate floors
    # and one verdict over both would let the weaker one hide behind the stronger.
    #
    # judge_in_loop is FALSE for both, and the reason is worth stating: what decides a
    # retrieval right or wrong is whether the syllable that comes back is the letter's
    # OWN syllable -- the letter/syllable correspondence, which is in the corpus and
    # which nothing here can move. The heads are being measured, not consulted.
    common = {"chance": 1.0 / len(syllables), "held_out": True,
              "judge_in_loop": False, "artifact": None, "looked_at": False,
              "independent": True,
              "judge": "class identity on a held-out take; the map is in the corpus",
              "objective_by": "nt-xent over pairs"}
    ear_last = log[-1]["hear"] if log else 0.0
    watch(dict(common, baseline=ear_floor, claimed_success=ear_last > ear_floor,
               steps=[{"step": e["step"], "metric": e["hear"], "terms": {}}
                      for e in log]),
          name="the ear alone, leave-one-TAKE-out (floor: the frozen cochlea)")
    cross_last = log[-1]["shape_to_sound"] if log else 0.0
    watch(dict(common, baseline=cross_floor, claimed_success=cross_last > cross_floor,
               steps=[{"step": e["step"], "metric": e["shape_to_sound"], "terms": {}}
                      for e in log]),
          name="THE ZIVUG, shape -> sound (floor: no binding at all)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
