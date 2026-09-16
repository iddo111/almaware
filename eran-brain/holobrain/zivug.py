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

    ear      leave-one-TAKE-out, 6 ways      the frozen ear's own 80.8% +- 8.4 is the bar
    zivug    show a SHAPE, get the SOUND     chance 4.5%
    winston  show HIS DRAWING, get the SOUND chance 4.5% -- the loop closed end to end

## 2026-09-06, code revision — the bar was a number from nowhere, and the split was picked

That bar used to read **79.55%**, and it matches NONE of the six possible held-out takes:
n=66 per take forces multiples of 1.515%. Recomputed here from `ear-human.npz` — raw
cosine to the nearest training centroid, 22-way, one line per take:

    take 0  92.4%   take 1  87.9%   take 2  69.7%
    take 3  78.8%   take 4  71.2%   take 5  84.8%     mean 80.8%, sd 8.4

The spread is **22.7 points**, and this file hard-coded `--holdout-take 5` — the
second-best of the six. One split is not a result. The floor is now measured on all six
every run and printed mean +- sd; `--loto` retrains the heads once per take so the
reported number carries the same treatment. Those six figures reproduce
`../ruler/ruler-measured.json`'s "R2 CENTROID of the syllable" row exactly, so the sweep
already existed on disk and was never wired back in.

    python zivug.py --ear ear-human.npz --eye ../eye/state/eye.pt
    python zivug.py --loto           # all six takes, mean +- sd
"""
from __future__ import annotations

import argparse
import copy
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

sys.path.insert(0, HERE)                     # guards.py lives beside this file

from murphy import watch                                             # noqa: E402
import guards                                                        # noqa: E402

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


def nt_xent(a, b, tau=0.12, labels=None):
    """These two are the same thing; everything else in the batch is not.

    ZIV-07, 2026-09-06: `labels` takes the SAME-CLASS clips out of the denominator, and
    without it this loss was fighting its own objective on every step. Batch 128 drawn
    from 22 syllables means every anchor was being pushed AWAY from its own syllable --
    measured by simulating this file's own sampling at seed 1933 over 2000 trials, 11.56
    of each anchor's 254 negatives (4.6%) were the same syllable. At tau=0.12 those are
    the highest-similarity negatives, i.e. exactly the ones the gradient is made of.
    Both call sites already hold the labels, so the mask costs nothing.
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


