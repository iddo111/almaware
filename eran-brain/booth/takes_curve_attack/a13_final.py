"""A13 -- is the honest flat-line driven only by /ma/ (the one cross-session unit)?"""
import json, numpy as np
from probe import load, nn1, DEEP
X, unit, take, mt, sit, dur = load()
rng = np.random.default_rng(101)
idx = {u: np.where(unit == u)[0][np.argsort(take[np.where(unit == u)[0]])] for u in DEEP}
FAR, LATE = np.arange(0,33), np.arange(67,100)
NG=[1,3,10,20,33]
print("  set (all HONEST: train takes 0-32, test takes 67-99)      chance  " +
      "".join(f"N={n:<6d}" for n in NG) + " N=33/N=10")
for name, us in [("all 6 deep units", DEEP),
                 ("5 units, /ma/ removed (no cross-sitting unit)", [u for u in DEEP if u!="ma"]),
                 ("3 units recorded in ONE unbroken sitting {ba,abba,ima}", ["ba","abba","ima"]),
                 ("/a/ family only {ah,ba,ma,abba}", ["ah","ba","ma","abba"])]:
    c=[]
    for N in NG:
        a=[]
        for _ in range(300):
            tr=np.concatenate([idx[u][rng.choice(FAR,N,replace=False)] for u in us])
            te=np.concatenate([idx[u][LATE] for u in us])
            a.append(nn1(X[tr],unit[tr],X[te],unit[te])[1])
        c.append(100*float(np.mean(a)))
    print(f"  {name:54s}  {100/len(us):5.1f}%  " + "".join(f"{v:<8.2f}" for v in c) +
          f" {c[-1]-c[NG.index(10)]:+.2f} pts")
