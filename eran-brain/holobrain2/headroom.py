# -*- coding: utf-8 -*-
"""HEADROOM PROBE -- run BEFORE the sibling's loop is wired to anything.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

WHY THIS FILE EXISTS. Two of Iddo's organs are sick in the same way tonight: the
nezer's four-band gate detects 4 of 29 negatives and has not moved in ten refits,
and the throat's wdist ruler cannot see a burst at all. Both LOOK like they are
learning. Both are structurally incapable of moving. That is the LayerNorm(1)
class of scar, and the only defence is to measure the RULER before trusting it
with a loop.

So: no learning is wired until this probe shows the measure can separate an easy
case from an impossible one, on the sibling's own material, with its own units.

  CEILING  name a human clip using references built from the SAME take
           (same session, same mouth, same room). If the ear cannot do THIS,
           it sees nothing and the whole plan is dead.
  TASK     name a held-out take using references from the other takes. This is
           the real job and the number the loop will move.
  FLOOR    identical protocol, labels permuted before the references are built.
           The syllable signal is destroyed; everything else is untouched.
  CHANCE   1/12 by construction (12 units, 18 clips each, perfectly balanced).

If CEILING does not clear FLOOR by a wide margin the answer is STOP, and this
script says so in words rather than shipping another blind ruler.
"""
import json, sys
import numpy as np

NPZ = sys.argv[1] if len(sys.argv) > 1 else "/home/eran3/ear-human.npz"
# The sibling's units (anatomy.UNITS) that human material actually exists for.
# ih / abba / ima are in its anatomy and NOT in this corpus -- said out loud
# rather than quietly dropped.
SIB_UNITS = ("pa","ma","na","ta","ga","da","la","ka","aa","ah","ra","ba")
MISSING   = ("ih","abba","ima")

W_FLOOR_ABS, W_FLOOR_REL, BLOCK_GAIN, D = 1e-3, 0.05, 12.0, 192


def spread_floor(std):
    """ear3/judge.py spread_floor(), legacy192 block only -- copied, not invented."""
    std = np.asarray(std, dtype=np.float64)
    med = float(np.median(std))
    floor = max(W_FLOOR_ABS, W_FLOOR_REL * med)
    return np.maximum(std, floor) * (np.sqrt(D) / np.sqrt(BLOCK_GAIN))


def refs(V, y, idx, units, g=None):
    """centroid + spread per unit, over the rows in idx. g = optional per-dim posture."""
    out = {}
    for u in range(len(units)):
        P = V[[i for i in idx if y[i] == u]]
        if len(P) < 2:
            continue
        t = P.mean(axis=0); w = spread_floor(P.std(axis=0))
        out[u] = (t, w if g is None else w / np.sqrt(np.maximum(g, 1e-6)))
    return out


def name(v, R):
    """ear3/judge.py wdist(): spread-weighted L2. argmin = what the ear calls it."""
    best, bu = None, None
    for u, (t, w) in R.items():
        d = float(np.sqrt(np.sum(((v - t) / w) ** 2)))
        if best is None or d < best:
            best, bu = d, u
    return bu


def acc(V, y, probe_idx, R):
    hit = sum(1 for i in probe_idx if name(V[i], R) == y[i])
    return hit / float(len(probe_idx)), hit, len(probe_idx)


def main():
    d = np.load(NPZ, allow_pickle=True)
    V, Y, T, SYL = d["V"].astype(np.float64), d["y"], d["t"], [str(s) for s in d["syllables"]]
    keep = [i for i in range(len(Y)) if SYL[Y[i]] in SIB_UNITS]
    units = [u for u in SIB_UNITS]
    remap = {SYL.index(u): k for k, u in enumerate(units)}
    V, y, t = V[keep], np.array([remap[Y[i]] for i in keep]), T[keep]
    takes = sorted(set(t.tolist()))
    print("corpus            %d clips, %d units, %d takes  (%d dims)" % (len(y), len(units), len(takes), V.shape[1]))
    print("units             %s" % " ".join(units))
    print("NOT in corpus     %s   <- the sibling has these units and no human material for them" % " ".join(MISSING))
    print("chance            %.4f  (1/%d)" % (1.0 / len(units), len(units)))
    print()

    # ---- CEILING: references from the SAME take, leave-one-clip-out ----------
    hit = n = 0
    for tk in takes:
        idx = [i for i in range(len(y)) if t[i] == tk]
        for i in idx:
            R = refs(V, y, [j for j in idx if j != i], units)
            hit += (name(V[i], R) == y[i]); n += 1
    ceiling = hit / float(n)
    print("CEILING  same-take, leave-one-clip-out      %.4f   (%d/%d)" % (ceiling, hit, n))

    # ---- TASK: leave-one-TAKE-out (the 08-21 session-leak scar, obeyed) -----
    per, hit, n = {}, 0, 0
    for tk in takes:
        tr = [i for i in range(len(y)) if t[i] != tk]
        te = [i for i in range(len(y)) if t[i] == tk]
        a, h, m = acc(V, y, te, refs(V, y, tr, units))
        per["t%02d" % tk] = round(a, 4); hit += h; n += m
    task = hit / float(n)
    print("TASK     leave-one-TAKE-out (the real job)  %.4f   (%d/%d)" % (task, hit, n))
    print("         per held-out take                  %s" % json.dumps(per))

    # ---- FLOOR: same protocol, labels permuted -----------------------------
    fl = []
    for seed in range(5):
        rng = np.random.RandomState(seed); ys = y.copy(); rng.shuffle(ys)
        hit = n = 0
        for tk in takes:
            tr = [i for i in range(len(y)) if t[i] != tk]
            te = [i for i in range(len(y)) if t[i] == tk]
            R = refs(V, ys, tr, units)
            hit += sum(1 for i in te if name(V[i], R) == ys[i]); n += len(te)
        fl.append(hit / float(n))
    floor = float(np.mean(fl))
    print("FLOOR    same protocol, labels permuted     %.4f   (5 seeds: %s)"
          % (floor, ", ".join("%.4f" % f for f in fl)))
    print()
    sep = ceiling - floor
    print("SEPARATION  ceiling - floor = %.4f" % sep)
    print("HEADROOM    task %.4f sits %.4f above floor, %.4f below ceiling"
          % (task, task - floor, ceiling - task))
    ok = sep > 0.25 and task > floor + 0.10
    print()
    print("VERDICT: %s" % ("the measure MOVES -- a loop may be wired to it."
                           if ok else
                           "BLIND RULER. ceiling and floor are not separated. "
                           "STOP -- do not wire a loop to this."))
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
