#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""validate.py -- does the Hebrew judge deserve to judge? Measured on HUMAN clips first."""
import os, sys, json, glob, collections
import numpy as np
import judge as J

def run(name, pairs, outdir):
    """pairs: [(path, true_canon_class)]"""
    res = J.judge_files([p for p, _ in pairs])
    rows = []
    ok = 0
    cm = collections.Counter()
    for (p, truth), r in zip(pairs, res):
        hit = (r["canon_top1"] == truth)
        ok += hit
        cm[(truth, r["canon_top1"])] += 1
        rows.append({"file": os.path.basename(p), "truth": truth, "pred": r["canon_top1"],
                     "conf": round(r["canon_conf"], 4), "hit": hit,
                     "top3": r["top3"], "phones": r["phones"]})
    acc = ok / max(1, len(pairs))
    out = {"set": name, "n": len(pairs), "top1": ok, "acc": acc,
           "confusion": {"%s>%s" % k: v for k, v in sorted(cm.items())}, "rows": rows}
    json.dump(out, open(os.path.join(outdir, "val-%s.json" % name), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("[%s] n=%d  top1(canon)=%d/%d = %.1f%%" % (name, len(pairs), ok, len(pairs), 100 * acc), flush=True)
    # per-class
    per = collections.defaultdict(lambda: [0, 0])
    for r in rows:
        per[r["truth"]][1] += 1
        per[r["truth"]][0] += r["hit"]
    for c in sorted(per):
        h, n = per[c]
        wrong = collections.Counter(r["pred"] for r in rows if r["truth"] == c and not r["hit"])
        print("   %-3s %d/%d %s" % (c, h, n, dict(wrong.most_common(3)) if wrong else ""), flush=True)
    return out

if __name__ == "__main__":
    HERE = os.path.dirname(os.path.abspath(__file__))
    OUT = os.path.join(HERE, "val"); os.makedirs(OUT, exist_ok=True)
    which = sys.argv[1] if len(sys.argv) > 1 else "human"
    if which == "human":
        pairs = []
        for p in sorted(glob.glob(os.path.join(HERE, "heldout-vault", "*.wav"))):
            pre = os.path.basename(p).split("_")[0]
            if pre in J.HELDOUT: pairs.append((p, J.HELDOUT[pre]))
        run("human132", pairs, OUT)

def run_dir(name, d):
    import glob as g
    pairs=[]
    for p in sorted(g.glob(os.path.join(d,"*.wav"))):
        pre=os.path.basename(p).split("_")[0]
        if pre in J.HELDOUT: pairs.append((p, J.HELDOUT[pre]))
    return run(name, pairs, os.path.join(os.path.dirname(os.path.abspath(__file__)),"val"))
