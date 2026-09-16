# dispatch-fix RUNBOOK

How to operate, debug, and roll back the PC <-> A70 dispatch bridge.

Authored 2026-04-27 by dispatch-fix agent.
See ARCHITECTURE.md for design.

---

## Daily operation (zero-touch path)

Iddo just uses the apps:

- **Type to A70 from PC**: open the Claude desktop, send a chat. The Android Claude app gets a push notification (FCM via claude.ai cloud). Channel `completion` (importance 4 = HIGH) shows a banner.
- **Type to PC from A70**: open the Claude Android app, send a chat. The PC Claude desktop syncs the conversation.

That covers Goal #1 — already working at 2026-04-27 06:38.

For programmatic dispatch (Claude on PC running scripts, agents pushing notifications, etc.), use the Layer 2 bridge below.

---

## Layer 2 bridge: Tailscale + tiny HTTP

### Send PC -> A70

```powershell
powershell.exe -ExecutionPolicy Bypass -File D:\CLAUDE\dispatch-fix\bin\dispatch-cli.ps1 -Msg "Hello from PC" -Title "Claude PC"
```

Or run an arbitrary adb shell command on A70:

```powershell
powershell.exe -ExecutionPolicy Bypass -File D:\CLAUDE\dispatch-fix\bin\dispatch-cli.ps1 -Cmd "am start -n com.anthropic.claude/.mainactivity.MainActivity"
```

The CLI tries Tailscale first (`POST http://<tailnet-ip>:18181/notify`); on failure it falls back to ADB-direct (`adb shell cmd notification post`). Both paths show a notification on A70.

### Send A70 -> PC

In Termux on the A70:

```bash
pc-msg "I'm at the cafe"
pc-msg --title "alert" "battery dying"
echo "stdin works too" | pc-msg
```

This POSTs to `http://<tailnet-ip>:18180/inbox` (PC Tailscale IP; read at runtime from `~/dispatch-bridge/pc-ip` on the A70). The PC listener appends to `D:\CLAUDE\dispatch-fix\state\pc-inbox.jsonl` and tries to pop a Windows toast.

### Tail the PC inbox

```powershell
Get-Content D:\CLAUDE\dispatch-fix\state\pc-inbox.jsonl -Wait
# or via HTTP from anywhere on the tailnet:
curl.exe http://<tailnet-ip>:18180/tail
```

---

## Layer 3 fallback (LAN-only, no internet/tailscale)

When Tailscale is down, the ADB tunnel still works:

```powershell
# Forward A70's listen port back to PC's localhost so A70 can POST to localhost:18180
adb -s <lan-ip>:40723 reverse tcp:18180 tcp:18180
adb -s <lan-ip>:40723 forward tcp:18181 tcp:18181
```

Then on A70 inside Termux, `pc-msg` automatically retries `localhost:18180` if Tailscale fails.

To send PC -> A70 over ADB direct:

```powershell
adb -s <lan-ip>:40723 shell "cmd notification post -S bigtext -t 'Claude PC' tag1 'hello via adb'"
```

`dispatch-cli.ps1 -Msg ...` does this fallback automatically when Tailscale fails.

---

## Persistence

| Component | Auto-start mechanism |
|-----------|----------------------|
| Tailscale (PC) | Windows service "Tailscale", StartType=Automatic |
| Tailscale (A70) | Always-on VPN toggle in Android settings |
| Karma sentry | HKCU\Run\KarmaSentry (logon) |
| supervisor.ps1 | Spawned by karma.ps1 in its 30 s loop |
| Bot-A70Keeper | Inside supervisor.ps1, 60 s cycle |
| Bot-DispatchListenerKeeper | Inside supervisor.ps1, 60 s cycle |
| pc-listener.py (PC inbox) | Spawned by Bot-DispatchListenerKeeper |
| a70-bridge.py (A70 daemon) | `~/.termux/boot/00-bridge.sh` (Termux:Boot package required) |

### Manually restart everything

```powershell
# PC side
Stop-Process -Name python -ErrorAction SilentlyContinue | Where-Object { (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)").CommandLine -match 'pc-listener.py' } | Stop-Process -Force
# Then wait <60s for supervisor to respawn, or:
Start-Process py -ArgumentList '-3.12','D:\CLAUDE\dispatch-fix\bin\pc-listener.py' -WindowStyle Hidden
```

```bash
# A70 side (inside Termux)
pkill -f a70-bridge.py
nohup python ~/dispatch-bridge/a70-bridge.py >> ~/dispatch-bridge/bridge.log 2>&1 &
```

---

## Debug

