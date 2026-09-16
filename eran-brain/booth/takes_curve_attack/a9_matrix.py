"""A9 -- the 6-way confusion matrix under the honest design, and WHY each unit is hard.
Two different causes get lumped together as 'hard'. Separate them:
  (1) session drift  -- the unit's train and test blocks are different sittings
  (2) phonetic collision -- the unit's train and test are the SAME sitting and it
      still loses, to a syllable that shares its vowel.
"""
import json, collections, numpy as np
from probe import load, nn1, DEEP
X, unit, take, mt, sit, dur = load()
rng = np.random.default_rng(53)
idx = {u: np.where(unit == u)[0][np.argsort(take[np.where(unit == u)[0]])] for u in DEEP}
EARLY, LATE = np.arange(0,33), np.arange(67,100)
print("which sittings does each deep unit's EARLY and LATE block come from?")
for u in DEEP:
    e = sorted(set(sit[idx[u][EARLY]])); l = sorted(set(sit[idx[u][LATE]]))
    same = "SAME sitting" if set(e) == set(l) and len(e) == 1 else ("OVERLAP" if set(e) & set(l) else "*** DIFFERENT SITTINGS ***")
    print(f"  {u:5s} early sits {e}   late sits {l}   -> {same}")

C = np.zeros((6,6))
for _ in range(200):
    tr = np.concatenate([idx[u][rng.choice(EARLY,10,replace=False)] for u in DEEP])
    te = np.concatenate([idx[u][LATE] for u in DEEP])
    p, _ = nn1(X[tr], unit[tr], X[te], unit[te])
    for i,u in enumerate(DEEP):
        for j,v in enumerate(DEEP):
            C[i,j] += np.sum((unit[te]==u) & (p==v))
C = 100*C/C.sum(1, keepdims=True)
print("\n6-way confusion, N=10 honest (rows=truth, cols=predicted), %:")
print("        " + "".join(f"{v:>7s}" for v in DEEP))
for i,u in enumerate(DEEP):
    print(f"  {u:5s} " + "".join(f"{C[i,j]:7.1f}" for j in range(6)))
print("\n  biggest off-diagonal flows:")
fl = sorted(((C[i,j], DEEP[i], DEEP[j]) for i in range(6) for j in range(6) if i!=j), reverse=True)
for c,a,b in fl[:6]: print(f"    {a:5s} -> {b:5s}  {c:5.1f}%")
json.dump(dict(matrix=C.tolist(), units=DEEP), open("a9.json","w"), indent=1)
