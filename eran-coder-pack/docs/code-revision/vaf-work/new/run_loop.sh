#!/usr/bin/env bash
# voice-ant-farm continuous loop: colony training + evening tribal fire, then rest.
#
# `fire.py cycle` calls train_colony itself both before and after the fire, so
# this single invocation covers day training AND the fire. Running colony.py
# train separately would only duplicate work.
#
# Guards live in fire.py: real audio always in the mix, heldout measured on real
# recordings only, synthetic proportion capped, provenance recorded per round.
# Candidate-checkpoint retention and the acceptance gate live in fire.py too, so
# that they take effect on the next CYCLE rather than on the next restart.
#
# This loop reports. It never restarts, stops or signals anything - a famine
# check that restarts the starving thing is the poison this project's siblings
# already swallowed.
set -u
cd "$HOME/voice-ant-farm"
mkdir -p logs fire state

SLEEP_SECONDS="${VAF_SLEEP_SECONDS:-900}"
# Each fire round writes ~25 MB of synthesized wavs. Keep a bounded window.
FIRE_KEEP="${VAF_FIRE_KEEP:-48}"
# VAF-10: `rc=$?` used to be echoed and thrown away, so a cycle that failed
# every time for a week produced an identical-looking journal and no alarm.
# The alarm threshold is DERIVED from this loop's own sleep - one hour of
# consecutive failures - never hand-picked.
FAIL_ALARM_AFTER="${VAF_FAIL_ALARM_AFTER:-$(( 3600 / SLEEP_SECONDS ))}"
[ "$FAIL_ALARM_AFTER" -lt 2 ] && FAIL_ALARM_AFTER=2
# VAF-02: when every ant's random-restart search is measurably exhausted, slow
# down instead of spinning. Bounded, and it can only ever make the wait LONGER.
EXHAUSTED_BACKOFF="${VAF_EXHAUSTED_BACKOFF:-4}"

consecutive_failures=0

# One line at service start, so a reader can see the thresholds this loop is
# actually using and that they were derived from its own cadence.
echo "[$(date -Is)] loop start sleep=${SLEEP_SECONDS}s fail_alarm_after=${FAIL_ALARM_AFTER} fire_keep=${FIRE_KEEP} exhausted_backoff=x${EXHAUSTED_BACKOFF}"

while true; do
  echo "[$(date -Is)] cycle start lane=${VAF_NODE_LANE:-auto}"

  # VAF-10: one cycle at a time. train_loop.sh (or a second run_loop) would
  # otherwise race this one on state/round.json and current.json with no
  # compare-and-swap, and one of two concurrent promotions would silently lose.
  rc=0
  if command -v flock >/dev/null 2>&1; then
    exec 9>state/.lock
    if flock -n 9; then
      python3 fire.py cycle \
        --recordings recordings \
        --manifest recordings/manifest.json \
        --state state \
        --out fire \
        --max-synthetic 0.3 \
        >> logs/cycles.jsonl 2>> logs/cycles.err
      rc=$?
      flock -u 9
    else
      rc=0
      echo "[$(date -Is)] cycle skipped: state/.lock held by another loop"
      printf '{"event":"cycle_skipped","reason":"state-lock-held","at":"%s"}\n' \
        "$(date -Is)" >> logs/cycles.jsonl
    fi
    exec 9>&-
  else
    python3 fire.py cycle \
      --recordings recordings \
      --manifest recordings/manifest.json \
      --state state \
      --out fire \
      --max-synthetic 0.3 \
      >> logs/cycles.jsonl 2>> logs/cycles.err
    rc=$?
  fi
  echo "[$(date -Is)] cycle done rc=$rc"

  # VAF-10: the exit code is data, not decoration.
  if [ "$rc" -ne 0 ]; then
    consecutive_failures=$(( consecutive_failures + 1 ))
    if [ "$consecutive_failures" -ge "$FAIL_ALARM_AFTER" ]; then
      printf '{"event":"cycle_failed","rc":%d,"consecutive_failures":%d,"alarm_after":%d,"at":"%s","last_stderr":%s}\n' \
        "$rc" "$consecutive_failures" "$FAIL_ALARM_AFTER" "$(date -Is)" \
        "$(tail -c 400 logs/cycles.err 2>/dev/null | python3 -c 'import json,sys; sys.stdout.write(json.dumps(sys.stdin.read()))' 2>/dev/null || echo '""')" \
        >> logs/cycles.jsonl
      printf '%s rc=%s consecutive=%s\n' "$(date -Is)" "$rc" "$consecutive_failures" \
        > state/UNHEALTHY
      echo "[$(date -Is)] UNHEALTHY: $consecutive_failures consecutive failed cycles"
    fi
  else
    if [ "$consecutive_failures" -gt 0 ]; then
      printf '{"event":"cycle_recovered","after_consecutive_failures":%d,"at":"%s"}\n' \
        "$consecutive_failures" "$(date -Is)" >> logs/cycles.jsonl
    fi
    consecutive_failures=0
    rm -f state/UNHEALTHY
  fi

  # Retention: drop all but the newest FIRE_KEEP round directories. The name
  # pattern is locked to fire.py's round_id format so nothing else can match.
  find fire -mindepth 1 -maxdepth 1 -type d -regextype posix-extended \
    -regex '.*/[0-9]{8}T[0-9]{6}Z$' -printf '%f\n' 2>/dev/null \
    | sort | head -n -"$FIRE_KEEP" \
    | while read -r stale; do rm -rf -- "fire/$stale"; done

  # VAF-02: back off only when fire.py itself measured every ant's search as
  # exhausted. Never shorter than the configured sleep.
  sleep_for="$SLEEP_SECONDS"
  if grep -q '"all_exhausted": true' state/search-status.json 2>/dev/null; then
    sleep_for=$(( SLEEP_SECONDS * EXHAUSTED_BACKOFF ))
    echo "[$(date -Is)] search exhausted on every ant; backing off to ${sleep_for}s"
  fi

  echo "[$(date -Is)] sleeping ${sleep_for}s"
  sleep "$sleep_for"
done
