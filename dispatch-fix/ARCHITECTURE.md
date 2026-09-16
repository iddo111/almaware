# Dispatch architecture (PC <-> A70)

Authored 2026-04-27 by dispatch-fix agent. Frozen before implementation per
`feedback_check_existing_before_creating.md`.

## Goal (4 facets, all four must work)

1. **Claude Android app sign-in + push** — Iddo opens the Claude app on A70, can chat, push notifications arrive.
2. **PC -> A70 dispatch** — PC-side Claude (or any PC script) can send a notification/message that arrives on the A70.
3. **A70 -> PC dispatch** — typing into the Claude Android app reaches PC-side Claude (claude.ai web/desktop). Fallback: typing into a bridge app on A70 reaches a PC daemon.
4. **Persistent across reboots, WiFi changes, IP rotations.**

## Audit summary (2026-04-27 06:38 local)

- A70 = `samsung/a70qxx/a70q` Android 11, API 30, arm64-v8a. Reachable at `<lan-ip>:40723` via wireless ADB (mDNS service `adb-R58MC0KVS0X-QEqIr1._adb-tls-connect._tcp`).
- Claude app `com.anthropic.claude` v1.260423.20 (updated 2026-04-25). MainActivity = `com.anthropic.claude/.mainactivity.MainActivity`. Permissions: `RECORD_AUDIO=granted`, `c2dm.RECEIVE=granted`, channel `completion`+`assist` importance=4 (HIGH). App is signed in (chat UI live, mic active 4h ago).
- Tailscale Android `com.tailscale.ipn` v1.96.4 installed (updated 2026-04-17). PC has NO Tailscale yet -> install in Phase A.
- Termux 0.118.3 + termux-api installed -> can run shell daemons.
- DND state: off (`zen_mode=0`).

Goal #1 is **already PASSED** at audit. Goal #4 is satisfied by Tailscale natively (cross-WiFi mesh).

## Architecture chosen

Three layers, each replacing the previous if available:

### Layer 1 (default success path): Claude.ai cloud round-trip

A70 Claude app and PC's Claude desktop both authenticate to claude.ai backend.
Conversation messages sync via the cloud. **This already works** as proven in audit.

PC -> A70: PC-side Claude posts to a chat -> FCM delivers a notification to A70 (channel `completion`). Iddo sees it.
A70 -> PC: A70 user types in chat -> PC's Claude desktop sees the same conversation thread.

This is the user-facing dispatch. No bridge code required. **Verification: a fresh chat on the PC must produce a visible notification on A70.**

### Layer 2 (always-on bridge): Tailscale tailnet

Both devices join Iddo's existing tailnet. Each has a stable `*.tailnet-XXXX.ts.net` hostname and a 100.x.y.z address that is **WiFi-network-independent** (works on home WiFi, phone hotspot, or LTE, no port-forwarding, no router config).

Use cases:
- **PC arbitrary command -> A70**: PC runs `ssh -p 8022 root@<a70-tailscale-ip>` via Termux SSH and executes anything (`am start`, `dumpsys`, `screencap`, `notify-send`...). This is the dispatch primitive that lets Claude on the PC *programmatically* drive A70 (e.g. push a custom toast, launch an app, run a command).
- **A70 -> PC**: A70 Termux runs a Python sender that POSTs to a tiny PC-side HTTP listener on the tailnet. Iddo can speak/type into Termux (e.g. `pc-msg "hello"`) and it lands in the PC inbox.
- **A70 native notification daemon -> PC**: Termux subscribes to the Android notification stream (via termux-notification-list) and forwards filtered events (e.g. SMS from a specific contact, missed call) to the PC inbox.

Tailscale survives WiFi changes natively. No keepalive bot needed for it.

### Layer 3 (LAN-only fallback): ADB-reverse tunnel

When Tailscale is briefly down (initial bootstrap, app crashed, account expired) but A70 and PC are on the same WiFi:

- `adb -s <lan-ip>:40723 reverse tcp:18181 tcp:18181` makes the PC's port 18181 reachable on A70 as `localhost:18181`.
- A70 Termux scripts can `curl http://localhost:18181/...` to talk to the PC.
- `adb forward tcp:18182 tcp:18182` gives PC a way to reach Termux on A70.
- This requires `adb connect <lan-ip>:40723` to be alive -> hence Bot-A70Keeper.

Layer 3 is the bottom of the stack: it works without internet, without Tailscale auth, as long as both devices are on the same LAN. Bot-A70Keeper keeps it alive.

## Component table

