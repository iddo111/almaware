#!/bin/bash
# WINSTON FOREVER — 24/7 training, Iddo's order 2026-09-01 00:27: "אני רוצה אימון 24 7".
# Each cycle continues the gallery painter from its last checkpoint for another 5,000
# steps, saves, and renders one fresh sample so every morning has proof of growth.
# It WAITS politely while any other winston job (a painting queue, a manual run) is on
# the GPU, and never starts over: --resume is the whole point.
cd ~/winston
mkdir -p forever daily
CKPT=forever/painter.pt
CYCLE=0
while true; do
  # politeness gate: one winston at a time on this GPU
  while pgrep -f "winston.py --img" > /dev/null || pgrep -f "winston.py --train" > /dev/null; do
    sleep 120
  done
  # adopt the first completed manual gallery run as the seed, once
  if [ ! -f "$CKPT" ] && [ -f outGALLERY/painter.pt ]; then
    cp outGALLERY/painter.pt "$CKPT"
  fi
  CYCLE=$((CYCLE+1))
  STAMP=$(date +%Y%m%d-%H%M)
  echo "=== FOREVER cycle $CYCLE @ $STAMP ==="
  if [ -f "$CKPT" ]; then
    python3 winston.py --train trainset --strokes 800 --size 192 --steps 5000 --chunk 16 --colour-w 2.5 --lr 1e-3 \
      --resume "$CKPT" --out forever 2>&1 | tail -4
  else
    python3 winston.py --train trainset --strokes 800 --size 192 --steps 5000 --chunk 16 --colour-w 2.5 --lr 1e-3 \
      --out forever 2>&1 | tail -4
  fi
  # keep a dated copy of the floors line + one sample per cycle
  cp forever/paint-00.png "daily/sample-$STAMP.png" 2>/dev/null
  sleep 30
done
