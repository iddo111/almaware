#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ALMA MASTER - one page over the whole fleet. / לוח בקרה ראשי.

100% ours: stdlib http.server, hand-written CSS and JS, zero dependencies,
zero CDN. Nothing here is a framework.

What it shows, and where each number actually comes from:

  FLEET + FABRIC   almaware-cockpit/status.json, written by the HUD collector
  WORKERS          per-node service probes over SSH (real, or honestly UNKNOWN)
  COUNCIL          RAMCHAT_COUNCIL_V1 / RAMCHAT_QUEUE_V1 shared memory
  QUORUM           HTTP probe of 127.0.0.1:8099

RULE: every tile shows live data or an honest BROKEN / UNKNOWN. Never a
placeholder, never a demo number. A dashboard that lies is worse than none.

    python server.py            ->  http://127.0.0.1:8795/
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, "static")
PORT = int(os.environ.get("ALMA_MASTER_PORT", "8795"))

COCKPIT_STATUS = r"D:\CLAUDE\almaware-cockpit\status.json"
RAMCHAT_DIR = r"D:\CLAUDE\RAMCHAT"
sys.path.insert(0, RAMCHAT_DIR)

QUORUM_URL = "http://127.0.0.1:8099/"
RECALL_URL = "http://127.0.0.1:8794/api/stats"
COCKPIT_URL = "http://127.0.0.1:8790/"

# Worker tiles. GLM/Colibri is NEW - it was only ever a line in a staged plan
# (antvoice-190m/E3_CUTOVER_PLAN.md, "NO CUTOVER HAS OCCURRED"), never code.
WORKERS = [
    {"node": "eran1", "name": "Grok-1 head", "probe": "port", "arg": 8080,
     "note": "llama-server"},
    {"node": "eran2", "name": "Grok-1 RPC worker", "probe": "port", "arg": 50052,
     "note": "rpc"},
    {"node": "eran3", "name": "Grok-1 RPC worker", "probe": "port", "arg": 50052,
     "note": "rpc"},
    {"node": "eran4", "name": "Eran voice", "probe": "proc", "arg": "train",
     "note": "training"},
    {"node": "eran4", "name": "GLM / Colibri", "probe": "ollama", "arg": "glm",
     "note": "inference"},
    {"node": "eran2", "name": "Ollama", "probe": "ollama", "arg": "",
     "note": "models"},
]

TTL = 20.0
_cache: dict = {}
_lock = threading.Lock()


def cached(key, fn, ttl=TTL):
    with _lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < ttl:
            return hit[1]
    try:
        val = fn()
    except Exception as e:
        val = {"state": "BROKEN", "error": str(e)[:120]}
    with _lock:
        _cache[key] = (time.time(), val)
    return val


def ssh(host, cmd, timeout=12):
    try:
        p = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=6",
             "-o", "StrictHostKeyChecking=accept-new", host, cmd],
            capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()
    except Exception as e:
        return 1, "", str(e)[:120]


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------

def gather_cockpit():
    """Fleet + fabric. The collector already does the hard part - reuse it."""
    try:
        st = os.stat(COCKPIT_STATUS)
    except OSError:
        return {"state": "BROKEN", "error": "status.json missing - collector not running"}
    age = time.time() - st.st_mtime
    with open(COCKPIT_STATUS, encoding="utf-8") as f:
        d = json.load(f)
    nodes = []
    for k in ("eran1", "eran2", "eran3", "eran4"):
        v = d.get("fleet", {}).get(k, {}) or {}
        g = v.get("gpu")
        if isinstance(g, list):
            g = g[0] if g else {}
        g = g or {}
        nodes.append({
            "id": k,
            "hostname": v.get("hostname"),
            "reachable": bool(v.get("reachable")),
            "gpu_temp": g.get("temp_c"),
            "gpu_util": g.get("util_pct"),
            "uptime_s": v.get("uptime_s"),
            "error": v.get("error"),
        })
    links = []
    for name, v in (d.get("fabric", {}).get("links") or {}).items():
        links.append({"name": name, "state": v.get("state"),
                      "gbps": v.get("speed_gbps"), "carrier": v.get("carrier"),
                      "ping": v.get("peer_ping")})
    return {
        "state": "STALE" if age > 60 else "LIVE",
        "age_s": round(age, 1),
        "nodes": nodes,
        "links": links,
    }


