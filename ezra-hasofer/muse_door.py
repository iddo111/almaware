#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MUSE DOOR -- remote access to Muse Code CLI, tailnet only.

Iddo, 2026-09-12 (away from the PC): wanted tailnet access to Muse Code.
Windows doesn't support Tailscale SSH, and opening a real SSH/shell server on
the main PC unattended is a bigger security step than this actually calls
for. This is the scoped alternative, same pattern as brain2 (:8897) and
RAMCHAT (:8876): a tiny tailnet-only HTTP door that runs ONE `muse exec`
prompt at a time and returns its output. Not a shell -- just this one tool.

Auth: token in state/token.txt (header X-Muse-Token or ?key=), gitignored.
Expose with: tailscale serve --bg --https=8900 http://127.0.0.1:8900
"""
import http.server
import json
import os
import secrets
import subprocess
import urllib.parse

HOST, PORT = "127.0.0.1", 8900
APP_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.join(APP_DIR, "state")
TOKEN_PATH = os.path.join(STATE_DIR, "muse_door_token.txt")
LOG_PATH = os.path.join(APP_DIR, "muse_door.log")


def get_token():
    os.makedirs(STATE_DIR, exist_ok=True)
    if not os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH, "w", encoding="utf-8") as f:
            f.write(secrets.token_urlsafe(24))
    return open(TOKEN_PATH, encoding="utf-8").read().strip()


TOKEN = get_token()


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (self.address_string(), fmt % args))

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authed(self):
        qs = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(qs)
        given = self.headers.get("X-Muse-Token") or (params.get("key") or [""])[0]
        return secrets.compare_digest(given or "", TOKEN)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/":
            return self._json(200, {"status": "ok", "door": "muse", "usage":
                                    "POST /exec {\"prompt\": \"...\"} with X-Muse-Token header"})
        return self._json(404, {"error": "not found"})

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path != "/exec":
            return self._json(404, {"error": "not found"})
        if not self._authed():
            return self._json(401, {"error": "X-Muse-Token required"})
        length = int(self.headers.get("Content-Length", 0))
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return self._json(400, {"error": "bad json"})
        prompt = (data.get("prompt") or "").strip()
        if not prompt:
            return self._json(400, {"error": "prompt is required"})
        # single prompt, no chaining -- the shell metacharacter risk is why
        # this takes a JSON body (never string-interpolated into a shell
        # command) and passes the prompt as one argv element to muse exec.
        try:
            out = subprocess.run(
                ["wsl.exe", "-e", "bash", "-lc",
                 # cd ~ first: launched from a scheduled task, wsl inherited
                 # C:\Windows\System32 as its cwd, so a --yolo Muse had System32 as its
                 # workspace root (seen in its own stderr, 2026-09-15 05:49).
                 'cd ~ && exec ~/.local/bin/muse exec --yolo "$1"', "--", prompt],
                capture_output=True, text=True, timeout=600,
                # Muse answers in Hebrew; without an explicit codec Windows decodes the
                # pipe as cp1252 and the handler dies with a 500 (2026-09-15 05:41).
                encoding="utf-8", errors="replace",
                # pythonw parent: without this wsl.exe opens a visible terminal window
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return self._json(200, {"stdout": out.stdout[-20000:],
                                    "stderr": out.stderr[-4000:],
                                    "returncode": out.returncode})
        except subprocess.TimeoutExpired:
            return self._json(504, {"error": "muse exec timed out after 600s"})
        except Exception as e:
            return self._json(500, {"error": "%s: %s" % (type(e).__name__, e)})


if __name__ == "__main__":
    print("muse door token: see", TOKEN_PATH)
    print("listening on http://%s:%d" % (HOST, PORT))
    http.server.ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
