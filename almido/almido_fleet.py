#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""almido_fleet.py -- fleet_probe: what is REALLY up on Iddo's fleet, right now.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

Iddo, 2026-09-11: ALMIDO should be able to answer "is the fleet alive" without a human
running twelve curls. The 04:55 morning survey did exactly that by hand and caught two
things a status page would have missed -- eran4's LAN address had CHANGED after the 03:27
reboot, and a door that answers 403 is ALIVE, not broken.

THIS TOOL IS READ-ONLY. It opens sockets, runs `ssh <host> uptime`, and asks `tailscale
status`. It starts nothing, restarts nothing, and writes nothing anywhere on the fleet.
There is no verb here that changes a remote machine -- deliberately, because a prober that
can also repair is a prober nobody dares run.

TWO THINGS IT REFUSES TO GET WRONG
  1. **A non-200 is not a death.** CONTROL on :8896 answers 403 because it is auth-gated;
     eran4's coder doors answer 404 on /v1/models because that is not their route. Both are
     ALIVE. The only real death is no answer at all -- connection refused, timeout, DNS.
     So every door records its HTTP CODE and a verdict derived from `alive_codes`, never
     from "== 200".
  2. **Nothing hangs.** Every single check carries its own timeout (default 8 s) and the
     whole probe carries a wall-clock budget (default 60 s). Checks run in a thread pool,
     so 20 doors cost about as long as the slowest one. A probe that hangs is worse than
     no probe: it blocks the agent that called it.

WHERE THE ADDRESSES COME FROM. `D:\CLAUDE\fleet_inventory.json` if it exists (another
agent maintains it), otherwise the built-in table below, which was MEASURED 2026-09-11
08:33. The output always says which source answered, because a stale address is the single
most expensive lie in this workspace -- CLAUDE.md has been wrong about eran2, eran4 and
the printer in the last month alone.

Run:  python almido_fleet.py            (human summary)
      python almido_fleet.py --json     (the whole JSON)
Test: python -m pytest tests/test_almido_fleet.py
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

INVENTORY = Path(os.environ.get("ALMIDO_FLEET_INVENTORY", r"D:\CLAUDE\fleet_inventory.json"))
PER_CHECK_TIMEOUT = min(8.0, float(os.environ.get("ALMIDO_FLEET_TIMEOUT", "8") or 8))
TOTAL_BUDGET = min(120.0, float(os.environ.get("ALMIDO_FLEET_BUDGET", "60") or 60))
WORKERS = max(4, int(os.environ.get("ALMIDO_FLEET_WORKERS", "12") or 12))

# MEASURED 2026-09-11 08:33 (ssh uptime on all four; ARP for the LAN addresses). The
# fallback, used only when fleet_inventory.json is absent.
DEFAULT_HOSTS = {
    "eran1": {"lan": "<lan-ip>", "tailscale": "<tailnet-ip>", "ssh": "eran1",
              "role": "ERAN himself"},
    "eran2": {"lan": "<lan-ip>", "tailscale": "<tailnet-ip>", "ssh": "eran2",
              "role": "senses + fabric hub"},
    "eran3": {"lan": "<lan-ip>", "tailscale": "<tailnet-ip>", "ssh": "eran3",
              "role": "behind eran2"},
    "eran4": {"lan": "<lan-ip>", "tailscale": "<tailnet-ip>", "ssh": "eran4",
              "role": "DARWISH + the coder doors"},
}

