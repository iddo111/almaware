#!/bin/bash
# WINSTON FOREVER v2 — 2026-09-02 night. Iddo: "תאמן אותו יותר חזק שייתן תמונות חדות
# ומדוייקות יותר. אולי תגדיל לו את הקורפוס. תבחר אתה מה."
#
# What changed from winston_forever.sh, and why (details in NEXT-RUN.md):
#   --size 256 (was 192)        the loss sees 1.78x the pixels: sharper is only possible
#                               if the painter can SEE the detail it is asked to paint.
#   --recompute                 gradient checkpointing per stroke chunk. Measured: peak
#                               memory 12.2 GB -> 2.9 GB at 256px (b8/120 strokes),
#                               gradient bit-identical. This is what pays for 256.
#   --guard --logit-cap 12      the rainbow collapse, diagnosed and fenced. The collapsed
#                               painter had colour logits of 24,000 (healthy: 1-7) and a
#                               dead gradient. The cap gives the one gradient that never
#                               dies; the guard rolls back to the last good snapshot and
#                               halves the lr if it happens anyway. Proven on a forced
#                               collapse (lr 0.5): 8 detections, good snapshot saved.
#   --lr 5e-4 (was 1e-3)        every cycle re-warms OneCycle to its peak on an already-
#                               trained net; the 4K Alma run collapsed inside that warm-up.
#   trainset-iddo-alma-v2       93 photos (was 19): the 19, 4 Alma-memorial photos from
#                               the PC, 70 curated family photos from the iCloud-stream
#                               backup. EXIF orientation BAKED IN (8 of the old 19 were
#                               being learned sideways). MANIFEST.tsv lists every source.
#   forever-v2/                 its own checkpoint chain, seeded ONCE from forever/painter.pt.
#                               The v1 loop's files are never written.
#
# STEPS is smaller because a 256px step costs more: see NEXT-RUN.md for the measured
# s/step. Override with WINSTON_STEPS=... in the unit if a cycle should be longer.
cd ~/winston
mkdir -p forever-v2 daily
CKPT=forever-v2/painter.pt
STEPS=${WINSTON_STEPS:-2000}
TRAIN=${WINSTON_TRAIN:-trainset-iddo-alma-v2}
CYCLE=0
while true; do
  # politeness gate: one winston at a time on this GPU
  while pgrep -f "winston.py --img" > /dev/null || pgrep -f "winston.py --train" > /dev/null; do
    sleep 120
  done
  # seed from the v1 painter, once (strokes must match: both are 800)
  if [ ! -f "$CKPT" ] && [ -f forever/painter.pt ]; then
    cp forever/painter.pt "$CKPT"
    echo "=== v2 seeded from forever/painter.pt ==="
  fi
  CYCLE=$((CYCLE+1))
  STAMP=$(date +%Y%m%d-%H%M)
  echo "=== FOREVER-v2 cycle $CYCLE @ $STAMP  (train=$TRAIN steps=$STEPS) ==="
  RESUME=""
  [ -f "$CKPT" ] && RESUME="--resume $CKPT"
  python3 winston.py --train "$TRAIN" --strokes 800 --size 256 --steps "$STEPS" --chunk 16 \
      --colour-w 2.5 --lr 5e-4 --recompute --guard --guard-every 100 --logit-cap 12 \
      $RESUME --out forever-v2 2>&1 | grep --line-buffered -E "GUARD|BLANK|CHROMA|BUSY|PASSES|FAILS|resumed|step +[0-9]+00 "
  cp forever-v2/paint-00.png "daily/sample-v2-$STAMP.png" 2>/dev/null
  sleep 30
done
