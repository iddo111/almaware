"""STT client: 'auto' unrepresentable, request-id law, script-retry law —
proven against a REAL in-process HTTP server, not a mock of our own code."""
from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from k2 import sttclient


class RequestIds(unittest.TestCase):

    def test_format(self):
        self.assertEqual(sttclient.make_request_id("abcd1234", 7),
                         "abcd1234-000007")

    def test_widens_past_six_digits(self):
        rid = sttclient.make_request_id("abcd1234", 1_000_000)
        self.assertEqual(rid, "abcd1234-1000000")
        self.assertTrue(sttclient.valid_request_id(rid))

    def test_bad_session_refused(self):
        for bad in ("ABCD1234", "abc", "", "abcd12345"):
            with self.assertRaises(ValueError):
                sttclient.make_request_id(bad, 0)

    def test_valid_request_id(self):
        self.assertTrue(sttclient.valid_request_id("abcd1234-000001"))
        self.assertFalse(sttclient.valid_request_id("abcd1234-1"))
        self.assertFalse(sttclient.valid_request_id(None))


class ScriptLaw(unittest.TestCase):

    def test_ratio_counts_letters_only(self):
        he, la = sttclient.script_ratio("שלום world 123 !!!")
        self.assertEqual((he, la), (4, 5))

    def test_hebrew_hint_latin_result_retries_to_en(self):
        self.assertEqual(
            sttclient.wrong_script_hint("hello there friend", "he"), "en")

    def test_en_hint_hebrew_result_retries_to_he(self):
        self.assertEqual(
            sttclient.wrong_script_hint("שלום לך חבר יקר", "en"), "he")

    def test_majority_right_script_no_retry(self):
        self.assertIsNone(sttclient.wrong_script_hint("שלום okay", "he"))

    def test_exact_half_does_not_retry(self):
        """>50%, not >=: an even split is not evidence of a wrong hint."""
        self.assertIsNone(sttclient.wrong_script_hint("של ok", "he"))

    def test_letterless_text_never_retries(self):
        self.assertIsNone(sttclient.wrong_script_hint("123 ... !", "he"))

    def test_auto_hint_raises(self):
        with self.assertRaises(ValueError):
            sttclient.wrong_script_hint("text", "auto")


class AutoUnrepresentable(unittest.TestCase):

    def test_constructor_refuses_auto_default(self):
        with self.assertRaises(ValueError) as ctx:
            sttclient.SttClient("http://127.0.0.1:8737", "tok",
                                default_hint="auto")
        self.assertIn("unrepresentable", str(ctx.exception))

    def test_transcribe_refuses_auto_hint(self):
        c = sttclient.SttClient("http://127.0.0.1:8737", "tok")
        with self.assertRaises(ValueError):
            c.transcribe(b"\x00\x00", request_id="abcd1234-000001",
                         duration_ms=10, lang_hint="auto")

    def test_url_must_carry_port(self):
        with self.assertRaises(ValueError):
            sttclient.SttClient("http://host/", "tok")


# ----------------------------------------------------- real-server tests


class _FakeStt(BaseHTTPRequestHandler):
    """A REAL HTTP server speaking the eran1 contract. Scripted per test
    via class attrs. Responds to the hint it was SENT — so the retry law
    is proven over an actual socket, headers and all."""

    # scenario: hint -> text to return (+ optional per-hint logprob)
    responses: dict = {}
    logprobs: dict = {}
    requests_seen: list = []
    health: dict = {}

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        self.rfile.read(n)
        rid = self.headers.get("X-Request-Id", "")
        hint = self.headers.get("X-Lang-Hint", "")
        type(self).requests_seen.append((rid, hint))
        text = type(self).responses.get(hint, "")
        lp = type(self).logprobs.get(hint, -0.2)
        body = json.dumps({
            "request_id": rid, "text": text, "lang": hint,
            "lang_prob": 0.9, "avg_logprob": lp, "no_speech_prob": 0.01,
            "decode_ms": 42, "model": "fake-ct2",
        }).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        body = json.dumps(type(self).health).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):                       # quiet
        pass


