import glob,sys,re,numpy as np,torch
from collections import defaultdict
from safetensors.torch import load_file
d=sys.argv[1]; f=sorted(glob.glob(d+"*.safetensors"))[0]
sd=load_file(f)
def hill(lam,frac=0.2):
    lam=np.sort(lam)[::-1]; k=max(10,int(len(lam)*frac)); t=lam[:k]; xmin=t[-1]
    return 1.0+k/np.sum(np.log(t/xmin)+1e-12)
rows=[]
for k,W in sd.items():
    if W.ndim!=2: continue
    s=torch.linalg.svdvals(W.float()).cpu().numpy()
    smax=float(s[0]); fro2=float((s**2).sum())
    rows.append((k,tuple(W.shape),smax,fro2/(smax**2),hill(s**2),float(s[0]/(s[1]+1e-9))))
def grp(k): return re.sub(r"layers\.\d+","layers.N",k)
G=defaultdict(list)
for r in rows: G[grp(r[0])].append(r)
print("%d 2D weight matrices analyzed\n"%len(rows))
print("%-38s %3s %9s %9s %7s %9s"%("group","n","alpha_med","alpha_min","sr_med","spike_max"))
flags=[]
for g,rs in sorted(G.items()):
    al=np.array([x[4] for x in rs]); sr=np.array([x[3] for x in rs]); sp=np.array([x[5] for x in rs])
    print("%-38s %3d %9.2f %9.2f %7.1f %9.2f"%(g,len(rs),np.median(al),al.min(),np.median(sr),sp.max()))
    med=np.median(al); mad=np.median(np.abs(al-med))+1e-9
    for x in rs:
        z=abs(x[4]-med)/(1.4826*mad)
        if z>4 and len(rs)>4: flags.append((x[0],x[4],med,z,x[5]))
print("\n=== ANOMALY FLAGS (alpha >4 robust-sigma from group median) ===")
if not flags: print("none - spectra homogeneous across layers (no obvious bolted-in low-rank anomaly)")
for name,a,med,z,sp in sorted(flags,key=lambda t:-t[3])[:15]:
    print("  %-52s alpha=%.2f (grp med %.2f, z=%.1f) spike=%.1f"%(name,a,med,z,sp))
al=np.array([r[4] for r in rows])
print("\nGLOBAL alpha range [%.2f,%.2f] median %.2f  (healthy ~2-6; <2 or huge = suspicious)"%(al.min(),al.max(),np.median(al)))
