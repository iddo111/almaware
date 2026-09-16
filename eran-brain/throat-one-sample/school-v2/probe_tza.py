import itertools, json, collections, ruler as R
base = dict(R.BASE_0902["tza"]); n=0; passes=[]; hist=collections.Counter()
grid = {"trans_voi": [0.0, None], "glide": [0.1, 0.2], "gap_area": [0.22, 0.26, 0.28, 0.30, 0.32], "gap_pos": [0.86, 0.88, 0.90, 0.92],
        "d_gap": [0.07, 0.08, 0.10], "gain": [6.0, 9.0], "d_trans": [0.01], "gap_ten": [0.6, 0.9]}
keys=list(grid)
for combo in itertools.product(*[grid[k] for k in keys]):
    s=dict(base); s.update(dict(zip(keys,combo))); n+=1
    ok,fails,brief,y=R.judge("tza",s)
    if ok: passes.append({k:s[k] for k in keys})
    for f in fails: hist[f.split("(")[0][:50]]+=1
print("tza: %d/%d pass"%(len(passes),n))
for p in passes[:16]: print("   PASS",json.dumps(p))
for f,c in hist.most_common(10): print("   fail %3d %s"%(c,f))
if not passes:
    s=dict(base); s.update({"trans_voi":0.0,"glide":0.1,"gap_area":0.30,"gap_pos":0.90,"d_gap":0.08,"gain":9.0,"gap_ten":0.6}); ok,fails,brief,y=R.judge("tza",s); print(brief[:600])