def gather_workers():
    out = []
    for w in WORKERS:
        key = "w:%s:%s:%s" % (w["node"], w["name"], w["arg"])

        def probe(w=w):
            if w["probe"] == "port":
                rc, so, _ = ssh(w["node"],
                                "ss -ltn 2>/dev/null | grep -c ':%d ' || true" % w["arg"])
                if rc != 0:
                    return {"state": "UNKNOWN", "detail": "node unreachable"}
                n = int(so.split()[0]) if so.split() and so.split()[0].isdigit() else 0
                return {"state": "UP" if n else "DOWN",
                        "detail": "port %d %s" % (w["arg"], "listening" if n else "closed")}
            if w["probe"] == "proc":
                rc, so, _ = ssh(w["node"],
                                "pgrep -fc '%s' 2>/dev/null || echo 0" % w["arg"])
                if rc != 0:
                    return {"state": "UNKNOWN", "detail": "node unreachable"}
                n = int(so.split()[0]) if so.split() and so.split()[0].isdigit() else 0
                return {"state": "UP" if n else "DOWN",
                        "detail": "%d process(es) matching '%s'" % (n, w["arg"])}
            if w["probe"] == "ollama":
                rc, so, _ = ssh(w["node"],
                                "curl -s --max-time 5 http://127.0.0.1:11434/api/tags "
                                "|| true")
                if rc != 0 or not so:
                    return {"state": "DOWN", "detail": "ollama not answering"}
                try:
                    tags = json.loads(so).get("models", [])
                except Exception:
                    return {"state": "DOWN", "detail": "bad response"}
                names = [m.get("name", "") for m in tags]
                if w["arg"]:
                    hit = [n for n in names if w["arg"].lower() in n.lower()]
                    if not hit:
                        return {"state": "NOT BUILT",
                                "detail": "no model matching '%s' (%d present)"
                                          % (w["arg"], len(names))}
                    return {"state": "UP", "detail": ", ".join(hit[:2])}
                return {"state": "UP", "detail": "%d models" % len(names)}
            return {"state": "UNKNOWN", "detail": "no probe"}

        r = cached(key, probe)
        out.append(dict(w, **r))
    return out


def gather_council():
    try:
        import ramlink
    except Exception as e:
        return {"state": "BROKEN", "error": "ramlink not importable: %s" % str(e)[:80]}
    msgs, shared, msrc = ramlink.get_transcript()
    items, qsrc = ramlink.get_queue()
    blk = ramlink.read_block(ramlink.COUNCIL_NAME, ramlink.COUNCIL_SIZE,
                             ramlink.COUNCIL_MAGIC)
    open_tasks = [t for t in items
                  if not t.get("claimed_by") and t.get("status") not in ("done", "completed")]
    held = [t for t in items if t.get("claimed_by") and t.get("status") == "in_progress"]
    return {
        "state": "LIVE" if blk else "DISK ONLY",
        "ram_held": bool(blk),
        "source": msrc,
        "mission": (shared or {}).get("mission"),
        "messages": [{"who": m.get("who"), "at": m.get("at"),
                      "text": (m.get("text") or "")[:220]} for m in msgs[-12:]],
        "n_messages": len(msgs),
        "open": [{"id": t.get("id"), "prompt": (t.get("prompt") or "")[:110]}
                 for t in open_tasks[-8:]],
        "held": [{"id": t.get("id"), "who": t.get("claimed_by"),
                  "prompt": (t.get("prompt") or "")[:110]} for t in held[-8:]],
        "n_open": len(open_tasks),
        "n_held": len(held),
    }


def http_probe(url, timeout=4):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return {"state": "UP", "code": r.status}
    except urllib.error.HTTPError as e:
        return {"state": "UP", "code": e.code}
    except Exception as e:
        return {"state": "DOWN", "error": str(e)[:80]}


def gather_services():
    return {
        "quorum": cached("svc:quorum", lambda: http_probe(QUORUM_URL)),
        "cockpit": cached("svc:cockpit", lambda: http_probe(COCKPIT_URL)),
        "recall": cached("svc:recall", lambda: recall_stats()),
    }


def recall_stats():
    # 4 s was too tight - /api/stats runs aggregate queries over a 181 MB
    # SQLite db and can take several seconds on a cold cache, which showed a
    # healthy service as DOWN.
    try:
        with urllib.request.urlopen(RECALL_URL, timeout=12) as r:
            d = json.loads(r.read())
        return {"state": "UP", "sessions": d.get("total_sessions"),
                "msgs": d.get("total_msgs")}
    except Exception as e:
        return {"state": "DOWN", "error": str(e)[:80]}


def build_status():
    return {
        "generated_at": time.time(),
        "cockpit": cached("cockpit", gather_cockpit, ttl=4),
        "workers": gather_workers(),
        "council": cached("council", gather_council, ttl=4),
        "services": gather_services(),
    }


# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "AlmaMaster/1.0"

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?")[0]
        try:
            if path == "/api/status":
                return self._send(200, json.dumps(build_status(), ensure_ascii=False),
                                  "application/json; charset=utf-8")
            fn = "index.html" if path == "/" else path.lstrip("/")
            fp = os.path.join(STATIC, fn)
            if not os.path.abspath(fp).startswith(os.path.abspath(STATIC)):
                return self._send(403, "no", "text/plain")
            if not os.path.isfile(fp):
                return self._send(404, "not found", "text/plain")
            ctype = ("text/html; charset=utf-8" if fn.endswith(".html")
                     else "text/css; charset=utf-8" if fn.endswith(".css")
                     else "application/javascript; charset=utf-8" if fn.endswith(".js")
                     else "application/octet-stream")
            with open(fp, "rb") as f:
                return self._send(200, f.read(), ctype)
        except Exception as e:
            return self._send(500, json.dumps({"error": str(e)}),
                              "application/json; charset=utf-8")


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print("ALMA MASTER on http://127.0.0.1:%d/" % PORT)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
