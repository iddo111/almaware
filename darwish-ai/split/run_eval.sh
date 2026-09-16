#!/bin/bash
# run_eval.sh - score every checkpoint against the full heldout set, in parallel.
# One process per (alphabet, seed); each writes a partial that split_report.py
# merges after checking the partials agree about the heldout set.
set -u
cd "$(dirname "$0")"
SEEDS="${SEEDS:-1337 2026 907}"
MARKS="${MARKS:-375 750 1500}"
RUNS="${RUNS:-../runs}"
OUTDIR="${OUTDIR:-../evals}"
SEQ="${SEQ:-2048}"
EXTRA="${EXTRA:-}"
mkdir -p "$OUTDIR"

build_runs() {   # $1=alphabet $2=seed
  python3 - "$1" "$2" "$RUNS" $MARKS <<'PY'
import json,sys,os
a,seed,runs=sys.argv[1],sys.argv[2],sys.argv[3]
marks=sys.argv[4:]
d={a:{seed:{}}}
for m in marks:
    p=os.path.join(runs,"%s-s%s"%(a,seed),"step%s.pt"%m)
    if os.path.exists(p): d[a][seed][m]=p
print(json.dumps(d))
PY
}

TD='{"joint":"../tokens-poly","rhythm":"../tokens-rhythm","pitch":"../tokens-pitch"}'
CA='{"joint":"../cache-joint","rhythm":"../cache-rhythm","pitch":"../cache-pitch"}'

for seed in $SEEDS; do
  for a in joint rhythm pitch; do
    R=$(build_runs "$a" "$seed")
    out="$OUTDIR/eval-$a-s$seed.json"
    PYTHONIOENCODING=utf-8 OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 \
    nice -n 19 python3 split_eval.py --runs "$R" --tokdirs "$TD" --caches "$CA" \
        --seq "$SEQ" --threads 2 --only-alphabet "$a" --only-seed "$seed" \
        $EXTRA --out "$out" > "$OUTDIR/eval-$a-s$seed.log" 2>&1 &
    echo "eval launched $a seed=$seed -> $out"
  done
done
wait
echo "ALL EVALS DONE"
ls -la "$OUTDIR"
