#!/data/data/com.termux/files/usr/bin/bash
# ALMA-NET — keeps the S26 reachable from anywhere (Iddo, 2026-09-11 05:47: "auto wifi connect + auto wifi debug").
# What it does, every time it runs:
#   1. wake-lock            (Termux stays alive with the screen off)
#   2. Wi-Fi on             (Termux:API)
#   3. sshd on :8022        (the PC / fleet reach the phone over LAN or Tailscale)
#   4. Tailscale connect    (broadcast to the Tailscale app; it must be installed + logged in — it is)
#   5. wireless debugging   (settings put global adb_wifi_enabled 1 — works only after the PC ran once:
#                            adb shell pm grant com.termux android.permission.WRITE_SECURE_SETTINGS)
# Where it runs from:  ~/.shortcuts/ALMA-NET.sh (Termux:Widget, one tap)   ·   ~/.bashrc (every Termux open)
#                      ~/.termux/boot/00-alma-net.sh (runs at boot ONLY if the Termux:Boot app is installed)
# Log: ~/alma-net.log

LOG="$HOME/alma-net.log"
ts() { date '+%Y-%m-%d %H:%M:%S'; }
say() { echo "$(ts) $*" | tee -a "$LOG"; }
have() { command -v "$1" >/dev/null 2>&1; }

say "--- alma-net start ($0)"

# 1. wake-lock
if have termux-wake-lock; then termux-wake-lock && say "wake-lock: on"; else say "wake-lock: termux-api missing"; fi

# 2. Wi-Fi on
if have termux-wifi-enable; then termux-wifi-enable true && say "wifi: enable requested"; fi

# 3. sshd
if pgrep -x sshd >/dev/null 2>&1; then say "sshd: already running :8022"
elif have sshd; then sshd && say "sshd: started :8022" || say "sshd: FAILED to start"
else say "sshd: openssh not installed (pkg install openssh)"; fi

# 4. Tailscale up — try termux-am, then the system am
AM=""
if have termux-am; then AM=termux-am; elif [ -x /system/bin/am ]; then AM=/system/bin/am; fi
if [ -n "$AM" ]; then
  if $AM broadcast -a com.tailscale.ipn.CONNECT_VPN -n com.tailscale.ipn/.IPNReceiver >>"$LOG" 2>&1; then
    say "tailscale: CONNECT_VPN sent via $AM"
  else
    $AM start -n com.tailscale.ipn/.MainActivity >>"$LOG" 2>&1 && say "tailscale: app opened via $AM (tap Connect if it is off)"
  fi
else
  say "tailscale: no am command (pkg install termux-am)"
fi

# 5. wireless debugging — MEASURED 2026-09-11 06:30: Termux CANNOT flip it. `settings put` dies in SettingsService
#    (getCurrentUser needs INTERACT_ACROSS_USERS, even with --user 0) and `content` needs app_process, which Termux
#    may not exec. Android also resets adb_wifi_enabled to 0 at every boot. Only a shell-uid helper can do it:
#    Shizuku's rish (if its files were exported into Termux) — try it; otherwise say so once, no stack traces.
if [ -x "$HOME/rish" ] || have rish; then
  RISH=$( [ -x "$HOME/rish" ] && echo "$HOME/rish" || echo rish )
  if echo 'settings put global adb_wifi_enabled 1' | $RISH >>"$LOG" 2>&1; then say "adb wifi: adb_wifi_enabled=1 (via Shizuku rish)"
  else say "adb wifi: rish present but Shizuku not running (it starts only while wireless debugging is on)"; fi
else
  say "adb wifi: cannot be turned on from Termux (Android blocks it); needs a WRITE_SECURE_SETTINGS app (MacroDroid/Tasker) or the toggle in Developer options"
fi

# 6. report (Termux may not read `ip`; use termux-api + a ping to the PC's tailnet IP)
IP=$(termux-wifi-connectioninfo 2>/dev/null | grep -oE '"ip": "[^"]+"' | cut -d'"' -f4)
SSID=$(termux-wifi-connectioninfo 2>/dev/null | grep -oE '"ssid": "[^"]+"' | cut -d'"' -f4)
TS=$(ping -c1 -W2 <tailnet-ip> >/dev/null 2>&1 && echo up || echo down)
say "state: wifi=${SSID:-?} ip=${IP:-none} tailscale=${TS} sshd=$(pgrep -x sshd >/dev/null && echo up || echo down)"
say "--- alma-net end"
