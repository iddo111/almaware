"""KESHEV -- the boot deaf-window regression test.

Scar, 2026-08-23 05:29-05:36: after a reboot the STT server binds :8737 and logs
LISTENING *before* the models are loaded, then answers every /v1/transcribe with
503 {"state":"LOADING"} until MODELS_LOADED (measured 22s .. 423s, worst case on a
cold boot).  decoder.py caught that 503 inside a bare `except requests.RequestException`
via raise_for_status(), returned (False, "", "he", 0.0), and main.py logged it as
`decode=fail`.  For seven minutes every word Iddo said was thrown away silently.

These two tests are the fence:
  1. wait_until_ready() must BLOCK while the server says LOADING and return True
     the moment it says READY -- so the mic never opens its stream into a deaf server.
  2. transcribe_hebrew_pcm() must RIDE OUT a short 503 (a mid-session restart)
     instead of dropping the sentence on the first refusal.

Run:  python tests\test_decoder_readiness.py
"""
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))

# state shared with the fake server
READY_AT = {"t": 0.0}          # monotonic time the fake server flips to READY
HITS = {"health": 0, "transcribe": 0}


class FakeStt(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _ready(self):
        return time.monotonic() >= READY_AT["t"]

    def _json(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path != "/health":
            self._json(404, {"error": "not_found"})
            return
        HITS["health"] += 1
        if self._ready():
            self._json(200, {"state": "READY"})
        else:
            self._json(503, {"state": "LOADING"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(n)
        HITS["transcribe"] += 1
        if not self._ready():
            self._json(503, {"state": "LOADING"})
            return
        self._json(200, {"text": "shalom", "lang": "he", "avg_logprob": -0.2})


def main():
    srv = HTTPServer(("127.0.0.1", 0), FakeStt)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    os.environ["KESHEV_STT_URL"] = f"http://127.0.0.1:{port}/v1/transcribe"
    os.environ["KESHEV_STT_TOKEN"] = "test-token"

    import decoder

    failures = []

    # --- 1. wait_until_ready blocks through LOADING, returns True at READY -------
    READY_AT["t"] = time.monotonic() + 1.5
    HITS["health"] = 0
    seen = []
    t0 = time.monotonic()
    ok = decoder.wait_until_ready(poll_s=0.2, on_wait=lambda st, w: seen.append(st))
    waited = time.monotonic() - t0
    try:
        assert ok is True, f"wait_until_ready returned {ok!r}, expected True"
        assert waited >= 1.4, f"returned after {waited:.2f}s -- it did not wait for READY"
        assert waited < 6.0, f"returned after {waited:.2f}s -- far too slow to notice READY"
        assert "LOADING" in seen, f"never reported LOADING to the caller: {seen}"
        assert HITS["health"] >= 2, f"only polled /health {HITS['health']} time(s)"
        print(f"PASS  wait_until_ready blocked {waited:.2f}s through LOADING, saw {seen}")
    except AssertionError as e:
        failures.append(f"wait_until_ready: {e}")
        print(f"FAIL  wait_until_ready: {e}")

    # --- 2. a mid-session 503 must not throw the sentence away -------------------
    READY_AT["t"] = time.monotonic() + 1.5
    HITS["transcribe"] = 0
    t0 = time.monotonic()
    ok, text, lang, lp = decoder.transcribe_hebrew_pcm(b"\x00\x01" * 8000)
    waited = time.monotonic() - t0
    try:
        assert ok is True, "dropped the segment on a 503 LOADING instead of retrying"
        assert text == "shalom", f"got text={text!r}"
        assert HITS["transcribe"] >= 2, f"only posted {HITS['transcribe']} time(s) -- no retry"
        print(f"PASS  transcribe rode out 503 LOADING in {waited:.2f}s "
              f"({HITS['transcribe']} posts), text={text!r}")
    except AssertionError as e:
        failures.append(f"transcribe/503: {e}")
        print(f"FAIL  transcribe/503: {e}")

    # --- 3. a genuinely dead server still fails, and fails fast ------------------
    os.environ["KESHEV_STT_URL"] = "http://127.0.0.1:1/v1/transcribe"
    decoder._token_cache = None
    t0 = time.monotonic()
    ok, text, lang, lp = decoder.transcribe_hebrew_pcm(b"\x00\x01" * 8000)
    waited = time.monotonic() - t0
    try:
        assert ok is False, "claimed success against a dead server"
        assert waited < 20.0, f"took {waited:.1f}s to give up on a dead server"
        print(f"PASS  dead server -> failure in {waited:.2f}s")
    except AssertionError as e:
        failures.append(f"dead server: {e}")
        print(f"FAIL  dead server: {e}")

    srv.shutdown()
    if failures:
        print(f"\nDECODER READINESS: {len(failures)} FAILURE(S)")
        sys.exit(1)
    print("\nDECODER READINESS OK")


if __name__ == "__main__":
    main()
