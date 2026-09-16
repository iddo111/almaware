# -*- coding: utf-8 -*-
"""Assemble the round 2 question pool and assign stable question_ids.

    origin=corpus   questions generated FROM real fineweb-edu pages     -> TRAIN / VAL
    origin=iddo     questions derived from Iddo's own written material  -> SEALED TEST

The 98 round-1 questions (questions.py, written by hand from his eight FINDINGS files)
are folded into the iddo set verbatim, because they are the most literally his.

Dedup runs ACROSS both sets on content words. A collision is resolved in favour of the
IDDO set, so no sealed question is also a training question. That check is the one that
would otherwise silently destroy the whole experiment.
"""
import json, re, sys

HOME = "/home/eran2/miko-bench"
sys.path.insert(0, HOME)


def key(q):
    ws = [w for w in re.findall(r"[a-z]+", q.lower()) if len(w) > 3]
    return " ".join(sorted(set(ws)))


iddo, corpus = [], []

# round 1's hand-written questions - the most literally his
try:
    from questions import QUESTIONS
    for cl, q in QUESTIONS:
        iddo.append({"question": q, "origin": "iddo", "seed_id": f"round1::{cl}",
                     "seed_source": "findings_handwritten", "seed_title": cl})
except Exception as e:
    print("round-1 questions unavailable:", e, file=sys.stderr)

for path, origin in ((HOME + "/data/q_iddo.jsonl", "iddo"),
                     (HOME + "/data/q_corpus.jsonl", "corpus")):
    try:
        for l in open(path, encoding="utf-8"):
            r = json.loads(l)
            r["origin"] = origin
            (iddo if origin == "iddo" else corpus).append(r)
    except FileNotFoundError:
        print("missing:", path, file=sys.stderr)

seen, out = set(), []
n_collide = 0
for r in iddo + corpus:                      # iddo first: it wins every collision
    k = key(r["question"])
    if k in seen:
        n_collide += 1
        continue
    seen.add(k)
    out.append(r)

for i, r in enumerate(out):
    r["question_id"] = i

with open(HOME + "/data/questions2.jsonl", "w", encoding="utf-8") as f:
    for r in out:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")

from collections import Counter
c = Counter(r["origin"] for r in out)
print(f"{len(out)} questions  ({n_collide} cross-set duplicates dropped, "
      f"iddo always kept over corpus)")
print("by origin:", dict(c))
print("iddo by seed source:", dict(Counter(r.get("seed_source") for r in out
                                           if r["origin"] == "iddo")))
print("\nsample IDDO:")
for r in [x for x in out if x["origin"] == "iddo"][:6]:
    print("   ", r["question"])
print("sample CORPUS:")
for r in [x for x in out if x["origin"] == "corpus"][:6]:
    print("   ", r["question"])
