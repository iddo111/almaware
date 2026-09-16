# STATUS — ALMAWARE Eran-Stats Dashboard

**Last verified: 2026-07-03** (post fleet-work polish pass)

## Health: GREEN — reads real live data

| Check | Result |
|---|---|
| `eran_dashboard.py` compiles | ✅ `py_compile` OK |
| Pure-helper tests | ✅ 8 passed |
| GUI builds + ticks (headless) | ✅ no widget errors |
| **Eran LIVE step** | ✅ **7,284,440** (~7.28M) read from `eran-live\logs\metrics.jsonl` tail |
| Storm-guard rollup renders | ✅ e.g. `WARN (3/4 nodes report)` in amber |

## Live fleet poll (through the dashboard's own code, read-only)

| Node | Online | GPU °C / util | Training | Storm-guard | Ping |
|---|---|---|---|---|---|
| eran1 | ✅ | 72° / 93% | ▶ `…/eran/.venv/bin/python …` | **WARN** (memory_pressure) | 24 ms |
| eran2 | ✅ | 42° / 0%  | — | OK | — |
| eran3 | ✅ | 48° / 14% | ▶ `tmux …peret…` | OK | — |
| eran4 | ✅ | 63° / 76% | — | OK | 1 ms |

(eran1's WARN is legitimate — high RAM under active training, the same failure class the
storm-guard exists to catch. Advisory only; nothing was acted on.)

## What was fixed tonight

1. **Root-cause fleet fix — stale SSH config drift.**
   The FLEET tab was blind because the winning `~/.ssh` include (`eran.ssh_config`) had
   drifted IPs (eran1→.72, eran2→<fabric-ip> via ProxyJump, eran3→.26, eran4→.163) while a
   second include held the correct ones. The dashboard now connects with an **explicit
   `-i <key>` + `user@ip`** from its own authoritative map, so it is immune to that drift.
   No system SSH config was modified (kept scope to this project).

2. **Updated `NODE_IP`** to the current addresses (eran2 `.108→.59`, eran3 `.26→.20`;
   eran1 `.198`, eran4 `.12` unchanged) and added `NODE_USER` / `NODE_KEY` (eran1 uses the
   NVIDIA-Sync `nvsync.key`, others use `id_ed25519`). This is what the ping column reads.

3. **Storm-guard indicator (ties to `D:\CLAUDE\alma-govern`).**
   Folded a read-only `alma_govern.cli check --json` into the existing per-node SSH payload
   (no extra connections). New FLEET **STORM-GUARD** row shows the worst severity across
   reporting nodes; a `⚠` glyph appears on any node at WARN+. Also exposed as `gov_sev` /
   `summary.gov_worst` on the `/status.json` endpoint.

## Known-benign notes

- `STATUS_FILE` constant points at a non-existent path but is **dead** (never read) — left
  untouched to avoid churn.
- GPU `memory.used/total` reads `[N/A]` on the DGX Spark GPUs; the parser degrades
  gracefully (shows the raw tokens, no crash).

## Build

`dist_alma\ALMAWARE-Eran-Stats.exe` rebuilt from the updated source on 2026-07-03 via the
documented PyInstaller command (see README). The `.py` runs directly with identical behavior.
