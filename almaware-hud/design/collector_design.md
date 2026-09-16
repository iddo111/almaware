🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# ALMAWARE-HUD Collector Daemon — Design (DESIGN 2)

**File**: `D:\CLAUDE\almaware-hud\collector.py`
**Purpose**: Long-running Python 3.13 daemon. Reads the world, writes `D:\CLAUDE\almaware-hud\status.json` every 5s. Cockpit is a *pure reader* — this daemon is the only writer.
**Constraints**: stdlib only. Never blocks. Atomic writes. Graceful degradation.

---

## 1. Top-level architecture

```
                       ┌──────────────────────────────────────┐
                       │           MAIN LOOP (5s tick)        │
                       │  every_tick_probes() → merge cache   │
                       │  → build status dict                 │
                       │  → atomic_write(status.json)         │
                       └──────────────────────────────────────┘
                              │              ▲
                cheap probes  │              │ read cached results
                (inline)      ▼              │
                       ┌──────────────┐   ┌──────────────────┐
                       │  every-tick  │   │   CACHE STORE    │
                       │  gatherers   │   │  (thread-safe    │
                       │  (fast <1s)  │   │   dict + RLock)  │
                       └──────────────┘   └──────────────────┘
                                              ▲     ▲    ▲
                                              │     │    │
                       ┌──────────────────────┴─────┴────┴────────┐
                       │       BACKGROUND WORKER THREADS          │
                       │  fleet_worker   (SSH DGX,       60s TTL) │
                       │  fabric_worker  (SSH QSFP,      60s TTL) │
                       │  project_worker (~30 mtimes,    30s TTL) │
                       │  git_worker     (git status,    60s TTL) │
                       │  todo_worker    (aggregate,     60s TTL) │
                       │  system_worker  (wmi CPU/disk,  30s TTL) │
                       └──────────────────────────────────────────┘
```

**Rule**: nothing in the main loop is allowed to block for more than ~500ms. Anything slower gets its own thread with a TTL cache.

---

## 2. `status.json` schema — full contract with cockpit

This is the exact schema DESIGN 1 (cockpit) reads. It is stable. Additive changes only.

