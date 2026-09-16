import os, re, wave, collections
import numpy as np
D = r"D:\CLAUDE\eran-brain\booth\staged\t06"
recs=[]
for f in sorted(os.listdir(D)):
    if not f.endswith(".wav"): continue
    m=re.match(r"^(.*)_t06_(\d+)\.wav$", f); p=os.path.join(D,f)
    with wave.open(p,'rb') as w:
        n,sr=w.getnframes(),w.getframerate(); x=np.frombuffer(w.readframes(n),dtype='<i2').astype(np.float32)/32768.0
    peak=float(np.abs(x).max()); rms=float(np.sqrt((x*x).mean()))
    thr=max(0.02,peak*0.10); fr=int(0.01*sr)
    env=np.array([np.abs(x[i:i+fr]).max() for i in range(0,len(x)-fr,fr)])
    v=env>thr
    voiced=float(v.sum()*0.01); span=float((np.where(v)[0].max()-np.where(v)[0].min()+1)*0.01) if v.any() else 0.0
    recs.append(dict(unit=m.group(1),take=int(m.group(2)),mtime=os.path.getmtime(p),
                     dur=n/sr,peak=peak,rms=rms,voiced=voiced,span=span))
recs.sort(key=lambda r:r["mtime"])
sit=0;last=None
for r in recs:
    if last is not None and r["mtime"]-last>120: sit+=1
    r["sit"]=sit; last=r["mtime"]
DEEP=["ah","ba","ma","ima","ih","abba"]
print("LEVEL DRIFT inside one unbroken block (largest block per deep unit)")
rng=np.random.default_rng(0)
for u in DEEP:
    rs=[r for r in recs if r["unit"]==u]
    bysit=collections.Counter(r["sit"] for r in rs); s=bysit.most_common(1)[0][0]
    b=[r for r in rs if r["sit"]==s]; b.sort(key=lambda r:r["mtime"])
    t=np.array([(r["mtime"]-b[0]["mtime"])/60 for r in b])
    db=np.array([20*np.log10(max(r["peak"],1e-6)) for r in b])
    sl=np.polyfit(t,db,1)[0]
    bs=[np.polyfit(t[i],db[i],1)[0] for i in (rng.integers(0,len(b),len(b)) for _ in range(2000))]
    lo,hi=np.percentile(bs,[2.5,97.5])
    print("  %-5s n=%3d block=%4.1f min  slope %+6.2f dB/min  95%% CI [%+.2f,%+.2f]  %s" % (
        u,len(b),t[-1],sl,lo,hi,"DRIFTS" if hi<0 or lo>0 else "flat (n.s.)"))
print()
print("POOLED across all 6 deep units, by take quartile (peak dBFS):")
q=collections.defaultdict(list)
for r in recs:
    if r["unit"] in DEEP: q[min(3,r["take"]//25)].append(20*np.log10(max(r["peak"],1e-6)))
for k in sorted(q): print("   takes %2d-%2d  mean %.1f dBFS  n=%d" % (k*25,k*25+24,np.mean(q[k]),len(q[k])))
mn=min(r["peak"] for r in recs)
print("   quietest clip peak %.4f   booth auto-reject floor 0.03   margin %.0f%%" % (mn,100*(mn/0.03-1)))
print()
print("DURATION drift (voiced span) by quartile, pooled deep:")
qd=collections.defaultdict(list)
for r in recs:
    if r["unit"] in DEEP: qd[min(3,r["take"]//25)].append(r["span"])
for k in sorted(qd): print("   takes %2d-%2d  median %.3f s  n=%d" % (k*25,k*25+24,np.median(qd[k]),len(qd[k])))
tk=np.array([r["take"] for r in recs if r["unit"] in DEEP]); sp=np.array([r["span"] for r in recs if r["unit"] in DEEP])
print("   pooled r(take, voiced span) = %+.4f" % np.corrcoef(tk,sp)[0,1])
print()
print("SHALLOW 19+aa units (the only correctly-trimmed clips):  n=%d" % len([r for r in recs if r["unit"] not in DEEP]))
sh=[r for r in recs if r["unit"] not in DEEP]
print("   file dur   median %.3f s  mean %.3f" % (np.median([r["dur"] for r in sh]),np.mean([r["dur"] for r in sh])))
print("   voiced     median %.3f s  mean %.3f" % (np.median([r["voiced"] for r in sh]),np.mean([r["voiced"] for r in sh])))
n138=sum(1 for r in recs if abs(r["dur"]-1.38)<0.005)
print("   clips stuck at the 1.380 s window ceiling: %d / %d = %.1f%%" % (n138,len(recs),100*n138/len(recs)))
