# WhatsApp + Dispatch — שמירה על חיבור קבוע ב-A70
# WhatsApp + Dispatch — Permanent Background Fix for A70

> **Device:** Samsung A70 (`SM-A705FN`), Android 11, Termux `u0_a688`
> **Context:** dispatch-fix bridge is already installed (`D:\CLAUDE\dispatch-fix\`). Tailscale active on both PC and A70. This guide addresses keeping WhatsApp *and* the dispatch bridge alive permanently — even when the screen turns off or the phone reboots.

---

## חלק א: הבעיה — למה אפליקציות מתות בלילה
## Part A: The Problem — Why Apps Die in the Background

Android 11 on Samsung (One UI) aggressively kills background processes via:
1. **Adaptive Battery** — app-specific sleep if not whitelisted
2. **App power management** — "Put unused apps to sleep"
3. **Doze mode** — all wakelocks suspended when screen off for extended periods
4. **Termux specifically** — dies when the Android system reclaims RAM unless a foreground notification is active

---

## חלק ב: תיקון WhatsApp — 4 שלבים, עשה פעם אחת
## Part B: WhatsApp Fix — 4 Steps, Done Once

### שלב 1 / Step 1 — Whitelist WhatsApp from battery optimization

**On A70:**
```
Settings → Apps → WhatsApp → Battery → Battery optimization
→ Select "Don't optimize" (לא לבצע אופטימיזציה)
```

Or via ADB from PC (if A70 is ADB-connected):
```powershell
adb -s <lan-ip>:40723 shell dumpsys deviceidle whitelist +com.whatsapp
```

### שלב 2 / Step 2 — Allow background data for WhatsApp

```
Settings → Apps → WhatsApp → Mobile data → Background data: ON
Settings → Apps → WhatsApp → Mobile data → Unrestricted data: ON
```

Via ADB:
```powershell
adb -s <lan-ip>:40723 shell cmd appops set com.whatsapp RUN_IN_BACKGROUND allow
adb -s <lan-ip>:40723 shell cmd appops set com.whatsapp RUN_ANY_IN_BACKGROUND allow
```

### שלב 3 / Step 3 — Lock WhatsApp in Recent Apps (screen-lock pinning)

1. Open WhatsApp
2. Press the Recents button (square)
3. Long-press the WhatsApp card
4. Tap the lock icon (🔒) that appears

This prevents One UI from sweeping WhatsApp when memory is reclaimed.

### שלב 4 / Step 4 — Disable "Auto-restart apps" Samsung feature (optional but helpful)

```
Settings → Device care → Battery → Background usage limits
→ "Put unused apps to sleep": make sure WhatsApp is NOT listed
→ "Auto-disable unused apps": OFF
→ "Optimize settings": OFF
```

---

## חלק ג: תיקון Termux / Dispatch Bridge — שמירה על החיבור אחרי אתחול
## Part C: Termux / Dispatch Bridge — Persistent After Reboot

### שלב 1 / Step 1 — Tailscale Always-On VPN (CRITICAL — do this once)

Without this, Tailscale on the A70 does NOT restart after reboot:

```
Settings → Connections → More connection settings → VPN
→ Tap the gear icon next to "Tailscale"
→ Toggle: Always-on VPN → ON
```

Verify (from PC):
```powershell
& 'C:\Program Files\Tailscale\tailscale.exe' status | findstr a70
# Expected: <tailnet-ip>  a70  iddo111@  android  ...
```

### שלב 2 / Step 2 — Install Termux:Boot (lets Termux scripts run at boot)

Install from F-Droid (same source as your Termux):
```
https://f-droid.org/packages/com.termux.boot/
```

After installing, open the Termux:Boot app ONCE — this registers the boot trigger.

Scripts placed in `~/.termux/boot/` will run automatically at every boot.

### שלב 3 / Step 3 — Verify the bridge boot script exists

The bridge auto-start script should already be at `~/.termux/boot/00-bridge.sh`.
Check inside Termux:
```bash
ls -la ~/.termux/boot/
cat ~/.termux/boot/00-bridge.sh
```

If missing, recreate it (run inside Termux on A70):
```bash
mkdir -p ~/.termux/boot
cat > ~/.termux/boot/00-bridge.sh << 'EOF'
#!/data/data/com.termux/files/usr/bin/bash
# Auto-start dispatch bridge on boot
sleep 10
nohup python ~/dispatch-bridge/a70-bridge.py >> ~/dispatch-bridge/bridge.log 2>&1 &
EOF
chmod +x ~/.termux/boot/00-bridge.sh
```

### שלב 4 / Step 4 — Keep Termux alive with a foreground notification

Run inside Termux:
```bash
# Create a persistent foreground service wrapper (prevents Termux from being killed)
cat > ~/bin/keep-alive.sh << 'EOF'
#!/data/data/com.termux/files/usr/bin/bash
# Show a persistent notification so Android keeps Termux in foreground
termux-notification \
  --id 9999 \
  --title "Dispatch Bridge" \
  --content "Bridge active — tap to open Termux" \
  --ongoing \
  --action "am start com.termux/.HomeActivity" &
# Keep the shell alive
while true; do
  sleep 300
  # Re-ping bridge to confirm alive
  curl -s http://localhost:18181/ping > /dev/null 2>&1 || \
    nohup python ~/dispatch-bridge/a70-bridge.py >> ~/dispatch-bridge/bridge.log 2>&1 &
done
EOF
chmod +x ~/bin/keep-alive.sh
```

Add to boot script:
```bash
echo "nohup bash ~/bin/keep-alive.sh >> ~/dispatch-bridge/keepalive.log 2>&1 &" \
  >> ~/.termux/boot/00-bridge.sh
```

### שלב 5 / Step 5 — Whitelist Termux from battery optimization

```powershell
# From PC via ADB:
adb -s <lan-ip>:40723 shell dumpsys deviceidle whitelist +com.termux
adb -s <lan-ip>:40723 shell cmd appops set com.termux RUN_IN_BACKGROUND allow
adb -s <lan-ip>:40723 shell cmd appops set com.termux RUN_ANY_IN_BACKGROUND allow
```

Or on the phone:
```
Settings → Apps → Termux → Battery → Battery optimization → Don't optimize
```

---

## חלק ד: אימות — בדיקה שהכל עובד
## Part D: Verification

### After applying fixes, reboot the A70 and test:

```powershell
# From PC — wait ~90 sec after reboot, then:

# 1. Check Tailscale sees A70
& 'C:\Program Files\Tailscale\tailscale.exe' status | findstr a70

# 2. Ping the bridge
curl.exe -s --max-time 5 http://<tailnet-ip>:18181/ping
# Expected: pong

# 3. Send a test dispatch
powershell.exe -ExecutionPolicy Bypass -File D:\CLAUDE\dispatch-fix\bin\dispatch-cli.ps1 -Msg "Reboot survival test"
# Expected: notification on A70 within 5 sec
```

From Termux on A70:
```bash
# Check bridge is running
pgrep -a python | grep a70-bridge
# Expected: PID + path

# Check bridge log
tail -20 ~/dispatch-bridge/bridge.log
```

---

## חלק ה: טבלת סיכום — מה עושה מה
## Part E: Summary Table

| Component | Kept alive by | Auto-start after reboot |
|---|---|---|
| WhatsApp | Battery whitelist + recents lock | YES (FCM wakes it) |
| Tailscale on A70 | Always-On VPN setting | YES after enabling |
| Termux | Foreground notification + battery whitelist | YES via Termux:Boot |
| a70-bridge.py | `~/.termux/boot/00-bridge.sh` + keep-alive watchdog | YES (requires Termux:Boot installed) |
| Bot-A70Keeper (PC side) | supervisor.ps1 via KarmaSentry in HKCU\Run | YES (Windows auto-start) |

---

## בעיות נפוצות / Common Issues

| Symptom | Cause | Fix |
|---|---|---|
| Bridge ping fails after reboot | Termux:Boot not installed | Install from F-Droid, open once |
| Tailscale shows A70 offline | Always-On VPN not set | Step C-1 above |
| WhatsApp notifications delayed | Adaptive battery active | Steps B-1 through B-4 |
| Bridge running but WA notifications muted | DND on, or channel importance reset | `adb shell cmd notification get-allow-dnd com.whatsapp` |

---

*Created 2026-05-02. Based on context from [`D:\CLAUDE\dispatch-fix\RUNBOOK.md`](file:///D:/CLAUDE/dispatch-fix/RUNBOOK.md) and [`D:\CLAUDE\dispatch-fix\BLOCKED_post_reboot_unlock.md`](file:///D:/CLAUDE/dispatch-fix/BLOCKED_post_reboot_unlock.md).*
