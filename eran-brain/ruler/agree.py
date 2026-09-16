# -*- coding: utf-8 -*-
"""agree.py -- does the NEW ruler agree with IDDO'S EAR better than the old one?

> BROKEN WINDOWS LAW: if it is not working, fix it IMMEDIATELY. Test the REAL output.

ruler.py measured the ruler on HUMAN clips. That is necessary and not sufficient:
the throat search never scores a human, it scores ERAN's synthetic mouth, which
lives off the human manifold. So this file runs the two tests a ruler for a
throat actually has to pass.

  TEST 1 -- IDDO'S EAR. 112 candidates ERAN found himself, each one already
    ruled on by Iddo at the judging station: 1 = he recognises it, 3 = no.
    Within each unit, does the ruler put his YES nearer the target than his NO?
    Reported as AUC. Floor: 0.500, a coin. This is the only ground truth that
    exists for a synthetic clip.

  TEST 2 -- OFF-MANIFOLD SAFETY. A whitening ruler divides by directions the
    human corpus barely moves in. A human clip lives inside that corpus and is
    safe; ERAN's mouth does not. Measured: how far outside the human cloud each
    candidate sits under each ruler, as a multiple of the human bar. A ruler
    that hands a synthetic candidate a score 50x the human bar is measuring its
    own blind spot, not the syllable.

Everything is in the frozen legacy192 cochlea, the ear all these numbers were
born in; data/ruler-ref.npz was recomputed on eran2 and matches
holobrain/ear-human.npz to 1.5e-08.
"""
from __future__ import annotations

import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, "data")
LAM = 0.50          # the shrinkage the nested fold-honest pick landed on (median)
FLOOR_REL = 0.05


def unit_of(name):
    return name.split("_")[0]


def load():
    r = np.load(os.path.join(D, "ruler-ref.npz"), allow_pickle=True)
    X = r["V"].astype(np.float64)
    names = [str(s) for s in r["names"]]
    units = sorted({unit_of(n) for n in names})
    y = np.array([units.index(unit_of(n)) for n in names])
    j = np.load(os.path.join(D, "ruler-judged.npz"), allow_pickle=True)
    J = j["V"].astype(np.float64)
    jn = [str(s) for s in j["names"]]
    meta = {m["file"]: m for m in json.load(open(os.path.join(D, "_meta.json"),
                                                 encoding="utf-8"))}
    c = np.load(os.path.join(D, "ruler-cand.npz"), allow_pickle=True)
    return X, y, units, J, jn, meta, c["V"].astype(np.float64), \
        [str(s) for s in c["names"]]


# ------------------------------------------------------------------ rulers
def build(X, y, C):
    M = np.stack([X[y == c].mean(0) for c in range(C)])
    Mn = M / np.linalg.norm(M, axis=1, keepdims=True)
    W = []
    for c in range(C):
        s = X[y == c].std(0, ddof=0)
        W.append(np.maximum(s, max(1e-12, FLOOR_REL * float(np.median(s)))))
    W = np.stack(W)
    R = np.concatenate([X[y == c] - X[y == c].mean(0) for c in range(C)])
    S = np.cov(R, rowvar=False, bias=True)
    S = (1 - LAM) * S + LAM * (np.trace(S) / S.shape[0]) * np.eye(S.shape[0])
    ev, U = np.linalg.eigh(S)
    ev = np.maximum(ev, 1e-10)
    A = U @ np.diag(ev ** -0.5) @ U.T
    A = A / np.sqrt(np.mean(np.diag(A @ A.T)))     # scale-neutral, for readability
    MA = M @ A
    amp = float(np.sqrt(ev.max() / ev.min()))

    def old_clip(V):     # distance to the NEAREST single human clip of the unit
        Dm = np.linalg.norm(V[:, None, :] - X[None, :, :], axis=-1)
        return np.stack([Dm[:, y == c].min(1) for c in range(C)], 1)

    def old_wdist(V):    # ear3.judge convention: per-class centroid AND spread
        return np.stack([np.linalg.norm((V - M[c]) / W[c], axis=-1)
                         for c in range(C)], 1)

    def new_cent(V):     # distance to the syllable's centre
        return np.linalg.norm(V[:, None, :] - Mn[None, :, :], axis=-1)

    def new_wccn(V):     # centre, in the within-class-whitened space
        return np.linalg.norm((V @ A)[:, None, :] - MA[None, :, :], axis=-1)

    return {"OLD  nearest single clip": old_clip,
            "OLD  ear3 wdist (per-class spread)": old_wdist,
            "NEW  syllable centroid": new_cent,
            "NEW  WCCN whiten + centroid": new_wccn}, amp


