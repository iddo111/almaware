# -*- coding: utf-8 -*-
"""Build the R5-WCCN dowry table into copy-new/dowry, then prove offline (against
BOTH lean copies -- copy-old untouched, copy-new patched) that `correct` is no
longer a dead wire capped at 3/12.

Runs the REAL anatomy.listen() / dowry.load_all() code, unmodified, from each
lean copy. Never imports or touches the live ~/sibling or ~/sibling-ear, never
starts a service. Pure read + a write into /tmp/sibling-prep/copy-new/dowry only.
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, "/home/eran3")
from sibling_ear import CORPUS_UNITS, EXAM_TAKE, fit_whitener, build_refs_flat, wdist_matrix

EAR_HUMAN = "/home/eran3/sibling-ear/corpus/ear-human.npz"
DOWRY_VECS = "/home/eran3/sibling-ear/dowry-vectors.json"
LAM = 0.7
TRAIN_TAKES = {0, 1, 2, 3, 4}
COPY_NEW_DOWRY = "/tmp/sibling-prep/copy-new/dowry"


def fit_ruler():
    d = np.load(EAR_HUMAN, allow_pickle=True)
    V = d["V"].astype(np.float64)
    y = np.asarray(d["y"])
    t = np.asarray(d["t"])
    syl = [str(s) for s in d["syllables"]]
    remap = {syl.index(u): k for k, u in enumerate(CORPUS_UNITS)}
    keep = [i for i in range(len(y)) if syl[y[i]] in CORPUS_UNITS]
    V12 = V[keep]
    y12 = np.array([remap[y[i]] for i in keep])
    t12 = t[keep]
    idx12 = [i for i in range(len(y12)) if int(t12[i]) in TRAIN_TAKES]

    fit_all_full = [i for i in range(len(y)) if int(t[i]) in TRAIN_TAKES]
    A = fit_whitener(V, y, fit_all_full, LAM)   # whitener fit on all 22 syllables

    W0 = V12 @ A.T
    R0 = build_refs_flat(W0, y12, idx12, len(CORPUS_UNITS))
    _, D0 = wdist_matrix(W0, idx12, R0, np.ones(W0.shape[1]), {})
    sc = 8.2184 / max(float(np.mean(D0)), 1e-12)
    W = W0 * sc
    R = build_refs_flat(W, y12, idx12, len(CORPUS_UNITS))

    exam_idx = [i for i in range(len(y12)) if int(t12[i]) == EXAM_TAKE]
    us, D = wdist_matrix(W, exam_idx, R, np.ones(W.shape[1]), {})
    pred = np.asarray(us)[np.argmin(D, axis=1)]
    acc = float(np.mean(pred == y12[exam_idx]))
    print("sealed-take (t05) accuracy reproduced by this fit: %.4f "
          "(must equal journal's R5-WCCN BORN = 0.8889)" % acc)
    assert abs(acc - 0.8889) < 0.0005, "whitener fit does not reproduce the documented ruler"
    return A, sc, R


def write_new_dowry(A, sc, R):
    us_sorted = sorted(R)
    unit_name = {u: CORPUS_UNITS[u] for u in us_sorted}
    vecs996 = json.load(open(DOWRY_VECS, encoding="utf-8"))

    def new_nearest_for(unit):
        v = np.asarray(vecs996[unit], dtype=np.float64)[:192]
        w = (v[None, :] @ A.T) * sc
        _, D = wdist_matrix(w, [0], R, np.ones(w.shape[1]), {})
        row = D[0]
        pairs = sorted(((unit_name[u], round(float(row[j]), 4))
                         for j, u in enumerate(us_sorted)), key=lambda kv: kv[1])
        return pairs

    n_written = 0
    for unit in sorted(vecs996):
        src = os.path.join(COPY_NEW_DOWRY, unit + ".json")
        if not os.path.exists(src):
            print("  skip %s: not a dowry.py unit (no old json to preserve fields from)" % unit)
            continue
        d = json.load(open(src, encoding="utf-8"))
        pairs = new_nearest_for(unit)
        d["nearest"] = [{"unit": u, "wdist": w} for u, w in pairs]
        d["nearest_ruler"] = "R5-WCCN"
        d["nearest_ruler_note"] = ("Rebuilt 2026-09-07 from sibling-ear's corrected "
            "R5-WCCN whitener (fit_whitener/build_refs_flat/wdist_matrix, lam=0.7, "
            "train takes t00-t04, EXAM_TAKE=5 never touched). Targets limited to the "
            "12 CORPUS_UNITS the human corpus actually has (abba/ima/ih dropped as "
            "TARGETS -- NO_HUMAN_MATERIAL in sibling_ear.py -- same honesty rule the "
            "dowry already applies to itself.")
        json.dump(d, open(src, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
        n_written += 1
    print("wrote new nearest tables for %d/%d dowry units into %s"
          % (n_written, len(vecs996), COPY_NEW_DOWRY))


def sweep(copy_root, thetas, taus):
    """Run the REAL anatomy.listen()/dowry.load_all() from one lean copy, across
    a theta x tau grid, exactly reproducing round()'s self-naming loop for each
    grid point. Returns {(theta,tau): correct_count}."""
    sys.path.insert(0, copy_root)
    for m in ("anatomy", "dowry"):
        sys.modules.pop(m, None)
    import anatomy
    import dowry as dowry_mod
    units = dowry_mod.load_all()
    out = {}
    for th in thetas:
        for ta in taus:
            correct = 0
            for u, v in units.items():
                o = anatomy.listen(v["nearest"], theta=th, tau=ta)
                if o["said"] == u:
                    correct += 1
            out[(th, ta)] = correct
    sys.path.remove(copy_root)
    return out, units


def main():
    A, sc, R = fit_ruler()
    write_new_dowry(A, sc, R)

    # THETA default is 3/15=0.2 (15 candidates at birth); TAU default is 1.0.
    # Sweep around both defaults -- same spirit as the prior session's "72-point
    # theta x tau sweep" that never moved the OLD table off 3/12.
    thetas = [0.05, 0.10, 0.15, 0.20, 0.25, 0.35, 0.50]
    taus = [0.25, 0.5, 1.0, 2.0, 4.0]

    print("\n=== OLD table (copy-old, untouched) ===")
    old_out, old_units = sweep("/tmp/sibling-prep/copy-old", thetas, taus)
    old_vals = sorted(set(old_out.values()))
    for (th, ta), c in sorted(old_out.items()):
        print("  theta=%.2f tau=%.2f -> correct=%d/12" % (th, ta, c))
    print("OLD distinct correct values across %d grid points: %s"
          % (len(old_out), old_vals))

    print("\n=== NEW table (copy-new, R5-WCCN rebuilt) ===")
    new_out, new_units = sweep("/tmp/sibling-prep/copy-new", thetas, taus)
    new_vals = sorted(set(new_out.values()))
    for (th, ta), c in sorted(new_out.items()):
        print("  theta=%.2f tau=%.2f -> correct=%d/12" % (th, ta, c))
    print("NEW distinct correct values across %d grid points: %s"
          % (len(new_out), new_vals))

    print("\n=== VERDICT ===")
    print("OLD table: %d distinct correct-value(s) over the grid -> %s"
          % (len(old_vals), "DEAD WIRE (frozen)" if len(old_vals) == 1 else "moves"))
    print("NEW table: %d distinct correct-value(s) over the grid -> %s"
          % (len(new_vals), "still frozen!" if len(new_vals) == 1 else "MOVES -- dead wire is gone"))


if __name__ == "__main__":
    main()
