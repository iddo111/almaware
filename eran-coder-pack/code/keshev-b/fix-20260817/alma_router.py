#!/usr/bin/env python3
"""ALMA fleet router v3 - ONE OpenAI endpoint in front of a fleet that serves MORE THAN ONE model.

Why v2: fleet_router.py assumed every box served the same model. It no longer does.
This one asks each backend what it is serving (/v1/models, refreshed every 20 s) and routes
each request to a box that actually has the requested model, choosing the least busy one.
An unknown model name falls back to the whole fleet, so old clients keep working.

Why v3 (2026-08-17, claude-cli-FIXER): routing logic UNCHANGED. Three broken windows closed,
all of them things every client was otherwise required to remember on its own:

  1. GLM NEVER TERMINATES without chat_template_kwargs {"enable_thinking": false}.
     Measured at temp 0: 9000 completion tokens, no usable answer, reproducible.
     That is not a preference, it is a hang. The router now injects the flag for
     glm-4.7-flash unless the caller set chat_template_kwargs itself.
  2. THE EMPTY-STRING TRAP. nemotron-3-super and gpt-oss-120b think before they answer.
     With a small max_tokens the whole budget goes into reasoning and content comes back
     '' - which reads as a dead server and is how the 1-bit GLM fooled us. The router
     raises a too-small max_tokens to 900 for those two backends.
  3. STREAMING WAS BUFFERED. v2 read the entire upstream body, then sent it with
     Content-Type: application/json and a Content-Length. stream=true clients got the
     whole SSE payload in one lump at the end, mislabelled. Now it is a real chunked
     passthrough with the upstream's own Content-Type.

NOTHING IS SILENT. Every rewrite sets X-Alma-Fixed on the response, is counted in /fleet,
and prints a line to the log. A caller can always see that the router touched its request.

  GET  /health          -> 200 when at least one backend is alive
  GET  /v1/models       -> the union of what the fleet serves
  GET  /fleet           -> who is up, what they serve, how many requests each took,
                           and how many requests the router had to repair
  POST /v1/*            -> proxied (streaming and non-streaming)

Pure stdlib. Managed by systemd: alma-router.service (Restart=always, survives reboot).
Manual start, if ever needed:
  setsid nohup python3 alma_router.py >/tmp/alma_router.log 2>&1 </dev/null &
"""
import json, sys, threading, time, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BACKENDS = [
    "http://<fabric-ip>:8000",   # eran1  (<lan-ip> on LAN)
    "http://<fabric-ip>:8000",   # eran2  (<lan-ip>  on LAN)
    "http://<fabric-ip>:8000",   # eran3  (no LAN of its own; reached through eran2)
    "http://<lan-ip>:8000", # eran4  (plain LAN, not on the fabric; serves gpt-oss-120b)
]
PORT = 8010
COOLDOWN = 30.0
PROBE_EVERY = 20.0

# --- the three repairs, by model name (see docstring) -------------------------------
NO_THINK_MODELS = {"glm-4.7-flash"}                    # hangs forever with thinking on
THINKY_MODELS = {"nemotron-3-super", "gpt-oss-120b"}   # spend a small budget on reasoning alone
MIN_TOKENS_THINKY = 900

inflight = {b: 0 for b in BACKENDS}
dead_until = {b: 0.0 for b in BACKENDS}
served = {b: 0 for b in BACKENDS}
models = {b: [] for b in BACKENDS}          # backend -> [model id, ...]
repaired = {"glm-nothink": 0, "max-tokens": 0}
lock = threading.Lock()


def probe():
    while True:
        for b in BACKENDS:
            try:
                with urllib.request.urlopen(b + "/v1/models", timeout=5) as r:
                    ids = [m["id"] for m in json.loads(r.read().decode())["data"]]
                with lock:
                    models[b] = ids
                    dead_until[b] = 0.0
            except Exception:
                with lock:
                    models[b] = []
        time.sleep(PROBE_EVERY)


def pick(model):
    now = time.time()
    with lock:
        live = [b for b in BACKENDS if dead_until[b] <= now]
        if model:
            match = [b for b in live if model in models[b]]
            if match:
                live = match
        if not live:
            live = list(BACKENDS)
        b = min(live, key=lambda x: (inflight[x], served[x]))
        inflight[b] += 1
        served[b] += 1
        return b


