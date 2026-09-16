#!/bin/bash
# sup.sh -- supervisor for ONE worker: relaunch on crash, resume from state.json,
# stop on deadline (exit 99) or when a STOP file appears in the search dir.
arm=$1; seed=$2; nice_n=${3:-5}; hours=${4:-47}
cd "$(dirname "$0")" || exit 1
out="run/$arm-$seed"
mkdir -p "$out"
while true; do
  if [ -f STOP ]; then
    echo "$(date -u +%FT%TZ) STOP file seen, not relaunching" >> "$out/console.log"
    break
  fi
  OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    nice -n "$nice_n" python3 run_worker.py --arm "$arm" --seed "$seed" \
    --out "$out" --hours "$hours" >> "$out/console.log" 2>&1
  rc=$?
  echo "$(date -u +%FT%TZ) worker exited rc=$rc" >> "$out/console.log"
  [ "$rc" -eq 99 ] && break
  sleep 15
done
