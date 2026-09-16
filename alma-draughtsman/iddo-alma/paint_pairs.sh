#!/bin/bash
# Paint the nine Iddo+Alma photos, then resume the gallery training.
cd ~/winston-family
pkill -STOP -f "winston.py --train"
echo "gallery-PAUSED"
for img in iddo-alma/*.jpg; do
  base=$(basename "$img"); stem="${base%.*}"
  [ -f "out-pairs/$stem/painting-2048px.png" ] && continue
  echo "=== painting $base ==="
  python3 winston.py --img "$img" --strokes 600 --size 176 --steps 4000 --chunk 24 --render 2048 --out "out-pairs/$stem" 2>&1 | tail -2
done
echo "ALL-PAIRS-DONE"
pkill -CONT -f "winston.py --train"
echo "gallery-RESUMED"