```jsonc
{
  "meta": {
    "version": 1,                            // schema version
    "ts": 1720699200.123,                    // unix epoch, float
    "ts_iso": "2026-07-11T09:00:00+03:00",   // Israel local time
    "collector_pid": 12345,
    "collector_uptime_s": 3600,
    "tick_ms": 42,                           // last tick duration
    "stale": false                           // true if any critical probe > 3× TTL
  },

  "eran": {
    "state": "training" | "idle" | "crashed" | "unknown",
    "http": {
      "port": 8792,
      "up": true,
      "latency_ms": 12,
      "checked_at": 1720699200.0
    },
    "log_tail": {
      "path": "D:\\CLAUDE\\eran-live\\eran.log",
      "last_line": "step 7,742,110 loss 2.14 tok/s 380",
      "last_mtime": 1720699198.4,
      "age_s": 1.7,
      "recent_lines": ["...", "...", "..."]    // last 8 lines
    },
    "watch_tail": {
      "path": "D:\\CLAUDE\\eran-live\\watch.log",
      "last_line": "...",
      "age_s": 3.0
    },
    "step": 7742110,                          // parsed from eran.log
    "loss": 2.14,                             // parsed from eran.log
    "tok_s": 380,                             // parsed from eran.log
    "vram_gb": null                           // filled by fleet worker
  },

  "grok1": {
    "shim": {
      "port": 8899,
      "up": true,
      "latency_ms": 8,
      "process": {                            // psutil-free: tasklist parse
        "pid": 4432,
        "name": "python.exe",
        "cmdline_hint": "grok1_shim.py"
      }
    },
    "backend": {
      "url": "http://eran1.tailscale:8080",
      "up": true,
      "latency_ms": 45,
      "via": "tailscale"
    },
    "context_injection": {
      "loaded": true,                         // did shim log "context loaded"?
      "source_mtime": 1720650000.0
    }
  },

  "fleet": {
    "eran1": {
      "reachable": true,
      "cached_at": 1720699180.0,
      "cache_age_s": 20.1,
      "hostname": "eran1",
      "uptime_s": 864000,
      "load": [1.4, 1.2, 1.0],
      "mem": { "used_gb": 24.5, "total_gb": 64.0, "pct": 38.3 },
      "gpu": [
        { "index": 0, "name": "DGX Spark", "util_pct": 92, "mem_used_gb": 78.0, "mem_total_gb": 80.0, "temp_c": 68 }
      ],
      "cpu": { "util_pct": 41, "temp_c": 55 },
      "error": null
    },
    "eran2": { "...same shape...": true },
    "eran3": { "...same shape...": true }
  },

  "fabric": {
    "cached_at": 1720699180.0,
    "cache_age_s": 20.1,
    "links": {
      "eran1<->eran2": { "state": "up", "speed_gbps": 200, "errors": 0 },
      "eran1<->eran3": { "state": "up", "speed_gbps": 200, "errors": 0 },
      "eran2<->eran3": { "state": "down", "speed_gbps": 0, "errors": 0, "note": "no bridge — star via eran2 by design" }
    }
  },

  "services": {
    // Every service is a uniform record. Cockpit tiles iterate this dict.
    "eran_http":   { "kind": "http", "target": "http://127.0.0.1:8792/health", "up": true,  "latency_ms": 12,  "checked_at": 1720699200.0, "error": null },
    "grok1_shim":  { "kind": "http", "target": "http://127.0.0.1:8899/health", "up": true,  "latency_ms": 8,   "checked_at": 1720699200.0, "error": null },
    "grok1_backend":{ "kind": "http","target": "http://eran1:8080/health",     "up": true,  "latency_ms": 45,  "checked_at": 1720699200.0, "error": null },
    "nachman_rag": { "kind": "http", "target": "http://127.0.0.1:8783/health", "up": false, "latency_ms": null,"checked_at": 1720699200.0, "error": "ECONNREFUSED" },
    "eran_poc":    { "kind": "http", "target": "http://127.0.0.1:8781/health", "up": true,  "latency_ms": 20,  "checked_at": 1720699200.0, "error": null },
    "tailscale":   { "kind": "tcp",  "target": "eran1:41641",                  "up": true,  "latency_ms": 5,   "checked_at": 1720699200.0, "error": null }
  },

  "projects": {
    "cached_at": 1720699170.0,
    "cache_age_s": 30.5,
    "items": {
      "eran-live":            { "path": "D:\\CLAUDE\\eran-live",           "exists": true,  "last_mtime": 1720699198.4, "age_s": 1.7,     "active": true  },
      "alma-language":        { "path": "D:\\CLAUDE\\alma-language",       "exists": true,  "last_mtime": 1720690000.0, "age_s": 9200.0,  "active": true  },
      "alma-govern":          { "path": "D:\\CLAUDE\\alma-govern",         "exists": true,  "last_mtime": 1720680000.0, "age_s": 19200.0, "active": true  },
      "eran-audio":           { "path": "D:\\CLAUDE\\eran-audio",          "exists": true,  "last_mtime": 1720670000.0, "age_s": 29200.0, "active": false },
      "lora-mesh":            { "...": "..." },
      "shisha-brain":         { "...": "..." },
      "alma-mic":             { "...": "..." },
      "alma-ozen":            { "...": "..." },
      "protoneuron":          { "...": "..." },
      "alma-store":           { "...": "..." },
      "green-eran":           { "...": "..." },
      "eran-federation":      { "...": "..." },
      "alma-talmud":          { "...": "..." },
      "yahadut-portals":      { "...": "..." },
      "iddoperez-web":        { "...": "..." },
      "alma-smart-care":      { "...": "..." },
      "casanova":             { "...": "..." },
      "alma-lapdock":         { "...": "..." },
      "quorum":               { "...": "..." },
      "alma-meta-selector":   { "...": "..." },
      "rebbe-nachman":        { "...": "..." },
      "iff":                  { "...": "..." },
      "noam":                 { "...": "..." },
      "sefer-hamalchut":      { "...": "..." },
      "electric-cave":        { "...": "..." },
      "cave-wall-brain":      { "...": "..." },
      "green-bitcoin":        { "...": "..." },
      "micro-car":            { "...": "..." },
      "frc-cloudistan":       { "...": "..." },
      "peretz-inquiry":       { "...": "..." }
    }
  },

  "git": {
    "cached_at": 1720699170.0,
    "cache_age_s": 30.0,
    "branch": "swarm/alma-language-4",
    "main_branch": "main",
    "ahead": 0,
    "behind": 3,
    "dirty_count": 87,
    "staged_count": 6,
    "untracked_count": 41,
    "last_commit": {
      "sha": "3558b95",
      "subject": "grid-dashboard: reservoir training layer",
      "author_time": 1720650000,
      "age_s": 49200
    },
    "recent_commits": [
      { "sha": "3558b95", "subject": "grid-dashboard: reservoir training layer" },
      { "sha": "a925099", "subject": "shisha-lab: 3x3 thermal-memristor grid" },
      { "sha": "508a4f3", "subject": "shisha-lab: 9-memristor crossbar" }
    ]
  },

  "workflow": {
    "peretz_inquiry": {
      "journal_path": "D:\\CLAUDE\\...\\journal.jsonl",
      "cached_at": 1720699195.0,
      "cache_age_s": 5.2,
      "last_event": {
        "ts": 1720699190.0,
        "phase": "design",
        "agent": "collector-designer",
        "status": "in_progress",
        "message": "writing collector_design.md"
      },
      "recent_events": [ /* last 10 */ ],
      "counts": { "queued": 3, "running": 2, "done": 12, "failed": 0 }
    }
  },

  "todo": {
    "cached_at": 1720699150.0,
    "cache_age_s": 50.0,
    "items": [
      { "project": "eran-live",       "priority": 1, "text": "watchdog: restart on crash" },
      { "project": "alma-language",   "priority": 2, "text": "publish perceptron3d artifact" },
      { "project": "peretz-inquiry",  "priority": 1, "text": "finish HUD build" }
      // up to 10, sorted by (priority asc, project active desc)
    ]
  },

  "system": {
    "host": "IDDO-PC",
    "os": "Windows 11 Pro 26200",
    "boot_time": 1720000000.0,
    "cpu": { "pct": 32.0, "temp_c": null },     // temp may be null on Windows
    "mem": { "used_gb": 24.0, "total_gb": 64.0, "pct": 37.5 },
    "disks": {
      "C:": { "free_gb": 420.5, "total_gb": 2000.0, "pct_free": 21.0 },
      "D:": { "free_gb": 800.1, "total_gb": 4000.0, "pct_free": 20.0 },
      "F:": { "free_gb": 12000.0, "total_gb": 16000.0, "pct_free": 75.0 }
    },
    "gpu": null                                  // local RTX status if we can, else null
  },

  "errors": [
    // Ring buffer of last ~20 errors from any gatherer. Cockpit shows these in a footer.
    { "ts": 1720699100.0, "where": "fleet.eran3", "msg": "ssh: connection timeout" }
  ]
}
```

