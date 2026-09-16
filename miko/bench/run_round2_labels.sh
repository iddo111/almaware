#!/bin/bash
# After the rubric-A judge is cut at depth 20: finish the label side of round 2.
set -e
cd /home/eran2/miko-bench
export PYTHONUNBUFFERED=1
D=48840        # 20 pages x 2442 questions

echo "=== truncate to the complete depth-20 prefix ==="
wc -l data/pairs2.jsonl
head -n $D data/pairs2.jsonl > data/pairs2_d20.jsonl
mv data/pairs2.jsonl data/pairs2_raw_judged.jsonl
mv data/pairs2_d20.jsonl data/pairs2.jsonl
python3 - <<'PY'
import json
from collections import Counter
rows=[json.loads(l) for l in open("data/pairs2.jsonl",encoding="utf-8")]
per=Counter(r["question_id"] for r in rows)
print(f"{len(rows)} pairs over {len(per)} questions; per-question min={min(per.values())} max={max(per.values())}")
print("strata:", dict(Counter(r["stratum"] for r in rows)))
print("origin:", dict(Counter(r["origin"] for r in rows)))
PY

echo "=== rubric B on a 1-in-10 subsample of the SAME rows ==="
head -n $D data/pairs2_ordered.jsonl | awk 'NR%10==1' > data/pairs2B_input.jsonl
wc -l data/pairs2B_input.jsonl
python3 judge.py --inp data/pairs2B_input.jsonl --out data/pairs2_rubricB.jsonl \
        --rubric B --bs 32 2>&1 | grep -av "it/s\]" > judge2_B.log
tail -2 judge2_B.log

echo "=== label validity at the new scale ==="
python3 validity2.py 2>&1 | tee validity2.log

echo "=== the dataset's own numbers ==="
python3 - <<'PY'
import json
from collections import defaultdict
rows=[json.loads(l) for l in open("data/pairs2.jsonl",encoding="utf-8")]
print(f"pairs {len(rows)}  questions {len({r['question_id'] for r in rows})}  "
      f"unique pages {len({r['doc_id'] for r in rows})}  unique urls {len({r['url'] for r in rows})}")
for keyname in ("stratum","origin"):
    by=defaultdict(list)
    for r in rows: by[r[keyname]].append(r["score"])
    print(f"\nBY {keyname.upper()}")
    for k in sorted(by):
        v=sorted(by[k])
        print(f"  {k:<9} n={len(v):6d} mean={sum(v)/len(v):.3f} median={v[len(v)//2]:.3f} "
              f">=0.5:{sum(1 for x in v if x>=0.5)/len(v)*100:5.1f}% <=0.1:{sum(1 for x in v if x<=0.1)/len(v)*100:5.1f}%")
allv=[r["score"] for r in rows]
print(f"\noverall mean {sum(allv)/len(allv):.4f}  >=0.5 {sum(1 for x in allv if x>=0.5)/len(allv)*100:.1f}%  "
      f"<=0.1 {sum(1 for x in allv if x<=0.1)/len(allv)*100:.1f}%")
PY

echo "=== coverage filter ==="
python3 filter_pairs2.py 2>&1 | tee filter2.log
echo "=== LABELS DONE ==="; date
