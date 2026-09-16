#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
ONE PLACE -- the devices / models / chat / queue half of the CONTROL page.

    BROKEN WINDOWS LAW: if it is not working, fix it IMMEDIATELY.

Iddo, 2026-09-11 04:52: one page, from the phone, in Thailand -- every device,
every model, the work queue. 2026-09-11 08:29 "do all 13 upgrades in your order",
08:34 "לאט ובטוח, בנייה חזקה".

This module is imported by control.py (which owns the page and the audit log).
It never imports control.py back -- control.wire()s its audit function in, so
there is exactly one audit file and one lock.

100% stdlib. Addresses come from D:\CLAUDE\fleet_inventory.json via
fleet_inventory.py -- nothing here hard-codes an IP.

WHAT IT ADDS
  devices_state()   the 10 hosts of the inventory: online/offline (tailscale
                    status --json, cached), LAN + tailnet address, last seen,
                    role, and every door that host owns with a live pill.
  models_state()    ONE model list = QUORUM /api/models (live) + the model doors
                    in the inventory + `claude` + `openai:gpt-*` (only when
                    OPENAI_API_KEY is in the environment). One probe per BASE,
                    not per model.
  ask(model, text)  calls the chosen door server-side and returns the answer.
                    OpenAI-compatible /v1/chat/completions for fleet/ollama/
                    openai/nvidia; `claude -p` on stdin for claude.
  queue_state()     RAMCHAT tail + the open work queue.
  queue_op(op,id)   claim / done through ramlink.py itself (the atomic path).

SECRETS: an API key is read from os.environ INSIDE this process and used only as
an Authorization header on an outbound request. It is never put in the page,
never in the JSON state, never in the audit log, never in RAMCHAT.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

sys.path.insert(0, r"D:\CLAUDE")
try:
    import fleet_inventory as fi
except Exception:                                              # noqa: BLE001
    fi = None

RAMCHAT_DIR = r"D:\CLAUDE\RAMCHAT"
RAMLINK = os.path.join(RAMCHAT_DIR, "ramlink.py")
RAMCHAT_SESSION = os.path.join(RAMCHAT_DIR, "ramchat_session.json")
RAMCHAT_QUEUE = os.path.join(RAMCHAT_DIR, "ramchat_prompt_queue.json")
QUORUM_MODELS = "http://127.0.0.1:8099/api/models"
QUORUM_REGISTRY = r"D:\CLAUDE\quorum\state\registry.json"
OPENAI_BASE = "https://api.openai.com/v1"
ASK_CWD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ask-cwd")

_NOWIN = 0x08000000              # CREATE_NO_WINDOW
_BELOW_NORMAL = 0x00004000       # the PC is the microphone's machine, always

# The queue page acts as Iddo, from his own private page. Same name in RAMCHAT.
QUEUE_WHO = "iddo (control page)"

ASK_MAX_CHARS = 4096
ASK_RATE_PER_MIN = 20
ASK_TIMEOUT_HTTP = 120
ASK_TIMEOUT_CLAUDE = 180
DOOR_PROBE_BUDGET_S = 5.0        # a door slower than this is SLOW, not BROKEN

# curated OpenAI seats -- intersected with what the key actually lists, so a
# retired model never shows up as a dead option.
OPENAI_WANT = ["gpt-5.4", "gpt-5.4-mini", "gpt-5.2", "gpt-5.1", "gpt-4.1-mini"]
CLAUDE_SEATS = [("sonnet", "Claude Sonnet"), ("opus", "Claude Opus"), ("haiku", "Claude Haiku")]

_audit = None                    # wired by control.py


def wire(audit_fn):
    """control.py hands us its audit writer so there is one log and one lock."""
    global _audit
    _audit = audit_fn


def _log(action, result, detail=None, ip=None):
    if _audit is not None:
        try:
            return _audit(action, result, detail, ip=ip)
        except Exception:                                      # noqa: BLE001
            pass
    return None


# ---------------------------------------------------------------- small utils
def _ctx():
    try:
        import ssl
        c = ssl.create_default_context()
        c.check_hostname = False
        c.verify_mode = ssl.CERT_NONE
        return c
    except Exception:                                          # noqa: BLE001
        return None


_SSL = _ctx()


