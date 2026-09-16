# -*- coding: utf-8 -*-
"""Choose WHICH (question, page) pairs get judged. Real pages only.

The strata exist so the label distribution is not 95% zero. A dataset where almost
every pair is irrelevant teaches nothing, so each question deliberately gets:
    top      BM25 rank 1-10            expected: relevant
    near     BM25 rank 25-150          same vocabulary, wrong answer  (HARD NEGATIVE)
    sibling  top of an ADJACENT question's ranking, minus this question's top 150
                                       neighbouring topic             (HARD NEGATIVE)
    random   uniform from the corpus   irrelevant                     (easy negative)

--mode probe : top 12 only, for the coverage probe that decides which questions survive
--mode full  : the full strata, for the questions listed in --keep
"""
import argparse, gzip, json, random, sys
from collections import Counter, defaultdict

sys.path.insert(0, "/home/eran2/miko-bench")
from questions import QUESTIONS, SIBLING

CORPUS = "/home/eran2/miko-bench/data/corpus_full.jsonl.gz"
RANKS = "/home/eran2/miko-bench/data/ranks.json"
EXCERPT = 1024          # chars the judge sees == bytes MIKO reads (max_len 1024)
SEED = 20260905
SOURCE = "HuggingFaceFW/fineweb-edu:sample/10BT:013_00000.parquet"

ap = argparse.ArgumentParser()
ap.add_argument("--mode", choices=["probe", "full"], required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--keep", default="")      # comma separated question indices
a = ap.parse_args()

docs = []
with gzip.open(CORPUS, "rt", encoding="utf-8") as f:
    for line in f:
        docs.append(json.loads(line))
N = len(docs)
ranks = {int(k): v for k, v in json.load(open(RANKS)).items()}
keep = sorted(int(x) for x in a.keep.split(",") if x.strip()) if a.keep else list(range(len(QUESTIONS)))

rng = random.Random(SEED)
by_cluster = defaultdict(list)
for qi in keep:
    by_cluster[QUESTIONS[qi][0]].append(qi)

rows = []
for qi in keep:
    cl, q = QUESTIONS[qi]
    r = ranks[qi]
    if a.mode == "probe":
        picks = [(i, "top") for i in r[:12]]
    else:
        blocked = set(r[:150])
        picks = [(i, "top") for i in r[:10]]
        mid = r[25:150]
        picks += [(i, "near") for i in rng.sample(mid, min(16, len(mid)))]
        sibs = by_cluster.get(SIBLING[cl]) or [x for x in keep if x != qi]
        sib_qi = sibs[qi % len(sibs)]
        sib_pool = [i for i in ranks[sib_qi][:60] if i not in blocked]
        picks += [(i, "sibling") for i in rng.sample(sib_pool, min(8, len(sib_pool)))]
        seen = {i for i, _ in picks}
        rnd = []
        while len(rnd) < 6:
            i = rng.randrange(N)
            if i not in seen and i not in blocked:
                rnd.append(i); seen.add(i)
        picks += [(i, "random") for i in rnd]

    for i, stratum in picks:
        d = docs[i]
        rows.append({
            "pair_id": f"q{qi:03d}_d{i}",
            "question_id": qi,
            "cluster": cl,
            "question": q,
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
print(f"{len(rows)} pairs over {len(keep)} questions -> {a.out}")
print("strata:", Counter(r_["stratum"] for r_ in rows))
print("unique pages:", len({r_["doc_id"] for r_ in rows}))