### Contract rules
- **Every top-level key is always present.** Missing data → `null` on inner leaves, never remove keys. Cockpit's dark-mode CSS depends on the shape being stable.
- **Every cached section carries `cached_at` and `cache_age_s`.** Cockpit uses these to paint a "stale" outline.
- **Timestamps are floats (unix epoch).** `ts_iso` is only for humans; cockpit does its own formatting from `ts`.
- **Errors are opaque strings.** Never raw exception objects.

---

## 3. Function list (concrete public API)

Every gatherer returns a *shape-stable dict*. On failure it returns the same shape with `null` leaves and an `error` string. Nothing raises past the gatherer boundary.

### Every-tick (cheap, inline, must finish <500ms total)
```python
def gather_eran() -> dict          # log tails + HTTP :8792
def gather_grok1() -> dict         # HTTP :8899, HTTP eran1:8080, tasklist scan for shim
def gather_services() -> dict      # dict of ~6 tiny HTTP/TCP probes
def gather_workflow() -> dict      # tail peretz-inquiry journal.jsonl
def gather_meta(tick_start, uptime) -> dict
```

### Background-cached (each in its own thread, refresh loop = TTL)
```python
def gather_fleet() -> dict         # SSH eran1/2/3, TTL 60s
def gather_fabric() -> dict        # SSH ip -j link | mlxlink parse, TTL 60s
def gather_projects() -> dict      # scandir ~30 project dirs, TTL 30s
def gather_git() -> dict           # git status --short + git log -1, TTL 60s
def gather_todo() -> dict          # read TODO.md / journal-derived list, TTL 60s
def gather_system() -> dict        # powershell wmic / Get-Counter, TTL 30s
```

