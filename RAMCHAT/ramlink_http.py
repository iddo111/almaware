#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ramlink_http.py -- the smallest possible door into RAMCHAT from off-PC.

WHY THIS EXISTS
    ramlink.py talks to two named Windows shared-memory blocks. Named shared
    memory is a Windows-local object: the DGX boxes and the phone can never
    open it, no matter how good the network is. The eran1 spool mirror is
    one-way and lagged, so a fleet agent could read but never claim. That made
    "cross-agent" a word rather than a fact.

    This wraps ramlink.py in stdlib HTTP so any paired device can read the
    transcript, see the queue, and -- the part that actually matters -- CLAIM
    a task atomically, because the claim still happens inside ramlink.py on
    the PC. This process adds a door; it does not add a second source of truth.

SECURITY
    Bearer token, required on every endpoint except /health. The token lives in
    ramchat_http_token.txt next to this file (mode-restricted, gitignored) and
    is generated on first run. Binds 127.0.0.1 only; reachable from the fleet
    solely through `tailscale serve`, i.e. inside Iddo's single-user tailnet.
    Writes are attributed to the caller's own `who`, so RAMCHAT's authorship
    stays honest.

ENDPOINTS
    GET  /health                      -- no token; liveness only
    GET  /read?tail=N                 -- transcript tail
    GET  /queue?open=1&mine=<who>     -- the work queue
    POST /claim  {"task_id":..,"who":..}
    POST /done   {"task_id":..,"result":..,"who":..}
    POST /post   {"who":..,"text":..}

RUN
    python ramlink_http.py            (BELOW_NORMAL, 127.0.0.1:8876)
"""
import json
import os
import secrets
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
RAMLINK = os.path.join(HERE, "ramlink.py")
TOKEN_FILE = os.path.join(HERE, "ramchat_http_token.txt")
HOST, PORT = "127.0.0.1", 8876

# ramlink.py touches the shared-memory blocks; two concurrent writers racing
# through this door would be our own bug, not RAMCHAT's. One at a time.
_LOCK = threading.Lock()


def load_token():
    if os.path.exists(TOKEN_FILE):
        tok = open(TOKEN_FILE, "r", encoding="utf-8").read().strip()
        if tok:
            return tok
    tok = secrets.token_urlsafe(32)
    with open(TOKEN_FILE, "w", encoding="utf-8") as fh:
        fh.write(tok + "\n")
    try:
        os.chmod(TOKEN_FILE, 0o600)
    except OSError:
        pass
    return tok


TOKEN = load_token()


def ramlink(args, timeout=60):
    """Run ramlink.py. Hebrew is everywhere in these files: utf-8 or it crashes."""
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    with _LOCK:
        p = subprocess.run(
            [sys.executable, RAMLINK] + args,
            capture_output=True, cwd=HERE, env=env, timeout=timeout,
        )
    return {
        "rc": p.returncode,
        "stdout": p.stdout.decode("utf-8", "replace"),
        "stderr": p.stderr.decode("utf-8", "replace"),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "ramlink-http/1.0"

    def log_message(self, fmt, *a):
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % a))

    def _send(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authed(self):
        got = self.headers.get("Authorization", "")
        if got.startswith("Bearer "):
            got = got[7:]
        if secrets.compare_digest(got.strip(), TOKEN):
            return True
        self._send(401, {"error": "bad or missing bearer token"})
        return False

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path == "/health":
            return self._send(200, {"ok": True, "service": "ramlink_http", "port": PORT})
        if not self._authed():
            return
        if u.path == "/read":
            tail = q.get("tail", ["20"])[0]
            return self._send(200, ramlink(["read", "--tail", str(int(tail))]))
        if u.path == "/queue":
            args = ["queue"]
            if q.get("open"):
                args.append("--open")
            if q.get("mine"):
                args += ["--mine", q["mine"][0]]
            return self._send(200, ramlink(args))
        if u.path == "/status":
            return self._send(200, ramlink(["status"]))
        self._send(404, {"error": "no such endpoint", "path": u.path})

    def do_POST(self):
        u = urlparse(self.path)
        if not self._authed():
            return
        b = self._body()
        if b is None:
            return self._send(400, {"error": "body must be JSON"})
        try:
            if u.path == "/claim":
                return self._send(200, ramlink(["claim", b["task_id"], b["who"]]))
            if u.path == "/done":
                args = ["done", b["task_id"]]
                if b.get("result"):
                    args.append(b["result"])
                if b.get("who"):
                    args += ["--who", b["who"]]
                return self._send(200, ramlink(args))
            if u.path == "/post":
                return self._send(200, ramlink(["post", b["who"], b["text"]]))
        except KeyError as e:
            return self._send(400, {"error": "missing field %s" % e})
        self._send(404, {"error": "no such endpoint", "path": u.path})


def below_normal():
    """KESHEV must never be starved by this. 2026-09-03 scar."""
    try:
        import ctypes
        # BELOW_NORMAL_PRIORITY_CLASS
        ctypes.windll.kernel32.SetPriorityClass(
            ctypes.windll.kernel32.GetCurrentProcess(), 0x00004000)
    except Exception:
        pass


if __name__ == "__main__":
    below_normal()
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    sys.stderr.write("ramlink_http listening on http://%s:%d  (token in %s)\n"
                     % (HOST, PORT, os.path.basename(TOKEN_FILE)))
    srv.serve_forever()
