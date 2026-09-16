#!/usr/bin/env bash
# Two fine-tunes, sequential (24 GiB available on this node will not hold two).
#
# The open question the bake-off could not settle: the alpha=0.20 soup dominates
# the openai base on every measured metric today, but alpha=0.50 has clearly
# better Hebrew (fleurs_he 20.43 vs 25.87) and intact English DECODING
# (fleurs_en 6.30) -- what it lacks is language ID (38% on fleurs_en). Language
# ID is a single token with 10,323 supervised examples in this corpus, so it is
# plausibly the easiest thing for training to repair. If it does, alpha=0.50
# ends up the better model. That is a measurable question, so measure it.
set -u
cd "$HOME/whisper-iddo"
COMMON="--epochs 3 --bs 16 --accum 2 --lr 1e-5 --encoder-lr-mult 0.25 \
        --freeze-encoder-epochs 1.0 --warmup 50 --evals-per-epoch 3 \
        --ts-frac 0.2 --spec-augment 0.05 \
        --eval-sets iddo_tierA,fleurs_he,fleurs_en"

for A in 20 50; do
  echo "=== run soup_${A} $(date -Is)"
  PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1 ./.venv/bin/python train.py \
      --base "./soup_${A}" --out "./runs/ft${A}" $COMMON \
      > "logs/ft${A}.log" 2>&1
  echo "=== run soup_${A} exit=$? $(date -Is)"
done
echo "=== ALL RUNS COMPLETE $(date -Is)"
