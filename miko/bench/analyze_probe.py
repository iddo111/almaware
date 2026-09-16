# -*- coding: utf-8 -*-
"""Which questions can this corpus actually answer? Measured, not guessed."""
import json, statistics
from collections import defaultdict, Counter

rows = [json.loads(l) for l in open("/home/eran2/miko-bench/data/probe_scored.jsonl")]
by = defaultdict(list)
for r in rows:
    by[(r["question_id"], r["cluster"], r["question"])].append(r["score"])

items = []
for (qi, cl, q), v in by.items():
    v = sorted(v, reverse=True)
    items.append((qi, cl, q, max(v), statistics.mean(v), sum(1 for x in v if x >= 0.5)))
items.sort(key=lambda t: -t[3])

print(f"{len(items)} questions probed (top-12 BM25 each, judged by Qwen3-4B-Instruct-2507)")
print("\n--- WORST 20 (the corpus has little or nothing for these) ---")
for qi, cl, q, mx, mn, n5 in items[-20:]:
    print(f"  q{qi:03d} {cl} max={mx:.2f} mean={mn:.2f} n>=0.5:{n5:2d}  {q[:60]}")
print("\n--- BEST 12 ---")
for qi, cl, q, mx, mn, n5 in items[:12]:
    print(f"  q{qi:03d} {cl} max={mx:.2f} mean={mn:.2f} n>=0.5:{n5:2d}  {q[:60]}")

keep = sorted(qi for qi, cl, q, mx, mn, n5 in items if n5 >= 2)
print(f"\nKEEP (>=2 of top-12 scoring >=0.5): {len(keep)} questions")
print(Counter(cl for qi, cl, q, mx, mn, n5 in items if n5 >= 2))
open("/home/eran2/miko-bench/data/keep.txt", "w").write(",".join(str(x) for x in keep))
json.dump([{"qid": qi, "cluster": cl, "question": q, "max": mx, "mean": mn, "n_ge_0.5": n5}
           for qi, cl, q, mx, mn, n5 in items],
          open("/home/eran2/miko-bench/data/coverage.json", "w"), indent=1)
