# -*- coding: utf-8 -*-
"""Are the labels still valid at 15x the scale? Rubric A vs an independently worded B.

Round 1 measured Spearman 0.914 and 90.8% binary agreement on 65 questions. That number
does NOT carry over to a pool this size on its own - the generated questions are shorter,
blunter and cover topics the round-1 pool never touched - so it is re-measured here on a
fresh subsample, and reported by ORIGIN (corpus vs iddo) as well as overall. If the iddo
half is much less stable, the sealed test is measuring judge noise and the report has to
say so.
"""
import json, statistics, sys
from collections import defaultdict

HOME = "/home/eran2/miko-bench"
A = {}
for l in open(HOME + "/data/pairs2.jsonl", encoding="utf-8"):
    r = json.loads(l)
    A[r["pair_id"]] = r
B = [json.loads(l) for l in open(HOME + "/data/pairs2_rubricB.jsonl", encoding="utf-8")]
B = [r for r in B if r["pair_id"] in A]
print(f"rubric-B subsample: {len(B)} pairs of {len(A)}")


def rank(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2.0
        for k in range(i, j + 1):
            r[order[k]] = avg
        i = j + 1
    return r


def pearson(a, b):
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    da = sum((x - ma) ** 2 for x in a) ** 0.5
    db = sum((y - mb) ** 2 for y in b) ** 0.5
    return num / (da * db) if da * db > 1e-12 else float("nan")


def report(name, rows):
    if len(rows) < 30:
        print(f"  {name:<28} n={len(rows)} - too few to report")
        return
    a = [A[r["pair_id"]]["score"] for r in rows]
    b = [r["score"] for r in rows]
    sp = pearson(rank(a), rank(b))
    pe = pearson(a, b)
    binagree = sum(1 for x, y in zip(a, b) if (x >= 0.5) == (y >= 0.5)) / len(a)
    mad = sum(abs(x - y) for x, y in zip(a, b)) / len(a)
    print(f"  {name:<28} n={len(rows):6d}  spearman={sp:.4f}  pearson={pe:.4f}  "
          f"binary_agree={binagree*100:5.1f}%  mean|A-B|={mad:.4f}  "
          f"meanA={statistics.mean(a):.3f} meanB={statistics.mean(b):.3f}")


print("\nLABEL VALIDITY - rubric A (the label) vs rubric B (independent wording)")
report("ALL", B)
by = defaultdict(list)
for r in B:
    by["origin:" + A[r["pair_id"]]["origin"]].append(r)
    by["stratum:" + A[r["pair_id"]]["stratum"]].append(r)
for k in sorted(by):
    report(k, by[k])