### Helpers
```python
def http_probe(url, timeout=1.5) -> ProbeResult
def tcp_probe(host, port, timeout=1.0) -> ProbeResult
def tail_file(path, n=8) -> list[str]           # binary-safe, seeks from end
def parse_eran_line(line) -> dict               # step/loss/tok_s regex
def ssh_json(host, remote_cmd, timeout=5) -> dict  # ssh -o BatchMode=yes -o ConnectTimeout=3
def atomic_write_json(path, data) -> None       # write .tmp → os.replace()
def push_error(where, msg) -> None              # ring buffer, thread-safe
```

### Cache primitive
```python
class TTLCache:
    """Thread-safe {key: (expires_at, value)}. get() never blocks past lock."""
    def __init__(self, default_ttl: float): ...
    def get(self, key) -> Optional[Any]: ...
    def set(self, key, value, ttl=None) -> None: ...
    def age(self, key) -> Optional[float]: ...
```

### Worker pattern
```python
class Worker(threading.Thread):
    """One thread per cached section. Refreshes on its own clock.
    - Runs its gatherer in a try/except.
    - Publishes to CACHE under a stable key.
    - Sleeps interruptibly (Event) so shutdown is fast.
    """
    def __init__(self, name, fn, interval_s): ...
    def run(self): ...
```

### Main loop
```python
def main():
    setup_signal_handlers()      # SIGINT/SIGTERM → SHUTDOWN.set()
    start_background_workers()   # 6 workers
    while not SHUTDOWN.is_set():
        t0 = time.perf_counter()
        status = build_status(t0)
        atomic_write_json(STATUS_PATH, status)
        elapsed = time.perf_counter() - t0
        SHUTDOWN.wait(max(0.0, TICK_S - elapsed))
    shutdown_background_workers(join_timeout=2.0)
```

---

## 4. Threading model

| Section    | Where it runs        | Interval | TTL / max age before "stale" |
|------------|----------------------|----------|-------------------------------|
| meta       | inline (main)        | 5s       | n/a                           |
| eran       | inline (main)        | 5s       | 15s log freshness threshold   |
| grok1      | inline (main)        | 5s       | n/a                           |
| services   | inline (main)        | 5s       | n/a                           |
| workflow   | inline (main)        | 5s       | journal read is cheap         |
| fleet      | thread `fleet_worker`| 60s      | 180s → mark stale             |
| fabric     | thread `fabric_worker`| 60s     | 180s → mark stale             |
| projects   | thread `project_worker`| 30s    | 120s → mark stale             |
| git        | thread `git_worker`  | 60s      | 180s → mark stale             |
| todo       | thread `todo_worker` | 60s      | 300s → mark stale             |
| system     | thread `system_worker`| 30s     | 120s → mark stale             |

