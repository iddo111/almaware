# -*- coding: utf-8 -*-
"""The dataset's own numbers: score histogram, per-stratum means, label stability."""
import json, sys
from collections import Counter, defaultdict

P = "/home/eran2/miko-bench/data/pairs.jsonl"
rows = [json.loads(l) for l in open(P, encoding="utf-8")]
print(f"pairs           {len(rows)}")
print(f"questions       {len({r['question_id'] for r in rows})}")
print(f"unique pages    {len({r['doc_id'] for r in rows})}")
print(f"unique urls     {len({r['url'] for r in rows})}")
print(f"scoring model   {rows[0]['scoring_model']}")
print(f"scoring method  {rows[0]['scoring_method']}")

print("\nSCORE HISTOGRAM (10 bins of 0.1)")
bins = [0] * 10
for r in rows:
    bins[min(9, int(r["score"] * 10))] += 1
for i, c in enumerate(bins):
    lo, hi = i / 10, (i + 1) / 10
    print(f"  {lo:.1f}-{hi:.1f}  {c:5d}  {c/len(rows)*100:5.1f}%  {'#'*int(c/len(rows)*180)}")

print("\nARGMAX DIGIT (the judge's own discrete verdict)")
c = Counter(r["score_argmax_digit"] for r in rows)
for d in range(6):
    print(f"  digit {d}: {c[d]:5d}  {c[d]/len(rows)*100:5.1f}%")

print("\nBY STRATUM (this is the check that the strata did their job)")
by = defaultdict(list)
for r in rows:
    by[r["stratum"]].append(r["score"])
for k in ("top", "near", "sibling", "random"):
    v = by[k]
    v_s = sorted(v)
    print(f"  {k:<8} n={len(v):5d}  mean={sum(v)/len(v):.3f}  median={v_s[len(v)//2]:.3f}  "
          f">=0.5: {sum(1 for x in v if x >= 0.5)/len(v)*100:5.1f}%  "
          f"<=0.1: {sum(1 for x in v if x <= 0.1)/len(v)*100:5.1f}%")

print("\nBY CLUSTER (Iddo's eight research domains)")
bc = defaultdict(list)
for r in rows:
    bc[r["cluster"]].append(r["score"])
names = {"A": "giant models/weak machines", "B": "collective+solar", "C": "ear/mouth/world",
         "D": "the ERAN chip", "E": "biofeedback", "F": "cycles",
         "G": "makers lab", "H": "physical substrates"}
for k in sorted(bc):
    v = bc[k]
    print(f"  {k} {names[k]:<28} n={len(v):5d}  mean={sum(v)/len(v):.3f}  "
          f">=0.5: {sum(1 for x in v if x >= 0.5)/len(v)*100:5.1f}%")

allv = [r["score"] for r in rows]
print(f"\noverall mean {sum(allv)/len(allv):.4f}   "
      f">=0.5: {sum(1 for x in allv if x>=0.5)/len(allv)*100:.1f}%   "
      f"<=0.1: {sum(1 for x in allv if x<=0.1)/len(allv)*100:.1f}%")
