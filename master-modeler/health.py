#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
לזכרה של עלמה ז"ל

ALMAWARE Master Modeler — health.py (v0.2)
==========================================
LIVE, READ-ONLY health pings for the control plane. This module OBSERVES only:

  1. leand dashboards   — HTTP GET http://<node>:8899/health on each eran node
  2. fleet Claude reach — lightweight TCP connect to <node>:22 (no ssh commands)
  3. TRAINING heartbeat — mtime + last line of eran-live metrics.jsonl and
                          fleet/eran_live_status.json (age; flag stale)
  4. mic presence       — tasklist scan for pythonw.exe (report only)
  5. ENDPOINT registry  — config-driven (endpoints.json): cloud model CLIs
                          (claude/grok/gemini via `--version`), local HTTP
                          servers (GET), and DGX trainers (tcp reach only).
                          A `prober` can be injected so tests run OFFLINE.

HARD SAFETY (per SPEC.md): this file must NEVER kill, start, restart, ssh-exec,
write, or otherwise touch anything — especially not Eran's training
(D:\\CLAUDE\\eran-live) or the mic. Every check is wrapped in try/except and
degrades to OFFLINE / UNKNOWN. Pure stdlib.

Usage:
    python health.py            # human-readable report
    python health.py --json     # machine-readable dict
