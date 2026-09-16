#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""probe_readout2.py -- F2 and G. Two confounds section F owed.

F2. THE DURATION CONFOUND. Real /ba/ takes are ~0.32 s and real /a/ takes
    ~0.72 s, and BLOCK L literally carries total_dur and span_dur (dims 200,
    201). So part of F's AUC is a stopwatch, not an ear. Measured here:
    duration alone, and every group with dims 200-201 deleted.

G.  THE DURATION-FREE BURST TEST. Same clip, twice: intact and RAMP60 (the
    release ramped away). Identical length, identical samples after the first
    60 ms, no splice. A block that separates them is reading the release and
    nothing else. Folds are GROUPED BY CLIP so a pair never straddles the
    split -- otherwise the reader can memorise the take.
    Control: the same ramp on /a/, where there is no release to remove.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.expanduser("~/ear-v3"))
sys.path.insert(0, os.path.expanduser("~/judge2-groundA"))
from groundA import OUT, FINE, auc                                # noqa: E402
from probe_readout import ridge_fit, ridge_pred, folds, LAMBDAS, K_OUT, K_IN  # noqa: E402


def cv_auc_grouped(X, y, group, seed=0):
    """Ridge CV where every fold split keeps a group (= one take) intact."""
    rng = np.random.default_rng(seed)
    g = np.unique(group)
    gf = folds(len(g), K_OUT, rng)
    pred = np.zeros(len(y))
    for k in range(K_OUT):
        gte = set(g[gf[k]].tolist())
        te = np.array([i for i in range(len(y)) if group[i] in gte])
        tr = np.setdiff1d(np.arange(len(y)), te)
        mu, sd = X[tr].mean(axis=0), X[tr].std(axis=0)
        sd = np.maximum(sd, 1e-9)
        Xtr, Xte = (X[tr] - mu) / sd, (X[te] - mu) / sd
        gtr = np.unique(group[tr])
        rng2 = np.random.default_rng(seed + 1000 + k)
        inf = folds(len(gtr), K_IN, rng2)
        best, best_a = LAMBDAS[0], -1.0
        for lam in LAMBDAS:
            ip = np.zeros(len(tr))
            for j in range(K_IN):
                ite_g = set(gtr[inf[j]].tolist())
                ite = np.array([i for i in range(len(tr))
                                if group[tr][i] in ite_g])
                itr = np.setdiff1d(np.arange(len(tr)), ite)
                w = ridge_fit(Xtr[itr], y[tr][itr], lam)
                ip[ite] = ridge_pred(Xtr[ite], w)
            a = auc(ip[y[tr] > 0], ip[y[tr] < 0])
            if a > best_a:
                best_a, best = a, lam
        w = ridge_fit(Xtr, y[tr], best)
        pred[te] = ridge_pred(Xte, w)
    return auc(pred[y > 0], pred[y < 0])


def main():
    zb = np.load(os.path.join(OUT, "probe-ba.npz"))
    za = np.load(os.path.join(OUT, "probe-ah.npz"))
    Vb, Rb, Cb = zb["intact"], zb["ramp60"], zb["cut60"]
    Va, Ra = za["intact"], za["ramp60"]
    rep = {}

    print("=" * 78)
    print("F2. THE DURATION CONFOUND in the /ba/-vs-/a/ contrast")
    print("=" * 78)
    X = np.concatenate([Vb, Va])
    y = np.concatenate([np.ones(len(Vb)), -np.ones(len(Va))])
    grp = np.arange(len(y))                      # no pairing here
    dur = X[:, 200:202]
    print("   real /ba/ span_dur p50 %.3f s | real /a/ span_dur p50 %.3f s"
          % (np.median(Vb[:, 201]), np.median(Va[:, 201])))
    a = cv_auc_grouped(dur, y, grp)
    print("   DURATION ALONE (dims 200,201, d=2):            AUC %.3f" % a)
    rep["duration_only"] = float(a)
    keep = np.array([i for i in range(996) if i not in (200, 201)])
    for name, lo, hi in [("ALL 996", 0, 996), ("legacy192", 0, 192),
                         ("level", 192, 202), ("coch_slice0", 202, 267),
                         ("onset_slice0", 908, 919), ("pitch", 722, 853)]:
        cols = np.array([c for c in range(lo, hi) if c not in (200, 201)])
        a = cv_auc_grouped(X[:, cols], y, grp)
        print("   %-22s d=%-5d minus duration:  AUC %.3f" % (name, len(cols), a))
        rep["nodur_" + name] = float(a)

    print()
    print("=" * 78)
    print("G. DURATION-FREE BURST TEST -- intact vs RAMP60, SAME clip, same")
    print("   length. Folds grouped by take. ctrl = the same ramp on /a/.")
    print("=" * 78)
    print("   %-16s%6s%10s%11s%9s" % ("block", "d", "ba", "ctrl(ah)", "gap"))
    n = len(Vb)
    gpair = np.concatenate([np.arange(n), np.arange(n)])
    yy = np.concatenate([np.ones(n), -np.ones(n)])
    rows = []
    groups = list(FINE) + [("ALL 996", 0, 996), ("192:996 no legacy", 192, 996),
                           ("first-slice 192:267", 192, 267)]
    for name, lo, hi in groups:
        Xb = np.concatenate([Vb[:, lo:hi], Rb[:, lo:hi]])
        Xa = np.concatenate([Va[:, lo:hi], Ra[:, lo:hi]])
        ab = cv_auc_grouped(Xb, yy, gpair)
        aa = cv_auc_grouped(Xa, yy, gpair)
        rows.append((name, hi - lo, ab, aa))
        rep["ramp_" + name] = {"ba": float(ab), "ah": float(aa)}
    for name, d, ab, aa in sorted(rows, key=lambda r: -(r[2] - r[3])):
        bar = "#" * int(round(max(0.0, ab - aa) * 60))
        print("   %-16s%6d%10.3f%11.3f%9.3f  %s" % (name, d, ab, aa, ab - aa, bar))

    with open(os.path.join(OUT, "readout2-report.json"), "w",
              encoding="utf-8") as f:
        json.dump(rep, f, indent=1)
    print()
    print("wrote " + os.path.join(OUT, "readout2-report.json"))


if __name__ == "__main__":
    main()
