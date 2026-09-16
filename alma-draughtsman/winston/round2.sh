#!/bin/bash
# Round 2, after round 1 measured this (128px, 400 strokes, 1500 steps, same split/seed):
#
#            TRAIN            HELD-OUT (15 unseen)     sderot (outsider)   paints what it
#   pool  0.03215 x1.54 PASS  0.06750 x0.83 FAIL       0.08491 x0.55 FAIL  was shown 4/16
#   grid  0.03302 x1.50 PASS  0.06461 x0.87 FAIL       0.07102 x0.66 FAIL  was shown 9/16
#
# The readout change is doing real work -- it more than DOUBLES the number of held-out
# photographs whose painting is nearest to the photograph actually in front of it, on a
# net with 4.7x fewer parameters -- but it does not on its own clear BLANK on an unseen
# picture. The binding constraint is that 78 photographs is a tiny corpus.
#
# So round 2 adds the levers a spatially-grounded readout can actually use, and runs the
# pooled net under the IDENTICAL treatment as the control:
#   --aug          flip / zoom / shift. A shifted copy is a new example for weights shared
#                  across cells; under a global average pool it is nearly the same code.
#   two-scale      each grid now reads the stage-3 map (where the edge is) as well as
#                  stage 4 (the context). At 128px the last map is 8x8, so the 16x16 grid
#                  had been reading a blurred copy of the coarse features.
#   --colour-w 1.5 round 1 finished at chroma x1.56-x2.25 against the source. The hinge at
#                  2.5 over-saturates a short run, and over-saturated paint IS error.
#   2500 steps     grid's held-out bottomed at step 1050 and 1500 was not the limit.
cd ~/winston2
COMMON="--train trainset-iddo-alma-v2 --holdout 15 --seed 1933 --size 128 --strokes 400 \
--steps 2500 --batch 12 --chunk 50 --lr 5e-4 --colour-w 1.5 --detail-w 3.0 \
--logit-cap 12 --guard --guard-every 100 --recompute --aug --extra sderot_src.jpg"
for ARCH in grid pool; do
  echo "################ R2 ARCH=$ARCH aug  $(date +%H:%M:%S) ################"
  nice -n 10 python3 -u winston2.py $COMMON --arch $ARCH --out r2-$ARCH
done
echo "################ ROUND 2 DONE $(date +%H:%M:%S) ################"
