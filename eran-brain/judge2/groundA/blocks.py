#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""blocks.py -- the cleanest burst measurement available, with NO synthetic
manipulation at all, plus the paired manipulation test.

D. THE NATURAL CONTRAST. Human /ba/ and human /a/ from the same booth, same
   speaker, same session. They share the vowel; what /ba/ has and /a/ has not
   is the labial release. So: per block, how well can that block alone tell
   100 real /ba/ from 100 real /a/? Leave-one-out nearest-centroid on the
   block's own z-scored dims, AUC of the margin. 0.5 = the block cannot hear
   the /b/. This needs no cut, no ramp, no splice -- nothing to argue with.

E. THE PAIRED TEST. Per block, does removing the release push the clip AWAY
   from the human /ba/ centroid? Paired AUC over 100 takes, with the same
   operation on /a/ as the false-alarm control.

Reads the vectors groundA.py already wrote. No cochlea, seconds to run.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.expanduser("~/ear-v3"))
sys.path.insert(0, os.path.expanduser("~/judge2-groundA"))
from groundA import OUT, FINE, auc      # noqa: E402


def loo_margin(X, Y, lo, hi, s):
    """Leave-one-out nearest-centroid margin on dims [lo,hi), z-scored by s.
    Positive margin = closer to the X centroid. Returns (mX, mY)."""
    A = X[:, lo:hi] / s[lo:hi]
    B = Y[:, lo:hi] / s[lo:hi]
    ca, cb = A.mean(axis=0), B.mean(axis=0)
    na, nb = len(A), len(B)
    out_a, out_b = [], []
    for i in range(na):                       # leave i out of its OWN centroid
        c = (ca * na - A[i]) / (na - 1)
        out_a.append(np.linalg.norm(A[i] - cb) - np.linalg.norm(A[i] - c))
    for i in range(nb):
        c = (cb * nb - B[i]) / (nb - 1)
        out_b.append(np.linalg.norm(B[i] - ca) - np.linalg.norm(B[i] - c))
    return np.array(out_a), np.array(out_b)


def main():
    zb = np.load(os.path.join(OUT, "probe-ba.npz"))
    za = np.load(os.path.join(OUT, "probe-ah.npz"))
    Vb, Cb, Rb = zb["intact"], zb["cut60"], zb["ramp60"]
    Va, Ca, Ra = za["intact"], za["cut60"], za["ramp60"]
    s = np.concatenate([Vb, Va]).std(axis=0)
    s = np.maximum(s, 1e-9)

    rep = {}
    print("=" * 78)
    print("D. THE NATURAL CONTRAST -- 100 real human /ba/ vs 100 real human /a/")
    print("   (same booth, same speaker, same session; they share the vowel,")
    print("   /ba/ has the labial release and /a/ does not).")
    print("   Leave-one-out nearest-centroid on that block ALONE, z-scored.")
    print("   AUC 0.5 = the block cannot hear the /b/.  No manipulation used.")
    print("=" * 78)
    print("   %-15s%6s%10s" % ("block", "d", "AUC"))
    rows = []
    for name, lo, hi in FINE:
        ma, mb = loo_margin(Vb, Va, lo, hi, s)
        a_ = auc(ma, mb)
        rows.append((name, hi - lo, a_))
        rep[name] = {"d": hi - lo, "auc_ba_vs_ah_natural": float(a_)}
    for name, d, a_ in sorted(rows, key=lambda r: -r[2]):
        bar = "#" * int(round((a_ - 0.5) * 60)) if a_ > 0.5 else ""
        print("   %-15s%6d%10.3f  %s" % (name, d, a_, bar))
    ma, mb = loo_margin(Vb, Va, 0, 996, s)
    print("   %-15s%6d%10.3f  (all 996, equal per-dim weight)"
          % ("ALL", 996, auc(ma, mb)))
    ma, mb = loo_margin(Vb, Va, 192, 996, s)
    print("   %-15s%6d%10.3f  (legacy192 DROPPED)" % ("192:996", 804, auc(ma, mb)))
    ma, mb = loo_margin(Vb, Va, 0, 192, s)
    print("   %-15s%6d%10.3f  (legacy192 ALONE)" % ("0:192", 192, auc(ma, mb)))

    print()
    print("=" * 78)
    print("E. PAIRED TEST -- does removing the release push the clip AWAY from")
    print("   the human /ba/ centroid, as seen by this block alone?")
    print("   AUC over 100 paired takes. ctrl = the same operation on /a/,")
    print("   where there is no release to remove (the false-alarm rate).")
    print("=" * 78)
    for tag, Mb, Ma in (("RAMP60", Rb, Ra), ("CUT60", Cb, Ca)):
        print("   -- %s" % tag)
        print("   %-15s%6s%10s%10s%9s" % ("block", "d", "ba", "ctrl(ah)", "gap"))
        out = []
        for name, lo, hi in FINE:
            c = (Vb[:, lo:hi] / s[lo:hi]).mean(axis=0)
            d_i = np.linalg.norm(Vb[:, lo:hi] / s[lo:hi] - c, axis=1)
            d_m = np.linalg.norm(Mb[:, lo:hi] / s[lo:hi] - c, axis=1)
            ab = auc(d_m, d_i)
            ca_ = (Va[:, lo:hi] / s[lo:hi]).mean(axis=0)
            e_i = np.linalg.norm(Va[:, lo:hi] / s[lo:hi] - ca_, axis=1)
            e_m = np.linalg.norm(Ma[:, lo:hi] / s[lo:hi] - ca_, axis=1)
            aa = auc(e_m, e_i)
            out.append((name, hi - lo, ab, aa))
            rep[name]["auc_%s_ba" % tag.lower()] = float(ab)
            rep[name]["auc_%s_ah" % tag.lower()] = float(aa)
        for name, d, ab, aa in sorted(out, key=lambda r: -(r[2] - r[3])):
            print("   %-15s%6d%10.3f%10.3f%9.3f" % (name, d, ab, aa, ab - aa))
        print()

    with open(os.path.join(OUT, "blocks-report.json"), "w", encoding="utf-8") as f:
        json.dump(rep, f, indent=1)
    print("wrote " + os.path.join(OUT, "blocks-report.json"))


if __name__ == "__main__":
    main()
