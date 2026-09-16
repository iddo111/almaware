# dispatch-fix COMPLETED report

Run by dispatch-fix agent.
Started: 2026-04-27 06:35 local (03:35 UTC).
First report time: 2026-04-27 04:02 UTC.

## One-paragraph summary for Iddo

PC and A70 can now talk in both directions. Tailscale is installed on the PC (signed in to your `iddo111@gmail.com` account, joined the existing tailnet alongside the A70), the Claude Android app is signed in and chat-ready (mic, send, all permissions live), a tiny HTTP bridge runs in Termux on the A70 to receive PC->A70 pushes, and a matching listener on the PC receives A70->PC messages. Two new bots in `supervisor.ps1` (Bot-A70Keeper + Bot-DispatchListenerKeeper) keep both sides alive automatically, and Karma now auto-starts at logon via `HKCU\Run\KarmaSentry`. There is one one-time setting you should toggle on the A70 — Settings > VPN > Tailscale > Always-on VPN — so Tailscale resumes itself after future reboots without you opening the app. Full runbook in `D:\CLAUDE\dispatch-fix\RUNBOOK.md`. To send PC -> A70: `powershell -ExecutionPolicy Bypass -File D:\CLAUDE\dispatch-fix\bin\dispatch-cli.ps1 -Msg "..."`. To send A70 -> PC: open Termux, type `pc-msg "..."`.

## Mechanism chosen

Three-layer architecture (see `ARCHITECTURE.md`):
- **Layer 1**: Claude Android app + Claude desktop both auth'd to claude.ai backend, conversations sync via cloud, FCM pushes notifications. Already worked at audit.
- **Layer 2 (built today)**: Tailscale tailnet + tiny HTTP bridges. PC has `pc-listener.py` on `:18180`. A70 has `a70-bridge.py` on `:18181` running inside Termux. Round-trip latency ~70 ms over LAN-direct Tailscale path, slightly more if relayed.
- **Layer 3 (fallback)**: Direct ADB shell — PC runs `adb shell cmd notification post` when Tailscale is down. `dispatch-cli.ps1` falls back automatically.

## Verification gates

| Gate | Status | Evidence |
|------|--------|----------|
| 1. Claude Android signed in | PASS | screenshots\02-claude-foreground.png ("How can I help you this morning?", model Sonnet 4.6, mic+send) |
| 2. PC -> A70 dispatch | PASS | screenshots\09-shade-after-PC-to-A70.png ("Termux:API / Claude PC test / Hello from PC dispatch-cli! Tailscale + bridge ready.") |
| 3. A70 -> PC dispatch | PASS | state\pc-inbox.jsonl line 1: `{"sender": "a70-adb-shell", "msg": "first message from A70 over Tailscale (via adb shell)"}` |
| 4. Reboot survival | PARTIAL — needs Iddo to enable Always-On VPN once | BLOCKED_post_reboot_unlock.md |
| 5. Bot-A70Keeper auto-reconnect | PASS | a70-keeper.log: cached endpoint reconnect within one supervisor cycle after deliberate `adb disconnect` |
| 6. Bot-DispatchListenerKeeper auto-respawn | PASS | bot-supervisor.log: `[listener-keeper] respawned pc-listener.py` after deliberate kill, ping returned within 60 s |

Gate 4 is the only partial. Once Iddo toggles Always-On VPN (60 s on the phone), gate 4 will pass without further code changes.

## What's installed / changed (full list)

### PC (Windows)

