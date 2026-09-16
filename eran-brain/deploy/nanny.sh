#!/bin/bash
# nanny.sh — checks the REAL outputs (health:ok != working), every 10 minutes.
#   1. newest metrics line younger than 15 minutes
#   2. state file integrity (brain.json.gz gunzips to valid JSON)
#   3. the observation window answers on :8820
# Any failure -> systemctl --user restart of the sick organ + one log line.
set -u
HOME_DIR="${HOME}"
BASE="${HOME_DIR}/eran-brain"
METRICS="${BASE}/state/metrics.jsonl"
BRAIN="${BASE}/state/brain.json.gz"
LOG="${BASE}/state/nanny.log"
STAMP="$(date -Is)"
PROBLEMS=""

# 1. metrics freshness (the life loop writes a line every beat)
if [ -f "${METRICS}" ]; then
    AGE=$(( $(date +%s) - $(stat -c %Y "${METRICS}") ))
    if [ "${AGE}" -gt 900 ]; then
        PROBLEMS="${PROBLEMS} metrics-stale(${AGE}s)"
    fi
else
    PROBLEMS="${PROBLEMS} metrics-missing"
fi

# 2. brain file integrity
if [ -f "${BRAIN}" ]; then
    if ! python3 -c "import gzip,json,sys; json.load(gzip.open('${BRAIN}','rt'))" 2>/dev/null; then
        PROBLEMS="${PROBLEMS} brain-corrupt"
    fi
fi

# 3. the window answers
if ! curl -sf -m 5 "http://127.0.0.1:8820/" >/dev/null 2>&1; then
    PROBLEMS="${PROBLEMS} serve-silent"
    systemctl --user restart eranb-serve.service
fi

if echo "${PROBLEMS}" | grep -q "metrics"; then
    systemctl --user restart eranb-life.service
fi

if [ -n "${PROBLEMS}" ]; then
    echo "${STAMP} SICK:${PROBLEMS} -> restarted" >> "${LOG}"
else
    echo "${STAMP} ok (real outputs checked, not liveness)" >> "${LOG}"
fi
exit 0
