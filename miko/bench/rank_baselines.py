# -*- coding: utf-8 -*-
"""Ranking reference points, so NDCG@10 = 0.28 can be read as good, chance, or bad.

  random    a uniformly random ordering of the same 40 pages (1000 draws)
  bm25      the ordering that RETRIEVED these pages in the first place - a real IR
            baseline, and the one PLAN.md 0.5 says MIKO must eventually beat
  oracle    1.0 by construction
"""
import json, math, random, statistics, sys

PAIRS = "/home/eran2/miko-bench/data/pairs.jsonl"
RANKS = "/home/eran2/miko-bench/data/ranks.json"

rows = [json.loads(l) for l in open(PAIRS, encoding="utf-8")]
ranks = {int(k): v for k, v in json.load(open(RANKS)).items()}
pos = {qi: {d: i for i, d in enumerate(v)} for qi, v in ranks.items()}

by_q = {}
for r in rows:
    d_idx = int(r["pair_id"].split("_d")[1])
    by_q.setdefault(r["question_id"], []).append((d_idx, r["score"]))


def ndcg(order_scores, k=10):
    g = order_scores[:k]
    dcg = sum(x / math.log2(i + 2) for i, x in enumerate(g))
    ideal = sorted(order_scores, reverse=True)[:k]
    idcg = sum(x / math.log2(i + 2) for i, x in enumerate(ideal))
    return dcg / idcg if idcg > 1e-9 else None


qids_all = sorted(by_q)
for ss in (11, 23):
    qs = list(qids_all)
    random.Random(ss).shuffle(qs)
    n = len(qs)
    te = set(qs[int(0.6 * n) + int(0.2 * n):])

    rnd_all, bm_all = [], []
    rng = random.Random(7)
    for qi in te:
        items = by_q[qi]
        labels = [s for _, s in items]
        if max(labels) <= 1e-9:
            continue
        # random ordering, averaged over 200 draws
        vals = []
        for _ in range(200):
            sh = labels[:]
            rng.shuffle(sh)
            v = ndcg(sh)
            if v is not None:
                vals.append(v)
        rnd_all.append(statistics.mean(vals))
        # bm25 ordering: rank position in that question's own BM25 list, unranked last
        WORST = 10 ** 9
        ordered = sorted(items, key=lambda t: pos[qi].get(t[0], WORST))
        v = ndcg([s for _, s in ordered])
        if v is not None:
            bm_all.append(v)

    print(f"split_seed {ss}  ({len(rnd_all)} test questions with any non-zero label)")
    print(f"   RANDOM ordering  NDCG@10 = {statistics.mean(rnd_all):.4f}")
    print(f"   BM25   ordering  NDCG@10 = {statistics.mean(bm_all):.4f}")
    print(f"   ORACLE                   = 1.0000\n")
