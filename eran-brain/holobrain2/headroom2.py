# -*- coding: utf-8 -*-
"""HEADROOM PROBE 2 -- can the thing the sibling would LEARN actually move the number?

Probe 1 proved the RULER is not blind (ceiling 0.6481, floor 0.0806). But it also
showed something uncomfortable: the honest cross-take task (0.6389) sits 0.0093
below the same-take ceiling. Session shift is NOT what is costing the sibling its
accuracy -- the syllables are simply confusable in this ear. So "same-take" is a
WEAK ceiling and proves nothing about whether learning has room.

The real question, and the one that catches a LayerNorm(1) before it is shipped:
does the PARAMETER FAMILY the loop would fit have any reach at all?

The family: a per-dimension listening posture g (192 numbers, all 1.0 at birth,
which reproduces the inherited ear exactly). It divides the ear's own spread:
    wdist_g(v,u) = sqrt( sum_d ((v_d - t_ud)/w_ud)^2 * g_d )

  BORN     g = 1                                     the inherited ear
  HONEST   g fitted on TRAIN takes only              what the loop can really do
  ORACLE   g fitted on ALL takes incl. the test one  a deliberate cheat
  CHEAT+   g hill-climbed directly on the test take  the family's own ceiling

If CHEAT+ cannot clear BORN, the posture cannot move and there is nothing to
learn -- report it and STOP. If HONEST clears BORN, the loop is real.
"""
import sys
import numpy as np

sys.path.insert(0, "/home/eran3")
from headroom import spread_floor, SIB_UNITS          # noqa: E402

NPZ = "/home/eran3/ear-human.npz"


def load():
    d = np.load(NPZ, allow_pickle=True)
    V, Y, T, SYL = d["V"].astype(np.float64), d["y"], d["t"], [str(s) for s in d["syllables"]]
    keep = [i for i in range(len(Y)) if SYL[Y[i]] in SIB_UNITS]
    remap = {SYL.index(u): k for k, u in enumerate(SIB_UNITS)}
    return V[keep], np.array([remap[Y[i]] for i in keep]), T[keep]


def refs(V, y, idx, n_units):
    out = {}
    for u in range(n_units):
        P = V[[i for i in idx if y[i] == u]]
        if len(P) < 2:
            continue
        out[u] = (P.mean(axis=0), spread_floor(P.std(axis=0)))
    return out


def acc(V, y, probe, R, g):
    """One pass, vectorised. g is the posture; g=1 is the inherited ear."""
    us = sorted(R)
    Tm = np.stack([R[u][0] for u in us]); Wm = np.stack([R[u][1] for u in us])
    Z = (V[probe][:, None, :] - Tm[None, :, :]) / Wm[None, :, :]
    D = np.sqrt(np.einsum("pud,d->pu", Z * Z, g))
    return float(np.mean(np.array(us)[np.argmin(D, axis=1)] == y[probe]))


def fisher(V, y, idx, n_units):
    """between-syllable variance / within-syllable variance, per dim, on idx only.

    This is the posture the loop fits: keep the dims that separate SYLLABLES,
    discard the dims that only tell you whose mouth it was."""
    mu = V[idx].mean(axis=0); wi = []; bt = []
    for u in range(n_units):
        P = V[[i for i in idx if y[i] == u]]
        if len(P) < 2:
            continue
        wi.append(P.var(axis=0)); bt.append((P.mean(axis=0) - mu) ** 2)
    w = np.mean(wi, axis=0); b = np.mean(bt, axis=0)
    r = b / (w + 1e-12)
    return r / np.mean(r)                       # mean-1 so it is a posture, not a scale


def main():
    V, y, t = load()
    n_units, takes = len(SIB_UNITS), sorted(set(t.tolist()))
    born = hon = ora = che = 0.0
    one = np.ones(V.shape[1])
    rows = []
    for tk in takes:
        tr = [i for i in range(len(y)) if t[i] != tk]
        te = [i for i in range(len(y)) if t[i] == tk]
        R = refs(V, y, tr, n_units)
        b = acc(V, y, te, R, one)
        h = acc(V, y, te, R, fisher(V, y, tr, n_units))
        o = acc(V, y, te, R, fisher(V, y, list(range(len(y))), n_units))
        # CHEAT+: hill-climb the posture ON THE TEST TAKE. Deliberate overfit.
        g = fisher(V, y, tr, n_units).copy(); best = acc(V, y, te, R, g)
        rng = np.random.RandomState(0)
        for _ in range(300):
            gp = g * np.exp(rng.normal(0, 0.25, size=g.shape) *
                            (rng.rand(*g.shape) < 0.10))
            s = acc(V, y, te, R, gp)
            if s > best:
                g, best = gp, s
        rows.append((tk, b, h, o, best))
        born += b; hon += h; ora += o; che += best
    n = float(len(takes))
    print("held-out    BORN(g=1)  HONEST(fit on train)  ORACLE(fit on all)  CHEAT+(fit on test)")
    for tk, b, h, o, c in rows:
        print("  t%02d        %.4f       %.4f              %.4f            %.4f" % (tk, b, h, o, c))
    print("  MEAN       %.4f       %.4f              %.4f            %.4f"
          % (born / n, hon / n, ora / n, che / n))
    print()
    print("chance 0.0833 | floor(shuffled) 0.0806 | born %.4f" % (born / n))
    print("FAMILY REACH   cheat+ - born = %+.4f   <- the most the posture could ever buy"
          % (che / n - born / n))
    print("HONEST GAIN    honest - born = %+.4f   <- what the loop can actually buy"
          % (hon / n - born / n))
    ok = (che / n - born / n) > 0.02
    print()
    print("VERDICT: %s" % (
        "the posture MOVES the number. A loop fitted to it is not a LayerNorm(1)."
        if ok else
        "DEAD PARAMETER. Even fitted directly on the answers the posture cannot move "
        "the number. STOP -- this family is another LayerNorm(1)."))
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