| Component | Where | Owner | Started by |
|-----------|-------|-------|------------|
| Claude desktop | PC | Anthropic | Iddo manually |
| Claude Android | A70 | Anthropic | Iddo manually |
| Tailscale Windows client | PC | Tailscale Inc. | Auto-start (service) |
| Tailscale Android | A70 | Tailscale Inc. | Auto-start (already enabled) |
| Termux SSH (sshd on :8022) | A70 | OSS | A70 boot via Termux:Boot |
| Bot-A70Keeper | PC | this agent | Existing supervisor.ps1 (extension) |
| pc-listener.py (HTTP inbox on :18180) | PC | this agent | Scheduled task |
| termux-bridge.sh (sender CLI on A70) | A70 | this agent | manual / called from Tasker / from Termux shell |
| dispatch-cli.ps1 (PC sender) | PC | this agent | called from Claude Code or any user script |

## Round-trip flows

### Flow A: PC -> A70 notification (most common)

```
Claude on PC runs: dispatch-cli.ps1 -To A70 -Msg "hello from PC"
  -> POST http://<a70-tailscale-ip>:18181/notify   (via tailnet)
  -> Termux's listener.py validates + calls termux-notification --title "Claude PC" --content "hello from PC"
  -> Android shows the notification.
  -> Tap routes to claude.ai chat (or just dismisses).
```

Fallback if Tailscale down: use `adb -s <lan-ip>:40723 shell cmd notification post -S bigtext -t 'Claude PC' Tag1 'hello from PC'` directly.

### Flow B: A70 -> PC text

```
On A70 in Termux: pc-msg "I'm at the cafe"
  -> POST http://<pc-tailscale-ip>:18180/inbox
  -> PC's listener.py appends to D:\CLAUDE\dispatch-fix\pc-inbox.log
  -> Optionally: also calls msg.exe / win10toast to pop a toast on the PC desktop.
```

Fallback if Tailscale down: same POST to `http://localhost:18180` over `adb reverse tcp:18180`.

### Flow C: A70 Claude chat -> PC visible

This is just claude.ai sync. Iddo types in the Android app -> PC's Claude desktop shows the same thread. No bridge code needed. Already works.

### Flow D: PC Claude chat -> A70 notification

Same as Flow C, reverse direction. PC types -> A70 Claude app receives FCM push -> Android notification -> Iddo opens.

## Persistence (gate 4)

- Tailscale: auto-start service on Windows, "Always-on VPN" on Android.
- ADB-over-WiFi: Bot-A70Keeper polls every minute, reconnects on dropout.
- Scheduled tasks (already exist): `Karma` keeps `supervisor.ps1` alive; `supervisor.ps1` runs Bot-A70Keeper inside its loop.
- A70 reboot: Wireless Debugging port changes after reboot. Bot-A70Keeper does mDNS rediscovery, pulls the new port, reconnects.

## Why not...

- **KDE Connect**: requires desktop env + GUI; PC is bare Win11.
- **Pushbullet**: third-party SaaS, deprecation risk, requires sign-up.
- **Tasker + AutoNotification**: paid app, not installed.
- **scrcpy**: display mirroring, not messaging — useful for Iddo to see A70 from PC, separate concern.
- **WhatsApp/Telegram bridge**: requires phone number bot accounts and violates `feedback_no_send_messages.md` if it ever leaks beyond Iddo.

## Files this architecture creates

```
D:\CLAUDE\dispatch-fix\
  ARCHITECTURE.md          (this file)
  RUNBOOK.md               (how to operate / debug / roll back)
  STATUS.md                (live state — updated each phase)
  dispatch-fix.log         (timestamped append-only)
  screenshots\             (proof shots)
  bin\
    dispatch-cli.ps1       (PC -> A70 sender)
    pc-listener.py         (PC inbox HTTP)
    pc-listener.bat        (launches pc-listener under pythonw)
    a70-bridge.sh          (A70 Termux daemon)
    pc-msg.sh              (A70 -> PC convenience CLI)
    install-bridge.sh      (one-shot A70 setup)
  state\
    a70-tailscale-ip.txt   (cached IP, refreshed by Bot-A70Keeper)
    pc-inbox.jsonl         (every A70->PC message)
```

## Implementation order

1. Install Tailscale on PC, log in to Iddo's account interactively, confirm A70 visible in tailnet.
2. Write `pc-listener.py` and start it under `pythonw`. Add scheduled task.
3. Push `a70-bridge.sh` + `pc-msg.sh` to A70 via `adb push`. Make Termux execute them on boot via `~/.termux/boot/`.
4. Extend `supervisor.ps1` with Bot-A70Keeper.
5. Write `dispatch-cli.ps1`. Test PC -> A70.
6. Test A70 -> PC.
7. Reboot survival tests (gate 4).
8. Document.
