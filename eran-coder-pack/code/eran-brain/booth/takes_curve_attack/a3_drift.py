"""A3 -- does the session penalty GROW with the elapsed gap between sittings?

If it does, 'next Tuesday' is worse than the 20-min-to-5-hour gaps this data
contains, and every cross-sitting number above is itself an upper bound.
Two measures per ordered sitting pair of the same unit:
  cos(prototype_A, prototype_B) -- how far his own /ma/ moved
  the within-sitting cos for the same unit, as the scale to read it on
"""
import json, itertools, numpy as np, datetime
from probe import load
X, unit, take, mt, sit, dur = load()
rows = []
print(" unit  sitA->sitB    gap        proto cos   within-A cos  within-B cos   drop")
for u in sorted(set(unit)):
    ss = [s for s in sorted(set(sit[unit == u]))
          if ((unit == u) & (sit == s)).sum() >= 20]
    for a, b in itertools.combinations(ss, 2):
        ra = np.where((unit == u) & (sit == a))[0]
        rb = np.where((unit == u) & (sit == b))[0]
        pa, pb = X[ra].mean(0), X[rb].mean(0)
        pa, pb = pa/np.linalg.norm(pa), pb/np.linalg.norm(pb)
        c = float(pa @ pb)
        # within-sitting scale: split each sitting in half, cos of the halves
        def halfcos(r):
            h = len(r)//2; p = X[r[:h]].mean(0); q = X[r[h:]].mean(0)
            return float((p/np.linalg.norm(p)) @ (q/np.linalg.norm(q)))
        ca, cb = halfcos(ra), halfcos(rb)
        gap_h = (np.median(mt[rb]) - np.median(mt[ra]))/3600.0
        rows.append(dict(unit=u, a=int(a), b=int(b), gap_h=gap_h, proto_cos=c,
                         within_a=ca, within_b=cb, drop=(ca+cb)/2 - c))
        print(f" {u:5s} {a}->{b}      {gap_h:5.2f} h     {c:.4f}      {ca:.4f}       {cb:.4f}     {(ca+cb)/2-c:+.4f}")
r = [x for x in rows]
g = np.array([x["gap_h"] for x in r]); d = np.array([x["drop"] for x in r])
print(f"\n  Pearson r(elapsed gap, prototype drop) = {np.corrcoef(g,d)[0,1]:+.3f}  (n={len(r)} pairs)")
print(f"  gaps span {g.min():.2f} h to {g.max():.2f} h -- ALL inside 2026-08-23.")

print("\n=== the scale that matters: is a sitting-gap as big as a SYLLABLE gap? ===")
DEEP = ["ah","ba","ma","ima","ih","abba"]
protos = {}
for u in DEEP:
    p = X[unit==u].mean(0); protos[u] = p/np.linalg.norm(p)
cross = [(u,v,float(protos[u]@protos[v])) for u,v in itertools.combinations(DEEP,2)]
cross.sort(key=lambda x:-x[2])
print("  DIFFERENT syllables, prototype cos (closest first):")
for u,v,c in cross[:4]: print(f"    {u:5s} vs {v:5s}  {c:.4f}")
print(f"    ... median over all 15 pairs: {np.median([c for _,_,c in cross]):.4f}")
print("  SAME syllable, two different sittings:")
for x in sorted(rows, key=lambda z: z['proto_cos']):
    print(f"    {x['unit']:5s} sit{x['a']} vs sit{x['b']}  {x['proto_cos']:.4f}")
json.dump(rows, open("a3.json","w"), indent=1)
