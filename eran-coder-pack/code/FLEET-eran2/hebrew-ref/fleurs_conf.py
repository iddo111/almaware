# -*- coding: utf-8 -*-
"""Leave-SPEAKER-out confusion over the 19 FLEURS phone classes.
Which Hebrew consonants are actually separable across unseen mouths?
CPU only. Reads only. Plays nothing."""
import os, glob, re, wave, json, collections
import numpy as np
FD=os.path.expanduser("~/eran-food-human2")
CL=sorted([d for d in os.listdir(FD) if os.path.isdir(os.path.join(FD,d))])
def rd(p):
    with wave.open(p,"rb") as w:
        return np.frombuffer(w.readframes(w.getnframes()),"<i2").astype(np.float64)/32768.0
def trim(x):
    hop=160
    if x.size<hop*3: return x
    env=np.array([np.sqrt(np.mean(x[i:i+hop]**2)) for i in range(0,x.size-hop,hop)])
    room=np.percentile(env,10); pk=env.max()
    on=env>room+0.10*(pk-room); idx=np.where(on)[0]
    return x[idx[0]*hop:min(x.size,(idx[-1]+1)*hop)] if idx.size else x
def feats(x,nfr=10,nb=26):
    x=trim(x)
    if x.size<400: x=np.pad(x,(0,400-x.size))
    x=x/(np.sqrt(np.mean(x**2))+1e-9)
    win=400; hop=max(1,(x.size-win)//max(1,nfr-1)) if x.size>win else 1
    F=[]
    for k in range(nfr):
        s=min(k*hop,max(0,x.size-win)); seg=x[s:s+win]
        if seg.size<win: seg=np.pad(seg,(0,win-seg.size))
        sp=np.abs(np.fft.rfft(seg*np.hanning(win)))**2
        e=np.linspace(0,sp.size,nb+1).astype(int)
        F.append([np.log(sp[e[i]:e[i+1]].sum()+1e-10) for i in range(nb)])
    F=np.array(F); return np.concatenate([F.ravel(),np.diff(F,axis=0).ravel()])
X=[];y=[];spk=[]
for ci,c in enumerate(CL):
    for f in sorted(glob.glob(os.path.join(FD,c,"*.wav"))):
        m=re.search(r"u(\d+)",os.path.basename(f))
        X.append(feats(rd(f))); y.append(ci); spk.append(m.group(1) if m else "?")
X=np.array(X);y=np.array(y);spk=np.array(spk)
print(f"{X.shape[0]} clips, {len(CL)} classes, {len(set(spk))} speakers, {X.shape[1]} dims",flush=True)
rs=np.random.RandomState(0); sp=np.array(sorted(set(spk)))
C=np.zeros((len(CL),len(CL)))
accs=[]
for fold in range(5):
    rs.shuffle(sp); te_s=set(sp[:len(sp)//5])
    te=np.array([s in te_s for s in spk]); tr=~te
    mu=X[tr].mean(0); sd=X[tr].std(0)+1e-9
    A=(X[tr]-mu)/sd; B=(X[te]-mu)/sd
    # nearest class CENTROID (cheap, no speaker leak)
    cent=np.array([A[y[tr]==k].mean(0) for k in range(len(CL))])
    cn=cent/ (np.linalg.norm(cent,axis=1,keepdims=True)+1e-9)
    Bn=B/(np.linalg.norm(B,axis=1,keepdims=True)+1e-9)
    pred=np.argmax(Bn@cn.T,axis=1)
    accs.append((pred==y[te]).mean())
    for t,p in zip(y[te],pred): C[t,p]+=1
    print(f"  fold {fold+1}: {len(te_s)} unseen mouths, top1 {accs[-1]*100:.1f}%",flush=True)
acc=np.mean(accs)
print(f"\nLEAVE-SPEAKER-OUT top1 {acc*100:.1f}% (sd {np.std(accs)*100:.1f}) vs chance {100/len(CL):.1f}%")
Cn=C/C.sum(1,keepdims=True)
print("\nper-class recall across unseen mouths:")
rec={CL[i]:Cn[i,i] for i in range(len(CL))}
for k,v in sorted(rec.items(),key=lambda t:-t[1]):
    print(f"   {k:<3} {v*100:5.1f}%")
print("\nworst confusions (true -> predicted, off-diagonal):")
pairs=[(Cn[i,j],CL[i],CL[j]) for i in range(len(CL)) for j in range(len(CL)) if i!=j]
for v,a,b in sorted(pairs,reverse=True)[:15]:
    print(f"   {a:<3} taken for {b:<3} {v*100:5.1f}%")
json.dump({"classes":CL,"conf":C.tolist(),"acc":acc},open(os.path.expanduser("~/fleurs_conf.json"),"w"))
print("\nsaved ~/fleurs_conf.json")