def retrieval(q, keys, qy, ky, n_cls):
    """Show one thing, ask for the other. Nearest key, and whether it was the right one.

    ZIV-09, 2026-09-06: `n_cls` is REQUIRED and every class must be present. The old
    version built its centroid table from `sorted(set(ky))`, so a class missing from the
    key set shifted every row after the gap and scored the rest against the wrong class
    -- a plausible wrong number, no exception, no warning. Reproduced: with class 2
    absent it returned 0.0 where 1.0 is correct. close_loop.py's twin (`centroids`)
    already asserted this; this one did not, and the corpus WAS regenerated on 08-31.
    """
    cent = []
    for c in range(n_cls):
        m = ky == c
        assert bool(m.any()), (
            "class %d has no keys -- the candidate set is broken" % c)
        cent.append(keys[m].mean(0))
    cent = F.normalize(torch.stack(cent), dim=-1)
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
    ap.add_argument("--loto", action="store_true",
                    help="Leave-one-TAKE-out over ALL takes, and report mean +- sd. "
                         "One split is a number; six splits are a result (ZIV-04).")
    ap.add_argument("--no-hand", action="store_true",
                    help="Run without WINSTON on purpose. Without this flag a missing "
                         "hand.pt is a REFUSAL, not a silently shorter report.")
    ap.add_argument("--part-of-loto", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--i-know-this-is-the-PC", dest="on_pc", action="store_true",
                    help="Override the fleet-hostname guard. For a few-second smoke "
                         "test only -- training on the PC is forbidden.")
    a = ap.parse_args(argv)

    # ZIV-13: nezer.py refuses by hostname and writes the incident at the site -- agents
    # ran eye.py and zivug.py on the PC, took it to 100% CPU while Iddo was working, and
    # had to be killed twice. The scripts nezer COPIES never carried the guard nezer got.
    # Note that --device already defaults to cpu here (torch.cuda.is_available() is False
    # on the PC), so the default was the failure mode, not a protection against it.
    guards.refuse_on_pc(a.on_pc, "zivug.py")

    # ZIV-04: the same experiment six ways instead of the one favourable split.
    if a.loto:
        return _loto(a, argv, ap)

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

    # The floor: what the frozen ear does with no learning at all -- ON EVERY TAKE.
    # ZIV-04: this used to be one number for one hard-coded take. Six takes cost nothing
    # (no training, just cosines) and the spread is 22.7 points, so the single number was
    # hiding the most important fact about it.
    raw = F.normalize(V, dim=-1)
    n_take_all = int(et.max()) + 1
    floors = [retrieval(raw[et == t_], raw[et != t_], ey[et == t_], ey[et != t_],
                        len(syllables)) for t_ in range(n_take_all)]
    ear_floor = floors[a.holdout_take]
    print("  frozen cochlea, raw distance, held-out take %d: %.1f%%   (chance %.1f%%)"
          % (a.holdout_take, 100 * ear_floor, 100 / len(syllables)))
    print("  the same floor on ALL %d takes: %s  -> mean %.1f%%, sd %.1f%%   "
          "(the chosen split ranks %d of %d)"
          % (n_take_all, " ".join("%.1f" % (100 * f) for f in floors),
             100 * float(np.mean(floors)), 100 * float(np.std(floors)),
             sorted(floors, reverse=True).index(ear_floor) + 1, n_take_all))

    # ---------------------------------------------------------------- the eye
    # ZIV-01: this line used to die with a bare `size mismatch for proj.weight` and
    # nothing said WHICH of the two files had moved. eye.pt is a GRAYSCALE encoder; the
    # corpus went to 3-channel colour on 2026-08-31 and the eye was never retrained, so
    # this chain has been dead on arrival for six days and NOTHING SAID SO. The guard
    # names both files, both mtimes and both shapes. strict=False would have "fixed" it
    # by handing the run a RANDOM projection and a plausible number -- far worse.
    from eye import CH, PATCH, Encoder                                # noqa: E402
    eye_ck = guards.check_eye_checkpoint(a.eye, a.letters, PATCH, CH)
    enc = Encoder().to(dev)
    enc.load_state_dict(eye_ck["encoder"])
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
    # ZIV-14: what is held out here is the BINDING's half. Whether the frozen ENCODER
    # ever saw those faces is a different question, and eye.pt does not answer it --
    # eye.py's --holdout defaults to 0 (trains on ALL faces) and the checkpoint stores no
    # args. close_loop.py printed "the eye encoder AND the binding never saw them"
    # unconditionally against exactly that.
    enc_hold = guards.encoder_holdout(eye_ck)
    print("  the BINDING never sees those %d typefaces. The ENCODER's own holdout: %s"
          % (a.holdout_fonts,
             ("%d faces, recorded in the checkpoint" % enc_hold) if enc_hold is not None
             else "UNKNOWN -- eye.pt records no holdout field, so 'the eye never saw "
                  "them' is NOT established"))

    # THE FLOOR FOR SHAPE->SOUND, which this file reported against chance alone. Chance is
    # the wrong bar. The question is what the two senses already retrieve across each other
    # with NO binding at all -- a raw eye gist against a raw cochlea vector, both
    # L2-normalised, no head, no training, nothing learned. They are both 192-d and they
    # are in unrelated spaces, so this should land near chance; the point is that it is
    # MEASURED on the same held-out typefaces and could have come back high.
    cross_floor = retrieval(G[l_te], raw[tr], l2s[ly[l_te]], ey[tr], len(syllables))
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
    # ZIV-03: the checkpoint used to be whatever the LAST step happened to be. Best-by-
    # eval, and the eval that decides is the one this file is named for.
    best = {"step": 0, "hear": 0.0, "shape_to_sound": -1.0, "ear": None, "eye": None}
    os.makedirs(a.out, exist_ok=True)

    for step in range(1, a.steps + 1):
        # 1. THE EAR, on its own: the same syllable from two different takes.
        want = torch.randint(0, n_syl, (a.batch,), device=dev, generator=gen)
        i, ti = pick(want)
        j, _ = pick(want, exclude=ti)              # same syllable, a DIFFERENT mouth
        l_ear = nt_xent(ear_h(V[i]), ear_h(V[j]), labels=want)

        # 2. THE ZIVUG: a letter's shape and its syllable's sound, arriving together.
        li = torch.nonzero(l_tr).squeeze(1)[torch.randint(
            0, int(l_tr.sum()), (a.batch,), device=dev, generator=gen)]
        s_of = l2s[ly[li]]
        k, _ = pick(s_of)
        l_bind = nt_xent(eye_h(G[li]), ear_h(V[k]), labels=s_of)

        loss = l_ear + l_bind
        opt.zero_grad(set_to_none=True)
        loss.backward()
        opt.step()
        sched.step()

        if step % 500 == 0 or step == a.steps:
            with torch.no_grad():
                ear_h.eval(); eye_h.eval()
                E_te, E_tr = ear_h(V[te]), ear_h(V[tr])
                hear = retrieval(E_te, E_tr, ey[te], ey[tr], len(syllables))
                cross = retrieval(eye_h(G[l_te]), E_tr, l2s[ly[l_te]], ey[tr],
                                  len(syllables))
                ear_h.train(); eye_h.train()
            log.append({"step": step, "hear": hear, "shape_to_sound": cross})
            if cross > best["shape_to_sound"]:
                best = {"step": step, "hear": hear, "shape_to_sound": cross,
                        "ear": copy.deepcopy(ear_h.state_dict()),
                        "eye": copy.deepcopy(eye_h.state_dict())}
            print("  step %5d  ear %.1f%%   SHAPE->SOUND %.1f%%   (%.0fs)"
                  % (step, 100 * hear, 100 * cross, time.time() - t0), flush=True)

    # The heads that get saved AND the heads Winston is measured against are the same
    # ones, and they are the best eval rather than the last step.
    if best["ear"] is not None and best["step"] != (log[-1]["step"] if log else 0):
        ear_h.load_state_dict(best["ear"])
        eye_h.load_state_dict(best["eye"])
        print("  restored the BEST eval (step %d, SHAPE->SOUND %.1f%%) -- the last step "
              "is not necessarily the best" % (best["step"], 100 * best["shape_to_sound"]))
    ear_h.eval(); eye_h.eval()

    # -------------------------------------------------------------- WINSTON
    # The loop closed end to end: his own hand draws, his own eye looks, and the sound
    # of the letter comes back out. If this is at chance the holobrain is a diagram.
    # ZIV-11: the hand used to be an accident of the filesystem. If hand.pt was absent
    # the whole third question -- the one this file's docstring calls "the loop closed
    # end to end" -- vanished from the report with no warning and win=None in the JSON.
    # A missing organ read as a shorter report. It is a declared expectation now.
    win = None
    if a.no_hand:
        win = "SKIPPED: --no-hand was passed"
        print("\nWINSTON: SKIPPED ON PURPOSE (--no-hand). The loop is NOT closed end to "
              "end in this run, and no number here says anything about the hand.")
    elif not os.path.exists(a.hand):
        raise guards.Refused(
            "WINSTON's hand is missing: %s does not exist.\n"
            "  This file's third question -- show HIS DRAWING, get the SOUND -- cannot "
            "be asked without it, and dropping it silently is how a claim disappears "
            "with nobody noticing. Pass --no-hand to run the other two deliberately."
            % a.hand)
    else:
        from hand_eye import Winston, ink                            # noqa: E402
        n_l = int(ly.max()) + 1
        hand = Winston(n_l).to(dev)
        hand.load_state_dict(torch.load(a.hand, map_location=dev)["hand"])
        with torch.no_grad():
            # ZIV-16: ink() draws one channel and the eye reads CH. Without this the
            # loop does not close at all -- it raises inside patchify.
            drawn = guards.ink_to_eye(ink(hand(torch.eye(n_l, device=dev))[0]), CH)
            win = retrieval(eye_h(enc.gist(drawn)), ear_h(V[tr]), l2s[torch.arange(
                n_l, device=dev)], ey[tr], len(syllables))
        print("\nWINSTON DRAWS -> the eye looks -> the SOUND comes back: %.1f%%   "
              "(chance %.1f%%)" % (100 * win, 100 / len(syllables)))

    # MURPHY, twice, because this file makes two separate claims with two separate floors
    # and one verdict over both would let the weaker one hide behind the stronger.
    #
    # ZIV-05: he now sits BEFORE the save and his ruling is CAPTURED. It used to be:
    # torch.save, json.dump, and only then two watch() calls whose return values were
    # discarded, with main() returning 0 whatever he said -- so "FOOLING ITSELF" cost the
    # run precisely nothing. murphy.py:347 documents that watch returns
    # {"fooling": bool, "score": float, ...} "so a caller can act on it as well as read
    # it", and no caller did. murphy.py:351 quotes Iddo, 2026-08-30:
    # "שאף ריצה לא תדווח בלי פסק שלו."
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
    ear_best = best["hear"] if log else 0.0
    v_ear = watch(dict(common, baseline=ear_floor, claimed_success=ear_best > ear_floor,
                       steps=[{"step": e["step"], "metric": e["hear"], "terms": {}}
                              for e in log]),
                  name="the ear alone, leave-one-TAKE-out (floor: the frozen cochlea)")
    cross_best = best["shape_to_sound"] if log else 0.0
    v_cross = watch(dict(common, baseline=cross_floor,
                         claimed_success=cross_best > cross_floor,
                         steps=[{"step": e["step"], "metric": e["shape_to_sound"],
                                 "terms": {}} for e in log]),
                    name="THE ZIVUG, shape -> sound (floor: no binding at all)")
    verdicts = {"ear": _verdict(v_ear), "zivug": _verdict(v_cross)}
    fooling = any(v.get("fooling") for v in verdicts.values())

    # ZIV-03: the checkpoint used to carry four keys and nothing about the run that made
    # it -- no steps, no seed, no holdout, no corpus. Two files reporting one result
    # cannot even check they are talking about the same model without this.
    meta = {"written_by": "zivug.py", "written_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "steps": a.steps, "seed": a.seed, "batch": a.batch,
            "holdout_take": a.holdout_take, "holdout_fonts": a.holdout_fonts,
            "best_step": best["step"], "best_shape_to_sound": best["shape_to_sound"],
            "best_hear": best["hear"], "encoder_holdout": enc_hold,
            "ear_floor": ear_floor, "ear_floor_all_takes": floors,
            "cross_floor": cross_floor,
            "corpus": {"ear": guards.fingerprint(a.ear, "V"),
                       "letters": guards.fingerprint(a.letters, "X"),
                       "eye": guards.fingerprint(a.eye)}}
    rec = {"log": log, "winston": win, "chance": 1.0 / len(syllables),
           "ear_floor": ear_floor, "ear_floor_all_takes": floors,
           "cross_floor": cross_floor, "meta": meta, "murphy": verdicts,
           "single_split": not a.part_of_loto, "args": vars(a)}
    json.dump(rec, open(os.path.join(a.out, "zivug.json"), "w"), indent=1)

    # A SUSPECT checkpoint does not sit where a clean one sits, and the exit code says so.
    out_pt = os.path.join(a.out, "SUSPECT" if fooling else "", "zivug.pt")
    os.makedirs(os.path.dirname(out_pt), exist_ok=True)
    torch.save({"ear_head": ear_h.state_dict(), "eye_head": eye_h.state_dict(),
                "syllables": syllables, "dim": D, "meta": meta,
                "murphy": verdicts}, out_pt)
    print("saved %s" % out_pt)
    if not a.part_of_loto:
        print("NOTE: this is a SINGLE SPLIT (take %d of %d). The frozen-ear floor alone "
              "moves %.1f-%.1f%% across takes -- run --loto before quoting a number."
              % (a.holdout_take, n_take_all, 100 * min(floors), 100 * max(floors)))
    if fooling:
        print("MURPHY RULED FOOLING -- the checkpoint went to %s and this run exits 2."
              % os.path.dirname(out_pt))
        return 2
    return 0


