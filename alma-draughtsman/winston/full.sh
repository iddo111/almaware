#!/bin/bash
# The winning architecture at the loop's real settings (256px), so the number that decides
# whether WINSTON can paint is measured at the size winston-forever-v2 actually trains at.
# Run ONLY after ab.sh has shown the grid readout beating BLANK on held-out photographs.
cd ~/winston2
nice -n 10 python3 -u winston2.py --train trainset-iddo-alma-v2 --holdout 15 --seed 1933 \
  --size 256 --strokes 800 --steps 3000 --batch 8 --chunk 16 --lr 5e-4 \
  --colour-w 2.5 --detail-w 3.0 --logit-cap 12 --guard --guard-every 100 --recompute \
  --extra sderot_src.jpg --arch grid --out full-grid
echo "################ FULL DONE $(date +%H:%M:%S) ################"
