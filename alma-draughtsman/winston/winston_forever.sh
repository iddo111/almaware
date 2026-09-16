#!/bin/bash
# WINSTON FOREVER - 24/7 training. Iddo, 2026-09-01 00:27: "אני רוצה אימון 24 7".
#
# REWRITTEN 2026-09-01 17:xx, after the first 17 hours of this order produced nothing at
# all. Three faults were found and each one has a correction here:
#
#   * The old loop piped every cycle through `tail -4`, which threw away the floors and
#     would have thrown away Murphy's ruling. A cycle that reports four lines of nothing
#     is not proof of growth. Now: the FULL log is kept per cycle, and one line per cycle
#     goes into forever/LEDGER.tsv, so growth -- or its absence -- is a table anybody can
#     read in one look instead of a claim anybody has to believe.
#
#   * NOTHING WAS HELD OUT. Every number the old loop could have printed was measured on
#     the pictures it had just trained on, so no cycle could ever have been refuted.
#     `--holdout 0.15` is on, and the held-out number is the only one the ledger records.
#
#   * A cycle was ~7 hours (5,000 steps at 800 strokes / 192px) and winston.py saved only
#     after its loop finished, so an interrupted cycle lost everything. That is exactly
#     how the gallery run burned 17.7 hours and 69 GB of GPU for zero bytes on disk.
#     winston.py now checkpoints at every log step and keeps the BEST state by training
#     loss, and the cycle here is sized to finish and to leave a fresh sample behind.
#
# The recipe below is the one MEASURED on 2026-09-01 to have headroom -- see
# ~/winston-family/headroom/ for the four arms and their numbers.
set -u
cd ~/winston-family || exit 1
mkdir -p forever daily

# THE MEASURED RECIPE, and it is deliberately not the biggest one available. These are
# the exact numbers of the 2026-09-01 headroom experiment (~/winston-family/headroom):
# BORN 0.30116 -> CEILING 0.01156, held-out 0.04424 against BLANK 0.04464 with grid 4.
# grid 1 -- the old global-average encoder -- reached 0.04902 on the same split and does
# NOT beat its floor. A bigger canvas or a longer stroke budget may well be better, but
# nobody has measured it, so it does not go in here until somebody has.
STROKES=${STROKES:-200}
SIZE=${SIZE:-96}
STEPS=${STEPS:-2000}
GRID=${GRID:-4}
CKPT=forever/painter.pt
LEDGER=forever/LEDGER.tsv

[ -f "$LEDGER" ] || printf 'when\tcycle\tstep\tHELD_OUT\tFLOOR\tBLANK\tBUSY\tDEV\tgate1\tgate2\tmurphy\twitnesses\n' > "$LEDGER"

