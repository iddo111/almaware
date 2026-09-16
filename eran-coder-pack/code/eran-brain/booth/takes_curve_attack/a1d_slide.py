"""A1d -- ONE fixed train block, test window slid away from it.

train = 20 takes drawn at random from takes [0,30) of every unit  (the same
        20 for every distance in a draw)
test  = 10 takes drawn at random from takes [O, O+30) of every unit
Sweep O.  O=0 means test clips sit INSIDE the training window (interleaved);
O=70 means they are ~2.7 minutes later in the same sitting.
Only the distance changes. Train size, test size and probe are identical.
"""
import json, numpy as np
from probe import load, nn1, DEEP
X, unit, take, mt, sit, dur = load()
idx = {u: np.where(unit == u)[0][np.argsort(take[np.where(unit == u)[0]])] for u in DEEP}
rng = np.random.default_rng(11)
# measured seconds per take, per unit, from mtimes (median consecutive gap)
gaps = []
for u in DEEP:
    t = np.sort(mt[np.where(unit == u)[0]]); g = np.diff(t); gaps += list(g[g < 60])
SPT = float(np.median(gaps))
print(f"median seconds per take, measured from mtimes: {SPT:.2f} s\n")
print("  O   test takes   ~seconds after train   accuracy   (6-way, chance 16.67%)")
rows = []
for O in [0, 10, 20, 30, 40, 50, 60, 70]:
    accs = []
    for _ in range(400):
        tr, te = [], []
        for u in DEEP:
            trk = rng.choice(np.arange(0, 30), 20, replace=False)
            pool = np.arange(O, O + 30)
            tek = rng.choice(np.setdiff1d(pool, trk) if O < 30 else pool, 10, replace=False)
            tr.append(idx[u][trk]); te.append(idx[u][tek])
        tr, te = np.concatenate(tr), np.concatenate(te)
        accs.append(nn1(X[tr], unit[tr], X[te], unit[te])[1])
    m, se = 100*np.mean(accs), 100*np.std(accs)/np.sqrt(len(accs))
    rows.append(dict(O=O, sec=round((O)*SPT,1), acc=m, se=se))
    print(f" {O:3d}   [{O:3d},{O+30:3d})      {O*SPT:7.1f}          {m:6.2f} +-{se:4.2f}")
json.dump(dict(sec_per_take=SPT, rows=rows), open("a1d.json","w"), indent=1)

print("\n=== per-unit: early(0-32) -> late(67-99), N=20 train, all 33 late as test ===")
print("  unit   own-class recall early->late   own-class recall within-early")
EARLY, LATE = np.arange(0,33), np.arange(67,100)
rec_el, rec_in = {u: [] for u in DEEP}, {u: [] for u in DEEP}
for _ in range(200):
    tr = np.concatenate([idx[u][rng.choice(EARLY,20,replace=False)] for u in DEEP])
    te = np.concatenate([idx[u][LATE] for u in DEEP])
    pred,_ = nn1(X[tr], unit[tr], X[te], unit[te])
    for u in DEEP: rec_el[u].append(np.mean(pred[unit[te]==u]==u))
    tr2, te2 = [], []
    for u in DEEP:
        p = rng.permutation(EARLY); tr2.append(idx[u][p[:20]]); te2.append(idx[u][p[20:]])
    tr2, te2 = np.concatenate(tr2), np.concatenate(te2)
    pred2,_ = nn1(X[tr2], unit[tr2], X[te2], unit[te2])
    for u in DEEP: rec_in[u].append(np.mean(pred2[unit[te2]==u]==u))
for u in DEEP:
    print(f"  {u:5s}  {100*np.mean(rec_el[u]):6.2f}                    {100*np.mean(rec_in[u]):6.2f}")
