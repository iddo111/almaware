# -*- coding: utf-8 -*-
"""VAADA-MIKO-BIO exp5: the PHONOLOGICAL BRIDGE as a second pathway.

Biological framing (Treves & Rolls 1992, two distinct input systems to CA3):
  pathway 1 = literal lexical match  (many weak modifiable synapses, perforant path)
  pathway 2 = consonant-skeleton match (few strong synapses that force a code, mossy fibre)
Both converge; neither replaces the other.

Hebrew is an abjad. Its matres lectionis (a-h-w-y + the guttural ayin) are WRITTEN VOWELS.
Latin script writes vowels too. Strip vowels from BOTH and the invented proper nouns and
the tech loanwords collide on a shared consonant skeleton -- with zero learned parameters.
"""
import json, sys, re, math
import numpy as np
from collections import Counter
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r"D:\CLAUDE\miko\v1")
from bm25 import BM25

BASE = r"D:\CLAUDE\miko\v1"
docs = [json.loads(l) for l in open(BASE + r"\corpus.jsonl", encoding='utf-8')]
exam = json.load(open(BASE + r"\exam.json", encoding='utf-8'))
ids = [d['id'] for d in docs]; texts = [d['text'] for d in docs]
N = len(docs); pos = {d: i for i, d in enumerate(ids)}
TAV, YETIV = chr(0x05EA), chr(0x05AA)

# --- the transducer: consonant skeleton, shared by both scripts -----------------
# matres lectionis / gutturals -> written vowels, dropped
HEB_VOWEL = set('אהויע')
HEB_CONS = {'ב':'b','ג':'g','ד':'d','ז':'z','ח':'h','ט':'t','כ':'k','ך':'k',
            'ל':'l','מ':'m','ם':'m','נ':'n','ן':'n','ס':'s','פ':'p','ף':'p',
            'צ':'ts','ץ':'ts','ק':'k','ר':'r','ש':'s','ת':'t'}
LAT_VOWEL = set('aeiou')

def skeleton(word: str) -> str:
    w = word.replace(YETIV, TAV)
    out = []
    prev_heb_vowel_run = 0
    for i, ch in enumerate(w):
        if ch in HEB_VOWEL:
            # vav/yod are CONSONANTS word-initially or when doubled; else written vowels
            if ch == 'ו':
                doubled = (i + 1 < len(w) and w[i+1] == 'ו') or (i > 0 and w[i-1] == 'ו')
                if i == 0 or doubled:
                    out.append('w'); continue
            if ch == 'י' and i == 0:
                out.append('y'); continue
            continue                                   # written vowel -> drop
        if ch in HEB_CONS:
            out.append(HEB_CONS[ch]); continue
        c = ch.lower()
        if c.isascii() and c.isalpha():
            if c in LAT_VOWEL:
                continue                               # drop latin vowels too
            out.append({'v':'w','f':'p','q':'k','c':'k','j':'y','x':'ks'}.get(c, c))
            continue
        if c.isdigit():
            out.append(c)
    s = ''.join(out)
    s = s.replace('tzh', 'ts').replace('tz', 'ts').replace('sh', 's').replace('ch', 'h')
    s = re.sub(r'(.)\1+', r'\1', s)                    # collapse geminates
    return s

# sanity check the bridge on the invented proper nouns
print("TRANSDUCER sanity -- do the invented names collide across scripts?")
for he, en in [('ערן','eran'),('צלם','tzelem'),('קו','kav'),('וינסטון','winston'),
               ('מיקו','miko'),('קשב','keshev'),('עלמה','alma'),('דארוויש','darwish'),
               ('אורגן','organ'),('רינדור','render'),('קריאליטי','creality'),
               ('מודל','model'),('פרויקט','project'),('שופט','judge')]:
    a, b = skeleton(he), skeleton(en)
    print(f"   {he:9s} -> {a:8s} | {en:10s} -> {b:8s}  {'MATCH' if a == b and a else 'no'}")
print()

WORD_RE = re.compile(r'\w+', re.UNICODE)
def words(s):  return [w.lower() for w in WORD_RE.findall(s.replace(YETIV, TAV))]

# --- channel 2 index: skeleton -> docs, with idf ------------------------------
def build_skel_index(min_len=3):
    dfreq = Counter(); dsk = []
    for t in texts:
        sk = Counter()
        for w in words(t):
            s = skeleton(w)
            if len(s) >= min_len: sk[s] += 1
        dsk.append(sk)
        for s in sk: dfreq[s] += 1
    idf = {s: math.log(1.0 + (N - c + 0.5) / (c + 0.5)) for s, c in dfreq.items()}
    return dsk, idf, dfreq

dsk, sk_idf, sk_df = build_skel_index()
dsk_len = np.array([sum(c.values()) for c in dsk], dtype=np.float32)
avg_sk = dsk_len.mean()

def skel_bm25(query, k1=1.5, b=0.75):
    sc = np.zeros(N, dtype=np.float32)
    qs = [skeleton(w) for w in words(query)]
    for s in qs:
        if len(s) < 3 or s not in sk_idf: continue
        idf = sk_idf[s]
        for i in range(N):
            f = dsk[i].get(s, 0)
            if f:
                sc[i] += idf * (f * (k1 + 1)) / (f + k1 * (1 - b + b * dsk_len[i] / avg_sk))
    return sc

bm = BM25(ids, texts)
def word_bm25(query):
    sc = np.zeros(N, dtype=np.float32)
    for did, s in bm.search(query.replace(YETIV, TAV), top_k=N): sc[pos[did]] = s
    return sc

def zn(v):
    return (v - v.mean()) / (v.std() + 1e-9)

def report(scorer, label):
    r1 = r5 = 0; mrr = 0.0; he1 = en1 = 0; ranks = {'he': [], 'en': []}
    for e in exam:
        s = scorer(e['query'])
        order = np.argsort(-s)
        rank = int(np.where(order == pos[e['target_id']])[0][0]) + 1
        r1 += rank == 1; r5 += rank <= 5; mrr += 1.0 / rank
        ranks[e['lang']].append(rank)
        if rank == 1:
            if e['lang'] == 'he': he1 += 1
            else: en1 += 1
    import statistics as st
    print(f"{label:46s} r@1 {r1:2d}/30={r1/30:.3f}  r@5 {r5:2d}/30  MRR {mrr/30:.3f}  "
          f"[he {he1}/15 med{st.median(ranks['he']):.0f}  en {en1}/15 med{st.median(ranks['en']):.0f}]")
    return r1

print("=" * 116)
report(word_bm25,  "A  word BM25 (control)")
report(skel_bm25,  "G  skeleton BM25 alone (bridge only)")
for w in (0.3, 0.5, 0.7, 1.0, 1.5):
    report(lambda q, w=w: zn(word_bm25(q)) + w * zn(skel_bm25(q)),
           f"H  word BM25 + {w:.1f} x skeleton bridge")
print("=" * 116)
