# -*- coding: utf-8 -*-
"""BM25 over the same 166,425-page real-web corpus, for the ROUND 2 question pool.

Identical scoring to round 1's rank_all.py - same corpus, same stopwords, same K1/B -
so BM25 remains a comparable floor across both rounds. Only the question pool changed.

Input : data/questions2.jsonl   {question_id, question, origin, ...}
Output: data/ranks2.json        {question_id: [doc_row_index, ...top 400]}
"""
import gzip, json, math, re, sys, time
from collections import Counter, defaultdict

HOME = "/home/eran2/miko-bench"
CORPUS = HOME + "/data/corpus_full.jsonl.gz"
QUESTIONS = HOME + "/data/questions2.jsonl"
OUT = HOME + "/data/ranks2.json"
TOPK = 400

STOP = set("""a about above after again all also am an and any are as at be because been before being
below between both but by can cannot could did do does doing down during each few for from further had
has have having he her here hers him his how i if in into is it its itself just me more most my no nor
not of off on once only or other our out over own same she should so some such than that the their them
then there these they this those through to too under until up very was we were what when where which
while who whom why will with would you your does actually""".split())

tok_re = re.compile(r"[a-z0-9]+")


def toks(s):
    return [t for t in tok_re.findall(s.lower()) if len(t) > 2 and t not in STOP]


t0 = time.time()
print("loading corpus ...", flush=True)
texts = []
with gzip.open(CORPUS, "rt", encoding="utf-8") as f:
    for line in f:
        texts.append(json.loads(line)["text"])
N = len(texts)
print(f"  {N} pages  ({time.time()-t0:.0f}s)", flush=True)

print("indexing ...", flush=True)
df = Counter()
dl = [0] * N
postings = defaultdict(list)
for i, t in enumerate(texts):
    c = Counter(toks(t))
    dl[i] = sum(c.values())
    for term, n in c.items():
        postings[term].append((i, n))
        df[term] += 1
    if i % 40000 == 0:
        print(f"  {i}/{N}  {time.time()-t0:.0f}s", flush=True)
avgdl = sum(dl) / N
print(f"  vocab {len(postings)}  avgdl {avgdl:.0f}  ({time.time()-t0:.0f}s)", flush=True)

K1, B = 1.5, 0.75
idf = {t: math.log(1 + (N - n + 0.5) / (n + 0.5)) for t, n in df.items()}
MAXDF = N * 0.25

qs = [json.loads(l) for l in open(QUESTIONS, encoding="utf-8")]
print(f"ranking {len(qs)} questions ...", flush=True)
ranks, hits = {}, {}
for j, q in enumerate(qs):
    scores = defaultdict(float)
    for term in set(toks(q["question"])):
        pl = postings.get(term)
        if not pl or df[term] > MAXDF:
            continue
        w = idf[term]
        for i, n in pl:
            scores[i] += w * (n * (K1 + 1)) / (n + K1 * (1 - B + B * dl[i] / avgdl))
    top = sorted(scores.items(), key=lambda kv: -kv[1])[:TOPK]
    ranks[q["question_id"]] = [i for i, _ in top]
    hits[q["question_id"]] = len(scores)
    if j % 100 == 0:
        print(f"  q{j}/{len(qs)}  hits={len(scores)}  {time.time()-t0:.0f}s", flush=True)

json.dump(ranks, open(OUT, "w"))
thin = [k for k, v in hits.items() if v < 200]
print(f"\nwrote {OUT}  ({time.time()-t0:.0f}s)")
print(f"questions with <200 BM25 hits (thin coverage): {len(thin)}")
