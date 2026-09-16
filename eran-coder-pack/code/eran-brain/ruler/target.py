# -*- coding: utf-8 -*-
"""target.py -- the ruler was not the broken part. The TARGET is.

> BROKEN WINDOWS LAW: if it is not working, fix it IMMEDIATELY. Test the REAL output.

whose_voice.py measured the thing the whole "fix the ruler" plan rested on and
it did not hold: the six takes of the 396-clip reference set carry 1.3% of the
variance and are retrievable from an unseen syllable at 18.9% against a 16.7%
floor. A take is NOT a different throat. So the 0.575 within-syllable spread is
not a speaker -- it is ordinary variation inside a syllable, and no amount of
speaker-nulling can remove it.

What the same measurement DID find is worse and more useful: the corpus the
throat search actually aims at, t06, is ONE TAKE, its per-unit spread is LARGER
than the six-take reference set's, and its /ba/ centre sits 1.278 from the
reference set's /ba/ centre -- further than any two DIFFERENT syllables sit
apart (0.903). Iddo said it out loud on 08-30 before any of this was measured:
"my reference recordings are full of noise."

This file puts numbers on that, with floors:

  1. how separable Iddo's six t06 units are, leave-one-clip-out. Floor 16.7%.
  2. CROSS-CORPUS. Do the six-take reference centroids retrieve t06's clips of
     the same unit, and vice versa? Two corpora that mean the same thing by
     /ba/ must. Floor 33.3% on the three shared units.
  3. the ruler comparison again, but ON THE TARGET, and the agreement with
     Iddo's ear scored against t06 instead of the reference set.
"""
from __future__ import annotations

import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, "data")
LAM = 0.50


def unit_of(n):
    return n.split("_")[0]


def cent(V, lab, us, renorm=True):
    M = np.stack([V[lab == u].mean(0) for u in us])
    return M / np.linalg.norm(M, axis=1, keepdims=True) if renorm else M


def wccn(V, lab, us, lam=LAM):
    R = np.concatenate([V[lab == u] - V[lab == u].mean(0) for u in us])
    S = np.cov(R, rowvar=False, bias=True)
    S = (1 - lam) * S + lam * (np.trace(S) / S.shape[0]) * np.eye(S.shape[0])
    ev, U = np.linalg.eigh(S)
    A = U @ np.diag(np.maximum(ev, 1e-10) ** -0.5) @ U.T
    return A / np.sqrt(np.mean(np.diag(A @ A.T)))


