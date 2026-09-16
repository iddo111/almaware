# BLOCKED: A70 needs unlock + Always-On VPN to fully self-recover post-reboot

Detected 2026-04-27 04:00 UTC by dispatch-fix agent during gate-4 (reboot survival).

## Symptom

After `adb reboot` issued at 03:58:05 UTC:
- A70 IP `<lan-ip>` is back on LAN within ~90 seconds (LAN ping responds).
- **TCP port 40723 (wireless ADB) stays closed** — Samsung's stock Android 11 does NOT auto-restart Wireless Debugging across reboot.
- **Tailscale on A70 stays offline** in tailnet — Tailscale Android does NOT auto-start unless "Always-On VPN" is set.
- Bot-A70Keeper correctly detects the disconnect, retries every 60 s with the cached endpoint, and falls through to mDNS rediscovery (also empty because the A70 isn't advertising). Logs in `~\.claude\a70-keeper.log`.

## What Iddo needs to do (one-time, ~60 seconds)

### Fix #1 — Tailscale Always-On VPN

So Tailscale auto-starts after every reboot:

1. On A70: **Settings > Connections > More connection settings > VPN**.
2. Tap the gear icon next to "Tailscale".
3. Toggle **Always-on VPN** ON.
4. Optional: also toggle **Block connections without VPN** for paranoid leak protection (skip if Iddo wants split-tunnel).

### Fix #2 — Wireless Debugging persistence (optional)

Stock Samsung Android 11 won't keep Wireless Debugging on across reboots. Two options:

- **Option A (recommended)**: rely on Tailscale alone for Layer 2 dispatch. Re-enable Wireless Debugging only when needed for dev work.
- **Option B**: install a Tasker/MacroDroid recipe that watches for `BOOT_COMPLETED` and runs `am start -a com.android.settings.DEVELOPMENT_SETTINGS` then taps the toggle. Untrustworthy in practice; skip.
- **Option C**: root the device. Already on the hack queue but high effort vs low reward here.

Decision: Always-On VPN (#1) is sufficient. ADB is needed only for control-plane tasks (e.g. running `cmd notification post` as fallback when Tailscale is down — and if Tailscale is down, ADB is also likely unreachable, so the fallback is moot).

## After Iddo applies fix #1

1. On A70: Settings > VPN > tap Tailscale > confirm "Always-on" is on.
2. Test: reboot the A70. Within 30-60 s after boot completes, run on PC:
   ```powershell
   & 'C:\Program Files\Tailscale\tailscale.exe' status | findstr a70
   ```
   Expected: `<tailnet-ip> a70 iddo111@ android idle; ...` (no "offline").
3. Re-run gate-4:
   ```powershell
   curl.exe -s --max-time 4 http://<tailnet-ip>:18181/ping
   ```
   Expected: `pong`.

## Status of dispatch system without this fix

- **Steady-state operation (no reboot)**: ALL FOUR mission goals work fully (verified gates 1, 2, 3, 5, 6 already passed).
- **Across reboots**: Tailscale on A70 needs Iddo to either open the Tailscale app once OR enable Always-On VPN once. After that, no further intervention.

This is documented in `RUNBOOK.md` "Known limitations".
