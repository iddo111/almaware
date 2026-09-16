# -*- coding: utf-8 -*-
"""
ERAN Federation panel aggregator — לוח הפדרציה של ערן (שרת איסוף)
==================================================================
🪟 BROKEN WINDOWS LAW: if it's not working, fix it immediately. Real output, not a proxy.

Binds 127.0.0.1:8895 (port claimed in RAMCHAT by claude-cli-FABLE, 2026-08-10).
stdlib only. Merges, with per-source caching:

  * HUD collector   http://127.0.0.1:8790/status.json  (minus eran / todo / workflow subtrees)
  * QUORUM          /health (instant) + /api/health + /api/models (cached 30s, timeout 20s)
  * RAMCHAT         durable JSON files ONLY (never the shared-memory blocks) —
                    queue counts honor BOTH status vocabularies
                    (open/in_progress/done AND processing/completed/failed)
  * alma-federation GET http://127.0.0.1:8950/status with X-Alma-Token read at runtime
                    from D:\\CLAUDE\\alma-federation\\.alma_token — the token value is
                    NEVER stored, logged, or echoed in any response.
  * registry.json   probes → every node gets {state: green|red|gray, checked_at, detail}
                    gray = stale/unknown — never fake green (ALMA Standard / BE-TRUTH).

Endpoints:
  GET  /                      panel index.html (bilingual fallback until task 3 lands)
  GET  /api/federation.json   merged snapshot (CORS-open, read-only)
  GET  /api/registry.json     the raw registry (local convenience for the panel)
  GET  /api/push_preview.json the EXACT sanitized payload the cloud pusher sends
  GET  /health                {"ok": true}
  POST /api/talk              {node|model, prompt} → proxy to QUORUM POST /api/chat
                              (200s timeout; REFUSED when the registry's talk is null;
                               requires Content-Type: application/json; NO CORS — quorum
                               is unauthenticated and coder-harness writes real files,
                               so cross-origin browser access to talk stays blocked)

Security notes:
  - Loopback bind only. Never expose this port via funnel/port-forward.
  - CORS "*" is granted ONLY to read-only GET endpoints; /api/talk gets no
    Access-Control-Allow-Origin and OPTIONS never allows POST, so browsers
    enforce same-origin for talk (JSON content-type forces a preflight).
  - public:false registry nodes are INCLUDED in the local snapshot; the cloud
    pusher (task 5) is responsible for dropping them + full sanitization.

Task 5 (live): 60s pusher thread → WHITELIST-sanitized snapshot copy POSTed to the
federation Worker (Bearer FED_PUSH_TOKEN read at runtime from .fed_push_token,
never logged). public:false nodes are dropped; all file paths, tokens, LAN/tailnet
IPs and transcript text are stripped — only names (Hebrew allowed), states,
latencies, ages and counts leave this machine. Self-check before every send:
a payload that fails the forbidden-pattern scan is NOT pushed.
"""

import json
import logging
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
import urllib.error
import urllib.request

# ----------------------------------------------------------------------------- paths / consts
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REGISTRY_PATH = os.path.join(BASE_DIR, "registry.json")
INDEX_PATH = os.path.join(BASE_DIR, "index.html")
LOG_PATH = os.path.join(BASE_DIR, "server.log")
PID_PATH = os.path.join(BASE_DIR, "server.pid")

HOST, PORT = "127.0.0.1", 8895
SELF_PREFIX = "http://127.0.0.1:%d" % PORT

HUD_URL = "http://127.0.0.1:8790/status.json"
QUORUM_BASE = "http://127.0.0.1:8099"
QUORUM_HEALTH = QUORUM_BASE + "/health"
QUORUM_API_HEALTH = QUORUM_BASE + "/api/health"
QUORUM_API_MODELS = QUORUM_BASE + "/api/models"
QUORUM_CHAT = QUORUM_BASE + "/api/chat"

ALMA_STATUS_URL = "http://127.0.0.1:8950/status"
ALMA_TOKEN_PATH = r"D:\CLAUDE\alma-federation\.alma_token"

RAMCHAT_DIR = r"D:\CLAUDE\RAMCHAT"
RC_SESSION = os.path.join(RAMCHAT_DIR, "ramchat_session.json")
RC_QUEUE = os.path.join(RAMCHAT_DIR, "ramchat_prompt_queue.json")
RC_ROSTER = os.path.join(RAMCHAT_DIR, "roster.json")
RC_WATCHDOG = os.path.join(RAMCHAT_DIR, "ramchat_watchdog_status.json")

# ramlink.py's two live status vocabularies (GUI + ramlink) — both must count.
TERMINAL_STATUS = {"done", "cancelled", "completed", "failed", "rejected"}
BUSY_STATUS = {"in_progress", "processing", "claimed"}

HUD_STRIP = ("eran", "todo", "workflow")  # fossil / hardcoded fake / finished journal
HUD_KEEP = ("meta", "services", "projects", "git", "system")  # + fleet/fabric promoted

TALK_TIMEOUT_S = 200
MAX_TALK_BODY = 65536
ROSTER_STALE_S = 20 * 60  # roster_probe runs every 5 min; >20 min = stale
SNAPSHOT_TTL_S = 2.0

# --- cloud pusher (task 5) ---------------------------------------------------
PUSH_URLS = (
    "https://federation.iddoperez.ai/api/push",
    "https://federation.almaware.workers.dev/api/push",  # workers.dev fallback
)
PUSH_TOKEN_PATH = os.path.join(BASE_DIR, ".fed_push_token")
# 2026-08-26 night: 60s pushes = 1,440 KV writes/day > the 1,000/day free quota —
# quota exhausted daily (~22:15, resets 03:00 JDT) and every push then 500s.
# 120s = 720/day, safely under. The real fix is snapshot-in-GridDO like grid v2.
PUSH_INTERVAL_S = 120
PUSH_TIMEOUT_S = 25
# A real UA is REQUIRED: Cloudflare bot protection 403s the default urllib UA
# (verified during the task-4 worker deploy).
PUSH_UA = "eran-federation-pusher/1.0"