def release(b, ok):
    with lock:
        inflight[b] = max(0, inflight[b] - 1)
        if not ok:
            dead_until[b] = time.time() + COOLDOWN


def repair(body, path):
    """Return (new_raw_or_None, [names of repairs applied]). Never changes routing."""
    if "completions" not in path:
        return None, []
    model = body.get("model")
    fixes = []

    if model in NO_THINK_MODELS and "chat_template_kwargs" not in body:
        body["chat_template_kwargs"] = {"enable_thinking": False}
        fixes.append("glm-nothink")

    if model in THINKY_MODELS:
        for key in ("max_tokens", "max_completion_tokens"):
            v = body.get(key)
            if isinstance(v, int) and not isinstance(v, bool) and 0 < v < MIN_TOKENS_THINKY:
                body[key] = MIN_TOKENS_THINKY
                fixes.append("max-tokens")
                break

    if not fixes:
        return None, []
    with lock:
        for f in fixes:
            repaired[f] = repaired.get(f, 0) + 1
    print("repair %s for %s (%s)" % (",".join(fixes), model, path), flush=True)
    return json.dumps(body).encode("utf-8"), fixes


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def do_GET(self):
        if self.path.rstrip("/") == "/health":
            with lock:
                alive = any(models[b] for b in BACKENDS)
            return self._send(200 if alive else 503,
                              json.dumps({"ok": alive}).encode())
        if self.path.rstrip("/") == "/fleet":
            with lock:
                snap = {b: {"models": models[b], "inflight": inflight[b], "served": served[b]}
                        for b in BACKENDS}
                snap["repaired"] = dict(repaired)
            return self._send(200, json.dumps(snap, indent=1).encode())
        if self.path.endswith("/v1/models") or self.path.endswith("/models"):
            with lock:
                ids = sorted({m for b in BACKENDS for m in models[b]})
            return self._send(200, json.dumps(
                {"object": "list",
                 "data": [{"id": i, "object": "model", "owned_by": "alma-fleet"} for i in ids]}
            ).encode())
        return self._send(404, b'{"error":"not found"}')

    def _stream(self, r, b, fixes):
        """Chunked passthrough. v2 buffered the whole SSE body and mislabelled it JSON."""
        self.send_response(r.status)
        self.send_header("Content-Type", r.headers.get("Content-Type", "text/event-stream"))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Alma-Backend", b)
        if fixes:
            self.send_header("X-Alma-Fixed", ",".join(fixes))
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        read = r.read1 if hasattr(r, "read1") else r.read
        while True:
            chunk = read(8192)
            if not chunk:
                break
            self.wfile.write(b"%x\r\n" % len(chunk) + chunk + b"\r\n")
            self.wfile.flush()
        self.wfile.write(b"0\r\n\r\n")
        self.wfile.flush()

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n)
        model = None
        stream = False
        fixes = []
        try:
            body = json.loads(raw.decode("utf-8"))
            model = body.get("model")
            stream = body.get("stream") is True
            fixed_raw, fixes = repair(body, self.path)
            if fixed_raw is not None:
                raw = fixed_raw
        except Exception:
            pass
        b = pick(model)
        ok = False
        try:
            req = urllib.request.Request(b + self.path, data=raw,
                                         headers={"Content-Type": "application/json"})
            r = urllib.request.urlopen(req, timeout=3600)
            try:
                if stream:
                    ok = True
                    return self._stream(r, b, fixes)
                body_out = r.read()
                code = r.status
                ok = True
            finally:
                r.close()
        except urllib.error.HTTPError as e:
            body_out, code, ok = e.read(), e.code, True   # a 4xx is the backend answering
        except Exception as e:
            body_out = json.dumps({"error": {"message": "backend %s: %r" % (b, e)}}).encode()
            code = 502
        finally:
            release(b, ok)
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body_out)))
        self.send_header("X-Alma-Backend", b)
        if fixes:
            self.send_header("X-Alma-Fixed", ",".join(fixes))
        self.end_headers()
        try:
            self.wfile.write(body_out)
        except Exception:
            pass


class S(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 256          # the stdlib default of 5 drops clients above ~40 concurrent
    allow_reuse_address = True


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    threading.Thread(target=probe, daemon=True).start()
    time.sleep(2)
    print("alma_router v3 on :%d -> %s" % (port, BACKENDS), flush=True)
    S(("0.0.0.0", port), H).serve_forever()