"""
from __future__ import annotations

import json
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Optional

# --------------------------------------------------------------------------- #
# Locations + defaults (current IPs as of 2026-07; nodes.json can override).
# --------------------------------------------------------------------------- #
ROOT = Path(__file__).resolve().parent.parent          # D:\CLAUDE
HERE = Path(__file__).resolve().parent                 # D:\CLAUDE\master-modeler
NODES_JSON = HERE / "nodes.json"                       # optional {"eran1": "ip", ...}
ENDPOINTS_JSON = HERE / "endpoints.json"               # config-driven endpoint registry
CLI_TIMEOUT = 6                                         # seconds per `cli --version`

DEFAULT_NODES = {
    "eran1": "<lan-ip>",
    "eran2": "<lan-ip>",
    "eran3": "<lan-ip>",
    "eran4": "<lan-ip>",
}

DASHBOARD_PORT = 8899
SSH_PORT = 22
HTTP_TIMEOUT = 2.5          # seconds per dashboard ping
TCP_TIMEOUT = 1.5           # seconds per ssh-port probe

METRICS_JSONL = ROOT / "eran-live" / "logs" / "metrics.jsonl"
ERAN_STATUS = ROOT / "fleet" / "eran_live_status.json"
STALE_AFTER_S = 15 * 60     # heartbeat older than 15 min => STALE

# Windows consoles default to cp1252; ALMAWARE speaks Hebrew. Force UTF-8.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")          # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass


# --------------------------------------------------------------------------- #
# Node table (defaults + optional nodes.json override). Read-only.
# --------------------------------------------------------------------------- #
def load_nodes() -> dict:
    nodes = dict(DEFAULT_NODES)
    try:
        if NODES_JSON.exists():
            override = json.loads(NODES_JSON.read_text(encoding="utf-8"))
            if isinstance(override, dict):
                for name, ip in override.items():
                    if isinstance(ip, str) and ip.strip():
                        nodes[str(name)] = ip.strip()
    except Exception:
        pass                                            # bad override => defaults
    return nodes


# --------------------------------------------------------------------------- #
# 1) leand dashboards — GET http://<ip>:8899/health
# --------------------------------------------------------------------------- #
def _ping_dashboard(name: str, ip: str) -> dict:
    url = "http://%s:%d/health" % (ip, DASHBOARD_PORT)
    result = {"node": name, "ip": ip, "url": url, "status": "OFFLINE",
              "http": None, "body": None, "ms": None}
    try:
        t0 = time.monotonic()
        req = urllib.request.Request(url, method="GET",
                                     headers={"User-Agent": "master-modeler-health"})
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            body = resp.read(2048).decode("utf-8", "replace").strip()
            result["ms"] = round((time.monotonic() - t0) * 1000)
            result["http"] = resp.status
            result["body"] = body[:200]
            result["status"] = "OK" if 200 <= resp.status < 300 else "DEGRADED"
    except Exception as exc:
        result["status"] = "OFFLINE"
        result["body"] = type(exc).__name__
    return result


def check_dashboards(nodes: dict | None = None) -> dict:
    nodes = nodes or load_nodes()
    out = {}
    try:
        with ThreadPoolExecutor(max_workers=max(1, len(nodes))) as pool:
            futs = {name: pool.submit(_ping_dashboard, name, ip)
                    for name, ip in nodes.items()}
            for name, fut in futs.items():
                try:
                    out[name] = fut.result(timeout=HTTP_TIMEOUT + 2)
                except Exception:
                    out[name] = {"node": name, "status": "UNKNOWN"}
    except Exception:
        for name, ip in nodes.items():
            out.setdefault(name, {"node": name, "ip": ip, "status": "UNKNOWN"})
    return out


# --------------------------------------------------------------------------- #
# 2) fleet Claude reachability — TCP :22 probe only (never run remote commands)
# --------------------------------------------------------------------------- #
def _probe_tcp(name: str, ip: str, port: int = SSH_PORT) -> dict:
    result = {"node": name, "ip": ip, "port": port, "status": "OFFLINE", "ms": None}
    try:
        t0 = time.monotonic()
        with socket.create_connection((ip, port), timeout=TCP_TIMEOUT):
            result["ms"] = round((time.monotonic() - t0) * 1000)
            result["status"] = "OK"
    except Exception as exc:
        result["status"] = "OFFLINE"
        result["error"] = type(exc).__name__
    return result


def check_ssh_reach(nodes: dict | None = None) -> dict:
    nodes = nodes or load_nodes()
    out = {}
    try:
        with ThreadPoolExecutor(max_workers=max(1, len(nodes))) as pool:
            futs = {name: pool.submit(_probe_tcp, name, ip)
                    for name, ip in nodes.items()}
            for name, fut in futs.items():
                try:
                    out[name] = fut.result(timeout=TCP_TIMEOUT + 2)
                except Exception:
                    out[name] = {"node": name, "status": "UNKNOWN"}
    except Exception:
        for name, ip in nodes.items():
            out.setdefault(name, {"node": name, "ip": ip, "status": "UNKNOWN"})
    return out


# --------------------------------------------------------------------------- #
# 3) TRAINING heartbeat freshness — READ mtime + last line, never write.
# --------------------------------------------------------------------------- #
def _tail_line(path: Path, max_scan: int = 65536) -> str | None:
    """Last non-empty line of a file, reading only the tail. Read-only."""
    try:
        size = path.stat().st_size
        with open(path, "rb") as fh:
            fh.seek(max(0, size - max_scan))
            chunk = fh.read(max_scan)
        lines = [ln for ln in chunk.splitlines() if ln.strip()]
        return lines[-1].decode("utf-8", "replace") if lines else None
    except Exception:
        return None


def _heartbeat(path: Path) -> dict:
    result = {"path": str(path), "status": "UNKNOWN", "age_s": None,
              "age_h": None, "mtime": None, "last": None, "stale": None}
    try:
        if not path.exists():
            result["status"] = "MISSING"
            return result
        mtime = path.stat().st_mtime
        age = max(0.0, time.time() - mtime)
        result["mtime"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime))
        result["age_s"] = round(age)
        result["age_h"] = round(age / 3600.0, 2)
        result["stale"] = age > STALE_AFTER_S
        result["status"] = "STALE" if result["stale"] else "FRESH"
        last = _tail_line(path)
        if last:
            try:                                        # pretty if it's JSON
                obj = json.loads(last)
                keep = {k: obj[k] for k in
                        ("step", "loss", "ema_loss", "updated", "host", "service")
                        if k in obj}
                result["last"] = keep or last[:300]
            except Exception:
                result["last"] = last[:300]
    except Exception:
        result["status"] = "UNKNOWN"
    return result


def check_training() -> dict:
    return {
        "metrics_jsonl": _heartbeat(METRICS_JSONL),
        "eran_live_status": _heartbeat(ERAN_STATUS),
        "stale_after_s": STALE_AFTER_S,
    }


# --------------------------------------------------------------------------- #
# 4) mic presence — tasklist only. NEVER kill/start; report yes/no.
# --------------------------------------------------------------------------- #
def check_mic() -> dict:
    result = {"process": "pythonw.exe", "running": None, "count": 0,
              "status": "UNKNOWN"}
    try:
        proc = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq pythonw.exe", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=8,
        )
        lines = [ln for ln in (proc.stdout or "").splitlines()
                 if "pythonw.exe" in ln.lower()]
        result["count"] = len(lines)
        result["running"] = bool(lines)
        result["status"] = "YES" if lines else "NO"
    except Exception:
        result["status"] = "UNKNOWN"
    return result


# --------------------------------------------------------------------------- #
# 5) CONFIG-DRIVEN endpoint registry (endpoints.json) — unified reachability.
# Each endpoint declares a `check`: cli | http | tcp. All checks are READ-ONLY
# (cli => `--version`, http => GET, tcp => connect). A `prober` may be injected
# so tests run fully OFFLINE against a mock without hitting the network/CLIs.
# --------------------------------------------------------------------------- #
def load_endpoints() -> list[dict]:
    """Read endpoints.json (the single source of truth). Empty list on any error."""
    try:
        if not ENDPOINTS_JSON.exists():
            return []
        data = json.loads(ENDPOINTS_JSON.read_text(encoding="utf-8"))
        eps = data.get("endpoints") if isinstance(data, dict) else data
        return [e for e in eps if isinstance(e, dict)] if isinstance(eps, list) else []
    except Exception:
        return []


def _check_cli(ep: dict) -> dict:
    """Reachability of a cloud CLI via `<cmd> --version` (read-only, no prompt)."""
    cmd = ep.get("command") or []
    exe = cmd[0] if cmd else ep.get("name", "?")
    res = {"status": "OFFLINE", "detail": None}
    try:
        if shutil.which(exe) is None:
            res["detail"] = "not on PATH"
            return res
        t0 = time.monotonic()
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=CLI_TIMEOUT)
        res["ms"] = round((time.monotonic() - t0) * 1000)
        out = ((proc.stdout or "") + (proc.stderr or "")).strip().splitlines()
        res["detail"] = (out[0][:80] if out else "ok")
        res["status"] = "OK" if proc.returncode == 0 else "DEGRADED"
    except Exception as exc:
        res["detail"] = type(exc).__name__
    return res


def _check_http(ep: dict) -> dict:
    res = {"status": "OFFLINE", "detail": None}
    url = ep.get("url", "")
    try:
        t0 = time.monotonic()
        req = urllib.request.Request(url, method="GET",
                                     headers={"User-Agent": "master-modeler-health"})
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            res["ms"] = round((time.monotonic() - t0) * 1000)
            res["http"] = resp.status
            res["status"] = "OK" if 200 <= resp.status < 300 else "DEGRADED"
            res["detail"] = "http %s" % resp.status
    except Exception as exc:
        res["detail"] = type(exc).__name__
    return res


def _check_tcp_ep(ep: dict) -> dict:
    res = {"status": "OFFLINE", "detail": None}
    host, port = ep.get("host", ""), int(ep.get("port", 22))
    try:
        t0 = time.monotonic()
        with socket.create_connection((host, port), timeout=TCP_TIMEOUT):
            res["ms"] = round((time.monotonic() - t0) * 1000)
            res["status"] = "OK"
            res["detail"] = "tcp %s:%d reachable (probe only)" % (host, port)
    except Exception as exc:
        res["detail"] = type(exc).__name__
    return res


# Default prober: dispatch on the endpoint's declared `check`. Tests inject a
# mock with the SAME signature (ep -> {"status": ...}) to run offline.
def default_prober(ep: dict) -> dict:
    check = ep.get("check")
    if check == "cli":
        return _check_cli(ep)
    if check == "http":
        return _check_http(ep)
    if check == "tcp":
        return _check_tcp_ep(ep)
    return {"status": "UNKNOWN", "detail": "no/unknown check type %r" % check}


def check_endpoints(endpoints: Optional[list[dict]] = None,
                    prober: Optional[Callable[[dict], dict]] = None) -> list[dict]:
    """Probe every endpoint in the registry, in parallel, read-only.

    `endpoints`  — defaults to load_endpoints() (endpoints.json).
    `prober(ep)` — defaults to default_prober; inject a mock for offline tests.
    Returns one dict per endpoint: name/kind/provider/notes + probe result.
    Never raises.
    """
    endpoints = load_endpoints() if endpoints is None else endpoints
    prober = prober or default_prober
    results: list[dict] = []

    def _one(ep: dict) -> dict:
        base = {
            "name": ep.get("name", "?"),
            "kind": ep.get("kind", "?"),
            "provider": ep.get("provider", "?"),
            "check": ep.get("check", "?"),
            "notes": ep.get("notes", ""),
            "status": "UNKNOWN",
        }
        try:
            base.update(prober(ep) or {})
        except Exception as exc:
            base["status"] = "UNKNOWN"
            base["detail"] = type(exc).__name__
        return base

    if not endpoints:
        return results
    try:
        with ThreadPoolExecutor(max_workers=max(1, len(endpoints))) as pool:
            futs = [pool.submit(_one, ep) for ep in endpoints]
            for ep, fut in zip(endpoints, futs):
                try:
                    results.append(fut.result(timeout=CLI_TIMEOUT + 4))
                except Exception:
                    results.append({"name": ep.get("name", "?"),
                                    "kind": ep.get("kind", "?"),
                                    "status": "UNKNOWN"})
    except Exception:
        # Degrade to sequential if the pool itself fails; still never raise.
        for ep in endpoints:
            results.append(_one(ep))
    return results


# --------------------------------------------------------------------------- #
# Aggregate + render
# --------------------------------------------------------------------------- #
def health(prober: Optional[Callable[[dict], dict]] = None) -> dict:
    """Full read-only snapshot. Never raises.

    `prober` is passed through to check_endpoints so tests can run the whole
    snapshot OFFLINE against a mock. When None, real read-only probes are used.
    """
    snap = {"generated": time.strftime("%Y-%m-%d %H:%M:%S"),
            "read_only": True}
    nodes = load_nodes()
    snap["nodes"] = nodes
    for key, fn in (("endpoints", lambda: check_endpoints(prober=prober)),
                    ("dashboards", lambda: check_dashboards(nodes)),
                    ("ssh_reach", lambda: check_ssh_reach(nodes)),
                    ("training", check_training),
                    ("mic", check_mic)):
        try:
            snap[key] = fn()
        except Exception as exc:
            snap[key] = {"status": "UNKNOWN", "error": type(exc).__name__}
    return snap


def render_health(snap: dict | None = None) -> str:
    try:
        snap = snap or health()
        lines = []
        lines.append("ALMAWARE Master Modeler — HEALTH (read-only)  %s"
                     % snap.get("generated", "?"))
        lines.append("=" * 62)

        eps = snap.get("endpoints") or []
        if eps:
            lines.append("ENDPOINTS (endpoints.json — cloud CLIs / local / DGX)")
            for e in eps:
                detail = ("  %s" % e["detail"]) if e.get("detail") else ""
                ms = ("  %sms" % e["ms"]) if e.get("ms") is not None else ""
                lines.append("  %-13s %-12s %-8s%s%s"
                             % (e.get("name", "?"), e.get("kind", "?"),
                                e.get("status", "UNKNOWN"), ms, detail))

        lines.append("leand dashboards (:%d/health)" % DASHBOARD_PORT)
        dash = snap.get("dashboards") or {}
        for name in sorted(dash):
            d = dash[name] if isinstance(dash[name], dict) else {}
            extra = ""
            if d.get("ms") is not None:
                extra = "  %sms" % d["ms"]
            elif d.get("body"):
                extra = "  (%s)" % d["body"]
            lines.append("  %-6s %-15s %-8s%s"
                         % (name, d.get("ip", "?"), d.get("status", "UNKNOWN"), extra))

        lines.append("fleet reach (tcp :%d — probe only, no ssh-exec)" % SSH_PORT)
        ssh = snap.get("ssh_reach") or {}
        for name in sorted(ssh):
            s = ssh[name] if isinstance(ssh[name], dict) else {}
            extra = "  %sms" % s["ms"] if s.get("ms") is not None else ""
            lines.append("  %-6s %-15s %-8s%s"
                         % (name, s.get("ip", "?"), s.get("status", "UNKNOWN"), extra))

        lines.append("TRAINING heartbeat (stale > %d min)" % (STALE_AFTER_S // 60))
        tr = snap.get("training") or {}
        for key in ("metrics_jsonl", "eran_live_status"):
            hb = tr.get(key) or {}
            age = ("%.2fh" % hb["age_h"]) if hb.get("age_h") is not None else "?"
            flag = " <-- STALE" if hb.get("stale") else ""
            lines.append("  %-18s %-8s age=%-8s mtime=%s%s"
                         % (key, hb.get("status", "UNKNOWN"), age,
                            hb.get("mtime", "?"), flag))
            last = hb.get("last")
            if last:
                txt = json.dumps(last, ensure_ascii=False) \
                    if isinstance(last, dict) else str(last)
                lines.append("    last: %s" % txt[:110])

        mic = snap.get("mic") or {}
        lines.append("mic (pythonw.exe present — observe only): %s (count=%s)"
                     % (mic.get("status", "UNKNOWN"), mic.get("count", "?")))
        return "\n".join(lines)
    except Exception as exc:
        return "health render failed: %s" % type(exc).__name__


if __name__ == "__main__":
    try:
        if "--json" in sys.argv:
            print(json.dumps(health(), ensure_ascii=False, indent=2))
        else:
            print(render_health())
    except Exception as exc:                            # never crash
        print("health failed: %s" % type(exc).__name__)