GREEN, RED, GRAY = "green", "red", "gray"

log = logging.getLogger("fedpanel")


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def iso(ts):
    try:
        return datetime.fromtimestamp(ts, timezone.utc).astimezone().isoformat(timespec="seconds")
    except Exception:
        return None


# ----------------------------------------------------------------------------- TTL cache
class SourceCache:
    """Per-key TTL cache with per-key locks (no stampede; errors are cached too)."""

    def __init__(self):
        self._entries = {}   # key -> (fetched_at, value, error_str_or_None)
        self._locks = {}
        self._glock = threading.Lock()

    def _lock_for(self, key):
        with self._glock:
            return self._locks.setdefault(key, threading.Lock())

    def get(self, key, ttl, producer):
        ent = self._entries.get(key)
        if ent and time.time() - ent[0] < ttl:
            return ent
        lk = self._lock_for(key)
        with lk:
            ent = self._entries.get(key)
            if ent and time.time() - ent[0] < ttl:
                return ent
            try:
                val = producer()
                ent = (time.time(), val, None)
            except Exception as exc:  # error cached for ttl → no hammering a dead source
                ent = (time.time(), None, "%s: %s" % (type(exc).__name__, exc))
            self._entries[key] = ent
            return ent


CACHE = SourceCache()


# ----------------------------------------------------------------------------- fetch helpers
def http_get_json(url, timeout, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def http_probe(url, timeout=3.0):
    """Liveness probe: 2xx-4xx = answering (green); refused/timeout = down."""
    t0 = time.time()
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return {"up": True, "status": resp.status,
                    "latency_ms": int((time.time() - t0) * 1000)}
    except urllib.error.HTTPError as exc:
        return {"up": 200 <= exc.code < 500, "status": exc.code,
                "latency_ms": int((time.time() - t0) * 1000)}
    except Exception as exc:
        return {"up": False, "error": "%s: %s" % (type(exc).__name__, exc)}


def read_json_file(path):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        mtime = None
    return {"data": data, "mtime": mtime}


# ----------------------------------------------------------------------------- cached sources
def get_hud():
    return CACHE.get("hud", 5, lambda: http_get_json(HUD_URL, 4))


def get_quorum_health():
    return CACHE.get("q_health", 5, lambda: http_get_json(QUORUM_HEALTH, 3))


def get_quorum_api_health():
    return CACHE.get("q_api_health", 30, lambda: http_get_json(QUORUM_API_HEALTH, 20))


def get_quorum_api_models():
    return CACHE.get("q_api_models", 30, lambda: http_get_json(QUORUM_API_MODELS, 20))


def _fetch_alma():
    """GET alma-federation /status. Token read at runtime, kept in this frame only."""
    try:
        with open(ALMA_TOKEN_PATH, encoding="utf-8") as fh:
            token = fh.read().strip()
    except OSError:
        return {"error": "credential file unreadable", "http_status": None}
    if not token:
        return {"error": "credential file empty", "http_status": None}
    req = urllib.request.Request(ALMA_STATUS_URL, headers={"X-Alma-Token": token})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return {"http_status": resp.status,
                    "data": json.loads(resp.read().decode("utf-8", "replace"))}
    except urllib.error.HTTPError as exc:
        return {"http_status": exc.code, "error": "HTTP %d" % exc.code}
    except Exception as exc:
        return {"http_status": None, "error": "%s: %s" % (type(exc).__name__, exc)}


def get_alma():
    return CACHE.get("alma", 15, _fetch_alma)


def get_ramchat_file(path):
    return CACHE.get("rc:" + path, 5, lambda: read_json_file(path))


def get_http_probe(url):
    ttl = 120 if url.startswith("https://") else 10
    timeout = 6.0 if url.startswith("https://") else 3.0
    return CACHE.get("probe:" + url, ttl, lambda: http_probe(url, timeout))


def get_registry():
    def _load():
        return read_json_file(REGISTRY_PATH)
    return CACHE.get("registry", 10, _load)


# ----------------------------------------------------------------------------- JSON pointer + fragments
def json_pointer(doc, pointer):
    """RFC 6901. '' or '/' → whole doc. Returns (value, found)."""
    if pointer in ("", "/"):
        return doc, True
    cur = doc
    for tok in pointer.split("/")[1:]:
        tok = tok.replace("~1", "/").replace("~0", "~")
        if isinstance(cur, dict):
            if tok not in cur:
                return None, False
            cur = cur[tok]
        elif isinstance(cur, list):
            try:
                cur = cur[int(tok)]
            except (ValueError, IndexError):
                return None, False
        else:
            return None, False
    return cur, True


def find_in_models(doc, wanted_id):
    """'#id=X' convention: element with id==X inside the top-level models array."""
    arr = doc.get("models") if isinstance(doc, dict) else doc
    if not isinstance(arr, list):
        return None, False
    for item in arr:
        if isinstance(item, dict) and item.get("id") == wanted_id:
            return item, True
    return None, False


# ----------------------------------------------------------------------------- node classification
def _fmt_age(seconds):
    if seconds is None:
        return "?"
    seconds = int(seconds)
    if seconds < 3600:
        return "%dm" % (seconds // 60)
    if seconds < 172800:
        return "%.1fh" % (seconds / 3600)
    return "%dd" % (seconds // 86400)


def classify_value(value):
    """Map a resolved JSON value to (state, detail). Honest: unknown shape → gray."""
    if isinstance(value, dict):
        # HUD fleet node: {"reachable": bool, load, mem, gpu[...]}
        if "reachable" in value:
            if value.get("reachable"):
                bits = []
                load = value.get("load")
                if isinstance(load, list) and load:
                    bits.append("load %s" % load[0])
                mem = value.get("mem") or {}
                if isinstance(mem, dict) and mem.get("pct") is not None:
                    bits.append("mem %s%%" % mem.get("pct"))
                gpu = value.get("gpu")
                if isinstance(gpu, list) and gpu and isinstance(gpu[0], dict):
                    g = gpu[0]
                    seg = "GPU %s%%" % g.get("util_pct")
                    if g.get("temp_c") is not None:
                        seg += " %sC" % g.get("temp_c")
                    if g.get("power_w") is not None:
                        seg += " %sW" % g.get("power_w")
                    bits.append(seg)
                return GREEN, "reachable — " + (", ".join(bits) or "no metrics")
            return RED, "unreachable: %s" % (value.get("error") or "ssh probe failed")

        # HUD fabric: {"links": {name: {state: up|down, ...}}}
        if isinstance(value.get("links"), dict):
            links = value["links"]
            total = len(links)
            up = sum(1 for l in links.values()
                     if isinstance(l, dict) and l.get("state") == "up")
            if value.get("error"):
                return GRAY, "fabric probe error: %s" % value["error"]
            if total == 0:
                return GRAY, "no links reported"
            if up == total:
                speeds = {l.get("speed_gbps") for l in links.values() if isinstance(l, dict)}
                sp = ("@%sG" % speeds.pop()) if len(speeds) == 1 and None not in speeds else ""
                return GREEN, "%d/%d links up %s" % (up, total, sp)
            return RED, "only %d/%d links up" % (up, total)

        # quorum /api/health models entry OR /api/models health: {"state": ..}
        st = value.get("state")
        if isinstance(st, str):
            if st in ("up", "ready", "ok", "running"):
                return GREEN, str(value.get("detail") or st)
            if st == "installed":
                return GREEN, "installed (presence only — first real turn is the gate)"
            if st in ("down", "auth", "dead", "error"):
                return RED, str(value.get("detail") or st)
            return GRAY, "state=%s %s" % (st, value.get("detail") or "")

        # /api/models entry: {"id","label","health":{...}}
        if "health" in value and isinstance(value["health"], dict):
            state, detail = classify_value(value["health"])
            label = value.get("label")
            return state, ("%s — %s" % (label, detail)) if label else detail

        # HUD service / generic: {"up": bool}
        if "up" in value:
            if value.get("up"):
                lat = value.get("latency_ms")
                stc = value.get("status") or value.get("status_code")
                bits = [b for b in (("HTTP %s" % stc) if stc else None,
                                    ("%sms" % lat) if lat is not None else None) if b]
                return GREEN, " ".join(bits) or "answering"
            return RED, str(value.get("error") or "not answering")

        # HUD project item: {"exists","last_mtime","age_s","active","file_count"}
        if "exists" in value:
            if not value.get("exists"):
                return RED, "directory missing"
            age = value.get("age_s")
            if value.get("active"):
                return GREEN, "active — changed %s ago, %s files" % (
                    _fmt_age(age), value.get("file_count", "?"))
            return GRAY, "quiet — last change %s ago" % _fmt_age(age)

        # roster member: {"status": "alive"|"dead", "detail", "fails"}
        if value.get("status") in ("alive", "dead"):
            det = str(value.get("detail") or "")
            if value["status"] == "alive":
                return GREEN, det or "alive"
            fails = value.get("fails")
            return RED, (det or "dead") + (" (fails=%s)" % fails if fails else "")

        # watchdog gui block: {"ok": bool}
        if "ok" in value:
            return (GREEN, "ok") if value.get("ok") else (RED, "not ok")

        return GRAY, "unrecognized shape — not measured"

    if isinstance(value, list):
        return GREEN, "%d entries" % len(value)
    return GRAY, "unrecognized value — not measured"


# ----------------------------------------------------------------------------- node evaluation
def eval_node(node):
    """Return {id, name, name_he, kind, public, talk, state, checked_at, detail}."""
    out = {
        "id": node.get("id"),
        "name": node.get("name"),
        "name_he": node.get("name_he"),
        "kind": node.get("kind"),
        "public": bool(node.get("public")),
        "talk": (node.get("talk") or {}).get("model_id") if node.get("talk") else None,
        "state": GRAY,
        "checked_at": now_iso(),
        "detail": "not probed",
    }
    probe = node.get("probe") or {}
    ptype = probe.get("type")
    target = probe.get("target", "")

    try:
        if ptype == "http":
            if target.startswith(SELF_PREFIX):
                # self-probe would deadlock the snapshot lock — we are obviously serving.
                out.update(state=GREEN, detail="this server — answering (self)")
                return out
            ts, val, err = get_http_probe(target)
            out["checked_at"] = iso(ts) or out["checked_at"]
            if err:
                out.update(state=RED, detail=err)
            else:
                out["state"], out["detail"] = classify_value(val)

        elif ptype == "status_json":
            base, _, frag = target.partition("#")
            if base.startswith(HUD_URL):
                ts, doc, err = get_hud()
                src = "HUD :8790"
            elif base == QUORUM_API_HEALTH:
                ts, doc, err = get_quorum_api_health()
                src = "quorum /api/health"
            elif base == QUORUM_API_MODELS:
                ts, doc, err = get_quorum_api_models()
                src = "quorum /api/models"
            else:
                ts, doc, err = CACHE.get("json:" + base, 15,
                                         lambda: http_get_json(base, 6))
                src = base
            out["checked_at"] = iso(ts) or out["checked_at"]
            if err or doc is None:
                out.update(state=GRAY, detail="source unreachable (%s): %s" % (src, err))
                return out
            if frag.startswith("id="):
                value, found = find_in_models(doc, frag[3:])
                if not found:
                    out.update(state=GRAY,
                               detail="not present in %s (route not configured)" % src)
                    return out
            else:
                value, found = json_pointer(doc, frag)
                if not found:
                    out.update(state=GRAY,
                               detail="key %r missing in %s — not tracked yet" % (frag, src))
                    return out
            # strip eran/todo/workflow even if a pointer lands on the HUD root
            if base.startswith(HUD_URL) and isinstance(value, dict) and frag in ("", "/"):
                value = {k: v for k, v in value.items() if k not in HUD_STRIP}
            out["state"], out["detail"] = classify_value(value)

        elif ptype == "ramchat_file":
            path, _, frag = target.partition("#")
            ts, blob, err = get_ramchat_file(path)
            out["checked_at"] = iso(ts) or out["checked_at"]
            if err or blob is None:
                out.update(state=RED, detail="file unreadable: %s" % err)
                return out
            value, found = json_pointer(blob["data"], frag)
            if not found:
                out.update(state=GRAY, detail="key %r missing in %s" %
                                              (frag, os.path.basename(path)))
                return out
            state, detail = classify_value(value)
            # roster/watchdog staleness: old file → we do NOT know → gray
            mtime = blob.get("mtime")
            if mtime and (time.time() - mtime) > ROSTER_STALE_S and \
                    os.path.basename(path) in ("roster.json", "ramchat_watchdog_status.json"):
                state = GRAY
                detail = "stale (%s old) — last known: %s" % (
                    _fmt_age(time.time() - mtime), detail)
            if os.path.basename(path) == "ramchat_prompt_queue.json" and frag in ("", "/"):
                counts = queue_counts(value)
                detail = ("%(total)d tasks — open %(open)d, busy %(busy)d, "
                          "terminal %(terminal)d" % counts)
            out.update(state=state, detail=detail)

        elif ptype == "alma_status":
            ts, val, err = get_alma()
            out["checked_at"] = iso(ts) or out["checked_at"]
            if err or val is None:
                out.update(state=RED, detail="probe failed: %s" % err)
            elif val.get("http_status") == 200:
                data = val.get("data") or {}
                out.update(state=GREEN,
                           detail="DRY-RUN — polling, NOT executing; pending=%s jobs=%s "
                                  "online=%s" % (data.get("pending"), data.get("jobs"),
                                                 data.get("online")))
            elif val.get("http_status") == 401:
                out.update(state=RED, detail="401 unauthorized (credential mismatch)")
            else:
                out.update(state=RED, detail=str(val.get("error") or "unreachable"))
        else:
            out.update(state=GRAY, detail="unknown probe type %r" % ptype)
    except Exception as exc:  # a single bad node must never kill the snapshot
        log.exception("eval_node %s failed", node.get("id"))
        out.update(state=GRAY, detail="probe crashed: %s: %s" % (type(exc).__name__, exc))
    return out


# ----------------------------------------------------------------------------- section builders
def queue_counts(items):
    by_status = {}
    open_n = busy_n = term_n = 0
    for it in items if isinstance(items, list) else []:
        st = str(it.get("status") or "")
        by_status[st] = by_status.get(st, 0) + 1
        if st in TERMINAL_STATUS:
            term_n += 1
        elif st in BUSY_STATUS:
            busy_n += 1
        elif not it.get("claimed_by"):
            open_n += 1
    return {"total": len(items) if isinstance(items, list) else 0,
            "open": open_n, "busy": busy_n, "terminal": term_n,
            "by_status": by_status}


def build_ramchat_section():
    sec = {"checked_at": now_iso()}
    ts, blob, err = get_ramchat_file(RC_ROSTER)
    if err or blob is None:
        sec["roster"] = {"error": err}
    else:
        age = (time.time() - blob["mtime"]) if blob.get("mtime") else None
        data = blob["data"]
        sec["roster"] = {
            "updated_at": data.get("updated_at"),
            "file_age_s": int(age) if age is not None else None,
            "stale": bool(age and age > ROSTER_STALE_S),
            "members": data.get("members", {}),
        }
    ts, blob, err = get_ramchat_file(RC_QUEUE)
    if err or blob is None:
        sec["queue"] = {"error": err}
    else:
        sec["queue"] = queue_counts(blob["data"])
    ts, blob, err = get_ramchat_file(RC_WATCHDOG)
    if err or blob is None:
        sec["watchdog"] = {"error": err}
    else:
        wd = blob["data"]
        sec["watchdog"] = {
            "checked_at": wd.get("checked_at"),
            "gui_ok": bool((wd.get("gui") or {}).get("ok")),
            "shared_memory": {k: bool(v.get("ok")) if isinstance(v, dict) else None
                              for k, v in (wd.get("shared_memory") or {}).items()},
        }
    ts, blob, err = get_ramchat_file(RC_SESSION)
    if err or blob is None:
        sec["transcript"] = {"error": err}
    else:
        msgs = blob["data"] if isinstance(blob["data"], list) else []
        sec["transcript"] = {
            "total": len(msgs),
            "last5": [{"who": m.get("who"), "at": m.get("at"),
                       "text": (m.get("text") or "")[:400]} for m in msgs[-5:]],
        }
    return sec


def build_quorum_section():
    sec = {}
    ts, val, err = get_quorum_health()
    sec["health"] = {"checked_at": iso(ts), "data": val, "error": err,
                     "state": GREEN if (val and val.get("ok")) else RED}
    ts, val, err = get_quorum_api_health()
    if err or val is None:
        sec["api_health"] = {"checked_at": iso(ts), "error": err, "state": GRAY}
    else:
        sec["api_health"] = {
            "checked_at": iso(ts), "state": GREEN if val.get("ok") else RED,
            "enabled": val.get("enabled"),
            "models": val.get("models"),
            "workers": val.get("workers"),
            "rooms": val.get("rooms"),
        }
    return sec


def build_alma_section():
    ts, val, err = get_alma()
    sec = {"checked_at": iso(ts),
           "note": "DRY-RUN — a green light means the worker is POLLING, not executing "
                   "(הרצה יבשה — ירוק פירושו תשאול בלבד)"}
    if err or val is None:
        sec.update(state=RED, detail=str(err))
    elif val.get("http_status") == 200:
        data = val.get("data") or {}
        sec.update(state=GREEN, pending=data.get("pending"), jobs=data.get("jobs"),
                   nodes=data.get("nodes"), online=data.get("online"))
    elif val.get("http_status") == 401:
        sec.update(state=RED, detail="401 unauthorized (credential mismatch)")
    else:
        sec.update(state=RED, detail=str(val.get("error") or "unreachable"))
    return sec


def prefetch_sources(nodes):
    """Warm every distinct source in parallel so node eval is all cache hits."""
    jobs = [get_hud, get_quorum_health, get_quorum_api_health, get_quorum_api_models,
            get_alma,
            lambda: get_ramchat_file(RC_ROSTER), lambda: get_ramchat_file(RC_QUEUE),
            lambda: get_ramchat_file(RC_WATCHDOG), lambda: get_ramchat_file(RC_SESSION)]
    for node in nodes:
        probe = node.get("probe") or {}
        if probe.get("type") == "http":
            url = probe.get("target", "")
            if url and not url.startswith(SELF_PREFIX):
                jobs.append(lambda u=url: get_http_probe(u))
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = [pool.submit(j) for j in jobs]
        for fut in futures:
            try:
                fut.result(timeout=25)
            except Exception:
                pass


def _build_snapshot():
    ts, reg_blob, reg_err = get_registry()
    nodes_def = (reg_blob["data"].get("nodes") if reg_blob else None) or []
    prefetch_sources(nodes_def)

    hud_ts, hud_doc, hud_err = get_hud()
    hud_doc = hud_doc if isinstance(hud_doc, dict) else {}
    fleet = hud_doc.get("fleet") or {"error": hud_err or "hud unreachable"}
    fabric = hud_doc.get("fabric") or {"error": hud_err or "hud unreachable"}
    hud_slim = {k: hud_doc[k] for k in HUD_KEEP if k in hud_doc}
    hud_slim["checked_at"] = iso(hud_ts)
    if hud_err:
        hud_slim["error"] = hud_err

    snapshot = {
        "schema": "fed-snapshot-v1",
        "generated_at": now_iso(),
        "generated_by": "eran-federation panel aggregator :8895 (local, loopback-only)",
        "nodes": [eval_node(n) for n in nodes_def],
        "fleet": fleet,
        "fabric": fabric,
        "quorum": build_quorum_section(),
        "ramchat": build_ramchat_section(),
        "alma_federation": build_alma_section(),
        "hud": hud_slim,
        "registry": {"count": len(nodes_def), "error": reg_err,
                     "loaded_at": iso(ts) if ts else None},
        "pusher": dict(PUSHER_STATE),  # local truth about the cloud push loop
    }
    counts = {}
    for n in snapshot["nodes"]:
        counts[n["state"]] = counts.get(n["state"], 0) + 1
    snapshot["summary"] = {"nodes_total": len(snapshot["nodes"]), "by_state": counts}
    return snapshot


def get_snapshot():
    ts, snap, err = CACHE.get("snapshot", SNAPSHOT_TTL_S, _build_snapshot)
    if snap is None:
        return {"schema": "fed-snapshot-v1", "generated_at": now_iso(),
                "error": err, "nodes": [], "fleet": {}, "fabric": {},
                "quorum": {}, "ramchat": {}, "alma_federation": {}}
    return snap


# ----------------------------------------------------------------------------- talk proxy
def do_talk(payload):
    """{node|model, prompt} → quorum POST /api/chat. Refuses talk-less nodes."""
    prompt = payload.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return 400, {"ok": False, "error": "prompt required (חסר prompt)"}

    node_id = payload.get("node")
    model_id = None
    ts, reg_blob, reg_err = get_registry()
    nodes_def = (reg_blob["data"].get("nodes") if reg_blob else None) or []

    if node_id:
        node = next((n for n in nodes_def if n.get("id") == node_id), None)
        if node is None:
            return 404, {"ok": False, "error": "unknown node %r (צומת לא מוכר)" % node_id}
        talk = node.get("talk")
        if not talk or not talk.get("model_id"):
            return 403, {"ok": False,
                         "error": "node %r has no talk route — refused "
                                  "(לצומת הזה אין ערוץ דיבור)" % node_id}
        model_id = talk["model_id"]
    elif payload.get("model"):
        wanted = payload["model"]
        node = next((n for n in nodes_def
                     if (n.get("talk") or {}).get("model_id") == wanted), None)
        if node is None:
            return 403, {"ok": False,
                         "error": "model %r is not a registered talk route — refused" % wanted}
        model_id = wanted
    else:
        return 400, {"ok": False, "error": "node or model required"}

    body = {"model": model_id, "prompt": prompt}
    if isinstance(payload.get("max_tokens"), int):
        body["max_tokens"] = payload["max_tokens"]
    raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(QUORUM_CHAT, data=raw,
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=TALK_TIMEOUT_S) as resp:
            out = json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        try:
            out = json.loads(exc.read().decode("utf-8", "replace"))
        except Exception:
            out = {"ok": False, "error": "quorum HTTP %d" % exc.code}
        return 502, out
    except Exception as exc:
        return 502, {"ok": False,
                     "error": "quorum unreachable: %s: %s" % (type(exc).__name__, exc)}
    out.setdefault("elapsed", round(time.time() - t0, 1))
    out.setdefault("model", model_id)
    return 200, out


# ----------------------------------------------------------------------------- HTTP handler
FALLBACK_INDEX = """<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>לוח הפדרציה של ערן · ERAN Federation Panel</title>
<style>body{font-family:system-ui,'Segoe UI',sans-serif;background:#f7f9fc;color:#123;
margin:0;padding:3rem;text-align:center}h1{font-size:1.6rem}
a{color:#0b62d6}.card{background:#fff;border:1px solid #dde5f0;border-radius:12px;
max-width:640px;margin:2rem auto;padding:2rem;box-shadow:0 2px 8px rgba(20,40,80,.06)}
code{background:#eef3fa;padding:.15em .4em;border-radius:6px;direction:ltr;display:inline-block}
</style></head><body><div class="card">
<h1>לוח הפדרציה של ערן · ERAN Federation Panel</h1>
<p>שרת האיסוף חי. ממשק הלוח המלא נבנה כרגע (משימה 3).<br>
The aggregator is alive. The full panel UI is being built (task 3).</p>
<p>נתונים חיים · live data: <a href="/api/federation.json"><code>/api/federation.json</code></a></p>
</div></body></html>"""


class Handler(BaseHTTPRequestHandler):
    server_version = "FedPanel/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        log.info("%s %s", self.address_string(), fmt % args)

    # -- helpers ------------------------------------------------------------
    def _send(self, code, payload, ctype="application/json; charset=utf-8", cors=False):
        if isinstance(payload, (dict, list)):
            body = json.dumps(payload, ensure_ascii=False, indent=1).encode("utf-8")
        elif isinstance(payload, str):
            body = payload.encode("utf-8")
        else:
            body = payload
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if cors:  # read-only GET endpoints only — never /api/talk
            self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (ConnectionError, BrokenPipeError):
            pass

    # -- GET ----------------------------------------------------------------
    def do_GET(self):
        path = urlsplit(self.path).path
        if path in ("/", "/index.html"):
            if os.path.isfile(INDEX_PATH):
                with open(INDEX_PATH, encoding="utf-8") as fh:
                    html = fh.read()
            else:
                html = FALLBACK_INDEX
            self._send(200, html, "text/html; charset=utf-8")
        elif path == "/api/federation.json":
            self._send(200, get_snapshot(), cors=True)
        elif path == "/api/registry.json":
            ts, blob, err = get_registry()
            if blob is None:
                self._send(500, {"ok": False, "error": err}, cors=True)
            else:
                self._send(200, blob["data"], cors=True)
        elif path == "/api/push_preview.json":
            # the EXACT sanitized payload the 60s pusher would send right now
            self._send(200, build_public_payload(get_snapshot()), cors=True)
        elif path == "/health":
            self._send(200, {"ok": True, "service": "eran-federation-panel",
                             "port": PORT, "ts": now_iso()}, cors=True)
        else:
            self._send(404, {"ok": False, "error": "not found"})

    def do_HEAD(self):
        self.do_GET()

    # -- OPTIONS (CORS preflight: GET-only, talk is never allowed) ----------
    def do_OPTIONS(self):
        path = urlsplit(self.path).path
        if path == "/api/talk":
            # No Access-Control-Allow-* → browser blocks cross-origin talk.
            self._send(403, {"ok": False,
                             "error": "talk is same-origin only (מקומי בלבד)"})
            return
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", "0")
        self.end_headers()

    # -- POST ---------------------------------------------------------------
    def do_POST(self):
        path = urlsplit(self.path).path
        if path != "/api/talk":
            self._send(404, {"ok": False, "error": "not found"})
            return
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype != "application/json":
            self._send(415, {"ok": False,
                             "error": "Content-Type must be application/json"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_TALK_BODY:
            self._send(413, {"ok": False, "error": "body size out of range"})
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8", "replace"))
            if not isinstance(payload, dict):
                raise ValueError("payload must be a JSON object")
        except Exception as exc:
            self._send(400, {"ok": False, "error": "bad JSON: %s" % exc})
            return
        code, out = do_talk(payload)
        self._send(code, out)


# ----------------------------------------------------------------------------- public payload (sanitizer)
# WHITELIST philosophy: nothing enters the cloud payload unless a line below
# explicitly copies it. Kept: node names (Hebrew allowed), states, latencies,
# ages, counts. Stripped: file paths, tokens, LAN/tailnet/loopback IPs, URLs,
# transcript text, backslashes, private (public:false) nodes.

_SCRUB_PATTERNS = [
    ("win-path", re.compile(r"[A-Za-z]:[\\/]")),
    ("backslash", re.compile(r"\\")),
    ("lan-ip", re.compile(r"192\.168\.")),
    ("cgnat-ip", re.compile(r"100\.")),          # tailnet <tailnet-ip>/10 style
    ("lan10-ip", re.compile(r"10\.0\.")),
    ("loopback", re.compile(r"127\.0\.0\.1")),
    ("url", re.compile(r"://")),
    ("token-word", re.compile(r"token", re.I)),
    ("tailnet", re.compile(r"ts\.net", re.I)),
]

GENERIC_DETAIL = {
    GREEN: "measured OK (נמדד — תקין)",
    RED: "measured DOWN (נמדד — לא עונה)",
    GRAY: "not measured (לא נמדד)",
}


def _dirty(text):
    return any(rx.search(text) for _, rx in _SCRUB_PATTERNS)


def scrub_text(text, state=GRAY):
    """Pass a detail string through the forbidden scan; on ANY hit, fall back to
    an honest generic per-state phrase (never leak, never fake green)."""
    if not isinstance(text, str) or not text.strip():
        return GENERIC_DETAIL.get(state, GENERIC_DETAIL[GRAY])
    # quotes/control chars would create backslash escapes in the JSON wire text
    text = text.replace('"', "'").replace("\n", " ").replace("\r", " ").replace("\t", " ")
    if _dirty(text):
        return GENERIC_DETAIL.get(state, GENERIC_DETAIL[GRAY])
    return text


def pubnum(v):
    """Numbers that can NEVER serialize with a '100.'-style substring:
    floats with integer part >= 100 (or whole floats) become ints."""
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        r = round(v, 2)
        if r == int(r) or abs(r) >= 99.995:
            return int(round(v))
        return r
    return None


def _pub_fleet(fleet):
    out = {}
    for name, val in (fleet or {}).items():
        if name.startswith("_") or not isinstance(val, dict) or _dirty(name):
            continue
        ent = {"reachable": bool(val.get("reachable"))}
        mem = val.get("mem") or {}
        if isinstance(mem, dict) and isinstance(mem.get("pct"), (int, float)):
            ent["mem_pct"] = pubnum(mem["pct"])
        load = val.get("load")
        if isinstance(load, list) and load and isinstance(load[0], (int, float)):
            ent["load_1m"] = pubnum(load[0])
        gpu = val.get("gpu")
        if isinstance(gpu, list) and gpu and isinstance(gpu[0], dict):
            g = gpu[0]
            ent["gpu"] = {k: pubnum(g[k]) for k in ("util_pct", "temp_c", "power_w")
                          if isinstance(g.get(k), (int, float))}
        out[name] = ent
    if not out:
        return {"note": "fleet not measured (לא נמדד)"}
    meta = (fleet or {}).get("_meta") or {}
    if isinstance(meta.get("cache_age_s"), (int, float)):
        out["_age_s"] = pubnum(meta["cache_age_s"])
    return out


def _pub_fabric(fabric):
    links = (fabric or {}).get("links")
    if not isinstance(links, dict) or not links:
        return {"note": "fabric not measured (לא נמדד)"}
    out_links, up = {}, 0
    for lname, l in links.items():
        if not isinstance(l, dict):
            continue
        key = lname if (isinstance(lname, str) and not _dirty(lname)) else \
            "link-%d" % (len(out_links) + 1)
        state = l.get("state") if l.get("state") in ("up", "down") else "unknown"
        ent = {"state": state}
        if isinstance(l.get("speed_gbps"), (int, float)):
            ent["speed_gbps"] = pubnum(l["speed_gbps"])
        out_links[key[:60]] = ent
        up += state == "up"
    return {"links": out_links, "links_up": up, "links_total": len(out_links)}


def _pub_quorum(q):
    out = {}
    h = (q or {}).get("health") or {}
    out["state"] = h.get("state") if h.get("state") in (GREEN, RED) else GRAY
    ah = (q or {}).get("api_health") or {}
    if isinstance(ah.get("enabled"), bool):
        out["enabled"] = ah["enabled"]
    models = ah.get("models")
    if isinstance(models, dict):
        out["models"] = {}
        for mid, m in models.items():
            if not isinstance(mid, str) or _dirty(mid):
                continue
            st = m.get("state") if isinstance(m, dict) else None
            out["models"][mid[:60]] = st if st in (
                "up", "down", "auth", "ready", "installed", "unknown") else "unknown"
    workers = ah.get("workers")
    if isinstance(workers, dict):
        out["workers"] = {k: workers[k] for k in ("workers_total", "workers_live", "jobs")
                          if isinstance(workers.get(k), int)}
    rooms = ah.get("rooms")
    if isinstance(rooms, dict):
        out["rooms"] = {k: rooms[k] for k in ("rooms", "messages")
                        if isinstance(rooms.get(k), int)}
    return out


def _pub_ramchat(rc):
    out = {}
    q = (rc or {}).get("queue") or {}
    out["queue"] = {k: q[k] for k in ("total", "open", "busy", "terminal")
                    if isinstance(q.get(k), int)}
    roster = (rc or {}).get("roster") or {}
    members = roster.get("members") or {}
    alive = dead = 0
    mem_out = {}
    for label, m in members.items() if isinstance(members, dict) else []:
        st = (m or {}).get("status") if isinstance(m, dict) else None
        if st == "alive":
            alive += 1
        elif st == "dead":
            dead += 1
        else:
            continue
        if isinstance(label, str) and label.strip() and not _dirty(label):
            mem_out[label[:60]] = st  # label only — details (Hebrew text) stay local
    out["roster"] = {"alive": alive, "dead": dead,
                     "stale": bool(roster.get("stale")), "members": mem_out}
    tr = (rc or {}).get("transcript") or {}
    if isinstance(tr.get("total"), int):
        out["transcript_messages"] = tr["total"]  # COUNT only — text never leaves
    return out


def _pub_alma(a):
    a = a or {}
    out = {"state": a.get("state") if a.get("state") in (GREEN, RED, GRAY) else GRAY,
           "note": "DRY-RUN — polling only, not executing (הרצה יבשה — תשאול בלבד)"}
    for k in ("pending", "jobs", "nodes"):
        if isinstance(a.get(k), (int, float)):
            out[k] = pubnum(a[k])
    if isinstance(a.get("online"), list):
        out["online_count"] = len(a["online"])
    return out


def build_public_payload(snapshot):
    """WHITELIST copy of the local snapshot for the cloud front door."""
    nodes_out, hidden = [], 0
    for n in snapshot.get("nodes") or []:
        if not n.get("public"):
            hidden += 1
            continue
        state = n.get("state") if n.get("state") in (GREEN, RED, GRAY) else GRAY
        ident = str(n.get("id") or "")
        name = str(n.get("name") or ident)
        name_he = str(n.get("name_he") or "")
        if not ident or _dirty(ident) or _dirty(name) or _dirty(name_he):
            hidden += 1  # curated names must already be clean; a dirty one is dropped whole
            continue
        kind = n.get("kind")
        nodes_out.append({
            "id": ident[:80],
            "name": name[:120],
            "name_he": name_he[:120],
            "kind": kind if kind in ("service", "dgx", "model", "council", "project")
            else "service",
            "state": state,
            "checked_at": n.get("checked_at") if isinstance(n.get("checked_at"), str)
            else None,
            "detail": scrub_text(n.get("detail"), state)[:220],
        })
    by_state = {}
    for n in nodes_out:
        by_state[n["state"]] = by_state.get(n["state"], 0) + 1
    return {
        "schema": "fed-public-v1",
        "generated_at": snapshot.get("generated_at"),
        "source": "eran-federation panel — sanitized 60s push "
                  "(עותק מסונן: שמות, מצבים וספירות בלבד)",
        "nodes": nodes_out,
        "summary": {"nodes_public": len(nodes_out), "nodes_hidden": hidden,
                    "by_state": by_state},
        "fleet": _pub_fleet(snapshot.get("fleet")),
        "fabric": _pub_fabric(snapshot.get("fabric")),
        "quorum": _pub_quorum(snapshot.get("quorum")),
        "ramchat": _pub_ramchat(snapshot.get("ramchat")),
        "alma_federation": _pub_alma(snapshot.get("alma_federation")),
    }


# literal substrings that must NEVER appear in the serialized wire payload
PUSH_CHECK_LITERALS = ("D:\\", "C:\\", "D:/", "C:/", "192.168.", "100.",
                       "127.0.0.1", "://", "\\")
PUSH_CHECK_WORDS_CI = ("token", "ts.net")


def payload_violations(wire_text, secrets=()):
    """Final unit-check before send. Returns hit labels (never the content)."""
    hits = [lit for lit in PUSH_CHECK_LITERALS if lit in wire_text]
    low = wire_text.lower()
    hits += [w for w in PUSH_CHECK_WORDS_CI if w in low]
    for sec in secrets:
        if sec and sec in wire_text:
            hits.append("<secret value>")
    return hits


# ----------------------------------------------------------------------------- pusher (60s loop)
PUSHER_STATE = {
    "enabled": True,
    "interval_s": PUSH_INTERVAL_S,
    "target": "federation.iddoperez.ai",
    "last_attempt_at": None,
    "last_ok_at": None,
    "last_http_status": None,
    "last_error": None,
    "pushes_ok": 0,
    "pushes_failed": 0,
}


def _read_push_token():
    try:
        with open(PUSH_TOKEN_PATH, encoding="utf-8") as fh:
            tok = fh.read().strip()
        return tok or None
    except OSError:
        return None


def push_once():
    """One sanitize→self-check→POST cycle. Token stays inside this frame."""
    PUSHER_STATE["last_attempt_at"] = now_iso()
    token = _read_push_token()
    if not token:
        PUSHER_STATE.update(last_error="push credential file missing/empty",
                            pushes_failed=PUSHER_STATE["pushes_failed"] + 1)
        log.warning("pusher: credential file missing/empty — push skipped")
        return False
    payload = build_public_payload(get_snapshot())
    wire_text = json.dumps(payload, ensure_ascii=False)
    hits = payload_violations(wire_text, secrets=(token,))
    if hits:
        PUSHER_STATE.update(last_error="payload failed self-check: %s" % ", ".join(hits),
                            pushes_failed=PUSHER_STATE["pushes_failed"] + 1)
        log.error("pusher: payload failed self-check (%s) — NOT pushed",
                  ", ".join(hits))
        return False
    body = wire_text.encode("utf-8")  # UTF-8 bytes via urllib — curl argv mangles Hebrew
    last_err = None
    for url in PUSH_URLS:
        req = urllib.request.Request(url, data=body, method="POST", headers={
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": "Bearer " + token,
            "User-Agent": PUSH_UA,
        })
        try:
            with urllib.request.urlopen(req, timeout=PUSH_TIMEOUT_S) as resp:
                resp.read()
                PUSHER_STATE.update(last_ok_at=now_iso(), last_http_status=resp.status,
                                    last_error=None,
                                    pushes_ok=PUSHER_STATE["pushes_ok"] + 1)
                log.info("pusher: pushed %d bytes, %d public nodes → HTTP %d (%s)",
                         len(body), len(payload.get("nodes") or []), resp.status,
                         url.split("/")[2])
                return True
        except urllib.error.HTTPError as exc:
            last_err = "HTTP %d from %s" % (exc.code, url.split("/")[2])
            PUSHER_STATE["last_http_status"] = exc.code
            log.warning("pusher: %s", last_err)
        except Exception as exc:
            last_err = "%s unreachable: %s" % (url.split("/")[2], type(exc).__name__)
            log.warning("pusher: %s: %s", last_err, exc)
    PUSHER_STATE.update(last_error=last_err,
                        pushes_failed=PUSHER_STATE["pushes_failed"] + 1)
    return False


def start_pusher():
    """60s daemon loop: sanitize the snapshot (whitelist copy, public nodes only)
    → self-check → POST to the federation Worker with Bearer FED_PUSH_TOKEN
    (read from .fed_push_token at runtime each cycle, never logged)."""
    def _loop():
        time.sleep(8)  # let the server bind + sources warm before the cold build
        while True:
            t0 = time.time()
            try:
                push_once()
            except Exception:
                log.exception("pusher loop crashed (loop survives)")
            time.sleep(max(5.0, PUSH_INTERVAL_S - (time.time() - t0)))
    th = threading.Thread(target=_loop, name="fed-pusher", daemon=True)
    th.start()
    log.info("pusher: 60s loop started → %s", PUSHER_STATE["target"])
    return th


# ----------------------------------------------------------------------------- main
def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8")],
    )
    try:
        with open(PID_PATH, "w", encoding="utf-8") as fh:
            fh.write(str(os.getpid()))
    except OSError:
        pass
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    srv.daemon_threads = True
    log.info("ERAN federation panel aggregator listening on http://%s:%d/ (pid %d)",
             HOST, PORT, os.getpid())
    start_pusher()
    try:
        srv.serve_forever(poll_interval=1.0)
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
        log.info("stopped")


if __name__ == "__main__":
    main()
