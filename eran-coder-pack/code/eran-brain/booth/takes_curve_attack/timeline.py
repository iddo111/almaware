import json, datetime, collections
R = json.load(open("feats.json"))
# global sitting segmentation: gap > 60 s starts a new sitting
sit = 0; prev = None
for r in R:
    if prev is not None and r["mtime"]-prev > 60: sit += 1
    r["sit"] = sit; prev = r["mtime"]
print("GLOBAL SITTINGS (gap>60s):")
by = collections.OrderedDict()
for r in R: by.setdefault(r["sit"], []).append(r)
for s, g in by.items():
    t0 = datetime.datetime.fromtimestamp(g[0]["mtime"])
    t1 = datetime.datetime.fromtimestamp(g[-1]["mtime"])
    uc = collections.Counter(x["unit"] for x in g)
    print(f"  sit{s:<2} {t0:%H:%M:%S}-{t1:%H:%M:%S} ({(t1-t0).total_seconds()/60:5.1f} min) n={len(g):3d}  " +
          " ".join(f"{u}:{c}" for u,c in uc.most_common()))
print()
print("PER-UNIT sittings for the 6 deep units:")
for u in ["ah","ba","abba","ih","ma","ima"]:
    g = [r for r in R if r["unit"]==u]
    print(f" {u:5s} n={len(g)} sittings={sorted(set(x['sit'] for x in g))}")
json.dump(R, open("feats_sit.json","w"))
