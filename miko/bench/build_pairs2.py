# -*- coding: utf-8 -*-
"""Round 2 pair construction. Same idea as round 1, RE-WEIGHTED by what round 1 measured.

Round 1's own stratum table (2,600 pairs, judged by Qwen3-4B):

    top      n= 650  mean 0.439   >=0.5: 41.1%
    near     n=1040  mean 0.157   >=0.5:  8.1%    <- the REAL hard negative
    sibling  n= 520  mean 0.012   >=0.5:  0.2%    <- as easy as random. nearly useless.
    random   n= 390  mean 0.004   >=0.5:  0.0%

So `near` earns more of the budget and `sibling` is cut to a token control that keeps the
finding falsifiable. 24 pairs per question, not 40, because the binding constraint round 1
identified was QUESTION BREADTH, not pages per question - the same judge budget buys ~1.7x
more questions this way.

    top      10   BM25 rank 1-10        expected relevant
    near      9   BM25 rank 20-200      same vocabulary, wrong answer   HARD NEGATIVE
    sibling   2   another question's top 60, minus this question's 200  (control)
    random    3   uniform from the corpus                               easy negative
"""
import argparse, gzip, json, random, sys
from collections import Counter

HOME = "/home/eran2/miko-bench"
CORPUS = HOME + "/data/corpus_full.jsonl.gz"
EXCERPT = 1024          # chars the judge sees == bytes MIKO reads (max_len 1024)
SEED = 20260905
SOURCE = "HuggingFaceFW/fineweb-edu:sample/10BT:013_00000.parquet"

ap = argparse.ArgumentParser()
ap.add_argument("--questions", default=HOME + "/data/questions2.jsonl")
ap.add_argument("--ranks", default=HOME + "/data/ranks2.json")
ap.add_argument("--out", default=HOME + "/data/pairs2_unscored.jsonl")
ap.add_argument("--n_top", type=int, default=10)
ap.add_argument("--n_near", type=int, default=9)
ap.add_argument("--n_sib", type=int, default=2)
ap.add_argument("--n_rand", type=int, default=3)
a = ap.parse_args()

docs = []
with gzip.open(CORPUS, "rt", encoding="utf-8") as f:
    for line in f:
        docs.append(json.loads(line))
N = len(docs)
qs = [json.loads(l) for l in open(a.questions, encoding="utf-8")]
ranks = {int(k): v for k, v in json.load(open(a.ranks)).items()}
qids = [q["question_id"] for q in qs]

rng = random.Random(SEED)
rows = []
skipped = 0
for q in qs:
    qi = q["question_id"]
    r = ranks.get(qi, [])
    if len(r) < 60:                       # the corpus has almost nothing on this
        skipped += 1
        continue
    blocked = set(r[:200])
    picks = [(i, "top") for i in r[:a.n_top]]
    mid = r[20:200]
    picks += [(i, "near") for i in rng.sample(mid, min(a.n_near, len(mid)))]
    # sibling: the top of ANOTHER question's ranking, minus anything this question ranks
    sib_qi = qids[(qids.index(qi) + 1 + rng.randrange(len(qids) - 1)) % len(qids)]
    sib_pool = [i for i in ranks.get(sib_qi, [])[:60] if i not in blocked]
    picks += [(i, "sibling") for i in rng.sample(sib_pool, min(a.n_sib, len(sib_pool)))]
    seen = {i for i, _ in picks}
    rnd = []
    tries = 0
    while len(rnd) < a.n_rand and tries < 200:
        i = rng.randrange(N)
        tries += 1
        if i not in seen and i not in blocked:
            rnd.append(i); seen.add(i)
    picks += [(i, "random") for i in rnd]

    for i, stratum in picks:
        d = docs[i]
        rows.append({
            "pair_id": f"q{qi:05d}_d{i}",
            "question_id": qi,
            "question": q["question"],
            "origin": q["origin"],
            "seed_source": q.get("seed_source"),
            "stratum": stratum,
            "doc_id": d["doc_id"],
            "url": d["url"],
            "cc_dump": d["dump"],
            "source_dataset": SOURCE,
            "fineweb_edu_score": d["edu_score"],
            "page": d["text"][:EXCERPT],
        })

with open(a.out, "w", encoding="utf-8") as f:
    for r_ in rows:
        f.write(json.dumps(r_, ensure_ascii=False) + "\n")
print(f"{len(rows)} pairs over {len({r['question_id'] for r in rows})} questions "
      f"({skipped} questions skipped: fewer than 60 BM25 hits) -> {a.out}")
print("strata:", Counter(r_["stratum"] for r_ in rows))
print("origin:", Counter(r_["origin"] for r_ in rows))
print("unique pages:", len({r_["doc_id"] for r_ in rows}))
