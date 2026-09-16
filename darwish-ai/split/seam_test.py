# -*- coding: utf-8 -*-
"""seam_test.py - is the seam REAL? A model-free test of the whole premise.

לזכרו של לָאוֹר ז״ל.

THE CLAIM UNDER TEST
--------------------
The split is justified by one sentence: "drums genuinely are independent - they
do not care what key you are in - so that is the real seam." If that is true,
factorising P(drums, pitches | past) into P(drums | past drums) x
P(pitches | past pitches) throws away nothing. If it is false, the factorisation
DELETES the mutual information between the two hands, and no amount of freed
capacity can buy it back.

This file measures that mutual information directly, from the corpus, with no
model involved, so the answer does not depend on any training run.

WHY IT IS CONDITIONAL MUTUAL INFORMATION AND NOT PLAIN MI
----------------------------------------------------------
Drums and pitches are both driven by the metrical grid: a kick on the downbeat
and a bass note on the downbeat are correlated because both follow the BAR, not
because either causes the other. The shared STEP/BAR clock is carried by BOTH
sub-streams already, so information the position-in-bar explains is NOT lost by
the split. The quantity that is actually at stake is

    I(D ; P | position-in-bar)

- what the drums tell you about the pitches OVER AND ABOVE what the clock
already told you. That, in bits per sixteenth, is the price of the seam.

THE BIAS FLOOR, because a plug-in MI estimate is never zero
-------------------------------------------------------------
An empirical MI computed from finite counts is biased UPWARD; on truly
independent data it comes out positive. So every number here is reported beside
a SHUFFLE CONTROL: the pitch column is permuted within each position-in-bar
bucket, which destroys any real dependence while preserving both marginals and
the conditioning. MI minus the shuffle floor is the part that is real. Ten
shuffles give the floor a standard deviation of its own.

psytrance makes this a genuinely open question rather than a formality: the
rolling offbeat bass is locked to the kick by construction, so the honest
expectation is that the seam LEAKS. How much is what this measures.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import poly_tok as PT                                              # noqa: E402


def step_columns(toks):
    """Walk a v2 stream and emit, per sixteenth, (drum_code, pitch_code, pos).

    drum_code  : 3 bits, which of kick/body/hat fired at this step  (0..7)
    pitch_code : the SET of pitch classes struck at this step, as a 12-bit mask
    n_pitch    : how many pitch onsets at this step
    pos        : position in the bar, 0..15
    """
    step = 0
    d_now = 0
    pc_now = 0
    n_now = 0
    out_d, out_pc, out_n, out_pos = [], [], [], []
    for t in toks:
        t = int(t)
        if t == PT.TOK_STEP:
            out_d.append(d_now)
            out_pc.append(pc_now)
            out_n.append(min(n_now, 4))
            out_pos.append(step % PT.STEPS_PER_BAR)
            step += 1
            d_now = pc_now = n_now = 0
        elif PT.DRUM_BASE <= t < PT.PITCH_BASE:
            which, _ = PT.drum_of(t)
            d_now |= (1 << which)
        elif PT.PITCH_BASE <= t < PT.DUR_BASE:
            # key-relative degree; the octave is irrelevant to "which chord"
            pc_now |= (1 << ((t - PT.PITCH_BASE) % 12))
            n_now += 1
    return (np.asarray(out_d, dtype=np.int64), np.asarray(out_pc, dtype=np.int64),
            np.asarray(out_n, dtype=np.int64), np.asarray(out_pos, dtype=np.int64))


def cond_mi_bits(x, y, z):
    """I(X;Y|Z) in bits, plug-in estimator over the joint counts."""
    tot = len(x)
    if tot == 0:
        return 0.0
    mi = 0.0
    for zv in np.unique(z):
        m = z == zv
        n = int(m.sum())
        if n < 2:
            continue
        xs, ys = x[m], y[m]
        cx = Counter(xs.tolist())
        cy = Counter(ys.tolist())
        cxy = Counter(zip(xs.tolist(), ys.tolist()))
        h = 0.0
        for (a, b), c in cxy.items():
            pxy = c / n
            h += pxy * math.log2(pxy / ((cx[a] / n) * (cy[b] / n)))
        mi += (n / tot) * h
    return mi


def entropy_bits(v):
    c = np.asarray(list(Counter(v.tolist()).values()), dtype=float)
    p = c / c.sum()
    return float(-(p * np.log2(p)).sum())


def cond_entropy_bits(v, z):
    tot = len(v)
    h = 0.0
    for zv in np.unique(z):
        m = z == zv
        n = int(m.sum())
        if n == 0:
            continue
        h += (n / tot) * entropy_bits(v[m])
    return h


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tokdir", default=str(HERE.parent / "tokens-poly"))
    ap.add_argument("--split", default=str(HERE.parent / "code-midi" / "split.json"))
    ap.add_argument("--which", default="heldout", choices=("heldout", "train", "all"))
    ap.add_argument("--shuffles", type=int, default=10)
    ap.add_argument("--max-steps", type=int, default=3_000_000)
    ap.add_argument("--out", default=str(HERE / "seam_test.json"))
    a = ap.parse_args()

    try:
        os.nice(19)
    except Exception:
        pass

    sp = json.loads(Path(a.split).read_text(encoding="utf-8"))
    names = sp["heldout"] if a.which == "heldout" else (
        sp["train"] if a.which == "train" else sp["train"] + sp["heldout"])

    D, PCm, N, POS = [], [], [], []
    used = 0
    secs = 0.0                       # seconds of ONLY the tracks actually read,
    have = 0                         # so --max-steps truncation cannot inflate
    for nm in names:                 # the bits/second headline
        p = Path(a.tokdir) / nm
        if not p.exists():
            continue
        rec = json.loads(p.read_text(encoding="utf-8"))
        d, pc, n, pos = step_columns(rec["tokens"])
        D.append(d); PCm.append(pc); N.append(n); POS.append(pos)
        secs += rec["seconds"]
        have += len(d)
        used += 1
        if have >= a.max_steps:
            break
    d = np.concatenate(D); pc = np.concatenate(PCm)
    n = np.concatenate(N); pos = np.concatenate(POS)
    if len(d) > a.max_steps:
        d, pc, n, pos = d[:a.max_steps], pc[:a.max_steps], n[:a.max_steps], pos[:a.max_steps]

    print("%s: %d tracks, %d sixteenths" % (a.which, used, len(d)), flush=True)

    rng = np.random.default_rng(1337)
    res = {}
    for label, Y in (("n_pitch_onsets(0..4)", n), ("pitch_class_set(12-bit)", pc)):
        mi = cond_mi_bits(d, Y, pos)
        floors = []
        for _ in range(a.shuffles):
            Ys = Y.copy()
            for zv in np.unique(pos):                 # permute WITHIN the bucket
                m = np.flatnonzero(pos == zv)
                Ys[m] = Y[rng.permutation(m)]
            floors.append(cond_mi_bits(d, Ys, pos))
        f_m, f_s = float(np.mean(floors)), float(np.std(floors, ddof=1))
        hy = cond_entropy_bits(Y, pos)
        res[label] = {
            "I(D;Y|pos)_bits_per_sixteenth": round(mi, 5),
            "shuffle_floor_bits": round(f_m, 5),
            "shuffle_floor_sd": round(f_s, 6),
            "REAL_bits_per_sixteenth": round(mi - f_m, 5),
            "H(Y|pos)_bits": round(hy, 4),
            "fraction_of_H(Y|pos)_explained_by_drums": round((mi - f_m) / max(hy, 1e-9), 5),
            "n_distinct_Y": int(len(np.unique(Y))),
        }
        print("  %-24s I=%.5f  floor=%.5f+/-%.5f  REAL=%.5f bits/16th  "
              "= %.3f%% of H(Y|pos)=%.3f"
              % (label, mi, f_m, f_s, mi - f_m,
                 100.0 * (mi - f_m) / max(hy, 1e-9), hy), flush=True)

    # what that costs, in the headline unit. `secs` covers exactly the tracks
    # that were read; if --max-steps clipped the last one, scale it down too,
    # or the sixteenths-per-second rate comes out low and the answer looks
    # smaller than it is.
    if have > len(d):
        secs *= len(d) / float(have)
    per16 = res["pitch_class_set(12-bit)"]["REAL_bits_per_sixteenth"]
    steps_per_s = len(d) / max(secs, 1e-9)
    res["_headline"] = {
        "sixteenths": int(len(d)), "seconds": round(secs, 1),
        "sixteenths_per_second": round(steps_per_s, 3),
        "upper_bound_bits_per_second_lost_by_factorising":
            round(per16 * steps_per_s, 4),
        "note": ("This is an UPPER BOUND on what the split throws away by not "
                 "letting the pitch model see the drums, measured with no model "
                 "at all. It is same-step only: a leak across steps would add to "
                 "it. Compare it against the measured bits/second gap in "
                 "split_report.py - if the gap is much larger than this, the gap "
                 "is not caused by the factorisation but by the duplicated clock "
                 "or by the training budget."),
    }
    print("\nupper bound on what the seam throws away: %.4f bits/second of music"
          % res["_headline"]["upper_bound_bits_per_second_lost_by_factorising"])
    Path(a.out).write_text(json.dumps(res, indent=1), encoding="utf-8")
    print("wrote " + a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