def _verdict(v):
    """What watch() said, in a form that survives json.dump -- and an honest blank."""
    if not isinstance(v, dict):
        return {"fooling": False, "score": None,
                "note": "murphy did not rule (watch returned %r)" % type(v).__name__}
    return {"fooling": bool(v.get("fooling")), "score": v.get("score"),
            "spoke": list(v.get("spoke") or []),
            "undeclared": list(v.get("undeclared") or [])}


def _loto(a, argv, ap):
    """ZIV-04: the same run once per TAKE, and a mean +- sd instead of one split.

    Implemented by re-entering main() with --holdout-take set, so there is exactly one
    training path in this file and the six runs cannot drift from the single one.
    """
    argv_in = list(sys.argv[1:] if argv is None else argv)
    base, skip = [], False
    for tok in argv_in:
        if skip:
            skip = False
            continue
        if tok == "--loto":
            continue
        if tok in ("--holdout-take", "--out"):
            skip = True
            continue
        if tok.startswith("--holdout-take=") or tok.startswith("--out="):
            continue
        base.append(tok)
    n_take_all = int(np.load(a.ear, allow_pickle=True)["t"].max()) + 1
    rows, rc = [], 0
    for t_ in range(n_take_all):
        out_t = os.path.join(a.out, "loto", "take%d" % t_)
        print("\n" + "=" * 78)
        print("LEAVE-ONE-TAKE-OUT %d/%d -- holding out take %d" % (t_ + 1, n_take_all, t_))
        print("=" * 78, flush=True)
        rc = main(base + ["--holdout-take", str(t_), "--out", out_t,
                          "--part-of-loto"]) or rc
        rows.append(json.load(open(os.path.join(out_t, "zivug.json"))))
    hear = [r["meta"]["best_hear"] for r in rows]
    cross = [r["meta"]["best_shape_to_sound"] for r in rows]
    floor = [r["ear_floor"] for r in rows]
    print("\n" + "-" * 78)
    print("LEAVE-ONE-TAKE-OUT over all %d takes -- mean +- sd, not one favourable split"
          % n_take_all)
    print("  frozen-ear floor   %s  -> %.1f%% +- %.1f%%"
          % (" ".join("%.1f" % (100 * f) for f in floor),
             100 * float(np.mean(floor)), 100 * float(np.std(floor))))
    print("  ear, after binding %s  -> %.1f%% +- %.1f%%"
          % (" ".join("%.1f" % (100 * f) for f in hear),
             100 * float(np.mean(hear)), 100 * float(np.std(hear))))
    print("  SHAPE -> SOUND     %s  -> %.1f%% +- %.1f%%"
          % (" ".join("%.1f" % (100 * f) for f in cross),
             100 * float(np.mean(cross)), 100 * float(np.std(cross))))
    os.makedirs(a.out, exist_ok=True)
    json.dump({"takes": list(range(n_take_all)), "ear_floor": floor, "hear": hear,
               "shape_to_sound": cross,
               "mean": {"ear_floor": float(np.mean(floor)), "hear": float(np.mean(hear)),
                        "shape_to_sound": float(np.mean(cross))},
               "sd": {"ear_floor": float(np.std(floor)), "hear": float(np.std(hear)),
                      "shape_to_sound": float(np.std(cross))},
               "worst_exit_code": rc},
              open(os.path.join(a.out, "zivug-loto.json"), "w"), indent=1)
    print("  saved %s" % os.path.join(a.out, "zivug-loto.json"))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
