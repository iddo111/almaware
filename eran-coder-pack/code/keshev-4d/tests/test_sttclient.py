"""KING'S CANONICAL TESTS - sttclient. Workers may not edit this file.

The law: one attempt, deadline, late replies discarded loudly, dead servers
return a parkable reason and never an exception; token read per call.
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.sttclient import DecodeResult, SttClient  # noqa: E402


class _FakeStt(BaseHTTPRequestHandler):
    reply: dict = {}
    echo_id: bool = True

    def do_POST(self):  # noqa: N802
        n = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(n)
        body = dict(self.reply)
        if self.echo_id:
            body.setdefault("request_id", self.headers.get("X-Request-Id"))
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # noqa: N802 - /health
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *a):
        pass


class SttClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), _FakeStt)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.td = tempfile.TemporaryDirectory()
        cls.tok = pathlib.Path(cls.td.name) / "stt-token"
        cls.tok.write_text("test-token\n", encoding="utf-8")
        cls.client = SttClient(f"http://127.0.0.1:{cls.port}", cls.tok,
                               timeout_s=3)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.td.cleanup()

    def test_good_decode_round_trips(self):
        _FakeStt.reply = {"ok": True, "text": "shalom", "lang": "he",
                          "avg_logprob": -0.2, "decode_ms": 300}
        _FakeStt.echo_id = True
        r = self.client.decode("rec-1", b"RIFF")
        self.assertTrue(r.ok)
        self.assertEqual(r.text, "shalom")
        self.assertEqual(r.lang, "he")

    def test_late_reply_discarded_loudly(self):
        _FakeStt.reply = {"ok": True, "text": "ghost", "request_id": "OTHER"}
        _FakeStt.echo_id = False
        r = self.client.decode("rec-2", b"RIFF")
        self.assertFalse(r.ok)
        self.assertEqual(r.reason, "late_reply")

    def test_dead_server_parkable_never_raises(self):
        dead = SttClient("http://127.0.0.1:1", self.tok, timeout_s=1)
        r = dead.decode("rec-3", b"RIFF")
        self.assertFalse(r.ok)
        self.assertIn(r.reason, ("http", "timeout"))

    def test_health_true_on_200(self):
        self.assertTrue(self.client.health())

    def test_token_read_per_call(self):
        _FakeStt.reply = {"ok": True, "text": "x"}
        _FakeStt.echo_id = True
        self.tok.write_text("rotated\n", encoding="utf-8")
        r = self.client.decode("rec-4", b"RIFF")
        self.assertTrue(r.ok, "a rotated token must not require a restart")
        self.tok.write_text("test-token\n", encoding="utf-8")

    def test_result_defaults(self):
        r = DecodeResult(ok=False, reason="timeout")
        self.assertEqual((r.text, r.lang, r.ms), ("", None, 0))


if __name__ == "__main__":
    unittest.main()
