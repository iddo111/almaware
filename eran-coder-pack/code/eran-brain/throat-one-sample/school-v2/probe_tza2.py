import itertools, json, collections, ruler as R
base = dict(R.BASE_0902["tza"]); n=0; passes=[]; hist=collections.Counter()
grid = {"gap_area": [0.18, 0.20, 0.22, 0.24], "gap_pos": [0.84, 0.85, 0.86, 0.87, 0.88], "glide": [0.08, 0.1, 0.12, 0.15],
        "d_gap": [0.065, 0.07, 0.075, 0.08], "gain": [6.0, 7.0, 8.0], "d_cons": [0.05, 0.06, 0.07]}
keys=list(grid); base["trans_voi"]=0.0
for combo in itertools.product(*[grid[k] for k in keys]):
    s=dict(base); s.update(dict(zip(keys,combo))); n+=1
    ok,fails,brief,y=R.judge("tza",s)
    if ok: passes.append({k:s[k] for k in keys})
    for f in fails: hist[f.split("(")[0][:40]]+=1
print("tza fine: %d/%d pass"%(len(passes),n))
import collections as C
for k in keys: print("  ", k, dict(C.Counter(p[k] for p in passes)))
for f,c in hist.most_common(6): print("   fail %3d %s"%(c,f))
json.dump(passes, open("tza-passes.json","w"))