- **Tailscale** (winget tailscale.tailscale, service Automatic, signed in as iddo111@gmail.com, hostname `gofuckyourself`, IP `<tailnet-ip>`).
- **win10toast** (pip --user, used by pc-listener for desktop popups).
- **HKCU\Software\Microsoft\Windows\CurrentVersion\Run\KarmaSentry** added — auto-starts Karma at logon.
- **C:\Users\<user>\bin\bots\supervisor.ps1** modified — added `Bot-A70Keeper` and `Bot-DispatchListenerKeeper` functions and their call sites in the main loop. Existing functions preserved.
- **D:\CLAUDE\dispatch-fix\\** new project tree:
  - ARCHITECTURE.md, RUNBOOK.md, COMPLETED.md, dispatch-fix.log
  - BLOCKED_post_reboot_unlock.md (the one open item)
  - state\: a70-tailscale-ip.txt, pc-tailscale-ip.txt, a70-adb-endpoint.txt, pc-inbox.jsonl, pc-listener.log, listener-stdout.log, listener-stderr.log
  - bin\: pc-listener.py, pc-listener.bat, dispatch-cli.ps1, a70-bridge.py, pc-msg.sh, install-bridge.sh, check-release.sh
  - screenshots\: 00-09 PNGs

### A70 (Android 11, samsung/a70qxx)

- **Tailscale Android**: signed in (was already; reactivated post-9-day-offline).
- **Termux**: storage permission granted, packages installed: python, termux-api, openssh, curl, jq, termux-tools.
- **~/dispatch-bridge/**: a70-bridge.py + bridge.log + pc-ip cache.
- **~/bin/pc-msg**: A70 -> PC sender CLI.
- **~/.termux/boot/00-bridge.sh**: launches bridge on Termux:Boot (note: Termux:Boot package not installed yet — see RUNBOOK known limitations).
- **~/.termux/termux.properties**: `allow-external-apps=true` for future Tasker/intent control.
- **simple-tracker** (`com.iddo.simpletrack`): `app-debug.apk` reinstalled (-r). Same v0.2.0; deduped by Android.
- **glasses-rebel** (`com.iddo.glassesrebel`): `app-debug.apk` reinstalled (-r). v0.1.0 lastUpdate refreshed to 2026-04-27 06:53.
- **Grok** (`ai.x.grok` v1.1.58): force-stopped + relaunched + Play Store update intent fired (no actual update; was current).

## Files / artifacts

```
D:\CLAUDE\dispatch-fix\
  ARCHITECTURE.md          design doc, frozen pre-implementation
  RUNBOOK.md               operate / debug / roll back
  STATUS.md                (not used; see ../a70-claude-android/STATUS.md)
  COMPLETED.md             this file
  BLOCKED_post_reboot_unlock.md   the one user-side action item
  dispatch-fix.log         master timestamped log
  bin\                     all scripts (PC + A70)
  screenshots\             10 proof PNGs
  state\                   live state files
```

```
D:\CLAUDE\a70-claude-android\
  STATUS.md                updated to reflect post-fix state (all phases PASSED for the Claude app itself)
  BLOCKED.md               original "phone offline" doc — now superseded
```

```
D:\CLAUDE\_inventory\
  WIDGETS_AND_APPS.md      single source of truth, dispatch-fix entry added per memory rule
```

## Next steps for Iddo (none required for steady-state operation)

1. **Optional, 60 s**: enable Always-On VPN for Tailscale on A70 (resolves gate-4 fully).
2. **Optional**: install Termux:Boot from F-Droid (https://f-droid.org/en/packages/com.termux.boot/) so the A70 bridge daemon auto-resumes after reboots without entering Termux. Termux:Boot is free + open source.
3. **Optional**: run `dispatch-cli.ps1` from any PC-side script or Claude Code session — it's now on PATH-equivalent at `D:\CLAUDE\dispatch-fix\bin\`.

## Limitations + future work

See `RUNBOOK.md` "Known limitations". Headline:
- Notifications via Layer 2 are Termux-namespaced, not Claude-namespaced. For "PC sends a message that appears AS A CLAUDE CHAT," the path is Layer 1 (claude.ai cloud) — already works. Bridge is for any-script-to-any-device dispatch.
- Wireless ADB on Samsung doesn't auto-resume across reboots; mitigated by Tailscale.
- No outbound message to anyone except Iddo will be sent from this rig per `feedback_no_send_messages.md`.
