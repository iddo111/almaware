#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
ALMAWARE HUD Collector Daemon — BUILD 2 (per design/collector_design.md).

Long-running Python 3.13 daemon. Reads the world (Eran log, fleet SSH, fabric,
projects on disk, git, workflow journal, local system), builds a single
`status.json` every TICK_S seconds, and atomically writes it to BOTH:

    D:\CLAUDE\almaware-cockpit\status.json    (cockpit sits here, does fetch('./status.json'))
    D:\CLAUDE\almaware-hud\status.json        (HUD widget reads from here)

Rules of engagement:
- stdlib only
- main loop never blocks > ~500ms; slow probes live in worker threads with a TTL cache
- atomic writes via os.replace()
- graceful shutdown on SIGINT / SIGTERM / SIGBREAK
- rotating log at 5MB, keep 3 backups
- partial status is fine: any gatherer failure becomes shape-stable `null` leaves + error string

Do NOT touch (peretz-inquiry workflow files that other agents are writing):
    D:\CLAUDE\grok1_shim.py, script_hebrew.md, music/*, script.md
This daemon only reads log tails and mtimes; it never writes there.
"""

from __future__ import annotations

import argparse
import ctypes
import datetime as _dt
import json
import logging
import logging.handlers
import os
import platform
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

# -----------------------------------------------------------------------------
# THE ONE INVENTORY (2026-09-11). Addresses live in D:\CLAUDE\fleet_inventory.json,
# never in this file. If the inventory is missing we fall back to the ssh alias,
# which ~/.ssh/eran.ssh_config already resolves — so this daemon degrades to
# "still works" rather than "silently probes a dead address".
# -----------------------------------------------------------------------------
sys.path.insert(0, r"D:\CLAUDE")
try:
    import fleet_inventory as _fi
except Exception:                                             # noqa: BLE001
    _fi = None


def _fleet_target(name: str, ssh_alias_fallback: str) -> str:
    """ssh target for a fleet box: the alias if we have one, else best address."""
    if _fi is None:
        return ssh_alias_fallback
    try:
        return _fi.ssh_target(name) or _fi.ip(name, "best") or ssh_alias_fallback
    except Exception:                                         # noqa: BLE001
        return ssh_alias_fallback


def _fleet_door(door_name: str, fallback: str) -> str:
    if _fi is None:
        return fallback
    try:
        return _fi.door(door_name)
    except Exception:                                         # noqa: BLE001
        return fallback


_INV_MTIME: dict[str, Any] = {"m": None}


def _door_retired(door_name: str) -> Optional[str]:
    """The inventory's `retired` reason for a door, or None. Re-reads the file when its
    mtime changes (fleet_inventory.load() otherwise caches forever in a daemon)."""
    if _fi is None:
        return None
    try:
        m = os.path.getmtime(_fi.INVENTORY_PATH)
        force = m != _INV_MTIME["m"]
        _INV_MTIME["m"] = m
        rec = (_fi.load(force=force).get("doors") or {}).get(door_name) or {}
        r = rec.get("retired")
        return str(r)[:240] if r else None
    except Exception:                                         # noqa: BLE001
        return None


# =============================================================================
# 1. CONSTANTS (the whole knob panel — grep-able)
# =============================================================================

TICK_S = 5.0
INITIAL_WARMUP_S = 2.0

# Two write targets: cockpit (canonical, HTML fetch('./status.json')) and HUD.
STATUS_PATH_COCKPIT = r"D:\CLAUDE\almaware-cockpit\status.json"
STATUS_PATH_HUD     = r"D:\CLAUDE\almaware-hud\status.json"

LOG_PATH = r"D:\CLAUDE\almaware-hud\collector.log"
PID_PATH = r"D:\CLAUDE\almaware-hud\collector.pid"
SINGLETON_NAME = r"Local\ALMAWARE_HUD_COLLECTOR_V1"

# Eran (byte-LM) live artifacts
ERAN_LOG    = r"D:\CLAUDE\eran-live\eran.log"
WATCH_LOG   = r"D:\CLAUDE\eran-live\watch.log"
ERAN_HTTP   = "http://127.0.0.1:8792/health"
ERAN_ROOT   = "http://127.0.0.1:8792/"
# THE REAL ERAN. The two lines above point at the PC copy, which has been a corpse
# since 2026-07-11 (its log is 50 days old and :8792 answers nothing). The organism
# lives on eran1 and the only honest proof it is alive is that the BEAT ADVANCES.
# 2026-09-11: http://<lan-ip>:8820 was never right — eranb-serve's window is
# published by `tailscale serve` and :8820 is bound on eran1's TAILSCALE address
# only, so the LAN URL could never answer. Correct door below, from the inventory.
ERAN_LIVE_ROOT = _fleet_door("eran_window", "https://<tailnet-host>:8820/")
ERAN_LIVE_HOST = "eran1"

# Grok-1 shim + backend
GROK1_SHIM_HTTP    = "http://127.0.0.1:8899/health"
GROK1_SHIM_ROOT    = "http://127.0.0.1:8899/"
GROK1_BACKEND_HTTP = "http://<tailnet-ip>:8080/health"  # via tailscale, per recon/services.json
GROK1_SHIM_HINT    = "grok1_shim.py"

# Fleet SSH.
#
# 2026-09-11 (WAVE A2 address sweep): this list used to carry its own hard-coded
# copy of every LAN address, and a router swap on 09-10 silently blinded the
# whole CONTROL fleet panel — eran2 had moved .59 -> .156 and eran4 .8 -> .231.
# It now uses the ssh ALIASES from ~/.ssh/eran.ssh_config, which resolve through
# one file instead of twenty, and the addresses themselves come from
# D:\CLAUDE\fleet_inventory.json (see fleet_inventory.py --refresh).
#
# NEVER put a bare 192.168.x literal back in here. LAN leases drift; ssh aliases
# and tailnet names do not.
FLEET_HOSTS = [
    ("eran1", "eran1", _fleet_target("eran1", "eran1"), None),
    ("eran2", "eran2", _fleet_target("eran2", "eran2"), None),
    ("eran3", "eran3", _fleet_target("eran3", "eran3"), None),
    ("eran4", "eran4", _fleet_target("eran4", "eran4"), None),
]

# THE FABRIC IS ERAN2-CENTRED, not eran1. eran2 carries all four QSFP ports:
# two down to eran1, two across to eran3. eran1's second port has no cable.
# Measured 2026-08-05: 109-110 Gbit/s per link, iperf3, zero retransmits.
FABRIC_TARGET = ("eran2", _fleet_target("eran2", "eran2"), None)

# (edge label, interface on eran2, expected CIDR on eran2, peer IP)
FABRIC_LINKS = [
    ("eran2<->eran1 A", "enp1s0f1np1",   "<fabric-ip>/30", "<fabric-ip>"),
    ("eran2<->eran1 B", "enP2p1s0f1np1", "<fabric-ip>/30", "<fabric-ip>"),
    ("eran2<->eran3 A", "enp1s0f0np0",   "<fabric-ip>/30", "<fabric-ip>"),
    ("eran2<->eran3 B", "enP2p1s0f0np0", "<fabric-ip>/30", "<fabric-ip>"),
]

# RETIRED 2026-09-15 (broken-windows swarm W6). These five were probed every 5 s and
# painted red on CONTROL :8896 for weeks. Measured 2026-09-15 08:5x: no listener on
# 127.0.0.1:8781 / :8783 / :8792 / :8899, and <tailnet-ip>:8080 refuses. They are
# written to status.json under "services_retired" (NOT "services"), so no panel paints
# them red, and they are never probed. To revive one: move its line back into
# SERVICE_PROBES below. Backup: collector.py.bak-bw-20260915.
RETIRED_SERVICES: dict[str, dict] = {
    "eran_http":     {"target": "http://127.0.0.1:8792/",
                      "retired": "PC ERAN copy / chat_server :8792 -- dead since 2026-07-11 (scar); "
                                 "ERAN lives on eran1 and is disabled by Iddo's order 2026-09-11"},
    "grok1_shim":    {"target": GROK1_SHIM_ROOT,
                      "retired": "grok1_shim is gone; 127.0.0.1:8899 is PORTAL now, not a grok-1 shim"},
    "grok1_backend": {"target": GROK1_BACKEND_HTTP,
                      "retired": "no grok-1 backend on eran1:8080 (connection refused 2026-09-15)"},
    "nachman_rag":   {"target": "http://127.0.0.1:8783/health",
                      "retired": "no listener on the PC (measured 2026-09-15)"},
    "eran_poc":      {"target": "http://127.0.0.1:8781/health",
                      "retired": "no listener on the PC (measured 2026-09-15)"},
}

# Uniform service probes
SERVICE_PROBES: dict[str, tuple] = {
    # Tailscale's WireGuard transport is UDP; a TCP connect to 41641 is not a
    # valid health check and produced a false red service row.  Query the local
    # daemon's structured state instead.
    "tailscale":     ("tailscale_status",),
    # Federation wiring (2026-08-10): the revived local services the ERAN
    # federation panel reads through this collector's status.json.
    "quorum":            ("http", "http://127.0.0.1:8099/health"),
    "alma_recall":       ("http", "http://127.0.0.1:8794/"),
    "ant_farm":          ("http", "http://127.0.0.1:8803/"),
    # Probe the panel's root (serves index.html per-request, cheap) — NOT
    # /api/federation.json, which builds a full snapshot and can exceed the
    # 1.5s HTTP probe budget cold.
    "federation_panel":  ("http", "http://127.0.0.1:8895/"),
}

# ~30 projects to watch mtimes for (from recon/projects.json — active + priority set)
PROJECT_ROOTS: list[tuple[str, str]] = [
    ("eran-live",              r"D:\CLAUDE\eran-live"),
    ("eran-hardware",          r"D:\CLAUDE\eran-hardware"),
    ("eran-audio",             r"D:\CLAUDE\eran-audio"),
    ("eran-grid",              r"D:\CLAUDE\eran-grid"),
    ("eran-cloud",             r"D:\CLAUDE\eran-cloud"),
    ("perceptron-movie",       r"D:\CLAUDE\perceptron-movie"),
    ("shisha-lab",             r"D:\CLAUDE\shisha-lab"),
    ("memristor-grid",         r"D:\CLAUDE\memristor-grid"),
    ("protoneuron",            r"D:\CLAUDE\protoneuron"),
    ("alma-language",          r"D:\CLAUDE\alma-language"),
    ("alma-govern",            r"D:\CLAUDE\alma-govern"),
    ("alma-federation",        r"D:\CLAUDE\alma-federation"),
    ("alma-talmud",            r"D:\CLAUDE\alma-talmud"),
    ("alma-brain-sim",         r"D:\CLAUDE\alma-brain-sim"),
    ("alma-mic",               r"D:\CLAUDE\alma-mic"),
    ("alma-ozen",              r"D:\CLAUDE\alma-ozen"),
    ("alma-iff",               r"D:\CLAUDE\alma-iff"),
    ("cave-wall-brain-sim",    r"D:\CLAUDE\cave-wall-brain-sim"),
    ("lora-mesh",              r"D:\CLAUDE\lora-mesh"),
    ("grok1-chat",             r"D:\CLAUDE\grok1-chat"),
    ("grok-web-claws",         r"D:\CLAUDE\grok-web-claws"),
    ("grok-coder",             r"D:\CLAUDE\grok-coder"),
    ("ram-council",            r"D:\CLAUDE\ram-council"),
    ("wa-mcp",                 r"D:\CLAUDE\wa-mcp"),
    ("quorum",                 r"D:\CLAUDE\quorum"),
    ("master-modeler",         r"D:\CLAUDE\master-modeler"),
    ("iddoperez-portal",       r"D:\CLAUDE\iddoperez-portal"),
    ("federation-site",        r"D:\CLAUDE\federation-site"),
    ("fleet",                  r"D:\CLAUDE\fleet"),
    ("almaware-hud",           r"D:\CLAUDE\almaware-hud"),
    ("almaware-cockpit",       r"D:\CLAUDE\almaware-cockpit"),
    ("jetson-lean-os",         r"D:\CLAUDE\jetson-lean-os"),
    # --- added 2026-08-23 -----------------------------------------------------
    # The federation registry was asking the HUD for 17 project keys this list
    # never defined, so 17 real projects showed GRAY as "not tracked yet" on the
    # public panel — including eran-brain, the organism himself. Gray was honest
    # but it was still a hole. Four of the seventeen (philips-10ff2-listener,
    # historical-research-triad-20260803, model-operations-console,
    # semicom-listener) have NO directory on disk and are deliberately left out:
    # inventing a root for a project that does not exist would turn an honest
    # gray into a false green.
    ("eran-brain",             r"D:\CLAUDE\eran-brain"),
    ("eran-federation-app",    r"D:\CLAUDE\eran-federation-app"),
    ("vagabond",               r"D:\CLAUDE\vagabond"),
    ("eran-movie",             r"D:\CLAUDE\eran-movie"),
    ("alma-larynx",            r"D:\CLAUDE\alma-larynx"),
    ("sdr-lab",                r"D:\CLAUDE\sdr-lab"),
    ("alma-optical-perceptron", r"D:\CLAUDE\alma-optical-perceptron"),
    ("alma-pi",                r"D:\CLAUDE\alma-pi"),
    ("physical-ai",            r"D:\CLAUDE\physical-ai"),
    ("alma-tablet",            r"D:\CLAUDE\alma-tablet"),
    ("alma-headscan",          r"D:\CLAUDE\alma-headscan"),
    ("alma-mic-android",       r"D:\CLAUDE\alma-mic-android"),
    ("alma-figure",            r"D:\CLAUDE\alma-figure"),
    ("alma-comfy",             r"D:\CLAUDE\alma-comfy"),
    ("darwish-midi",           r"D:\CLAUDE\darwish-midi"),
    ("almido",                 r"D:\CLAUDE\almido"),
    ("voice-ant-farm",         r"D:\CLAUDE\voice-ant-farm"),
    ("alma-vr",                r"D:\CLAUDE\alma-vr"),
    ("keshev-next",            r"D:\CLAUDE\keshev-next"),
    ("mic-rebuild",            r"D:\CLAUDE\mic-rebuild"),
]

REPO_ROOT = r"D:\CLAUDE"
GIT_MAIN_BRANCH = "main"

# Peretz-inquiry workflow journal — auto-discovered by scanning:
WORKFLOWS_GLOB_ROOT = r"C:\Users\<user>\.claude\projects\D--CLAUDE\a85a27f8-4c6b-4e9e-8a4b-171f7fc94cd0\subagents\workflows"

# TTLs
TTL_FLEET    = 60.0
TTL_FABRIC   = 60.0
TTL_PROJECTS = 30.0
TTL_GIT      = 60.0
TTL_TODO     = 60.0
TTL_SYSTEM   = 30.0

STALE_FLEET_S    = 180.0
STALE_FABRIC_S   = 180.0
STALE_PROJECTS_S = 120.0
STALE_GIT_S      = 180.0
STALE_TODO_S     = 300.0
STALE_SYSTEM_S   = 120.0

SSH_CONNECT_TIMEOUT = 3
SSH_HARD_TIMEOUT_S  = 6.0
# 2026-09-05, measured: the fabric probe is NOT like the other SSH probes. It walks
# 4 QSFP links and each one does `ping -c 2 -W 1`, so ~4.6 s is its NORMAL, healthy
# time (3 runs: 4.54 / 4.60 / 4.60 s) -- 76% of the 6.0 s cap, i.e. no headroom at
# all. Under any load it blows it: the collector's own log shows dt=14177ms against
# the 6.0 s cap, streak=3, and "fabric timeout after 6.0s" recurring for 10 days.
# The fleet probe by comparison uses 0.46-0.58 s of the same 6.0 s (8%), so the cap
# is right for THAT and wrong only here. This worker is on a 60 s TTL / 180 s stale
# threshold and runs in its own thread, so a wider cap delays nothing.
SSH_FABRIC_TIMEOUT_S = 20.0
HTTP_TIMEOUT_S      = 1.5
TCP_TIMEOUT_S       = 1.0

ERROR_RING_SIZE = 20
BACKOFF_MAX_S   = 600.0
LOG_MAX_BYTES   = 5 * 1024 * 1024   # 5 MB per task spec (design said 1MB; task overrides)
LOG_BACKUPS     = 3

SCHEMA_VERSION = 1

# =============================================================================
# 2. GLOBAL STATE (locks, shutdown event, error ring, cache, start time)
# =============================================================================

SHUTDOWN = threading.Event()
_CACHE_LOCK = threading.RLock()
_CACHE: dict[str, tuple[Optional[float], Any]] = {}   # key -> (cached_at, value)

_ERR_LOCK = threading.Lock()
_ERR_RING: deque = deque(maxlen=ERROR_RING_SIZE)

_START_TIME = time.time()
_START_PERF = time.perf_counter()

log = logging.getLogger("collector")

_SINGLETON_HANDLE: Optional[int] = None


# =============================================================================
# 3. HELPERS: probes, tail, atomic write, error ring
# =============================================================================

@dataclass
class ProbeResult:
    up: bool
    latency_ms: Optional[float]
    checked_at: float
    error: Optional[str] = None
    status_code: Optional[int] = None
    body_sample: Optional[str] = None


def http_probe(url: str, timeout: float = HTTP_TIMEOUT_S,
               want_body: bool = False) -> ProbeResult:
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "almaware-collector/1"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            code = r.getcode()
            body_sample = None
            if want_body:
                try:
                    body_sample = r.read(512).decode("utf-8", "replace")
                except Exception:
                    body_sample = None
            latency_ms = (time.perf_counter() - t0) * 1000.0
            return ProbeResult(
                up=200 <= code < 500,   # 4xx still means the server is UP
                latency_ms=round(latency_ms, 2),
                checked_at=time.time(),
                error=None,
                status_code=code,
                body_sample=body_sample,
            )
    except urllib.error.HTTPError as e:
        latency_ms = (time.perf_counter() - t0) * 1000.0
        # HTTPError means we got an HTTP response — server is up.
        return ProbeResult(
            up=True,
            latency_ms=round(latency_ms, 2),
            checked_at=time.time(),
            error=f"HTTP {e.code}",
            status_code=e.code,
        )
    except Exception as e:
        return ProbeResult(
            up=False,
            latency_ms=None,
            checked_at=time.time(),
            error=str(e)[:200],
        )


def tcp_probe(host: str, port: int, timeout: float = TCP_TIMEOUT_S) -> ProbeResult:
    t0 = time.perf_counter()
    try:
        s = socket.create_connection((host, port), timeout=timeout)
        s.close()
        latency_ms = (time.perf_counter() - t0) * 1000.0
        return ProbeResult(
            up=True,
            latency_ms=round(latency_ms, 2),
            checked_at=time.time(),
        )
    except Exception as e:
        return ProbeResult(
            up=False,
            latency_ms=None,
            checked_at=time.time(),
            error=str(e)[:200],
        )


def tailscale_status_probe(timeout: float = HTTP_TIMEOUT_S) -> ProbeResult:
    """Validate the local Tailscale daemon without assuming a TCP transport."""
    t0 = time.perf_counter()
    rc, stdout, stderr = _run_subprocess(
        ["tailscale", "status", "--json"], timeout=timeout,
    )
    checked_at = time.time()
    if rc != 0:
        return ProbeResult(
            up=False,
            latency_ms=None,
            checked_at=checked_at,
            error=(stderr or stdout or f"tailscale exited {rc}")[:200],
        )
    try:
        payload = json.loads(stdout)
        backend_state = payload.get("BackendState")
        self_online = bool((payload.get("Self") or {}).get("Online"))
        up = backend_state == "Running" and self_online
        latency_ms = (time.perf_counter() - t0) * 1000.0
        summary = json.dumps(
            {"backend_state": backend_state, "self_online": self_online},
            separators=(",", ":"),
        )
        return ProbeResult(
            up=up,
            latency_ms=round(latency_ms, 2),
            checked_at=checked_at,
            error=None if up else f"BackendState={backend_state}; Self.Online={self_online}",
            body_sample=summary,
        )
    except (TypeError, ValueError, json.JSONDecodeError) as e:
        return ProbeResult(
            up=False,
            latency_ms=None,
            checked_at=checked_at,
            error=f"invalid tailscale status JSON: {e}"[:200],
        )


def tail_file(path: str, n_lines: int = 8, chunk: int = 65536) -> list[str]:
    """Binary-safe reverse tail. Never raises."""
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            data = b""
            pos = size
            while pos > 0 and data.count(b"\n") <= n_lines:
                step = min(chunk, pos)
                pos -= step
                f.seek(pos)
                data = f.read(step) + data
                if size - pos > 4 * 1024 * 1024:  # safety cap 4 MB
                    break
        text = data.decode("utf-8", "replace")
        lines = [ln for ln in text.splitlines() if ln.strip()]
        return lines[-n_lines:]
    except Exception:
        return []


ERAN_RE_FULL = re.compile(
    r"step\s+([\d,]+)\s+\|\s+loss\s+([\d.]+)"
    r".*?(?:tok/s|toks?/s|steps/s|sps)"
)
ERAN_RE_STEP = re.compile(r"step\s+([\d,]+)", re.IGNORECASE)
ERAN_RE_LOSS = re.compile(r"loss\s+([\d.]+)", re.IGNORECASE)
ERAN_RE_TOK  = re.compile(r"(\d+(?:\.\d+)?)\s*k?\s*tok/s", re.IGNORECASE)
ERAN_RE_SPS  = re.compile(r"(\d+(?:\.\d+)?)\s*steps?/s", re.IGNORECASE)


def parse_eran_line(line: str) -> dict:
    """Extract step / loss / tok_s / steps_per_s from an eran.log line. Never raises."""
    out: dict[str, Any] = {"step": None, "loss": None, "tok_s": None, "steps_per_s": None}
    if not line:
        return out
    try:
        m = ERAN_RE_STEP.search(line)
        if m:
            out["step"] = int(m.group(1).replace(",", ""))
    except Exception:
        pass
    try:
        m = ERAN_RE_LOSS.search(line)
        if m:
            out["loss"] = float(m.group(1))
    except Exception:
        pass
    try:
        m = ERAN_RE_TOK.search(line)
        if m:
            val = float(m.group(1))
            if "k" in line[m.start():m.end()].lower():
                val *= 1000.0
            out["tok_s"] = val
    except Exception:
        pass
    try:
        m = ERAN_RE_SPS.search(line)
        if m:
            out["steps_per_s"] = float(m.group(1))
    except Exception:
        pass
    return out


def push_error(where: str, msg: str) -> None:
    with _ERR_LOCK:
        _ERR_RING.append({
            "ts": time.time(),
            "where": where,
            "msg": str(msg)[:300],
        })
    try:
        log.warning("%s  %s", where, str(msg)[:300])
    except Exception:
        pass


def atomic_write_json(path: str, data: Any) -> None:
    """Write JSON atomically. Never raises."""
    try:
        d = os.path.dirname(path)
        if d and not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=False, default=str)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        os.replace(tmp, path)
    except Exception as e:
        push_error("atomic_write_json", f"{path}: {e}")


def _cache_get(key: str) -> tuple[Optional[float], Any]:
    with _CACHE_LOCK:
        return _CACHE.get(key, (None, None))


def _cache_set(key: str, value: Any) -> None:
    with _CACHE_LOCK:
        _CACHE[key] = (time.time(), value)


def _cache_age(key: str) -> Optional[float]:
    ts, _ = _cache_get(key)
    if ts is None:
        return None
    return time.time() - ts


def _run_subprocess(cmd: list[str], timeout: float, cwd: Optional[str] = None) -> tuple[int, str, str]:
    """Run a subprocess with hard timeout. Windows: no console window."""
    creationflags = 0
    if os.name == "nt":
        # CREATE_NO_WINDOW
        creationflags = 0x08000000
    try:
        p = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            cwd=cwd,
            creationflags=creationflags,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return p.returncode, p.stdout or "", p.stderr or ""
    except subprocess.TimeoutExpired as e:
        return 124, "", f"timeout after {timeout}s"
    except FileNotFoundError as e:
        return 127, "", f"not found: {cmd[0]}"
    except Exception as e:
        return 1, "", str(e)[:200]


def ssh_run(user: str, host: str, remote_cmd: str,
            timeout: float = SSH_HARD_TIMEOUT_S,
            proxy_jump: str | None = None) -> tuple[int, str, str]:
    """Run a command over SSH with hard timeouts and BatchMode."""
    cmd = [
        "ssh",
        "-o", "BatchMode=yes",
        f"-o", f"ConnectTimeout={SSH_CONNECT_TIMEOUT}",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", f"ServerAliveInterval=2",
    ]
    if proxy_jump:
        cmd.extend(["-J", proxy_jump])
    cmd.extend([f"{user}@{host}", remote_cmd])
    return _run_subprocess(cmd, timeout=timeout)


def _now_iso_local() -> str:
    ts = time.time()
    # Israel = UTC+3 (July / DST)
    try:
        # Prefer OS local time (Windows will match user's clock)
        return _dt.datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds")
    except Exception:
        return _dt.datetime.utcfromtimestamp(ts).isoformat(timespec="seconds") + "Z"


# =============================================================================
# 4. EVERY-TICK GATHERERS (cheap, inline, sub-500ms)
# =============================================================================

def gather_meta(tick_start_perf: float) -> dict:
    try:
        elapsed_ms = round((time.perf_counter() - tick_start_perf) * 1000.0, 2)
    except Exception:
        elapsed_ms = None
    return {
        "version": SCHEMA_VERSION,
        "ts": time.time(),
        "ts_iso": _now_iso_local(),
        "collector_pid": os.getpid(),
        "collector_uptime_s": round(time.time() - _START_TIME, 1),
        "tick_ms": elapsed_ms,
        "stale": False,   # patched at write time if any critical section is beyond STALE_*
        "host": platform.node(),
    }


_ERAN_BEAT_PREV: dict[str, Any] = {"beat": None, "ts": None}


def _eran_live_probe(timeout: float = 2.5) -> dict:
    """Ask the organism itself. A port that answers is NOT proof; an advancing beat is.

    Returns state one of: alive | frozen | down. `frozen` is the case the old collector
    could not express at all — the window serves, the organism has stopped.
    """
    out = {"host": ERAN_LIVE_HOST, "url": ERAN_LIVE_ROOT, "up": False, "state": "down",
           "beat": None, "beats_per_s": None, "unit": None, "prototypes": None,
           "mass": None, "energy": None, "latency_ms": None, "error": None}
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(ERAN_LIVE_ROOT,
                                     headers={"User-Agent": "almaware-collector/1"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read(2048).decode("utf-8", "replace")
        out["up"] = True
        out["latency_ms"] = round((time.perf_counter() - t0) * 1000.0, 2)
    except Exception as e:
        out["error"] = str(e)[:200]
        return out

    def grab(pat, cast=float):
        m = re.search(pat, body)
        if not m:
            return None
        try:
            return cast(m.group(1))
        except Exception:
            return None

    out["beat"] = grab(r"beat\s+(\d+)", int)
    out["prototypes"] = grab(r"prototypes\s+(\d+)", int)
    out["mass"] = grab(r"mass\s+([\d.]+)")
    out["energy"] = grab(r"energy\s+([\d.eE+-]+)")
    out["unit"] = grab(r"unit\s*<b>([^<]+)</b>", str)

    now = time.time()
    prev_beat, prev_ts = _ERAN_BEAT_PREV["beat"], _ERAN_BEAT_PREV["ts"]
    if out["beat"] is not None:
        if prev_beat is not None and prev_ts is not None and now > prev_ts:
            delta = out["beat"] - prev_beat
            out["beats_per_s"] = round(delta / (now - prev_ts), 1)
            # one tick of no movement is not a verdict; 30 s of it is.
            if delta > 0:
                out["state"] = "alive"
            elif (now - prev_ts) >= 30:
                out["state"] = "frozen"
            else:
                out["state"] = "alive"
        else:
            out["state"] = "alive"          # first sample: served a beat, nothing to compare
        if prev_beat is None or out["beat"] != prev_beat:
            _ERAN_BEAT_PREV["beat"], _ERAN_BEAT_PREV["ts"] = out["beat"], now
    else:
        out["state"] = "frozen"             # window answered but carried no beat
        out["error"] = "no beat in page"
    return out


def gather_eran() -> dict:
    """Read eran.log + watch.log tails + probe local :8792. Sub-500ms."""
    out: dict[str, Any] = {
        "state": "unknown",
        "http": {"port": 8792, "up": False, "latency_ms": None, "checked_at": time.time(), "error": None},
        "log_tail": {"path": ERAN_LOG, "last_line": None, "last_mtime": None, "age_s": None, "recent_lines": []},
        "watch_tail": {"path": WATCH_LOG, "last_line": None, "last_mtime": None, "age_s": None},
        "step": None, "loss": None, "tok_s": None, "steps_per_s": None,
        "vram_gb": None,   # supplied by fleet worker
        "error": None,
    }
    # 2026-09-15 (W6): the PC :8792 copy is retired -- not probed (see RETIRED_SERVICES).
    out["http"].update(up=None, retired=RETIRED_SERVICES["eran_http"]["retired"])

    # eran.log
    try:
        if os.path.isfile(ERAN_LOG):
            st = os.stat(ERAN_LOG)
            mtime = st.st_mtime
            age = time.time() - mtime
            lines = tail_file(ERAN_LOG, n_lines=8)
            last = lines[-1] if lines else None
            out["log_tail"].update(
                last_line=last, last_mtime=mtime, age_s=round(age, 2),
                recent_lines=lines,
            )
            if last:
                parsed = parse_eran_line(last)
                for k, v in parsed.items():
                    if v is not None:
                        out[k] = v
            # The PC copy's log age says nothing about the organism; it only says how
            # long ago this machine stopped being where ERAN lives.
            out["log_tail"]["note"] = ("PC ARCHIVE - not the live organism. "
                                       "ERAN lives on %s." % ERAN_LIVE_HOST)
            out["log_tail"]["dead"] = age > 86400
        else:
            out["log_tail"]["error"] = "eran.log not found"
            out["state"] = "unknown"
    except Exception as e:
        push_error("eran.log_tail", e)
        out["log_tail"]["error"] = str(e)[:200]

    # THE ONE THAT COUNTS
    # 2026-09-15 (W6): Iddo ordered ERAN disabled + archived (2026-09-11), and the
    # inventory now marks the eran_window door retired. Probing a window that is off
    # by order is not a health check -- it painted ERAN red and set meta.degraded
    # forever. If the inventory un-retires the door, this probe comes straight back.
    eran_retired = _door_retired("eran_window")
    if eran_retired:
        out["live"] = {"host": ERAN_LIVE_HOST, "url": ERAN_LIVE_ROOT, "up": None,
                       "state": "retired", "retired": eran_retired, "error": None}
        out["state"] = "retired"
        return out
    try:
        live = _eran_live_probe()
        out["live"] = live
        out["state"] = live["state"]          # alive | frozen | down - never "idle"
        if live.get("beat") is not None:
            out["beat"] = live["beat"]
            out["beats_per_s"] = live["beats_per_s"]
            out["unit"] = live["unit"]
    except Exception as e:
        push_error("eran.live", e)
        out["live"] = {"up": False, "state": "down", "error": str(e)[:200]}
        out["state"] = "down"

    # watch.log
    try:
        if os.path.isfile(WATCH_LOG):
            st = os.stat(WATCH_LOG)
            mtime = st.st_mtime
            age = time.time() - mtime
            lines = tail_file(WATCH_LOG, n_lines=1)
            last = lines[-1] if lines else None
            out["watch_tail"].update(last_line=last, last_mtime=mtime, age_s=round(age, 2))
    except Exception as e:
        push_error("eran.watch_tail", e)

    return out


def _scan_tasklist_for(hint: str) -> Optional[dict]:
    """Look through tasklist.exe /v output for a python process whose CMD line
    contains `hint`. Windows-only helper. Never raises."""
    if os.name != "nt":
        return None
    try:
        # tasklist /v /fo csv on Windows gives image name, PID, etc — but the
        # commandline is truncated. Use wmic (still present on Win11) — falls back to None on failure.
        rc, stdout, stderr = _run_subprocess(
            ["wmic", "process", "where", f"CommandLine like '%%{hint}%%'", "get",
             "ProcessId,Name,CommandLine", "/format:csv"],
            timeout=3.0,
        )
        if rc != 0 or not stdout.strip():
            return None
        for row in stdout.splitlines():
            row = row.strip()
            if not row or "ProcessId" in row or row.startswith("Node,"):
                continue
            parts = row.split(",")
            if len(parts) >= 4:
                cmdline = parts[-3] if len(parts) >= 4 else ""
                name = parts[-2]
                pid_s = parts[-1]
                if hint in cmdline:
                    try:
                        return {"pid": int(pid_s), "name": name, "cmdline_hint": hint}
                    except ValueError:
                        continue
    except Exception:
        return None
    return None


def gather_grok1() -> dict:
    # RETIRED 2026-09-15 (W6): no grok-1 shim and no grok-1 backend exist any more
    # (see RETIRED_SERVICES). Returning the retired record here stops two HTTP probes
    # and a wmic process scan every tick. The old body is kept below, unreachable,
    # as the restore line: delete this return to bring the probe back.
    return {
        "retired": RETIRED_SERVICES["grok1_shim"]["retired"],
        "shim": {"port": 8899, "up": None, "retired": RETIRED_SERVICES["grok1_shim"]["retired"]},
        "backend": {"url": GROK1_BACKEND_HTTP, "up": None,
                    "retired": RETIRED_SERVICES["grok1_backend"]["retired"]},
        "context_injection": {"loaded": None, "source_mtime": None},
    }
    out: dict[str, Any] = {
        "shim": {
            "port": 8899,
            "up": False, "latency_ms": None, "checked_at": time.time(),
            "process": None,
            "error": None,
        },
        "backend": {
            "url": GROK1_BACKEND_HTTP,
            "up": False, "latency_ms": None, "checked_at": time.time(),
            "via": "tailscale",
            "error": None,
        },
        "context_injection": {
            "loaded": None,
            "source_mtime": None,
        },
    }
    # Shim
    try:
        p = http_probe(GROK1_SHIM_ROOT, timeout=HTTP_TIMEOUT_S)
        out["shim"].update(up=p.up, latency_ms=p.latency_ms,
                            checked_at=p.checked_at, error=p.error)
    except Exception as e:
        out["shim"]["error"] = str(e)[:200]

    # Shim process (best-effort; cached ~60s to keep tick fast — wmic is 1-2s)
    try:
        ts, cached = _cache_get("_grok1_shim_proc")
        if cached is None or (ts and time.time() - ts > 60.0):
            # Refresh in a short-lived background thread so this tick doesn't wait
            def _refresh_proc():
                try:
                    proc = _scan_tasklist_for(GROK1_SHIM_HINT)
                    _cache_set("_grok1_shim_proc", proc)
                except Exception:
                    _cache_set("_grok1_shim_proc", None)
            threading.Thread(target=_refresh_proc, name="grok1.proc_refresh",
                             daemon=True).start()
        out["shim"]["process"] = cached
    except Exception:
        pass

    # Backend
    try:
        p = http_probe(GROK1_BACKEND_HTTP, timeout=HTTP_TIMEOUT_S)
        out["backend"].update(up=p.up, latency_ms=p.latency_ms,
                               checked_at=p.checked_at, error=p.error)
    except Exception as e:
        out["backend"]["error"] = str(e)[:200]

    # Context injection: check grok1_context.py mtime as proxy
    ctx_py = r"D:\CLAUDE\grok1_context.py"
    try:
        if os.path.isfile(ctx_py):
            st = os.stat(ctx_py)
            out["context_injection"]["source_mtime"] = st.st_mtime
            out["context_injection"]["loaded"] = out["shim"]["up"]  # only meaningful if shim is up
    except Exception:
        pass

    return out


def gather_services() -> dict:
    """Uniform HTTP/TCP probe dict. All probes run in parallel so a slow/down
    endpoint doesn't stall the main tick."""
    out: dict[str, Any] = {}
    results_lock = threading.Lock()

    def _do_one(name: str, spec: tuple) -> None:
        try:
            if spec[0] == "http":
                target = spec[1]
                p = http_probe(target, timeout=HTTP_TIMEOUT_S)
                rec = {
                    "kind": "http", "target": target,
                    "up": p.up, "latency_ms": p.latency_ms,
                    "checked_at": p.checked_at, "error": p.error,
                    "status_code": p.status_code,
                }
            elif spec[0] == "tcp":
                host, port = spec[1], spec[2]
                p = tcp_probe(host, int(port), timeout=TCP_TIMEOUT_S)
                rec = {
                    "kind": "tcp", "target": f"{host}:{port}",
                    "up": p.up, "latency_ms": p.latency_ms,
                    "checked_at": p.checked_at, "error": p.error,
                }
            elif spec[0] == "tailscale_status":
                p = tailscale_status_probe(timeout=HTTP_TIMEOUT_S)
                details = {}
                if p.body_sample:
                    try:
                        details = json.loads(p.body_sample)
                    except (TypeError, ValueError, json.JSONDecodeError):
                        details = {}
                rec = {
                    "kind": "tailscale_status",
                    "target": "local tailscale daemon",
                    "up": p.up, "latency_ms": p.latency_ms,
                    "checked_at": p.checked_at, "error": p.error,
                    **details,
                }
            else:
                rec = {"kind": "unknown", "target": None, "up": False,
                       "latency_ms": None, "checked_at": time.time(),
                       "error": f"unknown probe kind: {spec[0]}"}
        except Exception as e:
            rec = {"kind": spec[0], "target": str(spec[1:]),
                   "up": False, "latency_ms": None,
                   "checked_at": time.time(), "error": str(e)[:200]}
            push_error(f"services.{name}", e)
        with results_lock:
            out[name] = rec

    threads = []
    for name, spec in SERVICE_PROBES.items():
        t = threading.Thread(target=_do_one, args=(name, spec),
                             name=f"probe.{name}", daemon=True)
        t.start()
        threads.append(t)
    # Join with a hard cap so the tick can never exceed the biggest probe timeout by much
    deadline = time.time() + max(HTTP_TIMEOUT_S, TCP_TIMEOUT_S) + 0.5
    for t in threads:
        remaining = max(0.05, deadline - time.time())
        t.join(timeout=remaining)
    # Any probe that didn't finish becomes an explicit "unknown" record
    for name in SERVICE_PROBES:
        if name not in out:
            out[name] = {
                "kind": SERVICE_PROBES[name][0], "target": None,
                "up": False, "latency_ms": None,
                "checked_at": time.time(),
                "error": "probe did not return in tick budget",
            }
    return out


def _find_latest_workflow_dir() -> Optional[str]:
    try:
        if not os.path.isdir(WORKFLOWS_GLOB_ROOT):
            return None
        entries = []
        for name in os.listdir(WORKFLOWS_GLOB_ROOT):
            full = os.path.join(WORKFLOWS_GLOB_ROOT, name)
            if os.path.isdir(full):
                entries.append((os.path.getmtime(full), full))
        if not entries:
            return None
        entries.sort(reverse=True)
        return entries[0][1]
    except Exception:
        return None


def gather_workflow() -> dict:
    """Tail peretz-inquiry workflow journal.jsonl if present."""
    out: dict[str, Any] = {
        "peretz_inquiry": {
            "journal_path": None,
            "cached_at": time.time(),
            "cache_age_s": 0.0,
            "last_event": None,
            "recent_events": [],
            "counts": {"queued": 0, "running": 0, "done": 0, "failed": 0},
            "error": None,
        }
    }
    try:
        wf_dir = _find_latest_workflow_dir()
        if not wf_dir:
            out["peretz_inquiry"]["error"] = "no workflow dir found"
            return out
        journal = os.path.join(wf_dir, "journal.jsonl")
        out["peretz_inquiry"]["journal_path"] = journal
        if not os.path.isfile(journal):
            out["peretz_inquiry"]["error"] = "journal.jsonl not found"
            return out
        lines = tail_file(journal, n_lines=20)
        events = []
        for ln in lines:
            try:
                obj = json.loads(ln)
                events.append(obj)
            except Exception:
                continue
        out["peretz_inquiry"]["recent_events"] = events[-10:]
        out["peretz_inquiry"]["last_event"] = events[-1] if events else None
        counts = {"queued": 0, "running": 0, "done": 0, "failed": 0}
        for ev in events:
            status = str(ev.get("status", "")).lower()
            if status in counts:
                counts[status] += 1
            elif "complete" in status:
                counts["done"] += 1
            elif "fail" in status or "error" in status:
                counts["failed"] += 1
            elif "run" in status or "progress" in status:
                counts["running"] += 1
        out["peretz_inquiry"]["counts"] = counts
    except Exception as e:
        out["peretz_inquiry"]["error"] = str(e)[:200]
        push_error("workflow", e)
    return out


# =============================================================================
# 5. BACKGROUND-CACHED GATHERERS (each in its own thread)
# =============================================================================

def gather_fleet() -> dict:
    """SSH each host and collect uptime / load / mem / gpu. TTL 60s."""
    out: dict[str, Any] = {}
    remote_cmd = (
        "uptime; "
        "echo '---MEM---'; free -b | grep Mem; "
        "echo '---HOST---'; hostname; "
        "echo '---GPU---'; "
        "nvidia-smi --query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw "
        "--format=csv,noheader,nounits 2>/dev/null || echo NOGPU"
    )
    for name, user, addr, proxy_jump in FLEET_HOSTS:
        entry = {
            "reachable": False,
            "cached_at": time.time(),
            "hostname": None, "uptime_s": None,
            "load": None, "mem": None, "gpu": [], "cpu": None,
            "error": None,
        }
        try:
            rc, stdout, stderr = ssh_run(
                user, addr, remote_cmd,
                timeout=SSH_HARD_TIMEOUT_S,
                proxy_jump=proxy_jump,
            )
            if rc != 0:
                entry["error"] = (stderr or f"rc={rc}").strip()[:200]
                push_error(f"fleet.{name}", entry["error"])
                out[name] = entry
                continue
            entry["reachable"] = True
            # Parse the marker-delimited blocks without losing the content
            # between opening/closing dashes.
            sections: dict[str, list[str]] = {"UPTIME": []}
            current = "UPTIME"
            for line in stdout.splitlines():
                marker = line.strip()
                if marker in ("---MEM---", "---HOST---", "---GPU---"):
                    current = marker.strip("-")
                    sections.setdefault(current, [])
                    continue
                sections.setdefault(current, []).append(line)

            head = "\n".join(sections.get("UPTIME", []))
            m = re.search(r"load average:\s*([\d.]+),\s*([\d.]+),\s*([\d.]+)", head)
            if m:
                entry["load"] = [float(m.group(1)), float(m.group(2)), float(m.group(3))]
            m2 = re.search(r"up\s+([^,]+)", head)
            # (we don't parse absolute uptime seconds — cheap; skip)

            for section_name, section_lines in sections.items():
                body = "\n".join(section_lines).strip()
                if section_name == "MEM":
                    m3 = re.search(r"Mem:\s+(\d+)\s+(\d+)", body)
                    if m3:
                        total_b = int(m3.group(1)); used_b = int(m3.group(2))
                        entry["mem"] = {
                            "used_gb": round(used_b / 1e9, 2),
                            "total_gb": round(total_b / 1e9, 2),
                            "pct": round(used_b / total_b * 100.0, 1) if total_b else None,
                        }
                elif section_name == "HOST":
                    entry["hostname"] = body.strip().splitlines()[0] if body.strip() else None
                elif section_name == "GPU":
                    for row in body.strip().splitlines():
                        row = row.strip()
                        if not row or row == "NOGPU":
                            continue
                        parts = [p.strip() for p in row.split(",")]
                        if len(parts) >= 6:
                            try:
                                def _number(value: str) -> float | None:
                                    return None if value in ("[N/A]", "N/A", "") else float(value)

                                mem_used = _number(parts[3])
                                mem_total = _number(parts[4])
                                power_w = _number(parts[6]) if len(parts) >= 7 else None
                                entry["gpu"].append({
                                    "index": int(parts[0]),
                                    "name": parts[1],
                                    "util_pct": int(float(parts[2])),
                                    "mem_used_gb": round(mem_used / 1024.0, 2) if mem_used is not None else None,
                                    "mem_total_gb": round(mem_total / 1024.0, 2) if mem_total is not None else None,
                                    "temp_c": int(float(parts[5])),
                                    "power_w": round(power_w, 2) if power_w is not None else None,
                                })
                            except ValueError:
                                continue
        except Exception as e:
            entry["error"] = str(e)[:200]
            push_error(f"fleet.{name}", e)
        out[name] = entry
    return out


def gather_fabric() -> dict:
    """Validate the two physical 200G fabric links from Eran1. TTL 60s.

    A link is shown as up only when its expected /30 address, 200G carrier,
    and direct peer ping all pass.  The routed Eran2<->Eran3 path is not a
    physical cable and is deliberately omitted from ``links``.
    """
    out: dict[str, Any] = {
        "cached_at": time.time(),
        "hub": "eran1",
        "links": {},
        "raw": None,
        "error": None,
    }
    try:
        fabric_user, fabric_host, fabric_proxy = FABRIC_TARGET
        # Build the probe from FABRIC_LINKS so adding a cable is a one-line change.
        parts = []
        for idx, (_label, iface, _cidr, peer) in enumerate(FABRIC_LINKS):
            parts.append(
                "printf '%%s\\n' '===LINK%d==='; "
                "ip -o link show dev %s 2>&1; "
                "ip -o -4 addr show dev %s 2>&1; "
                "ethtool %s 2>/dev/null | grep -E 'Speed:|Link detected:'; "
                "if ping -I %s -c 2 -W 1 %s >/dev/null 2>&1; "
                "then echo 'peer_ping=up'; else echo 'peer_ping=down'; fi"
                % (idx, iface, iface, iface, iface, peer)
            )
        remote_cmd = "; ".join(parts)
        rc, stdout, stderr = ssh_run(
            fabric_user, fabric_host,
            remote_cmd,
            timeout=SSH_FABRIC_TIMEOUT_S,
            proxy_jump=fabric_proxy,
        )
        if rc != 0:
            out["error"] = (stderr or f"rc={rc}").strip()[:200]
            push_error("fabric", out["error"])
            return out
        out["raw"] = stdout[:2500]

        def _section(start_marker: str, end_marker: str | None = None) -> str:
            if start_marker not in stdout:
                return ""
            body = stdout.split(start_marker, 1)[1]
            if end_marker and end_marker in body:
                body = body.split(end_marker, 1)[0]
            return body

        def _link_evidence(section: str, interface: str,
                           expected_cidr: str, peer: str) -> dict[str, Any]:
            link_line = next(
                (line for line in section.splitlines()
                 if f": {interface}:" in line),
                "",
            )
            carrier = (
                "LOWER_UP" in link_line
                and "state UP" in link_line
                and bool(re.search(r"Link detected:\s*yes", section, re.I))
            )
            ip_configured = f"inet {expected_cidr}" in section
            peer_ping = "peer_ping=up" in section
            speed_match = re.search(r"Speed:\s*(\d+)\s*Mb/s", section, re.I)
            speed_gbps = (
                round(int(speed_match.group(1)) / 1000)
                if speed_match else None
            )
            speed_ok = speed_gbps == 200

            failures = []
            if not carrier:
                failures.append("carrier")
            if not ip_configured:
                failures.append("address")
            if not speed_ok:
                failures.append("speed")
            if not peer_ping:
                failures.append("peer_ping")

            link: dict[str, Any] = {
                "state": "up" if not failures else "down",
                "speed_gbps": speed_gbps,
                "errors": len(failures),
                "interface": interface,
                "expected_cidr": expected_cidr,
                "peer": peer,
                "carrier": carrier,
                "ip_configured": ip_configured,
                "peer_ping": peer_ping,
            }
            if failures:
                link["note"] = "failed evidence: " + ", ".join(failures)
            return link

        for idx, (label, iface, cidr, peer) in enumerate(FABRIC_LINKS):
            start = "===LINK%d===" % idx
            end = "===LINK%d===" % (idx + 1) if idx + 1 < len(FABRIC_LINKS) else None
            out["links"][label] = _link_evidence(
                _section(start, end), iface, cidr, peer,
            )
        out["note"] = (
            "Physical QSFP links, probed from eran2 (the hub). Two legs to eran1, "
            "two to eran3. eran1's second port has no cable. eran4 is LAN-only, "
            "no ConnectX fabric. Measured 109-110 Gbit/s per link on 2026-08-05."
        )
    except Exception as e:
        out["error"] = str(e)[:200]
        push_error("fabric", e)
    return out


def gather_projects() -> dict:
    out: dict[str, Any] = {
        "cached_at": time.time(),
        "items": {},
        "error": None,
    }
    try:
        now = time.time()
        for pid, root in PROJECT_ROOTS:
            item = {
                "path": root, "exists": False,
                "last_mtime": None, "age_s": None, "active": False,
                "file_count": None,
            }
            try:
                if os.path.isdir(root):
                    item["exists"] = True
                    latest_mtime = 0.0
                    count = 0
                    # Shallow-plus-one-level scan: root + top-level children (dirs and files).
                    # For each top-level *child dir*, take its own mtime only (cheap).
                    with os.scandir(root) as it:
                        for entry in it:
                            try:
                                st = entry.stat(follow_symlinks=False)
                                if st.st_mtime > latest_mtime:
                                    latest_mtime = st.st_mtime
                                count += 1
                            except OSError:
                                continue
                    # root's own mtime too
                    try:
                        root_mt = os.path.getmtime(root)
                        if root_mt > latest_mtime:
                            latest_mtime = root_mt
                    except OSError:
                        pass
                    if latest_mtime > 0:
                        item["last_mtime"] = latest_mtime
                        age = now - latest_mtime
                        item["age_s"] = round(age, 1)
                        item["active"] = age < 86400 * 2   # touched in last 48h
                    item["file_count"] = count
            except Exception as e:
                item["error"] = str(e)[:200]
                push_error(f"projects.{pid}", e)
            out["items"][pid] = item
    except Exception as e:
        out["error"] = str(e)[:200]
        push_error("projects", e)
    return out


def gather_git() -> dict:
    out: dict[str, Any] = {
        "cached_at": time.time(),
        "branch": None, "main_branch": GIT_MAIN_BRANCH,
        "ahead": None, "behind": None,
        "dirty_count": None, "staged_count": None, "untracked_count": None,
        "last_commit": None, "recent_commits": [],
        "error": None,
    }
    if not shutil.which("git"):
        out["error"] = "git not on PATH"
        return out
    try:
        # Current branch
        rc, stdout, _ = _run_subprocess(
            ["git", "-C", REPO_ROOT, "rev-parse", "--abbrev-ref", "HEAD"],
            timeout=3.0,
        )
        if rc == 0:
            out["branch"] = stdout.strip() or None

        # ahead / behind
        rc, stdout, _ = _run_subprocess(
            ["git", "-C", REPO_ROOT, "rev-list", "--left-right", "--count",
             f"origin/{GIT_MAIN_BRANCH}...HEAD"],
            timeout=3.0,
        )
        if rc == 0 and stdout.strip():
            try:
                behind, ahead = stdout.strip().split()
                out["ahead"] = int(ahead); out["behind"] = int(behind)
            except Exception:
                pass

        # status --porcelain
        rc, stdout, _ = _run_subprocess(
            ["git", "-C", REPO_ROOT, "status", "--porcelain=v1", "--untracked-files=normal"],
            timeout=6.0,
        )
        if rc == 0:
            dirty = staged = untracked = 0
            for ln in stdout.splitlines():
                if len(ln) < 2:
                    continue
                x, y = ln[0], ln[1]
                if x == "?" and y == "?":
                    untracked += 1
                    continue
                if x != " " and x != "?":
                    staged += 1
                if y != " " and y != "?":
                    dirty += 1
            out["dirty_count"] = dirty
            out["staged_count"] = staged
            out["untracked_count"] = untracked

        # Recent commits
        rc, stdout, _ = _run_subprocess(
            ["git", "-C", REPO_ROOT, "log", "-5", "--pretty=format:%h|%ct|%s"],
            timeout=3.0,
        )
        if rc == 0:
            commits = []
            for ln in stdout.splitlines():
                parts = ln.split("|", 2)
                if len(parts) == 3:
                    try:
                        sha, ct, subj = parts
                        commits.append({
                            "sha": sha,
                            "subject": subj,
                            "author_time": int(ct),
                            "age_s": round(time.time() - int(ct), 1),
                        })
                    except Exception:
                        continue
            out["recent_commits"] = [{"sha": c["sha"], "subject": c["subject"]} for c in commits[:5]]
            if commits:
                out["last_commit"] = commits[0]
    except Exception as e:
        out["error"] = str(e)[:200]
        push_error("git", e)
    return out


def gather_todo() -> dict:
    """Derive a todo list from journal + a couple of well-known TODO.md files.
    Best-effort — returns a small deterministic list."""
    out: dict[str, Any] = {
        "cached_at": time.time(),
        "items": [],
        "error": None,
    }
    try:
        candidates = [
            (r"D:\CLAUDE\eran-live", 1, "watchdog / continuous training health"),
            (r"D:\CLAUDE\almaware-hud", 1, "finish HUD build (this daemon)"),
            (r"D:\CLAUDE\almaware-cockpit", 1, "cockpit consumes ./status.json"),
            (r"D:\CLAUDE\alma-language", 2, "publish perceptron3d artifact"),
            (r"D:\CLAUDE\shisha-lab", 2, "reservoir training layer validation"),
            (r"D:\CLAUDE\grok1-chat", 3, "verify grok1_shim context injection"),
        ]
        items = []
        for path, prio, text in candidates:
            proj_id = os.path.basename(path)
            active = os.path.isdir(path)
            items.append({
                "project": proj_id, "priority": prio, "text": text, "active": active,
            })
        items.sort(key=lambda i: (i["priority"], not i["active"]))
        out["items"] = items[:10]
    except Exception as e:
        out["error"] = str(e)[:200]
        push_error("todo", e)
    return out


def gather_system() -> dict:
    """Local Windows CPU / mem / disks. Uses PowerShell for CPU pct."""
    out: dict[str, Any] = {
        "host": platform.node(),
        "os": f"{platform.system()} {platform.release()} {platform.version()}",
        "boot_time": None,
        "cpu": {"pct": None, "temp_c": None},
        "mem": {"used_gb": None, "total_gb": None, "pct": None},
        "disks": {},
        "gpu": None,
        "cached_at": time.time(),
        "error": None,
    }
    # Mem via ctypes (fast, no subprocess)
    if os.name == "nt":
        try:
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            m = MEMORYSTATUSEX()
            m.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            total_gb = m.ullTotalPhys / (1024.0 ** 3)
            avail_gb = m.ullAvailPhys / (1024.0 ** 3)
            used_gb = total_gb - avail_gb
            out["mem"] = {
                "used_gb": round(used_gb, 2),
                "total_gb": round(total_gb, 2),
                "pct": round(m.dwMemoryLoad, 1),
            }
        except Exception as e:
            push_error("system.mem", e)

        # Disks
        try:
            drives_mask = ctypes.windll.kernel32.GetLogicalDrives()
            for i in range(26):
                if not (drives_mask & (1 << i)):
                    continue
                letter = chr(ord('A') + i) + ":\\"
                try:
                    free_bytes = ctypes.c_ulonglong(0)
                    total_bytes = ctypes.c_ulonglong(0)
                    total_free = ctypes.c_ulonglong(0)
                    ok = ctypes.windll.kernel32.GetDiskFreeSpaceExW(
                        ctypes.c_wchar_p(letter),
                        ctypes.byref(free_bytes),
                        ctypes.byref(total_bytes),
                        ctypes.byref(total_free),
                    )
                    if ok and total_bytes.value > 0:
                        out["disks"][letter[:2]] = {
                            "free_gb": round(total_free.value / (1024.0 ** 3), 1),
                            "total_gb": round(total_bytes.value / (1024.0 ** 3), 1),
                            "pct_free": round(total_free.value / total_bytes.value * 100.0, 1),
                        }
                except Exception:
                    continue
        except Exception as e:
            push_error("system.disks", e)

        # CPU pct: quick PowerShell one-shot (Get-CimInstance) — bounded 3s
        try:
            rc, stdout, _ = _run_subprocess(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command",
                 "(Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average"],
                timeout=3.0,
            )
            if rc == 0:
                s = stdout.strip()
                if s and s.replace(".", "").isdigit():
                    out["cpu"]["pct"] = float(s)
        except Exception as e:
            push_error("system.cpu", e)

        # Boot time
        try:
            rc, stdout, _ = _run_subprocess(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command",
                 "(Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToString('o')"],
                timeout=3.0,
            )
            if rc == 0 and stdout.strip():
                try:
                    dt = _dt.datetime.fromisoformat(stdout.strip())
                    out["boot_time"] = dt.timestamp()
                except Exception:
                    pass
        except Exception:
            pass
    else:
        # POSIX fallback — leave nulls, not used on this box
        pass

    return out


# =============================================================================
# 6. WORKER THREADS
# =============================================================================

class Worker(threading.Thread):
    """Refreshes a single gatherer at TTL cadence and publishes to CACHE."""

    def __init__(self, key: str, fn: Callable[[], dict], interval_s: float):
        super().__init__(name=f"worker.{key}", daemon=True)
        self.key = key
        self.fn = fn
        self.interval_s = interval_s
        self._fail_streak = 0
        self._current_wait = interval_s

    def run(self) -> None:
        while not SHUTDOWN.is_set():
            try:
                t0 = time.perf_counter()
                value = self.fn()
                if isinstance(value, dict):
                    value["cache_age_s"] = 0.0
                _cache_set(self.key, value)
                dt_ms = (time.perf_counter() - t0) * 1000.0
                if isinstance(value, dict) and value.get("error"):
                    self._fail_streak += 1
                    log.warning("worker %s ok-with-error (streak=%d) dt=%.0fms",
                                self.key, self._fail_streak, dt_ms)
                else:
                    if self._fail_streak:
                        log.info("worker %s recovered after %d fails", self.key, self._fail_streak)
                    self._fail_streak = 0
                    log.debug("worker %s ok dt=%.0fms", self.key, dt_ms)
            except Exception as e:
                self._fail_streak += 1
                push_error(f"worker.{self.key}", e)
                log.error("worker %s crashed: %s\n%s", self.key, e, traceback.format_exc(limit=3))

            # Exponential backoff, capped
            wait_s = self.interval_s
            if self._fail_streak >= 3:
                wait_s = min(self.interval_s * (2 ** (self._fail_streak - 2)), BACKOFF_MAX_S)
            self._current_wait = wait_s
            SHUTDOWN.wait(wait_s)


WORKERS: list[Worker] = []


def start_background_workers() -> None:
    specs = [
        ("fleet",    gather_fleet,    TTL_FLEET),
        ("fabric",   gather_fabric,   TTL_FABRIC),
        ("projects", gather_projects, TTL_PROJECTS),
        ("git",      gather_git,      TTL_GIT),
        ("todo",     gather_todo,     TTL_TODO),
        ("system",   gather_system,   TTL_SYSTEM),
    ]
    for key, fn, ttl in specs:
        w = Worker(key, fn, ttl)
        WORKERS.append(w)
        w.start()


def stop_background_workers(join_timeout: float = 2.0) -> None:
    SHUTDOWN.set()
    end = time.time() + join_timeout
    for w in WORKERS:
        remaining = max(0.05, end - time.time())
        try:
            w.join(timeout=remaining)
        except Exception:
            pass


# =============================================================================
# 7. STATUS ASSEMBLY
# =============================================================================

def _cached_or_pending(key: str, stale_after_s: float) -> dict:
    ts, value = _cache_get(key)
    if value is None:
        return {
            "cached_at": None,
            "cache_age_s": None,
            "stale": False,
            "pending": True,
            "items": {} if key in ("fleet", "projects") else None,
            "error": None,
        }
    age = time.time() - ts if ts else None
    if isinstance(value, dict):
        value = dict(value)  # shallow copy
        value["cached_at"] = ts
        value["cache_age_s"] = round(age, 2) if age is not None else None
        value["stale"] = bool(age is not None and age > stale_after_s)
        value["pending"] = False
        return value
    # Non-dict values shouldn't happen but stay defensive
    return {
        "cached_at": ts, "cache_age_s": round(age, 2) if age else None,
        "stale": False, "pending": False, "value": value,
    }


def _run_inline_parallel() -> dict:
    """Run the 4 inline gatherers concurrently so a slow one doesn't block others."""
    results: dict[str, Any] = {}
    lock = threading.Lock()

    def _wrap(key: str, fn: Callable[[], dict]) -> None:
        try:
            v = fn()
        except Exception as e:
            v = {"error": str(e)[:200]}
            push_error(f"gather_{key}", e)
        with lock:
            results[key] = v

    threads = []
    for key, fn in (("eran", gather_eran), ("grok1", gather_grok1),
                    ("services", gather_services), ("workflow", gather_workflow)):
        t = threading.Thread(target=_wrap, args=(key, fn),
                             name=f"inline.{key}", daemon=True)
        t.start()
        threads.append(t)
    # Hard budget for inline gathers: HTTP timeout + a little slack.
    deadline = time.time() + HTTP_TIMEOUT_S + 1.0
    for t in threads:
        remaining = max(0.05, deadline - time.time())
        t.join(timeout=remaining)
    # Fill any that didn't finish
    for key in ("eran", "grok1", "services", "workflow"):
        if key not in results:
            results[key] = {"error": "gather exceeded tick budget"}
    return results


def build_status(tick_start_perf: float, starting: bool = False,
                  stopping: bool = False) -> dict:
    meta = gather_meta(tick_start_perf)
    if starting:
        meta["state"] = "starting"
    elif stopping:
        meta["state"] = "stopping"
    else:
        meta["state"] = "running"

    # Cheap probes — run in parallel
    inline = _run_inline_parallel()
    eran     = inline["eran"]
    grok1    = inline["grok1"]
    services = inline["services"]
    workflow = inline["workflow"]

    # Cached sections
    fleet    = _cached_or_pending("fleet",    STALE_FLEET_S)
    fabric   = _cached_or_pending("fabric",   STALE_FABRIC_S)
    projects = _cached_or_pending("projects", STALE_PROJECTS_S)
    git      = _cached_or_pending("git",      STALE_GIT_S)
    todo     = _cached_or_pending("todo",     STALE_TODO_S)
    system   = _cached_or_pending("system",   STALE_SYSTEM_S)

    # If cached fleet has GPU data, backfill eran.vram_gb from eran1's largest GPU
    try:
        if isinstance(fleet, dict) and "eran1" in fleet:
            gpus = fleet["eran1"].get("gpu") or []
            if gpus:
                # largest by mem_used
                gpu = max(gpus, key=lambda g: g.get("mem_used_gb", 0) or 0)
                eran["vram_gb"] = gpu.get("mem_used_gb")
    except Exception:
        pass

    # Errors ring
    with _ERR_LOCK:
        errors = list(_ERR_RING)

    # meta.stale describes the collector output itself. Individual cached
    # sections retain their own stale flags; exposing those as degraded avoids
    # painting a freshly-written status file as globally stale.
    stale_sections = [
        name for name, sec in (
            ("fleet", fleet), ("fabric", fabric), ("projects", projects),
            ("git", git), ("todo", todo), ("system", system),
        )
        if isinstance(sec, dict) and sec.get("stale")
    ]
    # A health tool that reports degraded=false while its own ERAN section says the
    # organism is down is worse than no health tool. 2026-08-30: it did exactly that
    # for 50 days. ERAN is the point of this machine; he counts toward degraded.
    eran_state = (eran or {}).get("state")
    eran_bad = eran_state in ("down", "frozen", "unknown")
    meta["stale"] = False
    meta["degraded"] = bool(stale_sections) or eran_bad
    meta["stale_sections"] = stale_sections
    meta["degraded_reasons"] = (["stale:" + n for n in stale_sections] +
                                (["eran:" + str(eran_state)] if eran_bad else []))

    # Tick duration recomputed (final)
    meta["tick_ms"] = round((time.perf_counter() - tick_start_perf) * 1000.0, 2)

    status = {
        "meta":     meta,
        "eran":     eran,
        "grok1":    grok1,
        "fleet":    fleet if not fleet.get("pending") else {"cached_at": None, "cache_age_s": None, "pending": True, "eran1": None, "eran2": None, "eran3": None},
        "fabric":   fabric,
        "services": services,
        "services_retired": RETIRED_SERVICES,   # never probed, never red (W6 2026-09-15)
        "projects": projects,
        "git":      git,
        "workflow": workflow,
        "todo":     todo,
        "system":   system,
        "errors":   errors,
    }

    # For fleet: expose per-host keys at top level too if cached
    if fleet and not fleet.get("pending"):
        # cached fleet dict is already {hostname: {...}} — normalize:
        # Move meta keys into a nested _meta so cockpit sees clean host list.
        host_out = {}
        meta_out = {}
        for k, v in fleet.items():
            if k in ("cached_at", "cache_age_s", "stale", "pending", "error"):
                meta_out[k] = v
                continue
            host_out[k] = v
        status["fleet"] = {**host_out, "_meta": meta_out}

    return status


# =============================================================================
# 8. WRITE STATUS TO BOTH TARGETS
# =============================================================================

def write_status(status: dict) -> None:
    for path in (STATUS_PATH_COCKPIT, STATUS_PATH_HUD):
        atomic_write_json(path, status)


# =============================================================================
# 9. STARTUP / MAIN LOOP / SHUTDOWN
# =============================================================================

def _setup_logging(level: str = "INFO") -> None:
    lvl = getattr(logging, level.upper(), logging.INFO)
    log.setLevel(lvl)
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    fh = logging.handlers.RotatingFileHandler(
        LOG_PATH, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUPS, encoding="utf-8"
    )
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)-5s] %(name)s.%(threadName)s  %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    ))
    log.addHandler(fh)
    # also to stderr for foreground runs — pythonw has no stderr, harmless
    sh = logging.StreamHandler()
    sh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)-5s] %(threadName)s  %(message)s",
                                       datefmt="%H:%M:%S"))
    log.addHandler(sh)


def _write_pid_file(force: bool = False) -> None:
    if os.path.exists(PID_PATH):
        try:
            with open(PID_PATH, "r", encoding="utf-8") as f:
                other = int(f.read().strip())
            # Check if still running (Windows)
            if os.name == "nt":
                try:
                    # OpenProcess QUERY_INFORMATION=0x0400
                    handle = ctypes.windll.kernel32.OpenProcess(0x0400, False, other)
                    if handle:
                        ctypes.windll.kernel32.CloseHandle(handle)
                        if not force:
                            print(f"collector already running as PID {other}. Use --force to override.",
                                   file=sys.stderr)
                            sys.exit(2)
                        else:
                            log.warning("--force: overriding stale/live PID %d", other)
                except Exception:
                    pass
        except Exception:
            pass
    try:
        os.makedirs(os.path.dirname(PID_PATH), exist_ok=True)
        with open(PID_PATH, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
    except Exception as e:
        push_error("pidfile", e)


def _acquire_singleton() -> None:
    """Acquire a crash-safe, machine-local singleton for the collector.

    The previous launcher relied on WMIC process matching and then passed
    ``--force``. WMIC is absent on current Windows builds, so simultaneous
    launch attempts could both become status writers. A named mutex is
    released by Windows automatically if the collector crashes.
    """
    global _SINGLETON_HANDLE
    if os.name != "nt":
        # ALMAWARE HUD is a Windows application. PID-file protection remains
        # the conservative fallback when this module is inspected elsewhere.
        return

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_mutex = kernel32.CreateMutexW
    create_mutex.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    create_mutex.restype = ctypes.c_void_p
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [ctypes.c_void_p]
    close_handle.restype = ctypes.c_bool

    handle = create_mutex(None, False, SINGLETON_NAME)
    if not handle:
        raise OSError(ctypes.get_last_error(), "CreateMutexW failed")
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        close_handle(handle)
        print("collector already running (singleton is held)", file=sys.stderr)
        raise SystemExit(2)
    _SINGLETON_HANDLE = handle


def _release_singleton() -> None:
    global _SINGLETON_HANDLE
    if os.name == "nt" and _SINGLETON_HANDLE:
        try:
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            close_handle = kernel32.CloseHandle
            close_handle.argtypes = [ctypes.c_void_p]
            close_handle.restype = ctypes.c_bool
            close_handle(_SINGLETON_HANDLE)
        finally:
            _SINGLETON_HANDLE = None


def _cleanup_pid_file() -> None:
    try:
        if os.path.exists(PID_PATH):
            with open(PID_PATH, "r", encoding="utf-8") as f:
                pid = int(f.read().strip())
            if pid == os.getpid():
                os.remove(PID_PATH)
    except Exception:
        pass


def _install_signal_handlers() -> None:
    def _handler(signum, frame):
        log.info("received signal %s — shutting down", signum)
        SHUTDOWN.set()
    for signame in ("SIGINT", "SIGTERM", "SIGBREAK"):
        try:
            sig = getattr(signal, signame)
            signal.signal(sig, _handler)
        except (AttributeError, ValueError):
            pass


def main() -> int:
    ap = argparse.ArgumentParser(description="ALMAWARE HUD collector daemon")
    ap.add_argument("--once", action="store_true", help="Single tick and exit")
    ap.add_argument("--dry-run", action="store_true", help="Do not write status.json")
    ap.add_argument("--log-level", default="INFO",
                    choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    ap.add_argument(
        "--force",
        action="store_true",
        help="Ignore the PID-file ownership check (never bypasses the singleton)",
    )
    args = ap.parse_args()

    _setup_logging(args.log_level)
    log.info("=== collector starting  pid=%d  python=%s  cwd=%s",
             os.getpid(), platform.python_version(), os.getcwd())

    _acquire_singleton()
    _write_pid_file(force=args.force)
    _install_signal_handlers()

    # Ensure both output dirs exist
    for path in (STATUS_PATH_COCKPIT, STATUS_PATH_HUD):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
        except Exception as e:
            push_error("mkdir", f"{path}: {e}")

    # Emit a starting status immediately so cockpit has something to read from tick 0
    t0 = time.perf_counter()
    starting_status = build_status(t0, starting=True)
    if not args.dry_run:
        write_status(starting_status)
    log.info("wrote initial 'starting' status.json to %s", STATUS_PATH_COCKPIT)

    # Start workers
    start_background_workers()
    log.info("started %d background workers", len(WORKERS))

    # Warmup — let workers publish at least once
    if not args.once:
        log.info("warmup %.1fs …", INITIAL_WARMUP_S)
        SHUTDOWN.wait(INITIAL_WARMUP_S)

    if args.once:
        # single tick
        t0 = time.perf_counter()
        status = build_status(t0)
        if not args.dry_run:
            write_status(status)
        log.info("--once tick done in %.0fms", (time.perf_counter() - t0) * 1000.0)
        stop_background_workers()
        _cleanup_pid_file()
        _release_singleton()
        return 0

    tick_no = 0
    while not SHUTDOWN.is_set():
        tick_no += 1
        t0 = time.perf_counter()
        try:
            status = build_status(t0)
            if not args.dry_run:
                write_status(status)
        except Exception as e:
            push_error("main_loop", e)
            log.error("main loop: %s\n%s", e, traceback.format_exc(limit=3))
        elapsed = time.perf_counter() - t0
        if tick_no <= 3 or tick_no % 12 == 0:
            log.info("tick %d done in %.0fms  cache_keys=%s", tick_no, elapsed * 1000.0,
                     sorted(list(_CACHE.keys())))
        # Interruptible sleep for the remainder of the tick
        SHUTDOWN.wait(max(0.0, TICK_S - elapsed))

    log.info("main loop exited — stopping workers")
    stop_background_workers(join_timeout=2.0)

    # Final "stopping" status
    try:
        t0 = time.perf_counter()
        final_status = build_status(t0, stopping=True)
        if not args.dry_run:
            write_status(final_status)
    except Exception:
        pass

    _cleanup_pid_file()
    _release_singleton()
    log.info("=== collector stopped cleanly  pid=%d", os.getpid())
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        SHUTDOWN.set()
        sys.exit(0)
