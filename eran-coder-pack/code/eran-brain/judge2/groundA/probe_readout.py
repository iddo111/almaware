#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""probe_readout.py -- F. A LEARNED READOUT PER BLOCK.

Section D used a nearest-centroid, which is a weak reader in 100-400 dims and
floors every AUC. This asks the same question with the reader Ground B will
actually use: a ridge regression trained on the block's dims.

Task: 100 real human /ba/ vs 100 real human /a/ from the same booth, same
speaker, same session. They share the vowel; /ba/ has the labial release.
So the AUC is a direct measure of how much burst information the block carries.

Protocol (nested, nothing chosen on the scored data):
  outer 10-fold CV (stratified by unit, deterministic split)
  inner 5-fold on the TRAINING folds only picks lambda from a fixed grid
  z-scoring fitted on the training folds only
  AUC computed on the pooled out-of-fold predictions
Floors printed: chance 0.5 and a label-shuffled control (same pipeline).

Pure numpy. Reads the vectors groundA.py already wrote.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.expanduser("~/ear-v3"))
sys.path.insert(0, os.path.expanduser("~/judge2-groundA"))
from groundA import OUT, FINE, auc      # noqa: E402

LAMBDAS = np.array([1e-2, 1e-1, 1.0, 1e1, 1e2, 1e3, 1e4])
K_OUT, K_IN = 10, 5


def ridge_fit(X, y, lam):
    n, d = X.shape
    Xb = np.hstack([X, np.ones((n, 1))])
    A = Xb.T @ Xb + lam * np.eye(d + 1)
    A[-1, -1] -= lam                      # do not penalise the intercept
    return np.linalg.solve(A, Xb.T @ y)


def ridge_pred(X, w):
    return np.hstack([X, np.ones((len(X), 1))]) @ w


def folds(n, k, rng):
    idx = rng.permutation(n)
    return [idx[i::k] for i in range(k)]


def cv_auc(X, y, seed=0):
    rng = np.random.default_rng(seed)
    n = len(y)
    pos, neg = np.where(y > 0)[0], np.where(y < 0)[0]
    fp, fn = folds(len(pos), K_OUT, rng), folds(len(neg), K_OUT, rng)
    pred = np.zeros(n)
    for k in range(K_OUT):
        te = np.concatenate([pos[fp[k]], neg[fn[k]]])
        tr = np.setdiff1d(np.arange(n), te)
        mu, sd = X[tr].mean(axis=0), X[tr].std(axis=0)
        sd = np.maximum(sd, 1e-9)
        Xtr, Xte = (X[tr] - mu) / sd, (X[te] - mu) / sd
        # inner selection of lambda on the training folds only
        ip = np.where(y[tr] > 0)[0]
        ineg = np.where(y[tr] < 0)[0]
        rng2 = np.random.default_rng(seed + 1000 + k)
        gp, gn = folds(len(ip), K_IN, rng2), folds(len(ineg), K_IN, rng2)
        best, best_a = LAMBDAS[0], -1.0
        for lam in LAMBDAS:
            ip_pred = np.zeros(len(tr))
            for j in range(K_IN):
                ite = np.concatenate([ip[gp[j]], ineg[gn[j]]])
                itr = np.setdiff1d(np.arange(len(tr)), ite)
                w = ridge_fit(Xtr[itr], y[tr][itr], lam)
                ip_pred[ite] = ridge_pred(Xtr[ite], w)
            a = auc(ip_pred[y[tr] > 0], ip_pred[y[tr] < 0])
            if a > best_a:
                best_a, best = a, lam
        w = ridge_fit(Xtr, y[tr], best)
        pred[te] = ridge_pred(Xte, w)
    return auc(pred[y > 0], pred[y < 0])


def main():
    Vb = np.load(os.path.join(OUT, "probe-ba.npz"))["intact"]
    Va = np.load(os.path.join(OUT, "probe-ah.npz"))["intact"]
    X = np.concatenate([Vb, Va])
    y = np.concatenate([np.ones(len(Vb)), -np.ones(len(Va))])
    ysh = y.copy()
    np.random.default_rng(7).shuffle(ysh)

    print("=" * 78)
    print("F. LEARNED READOUT PER BLOCK -- 100 real /ba/ vs 100 real /a/")
    print("   ridge, nested 10-fold CV, lambda chosen inside the training")
    print("   folds only. AUC 0.5 = the block cannot hear the /b/.")
    print("=" * 78)
    print("   %-15s%6s%10s%12s%8s" % ("block", "d", "AUC", "shuffled", "lam*"))
    rows, rep = [], {}
    groups = list(FINE) + [("ALL 996", 0, 996), ("192:996 no legacy", 192, 996),
                           ("0:192 legacy only", 0, 192),
                           ("first-slice only", 192, 267)]
    for name, lo, hi in groups:
        Xb = X[:, lo:hi]
        a = cv_auc(Xb, y)
        a0 = cv_auc(Xb, ysh)
        rows.append((name, hi - lo, a, a0))
        rep[name] = {"d": hi - lo, "auc": float(a), "auc_shuffled": float(a0)}
    for name, d, a, a0 in rows:
        bar = "#" * int(round(max(0.0, a - 0.5) * 60))
        print("   %-15s%6d%10.3f%12.3f  %s" % (name[:15], d, a, a0, bar))
    print()
    print("   ranked:")
    for name, d, a, a0 in sorted(rows, key=lambda r: -r[2]):
        print("     %-20s d=%-5d AUC %.3f" % (name, d, a))
    with open(os.path.join(OUT, "readout-report.json"), "w",
              encoding="utf-8") as f:
        json.dump(rep, f, indent=1)
    print()
    print("wrote " + os.path.join(OUT, "readout-report.json"))


if __name__ == "__main__":
    main()
