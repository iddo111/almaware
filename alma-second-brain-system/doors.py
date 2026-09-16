#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""doors.py -- what tools does a model ACTUALLY have right now? Measured, never declared.

> BROKEN WINDOWS LAW: test the REAL output, not a proxy. `health: ok` is not working.

The whole point of this module is that it refuses to answer from a list. A door is
reported open only if this process just proved it:

  stdio MCP  ->  the server is SPAWNED, sent a real `initialize` + `tools/list`
                 handshake, and its ACTUAL tool names come back. No handshake,
                 no door. (A config entry pointing at a missing python.exe is a
                 door that does not exist, and this says so.)
  http       ->  a real TCP connect + GET; the status code and body prefix are
                 reported, not summarised into "ok". A 401/403 is reported as
                 up-gated, because something IS answering -- calling that "down"
                 is exactly the lie this module exists to stop.
  ports      ->  netstat is read for what is genuinely LISTENING, so a live
                 service nobody wrote down still shows up as unclaimed.
  skills     ->  directories on disk are counted; presence on disk is presence,
                 and this module claims exactly that and no more.

CANDIDATES come from the config files that are the truth of what is wired
(.mcp.json, ~/.qwen/settings.json, ~/.claude.json) -- but a candidate is not a
door. Every candidate is then measured, and the measurement is what is returned.

Read-only. Spawning a stdio MCP server is the one side effect, and each child is
killed the moment its handshake answers or the timeout expires.

