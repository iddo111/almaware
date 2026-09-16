#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase-1 selection and the final tables, by rule, not by eye.

    python3 -m alma_guard.v02_select pick   # out/p1 -> print whole grid, write jobs_p2.txt, jobs_p3.txt
    python3 -m alma_guard.v02_select table  # out/p2 + out/p3 -> out/v02_tables.json + printed tables

PICK RULE (declared in v02_arms.py before any number existed):
  * ALMA families: best cell on fold-seed 0 by CV accuracy, ties by F1.
  * Controls are matched to the ALMA objective they are compared with:
      w1024 linear controls  <- pos_weight = r_miss of the chosen alma-1L-3f cell
      w9232 linear + MLP     <- pos_weight = r_miss of the chosen alma-h8-pert cell
    and within that pos_weight the best lr by the same accuracy rule.
"""
from __future__ import annotations

import glob
import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = Path("out")


def load(pattern):
    res = []
    for f in sorted(glob.glob(pattern)):
        try:
            res.append(json.loads(Path(f).read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            pass
    return res


def key(d):
    return (d["metrics"]["acc"], d["metrics"]["f1"])


def pick() -> int:
    fams = json.loads((HERE / "families.json").read_text(encoding="utf-8"))
    by_name = {d["arm"]["name"]: d for d in load(str(OUT / "p1" / "*_fs0.json"))}
    print(f"{'arm':38s} {'acc':>6s} {'P':>6s} {'R':>6s} {'F1':>6s} {'bal':>6s} shortHE-FA  params")
    for fam, names in fams.items():
        for n in names:
            d = by_name.get(n)
            if not d:
                print(f"{n:38s}  MISSING")
                continue
            m, sh = d["metrics"], d["short_hebrew"]
            print(f"{n:38s} {m['acc']:.4f} {m['precision']:.4f} {m['recall']:.4f} {m['f1']:.4f} "
                  f"{m['balanced']:.4f} {sh['false_alarms']:3d}/{sh['benign_n']:<3d}  {d['params']}")
    chosen = {}

    def best(names):
        got = [by_name[n] for n in names if n in by_name]
        return max(got, key=key)["arm"] if got else None

    missing = [n for names in fams.values() for n in names if n not in by_name]
    if missing:
        print(f"\nPHASE 1 INCOMPLETE: {len(missing)} of {sum(len(v) for v in fams.values())} "
              f"arms have no result yet ({', '.join(missing[:4])}...). No pick is made "
              f"from a partial grid.")
        return 2
    for fam in ("alma-1L-3f", "alma-h8-pert", "alma-h8-3f"):
        chosen[fam] = best(fams[fam])
    pw_1l = chosen["alma-1L-3f"]["r_miss"] / chosen["alma-1L-3f"]["r_fa"]
    pw_h = chosen["alma-h8-pert"]["r_miss"] / chosen["alma-h8-pert"]["r_fa"]
    # the three-factor ablation is run with the perturbation cell's objective
    for fam, pw in (("perceptron-w1024", pw_1l), ("logreg-w1024", pw_1l),
                    ("perceptron-w9232", pw_h), ("logreg-w9232", pw_h),
                    ("mlp-w1024-h8", pw_h)):
        chosen[fam] = best([n for n in fams[fam] if n.endswith(f"-pw{int(pw)}")])
    print("\nCHOSEN:")
    for fam, a in chosen.items():
        print(f"  {fam:18s} {a['name'] if a else 'NONE'}")
    p2, p3 = [], []
    for fam, a in chosen.items():
        arm = f"alma_guard/arms/{a['name']}.json"
        for fs in (1, 2, 3):
            p2.append(f"python3 -m alma_guard.v02_experiment cv --arm {arm} --fold-seed {fs} "
                      f"--out out/p2/{a['name']}_fs{fs}.json > logs/p2_{a['name']}_fs{fs}.log 2>&1")
        for s in range(5):
            save = f" --save out/p3/model_{a['name']}_s{s}.json" if a["kind"] == "alma" else ""
            p3.append(f"python3 -m alma_guard.v02_experiment final --arm {arm} --seed {s}{save} "
                      f"--out out/p3/{a['name']}_s{s}.json > logs/p3_{a['name']}_s{s}.log 2>&1")
    alma_first = sorted(p2 + p3, key=lambda c: ("alma-" not in c, c))
    (HERE / "jobs_p23.txt").write_text("\n".join(alma_first) + "\n", encoding="utf-8")
    (OUT / "chosen.json").write_text(json.dumps(chosen, indent=1), encoding="utf-8")
    print(f"\n{len(p2)} phase-2 + {len(p3)} phase-3 jobs -> alma_guard/jobs_p23.txt")
    return 0


def agg(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    return {"mean": statistics.mean(vals), "min": min(vals), "max": max(vals), "n": len(vals)}


def table() -> int:
    chosen = json.loads((OUT / "chosen.json").read_text(encoding="utf-8"))
    res = {"cv": {}, "heldout": {}}
    for fam, a in chosen.items():
        cv = load(str(OUT / "p2" / f"{a['name']}_fs*.json"))
        if cv:
            res["cv"][fam] = {
                "arm": a["name"], "params": cv[0]["params"], "seeds": len(cv),
                **{k: agg([d["metrics"][k] for d in cv])
                   for k in ("acc", "precision", "recall", "f1", "balanced")},
                "majority": cv[0]["majority"],
                "short_he_fa": [d["short_hebrew"]["false_alarms"] for d in cv],
                "short_he_benign_n": cv[0]["short_hebrew"]["benign_n"],
                "short_he_miss": [d["short_hebrew"]["misses"] for d in cv],
                "short_he_attack_n": cv[0]["short_hebrew"]["attack_n"],
                "per_source": {s: agg([d["per_source"][s]["acc"] for d in cv])
                               for s in cv[0]["per_source"]},
            }
        fin = load(str(OUT / "p3" / f"{a['name']}_s*.json"))
        if fin:
            srcs = sorted({s for d in fin for s in d["heldout"]})
            res["heldout"][fam] = {"arm": a["name"], "seeds": len(fin),
                                   "train_fit_acc": agg([d["train_fit"]["acc"] for d in fin])}
            for s in srcs:
                ds = [d["heldout"][s] for d in fin if s in d["heldout"]]
                res["heldout"][fam][s] = {
                    "n": ds[0]["metrics"]["n"], "majority": ds[0]["majority"],
                    **{k: agg([x["metrics"][k] for x in ds])
                       for k in ("acc", "precision", "recall", "f1")},
                    "caught": [x["metrics"]["tp"] for x in ds],
                    "attacks": ds[0]["metrics"]["tp"] + ds[0]["metrics"]["fn"],
                    "false_alarms": [x["metrics"]["fp"] for x in ds],
                    "short_he_fa": [x["short_hebrew"]["false_alarms"] for x in ds],
                    "short_he_benign_n": ds[0]["short_hebrew"]["benign_n"],
                    "short_he_miss": [x["short_hebrew"]["misses"] for x in ds],
                    "short_he_attack_n": ds[0]["short_hebrew"]["attack_n"],
                }
    (OUT / "v02_tables.json").write_text(json.dumps(res, ensure_ascii=False, indent=1),
                                         encoding="utf-8")

    def f(x):
        return "   -  " if x is None else f"{x['mean']:.3f}"

    print("CV (fold-seeds 1,2,3; mean)")
    print(f"  {'family':18s} {'params':>6s} {'acc':>6s} {'P':>6s} {'R':>6s} {'F1':>6s} {'bal':>6s}  shortHE FA / miss")
    for fam, r in res["cv"].items():
        print(f"  {fam:18s} {r['params']:6d} {f(r['acc'])} {f(r['precision'])} {f(r['recall'])} "
              f"{f(r['f1'])} {f(r['balanced'])}  {r['short_he_fa']}/{r['short_he_benign_n']}  "
              f"{r['short_he_miss']}/{r['short_he_attack_n']}")
    for s in ("fresh", "fresh-v02", "guard-p2", "shield-tests"):
        rows = [(fam, r[s]) for fam, r in res["heldout"].items() if s in r]
        if not rows:
            continue
        print(f"\nHELD-OUT {s} (n={rows[0][1]['n']}, majority {rows[0][1]['majority']:.3f}; 5 init seeds)")
        for fam, r in rows:
            print(f"  {fam:18s} acc {f(r['acc'])} R {f(r['recall'])} F1 {f(r['f1'])}  caught "
                  f"{r['caught']}/{r['attacks']}  FA {r['false_alarms']}  shortHE FA "
                  f"{r['short_he_fa']}/{r['short_he_benign_n']}")
    return 0


if __name__ == "__main__":
    sys.exit({"pick": pick, "table": table}[sys.argv[1]]())