# Every door the morning survey looks at. `alive_codes` is the point of this table: a door
# is alive if it ANSWERS, and each one answers differently.
#   code 0 in alive_codes  = "any HTTP answer at all counts"
DEFAULT_DOORS = [
    {"name": "CONTROL",        "url": "http://127.0.0.1:8896/",  "alive_codes": [0],
     "note": "403 = alive and auth-gated"},
    {"name": "QUORUM",         "url": "http://127.0.0.1:8099/",  "alive_codes": [0]},
    {"name": "phone-mic",      "url": "http://127.0.0.1:8893/",  "alive_codes": [0]},
    {"name": "portal",         "url": "http://127.0.0.1:8899/",  "alive_codes": [0]},
    {"name": "cockpit",        "url": "http://127.0.0.1:8790/",  "alive_codes": [0]},
    {"name": "RECALL",         "url": "http://127.0.0.1:8794/",  "alive_codes": [0]},
    {"name": "MAKOM",          "url": "http://127.0.0.1:8858/",  "alive_codes": [0]},
    {"name": "GALERIA",        "url": "http://127.0.0.1:8861/",  "alive_codes": [0]},
    {"name": "ERAN-window",    "url": "http://{eran1}:8820/",    "alive_codes": [0],
     "note": "400 = alive (it wants its own path). MEASURED 2026-09-11: refused on the LAN, "
             "answers over Tailscale -- which is why the LAN attempt falls back."},
    # RETIRED 2026-09-11 (holy harness law): eran4:8447/8448/8449 coder UIs archived to F:/ALMAWARE-ARCHIVE/HARNESSES-20260911.
    {"name": "eran4:8450",     "url": "https://<tailnet-host>:8450/v1/models", "alive_codes": [200],
     "note": "ALMIDO's own brain -- must really serve models, not merely answer"},
    # RETIRED 2026-09-11 (holy harness law): eran3:8443 ALMIDO IDE archived to F:/ALMAWARE-ARCHIVE/HARNESSES-20260911/eran3-almido-ide-8443.
    {"name": "480B",           "url": "https://<tailnet-host>:8443/v1/models", "alive_codes": [200],
     "note": "Qwen3-Coder-480B. 502 means the proxy is up but the model is NOT served."},
]

_TAILSCALE_CANDIDATES = (
    os.environ.get("ALMIDO_TAILSCALE", ""),
    r"C:\Program Files\Tailscale\tailscale.exe",
    "tailscale",
)


# ------------------------------------------------------------------ the inventory
def _normalise(info: dict) -> dict:
    r"""fleet_inventory.json spells the addresses `lan_ip` / `tailnet_ip`; this module
    (and every door template) uses `lan` / `tailscale`. Translating here is the difference
    between the inventory WINNING and the inventory being silently ignored in favour of
    the built-in table -- which is exactly the stale-address bug the inventory exists to
    end.

    `ssh` is carried through EXACTLY as written, including an explicit null: the printer,
    the phone, the Quest and the A70 are on that list and none of them has a shell.
    Falling back to the host name for them produced four confident BROKEN rows for things
    that were never broken."""
    out = dict(info)
    if info.get("lan_ip") and not info.get("lan"):
        out["lan"] = info["lan_ip"]
    if info.get("tailnet_ip") and not info.get("tailscale"):
        out["tailscale"] = info["tailnet_ip"]
    if "ssh" in info:
        out["ssh"] = info["ssh"] or ""
    return out


def load_hosts() -> tuple:
    r"""(hosts, source). fleet_inventory.json wins when it exists and parses.

    It is read defensively: a file another agent is mid-write on must not take the probe
    down, and a file that parses to something unexpected must not silently replace a
    measured table with nonsense."""
    try:
        if INVENTORY.is_file():
            doc = json.loads(INVENTORY.read_text(encoding="utf-8"))
            hosts = doc.get("hosts") if isinstance(doc, dict) else None
            if isinstance(hosts, dict) and hosts:
                merged = {k: dict(v) for k, v in DEFAULT_HOSTS.items()}
                for name, info in hosts.items():
                    if isinstance(info, dict):
                        merged.setdefault(name, {}).update(_normalise(info))
                return merged, "%s (mtime %s)" % (
                    INVENTORY, datetime.fromtimestamp(INVENTORY.stat().st_mtime)
                    .astimezone().isoformat(timespec="seconds"))
    except Exception as exc:
        return DEFAULT_HOSTS, "%s unreadable (%s: %s) -- using the built-in table measured 2026-09-11 08:33" % (
            INVENTORY, type(exc).__name__, exc)
    return DEFAULT_HOSTS, "built-in table, measured 2026-09-11 08:33 (%s does not exist)" % INVENTORY


