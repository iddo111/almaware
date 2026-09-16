# A70 Dispatch + Self-Healing Watchdog

PC <-> Samsung Galaxy A70 dispatch bridge, plus an hourly watchdog that monitors
the path and auto-repairs the pieces this PC owns.

- Architecture / design: `ARCHITECTURE.md`
- Operate / debug / roll back: `RUNBOOK.md`
- This file: the watchdog + the dispatch-path fixes (2026-06-14).

A70 tailnet IP: `<tailnet-ip>`. PC tailnet IP (when up): `<tailnet-ip>`.

---

## TL;DR

```powershell
# Install the hourly watchdog (run elevated for full self-heal):
pwsh -NoProfile -ExecutionPolicy Bypass -File D:\CLAUDE\dispatch-fix\install-watchdog.ps1

# Run the watchdog by hand any time:
pwsh -NoProfile -ExecutionPolicy Bypass -File D:\CLAUDE\dispatch-fix\watchdog.ps1 -Verbose

# Check-only, no repairs:
pwsh -File D:\CLAUDE\dispatch-fix\watchdog.ps1 -DryRun

# Current health at a glance:
Get-Content D:\CLAUDE\dispatch-fix\state\watchdog-health.json -Raw
```

---

## What was broken / fixed in the dispatch path (2026-06-14)

`bin/dispatch-cli.ps1` (PC -> A70 sender) had two real bugs that made the ADB
fallback silently dead on this machine:

1. **`adb` was called bare** (relying on PATH). `adb` is NOT on PATH on this PC
   and is not installed in the usual SDK location, so every `& adb ...` call
   produced a CommandNotFound that was swallowed -> the "Layer 3 ADB fallback"
   never actually ran. Fixed: added `Resolve-Adb` (probes PATH + common SDK /
   scoop / choco locations) and an `Invoke-Adb` wrapper used everywhere.

2. **The stored ADB endpoint is an mDNS service name**, not an `ip:port`
   (`adb-R58MC0KVS0X-QEqIr1._adb-tls-connect._tcp` in
   `state/a70-adb-endpoint.txt`). `adb -s <mdns-name> shell ...` only works if
   the device is already connected; after a reboot it is not. Fixed:
   `Refresh-Endpoints` now runs `adb connect <mdns-name>` first, then enumerates
   `adb devices`, matches the A70 by `ro.product.model`=SM-A70x or
   `ro.product.device`=a70q, and rewrites the state file with the live `ip:port`.
   The notify/exec helpers refuse to use a raw mDNS name and trigger a refresh.

Both `Try-AdbNotify` / `Try-AdbExec` now use `Invoke-Adb` and detect adb-absent
vs. device-offline distinctly, logging each to `dispatch-fix.log`.

The **broker `a70` user** bug (the MQTT broker installer never created the `a70`
account, so the phone auth-failed on every connect) was already fixed upstream in
`D:\grok\projects\glock-cowork-wt\glock-system\mqtt\install-broker.sh` (it now
provisions `a70` idempotently and writes the password to
`glock-mqtt-passwords.env`). Verified present. See **Human gates** for the
remaining broker-side action (the Tailscale listener is still commented out).

---

## The watchdog: `watchdog.ps1`

Runs hourly. Checks four things in dependency order and self-heals what this PC
can fix. It **never fakes connectivity** — anything offline is logged with a
`[GATE]` line and the exact human action, and the next hourly run retries.

| # | Check | Self-heal on this PC? | If it cannot |
|---|-------|-----------------------|--------------|
| 1 | **pc-listener.py** on `:18180` (port bound + `/ping` returns `pong`) | YES — reaps the wedged owner + respawns under `pythonw` (same logic as `keeper.py`), then re-verifies | logs gate: check python312 + pc-listener.py |
| 2 | **Tailscale (PC)** service up + logged in (`tailscale ip -4` returns 100.x) | Partial — starts the service if stopped; tries non-interactive `tailscale up` | if logged out (NeedsLogin): **human gate** — run `tailscale up` + browser login |
| 3 | **A70 reachable** via `tailscale ping <tailnet-ip>` (+ ADB LAN fallback) | No (remote device) | **human gate** — power on A70 + Always-on VPN + unlock |
| 4 | **MQTT broker** TCP `1883` (Tailscale `<tailnet-ip>`, then LAN `<lan-ip>`) | No (runs on the Linux laptop) | **human gate** — start laptop + `systemctl restart mosquitto` |

Output:
- Append-only log: `watchdog.log`
- Machine-readable health snapshot: `state/watchdog-health.json`
  (fields: `pc_listener`, `tailscale_pc`, `a70_reachable`, `broker`, `gates[]`,
  `overall`). `overall` is one of `healthy`, `pc-ok-remote-gated`, `degraded`.

The watchdog **always exits 0** — a remote device being off must not make the
Scheduler flag the task as failed. Health lives in the JSON + log.

### Idempotency / safety
- If pc-listener is already healthy, the watchdog does **not** touch it
  (verified: a run found `pc_listener: up`, `pc_listener_act: none`).
- Only ever kills processes whose command line contains `pc-listener.py`, plus
  the single PID that owns `:18180`. Nothing else.
- `-DryRun` reports without killing/respawning anything.

---

## The installer: `install-watchdog.ps1`

