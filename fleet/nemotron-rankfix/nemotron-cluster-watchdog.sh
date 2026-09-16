#!/usr/bin/env bash
set -u

STATE_DIR=/var/lib/nemotron-cluster-watchdog
STATUS_FILE="$STATE_DIR/status.json"
FAIL_FILE="$STATE_DIR/consecutive_failures"
RESTART_FILE="$STATE_DIR/last_restart_epoch"
LOG_FILE=/var/log/nemotron-cluster-watchdog.log
MAX_FAILURES=3
COOLDOWN_SECONDS=1800
API_CONTAINER=nemotron-cluster
API_LAUNCHER=/usr/local/sbin/nemotron-cluster-start

mkdir -p "$STATE_DIR"
now_epoch=$(date +%s)
now_iso=$(date -Is)
failures=$(cat "$FAIL_FILE" 2>/dev/null || printf '0')
last_restart=$(cat "$RESTART_FILE" 2>/dev/null || printf '0')

# Report competing runtimes, but never stop or delete them. Ray/vLLM Python
# workers are expected and intentionally excluded.
competing=$(ps -eo comm,args | grep -Ei '(^|/)(ollama|llama-server)|train(er|ing)' | grep -Ev 'grep|nemotron_cluster_watchdog' | head -20 || true)
if [[ -n "$competing" ]]; then
  competing_state=detected
else
  competing_state=none
fi

health_body=$(mktemp)
http_code=$(curl -sS --max-time 120 -o "$health_body" -w '%{http_code}' \
  -H 'Content-Type: application/json' \
  -d '{"model":"nvidia/nemotron-3-super","messages":[{"role":"system","content":"Return NEMOTRON_OK in the final answer. Do not explain."},{"role":"user","content":"Health check."}],"max_tokens":96,"temperature":0}' \
  http://127.0.0.1:8000/v1/chat/completions 2>/dev/null || printf '000')
body=$(tr '\n' ' ' < "$health_body" | head -c 1000)
rm -f "$health_body"

if [[ "$http_code" == 200 && "$body" == *NEMOTRON_OK* ]]; then
  failures=0
  state=healthy
  action=none
else
  failures=$((failures + 1))
  state=unhealthy
  action=none
  if (( failures >= MAX_FAILURES )); then
    if (( now_epoch - last_restart >= COOLDOWN_SECONDS )); then
      if docker container inspect "$API_CONTAINER" >/dev/null 2>&1; then
        docker restart "$API_CONTAINER" >>"$LOG_FILE" 2>&1 || true
        action=api_container_restarted
      elif [[ -x "$API_LAUNCHER" ]]; then
        "$API_LAUNCHER" >>"$LOG_FILE" 2>&1 || true
        action=api_container_recreated_by_launcher
      else
        action=api_container_missing_no_launcher
      fi
      if [[ "$action" != api_container_missing_no_launcher ]]; then
        printf '%s\n' "$now_epoch" > "$RESTART_FILE"
        failures=0
      fi
    else
      action=cooldown_no_restart
    fi
  fi
fi
printf '%s\n' "$failures" > "$FAIL_FILE"

python3 - "$STATUS_FILE" "$now_iso" "$state" "$http_code" "$failures" "$action" "$competing_state" "$body" <<'PY'
import json, sys
path, checked_at, state, http_code, failures, action, competing, detail = sys.argv[1:]
with open(path, "w", encoding="utf-8") as f:
    json.dump({
        "checked_at": checked_at,
        "state": state,
        "http_code": http_code,
        "consecutive_failures": int(failures),
        "action": action,
        "competing_gpu_consumers": competing,
        "detail": detail,
        "policy": {"max_failures": 3, "restart_cooldown_seconds": 1800},
    }, f, ensure_ascii=False, indent=2)
PY
printf '%s state=%s http=%s failures=%s action=%s competing=%s\n' \
  "$now_iso" "$state" "$http_code" "$failures" "$action" "$competing_state" >> "$LOG_FILE"
