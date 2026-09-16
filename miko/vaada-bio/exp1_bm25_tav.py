# -*- coding: utf-8 -*-
"""VAADA-MIKO-BIO experiment 1: reproduce BM25 exam score, then repair the tav corruption."""
import json, sys, re, math
from collections import Counter, defaultdict
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r"D:\CLAUDE\miko\v1")
from bm25 import BM25

BASE = r"D:\CLAUDE\miko\v1"
docs = [json.loads(l) for l in open(BASE + r"\corpus.jsonl", encoding='utf-8')]
exam = json.load(open(BASE + r"\exam.json", encoding='utf-8'))
ids = [d['id'] for d in docs]
texts = [d['text'] for d in docs]
idset = set(ids)

TAV = chr(0x05EA)
YETIV = chr(0x05AA)

def repair(s):
    return s.replace(YETIV, TAV)

bm = BM25(ids, texts)

def run(queries, label):
    r1 = r5 = 0
    mrr = 0.0
    detail = []
    for e, q in zip(exam, queries):
        gold = e['target_id']
        ranked = bm.search_all_ranked(q)
        rank = ranked.index(gold) + 1 if gold in ranked else None
        if rank == 1: r1 += 1
        if rank and rank <= 5: r5 += 1
        if rank: mrr += 1.0 / rank
        detail.append((e['lang'], rank, q, gold))
    n = len(exam)
    print(f"{label:38s} r@1 {r1}/{n} = {r1/n:.3f}   r@5 {r5}/{n} = {r5/n:.3f}   MRR {mrr/n:.3f}")
    return detail, r1

# sanity: every target exists
missing = [e['target_id'] for e in exam if e['target_id'] not in idset]
print("exam targets missing from corpus:", missing)
he = sum(1 for e in exam if e['lang'] == 'he')
print(f"exam: {he} hebrew / {len(exam)-he} english")
corrupt = [i for i, e in enumerate(exam) if YETIV in e['query']]
print(f"exam queries containing the corrupt U+05AA: {len(corrupt)} of {len(exam)}  -> indices {corrupt}")
print()

d_raw, n_raw = run([e['query'] for e in exam], "BM25 as-is (reproduce v1 report)")
d_fix, n_fix = run([repair(e['query']) for e in exam], "BM25 with tav repaired")
print()
print("per-question rank, as-is -> repaired (only where it changed):")
for (lang, ra, q, gold), (_, rb, q2, _) in zip(d_raw, d_fix):
    if ra != rb:
        print(f"  [{lang}] {q!r}")
        print(f"        -> {q2!r}")
        print(f"        rank {ra} -> {rb}   gold={gold}")
print()
print(f"DELTA from fixing one corrupted letter: {n_raw} -> {n_fix} correct at rank 1")
