# -*- coding: utf-8 -*-
"""Diagnose WHY hebrew queries fail: token overlap between query and gold doc."""
import json, sys, re
from collections import Counter
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r"D:\CLAUDE\miko\v1")
from bm25 import BM25, tokenize

BASE = r"D:\CLAUDE\miko\v1"
docs = [json.loads(l) for l in open(BASE + r"\corpus.jsonl", encoding='utf-8')]
exam = json.load(open(BASE + r"\exam.json", encoding='utf-8'))
byid = {d['id']: d for d in docs}
ids = [d['id'] for d in docs]
bm = BM25(ids, [d['text'] for d in docs])
TAV, YETIV = chr(0x05EA), chr(0x05AA)

print(f"{'lang':4s} {'rank':>5s} {'q_tok':>5s} {'hit':>4s} {'miss':>4s}  query / missing tokens")
print("-" * 100)
he_ranks, en_ranks = [], []
for e in exam:
    q = e['query'].replace(YETIV, TAV)
    gold = e['target_id']
    ranked = bm.search_all_ranked(q)
    rank = ranked.index(gold) + 1
    (he_ranks if e['lang'] == 'he' else en_ranks).append(rank)
    qt = tokenize(q)
    gt = set(tokenize(byid[gold]['text']))
    hit = [t for t in qt if t in gt]
    miss = [t for t in qt if t not in gt]
    print(f"{e['lang']:4s} {rank:5d} {len(qt):5d} {len(hit):4d} {len(miss):4d}  {q}")
    if miss:
        print(f"{'':22s}MISSING FROM GOLD DOC: {' '.join(miss)}")

import statistics as st
print()
print(f"hebrew  n={len(he_ranks):2d}  r@1={sum(1 for r in he_ranks if r==1)}  median rank={st.median(he_ranks):.0f}  ranks={sorted(he_ranks)}")
print(f"english n={len(en_ranks):2d}  r@1={sum(1 for r in en_ranks if r==1)}  median rank={st.median(en_ranks):.0f}  ranks={sorted(en_ranks)}")
