# -*- coding: utf-8 -*-
"""How much discrimination does NDCG@10 lose as the candidate set shrinks?

The judge budget forces a trade: more questions x fewer pages each. NDCG@10 over 12
candidates is nearly the whole list, so the random floor climbs and the metric stops
separating anything. This measures the floor at each depth on round 1's real labels
before the cut is chosen, instead of discovering it afterwards.
"""
import json, math, random, statistics
from collections import defaultdict

rows = [json.loads(l) for l in open("/home/eran2/miko-bench/data/pairs.jsonl",
                                    encoding="utf-8")]
by = defaultdict(list)
for r in rows:
    by[r["question_id"]].append((r["stratum"], r["score"]))

prop = {12: {"top": 5, "near": 5, "random": 1, "sibling": 1},
        16: {"top": 7, "near": 6, "random": 2, "sibling": 1},
        20: {"top": 8, "near": 8, "random": 2, "sibling": 2},
        24: {"top": 10, "near": 9, "random": 3, "sibling": 2},
        40: {"top": 10, "near": 16, "random": 6, "sibling": 8}}


def ndcg(v, k=10):
    d = sum(x / math.log2(i + 2) for i, x in enumerate(v[:k]))
    idl = sorted(v, reverse=True)[:k]
    i = sum(x / math.log2(j + 2) for j, x in enumerate(idl))
    return d / i if i > 1e-9 else None


rng = random.Random(7)
print("%6s %16s %16s" % ("depth", "random NDCG@10", "headroom to 1.0"))
for depth in sorted(prop):
    p = prop[depth]
    vals = []
    for qi, items in by.items():
        st = defaultdict(list)
        for s, sc in items:
            st[s].append(sc)
        cand = []
        for s, n in p.items():
            cand += st[s][:n]
        if max(cand, default=0) <= 1e-9:
            continue
        vv = []
        for _ in range(200):
            sh = cand[:]
            rng.shuffle(sh)
            x = ndcg(sh)
            if x is not None:
                vv.append(x)
        if vv:
            vals.append(statistics.mean(vv))
    m = statistics.mean(vals)
    print("%6d %16.4f %16.4f" % (depth, m, 1.0 - m))