def _get(url, timeout=5.0, headers=None):
    """One GET. Returns (code_or_None, ms, body_or_error). 4xx counts as answering."""
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers=dict(headers or {},
                                                       **{"User-Agent": "one-place/1"}))
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL) as r:
            return r.status, int((time.time() - t0) * 1000), r.read(200000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, int((time.time() - t0) * 1000), ""
    except Exception as e:                                     # noqa: BLE001
        return None, int((time.time() - t0) * 1000), str(e)[:160]


def _post_json(url, payload, timeout=60.0, headers=None):
    t0 = time.time()
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    try:
        req = urllib.request.Request(
            url, data=data, method="POST",
            headers=dict(headers or {}, **{"Content-Type": "application/json",
                                           "User-Agent": "one-place/1"}))
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL) as r:
            return r.status, int((time.time() - t0) * 1000), r.read(400000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read(4000).decode("utf-8", "replace")
        except Exception:                                      # noqa: BLE001
            pass
        return e.code, int((time.time() - t0) * 1000), body
    except Exception as e:                                     # noqa: BLE001
        return None, int((time.time() - t0) * 1000), str(e)[:200]


def _jload(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:                                          # noqa: BLE001
        return default


# ============================================================= DEVICES
_ts_cache = {"at": 0.0, "data": None}


def tailscale_status(max_age=60.0):
    """`tailscale status --json`, cached. Measured 0.24 s -- but never per GET."""
    now = time.time()
    if _ts_cache["data"] is not None and now - _ts_cache["at"] < max_age:
        return _ts_cache["data"]
    out = {"self": {}, "peers": {}, "error": None}
    try:
        p = subprocess.run(["tailscale", "status", "--json"], capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           timeout=12, creationflags=_NOWIN)
        d = json.loads(p.stdout or "{}")
        s = d.get("Self") or {}
        out["self"] = {"hostname": s.get("HostName"), "ips": s.get("TailscaleIPs") or [],
                       "online": bool(s.get("Online"))}
        for _, v in (d.get("Peer") or {}).items():
            dns = (v.get("DNSName") or "").rstrip(".")
            rec = {"hostname": v.get("HostName"), "dns": dns,
                   "ips": v.get("TailscaleIPs") or [], "online": bool(v.get("Online")),
                   "last_seen": v.get("LastSeen"), "os": v.get("OS")}
            for ipaddr in rec["ips"]:
                out["peers"][ipaddr] = rec
            if dns:
                out["peers"][dns] = rec
    except Exception as e:                                     # noqa: BLE001
        out["error"] = str(e)[:160]
    _ts_cache.update(at=now, data=out)
    return out


def _last_seen_human(iso):
    if not iso or iso.startswith("0001-"):
        return None
    try:
        t = datetime.strptime(iso.split(".")[0].rstrip("Z"), "%Y-%m-%dT%H:%M:%S")
    except Exception:                                          # noqa: BLE001
        return iso
    secs = (datetime.utcnow() - t).total_seconds()
    if secs < 90:
        return "עכשיו"
    if secs < 3600:
        return "לפני %d דק'" % (secs // 60)
    if secs < 86400:
        return "לפני %d שע'" % (secs // 3600)
    return "לפני %d ימים" % (secs // 86400)


def _probe_one_door(name, d):
    url = d.get("url") or ""
    expect = d.get("expect_any") or [200]
    budget = min(float(d.get("timeout_s") or DOOR_PROBE_BUDGET_S), DOOR_PROBE_BUDGET_S)
    code, ms, body = _get(url, timeout=budget)
    if code is None:
        # honest distinction: a page that is merely slow is not a dead door.
        slow = "timed out" in (body or "").lower() or "timeout" in (body or "").lower()
        state = "SLOW" if slow else "BROKEN"
    elif code in expect:
        state = "VERIFIED"
    elif isinstance(code, int) and code >= 500:
        state = "BROKEN"          # a 5xx behind a live proxy means the backend is gone
    else:
        state = "BROKEN"
    return {"name": name, "state": state, "code": code, "ms": ms, "url": url,
            "host": d.get("host"), "auth": d.get("auth"), "purpose": d.get("purpose"),
            "loopback": "127.0.0.1" in url or "localhost" in url}


def doors_check():
    """Every door in fleet_inventory.json, probed in parallel. Background only."""
    if fi is None:
        return {"error": "fleet_inventory not importable", "doors": [], "at": None}
    try:
        doors = fi.all_doors()
    except Exception as e:                                     # noqa: BLE001
        return {"error": str(e)[:160], "doors": [], "at": None}
    items = sorted(doors.items())
    with ThreadPoolExecutor(max_workers=12) as ex:
        rows = list(ex.map(lambda kv: _probe_one_door(kv[0], kv[1]), items))
    return {"doors": rows, "at": datetime.now().isoformat(timespec="seconds"),
            "ok": sum(1 for r in rows if r["state"] == "VERIFIED"), "total": len(rows)}


_inv_mtime = {"at": 0.0}


def _inventory():
    """fleet_inventory.load(), but RE-READ when the file on disk changes.

    `fleet_inventory --refresh` runs on a 6-hour scheduled task and rewrites the
    file whenever a DHCP lease moves a box. fi.load() caches forever, so without
    this the hub would keep serving the addresses it read at boot -- exactly the
    failure the inventory was built to end (eran2 .59 -> .156 broke four things
    silently on 2026-09-10).
    """
    try:
        m = os.path.getmtime(fi.INVENTORY_PATH)
    except OSError:
        m = 0.0
    changed = m != _inv_mtime["at"]
    _inv_mtime["at"] = m
    return fi.load(force=changed)


def devices_state(force=False):
    """The 10 hosts of the inventory + live/offline + the doors each one owns."""
    if fi is None:
        return {"error": "fleet_inventory not importable", "hosts": []}
    try:
        inv = _inventory()
    except Exception as e:                                     # noqa: BLE001
        return {"error": str(e)[:160], "hosts": []}
    ts = tailscale_status()
    dc = doors_check()
    by_host = {}
    for r in dc.get("doors") or []:
        by_host.setdefault(r.get("host") or "?", []).append(r)

    hosts = []
    for key, rec in inv.get("hosts", {}).items():
        tsip = rec.get("tailnet_ip")
        dns = rec.get("magicdns")
        peer = (ts["peers"].get(tsip) if tsip else None) or (ts["peers"].get(dns) if dns else None)
        if key == "pc":
            online, last_seen = True, "זה המחשב הזה"
        elif peer is not None:
            online = peer["online"]
            last_seen = "מחובר" if online else (_last_seen_human(peer.get("last_seen")) or "?")
        elif tsip is None:
            # no tailnet node at all (the printer): LAN reachability from the inventory
            online = bool(rec.get("reachable"))
            last_seen = "LAN בלבד"
        else:
            online, last_seen = False, "לא ברשת"
        mine = sorted(by_host.get(key, []), key=lambda r: r["name"])
        hosts.append({
            "key": key, "role": rec.get("role"), "os": rec.get("os"),
            "lan_ip": rec.get("lan_ip"), "tailnet_ip": tsip, "magicdns": dns,
            "ssh": rec.get("ssh"), "note": rec.get("note"),
            "online": online, "last_seen": last_seen,
            "doors": mine,
            "doors_ok": sum(1 for r in mine if r["state"] == "VERIFIED"),
            "doors_total": len(mine),
        })
    order = ["pc", "s26", "quest", "a70", "eran1", "eran2", "eran3", "eran4", "hp-laptop", "printer"]
    hosts.sort(key=lambda h: (order.index(h["key"]) if h["key"] in order else 99, h["key"]))
    return {"hosts": hosts, "measured_at": inv.get("measured_at"),
            "tailscale_error": ts.get("error"),
            "doors_ok": dc.get("ok"), "doors_total": dc.get("total"),
            "checked_at": dc.get("at")}


# ============================================================= MODELS
# One CATALOG entry per callable seat. `spec` never leaves this process.
_models_cache = {"at": 0.0, "data": None}
_openai_cache = {"at": 0.0, "ids": None}


def _inv_door(name, default=None):
    if fi is None:
        return default
    try:
        return fi.door(name)
    except Exception:                                          # noqa: BLE001
        return default


def _base_of(url):
    """'http://h:8000/v1/models' -> 'http://h:8000/v1'"""
    return re.sub(r"/(v1/)?models/?$", "/v1", url or "").rstrip("/")


def _openai_ids():
    """What Iddo's key actually serves, cached 10 min. Key never leaves the process."""
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return []
    now = time.time()
    if _openai_cache["ids"] is not None and now - _openai_cache["at"] < 600:
        return _openai_cache["ids"]
    code, _ms, body = _get(OPENAI_BASE + "/models", timeout=15,
                           headers={"Authorization": "Bearer " + key})
    ids = []
    if code == 200:
        try:
            ids = [m["id"] for m in (json.loads(body).get("data") or [])]
        except Exception:                                      # noqa: BLE001
            ids = []
    url = OPENAI_BASE + "/models"
    if ids:
        _openai_cache.update(at=now, ids=ids)
        _fail_until.pop(url, None)          # fresh -> the seats may show green
        return ids
    _fail_until[url] = now + SOURCE_BACKOFF_S   # stale -> the seats show red, honestly
    # One bad minute must not blank the OpenAI seats for the next ten: keep the
    # last good list and retry sooner. (Same reasoning as _enumerate above.)
    old = _openai_cache["ids"]
    if old:
        _openai_cache["at"] = now - 600 + SOURCE_BACKOFF_S
        return old
    _openai_cache.update(at=now - 600 + SOURCE_BACKOFF_S, ids=[])
    return []


# A seat must never VANISH because its door was slow for one probe cycle: the
# dropdown would reshuffle under Iddo's thumb and his remembered choice would
# disappear. Measured 2026-09-11: QUORUM /api/models (which health-probes every
# provider itself) went from 0.3 s to >10 s within the hour, and the PC ollama
# door answers in 3 ms warm but ~2 s cold. So every enumerating source keeps its
# LAST GOOD answer, and a failed source is backed off instead of retried at speed.
# The seats stay in the list and go red -- which is the truth, and is stable.
_last_good = {}          # source url -> {"ids"/"models": ..., "at": ts}
_fail_until = {}         # source url -> ts before which we do not retry
SOURCE_BACKOFF_S = 120


def _stale_note(url, secs):
    return "%s did not answer -- showing the last list from %s ago" % (
        url, ("%ds" % secs) if secs < 90 else ("%dm" % (secs // 60)))


def _enumerate(url, parse, timeout):
    """(value, note). Falls back to the last good value and backs the source off."""
    now = time.time()
    good = _last_good.get(url)
    if now < _fail_until.get(url, 0.0) and good:
        return good["value"], _stale_note(url, int(now - good["at"]))
    code, _ms, body = _get(url, timeout=timeout)
    if code == 200:
        try:
            value = parse(body)
            _last_good[url] = {"value": value, "at": now}
            _fail_until.pop(url, None)
            return value, None
        except Exception as e:                                 # noqa: BLE001
            pass
    _fail_until[url] = now + SOURCE_BACKOFF_S
    if good:
        return good["value"], _stale_note(url, int(now - good["at"]))
    return None, "%s: %s" % (url, code or "no answer")


def _quorum_models():
    v, note = _enumerate(QUORUM_MODELS,
                         lambda b: (json.loads(b).get("models") or []), 6)
    return (v or []), note


def _ollama_ids(base):
    return _enumerate(base + "/models",
                      lambda b: [m["id"] for m in (json.loads(b).get("data") or [])], 10)


def build_catalog():
    """The union. Returns (catalog list, specs dict id->spec, notes list)."""
    notes = []
    cat, specs = [], {}

    def add(mid, label, where, kind, spec, tag=None, note=None, up_hint=None):
        # up_hint: for a seat whose door we deliberately do NOT probe per refresh
        # (a keyed cloud base -- probing it costs a real API call). None means
        # "probe the base"; True/False means "this is what we already know".
        cat.append({"id": mid, "label": label, "where": where, "kind": kind,
                    "tag": tag, "note": note, "base": spec.get("base"),
                    "up_hint": up_hint})
        specs[mid] = spec

    def fresh(url):
        """True when a source answered recently rather than being served stale."""
        return time.time() >= _fail_until.get(url, 0.0)

    # ---- 1. the fleet's OpenAI-compatible doors, straight out of the inventory
    fleet_doors = [
        ("eran2_gptoss", "gpt-oss-120b", "GPT-OSS 120B", "eran2", "הענק שעונה"),
        ("eran1_router", "gpt-oss-120b", "GPT-OSS 120B · alma-router", "eran1", "הנתב"),
        ("coder480", "qwen3-coder-480b", "Qwen3-Coder-480B", "eran2+3+4", "vLLM PP×3"),
    ]
    for door, model, label, where, tag in fleet_doors:
        url = _inv_door(door)
        if not url:
            continue
        base = _base_of(url)
        add("fleet:%s@%s" % (model, door), "%s · %s" % (label, where), where, "openai",
            {"kind": "openai", "base": base, "model": model, "key_env": None,
             "probe": base + "/models"}, tag=tag)

    # ---- 2. ollama boxes: one seat per resident model
    for door, where, tag in (("eran4_ollama", "eran4", "ollama resident"),
                             ("pc_ollama", "PC", "ollama מקומי")):
        url = _inv_door(door) if door != "pc_ollama" else "http://127.0.0.1:11434/v1/models"
        if not url:
            continue
        base = _base_of(url.replace("/api/tags", "/v1/models"))
        ids, note = _ollama_ids(base)
        if note:
            notes.append("%s — %s" % (where, note))
        if not ids:
            continue
        for mid in ids:
            add("ollama:%s@%s" % (mid, where), "%s · %s" % (mid, where), where, "openai",
                {"kind": "openai", "base": base, "model": mid, "key_env": None,
                 "probe": base + "/models"}, tag=tag)

    # ---- 3. Claude, through the CLI that is already logged in on this PC
    for alias, label in CLAUDE_SEATS:
        add("claude:%s" % alias, label, "PC (claude -p)", "claude",
            {"kind": "claude", "model": alias}, tag="OAuth, ללא מפתח")

    # ---- 4. OpenAI -- only if the key is in the environment, and server-side only
    oids = _openai_ids()
    if oids:
        for want in OPENAI_WANT:
            if want in oids:
                add("openai:%s" % want, "OpenAI %s" % want, "api.openai.com", "openai",
                    {"kind": "openai", "base": OPENAI_BASE, "model": want,
                     "key_env": "OPENAI_API_KEY", "probe": None}, tag="הכסף שלו",
                    up_hint=fresh(OPENAI_BASE + "/models"))
    elif os.environ.get("OPENAI_API_KEY"):
        notes.append("OPENAI_API_KEY set but api.openai.com did not list models")
    else:
        notes.append("OPENAI_API_KEY not in this process's environment")

    # ---- 5. whatever QUORUM's hot-reloadable registry has that we do not.
    # QUORUM is asked for its LIVE list; the endpoint details come from its
    # registry file, because /api/models deliberately does not publish keys.
    qm, qerr = _quorum_models()
    if qerr:
        notes.append(qerr)
    reg = {r.get("id"): r for r in (_jload(QUORUM_REGISTRY, {}) or {}).get("models") or []}
    for m in qm:
        mid = m.get("id") or ""
        if (not mid) or mid.startswith("ollama") or mid in ("claude", "grok", "gemini"):
            continue                       # CLI seats: claude is already above, by alias
        r = reg.get(mid)
        if not r or r.get("type") != "openai" or not r.get("base"):
            continue                       # a seat we cannot call is not a seat
        key = "quorum:%s" % mid
        if key in specs:
            continue
        h = m.get("health") or {}
        add(key, m.get("label") or mid, "QUORUM registry", "openai",
            {"kind": "openai", "base": r["base"].rstrip("/") + "/v1",
             "model": r.get("model") or mid, "key_env": r.get("key_env"), "probe": None},
            tag="ענן", note=h.get("detail"),
            up_hint=(h.get("state") in ("up", "installed")) and fresh(QUORUM_MODELS))
    return cat, specs, notes


_specs_lock = threading.Lock()
_specs = {}


def models_state(force=False):
    """The model list + one live pill per BASE (not per model)."""
    now = time.time()
    if not force and _models_cache["data"] and now - _models_cache["at"] < 25:
        return _models_cache["data"]
    cat, specs, notes = build_catalog()
    with _specs_lock:
        _specs.clear()
        _specs.update(specs)

    bases = sorted({s["base"] for s in specs.values()
                    if s.get("kind") == "openai" and s.get("base")})
    probe_of = {}
    for mid, s in specs.items():
        if s.get("base") and s.get("probe"):
            probe_of[s["base"]] = s["probe"]

    def _p(base):
        url = probe_of.get(base)
        if not url:
            # a keyed cloud base (OpenAI/NVIDIA): we already listed its models above,
            # which IS the proof it answers. Do not spend another call per refresh.
            return base, (200, 0)
        if time.time() < _fail_until.get(url, 0.0):
            return base, (None, 0)      # already known down; do not pay the timeout twice
        code, ms, _b = _get(url, timeout=5)
        return base, (code, ms)

    live = {}
    if bases:
        with ThreadPoolExecutor(max_workers=8) as ex:
            for base, (code, ms) in ex.map(_p, bases):
                live[base] = {"code": code, "ms": ms,
                              "up": code is not None and not (isinstance(code, int) and code >= 500)}
    rows = []
    for c in cat:
        if c["kind"] == "claude":
            c = dict(c, up=_claude_present(), code="CLI", ms=0)
        elif c.get("up_hint") is not None:
            c = dict(c, up=bool(c["up_hint"]), code="—" if c["up_hint"] else None, ms=0)
        else:
            l = live.get(c["base"]) or {}
            c = dict(c, up=bool(l.get("up")), code=l.get("code"), ms=l.get("ms"))
        rows.append(c)
    data = {"models": rows, "notes": notes,
            "up": sum(1 for r in rows if r["up"]), "total": len(rows),
            "checked_at": datetime.now().isoformat(timespec="seconds")}
    _models_cache.update(at=now, data=data)
    return data


_claude_cache = {"at": 0.0, "ok": None}


def _claude_present():
    now = time.time()
    if _claude_cache["ok"] is not None and now - _claude_cache["at"] < 600:
        return _claude_cache["ok"]
    import shutil
    ok = bool(shutil.which("claude") or shutil.which("claude.cmd"))
    _claude_cache.update(at=now, ok=ok)
    return ok


# ============================================================= ASK (the chat)
_ask_hits = deque()
_ask_lock = threading.Lock()

# ---------------------------------------------------------------- THE SHIELD
# 2026-09-11. The same shield the WhatsApp bot and the tailnet chat use, imported
# from the one place it is written. This box is CONTROL's chat, which is
# tool-less - so the fencing of tool results does not apply here - but the other
# three defences do: a hardened system boundary, an outbound scrub that removes
# tokens and keys as well as paths, and a per-sender strike count.
#
# SOFT import. If wa-chat-agent is ever not on this machine, CONTROL must still
# come up; it just loses these three and says so in the audit row.
try:
    sys.path.insert(0, r"D:\CLAUDE\wa-chat-agent")
    import shield                                              # noqa: E402
    SHIELD_ON = True
except Exception:                                              # noqa: BLE001
    shield = None
    SHIELD_ON = False

_ASK_SYSTEM_BASE = (
    "You are answering Iddo from his private CONTROL page on his own machine. "
    "Answer briefly and plainly. If he writes Hebrew, answer in Hebrew. "
    "You have no tools and no file access here -- this is conversation only."
)
ASK_SYSTEM = shield.harden_system(_ASK_SYSTEM_BASE) if SHIELD_ON else _ASK_SYSTEM_BASE


def _shield_scrub(text):
    """Outbound. Paths, tokens, keys, JWTs, env dumps - see shield.scrub_sensitive."""
    return shield.scrub_sensitive(text) if SHIELD_ON else text


def _rate_ok():
    now = time.time()
    with _ask_lock:
        while _ask_hits and now - _ask_hits[0] > 60:
            _ask_hits.popleft()
        if len(_ask_hits) >= ASK_RATE_PER_MIN:
            return False
        _ask_hits.append(now)
        return True


def _ask_openai(spec, text):
    base = spec["base"]
    headers = {}
    env = spec.get("key_env")
    if env:
        key = os.environ.get(env)
        if not key:
            return "error", {"reason": "%s is not set in this process" % env}
        headers["Authorization"] = "Bearer " + key       # never logged, never rendered
    payload = {"model": spec["model"],
               "messages": [{"role": "system", "content": ASK_SYSTEM},
                            {"role": "user", "content": text}],
               "max_tokens": 800, "temperature": 0.3, "stream": False}
    code, ms, body = _post_json(base + "/chat/completions", payload,
                                timeout=ASK_TIMEOUT_HTTP, headers=headers)
    if code != 200:
        return "no-answer", {"ms": ms, "code": code, "error": (body or "")[:300]}
    try:
        d = json.loads(body)
        msg = ((d.get("choices") or [{}])[0]).get("message") or {}
        answer = (msg.get("content") or "").strip()
        if not answer:
            answer = (((d.get("choices") or [{}])[0]).get("text") or "").strip()
    except Exception as e:                                     # noqa: BLE001
        return "no-answer", {"ms": ms, "error": "unparsable: %s" % str(e)[:150]}
    if not answer:
        return "no-answer", {"ms": ms, "error": "empty content"}
    return "answered", {"ms": ms, "answer": answer}


def _ask_claude(spec, text):
    """The pattern wa-chat-agent\\claude_brain.py uses today: argv only, prompt on
    stdin, --safe-mode so D:\\CLAUDE\\CLAUDE.md is not picked up, no tools at all."""
    os.makedirs(ASK_CWD, exist_ok=True)
    cmd = ["claude", "-p",
           "--model", spec["model"],
           "--output-format", "text",
           "--safe-mode",
           "--tools", "",
           "--strict-mcp-config",
           "--system-prompt", ASK_SYSTEM]
    t0 = time.time()
    try:
        r = subprocess.run(cmd, input=text, shell=False, capture_output=True, text=True,
                           timeout=ASK_TIMEOUT_CLAUDE, encoding="utf-8", errors="replace",
                           cwd=ASK_CWD, creationflags=_NOWIN | _BELOW_NORMAL)
    except subprocess.TimeoutExpired:
        return "no-answer", {"ms": int((time.time() - t0) * 1000),
                             "error": "claude timed out after %ss" % ASK_TIMEOUT_CLAUDE}
    except FileNotFoundError:
        return "error", {"reason": "claude CLI not on PATH"}
    except Exception as e:                                     # noqa: BLE001
        return "error", {"reason": "%s: %s" % (type(e).__name__, str(e)[:160])}
    ms = int((time.time() - t0) * 1000)
    if r.returncode != 0:
        return "no-answer", {"ms": ms,
                             "error": ((r.stderr or r.stdout or "non-zero exit").strip()
                                       .replace("\n", " ")[:300])}
    answer = (r.stdout or "").strip()
    if not answer:
        return "no-answer", {"ms": ms, "error": "empty reply"}
    return "answered", {"ms": ms, "answer": answer}


def ask(model_id, text, ip=None):
    """Ask one model. Returns (result, detail). Never raises."""
    text = (text or "").strip()
    if not text:
        return "error", {"reason": "empty question"}
    if len(text) > ASK_MAX_CHARS:
        _log("ask", "refused", {"model": model_id, "chars": len(text),
                                "reason": "over %d chars" % ASK_MAX_CHARS}, ip=ip)
        return "refused", {"reason": "השאלה ארוכה מדי (%d תווים, המקסימום %d)"
                                     % (len(text), ASK_MAX_CHARS)}
    if not _rate_ok():
        _log("ask", "rate-limited", {"model": model_id, "chars": len(text)}, ip=ip)
        return "refused", {"reason": "rate limit: %d שאלות לדקה" % ASK_RATE_PER_MIN}
    with _specs_lock:
        spec = _specs.get(model_id)
    if spec is None:
        models_state()                       # the catalogue may simply not be built yet
        with _specs_lock:
            spec = _specs.get(model_id)
    if spec is None:
        _log("ask", "no-such-model", {"model": model_id, "chars": len(text)}, ip=ip)
        return "error", {"reason": "no such model in the catalogue: %s" % model_id}

    # SHIELD: count the strike before the model is reached, and refuse outright
    # while a sender is in cool-off. The identity is the caller's IP, carried as
    # a salted 8-hex id so nothing new about him reaches RAMCHAT or the audit.
    flags, sh = [], None
    if SHIELD_ON:
        flags = shield.detect_injection(text)
        sh = shield.sentinel.note("control:%s" % (ip or "?"), flags)
        if flags:
            _log("ask", "injection-flagged",
                 {"model": model_id, "sender": sh["anon"], "flags": ",".join(flags),
                  "strikes": sh["strikes"]}, ip=ip)
        if sh["blocked"]:
            _log("ask", "shield-blocked",
                 {"model": model_id, "sender": sh["anon"], "strikes": sh["strikes"]}, ip=ip)
            return "refused", {"reason": "יותר מדי ניסיונות לשנות את ההוראות. "
                                         "נסה שוב עוד כמה דקות."}

    if spec["kind"] == "claude":
        result, detail = _ask_claude(spec, text)
    else:
        result, detail = _ask_openai(spec, text)

    # SHIELD: the last line before the answer leaves this process.
    if SHIELD_ON and detail.get("answer"):
        detail["answer"] = _shield_scrub(detail["answer"])
    if sh is not None and sh.get("alert"):
        detail["shield_alert"] = sh["alert"]
    # AUDIT: the model, how big the question was, how big the answer was. Never the text.
    _log("ask", result, {"model": model_id, "kind": spec["kind"],
                         "chars_in": len(text), "chars_out": len(detail.get("answer") or ""),
                         "ms": detail.get("ms")}, ip=ip)
    return result, detail


# ============================================================= QUEUE (RAMCHAT)
_queue_cache = {"at": 0.0, "data": None}
_TERMINAL = ("done", "cancelled", "failed", "rejected")
_BUSY = ("in_progress", "claimed")


def queue_state(force=False, tail=12, open_max=14):
    now = time.time()
    if not force and _queue_cache["data"] and now - _queue_cache["at"] < 5:
        return _queue_cache["data"]
    msgs = _jload(RAMCHAT_SESSION, []) or []
    if isinstance(msgs, dict):
        msgs = msgs.get("messages") or []
    tailrows = [{"who": m.get("who"), "ts": m.get("ts") or m.get("time"),
                 "text": (m.get("text") or "")[:400]} for m in msgs[-tail:]]

    items = _jload(RAMCHAT_QUEUE, []) or []
    if isinstance(items, dict):
        items = items.get("items") or items.get("queue") or []
    open_rows, mine_rows = [], []
    for t in items:
        if not isinstance(t, dict):
            continue
        status = str(t.get("status") or "open")
        row = {"id": t.get("id"), "status": status, "held": t.get("claimed_by"),
               "prompt": (t.get("prompt") or "").replace("\n", " ")[:220],
               "for": t.get("targets") or t.get("for"), "at": t.get("created_at") or t.get("at")}
        if t.get("claimed_by") == QUEUE_WHO and status not in _TERMINAL:
            mine_rows.append(row)
        elif not t.get("claimed_by") and status not in _TERMINAL and status not in _BUSY:
            open_rows.append(row)
    data = {"ramchat": tailrows, "open": open_rows[-open_max:], "mine": mine_rows[-8:],
            "open_total": len(open_rows), "who": QUEUE_WHO,
            "read_at": datetime.now().isoformat(timespec="seconds")}
    _queue_cache.update(at=now, data=data)
    return data


_ID_RE = re.compile(r"^task-[0-9A-Za-z_.:-]{1,64}$")


def queue_op(op, task_id, result_text=None, ip=None):
    """claim / done, through ramlink.py itself -- that is where the atomic lock is."""
    op = str(op or "")
    task_id = str(task_id or "")
    if op not in ("claim", "done"):
        _log("queue." + op, "no-such-op", {"id": task_id}, ip=ip)
        return "error", {"reason": "only claim and done exist here"}
    if not _ID_RE.match(task_id):
        _log("queue." + op, "bad-id", {"id": task_id[:80]}, ip=ip)
        return "error", {"reason": "that is not a task id"}
    if not os.path.isfile(RAMLINK):
        return "error", {"reason": "ramlink.py missing"}
    cmd = [sys.executable, RAMLINK, op, task_id, QUEUE_WHO] if op == "claim" else \
          [sys.executable, RAMLINK, "done", task_id,
           (result_text or "done from the CONTROL page")[:400], "--who", QUEUE_WHO]
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    try:
        p = subprocess.run(cmd, cwd=RAMCHAT_DIR, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=30,
                           creationflags=_NOWIN | _BELOW_NORMAL, env=env)
    except Exception as e:                                     # noqa: BLE001
        _log("queue." + op, "error", {"id": task_id, "exc": str(e)[:160]}, ip=ip)
        return "error", {"reason": str(e)[:200]}
    out = ((p.stdout or "") + (p.stderr or "")).strip()
    _queue_cache["at"] = 0.0                                   # the list just changed
    if p.returncode == 0:
        res = "claimed" if op == "claim" else "done"
    elif "REFUSED" in out:
        res = "refused"
    else:
        res = "error"
    _log("queue." + op, res, {"id": task_id, "out": out[:300]}, ip=ip)
    return res, {"out": out[:600], "rc": p.returncode, "who": QUEUE_WHO}
