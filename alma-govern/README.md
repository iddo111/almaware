# ALMA-Govern

Shared thermal / CPU / GPU **and fleet-health** governance SDK for the ALMA /
Eran DGX fleet.

The project also contains the executable minimum gate for public-benefit
initiatives. Read [PUBLIC_BENEFIT_CHARTER.md](PUBLIC_BENEFIT_CHARTER.md) and use
`alma_govern.public_benefit.assess_public_benefit()` before starting or scaling
a community pilot. Missing evidence fails closed as `PAUSE` or `REJECT`.

Run the gate directly on a JSON proposal:

```bash
python -m alma_govern.public_benefit_cli pilots/community_garden_candidate.json
```

Exit codes are `0=APPROVE`, `2=PAUSE`, `3=REJECT`, and `4=INVALID`. The included
garden candidate is intentionally not approved: no community, lawful review,
baseline, external reviewer, or end date has been established yet.

**Principle:** *"mic always wins", protect the hardware.* Detection comes first.
Every "protect" action is **advisory and opt-in** — the SDK **never** runs a
destructive action on its own.

---

## Why the fleet-health guard exists

On the night of **2026-07-02** the DGX fleet hit a **network broadcast storm**
(a bridged loop on the ConnectX-7 fabric). It pegged the kernel's softirq
handling (`ksoftirqd` at ~100%), buffers backed up, RAM was exhausted, and the
kernel **OOM-killed the running trainings**.

`alma_govern.fleet_health` detects exactly that class of failure — early, and
without needing root or SSH to be tested — and tells the operator what it *would*
recommend, without ever pulling the trigger itself.

## What it detects

| Detector | Fires on | Example signal |
|---|---|---|
| **`detect_network_storm`** | broadcast/multicast storm, softirq peg | NIC broadcast pps spike, total rx pps flood, `ksoftirqd` pegged |
| **`detect_memory_pressure`** | memory exhaustion / imminent or in-progress OOM | `%` RAM used, low available-MiB floor, swap thrash, **new `oom_kill` count** |
| **`detect_gpu_health`** | GPU thermal + Xid faults | temp over warn/crit, critical Xids (48/79/94/95/**119/120** GSP-hang class) |

Each returns a `Finding` with a `Severity` (`OK / INFO / WARN / CRITICAL`), the
metrics it judged on, and an optional **advisory** `recommended_action` string.
`assess_node()` runs all three and rolls up to the worst severity.

## Design: detectors are pure, so tests run offline

Detectors are **pure functions over a metric-snapshot dict**. Real metrics are
gathered by `alma_govern.collectors` (Linux `/proc`, `psutil`, `nvidia-smi`,
`dmesg` Xid scrape) — but the detectors never touch the system directly, so the
whole suite runs **offline** with synthetic snapshots. No SSH, no root, no GPU
required to test.

```
alma-govern/
  PUBLIC_BENEFIT_CHARTER.md # project purpose, non-negotiables, pilot gate
  alma_govern/
    fleet_health.py   # detectors + Severity/Finding/Thresholds (pure)
    public_benefit.py # consent/rights/safety/evidence gate (pure)
    public_benefit_cli.py # strict JSON command-line gate
    collectors.py     # live metric sources (Linux/psutil/nvidia-smi); degrade gracefully
    cli.py            # `python -m alma_govern.cli check|watch`
    __init__.py
  demo.py             # offline scenario replay (storm night) — proves detectors fire
  pilots/community_garden_candidate.json # honest, currently unapproved draft
  tests/test_fleet_health.py
  tests/test_public_benefit.py
```

## Install / requirements

- Python 3.9+
- `psutil` (already present in this env). `nvidia-smi` / `dmesg` are used when
  available; missing sources are silently skipped.

No packaging step needed — run from the repo root.

## Usage — library

```python
from alma_govern import assess_node, Severity

snapshot = {
    "nics": {"fab0": {"bcast_pps": 950_000, "rx_pps": 2_400_000}},
    "ksoftirqd_pct": [98, 99],
    "mem_total_mib": 1_024_000, "mem_available_mib": 900,
    "oom_kill_delta": 3,
    "gpus": [{"index": 0, "temp_c": 70, "xids": []}],
}

a = assess_node("eran3", snapshot)
print(a.severity)                    # Severity.CRITICAL
for f in a.findings:
    print(f)                         # human line
    if f.recommended_action:
        print("  advisory:", f.recommended_action)   # printed, never run
```

Thresholds are all overridable:

```python
from alma_govern import Thresholds, detect_network_storm
th = Thresholds(bcast_pps_warn=10_000, bcast_pps_crit=40_000)
detect_network_storm(snapshot, th)
```

## Usage — CLI

Runs on a node, **alerts** (logs + threshold exit code), never acts.

```bash
# live check on this node (sources that don't exist here are skipped)
python -m alma_govern.cli check

# machine-readable
python -m alma_govern.cli check --json

# OFFLINE: judge a saved snapshot (no host access needed)
python -m alma_govern.cli check --from snapshot.json

# also PRINT the advisory protect actions (still never executed)
python -m alma_govern.cli check --protect

# loop and alert on change / whenever WARN+
python -m alma_govern.cli watch --interval 10
```

**Exit code = worst severity** (`0` OK, `1` INFO, `2` WARN, `3` CRITICAL), so it
drops straight into systemd / cron / a monitoring probe.

### The "protect" action is advisory — by design

`--protect` only **prints** a recommendation, e.g. for a storming link:

```
ADVISORY (not executed): consider isolating storming link 'fab0'
(advisory: `ip link set fab0 down`) after confirming it is not the only path;
investigate for a bridged loop
```

The SDK **does not** bring interfaces down, kill jobs, or reset GPUs. Given the
fabric's known **hidden loop** (only `eran2 <-> eran3` is a valid leg), auto-downing
a link could strand a node — so the human decides and executes.

## Run the demo & tests

```bash
# offline scenario replay — replays the 2026-07-02 storm night, exit 0 iff all fire
python demo.py

# unit tests (pytest, or plain-python fallback baked into the file)
python -m pytest tests/ -q
python tests/test_fleet_health.py
```

Verified on this machine: `demo.py` -> **all detectors fired**, exit 0;
`pytest` -> **19 passed**.

## Scope / safety notes

- Offline-first: nothing in the test path needs SSH, root, or hardware.
- Advisory-only protect actions; never auto-destructive.
- Heavy/real fleet collection (SSH fan-out) is intentionally **not** run from
  the PC — a collector runs *on* each node; the caller aggregates.