# ------------------------------------------------------------------ one door
def _http(url: str, timeout: float) -> dict:
    r"""GET a URL and report the CODE, not a boolean.

    TLS verification is off for the tailnet doors on purpose: they carry ts.net certs that
    this PC's store does not chain, and the question here is "is something listening and
    answering HTTP", not "is this a trusted party". Nothing is sent -- no body, no
    credential, no header -- so there is nothing for a MITM to take."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    t0 = time.time()
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": "almido-fleet-probe"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            resp.read(2048)
            return {"code": resp.status, "ms": int((time.time() - t0) * 1000)}
    except urllib.error.HTTPError as exc:      # 403/404/502 -- an ANSWER, which is the point
        return {"code": exc.code, "ms": int((time.time() - t0) * 1000)}
    except urllib.error.URLError as exc:
        return {"code": 0, "ms": int((time.time() - t0) * 1000),
                "error": str(getattr(exc, "reason", exc))[:160]}
    except (socket.timeout, TimeoutError):
        return {"code": 0, "ms": int((time.time() - t0) * 1000), "error": "timeout"}
    except Exception as exc:
        return {"code": 0, "ms": int((time.time() - t0) * 1000),
                "error": "%s: %s" % (type(exc).__name__, exc)}


def _fill(url: str, hosts: dict, field: str) -> str:
    for name, info in hosts.items():
        url = url.replace("{%s}" % name, str(info.get(field) or info.get("lan")
                                             or info.get("tailscale") or name))
    return url


def probe_door(door: dict, hosts: dict, timeout: float) -> dict:
    r"""One door. LAN first; if nothing answers at all, TRY THE TAILNET before calling it
    dead.

    That fallback is CLAUDE.md's own standing rule -- "before calling a DGX down: every box
    answers on Tailscale too" -- and it is not theoretical: on 2026-09-11 ERAN's window on
    :8820 refused the LAN address and answered 400 over Tailscale in the same second. One
    probe would have reported the organism's observation window as dead."""
    url = _fill(str(door["url"]), hosts, "lan")
    res = _http(url, timeout)
    if res.get("code", 0) == 0:
        alt = _fill(str(door["url"]), hosts, "tailscale")
        if alt != url:
            alt_res = _http(alt, timeout)
            if alt_res.get("code", 0) != 0:
                url, res = alt, alt_res
                res["via"] = "tailnet (the LAN address refused)"
    alive_codes = door.get("alive_codes") or [0]
    code = res.get("code", 0)
    if code == 0:
        verdict = "BROKEN"
    elif 0 in alive_codes:
        verdict = "VERIFIED"
    else:
        verdict = "VERIFIED" if code in alive_codes else "BROKEN"
    out = {"name": door["name"], "url": url, "http_code": code, "ms": res.get("ms"),
           "verdict": verdict}
    if res.get("via"):
        out["via"] = res["via"]
    if res.get("error"):
        out["error"] = res["error"]
    if door.get("note"):
        out["note"] = door["note"]
    if verdict == "BROKEN" and code:
        out["why"] = ("it answered %d but this door is only healthy on %s"
                      % (code, alive_codes))
    elif verdict == "BROKEN":
        out["why"] = "nothing answered: %s" % res.get("error", "no connection")
    return out


# ------------------------------------------------------------------ one box
def probe_host(name: str, info: dict, timeout: float) -> dict:
    """`ssh <host> uptime`. BatchMode so a box that wants a password fails instead of
    sitting at a prompt forever -- that was the whole reason the morning survey used it."""
    target = info.get("ssh") or name
    cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=%d" % max(2, int(timeout) - 1),
           "-o", "StrictHostKeyChecking=accept-new", target, "uptime"]
    t0 = time.time()
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=timeout,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        out = p.stdout.decode("utf-8", "replace").strip()
        err = p.stderr.decode("utf-8", "replace").strip()
        rc = p.returncode
    except subprocess.TimeoutExpired:
        rc, out, err = -9, "", "ssh timed out after %.0fs" % timeout
    except FileNotFoundError:
        rc, out, err = -1, "", "ssh not found on PATH"
    except Exception as exc:
        rc, out, err = -2, "", "%s: %s" % (type(exc).__name__, exc)
    res = {"host": name, "ssh": target, "role": info.get("role"),
           "lan": info.get("lan"), "tailscale": info.get("tailscale"),
           "ms": int((time.time() - t0) * 1000),
           "verdict": "VERIFIED" if rc == 0 and out else "BROKEN"}
    if rc == 0 and out:
        res["uptime"] = out[:200]
        for part in out.split(","):
            if "load average" in part or "load average" in out:
                break
    else:
        res["error"] = (err or "rc=%d" % rc)[:200]
    return res


