"""probe_fix.py -- tza / ka / qa: grids of candidate designs under ruler.judge. Prints passes + failure histogram."""
import itertools, json, sys, collections
import ruler as R
def run(syl, base, grid, limit=600):
    keys = list(grid); n = 0; passes = []; hist = collections.Counter()
    for combo in itertools.product(*[grid[k] for k in keys]):
        s = dict(base); s.update(dict(zip(keys, combo))); n += 1
        if syl in ("ka", "qa"): s["gap_pos"] = s["c_pos"]
        ok, fails, brief, y = R.judge(syl, s)
        if ok: passes.append({k: s[k] for k in keys})
        for f in fails: hist[f.split("(")[0][:60]] += 1
        if n >= limit: break
    print("%s: %d/%d pass" % (syl, len(passes), n))
    for p in passes[:14]: print("   PASS", json.dumps(p))
    for f, c in hist.most_common(8): print("   fail %3d  %s" % (c, f))
    return passes
if __name__ == "__main__":
    which = sys.argv[1:] or ["ka", "qa", "tza"]
    if "ka" in which:
        run("ka", R.BASE_0902["ka"], {"c_pos": [0.49, 0.50, 0.51], "gap_voi": [0.0], "gap_ten": [0.6], "gap_area": [0.2, 0.25, 0.3, 0.35],
                                     "d_gap": [0.03, 0.035, 0.04], "gain": [6.0, 8.0, 10.0], "d_cons": [0.08, 0.09], "trans_voi": [None, 0.0]}, limit=500)
    if "qa" in which:
        run("qa", R.BASE_0902["qa"], {"c_pos": [0.485, 0.49], "gap_voi": [0.0], "gap_ten": [0.6], "gap_area": [0.2, 0.25, 0.3],
                                     "d_gap": [0.03, 0.035, 0.04], "gain": [6.0, 8.0, 10.0], "d_cons": [0.08, 0.09], "trans_voi": [None, 0.0]}, limit=400)
    if "tza" in which:
        run("tza", R.BASE_0902["tza"], {"trans_voi": [0.0, None], "glide": [0.1, 0.2, 0.35], "gap_area": [0.12, 0.15, 0.2, 0.25], "gap_pos": [0.88, 0.90, 0.92],
                                       "d_gap": [0.07, 0.08], "gain": [6.0, 9.0], "d_trans": [0.01, 0.02]}, limit=600)
