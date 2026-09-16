#!/usr/bin/env bash
set -euo pipefail

mode="${1:-}"
qwen_unit="qwen3-coder-480b.service"
grok_unit="grok1-preserved.service"
qwen_first="/home/eran1/models/Qwen3-Coder-480B-A35B-Instruct-GGUF/Q4_K_M/Qwen3-Coder-480B-A35B-Instruct-Q4_K_M-00001-of-00006.gguf"

wait_http() {
  local url="$1"
  local attempts="${2:-180}"
  for ((i=1; i<=attempts; i++)); do
    if curl --fail --silent --max-time 3 "$url" >/dev/null; then
      return 0
    fi
    sleep 5
  done
  return 1
}

stop_manual_grok_head() {
  mapfile -t pids < <(pgrep -f '^/home/eran1/llama.cpp/build/bin/llama-server .*grok-1-Q6_K-merged.gguf' || true)
  if ((${#pids[@]} == 0)); then
    return 0
  fi
  printf 'Stopping preserved manual Grok head PID(s): %s\n' "${pids[*]}"
  kill -TERM "${pids[@]}"
  for _ in {1..24}; do
    if ! kill -0 "${pids[0]}" 2>/dev/null; then
      return 0
    fi
    sleep 5
  done
  echo 'Grok head did not stop after 120 seconds; refusing SIGKILL.' >&2
  return 1
}

case "$mode" in
  qwen)
    test -s "$qwen_first"
    systemctl --user stop "$grok_unit" 2>/dev/null || true
    stop_manual_grok_head
    systemctl --user start "$qwen_unit"
    wait_http 'http://127.0.0.1:8081/health' 360
    sudo -n tailscale serve --bg --yes --https=8448 8081 >/dev/null 2>&1 || \
      echo 'Warning: Qwen is healthy, but Tailscale Serve 8448 could not be configured.' >&2
    echo 'Qwen3 Coder health is ready on http://127.0.0.1:8081/health'
    ;;
  grok)
    systemctl --user stop "$qwen_unit" 2>/dev/null || true
    systemctl --user start "$grok_unit"
    wait_http 'http://127.0.0.1:8080/health' 360
    sudo -n tailscale serve --https=8448 off >/dev/null 2>&1 || true
    echo 'Grok-1 health is ready on http://127.0.0.1:8080/health'
    ;;
  status)
    systemctl --user --no-pager --full status "$qwen_unit" "$grok_unit" || true
    ;;
  *)
    echo 'Usage: switch-model.sh qwen|grok|status' >&2
    exit 2
    ;;
esac
