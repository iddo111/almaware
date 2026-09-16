#!/bin/bash
# The honest A/B. Same split, same seed, same steps, same losses, same floors -- the ONLY
# difference between the two runs is the readout: global average pool vs spatial pyramid.
# Sequential, not parallel: eran2 is already carrying MIKO2's judge, and this is a guest.
#
# 400 strokes and chunk 50, not 800/16, for a measured reason: at 800/16 the step is
# LAUNCH bound, not compute bound -- 50 checkpointed chunks per step, one core pinned at
# 100%, ~3 s/step, which is 4 hours for the pair on a GPU that MIKO2 is already using.
# 400 strokes at 128px is winston.py's own documented default ("400 painted a recognisable
# boulevard"), and 8 chunks instead of 50 removes the launch overhead. Both arms get the
# identical budget, so the comparison is untouched; the 256px/800-stroke confirmation runs
# afterwards on whichever readout wins.
cd ~/winston2
COMMON="--train trainset-iddo-alma-v2 --holdout 15 --seed 1933 --size 128 --strokes 400 \
--steps 1500 --batch 12 --chunk 50 --lr 5e-4 --colour-w 2.5 --detail-w 3.0 \
--logit-cap 12 --guard --guard-every 100 --recompute --extra sderot_src.jpg"
for ARCH in pool grid; do
  echo "################ ARCH=$ARCH  $(date +%H:%M:%S) ################"
  nice -n 10 python3 -u winston2.py $COMMON --arch $ARCH --out ab-$ARCH
done
echo "################ A/B DONE $(date +%H:%M:%S) ################"
