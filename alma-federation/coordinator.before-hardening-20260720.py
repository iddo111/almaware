"""
Alma Federation — Coordinator (the head node).  [HARDENED]
Holds a job queue; workers register, pull jobs, run them, post results back.
Pure stdlib — runs anywhere (DGX, a free VM, Colab). לע"נ עלמה ז"ל.

Hardening in this version:
  - hmac.compare_digest token check (constant-time); loud warning on default token
  - persistence: state saved to alma_state.json (survives restart)
  - node heartbeat + automatic prune of nodes not seen in ALMA_STALE seconds
  - transport: run behind Tailscale (encrypted) or bind to localhost; do NOT
    expose the raw HTTP port to the open internet.

Run:  ALMA_TOKEN=<secret> python coordinator.py     -> http://0.0.0.0:8900
Env:  ALMA_TOKEN  ALMA_PORT(8900)  ALMA_BIND(0.0.0.0)  ALMA_STALE(120)
"""
import json, os, time, threading, hmac, sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOKEN = os.environ.get("ALMA_TOKEN", "alma")
PORT = int(os.environ.get("ALMA_PORT", "8900"))
BIND = os.environ.get("ALMA_BIND", "0.0.0.0")
STALE = float(os.environ.get("ALMA_STALE", "120"))
STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alma_state.json")

_lock = threading.Lock()
_jobs, _pending, _nodes, _next = {}, [], {}, [1]


def _load():
    try:
        with open(STATE, encoding="utf-8") as f:
            d = json.load(f)
        _jobs.update(d.get("jobs", {})); _pending.extend(d.get("pending", []))
        _nodes.update(d.get("nodes", {})); _next[0] = d.get("next", 1)
        print(f"[coordinator] state restored: {len(_jobs)} jobs, {len(_nodes)} nodes")
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"[coordinator] state load skipped: {e}")


def _save():
    try:
        tmp = STATE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"jobs": _jobs, "pending": _pending, "nodes": _nodes, "next": _next[0]},
                      f, ensure_ascii=False)
        os.replace(tmp, STATE)
    except Exception as e:
        print(f"[coordinator] state save failed: {e}")


def _jid():
    j = f"job{_next[0]:05d}"; _next[0] += 1; return j


def _prune_loop():
    while True:
        time.sleep(30)
        now = time.time()
        with _lock:
            dead = [w for w, n in _nodes.items() if now - n.get("last_seen", 0) > STALE]
            for w in dead:
                _nodes[w]["online"] = False
        # keep record but mark offline (don't delete history)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _auth(self):
        got = self.headers.get("X-Alma-Token", "")
        return hmac.compare_digest(got, TOKEN)

    def _send(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        if not self._auth(): return self._send({"error": "auth"}, 401)
        path = self.path.split("?", 1)[0]
        q = dict(p.split("=", 1) for p in (self.path.split("?", 1)[1].split("&") if "?" in self.path else []) if "=" in p)
        if path == "/pull":
            wid = q.get("worker", "?")
            with _lock:
                if wid in _nodes: _nodes[wid].update(last_seen=time.time(), online=True)
                if _pending:
                    jid = _pending.pop(0)
                    _jobs[jid].update(status="running", worker=wid); _save()
                    return self._send({"job_id": jid, "cmd": _jobs[jid]["cmd"]})
            return self._send({})
        if path.startswith("/result/"):
            with _lock: j = _jobs.get(path.rsplit("/", 1)[1])
            return self._send(j or {"error": "no such job"}, 200 if j else 404)
        if path == "/nodes":
            with _lock: return self._send({"nodes": _nodes})
        if path == "/status":
            with _lock:
                online = [w for w, n in _nodes.items() if n.get("online")]
                return self._send({"pending": len(_pending), "jobs": len(_jobs),
                                   "nodes": len(_nodes), "online": online})
        return self._send({"error": "not found"}, 404)

    def do_POST(self):
        if not self._auth(): return self._send({"error": "auth"}, 401)
        try: b = self._body()
        except Exception as e: return self._send({"error": f"bad json: {e}"}, 400)
        if self.path == "/register":
            wid = b.get("worker", "?")
            with _lock:
                _nodes[wid] = {"meta": b.get("meta", {}), "last_seen": time.time(),
                               "online": True, "jobs_done": _nodes.get(wid, {}).get("jobs_done", 0)}
                _save()
            return self._send({"ok": True, "worker": wid})
        if self.path == "/submit":
            with _lock:
                jid = _jid()
                _jobs[jid] = {"cmd": b.get("cmd", ""), "status": "pending", "worker": None,
                              "output": None, "rc": None, "ts": time.time()}
                _pending.append(jid); _save()
            return self._send({"job_id": jid})
        if self.path == "/result":
            jid = b.get("job_id")
            with _lock:
                if jid in _jobs:
                    _jobs[jid].update(status="done", output=b.get("output"), rc=b.get("rc"))
                    w = _jobs[jid]["worker"]
                    if w in _nodes: _nodes[w]["jobs_done"] += 1
                    _save()
                    return self._send({"ok": True})
            return self._send({"error": "no such job"}, 404)
        return self._send({"error": "not found"}, 404)


if __name__ == "__main__":
    if TOKEN == "alma":
        print("⚠️  [coordinator] USING DEFAULT TOKEN 'alma' — set ALMA_TOKEN=<secret> before real use!")
    _load()
    threading.Thread(target=_prune_loop, daemon=True).start()
    print(f"[alma-federation] coordinator on http://{BIND}:{PORT}  (run behind Tailscale; don't expose to open internet)")
    ThreadingHTTPServer((BIND, PORT), H).serve_forever()
