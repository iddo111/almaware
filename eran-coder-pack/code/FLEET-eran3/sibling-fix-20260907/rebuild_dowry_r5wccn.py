# -*- coding: utf-8 -*-
"""Rebuild the sibling's dowry `nearest` table with the ACTUAL R5-WCCN ruler.

Supersedes ~/sibling-ear/rebuild_dowry.py (2026-09-01), which measured 0/12 and
1/12 self-naming and never wired anything in -- read closely, that script never
called fit_whitener()/build_refs_flat()/wdist_matrix() from sibling_ear.py at all.
It reimplemented R4's per-class-diagonal-spread formula (headroom.spread_floor,
per-unit std) on RAW unwhitened legacy192 features, with the R5 hill-climbed
posture `g` bolted on top of a space that g was never fitted for. That is not
R5-WCCN; it is R4 wearing R5's clothes, and its bad numbers were measuring that
mismatch, not the ruler.

This script instead calls the SAME functions sibling_ear.py's Ear class uses at
runtime: fit_whitener() (pooled within-class covariance, WCCN, lam dev-chosen =
0.7 per state/posture.json and the 2026-09-01 17:17 family_change record) and
build_refs_flat() (flat centroids in the whitened space, no per-class spread --
R5's whole point). Train takes are t00-t04 (EXAM_TAKE=5 is never touched, exactly
as sibling_ear.py's own whiten() enforces).

READ-ONLY. Prints old-vs-new self-naming under the CORRECT R5-WCCN math and does
NOT write any file. A second script (apply_dowry_r5wccn.py) does the writing,
after this one is inspected.
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, "/home/eran3")
from sibling_ear import (
    CORPUS_UNITS, EXAM_TAKE, WCCN_LAMBDAS,
    fit_whitener, build_refs_flat, wdist_matrix,
)

EAR_HUMAN = "/home/eran3/sibling-ear/corpus/ear-human.npz"
POSTURE = "/home/eran3/sibling-ear/state/posture.json"
DOWRY_VECS = "/home/eran3/sibling-ear/dowry-vectors.json"
LAM = 0.7          # dev-chosen, from state/posture.json + journal family_change
TRAIN_TAKES = {0, 1, 2, 3, 4}   # everything except EXAM_TAKE=5


def load_corpus():
    d = np.load(EAR_HUMAN, allow_pickle=True)
    V = d["V"].astype(np.float64)
    y = np.asarray(d["y"])
    t = np.asarray(d["t"])
    syl = [str(s) for s in d["syllables"]]
    return V, y, t, syl


def main():
    V, y, t, syl = load_corpus()
    print("ear-human corpus: V=%s  units=%s" % (V.shape, syl))

    fit_all = [i for i in range(len(y)) if int(t[i]) in TRAIN_TAKES]
    A = fit_whitener(V, y, fit_all, LAM)

    # remap corpus onto the 12 CORPUS_UNITS the exam/dowry actually name
    remap = {syl.index(u): k for k, u in enumerate(CORPUS_UNITS)}
    keep = [i for i in range(len(y)) if syl[y[i]] in CORPUS_UNITS]
    V12 = V[keep]
    y12 = np.array([remap[y[i]] for i in keep])
    t12 = t[keep]
    idx12 = [i for i in range(len(y12)) if int(t12[i]) in TRAIN_TAKES]

    W0 = V12 @ A.T
    R0 = build_refs_flat(W0, y12, idx12, len(CORPUS_UNITS))
    _, D0 = wdist_matrix(W0, idx12, R0, np.ones(W0.shape[1]), {})
    sc = 8.2184 / max(float(np.mean(D0)), 1e-12)   # DIST_SCALE from sibling_ear.py
    W = W0 * sc
    R = build_refs_flat(W, y12, idx12, len(CORPUS_UNITS))
    print("whitener fit on %d clips, %d units resolved as centroids"
          % (len(fit_all), len(R)))

    # sealed-take sanity check against the corpus's own held-out take (t05),
    # reproducing the 0.8889 the journal recorded for R5-WCCN BORN.
    exam_idx = [i for i in range(len(y12)) if int(t12[i]) == EXAM_TAKE]
    if exam_idx:
        us, D = wdist_matrix(W, exam_idx, R, np.ones(W.shape[1]), {})
        pred = np.asarray(us)[np.argmin(D, axis=1)]
        acc = float(np.mean(pred == y12[exam_idx]))
        print("sealed-take (t05) ruler accuracy, this script's math: %.4f "
              "(journal recorded R5-WCCN BORN = 0.8889 -- must match)" % acc)

    # ---- now score the DOWRY's own 12 units against those same centroids ----
    vecs996 = json.load(open(DOWRY_VECS, encoding="utf-8"))
    us_sorted = sorted(R)
    unit_name = {u: CORPUS_UNITS[u] for u in us_sorted}

    def score(vec192):
        w = (vec192[None, :] @ A.T) * sc
        _, D = wdist_matrix(w, [0], R, np.ones(w.shape[1]), {})
        row = D[0]
        return sorted(((unit_name[u], float(row[j])) for j, u in enumerate(us_sorted)),
                      key=lambda kv: kv[1])

    print("\nDOWRY self-naming under the CORRECT R5-WCCN ruler "
          "(legacy192 = first 192 dims of the Ear-v3 996-dim vector, "
          "as judge.py's BLOCK_GAINS documents):")
    hit = 0
    for unit in sorted(vecs996):
        v = np.asarray(vecs996[unit], dtype=np.float64)[:192]
        tb = score(v)
        top = tb[0][0]
        ok = unit in unit_name.values() and top == unit
        hit += ok
        print("   %-4s -> %-4s  d=%-8.3f %s   (%s)"
              % (unit, top, tb[0][1], "OK" if ok else "",
                 "no corpus centroid for this unit -- named against the 12 it CAN reach"
                 if unit not in unit_name.values() else ""))
    named = sum(1 for u in vecs996 if u in unit_name.values())
    print("\n%d/%d dowry units that HAVE a corpus centroid name themselves correctly."
          % (hit, named))
    print("(compare: OLD static table's frozen result was correct=3/12 forever; "
          "old rebuild_dowry.py's mismatched-math draft got 0/12 and 1/12)")


if __name__ == "__main__":
    main()
