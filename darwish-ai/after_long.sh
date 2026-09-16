#!/bin/bash
# Wait for the two long v2 runs to finish, then measure them properly.
# לזכרו של לָאוֹר ז״ל.
#
# PHASE 1 is the one that answers Iddo's question. Every snapshot of both
# seeds is re-scored on the FULL heldout stream (all 723 windows, every
# heldout target token exactly once), NOT on the 16 windows the training
# loop uses. That curve is what says whether the run turned over into
# overfitting, or merely flattened -- and a flat curve is the finding that
# 1.36M parameters, not compute, is the binding constraint.
#
# PHASE 2 is the expensive half: generation metrics (event density, the
# vertical-interval PEARSON, entropy slope) on a spread of checkpoints.
# Sampling has no KV cache and is O(n^2), so it runs on a subset, chosen by
# step number in advance rather than by which ones looked good.
cd ~/darwish-ai

while pgrep -f "ckpt ckpt-poly-long" > /dev/null; do sleep 60; done
echo "[gate] both training runs exited $(date +%H:%M:%S)"

# also wait for the CPU baseline generation job, so the GPU/CPU are ours
while pgrep -f "ckpts ckpt-poly-BACKUP" > /dev/null; do sleep 30; done
echo "[gate] baseline eval done $(date +%H:%M:%S)"

echo "=== PHASE 1: full-heldout bits/s on every snapshot, both seeds ==="
python3 long_eval.py --no-gen --device cuda --threads 4 \
  --out long_curve_s1337.json \
  --ckpts ckpt-poly-BACKUP-20260906/best.pt \
          "ckpt-poly-long-s1337/snap_*.pt" ckpt-poly-long-s1337/best.pt \
  2>&1 | tee long_curve_s1337.log

python3 long_eval.py --no-gen --device cuda --threads 4 \
  --out long_curve_s2026.json \
  --ckpts ckpt-poly-BACKUP-20260906/best.pt \
          "ckpt-poly-long-s2026/snap_*.pt" ckpt-poly-long-s2026/best.pt \
  2>&1 | tee long_curve_s2026.log

echo "=== PHASE 2: generation metrics on a fixed spread of checkpoints ==="
python3 long_eval.py --gen-seeds 5 --device cuda --threads 4 \
  --out long_gen.json \
  --ckpts ckpt-poly-BACKUP-20260906/best.pt \
          ckpt-poly-long-s1337/snap_001000.pt \
          ckpt-poly-long-s1337/snap_002000.pt \
          ckpt-poly-long-s1337/snap_005000.pt \
          ckpt-poly-long-s1337/snap_010000.pt \
          ckpt-poly-long-s1337/snap_020000.pt \
          ckpt-poly-long-s1337/snap_030000.pt \
          ckpt-poly-long-s2026/snap_030000.pt \
  2>&1 | tee long_gen.log

echo "[done] $(date +%H:%M:%S)"
