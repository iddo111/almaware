#!/bin/bash
# run_all.sh - the whole experiment. 3 alphabets x 3 seeds, one recipe.
#
# לזכרו של לָאוֹר ז״ל.
#
# Everything is held fixed except which tokens the model must predict:
#   n_layer 4, d 128, n_head 2, mem_every 2, seq 2048, micro_b 1, accum 8,
#   lr 3e-4, the SAME code-midi/split.json, the SAME 268 train / 30 heldout
#   tracks, the SAME 3 duplicate tracks dropped, the SAME 45,295.3 s of
#   heldout music.
#
# Checkpoints at 375 / 750 / 1500 steps give three budgets from one run each:
#   matched compute   joint@750  vs rhythm@375 + pitch@375
#   matched compute   joint@1500 vs rhythm@750 + pitch@750
#   matched STEPS     joint@1500 vs rhythm@1500 + pitch@1500   (2x compute -
#                     reported, and labelled as the 2x arm it is)
#
# CPU ONLY, nice 19, 2 threads per job. Every GPU on the fleet is committed:
# eran1 holds Iddo's two live KESHEV mic decoders, eran2's is ComfyUI (8KGFX),
# eran3's is the coder continued-pretraining, eran4's is WINSTON + gpt-oss-120b.
# None of them are ours to slow down.
set -u
cd "$(dirname "$0")"

SEEDS="${SEEDS:-1337 2026 907}"
MARKS="${MARKS:-375,750,1500}"
OUT="${OUT:-../runs}"
mkdir -p "$OUT"

for seed in $SEEDS; do
  for a in joint rhythm pitch; do
    case $a in
      joint)  td=../tokens-poly;   cd_=../cache-joint  ;;
      rhythm) td=../tokens-rhythm; cd_=../cache-rhythm ;;
      pitch)  td=../tokens-pitch;  cd_=../cache-pitch  ;;
    esac
    ck="$OUT/$a-s$seed"
    if [ -f "$ck/step${MARKS##*,}.pt" ]; then
      echo "skip $a seed=$seed (already has step${MARKS##*,}.pt)"
      continue
    fi
    mkdir -p "$ck"
    PYTHONIOENCODING=utf-8 OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 \
    nice -n 19 python3 split_train.py \
        --alphabet "$a" --tokdir "$td" --cache "$cd_" --ckpt "$ck" \
        --seed "$seed" --marks "$MARKS" --threads 2 \
        > "$ck/run.log" 2>&1 &
    echo "launched $a seed=$seed pid=$! -> $ck"
  done
done
wait
echo "ALL RUNS DONE"
