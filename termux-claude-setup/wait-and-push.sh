#!/usr/bin/env bash
# wait-and-push.sh — waits for the S26 to come back (adb / ssh :8022 / Tailscale), then installs ALMA-NET on it.
# Steps, each done once, in whatever order the phone allows:
#   GRANTED   adb: pm grant com.termux WRITE_SECURE_SETTINGS  (lets alma-net.sh re-enable wireless debugging)
#   TYPED     adb: opens Termux and types one line that authorizes the PC's ssh key + starts sshd
#   INSTALLED ssh: push-alma-net.sh installs ~/bin/alma-net.sh, widget, boot dir, .bashrc hook, runs it
# Prints one line per step (Monitor events). Exits 0 on DONE, 1 on timeout (1 h).
LAN=${LAN_IP:-<lan-ip>}; TS=${TS_IP:-<tailnet-ip>}
PUB=$(cat ~/.ssh/id_ed25519.pub); B64=$(printf '%s\n' "$PUB" | base64 -w0)
open_port() { timeout 3 bash -c "echo > /dev/tcp/$1/$2" 2>/dev/null; }
adb_ok() {
  # the phone may show up twice (mdns name + ip:port) -> "more than one device"; pin ANDROID_SERIAL to the ip:port entry
  local s; s=$(adb devices 2>/dev/null | tr -d '\r' | awk -v lan="$LAN" '$2=="device" && index($1,lan){print $1; exit}')
  [ -z "$s" ] && s=$(adb devices 2>/dev/null | tr -d '\r' | awk '$2=="device"{print $1; exit}')
  [ -n "$s" ] && export ANDROID_SERIAL="$s"
  [ -n "$s" ]
}
granted=0; keyed=0; installed=0; last=""
end=$((SECONDS + 3600))
while [ $SECONDS -lt $end ]; do
  if ! adb_ok; then
    P=$(adb mdns services 2>/dev/null | tr -d '\r' | grep -oE "$LAN:[0-9]+" | head -1)
    [ -n "$P" ] && adb connect "$P" >/dev/null 2>&1
  fi
  state="adb=$(adb_ok && echo on || echo off) ssh=$( (open_port $TS 8022 || open_port $LAN 8022) && echo open || echo closed)"
  [ "$state" != "$last" ] && { echo "phone: $state"; last=$state; }

  if adb_ok && [ $granted = 0 ]; then
    if adb shell pm grant com.termux android.permission.WRITE_SECURE_SETTINGS >/dev/null 2>&1; then
      granted=1; echo "GRANTED: WRITE_SECURE_SETTINGS -> com.termux"
    fi
    adb shell settings put global adb_wifi_enabled 1 >/dev/null 2>&1
  fi
  # Termux:Boot (Iddo approved the download 06:01; APK sha256-verified in the scratchpad) — install once, launch once, exempt from doze
  APK="$TERMUX_BOOT_APK"
  if adb_ok && [ "${booted:-0}" = 0 ] && [ -n "$APK" ] && [ -f "$APK" ] && [ "${boot_tries:-0}" -lt 2 ] && [ $SECONDS -ge "${boot_next:-0}" ]; then
    if adb shell pm list packages 2>/dev/null | tr -d '\r' | grep -q '^package:com.termux.boot$'; then
      booted=1; echo "BOOT: com.termux.boot already installed"
    else
      res=$(MSYS_NO_PATHCONV=1 timeout 90 adb install -r "$APK" 2>&1 | tr -d '\r' | tail -1)
      if echo "$res" | grep -q Success; then booted=1; echo "BOOT: Termux:Boot v0.8.1 installed"
      else boot_tries=$((${boot_tries:-0}+1)); boot_next=$((SECONDS+120)); echo "BOOT: install refused ($res) — try $boot_tries/2; Samsung Auto Blocker / Play Protect must allow it"; fi
    fi
    if [ "$booted" = 1 ]; then
      adb shell monkey -p com.termux.boot -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1 && echo "BOOT: app launched once (required for the boot receiver)"
      adb shell dumpsys deviceidle whitelist +com.termux.boot >/dev/null 2>&1 && echo "BOOT: exempted from battery optimization"
    fi
  fi
  if adb_ok && [ $keyed = 0 ]; then
    adb shell am start -n com.termux/.app.TermuxActivity >/dev/null 2>&1; sleep 5
    if adb shell "input text 'mkdir%s-p%s~/.ssh;echo%s$B64|base64%s-d>>~/.ssh/authorized_keys;chmod%s600%s~/.ssh/authorized_keys;pgrep%s-x%ssshd||sshd'" >/dev/null 2>&1 \
       && adb shell input keyevent 66 >/dev/null 2>&1; then
      keyed=1; echo "TYPED: PC ssh key -> ~/.ssh/authorized_keys + sshd (in Termux)"; sleep 5
    fi
  fi
  if [ $installed = 0 ]; then
    for H in $TS $LAN; do
      if open_port $H 8022; then
        out=$(bash "$(dirname "$0")/push-alma-net.sh" 2>&1)
        echo "$out" | grep -E "installed via|answered but|sshd :8022 OPEN|adb wifi|tailscale:|sshd:|wake-lock|state:" | sed 's/^/  push: /'
        if ssh -p 8022 -o BatchMode=yes -o ConnectTimeout=6 -o StrictHostKeyChecking=accept-new u0_a415@$H 'test -x ~/bin/alma-net.sh && echo INSTALLED' 2>/dev/null | grep -q INSTALLED; then
          installed=1; echo "INSTALLED: alma-net.sh + widget + boot + .bashrc hook via $H"
        fi
        break
      fi
    done
  fi
  if [ $installed = 1 ] && [ $granted = 1 ]; then echo "DONE: granted + installed"; exit 0; fi
  sleep 5
done
echo "TIMEOUT: granted=$granted keyed=$keyed installed=$installed"; exit 1
