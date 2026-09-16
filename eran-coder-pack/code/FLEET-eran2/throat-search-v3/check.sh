#!/bin/bash
# check.sh -- one screen of v3 progress: last heartbeat + best + the Ear-v3
# real-clip bar + review flag per worker.
cd "$(dirname "$0")" || exit 1
printf "%-20s %-22s %8s %10s %9s %7s\n" WORKER LAST-BEAT EVALS BEST REAL-BAR REVIEW
for d in run/*/; do
  n=$(basename "$d")
  hb=$(tail -1 "$d/heartbeat.jsonl" 2>/dev/null)
  utc=$(echo "$hb"  | python3 -c 'import json,sys;print(json.load(sys.stdin).get("utc","-"))' 2>/dev/null)
  ev=$(echo "$hb"   | python3 -c 'import json,sys;print(json.load(sys.stdin).get("evals","-"))' 2>/dev/null)
  best=$(echo "$hb" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("best","-"))' 2>/dev/null)
  bar=$(python3 -c 'import json;print(round(json.load(open("'"$d"'best.json"))["real_wdist_mean"],2))' 2>/dev/null)
  rev=$(python3 -c 'import json;print("FLAG" if json.load(open("'"$d"'best.json")).get("review_flagged") else "-")' 2>/dev/null)
  printf "%-20s %-22s %8s %10s %9s %7s\n" "$n" "${utc:--}" "${ev:--}" "${best:--}" "${bar:--}" "${rev:--}"
done
n_rev=$(ls review/*.wav 2>/dev/null | wc -l)
echo "review folder: $n_rev flagged candidates (for Iddo's ears, never auto-celebrated)"
