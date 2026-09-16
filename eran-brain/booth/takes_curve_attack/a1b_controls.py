"""A1b -- controls for the early->late gap, then the decisive measurement:
accuracy as a function of the FORBIDDEN TEMPORAL WINDOW around each test take.

  gap sweep: leave-one-take-out over ALL 100 takes, but the training takes for
  the unit of the test clip must be at least G takes away in recording order.
  Every other unit contributes N takes chosen the same way (uniformly at random
  from its 100).  G=0 is the ordinary random split.  If accuracy falls as G
  grows, the ear is scoring 'how close in time', not 'which syllable'.
"""
import json, numpy as np
from probe import load, nn1, DEEP

X, unit, take, mt, sit, dur = load()
rng = np.random.default_rng(7)
idx = {u: np.where(unit == u)[0][np.argsort(take[np.where(unit == u)[0]])] for u in DEEP}

EARLY, LATE = np.arange(0, 33), np.arange(67, 100)
print("=== control: direction of the early->late gap (N=20, 200 draws) ===")
for name, TR, TE in [("early -> late", EARLY, LATE), ("late -> early", LATE, EARLY)]:
    acc = []
    for _ in range(200):
        tr = np.concatenate([idx[u][rng.choice(TR, 20, replace=False)] for u in DEEP])
        te = np.concatenate([idx[u][TE] for u in DEEP])
        acc.append(nn1(X[tr], unit[tr], X[te], unit[te])[1])
    print(f"  {name:14s} {100*np.mean(acc):6.2f} +-{100*np.std(acc):5.2f}")
# within-block control: train 20 of first third, test the OTHER 13 of first third
acc = []
for _ in range(200):
    tr, te = [], []
    for u in DEEP:
        p = rng.permutation(EARLY); tr.append(idx[u][p[:20]]); te.append(idx[u][p[20:]])
    acc.append(nn1(X[np.concatenate(tr)], unit[np.concatenate(tr)],
                   X[np.concatenate(te)], unit[np.concatenate(te)])[1])
print(f"  {'within 1st third':14s} {100*np.mean(acc):6.2f} +-{100*np.std(acc):5.2f}   (same block, no time separation)")

print()
print("=== GAP SWEEP: forbidden window G around each test take (N=20/unit, 300 draws) ===")
print("   G  min separation   accuracy")
rows = []
for G in [0, 1, 2, 5, 10, 20, 40, 60, 80]:
    acc = []
    for _ in range(300):
        # one test take per unit
        t_sel = {u: int(rng.integers(0, 100)) for u in DEEP}
        te = np.array([idx[u][t_sel[u]] for u in DEEP])
        tr = []
        for u in DEEP:
            allowed = np.array([k for k in range(100) if abs(k - t_sel[u]) > G])
            if len(allowed) < 20: allowed = np.array([k for k in range(100) if k != t_sel[u]])
            tr.append(idx[u][rng.choice(allowed, 20, replace=False)])
        tr = np.concatenate(tr)
        acc.append(nn1(X[tr], unit[tr], X[te], unit[te])[1])
    m, s = 100*np.mean(acc), 100*np.std(acc)/np.sqrt(300)
    rows.append(dict(G=G, acc=m, se=s))
    print(f"  {G:3d}   >{G:3d} takes    {m:6.2f} +-{s:4.2f} (SE)")
json.dump(rows, open("a1b_gap.json","w"), indent=1)
