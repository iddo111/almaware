#!/usr/bin/env bash
# Robust RESIDENT launcher for the ALMAWARE babble daemon.
#
# Why this exact form: a non-interactive `ssh host '... &'` returns immediately and
# its process group gets SIGHUP'd on session close, which KILLS a naively-detached
# child (the old `setsid bash -c "exec ... &"` died seconds after launch — it served
# briefly then vanished, leaving a port that refuses connections). The reliable fix
# is `nohup setsid <python> ... < /dev/null &` run from THIS SCRIPT FILE (not inline),
# so the daemon is fully detached from the SSH session and immune to SIGHUP.
#
# Idempotent: if a healthy daemon is already serving the port, it does nothing.
#
# Usage:  babble_run.sh <ROOT> <PORT> <PYTHON>
#   e.g.  babble_run.sh ~/eran-vocal 8791 ~/eran/.venv/bin/python
set -u
ROOT="${1:?root}"; PORT="${2:?port}"; PY="${3:?python}"
ROOT="${ROOT/#\~/$HOME}"; PY="${PY/#\~/$HOME}"

cd "$ROOT" || { echo "no such root: $ROOT"; exit 1; }
mkdir -p "$ROOT/logs"

# already serving? (HTTP 200 from /health) -> leave it alone
if curl -s --max-time 3 "http://127.0.0.1:${PORT}/health" | grep -q '"ready"'; then
  echo "already-up:${PORT}"
  exit 0
fi

# kill any stale instance for THIS root/port (match the full arg so we don't nuke siblings)
pkill -f "babble_daemon.py --root $ROOT" 2>/dev/null
sleep 1

# fully-detached launch: nohup + setsid + stdin from /dev/null. Survives SSH close.
nohup setsid "$PY" "$ROOT/babble_daemon.py" --root "$ROOT" --port "$PORT" \
      >> "$ROOT/logs/babble_daemon.log" 2>&1 < /dev/null &
disown 2>/dev/null || true
echo "launched:${PORT}"
