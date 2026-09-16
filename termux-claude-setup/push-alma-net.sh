#!/usr/bin/env bash
# push-alma-net.sh — installs alma-net.sh into Termux on the S26 and wires it (widget tap, every Termux open, boot dir).
# Run from the PC (Git Bash):  bash D:/CLAUDE/termux-claude-setup/push-alma-net.sh
# Transport, in order:  (1) ssh to Termux sshd :8022 over Tailscale (<tailnet-ip>) or LAN (<lan-ip>)
#                       (2) adb (wireless debugging) — types the script into Termux as base64, no storage permission needed
# Over adb it ALSO grants Termux WRITE_SECURE_SETTINGS, which is what lets alma-net.sh turn wireless debugging back on.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$HERE/alma-net.sh"
TS_IP="${TS_IP:-<tailnet-ip>}"; LAN_IP="${LAN_IP:-<lan-ip>}"
USER_="${TERMUX_USER:-u0_a415}"   # Termux sshd ignores the user name; any name works

INSTALL_CMDS='set -e; mkdir -p ~/bin ~/.shortcuts ~/.termux/boot
mv -f ~/alma-net.sh ~/bin/alma-net.sh; chmod +x ~/bin/alma-net.sh
printf "#!/data/data/com.termux/files/usr/bin/bash\nexec ~/bin/alma-net.sh\n" > ~/.shortcuts/ALMA-NET.sh; chmod +x ~/.shortcuts/ALMA-NET.sh
cp -f ~/.shortcuts/ALMA-NET.sh ~/.termux/boot/00-alma-net.sh; chmod +x ~/.termux/boot/00-alma-net.sh
grep -q "alma-net.sh" ~/.bashrc 2>/dev/null || printf "\n# ALMA-NET: keep the phone reachable (2026-09-11)\n[ -x ~/bin/alma-net.sh ] && (~/bin/alma-net.sh >/dev/null 2>&1 &)\n" >> ~/.bashrc
~/bin/alma-net.sh; echo INSTALL_DONE'

open_port() { timeout 4 bash -c "echo > /dev/tcp/$1/$2" 2>/dev/null; }

# ---------- 1. ssh path ----------
for H in "$TS_IP" "$LAN_IP"; do
  if open_port "$H" 8022; then
    echo "[ssh] phone sshd reachable at $H:8022"
    if scp -P 8022 -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=accept-new "$SRC" "$USER_@$H:alma-net.sh" \
       && ssh -p 8022 -o BatchMode=yes -o ConnectTimeout=8 "$USER_@$H" "$INSTALL_CMDS"; then
      echo "[ssh] installed via $H"; SSH_OK=1; break
    else
      echo "[ssh] $H answered but scp/ssh failed (key not authorized? password auth?) — falling back to adb"
    fi
  fi
done

# ---------- 2. adb path ----------
if adb get-state >/dev/null 2>&1; then
  echo "[adb] attached: $(adb get-serialno)"
  echo "[adb] granting WRITE_SECURE_SETTINGS to com.termux (lets alma-net.sh re-enable wireless debugging)"
  adb shell pm grant com.termux android.permission.WRITE_SECURE_SETTINGS && echo "[adb] granted"
  adb shell settings put global adb_wifi_enabled 1
  if [ -z "${SSH_OK:-}" ]; then
    echo "[adb] no ssh — typing the script into Termux as base64 (takes ~20 s)"
    B64=$(base64 -w0 "$SRC")
    adb shell am start -n com.termux/.app.TermuxActivity >/dev/null; sleep 4
    adb shell input text "echo%s$B64%s|%sbase64%s-d%s>%s~/alma-net.sh%s&&%sbash%s-c%s'$(printf %s "$INSTALL_CMDS" | tr '\n' ';' | sed "s/ /%s/g; s/'/'\\\\''/g")'"
    adb shell input keyevent 66
    sleep 8
  fi
else
  echo "[adb] not attached — WRITE_SECURE_SETTINGS NOT granted. When wireless debugging is on: adb shell pm grant com.termux android.permission.WRITE_SECURE_SETTINGS"
fi

# ---------- 3. verify ----------
sleep 3
for H in "$TS_IP" "$LAN_IP"; do
  if open_port "$H" 8022; then
    echo "[verify] sshd :8022 OPEN at $H"
    ssh -p 8022 -o BatchMode=yes -o ConnectTimeout=8 "$USER_@$H" 'tail -12 ~/alma-net.log; ls -l ~/.shortcuts/ALMA-NET.sh ~/.termux/boot/00-alma-net.sh' 2>/dev/null
    exit 0
  fi
done
echo "[verify] sshd :8022 not reachable yet — open Termux on the phone once (or tap the ALMA-NET widget) and re-run"
exit 1