Registers the Scheduled Task **`ALMAWARE-A70-Dispatch-Watchdog`** via
`schtasks.exe /Create /XML` (works in restricted shells where the
`ScheduledTasks` cmdlets are blocked).

Triggers:
- **TimeTrigger** — repeats **every 1 hour, indefinitely**.
- **LogonTrigger** — also runs **2 minutes after logon** (closes the gap right
  after a reboot).

Privilege:
- Run from an **elevated** PowerShell -> registers as **Highest + S4U**: runs
  whether or not you are logged on, and can `Start-Service Tailscale` / kill
  wedged processes.
- Run **non-elevated** -> registers as **LeastPrivilege + Interactive**: still
  runs hourly while you are logged on, but cannot start the Tailscale service.
  Re-run elevated any time to upgrade.

```powershell
# Register / re-register (idempotent):
pwsh -NoProfile -ExecutionPolicy Bypass -File D:\CLAUDE\dispatch-fix\install-watchdog.ps1

# Register and run once immediately:
pwsh -File D:\CLAUDE\dispatch-fix\install-watchdog.ps1 -RunNow

# Remove:
pwsh -File D:\CLAUDE\dispatch-fix\install-watchdog.ps1 -Unregister
```

Verify / inspect:
```powershell
schtasks.exe /Query /TN 'ALMAWARE-A70-Dispatch-Watchdog' /FO LIST /V
```

---

## Human gates (cannot be automated — physical / auth actions)

The watchdog detects and logs these; only a human can clear them:

1. **A70 powered on + on the tailnet + unlocked + paired.** The phone must be on,
   Tailscale set to **Always-on VPN**, and (for the ADB LAN fallback) Wireless
   Debugging enabled + paired. When the phone is off or roaming off-tailnet, no
   PC-side fix applies — `a70_reachable: down`.

2. **Tailscale on the PC logged in.** As of 2026-06-14 the PC Tailscale is
   **logged out** (`state: NeedsLogin`). Clear it once:
   ```powershell
   & "C:\Program Files\Tailscale\tailscale.exe" up
   ```
   then complete the login URL in a browser. Until then all Tailscale-path
   dispatch + the `tailscale ping` health check are down.

3. **MQTT broker running on the Linux laptop (`lapclod`).** The GLOCK Mosquitto
   broker runs on the laptop, not this PC. Start the laptop and ensure the
   service is up:
   ```bash
   sudo systemctl restart mosquitto   # or re-run install-broker.sh
   ```
   **Known config gap:** `mosquitto-glock.conf` currently has **only a LAN
   listener** (`listener 1883 <lan-ip>`); the Tailscale listener line is
   commented out. So even with the `a70` user provisioned, the A70 cannot reach
   the broker over Tailscale **while roaming**. To enable roaming MQTT, uncomment
   the `listener 1883 100.x.x.x` line (set to the laptop's `tailscale ip -4`),
   copy the conf to `/etc/mosquitto/conf.d/glock.conf`, and
   `sudo systemctl reload mosquitto`. Also note `a70-dispatch.py` defaults its
   broker to `<tailnet-ip>` — confirm that matches the laptop's actual
   Tailscale IP.

4. **adb (platform-tools) installed on the PC** *(optional)* — only needed for
   the LAN-only ADB fallback (Layer 3). Not installed here. The Tailscale path
   (Layer 2) does not need it. If you want the fallback, install platform-tools;
   `Resolve-Adb` will then find it automatically.

---

## Files

```
D:\CLAUDE\dispatch-fix\
  watchdog.ps1               <- hourly health check + self-heal (NEW)
  install-watchdog.ps1       <- registers ALMAWARE-A70-Dispatch-Watchdog (NEW)
  README.md                  <- this file (NEW)
  watchdog.log               <- watchdog append-only log (created at first run)
  keeper.py                  <- prior pc-listener-only keeper (superseded by watchdog check 1)
  bin\
    dispatch-cli.ps1         <- PC -> A70 sender (FIXED: adb resolve + mDNS reconnect)
    pc-listener.py           <- PC inbox HTTP on :18180 (the piece the watchdog keeps alive)
    pc-msg.sh / a70-bridge.py / install-bridge.sh   <- A70-side Termux bridge
  state\
    watchdog-health.json     <- latest health snapshot (NEW)
    a70-tailscale-ip.txt     = <tailnet-ip>
    a70-adb-endpoint.txt     = <mDNS name; refreshed to ip:port on demand>
    pc-tailscale-ip.txt      = <tailnet-ip>
    pc-inbox.jsonl           <- every A70 -> PC message
```

---

## Verification done at authoring (2026-06-14)

- pc-listener was **down**; watchdog **respawned** it -> `:18180` returns `pong`
  (verified via HTTP). On the next run it found it healthy and left it alone
  (idempotent).
- Tailscale logged-out, A70 off, broker off -> all three surfaced as `[GATE]`
  lines with the human action; `overall = pc-ok-remote-gated`. No faked success.
- Scheduled task registered (`Schedule Type: One Time Only, Hourly; Repeat:
  Every 1 Hour(s)` + `At logon time`), ran once on demand, settled to
  `Status: Ready`, `Last Result: 0`.
- `dispatch-cli.ps1` smoke test with no connectivity failed gracefully through
  every layer (tailscale timeout -> adb-absent -> mDNS-skip -> retry) and logged
  each step to `dispatch-fix.log`.
