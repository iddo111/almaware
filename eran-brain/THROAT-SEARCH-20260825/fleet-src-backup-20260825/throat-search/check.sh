#!/bin/bash
# check.sh -- one screen of progress: last heartbeat + best score per worker.
cd "$(dirname "$0")" || exit 1
printf "%-16s %-22s %8s %10s %10s\n" WORKER LAST-BEAT EVALS BEST REAL-BAR
for d in run/*/; do
  n=$(basename "$d")
  hb=$(tail -1 "$d/heartbeat.jsonl" 2>/dev/null)
  utc=$(echo "$hb"  | python3 -c 'import json,sys;print(json.load(sys.stdin).get("utc","-"))' 2>/dev/null)
  ev=$(echo "$hb"   | python3 -c 'import json,sys;print(json.load(sys.stdin).get("evals","-"))' 2>/dev/null)
  best=$(echo "$hb" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("best","-"))' 2>/dev/null)
  bar=$(python3 -c 'import json;print(round(json.load(open("'"$d"'best.json"))["real_wdist_mean"],1))' 2>/dev/null)
  printf "%-16s %-22s %8s %10s %10s\n" "$n" "${utc:--}" "${ev:--}" "${best:--}" "${bar:--}"
done