def main():
    out = {}
    z = np.load(os.path.join(D, "ruler-t06.npz"), allow_pickle=True)
    V6 = z["V"].astype(np.float64)
    n6 = [str(s) for s in z["names"]]
    u6 = np.array([unit_of(s) for s in n6])
    BIG = [u for u in sorted(set(u6)) if (u6 == u).sum() >= 50]

    d = np.load(os.path.join(HERE, "..", "holobrain", "ear-human.npz"),
                allow_pickle=True)
    XR = d["V"].astype(np.float64)
    syl = [str(s) for s in d["syllables"]]
    yR = np.array([syl[i] for i in d["y"]])
    tR = d["t"].astype(np.int64)

    # ------------------------------------------------------------------ 1
    print("1. HOW SEPARABLE IS THE TARGET CORPUS ITSELF?")
    print("   t06, %d clips, units %s. Leave-one-CLIP-out nearest centroid."
          % (len(V6), BIG))
    for label, tf in (("plain centroid", None), ("WCCN centroid", "w")):
        ok = 0
        tot = 0
        sub = np.isin(u6, BIG)
        Vs, us_ = V6[sub], u6[sub]
        A = wccn(Vs, us_, BIG) if tf else np.eye(Vs.shape[1])
        Z = Vs @ A
        for i in range(len(Z)):
            m = np.ones(len(Z), bool)
            m[i] = False
            M = np.stack([Z[m][us_[m] == u].mean(0) for u in BIG])
            M = M / np.linalg.norm(M, axis=1, keepdims=True)
            zz = Z[i] / np.linalg.norm(Z[i])
            ok += (BIG[int(np.linalg.norm(zz - M, axis=1).argmin())] == us_[i])
            tot += 1
        print("     %-16s %5.1f%%   (floor %.1f%%)"
              % (label, 100 * ok / tot, 100 / len(BIG)))
        out["t06_loo_%s_pct" % (tf or "plain")] = round(100 * ok / tot, 2)
    out["t06_floor_pct"] = round(100 / len(BIG), 2)

    # ------------------------------------------------------------------ 2
    print("\n2. CROSS-CORPUS. Do the two human corpora mean the same /ba/?")
    SHARED = [u for u in ("ah", "ba", "ma") if u in BIG and u in syl]
    print("   shared units %s, floor %.1f%%" % (SHARED, 100 / len(SHARED)))
    MR = cent(XR, yR, SHARED)
    M6 = cent(V6, u6, SHARED)
    sel6 = np.isin(u6, SHARED)
    selR = np.isin(yR, SHARED)
    a = float(np.mean([SHARED[int(np.linalg.norm(v - MR, axis=1).argmin())] == u
                       for v, u in zip(V6[sel6], u6[sel6])]))
    b = float(np.mean([SHARED[int(np.linalg.norm(v - M6, axis=1).argmin())] == u
                       for v, u in zip(XR[selR], yR[selR])]))
    print("   reference centroids classify t06 clips     : %5.1f%%" % (100 * a))
    print("   t06 centroids classify reference clips     : %5.1f%%" % (100 * b))
    # and each corpus on itself, same 3 units, so the drop is readable
    aa = float(np.mean([SHARED[int(np.linalg.norm(v - M6, axis=1).argmin())] == u
                        for v, u in zip(V6[sel6], u6[sel6])]))
    bb = float(np.mean([SHARED[int(np.linalg.norm(v - MR, axis=1).argmin())] == u
                        for v, u in zip(XR[selR], yR[selR])]))
    print("   t06 on itself / reference on itself        : %5.1f%% / %5.1f%%"
          % (100 * aa, 100 * bb))
    out["cross"] = {"ref_centroids_on_t06_pct": round(100 * a, 2),
                    "t06_centroids_on_ref_pct": round(100 * b, 2),
                    "t06_self_pct": round(100 * aa, 2),
                    "ref_self_pct": round(100 * bb, 2),
                    "floor_pct": round(100 / len(SHARED), 2)}
    print("\n   centre-to-centre gap between the two corpora, per unit,")
    print("   set against how far two DIFFERENT syllables sit in the reference")
    print("   set (0.903) and how far two clips of the SAME syllable sit (0.574):")
    for u in SHARED:
        g = float(np.linalg.norm(cent(V6, u6, [u])[0] - cent(XR, yR, [u])[0]))
        print("     /%s/  %.3f" % (u, g))
        out.setdefault("centre_gap", {})[u] = round(g, 4)

    # ------------------------------------------------------------------ 3
    print("\n3. AGREEMENT WITH IDDO'S EAR, scored against t06 -- the corpus the")
    print("   search really optimised against. AUC of the ruler separating his")
    print("   1 (recognises) from his 3 (no), pooled within unit. Floor 0.500.")
    j = np.load(os.path.join(D, "ruler-judged.npz"), allow_pickle=True)
    J = j["V"].astype(np.float64)
    jn = [str(s) for s in j["names"]]
    meta = {m["file"]: m for m in json.load(
        open(os.path.join(D, "_meta.json"), encoding="utf-8"))}
    JU = [u for u in BIG]
    M6b = cent(V6, u6, JU)
    A = wccn(V6[np.isin(u6, JU)], u6[np.isin(u6, JU)], JU)
    M6w = np.stack([(V6[u6 == u] @ A).mean(0) for u in JU])

    def s_clip(v, u):        # OLD: nearest single t06 clip of that unit
        return float(np.linalg.norm(V6[u6 == u] - v, axis=1).min())

    def s_cent(v, u):        # NEW: the unit's centre
        return float(np.linalg.norm(v - M6b[JU.index(u)]))

    def s_wccn(v, u):
        return float(np.linalg.norm(v @ A - M6w[JU.index(u)]))

    def s_wd(v, u):          # ear3 convention: per-class centroid AND spread
        P = V6[u6 == u]
        m, s = P.mean(0), P.std(0)
        s = np.maximum(s, max(1e-12, 0.05 * float(np.median(s))))
        return float(np.linalg.norm((v - m) / s))

    rows = [(i, meta[f]["unit"], meta[f]["verdict"])
            for i, f in enumerate(jn)
            if f in meta and meta[f].get("unit") in JU
            and meta[f].get("verdict") in (1, 2, 3)]
    print("   usable judged clips: %d" % len(rows))
    for name, fn in (("OLD  nearest single t06 clip", s_clip),
                     ("OLD  ear3 wdist (per-class spread)", s_wd),
                     ("NEW  t06 unit centroid", s_cent),
                     ("NEW  WCCN + t06 centroid", s_wccn)):
        pos, neg = [], []
        for u in sorted({r[1] for r in rows}):
            p = [fn(J[i], u) for i, uu, v in rows if uu == u and v == 1]
            n = [fn(J[i], u) for i, uu, v in rows if uu == u and v == 3]
            if not p or not n:
                continue
            ref = np.array(p + n)
            mu, sd = ref.mean(), ref.std() + 1e-12
            pos += [(x - mu) / sd for x in p]
            neg += [(x - mu) / sd for x in n]
        pos, neg = np.array(pos), np.array(neg)
        A_ = float(((pos[:, None] < neg[None, :]).sum()
                    + 0.5 * (pos[:, None] == neg[None, :]).sum())
                   / (len(pos) * len(neg)))
        print("     %-38s AUC %.3f   (%d yes vs %d no)"
              % (name, A_, len(pos), len(neg)))
        out.setdefault("auc_vs_t06", {})[name] = round(A_, 4)

    with open(os.path.join(HERE, "target-measured.json"), "w",
              encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    print("\nwrote target-measured.json")


if __name__ == "__main__":
    main()
