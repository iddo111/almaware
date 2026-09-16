# ALMAWARE · Eran-Stats Dashboard

Floating, always-on-top, tabbed fleet widget for the ALMA / Eran DGX cluster.
Bright theme, frameless, draggable by its title bar, minimizes to the system tray.
**Real data only — no fabricated numbers.**

Source of the shipped `ALMAWARE-Eran-Stats.exe`: **`eran_dashboard.py`**
(`master_widget.py` is a separate, simpler legacy widget kept only for the pure-helper tests).

## Tabs

| Tab | Shows |
|---|---|
| **ERAN** | LIVE training: step, loss, EMA loss, steps/sec, a loss-trend sparkline; local GPU/CPU/RAM heat; active projects (from **running processes** under `D:\CLAUDE`, not a stale file). |
| **FLEET** | Per-node health for **PC + eran1..eran4**: GPU temp/util, ping, live ↓/↑ throughput, a training indicator, the 200G `brfab` fabric status, and a **STORM-GUARD** row (ALMA-Govern severity rollup). |
| **AI** | Claude usage (weekly + 5h burst, real OAuth snapshot) and Grok usage (monthly billing) with reset countdowns; local Grok route up/down. |
| **PC** | This machine: CPU / RAM / Disk D: / GPU bars, live net ↓/↑, internet reachability. |

## Where the numbers come from

- **Eran LIVE step/loss** — tail of `D:\CLAUDE\eran-live\logs\metrics.jsonl` (seeks to the
  file end, so it stays cheap as the log grows past millions of steps). Verified reading
  **step ≈ 7.28M** live.
- **Fleet nodes** — one lightweight **read-only** SSH call per node (`_REMOTE` payload:
  `nvidia-smi` query + a `ps` training-process match + net counters + `brfab` fabric +
  ALMA-Govern severity). Nothing is launched or killed on the fleet.
- **Storm-guard** — `python3 -m alma_govern.cli check --json` on each node
  (see `D:\CLAUDE\alma-govern`). **Advisory only**: it detects the broadcast-storm /
  memory-pressure / GPU-fault classes that OOM-killed trainings on 2026-07-02, and never
  acts on its own.

## Fleet connectivity (important)

The dashboard connects to each node with an **explicit key + `user@ip`** taken from its
own authoritative map in `eran_dashboard.py` — it does **not** rely on the ambient
`~/.ssh/config` (two included SSH configs on this PC disagree and have drifted). Current
map (2026-07-03):

| Node | IP | SSH key | Notes |
|---|---|---|---|
| eran1 | <lan-ip> | `…\NVIDIA Corporation\Sync\config\nvsync.key` | wired head node |
| eran2 | <lan-ip>  | `~\.ssh\id_ed25519` | WiFi worker |
| eran3 | <lan-ip>  | `~\.ssh\id_ed25519` | WiFi worker |
| eran4 | <lan-ip>  | `~\.ssh\id_ed25519` | wired spare |

If DHCP reassigns an IP, update `NODE_IP` (and `NODE_KEY` if a key changes) at the top of
`eran_dashboard.py`. Because connections are explicit, the widget is immune to `~/.ssh`
drift.

## Health / status endpoint

A localhost-only HTTP server (default `127.0.0.1:8788`, scans up to +10 ports) serves:

- `GET /health` → `{ok, nodes_online, nodes_total, training}`
- `GET /status.json` → sanitized fleet snapshot (logical node names only — **no IPs, hosts,
  paths, or PII**), now including per-node `gov_sev` and a `summary.gov_worst` rollup.

## Run

```powershell
# no console window:
pythonw eran_dashboard.py
# or with a console (for logs):
python  eran_dashboard.py
```

Override the status port with `ERAN_DASHBOARD_PORT`.

## Build the .exe

Single-file, windowed, tray-capable build via PyInstaller 6.x:

```powershell
cd D:\CLAUDE\eran-dashboard
python -m PyInstaller build_alma\ALMAWARE-Eran-Stats.spec `
    --distpath dist_alma --workpath build_alma --noconfirm
# -> dist_alma\ALMAWARE-Eran-Stats.exe  (~32 MB, UPX-compressed)
```

The build is heavy (~1–2 min) and is intentionally kept off the hot path; the `.py`
runs directly with identical behavior.

## Tests

```powershell
python -m pytest test_pure_helpers.py -q      # pure helpers (color thresholds, usage parsers)
```
