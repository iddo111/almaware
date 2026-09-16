# -*- coding: utf-8 -*-
"""Judge in an order that is COMPLETE AT EVERY PREFIX.

eran2's GPU is shared with two other agents' jobs (96% utilisation), so the judge runs at
3.6 pairs/s instead of round 1's 5.3 and the full 58,608 pairs would cost 4.5 hours. Rather
than guess a smaller budget now, the file is re-ordered so that judging can be cut at any
point and still leave EVERY question with the same number of pages, drawn in the same
stratum proportions.

Order = round robin over questions, and within a question an interleave of the four strata
in proportion to their counts. So after k*2442 rows, every question has exactly k pages,
balanced across top / near / sibling / random.
"""
import json, sys
from collections import defaultdict, Counter

HOME = "/home/eran2/miko-bench"
INP = HOME + "/data/pairs2_unscored.jsonl"
OUT = HOME + "/data/pairs2_ordered.jsonl"

PRIO = {"top": 0, "near": 1, "random": 2, "sibling": 3}

rows = [json.loads(l) for l in open(INP, encoding="utf-8")]
by_q = defaultdict(lambda: defaultdict(list))
for r in rows:
    by_q[r["question_id"]][r["stratum"]].append(r)

ordered_per_q = {}
depth = 0
for qi, strata in by_q.items():
    items = []
    for st, lst in strata.items():
        n = len(lst)
        for i, r in enumerate(lst):
            items.append(((i + 0.5) / n, PRIO[st], st, r))
    items.sort(key=lambda t: (t[0], t[1]))
    ordered_per_q[qi] = [t[3] for t in items]
    depth = max(depth, len(items))

qids = sorted(ordered_per_q)
out = []
for k in range(depth):
    for qi in qids:
        lst = ordered_per_q[qi]
        if k < len(lst):
            out.append(lst[k])

with open(OUT, "w", encoding="utf-8") as f:
    for r in out:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")

print(f"{len(out)} pairs, {len(qids)} questions, depth {depth} -> {OUT}")
for k in (12, 16, 20, depth):
    pref = out[:k * len(qids)]
    c = Counter(r["stratum"] for r in pref)
    per = Counter(r["question_id"] for r in pref)
    print(f"  prefix depth {k:2d}: {len(pref):6d} pairs, per-question "
          f"min={min(per.values())} max={max(per.values())}, strata {dict(c)}")
