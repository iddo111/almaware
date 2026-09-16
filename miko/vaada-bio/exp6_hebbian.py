# -*- coding: utf-8 -*-
"""VAADA-MIKO-BIO exp6: HEBBIAN cross-lingual association from our OWN corpus.

Iddo writes bilingually (the BILINGUAL LAW). So Hebrew and English words for the same
thing CO-OCCUR in the same documents far above chance. "Cells that fire together wire
together" -- a doc-level Hebbian outer product over the corpus gives a Hebrew->English
lexicon with no pretrained model, no gradient descent, and no corpus we do not own.

Query-time retrieval is then PATTERN COMPLETION: the Hebrew cue activates its bound
English partners, and the completed pattern drives the lexical index.
"""
import json, sys, re, math
import numpy as np
from collections import Counter, defaultdict
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r"D:\CLAUDE\miko\v1")
from bm25 import BM25

BASE = r"D:\CLAUDE\miko\v1"
docs = [json.loads(l) for l in open(BASE + r"\corpus.jsonl", encoding='utf-8')]
exam = json.load(open(BASE + r"\exam.json", encoding='utf-8'))
ids = [d['id'] for d in docs]; texts = [d['text'] for d in docs]
N = len(docs); pos = {d: i for i, d in enumerate(ids)}
TAV, YETIV = chr(0x05EA), chr(0x05AA)
WORD_RE = re.compile(r'\w+', re.UNICODE)

def words(s): return [w.lower() for w in WORD_RE.findall(s.replace(YETIV, TAV))]
def is_heb(w): return any(0x05D0 <= ord(c) <= 0x05EA for c in w)

# ---- how much bilingual signal do we actually own? --------------------------
doc_words = [set(words(t)) for t in texts]
heb_vocab = Counter(); en_vocab = Counter()
for dw in doc_words:
    for w in dw:
        (heb_vocab if is_heb(w) else en_vocab)[w] += 1
print(f"vocab: {len(heb_vocab)} hebrew types, {len(en_vocab)} latin types")
bilingual_docs = sum(1 for dw in doc_words if any(is_heb(w) for w in dw) and any(not is_heb(w) for w in dw))
print(f"documents containing BOTH scripts: {bilingual_docs}/{N}")

MIN_DF = 3
H = [w for w, c in heb_vocab.items() if c >= MIN_DF]
E = [w for w, c in en_vocab.items() if c >= MIN_DF and len(w) > 2]
hi = {w: i for i, w in enumerate(H)}; ei = {w: i for i, w in enumerate(E)}
print(f"after df>={MIN_DF}: {len(H)} hebrew x {len(E)} english association matrix")

# ---- the Hebbian outer product ---------------------------------------------
Mh = np.zeros((N, len(H)), dtype=np.float32)
Me = np.zeros((N, len(E)), dtype=np.float32)
for d, dw in enumerate(doc_words):
    for w in dw:
        if w in hi: Mh[d, hi[w]] = 1.0
        elif w in ei: Me[d, ei[w]] = 1.0
C = Mh.T @ Me                      # co-occurrence counts, |H| x |E|
nh = Mh.sum(0)[:, None]; ne = Me.sum(0)[None, :]
PMI = np.log((C * N + 1e-9) / (nh * ne + 1e-9) + 1e-12)
PMI = np.maximum(PMI, 0.0) * (C >= 2)          # positive PMI, seen together >=2x

print("\nHebbian bindings learned from OUR corpus (top-4 english partners):")
for probe in ['שופט', 'אוזן', 'חי', 'ערן', 'מדפסת', 'מסלול', 'מכונות', 'הפעימה', 'עומק']:
    if probe not in hi:
        print(f"   {probe:9s} -> NOT IN MATRIX (df<{MIN_DF})"); continue
    row = PMI[hi[probe]]
    top = np.argsort(-row)[:4]
    print(f"   {probe:9s} -> " + ", ".join(f"{E[j]}({row[j]:.1f})" for j in top if row[j] > 0))

# ---- retrieval: Hebrew cue -> pattern completion -> lexical index ------------
bm = BM25(ids, texts)
def word_bm25_scores(q):
    s = np.zeros(N, dtype=np.float32)
    for did, v in bm.search(q.replace(YETIV, TAV), top_k=N): s[pos[did]] = v
    return s

def complete(q, topn=3, min_pmi=1.0):
    """Pattern completion: expand hebrew cue words into bound english partners."""
    extra = []
    for w in words(q):
        if w in hi:
            row = PMI[hi[w]]
            for j in np.argsort(-row)[:topn]:
                if row[j] >= min_pmi: extra.append(E[j])
    return extra

def zn(v): return (v - v.mean()) / (v.std() + 1e-9)

def report(scorer, label):
    r1 = r5 = 0; mrr = 0.0; he1 = en1 = 0; rk = {'he': [], 'en': []}
    for e in exam:
        s = scorer(e)
        rank = int(np.where(np.argsort(-s) == pos[e['target_id']])[0][0]) + 1
        r1 += rank == 1; r5 += rank <= 5; mrr += 1.0 / rank; rk[e['lang']].append(rank)
        if rank == 1: he1 += e['lang'] == 'he'; en1 += e['lang'] == 'en'
    import statistics as st
    print(f"{label:48s} r@1 {r1:2d}/30={r1/30:.3f}  r@5 {r5:2d}/30  MRR {mrr/30:.3f}  "
          f"[he {he1}/15 med{st.median(rk['he']):.0f}  en {en1}/15 med{st.median(rk['en']):.0f}]")
    return r1

print("\n" + "=" * 118)
report(lambda e: word_bm25_scores(e['query']), "A  word BM25 (control)")
for topn in (1, 2, 3, 5):
    for w in (0.5, 1.0):
        report(lambda e, t=topn, w=w: zn(word_bm25_scores(e['query'])) +
                                      w * zn(word_bm25_scores(' '.join(complete(e['query'], t)))),
               f"I  BM25 + {w:.1f} x Hebbian completion (top{topn})")
print("=" * 118)
