# -*- coding: utf-8 -*-
import json, io, os, collections, numpy as np
SP = os.path.dirname(os.path.abspath(__file__))
ROWS = json.load(io.open(r'D:\CLAUDE\eran-brain\throat-ruler-measure\feats.json', encoding='utf-8'))
BAND = json.load(io.open(os.path.join(SP,'human-band.json'), encoding='utf-8'))

print('=== TOP END: every clip with f1_traj > 500 Hz, and what he rated it ===')
tops = sorted([r for r in ROWS if (r.get('f1_traj_hz') or 0) > 500], key=lambda r:-r['f1_traj_hz'])
for r in tops:
    print('  %7.1f Hz  y=%.2f  %-4s %-18s %s' % (r['f1_traj_hz'], r['y'], r['unit'], r['source'], (r.get('arm') or '')[:20]))
print('  n above 500:', len(tops))

def strat_auc(rows, score):
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
    return (conc+0.5*ties)/tot if tot else float('nan'), tot

def capped(cap_key):
    def f(d):
        b=BAND.get(d['unit'])
        v=d.get('f1_traj_hz')
        if b is None or v is None or v!=v: return None
        return min(float(v), float(b[cap_key]))
    return f

print()
print('=== chooser candidates, stratified AUC vs his labels ===')
def wd(d):
    v=d.get('wdist'); return None if v is None else -float(v)
def raw(d):
    v=d.get('f1_traj_hz'); return None if v is None else float(v)
rows_show=[('BORN wdist (negated)',wd),('raw f1_traj (uncapped)',raw)]
for ck in ['p75','p90','max']:
    rows_show.append(('capped at his real %-4s'%ck, capped(ck)))
for name,fn in rows_show:
    a,n=strat_auc(ROWS,fn); print('  %-30s AUC %.4f  n_pairs %d'%(name,a,n))

print()
print('=== is there a TURNING POINT?  AUC restricted by f1_traj range ===')
for loq,hiq in [(0,400),(0,600),(200,900),(300,1500),(400,1600)]:
    sub=[r for r in ROWS if r.get('f1_traj_hz') is not None and r['f1_traj_hz']==r['f1_traj_hz'] and loq<=r['f1_traj_hz']<=hiq]
    a,n=strat_auc(sub,raw)
    print('  f1_traj in [%4d,%4d]  n_clips %3d  AUC %.3f  n_pairs %4d'%(loq,hiq,len(sub),a,n))

print()
print('=== his mean rating by f1_traj decile (all 136) ===')
v=np.array([r['f1_traj_hz'] for r in ROWS if r.get('f1_traj_hz') is not None])
y=np.array([r['y'] for r in ROWS if r.get('f1_traj_hz') is not None])
o=np.argsort(v)
for i in range(0,len(o),14):
    ix=o[i:i+14]
    print('  f1_traj %7.1f..%7.1f  n=%2d  mean y %.3f'%(v[ix].min(),v[ix].max(),len(ix),y[ix].mean()))
