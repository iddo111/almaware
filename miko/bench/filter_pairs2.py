# -*- coding: utf-8 -*-
"""Drop the questions this corpus genuinely cannot answer, and SAY HOW MANY.

Round 1 did this with a separate coverage probe (top-12 judged first, 33 of 98 questions
dropped). Round 2 judges everything once and filters afterwards from the labels already
paid for - same decision, one pass instead of two.

The rule: a question survives if any of its `top` pages scored >= --thr. A question whose
best page is a zero teaches nothing except "predict zero", and it makes the constant-zero
floor look stronger for a reason that has nothing to do with any model.

The filter is a property of the CORPUS, not of any model, and it is applied identically
to train, val, gtest and sealed. Both files are kept and both floors are reported.
"""
import argparse, json
from collections import defaultdict, Counter

HOME = "/home/eran2/miko-bench"
ap = argparse.ArgumentParser()
ap.add_argument("--inp", default=HOME + "/data/pairs2.jsonl")
ap.add_argument("--out", default=HOME + "/data/pairs2f.jsonl")
ap.add_argument("--thr", type=float, default=0.2)
a = ap.parse_args()

rows = [json.loads(l) for l in open(a.inp, encoding="utf-8")]
best = defaultdict(float)
origin = {}
for r in rows:
    origin[r["question_id"]] = r["origin"]
    if r["stratum"] == "top":
        best[r["question_id"]] = max(best[r["question_id"]], r["score"])

keep = {q for q, b in best.items() if b >= a.thr}
kept = [r for r in rows if r["question_id"] in keep]

tot = Counter(origin.values())
kep = Counter(origin[q] for q in keep)
print(f"threshold: a question survives if its best `top` page scored >= {a.thr}")
for o in sorted(tot):
    print(f"  {o:<8} {kep[o]:5d} / {tot[o]:5d} questions survive "
          f"({kep[o]/tot[o]*100:5.1f}%)  -- {tot[o]-kep[o]} dropped as uncovered")
print(f"  TOTAL    {len(keep):5d} / {len(tot):5d} questions, "
      f"{len(kept):6d} / {len(rows):6d} pairs -> {a.out}")

with open(a.out, "w", encoding="utf-8") as f:
    for r in kept:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")

for name, rs in (("ALL", rows), ("FILTERED", kept)):
    v = [r["score"] for r in rs]
    print(f"  {name:<9} mean label {sum(v)/len(v):.4f}   "
          f">=0.5 {sum(1 for x in v if x >= 0.5)/len(v)*100:5.1f}%   "
          f"<=0.1 {sum(1 for x in v if x <= 0.1)/len(v)*100:5.1f}%")