**Total threads**: 1 main + 6 workers = 7. No threadpool needed. Locks: one `RLock` on `CACHE`, one `Lock` on the error ring buffer.

**Determinism**: all worker sleeps are `Event.wait(interval)` so shutdown is under 2s even mid-poll.

**Cold-start behavior**: workers do one gather immediately, don't sleep first. Main loop starts writing after workers had `INITIAL_WARMUP_S = 2.0` — during warmup cached sections are `null` with `cached_at: null`; cockpit renders them as pending, not error.

---

## 5. Error handling philosophy

**Three principles**, in order:

1. **No exception ever leaves a gatherer.** Every gatherer wraps its body in `try/except Exception as e`. On error it:
   - Returns the shape-stable dict with `null` leaves.
   - Sets its own `error` field to `str(e)[:200]`.
   - Calls `push_error(where, msg)` (ring buffer, kept to last 20).
   - Logs to `D:\CLAUDE\almaware-hud\collector.log` (rotated by size, 1MB × 3).

2. **Partial status is fine.** If SSH to `eran3` fails, we still ship `eran1` and `eran2`. If `git` fails, git block gets `error: "..."` and everything else is unaffected. The cockpit is designed to render N/A gracefully.

3. **Never DoS the fleet.** All SSH gathers use `-o BatchMode=yes -o ConnectTimeout=3 -o StrictHostKeyChecking=accept-new` and a *hard* subprocess timeout of 6s. If a host has failed 3 consecutive gathers, its TTL doubles up to 10min (exponential backoff). One success resets it. This honors the **Guarded Autonomy** rule.

**Never trust probe success as evidence of function** (Broken Windows Law): every HTTP probe hits `/health` *and* records the latency; the cockpit's Eran tile also cross-checks that `eran.log` mtime is < 15s old. `up: true` alone is not enough to claim training is progressing.

**Log format** (one line per event, easy to grep):
```
2026-07-11T09:00:00 [INFO ] main  tick_ms=42 stale_sections=0
2026-07-11T09:00:05 [WARN ] fleet.eran3  ssh timeout after 6.0s (fail streak=1)
2026-07-11T09:01:00 [ERROR] git  git.exe not on PATH (traceback in collector.log.1)
```

---

## 6. Startup behavior

Sequence, in order, from `python collector.py`:

1. **Parse args.** `--once` (single tick, exit), `--dry-run` (no write), `--log-level`, `--status-path`.
2. **Resolve config.** Constants defined at top of module — no external config file. Paths, ports, TTLs, SSH host list are all module-level for grep-ability.
3. **Init log file.** Rotating handler, `RotatingFileHandler("collector.log", 1_000_000, 3)`.
4. **Write PID file.** `almaware-hud\collector.pid`. If an existing PID is running, refuse to start (`--force` overrides).
5. **Register signal handlers.** `SIGINT`/`SIGTERM`/`SIGBREAK` → set `SHUTDOWN` event.
6. **Emit `status.json` immediately** with `state: starting` and everything else `null`. This way the cockpit *always* has a file to read from tick 0 — no race, no "file not found" flash.
7. **Start workers.** Each does one immediate gather (so first real tick has fresh cache).
8. **Wait `INITIAL_WARMUP_S = 2.0`** for workers to publish at least once.
9. **Enter main loop.** Every 5s: gather cheap probes, merge cache, write status.
10. **On shutdown**: set `SHUTDOWN`, `join(2.0)` each worker, write final `status.json` with `state: stopping`, delete PID file, exit 0.

**Idempotency**: if the daemon crashes mid-write, `os.replace()` guarantees the reader never sees a truncated file — it either sees the old file or the new one. The `.tmp` file is deleted on normal exit; on crash it's overwritten next tick.

