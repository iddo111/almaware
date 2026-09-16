"""A12 -- is the saturation at N=20 an artifact of the 33-take EARLY pool?

Same test block (takes 67-99) throughout. Two train pools:
  FAR   takes 0-32 only  -- every train take is >=34 takes from the test block
  WIDE  takes 0-66       -- larger N necessarily drags in takes ADJACENT to the
                            test block, which is the leak itself
If WIDE keeps climbing where FAR is flat, the climb is adjacency, not takes.
"""
import json, numpy as np
from probe import load, nn1, DEEP
X, unit, take, mt, sit, dur = load()
rng = np.random.default_rng(97)
idx = {u: np.where(unit == u)[0][np.argsort(take[np.where(unit == u)[0]])] for u in DEEP}
LATE = np.arange(67,100)
FAR, WIDE = np.arange(0,33), np.arange(0,67)
print("    N    FAR (0-32)      WIDE (0-66)     WIDE-FAR   mean take-distance of the")
print("                                                    nearest WIDE train take")
for N in [1,2,3,5,8,10,15,20,25,33,50,67]:
    out={}
    for nm,pool in [("FAR",FAR),("WIDE",WIDE)]:
        if N>len(pool): out[nm]=None; continue
        a=[]; nd=[]
        for _ in range(250):
            tr=[]; 
            for u in DEEP:
                k=rng.choice(pool,N,replace=False); tr.append(idx[u][k])
                if nm=="WIDE": nd.append(67-k.max())
            tr=np.concatenate(tr); te=np.concatenate([idx[u][LATE] for u in DEEP])
            a.append(nn1(X[tr],unit[tr],X[te],unit[te])[1])
        out[nm]=(100*float(np.mean(a)), float(np.mean(nd)) if nd else 0.0)
    f=out["FAR"]; w=out["WIDE"]
    fs = f"{f[0]:6.2f}" if f else "   --"
    ws = f"{w[0]:6.2f}" if w else "   --"
    gp = f"{w[0]-f[0]:+6.2f}" if (f and w) else "    --"
    dd = f"{w[1]:5.1f}" if w else "  --"
    print(f"  {N:3d}    {fs}          {ws}        {gp}      {dd} takes")
