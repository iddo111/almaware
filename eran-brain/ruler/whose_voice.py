# -*- coding: utf-8 -*-
"""whose_voice.py -- is a TAKE a different throat, and is t06 one throat?

> BROKEN WINDOWS LAW: if it is not working, fix it IMMEDIATELY. Test the REAL output.

Two questions the whole ruler argument rests on, neither of which was measured:

  Q1. Do the six takes of the 396-clip reference set carry a strong identity of
      their own? Measured directly: leave-one-SYLLABLE-out 6-way TAKE retrieval.
      If take identity survives when the syllable is unseen, the take is a
      throat, and the within-take direction is exactly the nuisance the ruler
      has been climbing. Floor: 16.67%.

  Q2. The throat search does not target these 396 clips. It targets t06 --
      6 units x ~100 repetitions, ALL FROM ONE TAKE. If t06 is one session of
      one mouth, then no centroid over t06 can average a speaker away, because
      there is only one speaker in it. Measured: where t06 sits relative to the
      six takes of the reference set, and how far ERAN's candidates sit from
      each.

This is the difference between fixing the ruler and fixing what it is held up
against.
"""
from __future__ import annotations

import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, "data")


def main():
    d = np.load(os.path.join(HERE, "..", "holobrain", "ear-human.npz"),
                allow_pickle=True)
    X = d["V"].astype(np.float64)
    y = d["y"].astype(np.int64)
    t = d["t"].astype(np.int64)
    syl = [str(s) for s in d["syllables"]]
    C, T = len(syl), int(t.max()) + 1
    out = {}

    # ---------------------------------------------------------------- Q1
    print("Q1  IS A TAKE A THROAT?")
    print("    leave-one-SYLLABLE-out, 6-way TAKE retrieval. The take centroid is")
    print("    built from 21 syllables; the held-out syllable's clips are asked")
    print("    which take they came from. Floor 16.67%%.\n")
    accs = []
    for c in range(C):
        tr, te = y != c, y == c
        M = np.stack([X[tr][t[tr] == k].mean(0) for k in range(T)])
        M = M / np.linalg.norm(M, axis=1, keepdims=True)
        pred = np.linalg.norm(X[te][:, None, :] - M[None, :, :], axis=-1).argmin(1)
        accs.append(float((pred == t[te]).mean()))
    print("    TAKE retrieval on unseen syllables: %.1f%%   (floor %.1f%%)"
          % (100 * np.mean(accs), 100 / T))
    out["take_retrieval_unseen_syllable_pct"] = round(100 * float(np.mean(accs)), 2)
    out["take_retrieval_floor_pct"] = round(100 / T, 2)

    # the same question for the syllable, so the two are on one page
    accs2 = []
    for k in range(T):
        tr, te = t != k, t == k
        M = np.stack([X[tr][y[tr] == c].mean(0) for c in range(C)])
        M = M / np.linalg.norm(M, axis=1, keepdims=True)
        pred = np.linalg.norm(X[te][:, None, :] - M[None, :, :], axis=-1).argmin(1)
        accs2.append(float((pred == y[te]).mean()))
    print("    SYLLABLE retrieval on unseen takes : %.1f%%   (floor %.1f%%)"
          % (100 * np.mean(accs2), 100 / C))
    out["syllable_retrieval_unseen_take_pct"] = round(100 * float(np.mean(accs2)), 2)

    # variance split
    gm = X.mean(0)
    tot = float(((X - gm) ** 2).sum())
    bt = float(sum(len(X[t == k]) * ((X[t == k].mean(0) - gm) ** 2).sum()
                   for k in range(T)))
    bs = float(sum(len(X[y == c]) * ((X[y == c].mean(0) - gm) ** 2).sum()
                   for c in range(C)))
    print("\n    variance explained by TAKE     : %.1f%%" % (100 * bt / tot))
    print("    variance explained by SYLLABLE : %.1f%%" % (100 * bs / tot))
    out["var_take_pct"] = round(100 * bt / tot, 2)
    out["var_syllable_pct"] = round(100 * bs / tot, 2)

    # ---------------------------------------------------------------- Q2
    print("\nQ2  WHAT IS THE SEARCH ACTUALLY AIMED AT?")
    z = np.load(os.path.join(D, "ruler-t06.npz"), allow_pickle=True)
    V6 = z["V"].astype(np.float64)
    n6 = [str(s) for s in z["names"]]
    u6 = np.array([s.split("_")[0] for s in n6])
    tk6 = sorted({s.split("_")[1] for s in n6})
    print("    t06 corpus: %d clips, %d units, takes present: %s"
          % (len(V6), len(set(u6)), tk6))
    out["t06_takes"] = tk6
    out["t06_n"] = len(V6)

    # how tight is t06 compared with the six-take reference set?
    for unit in ("ba", "ma", "ah"):
        a = V6[u6 == unit]
        if not len(a):
            continue
        ca = a.mean(0); ca /= np.linalg.norm(ca)
        spread6 = float(np.linalg.norm(a - a.mean(0), axis=1).mean())
        if unit in syl:
            b = X[y == syl.index(unit)]
            cb = b.mean(0); cb /= np.linalg.norm(cb)
            spreadR = float(np.linalg.norm(b - b.mean(0), axis=1).mean())
            gap = float(np.linalg.norm(ca - cb))
            print("    /%s/  t06 (n=%d, one take) spread %.3f  |  6-take ref "
                  "(n=%d) spread %.3f  |  the two centres are %.3f apart"
                  % (unit, len(a), spread6, len(b), spreadR, gap))
            out["unit_%s" % unit] = {"t06_spread": round(spread6, 4),
                                     "ref_spread": round(spreadR, 4),
                                     "centre_gap": round(gap, 4)}

    # where do ERAN's candidates sit, against BOTH corpora?
    c = np.load(os.path.join(D, "ruler-cand.npz"), allow_pickle=True)
    Cv = c["V"].astype(np.float64)
    cn = [str(s) for s in c["names"]]
    print("\n    ERAN's 22 v3 arm bests, judged 6-way against t06 (the corpus the")
    print("    search actually optimised against) and 22-way against the")
    print("    six-take reference set:")
    U6 = sorted({u for u in u6 if (u6 == u).sum() >= 50})
    M6 = np.stack([V6[u6 == u].mean(0) for u in U6])
    M6 = M6 / np.linalg.norm(M6, axis=1, keepdims=True)
    MR = np.stack([X[y == i].mean(0) for i in range(C)])
    MR = MR / np.linalg.norm(MR, axis=1, keepdims=True)
    ok6 = tot6 = 0
    rows = []
    for i, nm in enumerate(cn):
        arm = nm.replace("v3best__", "").replace(".wav", "")
        u = arm.replace("control-", "").split("-")[0]
        g6 = U6[int(np.linalg.norm(Cv[i] - M6, axis=1).argmin())]
        gR = syl[int(np.linalg.norm(Cv[i] - MR, axis=1).argmin())]
        if u in U6:
            tot6 += 1
            ok6 += (g6 == u)
        rows.append({"arm": arm, "want": u, "t06_says": g6, "ref22_says": gR})
        print("      %-20s want %-4s   t06 6-way -> %-5s   ref 22-way -> %s"
              % (arm, u, g6, gR))
    print("\n    t06 6-way agreement with the arm's own name: %d / %d" % (ok6, tot6))
    out["cand_rows"] = rows
    out["cand_t06_correct"] = [ok6, tot6]

    with open(os.path.join(HERE, "whose-voice.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    print("\nwrote whose-voice.json")


if __name__ == "__main__":
    main()
