import json, collections
import numpy as np
rows = json.load(open("feats.json"))
rows.sort(key=lambda r: r["mtime"])
# sittings = runs separated by >120 s
sit=0; last=None
for r in rows:
    if last is not None and r["mtime"]-last > 120: sit+=1
    r["sit"]=sit; last=r["mtime"]
by = collections.defaultdict(list)
for r in rows: by[(r["unit"],r["sit"])].append(np.array(r["vec"]))
X = np.array([r["vec"] for r in rows])
mu, sd = X.mean(0), X.std(0)+1e-9
groups = {k:np.array([(v-mu)/sd for v in vs]) for k,vs in by.items() if len(vs)>=8}
units = sorted(set(k[0] for k in groups))
multi = [u for u in units if sum(1 for k in groups if k[0]==u)>1]
print("units with >=2 sittings of >=8 clips:", multi)
sw_num=sw_den=0.0; means=collections.defaultdict(list); ns=collections.defaultdict(list)
for (u,s),G in groups.items():
    if u not in multi: continue
    c = G.mean(0)
    sw_num += ((G-c)**2).sum(); sw_den += (len(G)-1)*G.shape[1]
    means[u].append(c); ns[u].append(len(G))
sw2 = sw_num/sw_den
sb_num=sb_den=0.0
for u in multi:
    M = np.array(means[u]); gm = M.mean(0)
    sb_num += ((M-gm)**2).sum(); sb_den += (len(M)-1)*M.shape[1]
sb2_raw = sb_num/sb_den
kbar = np.mean([np.mean(ns[u]) for u in multi])
sb2 = max(0.0, sb2_raw - sw2/kbar)   # unbiased: between-mean spread contains sw2/k
print("within-sitting  sigma_w^2 = %.4f  (per-dim, z-scored)" % sw2)
print("between-sitting sigma_b^2 = %.4f  (raw %.4f, minus sw2/kbar=%.4f with kbar=%.1f)" % (sb2, sb2_raw, sw2/kbar, kbar))
print()
def err(K,S): return np.sqrt(sw2/(K*S) + sb2/S)
print("prototype error  sqrt(sw2/(K*S) + sb2/S):")
plans = [(1,1),(3,1),(4,1),(10,1),(30,1),(50,1),(100,1),(200,1),(4,3),(10,3),(3,3),(4,2),(10,10),(12,1),(4,4)]
base = err(30,1)
for K,S in plans:
    e=err(K,S)
    print("  K=%3d takes x S=%2d sittings = %4d clips : err %.4f   (%.2fx better than 30-in-one)" % (K,S,K*S,e,base/e))
print()
print("KEY COMPARISONS")
for a,b in [((30,1),(4,3)),((200,1),(30,1)),((200,1),(4,3)),((10,1),(4,3)),((100,1),(10,3))]:
    ea,eb = err(*a), err(*b)
    print("  %2dx%d (%4d clips) err %.4f   vs  %2dx%d (%4d clips) err %.4f   -> %.2fx" % (
        a[0],a[1],a[0]*a[1],ea,b[0],b[1],b[0]*b[1],eb, ea/eb))
