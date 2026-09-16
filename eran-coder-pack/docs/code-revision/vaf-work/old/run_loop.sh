#!/usr/bin/env bash
# voice-ant-farm continuous loop: colony training + evening tribal fire, then rest.
#
# `fire.py cycle` calls train_colony itself both before and after the fire, so
# this single invocation covers day training AND the fire. Running colony.py
# train separately would only duplicate work.
#
# Guards live in fire.py: real audio always in the mix, heldout measured on real
# recordings only, synthetic proportion capped, provenance recorded per round.
set -u
cd "$HOME/voice-ant-farm"
mkdir -p logs fire

SLEEP_SECONDS="${VAF_SLEEP_SECONDS:-900}"
# Each fire round writes ~25 MB of synthesized wavs. Keep a bounded window.
FIRE_KEEP="${VAF_FIRE_KEEP:-48}"

while true; do
  echo "[$(date -Is)] cycle start lane=${VAF_NODE_LANE:-auto}"
  python3 fire.py cycle \
    --recordings recordings \
    --manifest recordings/manifest.json \
    --state state \
    --out fire \
    --max-synthetic 0.3 \
    >> logs/cycles.jsonl 2>> logs/cycles.err
  rc=$?
  echo "[$(date -Is)] cycle done rc=$rc"

  # Retention: drop all but the newest FIRE_KEEP round directories. The name
  # pattern is locked to fire.py's round_id format so nothing else can match.
  find fire -mindepth 1 -maxdepth 1 -type d -regextype posix-extended \
    -regex '.*/[0-9]{8}T[0-9]{6}Z$' -printf '%f\n' 2>/dev/null \
    | sort | head -n -"$FIRE_KEEP" \
    | while read -r stale; do rm -rf -- "fire/$stale"; done

  echo "[$(date -Is)] sleeping ${SLEEP_SECONDS}s"
  sleep "$SLEEP_SECONDS"
done
