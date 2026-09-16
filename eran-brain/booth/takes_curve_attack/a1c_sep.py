"""A1c -- accuracy vs TEMPORAL SEPARATION, with everything else held constant.

train = a block of 20 CONSECUTIVE takes starting at s
test  = a block of 10 CONSECUTIVE takes starting at s + 20 + D
Same block sizes at every D. Averaged over every legal s, both directions.
D is measured in takes; the deep runs ran at ~2.3 s/take, so D takes ~= 2.3*D s.
"""
import json, numpy as np
from probe import load, nn1, DEEP
X, unit, take, mt, sit, dur = load()
idx = {u: np.where(unit == u)[0][np.argsort(take[np.where(unit == u)[0]])] for u in DEEP}
TR_W, TE_W = 20, 10
print("  D(takes)  ~seconds   n(s)   accuracy(6-way, chance 16.67)")
rows = []
for D in [0, 2, 5, 10, 20, 30, 40, 50, 60, 70]:
    accs = []
    for s in range(0, 100 - (TR_W + D + TE_W) + 1):
        tr_k = np.arange(s, s + TR_W)
        te_k = np.arange(s + TR_W + D, s + TR_W + D + TE_W)
        for fwd in (True, False):
            a_k, b_k = (tr_k, te_k) if fwd else (te_k, tr_k)   # direction flip
            trk = a_k if fwd else np.arange(s, s+TR_W)         # keep train=20 wide
            if not fwd:
                trk, tek = te_k, tr_k
                if len(trk) != TR_W:  # test block is 10 wide -> flip sizes instead
                    trk2 = np.arange(s + TR_W + D, s + TR_W + D + TR_W) if s+TR_W+D+TR_W<=100 else None
                    if trk2 is None: continue
                    trk, tek = trk2, np.arange(s, s + TE_W)
            else:
                tek = te_k
            tr = np.concatenate([idx[u][trk] for u in DEEP])
            te = np.concatenate([idx[u][tek] for u in DEEP])
            accs.append(nn1(X[tr], unit[tr], X[te], unit[te])[1])
    m, se = 100*np.mean(accs), 100*np.std(accs)/np.sqrt(len(accs))
    rows.append(dict(D=D, sec=round(2.33*D,1), n=len(accs), acc=m, se=se))
    print(f"  {D:5d}     {2.33*D:6.1f}   {len(accs):4d}   {m:6.2f} +-{se:4.2f}")
json.dump(rows, open("a1c_sep.json","w"), indent=1)
