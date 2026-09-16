#!/usr/bin/env bash
set -u

INTERVAL_SECONDS="${INTERVAL_SECONDS:-30}"
STATE_DIR="${STATE_DIRECTORY:-/var/lib/eran-fabric-watchdog}"
STATUS_FILE="${STATE_DIR}/status.txt"

mkdir -p "$STATE_DIR"

read_link() {
  local dev="$1"
  local peer="$2"
  local speed link mtu ping_summary counters
  speed="$(ethtool "$dev" 2>/dev/null | awk -F': ' '/Speed:/{print $2; exit}')"
  link="$(ethtool "$dev" 2>/dev/null | awk -F': ' '/Link detected:/{print $2; exit}')"
  mtu="$(cat "/sys/class/net/${dev}/mtu" 2>/dev/null || printf 'unknown')"
  ping_summary="$(ping -q -c 3 -W 1 -s 8972 -M do "$peer" 2>&1 | tail -n 2 | tr '\n' ' ')"
  counters="$(ethtool -S "$dev" 2>/dev/null | awk '
    /rx_crc_errors_phy:|rx_symbol_err_phy:|rx_discards_phy:|rx_corrected_bits_phy:/ {
      gsub(/^[[:space:]]+/, ""); printf "%s ", $0
    }
  ')"
  printf '%s peer=%s speed=%s link=%s mtu=%s | %s | %s\n' \
    "$dev" "$peer" "${speed:-unknown}" "${link:-unknown}" "$mtu" "$ping_summary" "$counters"
}

while true; do
  now="$(date --iso-8601=seconds)"
  health="$(curl -fsS --max-time 3 http://127.0.0.1:8080/health 2>&1 || true)"
  rpc2="$(ss -Htn state established '( dport = :50052 or sport = :50052 )' 2>/dev/null | grep -c '<fabric-ip>:50052' || true)"
  rpc3="$(ss -Htn state established '( dport = :50052 or sport = :50052 )' 2>/dev/null | grep -c '<fabric-ip>:50052' || true)"
  {
    printf 'updated=%s\n' "$now"
    printf 'grok_health=%s\n' "${health:-unavailable}"
    printf 'rpc_connections dgx2=%s dgx3=%s\n' "$rpc2" "$rpc3"
    read_link enp1s0f0np0 <fabric-ip>
    read_link enp1s0f1np1 <fabric-ip>
  } > "${STATUS_FILE}.tmp"
  mv "${STATUS_FILE}.tmp" "$STATUS_FILE"
  cat "$STATUS_FILE"
  sleep "$INTERVAL_SECONDS"
done