CYCLE=0
while true; do
  # politeness gate: one winston at a time on this GPU
  while pgrep -f "winston.py --img" > /dev/null || pgrep -f "winston.py --train" > /dev/null; do
    sleep 120
  done
  CYCLE=$((CYCLE + 1))
  STAMP=$(date +%Y%m%d-%H%M)
  LOG="forever/cycle-$STAMP.log"
  RES=""
  LR=2e-3
  # A resumed cycle re-runs the whole OneCycle schedule, so the learning rate climbs back
  # up and can undo what the last cycle bought. A resumed cycle therefore gets a quieter
  # one. This is a choice, not a measurement -- the ledger is what will say whether it
  # was the right one.
  if [ -f "$CKPT" ]; then RES="--resume $CKPT"; LR=5e-4; fi

  # A NEW SEED EVERY CYCLE, or the loop is theatre. winston.py used to pin
  # torch.manual_seed(1933), so a resumed cycle started from identical weights with an
  # identical batch order and reproduced the previous cycle step for step -- an
  # unattended loop would revert the same failing round forever and fill the ledger with
  # byte-identical lines. The SPLIT seed stays pinned inside winston.py, so train/dev/
  # test never move and dev cannot leak into train by reshuffling.
  # From the clock, not from $CYCLE: CYCLE restarts at 1 on every service restart, and
  # `Restart=always` means that happens. The seed is printed in the header line below and
  # in the cycle log, so any cycle can still be reproduced exactly by passing it back in.
  SEED=$(( ($(date +%s) % 900000) + 1933 ))
  echo "=== FOREVER cycle $CYCLE @ $STAMP  ($STROKES strokes, ${SIZE}px, $STEPS steps, grid $GRID, lr $LR, seed $SEED) ==="
  python3 winston.py --train trainset --strokes "$STROKES" --size "$SIZE" \
      --steps "$STEPS" --chunk 16 --grid "$GRID" --holdout 0.15 --lr "$LR" \
      --seed "$SEED" $RES --out forever --tag "forever cycle $CYCLE" > "$LOG" 2>&1
  RC=$?

  # one line per cycle, straight out of the run's own printed verdict
  ST=$(grep    '^  step'                 "$LOG" | tail -1 | awk '{print $2}')
  HO=$(grep    'REACHED (held out)'      "$LOG" | tail -1 | awk '{print $NF}')
  FL=$(grep    '  FLOOR    paintings'    "$LOG" | tail -1 | awk '{print $NF}')
  BK=$(grep    '  BLANK    one flat'     "$LOG" | tail -1 | awk '{print $NF}')
  BZ=$(grep    '^BUSY tenth:'            "$LOG" | tail -1 | awk '{print $4}')
  G1=$(grep    'gate 1'                  "$LOG" | tail -1 | awk '{print $7}')
  # $8, not $7: the gate-2 sentence has one more word than the gate-1 sentence, and the
  # very first ledger line duly recorded the word "all?" as a verdict. Fixed the same hour.
  G2=$(grep    'gate 2'                  "$LOG" | tail -1 | awk '{print $8}')
  MU=$(grep    '  RULING:'               "$LOG" | tail -1 | awk '{print $2}')
  # WHICH witness spoke, not merely that one did. Murphy will say FOOLING ITSELF on every
  # unattended cycle for as long as nobody opens the paintings -- that is `unlooked`, and
  # it is a correct standing demand for a human eye, not a training failure. A column that
  # cannot tell it apart from `below_floor` is a column that never moves.
  WI=$(sed -n '/witnesses that spoke:/,/RULING:/p' "$LOG" | grep -E '^     [a-z_]+ ' \
       | awk '{printf "%s,", $1}' | sed 's/,$//')
  DV=$(grep    '  DEV      '             "$LOG" | tail -1 | awk '{print $NF}')
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
     "$(date +%Y-%m-%dT%H:%M)" "$CYCLE" "${ST:-?}" "${HO:-?}" "${FL:-?}" "${BK:-?}" \
     "${BZ:-?}" "${DV:-?}" "${G1:-?}" "${G2:-?}" "${MU:-?}" "${WI:--}" >> "$LEDGER"
  echo "cycle $CYCLE rc=$RC  held-out ${HO:-?} vs blank ${BK:-?}  gate1 ${G1:-?}  murphy ${MU:-?}"

  # ACCEPT OR REVERT, decided on DEV and never on the number above.
  #
  # Measured 2026-09-01 18:32: cycle 2 resumed cycle 1's painter, drove the training loss
  # from 0.06902 down to 0.05604, and drove the held-out score from 0.04424 UP to 0.04695
  # -- BORN 0.04424, REACHED 0.04695, HEADROOM -0.00271. It went backwards, and a loop
  # that keeps every cycle would have kept it. A loop that decided on the held-out set
  # would fix that and quietly fit the held-out set instead, which is the same fake fix
  # under a better name. So the decision is made on DEV, and the held-out number stays a
  # report that nothing ever selects on.
  BESTF=forever/BEST_DEV
  BEST=$(cat "$BESTF" 2>/dev/null || echo "")
  KEPT="kept"
  if [ -n "${DV:-}" ] && [ -f "$CKPT" ]; then
    if [ -z "$BEST" ] || awk "BEGIN{exit !($DV < $BEST)}"; then
      cp "$CKPT" forever/painter-best.pt && echo "$DV" > "$BESTF"
      echo "  cycle $CYCLE ACCEPTED on dev ($DV < ${BEST:-inf}); painter-best.pt updated"
    else
      cp forever/painter-best.pt "$CKPT"
      KEPT="REVERTED"
      echo "  cycle $CYCLE REVERTED on dev ($DV >= $BEST); rolled back to painter-best.pt"
    fi
  fi
  echo "  ledger: $KEPT  dev=${DV:-?}  best_dev=$(cat "$BESTF" 2>/dev/null || echo -)"
  tail -26 "$LOG"

  cp forever/paint-00.png "daily/sample-$STAMP.png" 2>/dev/null
  sleep 30
done
