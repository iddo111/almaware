# -*- coding: utf-8 -*-
"""THE PROPOSED CHOOSER, measured against Iddo. FLOOR / BORN / CEILING / HEADROOM."""
import json, io, os, collections, numpy as np
SP=os.path.dirname(os.path.abspath(__file__))
ROWS=json.load(io.open(r'D:\CLAUDE\eran-brain\throat-ruler-measure\feats.json',encoding='utf-8'))
BAND=json.load(io.open(os.path.join(SP,'human-band.json'),encoding='utf-8'))
BARS=json.load(io.open(os.path.join(SP,'real-clip-bars.json'),encoding='utf-8'))['units']

def f1cost(d):
    b=BAND.get(d['unit']); v=d.get('f1_traj_hz')
    if b is None or not b.get('usable'): return None
    cap=float(b['p90'])
    if v is None or v!=v: return 1.0
    return (cap-min(float(v),cap))/cap

def wfence(d):
    u=BARS.get(d['unit']); w=d.get('wdist')
    if u is None or w is None: return None
    bar=float(u['win_bar_1p3x_mean'])
    return max(0.0,(float(w)-bar))/bar

print('=== how many clips violate the wdist fence, by his rating ===')
g=collections.defaultdict(lambda:[0,0])
for d in ROWS:
    f=wfence(d)
    if f is None: continue
    g[round(d['y'],2)][0]+=1
    if f>0: g[round(d['y'],2)][1]+=1
for k in sorted(g): print('  y=%.2f  n=%3d  outside fence %3d'%(k,g[k][0],g[k][1]))

def strat_auc(rows,score):
    S=collections.defaultdict(list)
    for d in rows:
        v=score(d)
        if v is None or v!=v: continue
        S[(d['source'],d['unit'])].append((float(v),float(d['y'])))
    conc=ties=tot=0
    for arr in S.values():
        for i in range(len(arr)):
            for j in range(i+1,len(arr)):
                (a,ya),(b,yb)=arr[i],arr[j]
                if ya==yb: continue
                tot+=1; hi,lo=(a,b) if ya>yb else (b,a)
                if hi>lo: conc+=1
                elif hi==lo: ties+=1
    return (conc+0.5*ties)/tot if tot else float('nan'),tot

def comp(wf):
    def f(d):
        a=f1cost(d); b=wfence(d)
        if a is None: return None
        if b is None: b=0.0
        return -(1.0*a + wf*b)
    return f

print()
print('=== THE CHOOSER ===')
def wd(d):
    v=d.get('wdist'); return None if v is None else -float(v)
a,n=strat_auc(ROWS,wd);           print('  BORN     wdist minimised (incumbent) AUC %.4f  n_pairs %d'%(a,n))
a0,_=strat_auc(ROWS,lambda d: -(f1cost(d) if f1cost(d) is not None else None) if f1cost(d) is not None else None)
print('  term     -f1cost alone                 AUC %.4f'%a0)
for wf in [0.0,1.0,3.0,10.0]:
    a,n=strat_auc(ROWS,comp(wf)); print('  PROPOSED -f1cost - %4.1f*wfence        AUC %.4f  n_pairs %d'%(wf,a,n))

# FLOOR
rng=np.random.default_rng(20260901); ys=np.array([r['y'] for r in ROWS]); null=[]
sc=comp(3.0)
for _ in range(2000):
    p=rng.permutation(len(ROWS))
    sh=[dict(r,y=float(ys[p[i]])) for i,r in enumerate(ROWS)]
    null.append(strat_auc(sh,sc)[0])
null=np.array(null)
obs=strat_auc(ROWS,sc)[0]
pv=float((null>=obs).mean())
print()
print('  FLOOR   (2000 label shuffles)          %.4f +- %.4f   95%% [%.3f, %.3f]'
      %(null.mean(),null.std(),np.percentile(null,2.5),np.percentile(null,97.5)))
print('  permutation p for the proposed chooser  %.5f'%max(pv,1/2000))

# CEILING: ridge on all numeric features fit ON THE TEST (cheat)
FE=['burst_rise_db','burst_rise_hf_db','head_hf_ratio_db','burst_time_s','vot_ms','voice_onset_s',
 'f1_med','f2_med','f2_f1','f2_traj_hz','f1_traj_hz','spec_flux','tilt_db_oct','centroid_hz','hf_lf_db',
 'f0_med','f0_range_st','f0_iqr_st','f0_slope_st_s','f0_jitter','periodicity','hnr_db','voiced_frac',
 'dur_total','dur_active','attack_s','decay_s','mod_ratio','noisefloor_rel_db','snr_db','crest_db',
 'rms_db','peak_db','wdist']
X=[]; Y=[]
for d in ROWS:
    v=[d.get(k) for k in FE]
    v=[np.nan if (x is None) else float(x) for x in v]
    X.append(v); Y.append(float(d['y']))
X=np.array(X); Y=np.array(Y)
col=np.nanmean(X,axis=0)
idx=np.where(np.isnan(X)); X[idx]=np.take(col,idx[1])
X=(X-X.mean(0))/np.maximum(X.std(0),1e-9)
X=np.hstack([X,np.ones((len(X),1))])
w=np.linalg.solve(X.T@X+1.0*np.eye(X.shape[1]), X.T@Y)
pred=X@w
for i,d in enumerate(ROWS): d['_cheat']=float(pred[i])
a,n=strat_auc(ROWS,lambda d: d['_cheat'])
print('  CEILING ridge on 34 feats fit ON TEST   %.4f'%a)