THREE THINGS THAT SIDE EFFECT WAS DOING WRONG until 2026-09-06 (Phase-2 defect #5):

  1. It spawned the almido MCP server -- the very process that calls this module --
     with ALMIDO_ANNOUNCE at its default, so every model-initiated brain_doors()
     posted a FAKE "almido-qwen session started ... via alma-brain-doors" line to the
     council and wrote a session_start row into the security audit. A probe that
     changes the thing it measures is not a measurement. Now: a candidate whose script
     resolves to this process is never spawned (state "skipped-self"), and every child
     that IS spawned gets ALMIDO_ANNOUNCE=0 and a throwaway ALMIDO_AUDIT.
  2. It spawned servers that can send messages OUTWARD (wa-mcp with
     HUB_OUTBOUND_ENABLED=1, alma-mail) purely to read their tool lists. Now those are
     skipped unless include_outbound=True.
  3. It GET the live organisms -- ERAN's window on eran1:8820, the senses on eran2:8830,
     darwish-tap on eran4:8806 -- on every call. Now the fleet is opt-in
     (include_fleet=True); the default probe stays on this PC.

And the 12 s stdio timeout was shorter than desktop-commander's real startup, so a live
server was reported down. It is 30 s now, matching qwen-code's own discovery timeout.
"""
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(os.environ.get("ALMA_WORKSPACE", r"D:\CLAUDE"))
HOME = Path.home()

# Config files that DECLARE doors. Declaration is a candidate, not a door.
MCP_CONFIGS = [
    ROOT / ".mcp.json",
    HOME / ".qwen" / "settings.json",
    HOME / ".claude.json",
]

# HTTP services on THIS PC. Each is PROBED; none is assumed.
HTTP_CANDIDATES = {
    "quorum": "http://127.0.0.1:8099/api/health",
    "alma-recall": "http://127.0.0.1:8794/",
    "almaware-hud": "http://127.0.0.1:8790/",
    "keshev-stt-pc": "http://127.0.0.1:8737/",
    "keshev-he": "http://127.0.0.1:8738/",
    "ollama-pc": "http://127.0.0.1:11434/api/tags",
}

# The fleet. OPT-IN (include_fleet=True): eran1:8820 is ERAN's own observation window,
# eran2:8830 his senses and eran4:8806 darwish's tap -- live organisms, not status pages.
# Knowing which doors THIS PC has does not require touching them.
FLEET_HTTP_CANDIDATES = {
    "ollama-eran4": "http://<lan-ip>:11434/api/tags",
    "eran-window": "http://<lan-ip>:8820/",
    "eran-senses": "http://<lan-ip>:8830/",
    "darwish-tap": "http://<lan-ip>:8806/",
}

SKILL_DIRS = [
    HOME / ".claude" / "skills",
    HOME / ".claude" / "plugins",
    ROOT / ".claude" / "skills",
]

# 12 s was shorter than desktop-commander's measured startup, so a live door was
# reported down. 30 s is qwen-code's own MCP discovery timeout.
STDIO_TIMEOUT = float(os.environ.get("BRAIN_DOOR_STDIO_TIMEOUT", "30"))
HTTP_TIMEOUT = float(os.environ.get("BRAIN_DOOR_HTTP_TIMEOUT", "10"))
TCP_TIMEOUT = float(os.environ.get("BRAIN_DOOR_TCP_TIMEOUT", "2.5"))

# Servers that can send something OUTWARD (a message, a mail) on someone's behalf.
# Spawning one only to read its tool list is a side effect nobody asked for.
OUTBOUND_HINTS = ("wa-mcp", "whatsapp", "mail", "gmail", "telegram", "slack", "sms",
                  "twilio", "discord", "signal")


def _looks_outbound(cand: dict) -> bool:
    name = str(cand.get("name", "")).lower()
    if any(hint in name for hint in OUTBOUND_HINTS):
        return True
    for key, value in (cand.get("env") or {}).items():
        if "OUTBOUND" in str(key).upper() and str(value).strip().lower() in ("1", "true", "yes", "on"):
            return True
    return False


def self_script_paths() -> set:
    r"""Resolved script paths of THIS process, which must never be spawned as a child.

    almido_mcp.py imports this module; spawning it from here gives a second almido that
    announces itself to the council and writes audit rows -- the measurement forging its
    own evidence. BRAIN_DOOR_NO_SPAWN adds more paths (os.pathsep-separated).
    """
    paths = set()
    for mod in ("__main__", "almido_mcp"):
        target = getattr(sys.modules.get(mod), "__file__", None)
        if target:
            try:
                paths.add(Path(target).resolve())
            except Exception:
                pass
    for extra in os.environ.get("BRAIN_DOOR_NO_SPAWN", "").split(os.pathsep):
        if extra.strip():
            try:
                paths.add(Path(extra.strip()).resolve())
            except Exception:
                pass
    return paths


def _is_self(cand: dict, mine: set) -> bool:
    if not mine:
        return False
    for token in [cand.get("command", "")] + list(cand.get("args") or []):
        try:
            if Path(str(token)).resolve() in mine:
                return True
        except Exception:
            continue
    return False


def probe_env(mine: set | None = None) -> dict:
    """Environment forced on every probed child: announce NOTHING, audit NOWHERE real."""
    scratch = Path(tempfile.gettempdir()) / "alma-brain-doors"
    try:
        scratch.mkdir(parents=True, exist_ok=True)
    except Exception:
        scratch = Path(tempfile.gettempdir())
    env = {"ALMIDO_ANNOUNCE": "0",
           "ALMIDO_AUDIT": str(scratch / ("probe-audit-%d.jsonl" % os.getpid())),
           "RAMCHAT_MCP_ANNOUNCE": "0"}
    no_spawn = os.pathsep.join(sorted(str(p) for p in (mine or self_script_paths())))
    if no_spawn:
        env["BRAIN_DOOR_NO_SPAWN"] = no_spawn      # a nested doors() must not recurse either
    return env


# ------------------------------------------------------------------ candidates
def mcp_candidates() -> list[dict]:
    """Every stdio MCP server DECLARED in any config we can read. Candidates only."""
    out: list[dict] = []
    seen: set[str] = set()
    for cfg in MCP_CONFIGS:
        try:
            data = json.loads(cfg.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        blocks = [data.get("mcpServers")]
        for proj in (data.get("projects") or {}).values():
            if isinstance(proj, dict):
                blocks.append(proj.get("mcpServers"))
        for block in blocks:
            if not isinstance(block, dict):
                continue
            for name, spec in block.items():
                if not isinstance(spec, dict) or not spec.get("command"):
                    continue
                key = str(name) + "|" + str(cfg)
                if key in seen:
                    continue
                seen.add(key)
                out.append({"name": str(name), "declared_in": str(cfg),
                            "command": str(spec.get("command")),
                            "args": [str(a) for a in (spec.get("args") or [])],
                            "cwd": spec.get("cwd") or None,
                            "env": {str(k): str(v) for k, v in (spec.get("env") or {}).items()}})
    return out


# ------------------------------------------------------------------ measurement
def _on_path(name: str) -> bool:
    if os.sep in name or "/" in name:
        return False
    exts = os.environ.get("PATHEXT", ".EXE;.CMD;.BAT").split(";") if os.name == "nt" else [""]
    for d in os.environ.get("PATH", "").split(os.pathsep):
        if not d:
            continue
        if Path(d, name).is_file():
            return True
        for ext in exts:
            if Path(d, name + ext.lower()).is_file():
                return True
    return False


def probe_stdio(cand: dict, timeout: float = STDIO_TIMEOUT, forced_env: dict | None = None) -> dict:
    """Spawn the server, do a REAL initialize + tools/list. Its own tool names, or nothing."""
    res: dict = {"name": cand["name"], "kind": "mcp-stdio", "declared_in": cand["declared_in"],
                 "state": "down", "tools": [], "detail": "", "ms": None}
    cmd = [cand["command"]] + list(cand["args"])
    if not Path(cmd[0]).is_file() and not _on_path(cmd[0]):
        res["detail"] = "command not found: " + cmd[0]
        return res
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env.update(cand["env"])
    # LAST, so a config that asks a child to announce itself cannot win over the probe. #5
    env.update(probe_env() if forced_env is None else forced_env)
    started = time.time()
    proc = None
    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, encoding="utf-8",
                                errors="replace", cwd=cand["cwd"], env=env, shell=False)
        req = (json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                           "params": {"protocolVersion": "2025-06-18",
                                      "capabilities": {},
                                      "clientInfo": {"name": "alma-brain-doors", "version": "1"}}}) + "\n"
               + json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"
               + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}) + "\n")
        out, err = proc.communicate(req, timeout=timeout)
        res["ms"] = int((time.time() - started) * 1000)
        for line in (out or "").splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if not isinstance(msg, dict):
                continue
            if msg.get("id") == 2 and isinstance(msg.get("result"), dict):
                res["tools"] = [str(t.get("name")) for t in (msg["result"].get("tools") or [])]
                res["state"] = "up"
            elif msg.get("id") == 1 and isinstance(msg.get("result"), dict):
                info = msg["result"].get("serverInfo") or {}
                res["detail"] = "%s %s" % (info.get("name", "?"), info.get("version", ""))
                if res["state"] != "up":
                    res["state"] = "handshake-only"
        if res["state"] == "down":
            res["detail"] = res["detail"] or (err or "").strip()[-200:] or "no JSON-RPC answer"
    except subprocess.TimeoutExpired:
        res["detail"] = "no answer in %.0f s" % timeout
        res["ms"] = int((time.time() - started) * 1000)
    except Exception as exc:
        res["detail"] = type(exc).__name__ + ": " + str(exc)[:160]
    finally:
        if proc is not None and proc.poll() is None:
            try:
                proc.kill()
                proc.wait(timeout=5)
            except Exception:
                pass
    return res


def _tcp_open(host: str, port: int, timeout: float = TCP_TIMEOUT) -> bool:
    """Is anything accepting connections there? The cheapest true fact about a port."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def _host_port(url: str) -> tuple:
    parsed = urllib.parse.urlsplit(url)
    return parsed.hostname or "", int(parsed.port or (443 if parsed.scheme == "https" else 80))


def probe_http(name: str, url: str, timeout: float = HTTP_TIMEOUT) -> dict:
    """GET it for real. A slow answer is NOT a dead port -- and this says which it was.

    QUORUM's /api/health probes every model before answering, so a tight timeout
    reports a live server as down. That false negative was measured on 2026-09-05
    and is why the TCP fallback below exists: netstat and this must agree.
    """
    res: dict = {"name": name, "kind": "http", "url": url, "state": "down", "detail": "", "ms": None}
    started = time.time()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read(400).decode("utf-8", "replace")
            res.update(state="up", ms=int((time.time() - started) * 1000),
                       detail="HTTP %d %s" % (resp.status, " ".join(body.split())[:160]))
            return res
    except urllib.error.HTTPError as exc:
        # 401/403/404: something IS answering, just gated. Calling it down is the lie.
        res.update(state="up-gated", detail="HTTP %d" % exc.code,
                   ms=int((time.time() - started) * 1000))
        return res
    except Exception as exc:
        res.update(detail=type(exc).__name__ + ": " + str(exc)[:120],
                   ms=int((time.time() - started) * 1000))
    host, port = _host_port(url)
    if host and _tcp_open(host, port):
        res["state"] = "listening-slow"
        res["detail"] = "TCP %s:%d accepts, but no HTTP answer in %.0f s -- %s" % (
            host, port, timeout, res["detail"])
    return res


_NETSTAT_RE = re.compile(r"^\s*TCP\s+(\S+):(\d+)\s+\S+\s+LISTENING\s+(\d+)", re.MULTILINE)


def listening_ports() -> list[dict]:
    """What is genuinely listening on this PC, read from the OS -- not from any list of ours."""
    try:
        p = subprocess.run(["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=25, shell=False)
    except Exception:
        return []
    seen: dict = {}
    for addr, port, pid in _NETSTAT_RE.findall(p.stdout or ""):
        key = (addr, int(port))
        if key not in seen:
            seen[key] = {"addr": addr, "port": int(port), "pid": int(pid)}
    return sorted(seen.values(), key=lambda r: r["port"])


def skills_on_disk() -> dict:
    out: dict = {}
    for d in SKILL_DIRS:
        if not d.is_dir():
            out[str(d)] = "absent"
            continue
        try:
            names = sorted(p.name for p in d.iterdir() if p.is_dir())
        except OSError as exc:
            out[str(d)] = "unreadable: " + str(exc)[:80]
            continue
        out[str(d)] = {"count": len(names), "names": names[:200]}
    return out


def _declared_ports(urls=None) -> set:
    ports = set()
    for url in (urls if urls is not None else list(HTTP_CANDIDATES.values()) + list(FLEET_HTTP_CANDIDATES.values())):
        m = re.search(r":(\d{2,5})(?:/|$)", url)
        if m:
            ports.add(int(m.group(1)))
    return ports


def _skipped(cand: dict, state: str, why: str) -> dict:
    return {"name": cand["name"], "kind": "mcp-stdio", "declared_in": cand["declared_in"],
            "state": state, "tools": [], "detail": why, "ms": 0}


# ------------------------------------------------------------------ the answer
def doors(*, include_ports: bool = True, include_skills: bool = True,
          stdio: bool = True, http: bool = True, workers: int = 6,
          include_fleet: bool = False, include_outbound: bool = False) -> dict:
    """Probe everything in parallel and report only what answered.

    include_fleet=False and include_outbound=False are the SAFE defaults (#5): the fleet
    organisms are not touched and no message-sending server is spawned. What is skipped is
    reported as skipped -- silence would be the same lie as calling a live door dead.
    """
    started = time.time()
    result: dict = {"measured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    "method": "probed, not declared",
                    "scope": {"fleet": bool(include_fleet), "outbound": bool(include_outbound)}}
    urls = dict(HTTP_CANDIDATES)
    if include_fleet:
        urls.update(FLEET_HTTP_CANDIDATES)
    mine = self_script_paths()
    forced = probe_env(mine)
    to_probe, skipped = [], []
    for cand in (mcp_candidates() if stdio else []):
        if _is_self(cand, mine):
            skipped.append(_skipped(cand, "skipped-self", "not spawned: this process IS this server"))
        elif _looks_outbound(cand) and not include_outbound:
            skipped.append(_skipped(cand, "skipped-outbound",
                                    "not spawned: can send messages outward (include_outbound=True to probe)"))
        else:
            to_probe.append(cand)
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        f_mcp = [pool.submit(probe_stdio, c, STDIO_TIMEOUT, forced) for c in to_probe]
        f_http = [pool.submit(probe_http, n, u) for n, u in (urls.items() if http else [])]
        mcp = [f.result() for f in f_mcp] + skipped
        web = [f.result() for f in f_http]
    result["mcp"] = sorted(mcp, key=lambda r: (r["state"] != "up", r["name"]))
    result["http"] = sorted(web, key=lambda r: (not str(r["state"]).startswith("up"), r["name"]))
    if include_ports:
        ports = listening_ports()
        declared = _declared_ports()
        result["listening"] = ports
        result["unclaimed_ports"] = [p for p in ports
                                     if p["port"] not in declared and 8000 <= p["port"] <= 9999]
    if include_skills:
        result["skills_on_disk"] = skills_on_disk()
    up_mcp = [r["name"] for r in mcp if r["state"] == "up"]
    result["summary"] = {
        "mcp_declared": len(mcp), "mcp_answering": len(up_mcp), "mcp_up": up_mcp,
        "mcp_tools_total": sum(len(r["tools"]) for r in mcp),
        "mcp_skipped": [r["name"] for r in skipped],
        "http_probed": len(web),
        "http_up": len([r for r in web if str(r["state"]).startswith("up")]),
        "http_listening_slow": len([r for r in web if r["state"] == "listening-slow"]),
        "probe_seconds": round(time.time() - started, 2),
    }
    return result


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Measure which doors are actually open right now.")
    ap.add_argument("--no-stdio", action="store_true", help="skip spawning MCP servers")
    ap.add_argument("--no-ports", action="store_true")
    ap.add_argument("--no-skills", action="store_true")
    ap.add_argument("--fleet", action="store_true", help="also GET the live fleet organisms (off by default)")
    ap.add_argument("--outbound", action="store_true", help="also spawn message-sending servers (off by default)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    d = doors(stdio=not a.no_stdio, include_ports=not a.no_ports, include_skills=not a.no_skills,
              include_fleet=a.fleet, include_outbound=a.outbound)
    if a.json:
        print(json.dumps(d, ensure_ascii=False, indent=1))
    else:
        print(json.dumps(d.get("summary"), ensure_ascii=False, indent=1))
        for r in d.get("mcp", []):
            print("  MCP  %-24s %-14s %s" % (r["name"], r["state"],
                                             (",".join(r["tools"]) or r["detail"])[:90]))
        for r in d.get("http", []):
            print("  HTTP %-24s %-14s %s" % (r["name"], r["state"], str(r["detail"])[:90]))
