#!/usr/bin/env bash
# מארג QSFP — מודד all-reduce busbw לטופולוגיה נתונה. Real numbers, no demo.
# usage:  bash bench_allreduce.sh <hostfile> <np> <tag>
#   hostfile = שורה לכל צומת (שם/IP slots=<GPUs>), למשל:  eran1 slots=1
#   np       = מספר תהליכים כולל (=סה"כ GPU)
#   tag      = שם הקונפיג (ring / triangle / double / single ...)
set -euo pipefail

HOSTFILE="${1:?hostfile}"; NP="${2:?np}"; TAG="${3:?tag}"
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/results"; mkdir -p "$OUT"
LOG="$OUT/$TAG.log"

# נתיב ל-all_reduce_perf (התאם אם בנית במקום אחר)
ARP="${ARP:-$HOME/nccl-tests/build/all_reduce_perf}"
if [[ ! -x "$ARP" ]]; then
  echo "❌ לא נמצא all_reduce_perf ב-$ARP — בנה: git clone https://github.com/NVIDIA/nccl-tests && cd nccl-tests && make MPI=1" | tee "$LOG"
  exit 1
fi

echo "=== [$TAG] np=$NP  $(cat "$HOSTFILE" | tr '\n' ' ') ===" | tee "$LOG"
# -b 8B  -e 8G  -f 2 (הכפלה)  -g 1 (GPU לכל תהליך)
mpirun --hostfile "$HOSTFILE" -np "$NP" \
  -x NCCL_DEBUG=WARN \
  "$ARP" -b 8 -e 8G -f 2 -g 1 2>&1 | tee -a "$LOG"

echo "--- שיא busbw ל-[$TAG]: ---" | tee -a "$LOG"
# העמודה האחרונה של הפלט = busbw (GB/s); ניקח את המקסימום
awk '/^ *[0-9]/{bw=$NF} END{printf "  busbw_max = %s GB/s\n", bw}' "$LOG" | tee -a "$LOG"
echo "נשמר: $LOG"
