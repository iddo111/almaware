#!/usr/bin/env bash
# Live telemetry poller for the 4 Eran DGX nodes -> status.json
OUT="D:/CLAUDE/eran-dashboard/status.json"
NODES="eran1 eran2 eran3 eran4"

probe(){
  ssh -o ConnectTimeout=6 -o BatchMode=yes "$1" '
    g=$(nvidia-smi --query-gpu=temperature.gpu,utilization.gpu,power.draw --format=csv,noheader,nounits 2>/dev/null | head -1 | tr -d " ")
    load=$(awk "{print \$1}" /proc/loadavg)
    up=$(cut -d. -f1 /proc/uptime)
    m=0; for z in /sys/class/thermal/thermal_zone*/temp; do v=$(cat "$z" 2>/dev/null); [ "${v:-0}" -gt "$m" ] 2>/dev/null && m=$v; done
    h=$(hostname)
    if pgrep -f "train_|gist|proto|comfy" >/dev/null 2>&1; then t=1; else t=0; fi
    echo "$g|$load|$up|$m|$h|$t"
  ' 2>/dev/null
}

while true; do
  ts=$(date +%s)
  json="{\"ts\":$ts,\"nodes\":["
  first=1
  for n in $NODES; do
    line=$(probe "$n")
    [ $first -eq 0 ] && json="$json,"; first=0
    if [ -z "$line" ]; then
      json="$json{\"name\":\"$n\",\"online\":false}"
    else
      IFS='|' read -r g load up m h t <<< "$line"
      gtemp=$(echo "$g" | cut -d, -f1); gutil=$(echo "$g" | cut -d, -f2); gpow=$(echo "$g" | cut -d, -f3)
      soc=$(( ${m:-0} / 1000 ))
      json="$json{\"name\":\"$n\",\"online\":true,\"host\":\"$h\",\"gtemp\":${gtemp:-0},\"gutil\":${gutil:-0},\"gpow\":${gpow:-0},\"soc\":$soc,\"load\":${load:-0},\"up\":${up:-0},\"train\":${t:-0}}"
    fi
  done
  json="$json]}"
  echo "$json" > "$OUT"
  sleep 5
done