# ------------------------------------------------------------------ tailscale and RAMCHAT
def tailnet(timeout: float) -> dict:
    exe = next((c for c in _TAILSCALE_CANDIDATES if c and (shutil.which(c) or Path(c).is_file())), None)
    if not exe:
        return {"verdict": "UNKNOWN", "error": "tailscale executable not found"}
    try:
        p = subprocess.run([exe, "status"], capture_output=True, timeout=timeout,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception as exc:
        return {"verdict": "UNKNOWN", "error": "%s: %s" % (type(exc).__name__, exc)}
    txt = p.stdout.decode("utf-8", "replace")
    nodes = []
    for line in txt.splitlines():
        parts = line.split()
        if len(parts) < 4 or not parts[0][0].isdigit():
            continue
        rest = " ".join(parts[4:])
        nodes.append({"ip": parts[0], "name": parts[1], "os": parts[3],
                      "online": "offline" not in rest.lower()})
    online = [n for n in nodes if n["online"]]
    return {"verdict": "VERIFIED" if nodes else "BROKEN",
            "nodes": nodes, "online": len(online), "total": len(nodes)}


def ramchat(timeout: float) -> dict:
    """RAMCHAT is the council's shared memory -- the probe reports whether it ANSWERS, and
    never posts anything. A prober that writes to the transcript pollutes what it measures."""
    script = Path(r"D:\CLAUDE\RAMCHAT\ramlink.py")
    if not script.is_file():
        return {"verdict": "BROKEN", "error": "%s does not exist" % script}
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    try:
        p = subprocess.run([sys.executable, str(script), "status"], capture_output=True,
                           timeout=timeout, cwd=str(script.parent), env=env,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception as exc:
        return {"verdict": "BROKEN", "error": "%s: %s" % (type(exc).__name__, exc)}
    out = p.stdout.decode("utf-8", "replace").strip()
    return {"verdict": "VERIFIED" if p.returncode == 0 else "BROKEN",
            "summary": out.replace("\n", " | ")[:300],
            "error": p.stderr.decode("utf-8", "replace").strip()[:200] or None}


# ------------------------------------------------------------------ the probe
def probe(doors: list = None, timeout: float = None, budget: float = None,
          include_hosts: bool = True, include_tailnet: bool = True) -> dict:
    r"""Measure the fleet. Read-only, parallel, budgeted.

    Everything runs in a pool so the wall clock is the SLOWEST check, not their sum; and a
    check that has not answered when the budget runs out is reported as UNKNOWN with its
    own timeout as the evidence, never quietly dropped."""
    t0 = time.time()
    timeout = float(timeout or PER_CHECK_TIMEOUT)
    budget = float(budget or TOTAL_BUDGET)
    hosts, source = load_hosts()
    doors = doors if doors is not None else DEFAULT_DOORS

    jobs: dict = {}
    out: dict = {"ts": datetime.now().astimezone().isoformat(timespec="seconds"),
                 "inventory_source": source,
                 "per_check_timeout_s": timeout, "budget_s": budget,
                 "doors": [], "hosts": [], "read_only": True}

    # NOT `with ThreadPoolExecutor(...)`. Its __exit__ calls shutdown(wait=True), which
    # BLOCKS until every straggler finishes -- so a probe that had already given up on a
    # slow door still sat there waiting for it. Measured by
    # test_the_whole_probe_is_budgeted: a 3 s budget took 30 s. The budget is a promise to
    # the caller, so the pool is shut down without waiting and the stragglers are left to
    # die on their own per-check timeouts.
    pool = ThreadPoolExecutor(max_workers=WORKERS)
    try:
        for d in doors:
            jobs[pool.submit(probe_door, d, hosts, timeout)] = ("door", d["name"])
        if include_hosts:
            for name, info in hosts.items():
                # Only boxes that really have a shell. An inventory entry may say ssh:null
                # (the printer, the phone, the Quest) -- sshing those produced four
                # confident BROKEN rows for things that were never broken.
                if "ssh" in info and not info.get("ssh"):
                    out["hosts"].append({"host": name, "verdict": "SKIPPED",
                                         "role": info.get("role"),
                                         "why": "no ssh on this device (inventory says ssh: null)"})
                    continue
                jobs[pool.submit(probe_host, name, info, timeout)] = ("host", name)
        if include_tailnet:
            jobs[pool.submit(tailnet, timeout)] = ("tailnet", "tailscale")
            jobs[pool.submit(ramchat, timeout)] = ("ramchat", "ramchat")
        done = set()
        try:
            for fut in as_completed(jobs, timeout=max(1.0, budget - (time.time() - t0))):
                kind, name = jobs[fut]
                done.add(fut)
                try:
                    res = fut.result()
                except Exception as exc:
                    res = {"name": name, "verdict": "BROKEN",
                           "error": "%s: %s" % (type(exc).__name__, exc)}
                if kind == "door":
                    out["doors"].append(res)
                elif kind == "host":
                    out["hosts"].append(res)
                else:
                    out[kind] = res
        except TimeoutError:
            pass
        for fut, (kind, name) in jobs.items():
            if fut in done:
                continue
            fut.cancel()
            row = {"name": name, "verdict": "UNKNOWN",
                   "error": "the %.0fs total budget ran out before this check answered "
                            "(it has its own %.0fs timeout and is finishing in the "
                            "background)" % (budget, timeout)}
            if kind == "door":
                out["doors"].append(row)
            elif kind == "host":
                out["hosts"].append(row)
            else:
                out.setdefault(kind, row)
    finally:
        try:
            pool.shutdown(wait=False, cancel_futures=True)
        except TypeError:                      # Python < 3.9
            pool.shutdown(wait=False)

    out["doors"].sort(key=lambda r: r.get("name", ""))
    out["hosts"].sort(key=lambda r: r.get("host", r.get("name", "")))
    out["elapsed_s"] = round(time.time() - t0, 2)
    out["summary"] = summarize(out)
    return out


def summarize(res: dict) -> str:
    """One line a human (or a coder model) can act on."""
    rows = [r for r in list(res.get("doors", [])) + list(res.get("hosts", []))
            if r.get("verdict") != "SKIPPED"]
    good = [r for r in rows if r.get("verdict") == "VERIFIED"]
    bad = [r for r in rows if r.get("verdict") == "BROKEN"]
    unk = [r for r in rows if r.get("verdict") == "UNKNOWN"]
    tn = res.get("tailnet") or {}
    parts = ["%d/%d VERIFIED" % (len(good), len(rows))]
    if tn.get("total"):
        parts.append("tailnet %d/%d online" % (tn.get("online", 0), tn["total"]))
    if bad:
        parts.append("BROKEN: " + ", ".join(str(r.get("name") or r.get("host")) for r in bad))
    if unk:
        parts.append("UNKNOWN: " + ", ".join(str(r.get("name") or r.get("host")) for r in unk))
    parts.append("%.1fs" % res.get("elapsed_s", 0))
    return "; ".join(parts)


def _cli(argv: list) -> int:
    res = probe()
    if "--json" in argv:
        print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
        return 0
    print(res["summary"])
    print("inventory: %s" % res["inventory_source"])
    for r in res["hosts"]:
        print("  %-8s %-9s %s" % (r.get("host"), r.get("verdict"),
                                  r.get("uptime") or r.get("error", "")))
    for r in res["doors"]:
        print("  %-14s %-9s http=%-4s %s" % (r.get("name"), r.get("verdict"),
                                             r.get("http_code"),
                                             r.get("why") or r.get("note") or ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv))
