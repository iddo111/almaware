import json, numpy as np, datetime
rows = json.load(open("feats.json"))
rows.sort(key=lambda r: r["mtime"])
mt = np.array([r["mtime"] for r in rows]); un=[r["unit"] for r in rows]
gaps = np.diff(mt)
same = np.array([un[i+1]==un[i] for i in range(len(un)-1)])
inrun = gaps<=120
print("session %s -> %s" % (datetime.datetime.fromtimestamp(mt[0]), datetime.datetime.fromtimestamp(mt[-1])))
print("n clips %d  n gaps %d  in-run gaps (<=120s) %d" % (len(rows), len(gaps), inrun.sum()))
g=gaps[inrun]
print("in-run gap: min %.2f p25 %.2f median %.2f p75 %.2f p90 %.2f mean %.2f" % (g.min(),np.percentile(g,25),np.median(g),np.percentile(g,75),np.percentile(g,90),g.mean()))
gs = gaps[inrun & same]; gn = gaps[inrun & ~same]
print("same-syllable  n=%d median %.2f mean %.2f" % (len(gs), np.median(gs), gs.mean()))
print("prompt-change  n=%d median %.2f mean %.2f" % (len(gn), np.median(gn), gn.mean()))
# runs
brk = np.where(gaps>120)[0]
starts=[0]+list(brk+1); ends=list(brk)+[len(rows)-1]
print("runs:")
tot=0
for s,e in zip(starts,ends):
    dur=(mt[e]-mt[s])/60; tot+=dur
    print("   %s  %5.1f min  %3d clips  %.2f s/clip  units=%s" % (
        datetime.datetime.fromtimestamp(mt[s]).strftime("%H:%M"), dur, e-s+1,
        (mt[e]-mt[s])/max(1,(e-s)), "/".join(sorted(set(un[s:e+1])))[:60]))
print("total in-run %.1f min for %d clips = %.2f s/clip; elapsed %.2f h; duty %.1f%%" % (
    tot, len(rows), tot*60/len(rows), (mt[-1]-mt[0])/3600, 100*tot*60/(mt[-1]-mt[0])))
# model
def t(N, sw=None, pc=None):
    sw = sw if sw else np.mean(gs); pc = pc if pc else np.mean(gn)
    return ((N-1)*sw + pc)/N
for N in [3,4,5,10,12,20]:
    per = t(N)
    print("  N=%2d takes/unit: %.2f s/clip | 22-unit row = %d clips = %.1f min | 140 units x N = %d clips = %.2f h" % (
        N, per, 22*N, 22*N*per/60, 140*N, 140*N*per/3600))
