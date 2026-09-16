#!/usr/bin/env bash
# SARID / שריד — install the slow flame on eran3 and light it.
#
# BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY.
#
# Daemon law, obeyed: systemd --user + linger, so the organ survives logout
# without a stray nohup orphan nobody can find. NEVER eran1 — guards.py
# refuses it by name before this script's unit can start.
#
#   ./RUN-SARID.sh install     write + enable + start the unit
#   ./RUN-SARID.sh status      is it alive, and what did it last say
#   ./RUN-SARID.sh stop        STOP file: halts MID-ROUND at a stage boundary
#   ./RUN-SARID.sh go          remove the STOP file and resume
#   ./RUN-SARID.sh prune       delete the whole shoot. Reaches nothing else.
set -euo pipefail

ROOT="${SARID_ROOT:-$HOME/sarid-shoot}"
CODE="${SARID_CODE:-$HOME/sarid/safa-achat}"
DATA="${SARID_DATA:-$HOME/sarid-data/nel/northeuralex-4.0}"
PY="${SARID_PY:-$HOME/sarid-venv/bin/python}"
UNIT="$HOME/.config/systemd/user/sarid.service"

case "${1:-status}" in

install)
  mkdir -p "$(dirname "$UNIT")" "$ROOT"
  cat > "$UNIT" <<EOF
[Unit]
Description=SARID / שריד — the שפה אחת organ (slow flame)
After=default.target

[Service]
Type=simple
WorkingDirectory=$CODE
Environment=PYTHONIOENCODING=utf-8
Environment=PYTHONUNBUFFERED=1
# nice: SARID is a guest on this box and never competes with the fleet's work
ExecStart=/usr/bin/nice -n 15 $PY -u $CODE/sarid/loop.py \\
    --data $DATA --root $ROOT --rounds 0 --sleep 60 --perm 120
# on-failure, NOT always. The STOP file makes the loop exit CLEANLY (0), and
# Restart=always revived it 30 seconds later to halt again - a restart loop
# that made `stop` mean "churn forever" instead of "stop". Measured live on
# 2026-09-01: systemctl reported `activating` in a cycle. With on-failure a
# clean STOP stays stopped, and a real crash still comes back.
Restart=on-failure
RestartSec=30

[Install]
WantedBy=default.target
EOF
  loginctl enable-linger "$USER" 2>/dev/null || true
  systemctl --user daemon-reload
  systemctl --user enable --now sarid.service
  sleep 3
  systemctl --user --no-pager status sarid.service | head -12
  ;;

status)
  systemctl --user --no-pager status sarid.service 2>/dev/null | head -12 || \
    echo "unit not installed"
  echo "--- last rounds ---"
  tail -n 5 "$ROOT/journal.jsonl" 2>/dev/null || echo "(no journal yet)"
  echo "--- state ---"
  cat "$ROOT/state.json" 2>/dev/null | head -8 || echo "(no state yet)"
  ;;

stop)
  touch "$ROOT/STOP"
  echo "STOP file written. The organ halts at the next stage boundary,"
  echo "mid-round if need be: $ROOT/STOP"
  ;;

go)
  rm -f "$ROOT/STOP"
  systemctl --user restart sarid.service
  echo "STOP removed, service restarted. It resumes from checkpoint —"
  echo "it never starts over."
  ;;

prune)
  systemctl --user disable --now sarid.service 2>/dev/null || true
  rm -f "$UNIT"
  systemctl --user daemon-reload 2>/dev/null || true
  rm -rf "$ROOT"
  echo "pruned: $ROOT is gone, and nothing outside it was ever written."
  ;;

*)
  echo "usage: $0 {install|status|stop|go|prune}" >&2
  exit 2
  ;;
esac