class RealServer(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), _FakeStt)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever,
                                      daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        _FakeStt.requests_seen = []
        _FakeStt.logprobs = {}
        self.events = []
        self.client = sttclient.SttClient(
            f"http://127.0.0.1:{self.port}", "tok",
            emit=lambda e, **f: self.events.append((e, f)))

    def test_right_script_single_decode(self):
        _FakeStt.responses = {"he": "שלום עולם"}
        r = self.client.transcribe(b"\x00" * 320,
                                   request_id="abcd1234-000001",
                                   duration_ms=10)
        self.assertEqual(r.text, "שלום עולם")
        self.assertFalse(r.script_retried)
        self.assertEqual(len(_FakeStt.requests_seen), 1)
        self.assertEqual(_FakeStt.requests_seen[0][1], "he")

    def test_wrong_script_retries_once_with_other_hint(self):
        """THE LAW END-TO-END: he-hint returns Latin -> ONE en re-decode,
        same request id, SCRIPT_RETRY journalled, final text is the en one."""
        _FakeStt.responses = {"he": "hello world okay",
                              "en": "hello world okay!"}
        r = self.client.transcribe(b"\x00" * 320,
                                   request_id="abcd1234-000002",
                                   duration_ms=10)
        self.assertTrue(r.script_retried)
        self.assertEqual(r.hint_used, "en")
        self.assertEqual(r.text, "hello world okay!")
        self.assertEqual([h for _, h in _FakeStt.requests_seen],
                         ["he", "en"])
        # same rid on both decodes — dedup at the typer is unaffected
        self.assertEqual(_FakeStt.requests_seen[0][0],
                         _FakeStt.requests_seen[1][0])
        self.assertEqual(self.events[0][0], "SCRIPT_RETRY")
        self.assertEqual(self.events[0][1]["hint_from"], "he")
        self.assertEqual(self.events[0][1]["hint_to"], "en")

    def test_retry_does_not_loop(self):
        """If the retry ALSO comes back wrong-script, no third decode —
        one retry, never a ping-pong."""
        _FakeStt.responses = {"he": "english text here",
                              "en": "עברית שוב איכשהו"}
        r = self.client.transcribe(b"\x00" * 320,
                                   request_id="abcd1234-000003",
                                   duration_ms=10)
        self.assertEqual(len(_FakeStt.requests_seen), 2)
        self.assertEqual(r.text, "עברית שוב איכשהו")

    def test_mixed_script_correct_first_decode_survives_retry(self):
        """D-009 (adversarial find, qwen): 'סוכה event okay' trips the
        letter trigger, but the he decode SCORES higher — the retry must
        not replace it. PROOF the confidence rule can fire."""
        _FakeStt.responses = {"he": "סוכה event okay",
                              "en": "suka event okay"}
        _FakeStt.logprobs = {"he": -0.15, "en": -0.55}   # retry is worse
        r = self.client.transcribe(b"\x00" * 320,
                                   request_id="abcd1234-000009",
                                   duration_ms=10)
        self.assertEqual(len(_FakeStt.requests_seen), 2)  # retry happened
        self.assertEqual(r.text, "סוכה event okay")       # first KEPT
        self.assertTrue(r.script_retried)
        self.assertEqual(r.hint_used, "he")
        evt = dict(self.events)["SCRIPT_RETRY"]
        self.assertEqual(evt["kept"], "first")
        self.assertEqual(evt["lp_first"], -0.15)
        self.assertEqual(evt["lp_retry"], -0.55)

    def test_mismatched_response_id_raises(self):
        class Liar(_FakeStt):
            def do_POST(self):
                body = json.dumps({
                    "request_id": "ffffffff-999999", "text": "x",
                    "lang": "he", "lang_prob": 1, "avg_logprob": -0.1,
                    "no_speech_prob": 0, "decode_ms": 1, "model": "m",
                }).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        srv = HTTPServer(("127.0.0.1", 0), Liar)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            c = sttclient.SttClient(
                f"http://127.0.0.1:{srv.server_address[1]}", "tok")
            with self.assertRaises(sttclient.SttError):
                c.transcribe(b"\x00" * 320, request_id="abcd1234-000004",
                             duration_ms=10)
        finally:
            srv.shutdown()
            srv.server_close()

    def test_probe_stale_canary_is_unhealthy(self):
        """scar 5: HTTP 200 with a stale canary is a LIE."""
        _FakeStt.health = {"state": "READY", "canary_age_s": 1200,
                           "decode_p50_ms": 400, "decode_p95_ms": 700}
        p = self.client.probe()
        self.assertFalse(p.healthy)
        self.assertEqual(p.reason, "canary_stale")

    def test_probe_healthy(self):
        _FakeStt.health = {"state": "READY", "canary_age_s": 30,
                           "decode_p50_ms": 400, "decode_p95_ms": 700}
        p = self.client.probe()
        self.assertTrue(p.healthy)

    def test_conn_refused_is_conn_error_and_probe_never_raises(self):
        dead = sttclient.SttClient("http://127.0.0.1:1", "tok", timeout=0.5)
        # Windows may surface a dead port as refused OR as a timeout —
        # both must map to a typed Stt error, and probe() must not raise.
        with self.assertRaises((sttclient.SttConnError,
                                sttclient.SttTimeout)):
            dead.transcribe(b"\x00" * 320, request_id="abcd1234-000005",
                            duration_ms=10)
        p = dead.probe()
        self.assertFalse(p.healthy)
        self.assertIn(p.reason, ("conn", "timeout"))


class TokenFile(unittest.TestCase):

    def test_missing_token_is_loud(self):
        with self.assertRaises(sttclient.SttAuthError):
            sttclient.load_token(r"C:\no\such\token")

    def test_empty_token_is_loud(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".tok",
                                         delete=False) as fh:
            fh.write("   \n")
            path = fh.name
        try:
            with self.assertRaises(sttclient.SttAuthError):
                sttclient.load_token(path)
        finally:
            import os
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