def auc(pos, neg):
    """P(a random pos scores LOWER than a random neg). Distances: lower=better."""
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    if not len(pos) or not len(neg):
        return float("nan"), 0
    w = (pos[:, None] < neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum()
    return float(w / (len(pos) * len(neg))), len(pos) * len(neg)


def main():
    X, y, units, J, jn, meta, Cv, cn = load()
    C = len(units)
    print("reference: %d human clips, %d units %s" % (len(X), C, units))
    rulers, amp = build(X, y, C)
    print("WCCN condition number at lam=%.2f: %.2f  (1.0 = no reweighting at all)"
          % (LAM, amp))

    # the human bar per ruler: how far a real human clip sits from its own centre
    bar = {}
    for name, f in rulers.items():
        s = f(X)
        bar[name] = float(np.mean([s[i, y[i]] for i in range(len(X))]))

    # ---------------------------------------------------- TEST 1: Iddo's ear
    print("\nTEST 1 -- AGREEMENT WITH IDDO'S EAR")
    print("  112 candidates ERAN found himself; within each unit, AUC of the")
    print("  ruler score separating his 1 (recognises) from his 3 (no).")
    print("  floor 0.500 = a coin. above 0.5 = the ruler agrees with him.\n")
    idx = {u: i for i, u in enumerate(units)}
    rows = []
    for f in jn:
        m = meta.get(f)
        if not m or m.get("unit") not in idx or m.get("verdict") not in (1, 2, 3):
            continue
        rows.append((jn.index(f), m["unit"], m["verdict"], m.get("wdist")))
    print("  judged clips usable: %d  (%s)"
          % (len(rows), {v: sum(1 for r in rows if r[2] == v) for v in (1, 2, 3)}))
    by_unit = {}
    for _, u, v, _ in rows:
        by_unit.setdefault(u, {1: 0, 2: 0, 3: 0})[v] += 1
    print("  per unit: %s\n" % by_unit)

    out = {"units": units, "wccn_condition": amp, "human_bar": bar,
           "verdict_counts": by_unit, "test1": {}, "test2": {}}
    print("  %-38s %10s %10s %8s" % ("ruler", "AUC(1v3)", "AUC(1v2+3)", "pairs"))
    for name, f in rulers.items():
        S = f(J)
        allp13, alln13, allp1x, alln1x = [], [], [], []
        per_unit = {}
        for u in sorted(by_unit):
            iu = idx[u]
            p = [S[i, iu] for i, uu, v, _ in rows if uu == u and v == 1]
            n3 = [S[i, iu] for i, uu, v, _ in rows if uu == u and v == 3]
            nx = [S[i, iu] for i, uu, v, _ in rows if uu == u and v in (2, 3)]
            # z-score inside the unit so units can be pooled honestly
            ref = np.array(p + nx)
            mu, sd = (ref.mean(), ref.std() + 1e-12) if len(ref) > 1 else (0.0, 1.0)
            allp13 += [(x - mu) / sd for x in p]
            alln13 += [(x - mu) / sd for x in n3]
            allp1x += [(x - mu) / sd for x in p]
            alln1x += [(x - mu) / sd for x in nx]
            a13, _ = auc(p, n3)
            per_unit[u] = {"auc_1v3": None if a13 != a13 else round(a13, 3),
                           "n_yes": len(p), "n_no": len(n3)}
        a13, n13 = auc(allp13, alln13)
        a1x, n1x = auc(allp1x, alln1x)
        out["test1"][name] = {"auc_1v3": round(a13, 4), "auc_1v23": round(a1x, 4),
                              "pairs_1v3": n13, "per_unit": per_unit}
        print("  %-38s %10.3f %10.3f %8d" % (name, a13, a1x, n13))

    # ------------------------------------------- TEST 2: off-manifold safety
    print("\nTEST 2 -- OFF-MANIFOLD SAFETY  (score / human bar; 1.0 = as close")
    print("  to the centre as a real human clip is. Big = the ruler is looking")
    print("  at a direction no human ever excited.)\n")
    print("  %-38s %9s %9s %9s %9s" % ("ruler", "human", "ERAN med", "ERAN max",
                                       "ratio"))
    for name, f in rulers.items():
        Sc = f(Cv)
        # each v3 arm best scored against ITS OWN unit
        vals = []
        for i, nm in enumerate(cn):
            arm = nm.replace("v3best__", "").replace(".wav", "")
            u = arm.replace("control-", "").split("-")[0]
            if u in idx:
                vals.append(Sc[i, idx[u]])
        vals = np.array(vals)
        out["test2"][name] = {"human_bar": round(bar[name], 4),
                              "eran_median": round(float(np.median(vals)), 4),
                              "eran_max": round(float(vals.max()), 4),
                              "median_over_bar": round(float(np.median(vals) / bar[name]), 2),
                              "n": len(vals)}
        print("  %-38s %9.3f %9.3f %9.3f %8.1fx"
              % (name, bar[name], np.median(vals), vals.max(),
                 np.median(vals) / bar[name]))

    # ------------------------- TEST 3: what the ruler CALLS ERAN's candidates
    print("\nTEST 3 -- 22-WAY VERDICT ON ERAN'S 22 v3 ARM BESTS")
    print("  %-38s %s" % ("ruler", "called by its own unit's name"))
    for name, f in rulers.items():
        Sc = f(Cv)
        ok = tot = 0
        called = {}
        for i, nm in enumerate(cn):
            arm = nm.replace("v3best__", "").replace(".wav", "")
            u = arm.replace("control-", "").split("-")[0]
            if u not in idx:
                continue
            tot += 1
            got = units[int(Sc[i].argmin())]
            called[arm] = got
            ok += (got == u)
        out.setdefault("test3", {})[name] = {"correct": ok, "total": tot,
                                             "called": called}
        print("  %-38s %d / %d" % (name, ok, tot))

    with open(os.path.join(HERE, "agree-measured.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    print("\nwrote agree-measured.json")


if __name__ == "__main__":
    main()
