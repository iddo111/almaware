# -*- coding: utf-8 -*-
"""Is the real failure CROSS-LINGUAL? Measure script mix of query vs gold doc."""
import json, sys, re
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r"D:\CLAUDE\miko\v1")
from bm25 import BM25, tokenize

BASE = r"D:\CLAUDE\miko\v1"
docs = [json.loads(l) for l in open(BASE + r"\corpus.jsonl", encoding='utf-8')]
exam = json.load(open(BASE + r"\exam.json", encoding='utf-8'))
byid = {d['id']: d for d in docs}
TAV, YETIV = chr(0x05EA), chr(0x05AA)

def heb_frac(s):
    heb = sum(1 for c in s if 0x05D0 <= ord(c) <= 0x05EA)
    lat = sum(1 for c in s if c.isascii() and c.isalpha())
    return heb / max(1, heb + lat)

ids = [d['id'] for d in docs]
bm = BM25(ids, [d['text'] for d in docs])

print(f"{'lang':4s} {'rank':>5s} {'doc_heb%':>8s}  gold_id")
print("-" * 78)
rows = []
for e in exam:
    q = e['query'].replace(YETIV, TAV)
    gold = e['target_id']
    rank = bm.search_all_ranked(q).index(gold) + 1
    hf = heb_frac(byid[gold]['text'])
    rows.append((e['lang'], rank, hf, gold))
    print(f"{e['lang']:4s} {rank:5d} {hf*100:7.1f}%  {gold}")

print()
# cross-lingual bucket analysis
for ql in ('he', 'en'):
    for lo, hi, name in ((0.0, 0.25, 'doc mostly ENGLISH'), (0.25, 1.01, 'doc has real HEBREW')):
        sel = [r for r in rows if r[0] == ql and lo <= r[2] < hi]
        if not sel:
            continue
        r1 = sum(1 for r in sel if r[1] == 1)
        import statistics as st
        print(f"query={ql}  {name:22s}  n={len(sel):2d}  r@1={r1}/{len(sel)}  median rank={st.median([r[1] for r in sel]):.0f}")

print()
print("corpus-wide: hebrew fraction of doc bodies")
hfs = sorted(heb_frac(d['text']) for d in docs)
n = len(hfs)
print(f"  p10 {hfs[n//10]*100:.1f}%  p25 {hfs[n//4]*100:.1f}%  median {hfs[n//2]*100:.1f}%  p75 {hfs[3*n//4]*100:.1f}%  p90 {hfs[9*n//10]*100:.1f}%")
print(f"  docs <10% hebrew (essentially english): {sum(1 for h in hfs if h < 0.10)} / {n}")

# The smoking gun: are the invented proper nouns present in BOTH scripts?
print()
print("Proper-noun alias check -- how many docs contain each form:")
pairs = [('ערן','eran'),('צלם','tzelem'),('קו','kav'),('וינסטון','winston'),
         ('מיקו','miko'),('קשב','keshev'),('עלמה','alma'),('דארוויש','darwish')]
for he, en in pairs:
    dh = sum(1 for d in docs if he in d['text'])
    de = sum(1 for d in docs if en in d['text'].lower())
    both = sum(1 for d in docs if he in d['text'] and en in d['text'].lower())
    print(f"  {he:8s} in {dh:4d} docs | {en:8s} in {de:4d} docs | BOTH in {both:4d} docs")