| Symptom | Check | Fix |
|---------|-------|-----|
| `dispatch-cli` says "BOTH paths failed" | tailscale status; adb devices | `tailscale up`; supervisor's Bot-A70Keeper handles ADB |
| A70 in tailnet but no notify | `curl http://<tailnet-ip>:18181/ping` | Termux:Boot may not have launched bridge — run `bash /sdcard/Download/install-bridge.sh` |
| pc-listener not reachable | `Get-NetTCPConnection -LocalPort 18180 -State Listen` | Bot-DispatchListenerKeeper restarts on next 60 s cycle |
| ADB drops every minute | `adb mdns services` | A70 reboot changed wireless port — Bot-A70Keeper rediscovers via mDNS, but if mDNS is empty, Iddo must re-pair via Settings > Developer options > Wireless debugging |
| Notification text shows but Claude app ignored | tap directly on the notification card; or open Claude manually | this bridge sends Termux notifications — they're informational, not deep-linked into Claude |

### Logs

| Log | Path |
|-----|------|
| Master dispatch log | `D:\CLAUDE\dispatch-fix\dispatch-fix.log` |
| Inbox messages (jsonl) | `D:\CLAUDE\dispatch-fix\state\pc-inbox.jsonl` |
| pc-listener stdout | `D:\CLAUDE\dispatch-fix\state\listener-stdout.log` |
| pc-listener Python log | `D:\CLAUDE\dispatch-fix\state\pc-listener.log` |
| Bot-A70Keeper | `~\.claude\a70-keeper.log` |
| Bot supervisor master | `~\.claude\bot-supervisor.log` |
| A70 bridge daemon | `~/dispatch-bridge/bridge.log` (inside Termux on A70) |

---

## Roll back

To remove all dispatch-fix automation but leave the apps:

```powershell
# 1. Remove HKCU Run entry for Karma (optional; karma is general infra not just dispatch)
# Skip if Iddo wants karma still running.

# 2. Remove Bot-A70Keeper + Bot-DispatchListenerKeeper from supervisor.ps1
notepad C:\Users\<user>\bin\bots\supervisor.ps1
# Delete the two functions and their call sites in the while loop.

# 3. Stop pc-listener
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | ? { $_.CommandLine -match 'pc-listener.py' } | % { Stop-Process -Id $_.ProcessId -Force }

# 4. Remove dispatch-fix tree if desired
Remove-Item -Recurse -Force D:\CLAUDE\dispatch-fix

# 5. On A70, kill the bridge daemon
adb shell am force-stop com.termux  # or in Termux: pkill -f a70-bridge.py

# 6. Tailscale (only if you want to remove): tailscale logout; winget uninstall tailscale.tailscale
```

The Tailscale install + login is **independent value** — it provides ssh/file-share/etc. between Iddo's devices regardless of dispatch-fix. Keeping it costs nothing.

---

## Verification gates (re-runnable)

```powershell
# Gate 1: Claude Android signed in
adb -s <lan-ip>:40723 shell am start -n com.anthropic.claude/.mainactivity.MainActivity
# expected: chat UI appears, mic + send buttons visible

# Gate 2: PC -> A70
powershell.exe -ExecutionPolicy Bypass -File D:\CLAUDE\dispatch-fix\bin\dispatch-cli.ps1 -Msg "gate2 test"
# expected: notification appears on A70 in shade

# Gate 3: A70 -> PC
adb -s <lan-ip>:40723 shell "curl -fsS -X POST -H 'Content-Type: application/json' -d '{\"sender\":\"a70\",\"msg\":\"gate3 test\"}' http://<tailnet-ip>:18180/inbox"
# expected: "ok"; entry appears in pc-inbox.jsonl

# Gate 4: persistence (A70 reboot)
adb -s <lan-ip>:40723 reboot
# wait ~90s
# Bot-A70Keeper should rediscover the new wireless port via mDNS within 60s
adb devices -l
# expected: A70 reappears as "device" within 2 minutes

# Gate 5: supervisor restart survival
Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" | ? { $_.CommandLine -match 'supervisor.ps1' } | % { Stop-Process -Id $_.ProcessId -Force }
# wait 30 s for karma to respawn
Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" | ? { $_.CommandLine -match 'supervisor.ps1' }
# expected: a fresh supervisor PID
```

---

## Known limitations

- **Termux:Boot** is a separate Play Store/F-Droid app. Iddo doesn't have it installed yet. Without it, `~/.termux/boot/00-bridge.sh` does NOT run automatically after a phone reboot — Iddo must launch Termux manually. Workaround: Bot-A70Keeper detects ADB liveness; on reconnect after reboot, it could be extended to push `am start com.termux/.HomeActivity` + run `nohup python ~/dispatch-bridge/a70-bridge.py &`.
- **A70 wireless ADB port changes** every time Wireless Debugging is toggled or the phone reboots, but mDNS rediscovery handles this.
- **Claude desktop on PC** is currently the user-facing surface for Goal #1 — there is no claude.ai HTTP API plumbed in here. If Iddo wants programmatic chat from the PC into the Claude Android app's claude.ai conversation, that requires an Anthropic API integration (separate project).
- **Notifications via this bridge are Termux-namespaced** ("Termux:API" is the source app shown). They do NOT post into the Claude Android app's chat. If Iddo wants real chat-driven notifications, those flow via FCM from claude.ai automatically (Goal #1 path).