**Assumptions we're allowed to make** (else fail fast at startup with a clear message):
- Python 3.13
- `ssh` on PATH
- `git` on PATH
- Windows PowerShell available for `system_worker`
- Write access to `D:\CLAUDE\almaware-hud\`

If any of these fail, we log a single clear WARNING and *continue* — the corresponding section becomes `null` with `error: "prerequisite missing: git"`. The daemon must survive a bare Windows box.

---

## 7. Constants (top of module — the whole knob panel in one place)

```python
TICK_S = 5.0
INITIAL_WARMUP_S = 2.0
STATUS_PATH = r"D:\CLAUDE\almaware-hud\status.json"
LOG_PATH    = r"D:\CLAUDE\almaware-hud\collector.log"
PID_PATH    = r"D:\CLAUDE\almaware-hud\collector.pid"

ERAN_LOG    = r"D:\CLAUDE\eran-live\eran.log"
WATCH_LOG   = r"D:\CLAUDE\eran-live\watch.log"
ERAN_HTTP   = "http://127.0.0.1:8792/health"

GROK1_SHIM_HTTP    = "http://127.0.0.1:8899/health"
GROK1_BACKEND_HTTP = "http://eran1:8080/health"
GROK1_SHIM_HINT    = "grok1_shim.py"

FLEET_HOSTS = [("eran1","iddo"), ("eran2","iddo"), ("eran3","iddo")]
FABRIC_HOST = "eran2"

SERVICE_PROBES = {
  "eran_http":    ("http", "http://127.0.0.1:8792/health"),
  "grok1_shim":   ("http", GROK1_SHIM_HTTP),
  "grok1_backend":("http", GROK1_BACKEND_HTTP),
  "nachman_rag":  ("http", "http://127.0.0.1:8783/health"),
  "eran_poc":     ("http", "http://127.0.0.1:8781/health"),
  "tailscale":    ("tcp",  "eran1", 41641),
}

PROJECT_ROOTS = [
  ("eran-live", r"D:\CLAUDE\eran-live"),
  ("alma-language", r"D:\CLAUDE\alma-language"),
  # ... ~30 entries from recon
]

TTL_FLEET    = 60.0
TTL_FABRIC   = 60.0
TTL_PROJECTS = 30.0
TTL_GIT      = 60.0
TTL_TODO     = 60.0
TTL_SYSTEM   = 30.0

STALE_FLEET_S    = 180.0
STALE_FABRIC_S   = 180.0
STALE_PROJECTS_S = 120.0

SSH_CONNECT_TIMEOUT = 3
SSH_HARD_TIMEOUT_S  = 6.0
HTTP_TIMEOUT_S      = 1.5
TCP_TIMEOUT_S       = 1.0

ERROR_RING_SIZE = 20
BACKOFF_MAX_S   = 600.0
```

---

## 8. Buildability checklist (what phase-3 needs to compile from this doc)

- [x] Every field in the schema has a defined source and default (`null`).
- [x] Every gatherer has a name, TTL, thread assignment, and error contract.
- [x] Constants are pinned; no magic numbers in prose.
- [x] Shutdown is deterministic (≤2s).
- [x] Atomic writes specified (`os.replace`).
- [x] No third-party deps — every capability maps to a stdlib module:
  - `socket` — TCP probes, DNS
  - `urllib.request` — HTTP probes
  - `subprocess` — ssh, git, powershell
  - `threading` — workers, locks, event
  - `json` — read/write status
  - `os` / `os.path` — mtimes, atomic rename, PID file
  - `time` — tick pacing, TTL math
  - `signal` — SIGINT/SIGTERM
  - `logging` + `logging.handlers.RotatingFileHandler`
  - `argparse` — CLI flags
  - `dataclasses` — ProbeResult/CacheEntry types
  - `collections.deque` — error ring buffer
  - `re` — parse `eran.log` step/loss/tok_s
- [x] Cockpit contract is frozen: no schema drift without a version bump.

**Ready for phase 3 (build).**
