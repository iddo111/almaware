"""gates + stt tests — every branch reachable, wiring proven."""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.gates import (GATE_RMS, HALLUCINATIONS, LOGPROB_FLOOR,  # noqa: E402
                       energy_ok, verdict)
from app.stt import SttClient  # noqa: E402


class GateTests(unittest.TestCase):
    def test_energy_gate_calibration_is_between_the_populations(self):
        # floor p90 0.0060 < gate < speech median 0.0276 (measured, A's data)
        self.assertGreater(GATE_RMS, 0.0060)
        self.assertLess(GATE_RMS, 0.0276)
        self.assertFalse(energy_ok(0.003))
        self.assertTrue(energy_ok(0.0276))

    def test_every_branch_fires_on_realistic_input(self):
        self.assertEqual(verdict("", -0.1, "he"), (False, "empty"))
        self.assertEqual(verdict("שלום", -0.1, None), (False, "lang"))
        self.assertEqual(verdict("hello", -0.1, "is"), (False, "lang"))
        # Russian is FAMILY (Iddo speaks it): must pass, never transliterate
        self.assertEqual(verdict("сука нахуй", -0.2, "ru"), (True, "ok"))
        # the calibrated floor CATCHES -0.7 — the whole point (species #1)
        self.assertEqual(verdict("מה קורה", -0.7, "he"), (False, "logprob"))
        self.assertEqual(verdict("Thank you.", -0.1, "en"),
                         (False, "hallucination"))
        self.assertEqual(verdict("תודה רבה.", -0.1, "he"),
                         (False, "hallucination"))
        self.assertEqual(verdict("תבדוק את הקוד", -0.3, "he"), (True, "ok"))

    def test_floor_is_reachable_by_the_real_distribution(self):
        """A's worst real decode was -0.913; the floor must sit ABOVE some
        real decodes (reachable) and BELOW the typical good one."""
        self.assertGreater(LOGPROB_FLOOR, -0.913)
        self.assertLess(LOGPROB_FLOOR, -0.1)

    def test_none_logprob_passes_floor(self):
        # a server that omits confidence must not silence speech
        self.assertEqual(verdict("שלום לך", None, "he"), (True, "ok"))

    def test_repetition_loop_caught(self):
        """The 13:07 live scar: 'This is the one who is' * 50 must never
        type again. Reachability on the EXACT live shape."""
        loop = ("This is the one who is " * 30).strip()
        self.assertEqual(verdict(loop, -0.2, "en"), (False, "loop"))
        short_ok = "זה בסדר גמור וזה לא לולאה בכלל"
        self.assertEqual(verdict(short_ok, -0.2, "he"), (True, "ok"))

    def test_yawn_single_token_char_run_caught(self):
        """LIVE 2026-08-20 01:05 — a yawn decoded as one giant 'אההה...' (200+
        chars) and was TYPED AND ENTERED into Iddo's chat as him. One word, so
        the loop guard (word-level) never looked at it. A run of the same
        character ≥10 long inside a single token is never his dictation."""
        yawn = "א" + "ה" * 230
        self.assertEqual(verdict(yawn, -0.2, "he"), (False, "loop"))
        self.assertEqual(verdict("אהההההההההה", -0.2, "he"), (False, "loop"))
        self.assertEqual(verdict("Nooooooooooo!", -0.2, "en"), (False, "loop"))
        # legit words with short runs pass: אמממ? no — 3 chars is fine
        self.assertEqual(verdict("אהה, הבנתי", -0.2, "he")[0], True)
        self.assertEqual(verdict("שלום עולם", -0.2, "he")[0], True)

    def test_hallucination_normalization(self):
        self.assertIn("thank you", HALLUCINATIONS)
        self.assertEqual(verdict("  Thank You!  ", -0.1, "en")[1],
                         "hallucination")


class _FakeStt(BaseHTTPRequestHandler):
    """Answers /v1/transcribe; the test controls the reply via class attrs."""
    reply: dict = {}
    echo_id: bool = True

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        body = dict(self.reply)
        if self.echo_id:
            body.setdefault("request_id", self.headers.get("X-Request-Id"))
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):  # silence
        pass


class SttTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), _FakeStt)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.td = tempfile.TemporaryDirectory()
        tok = pathlib.Path(cls.td.name) / "stt-token"
        tok.write_text("test-token\n", encoding="utf-8")
        cls.client = SttClient(f"http://127.0.0.1:{cls.port}", tok, timeout_s=3)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.td.cleanup()

    def test_good_decode_round_trips(self):
        _FakeStt.reply = {"ok": True, "text": "שלום", "lang": "he",
                          "avg_logprob": -0.2, "decode_ms": 300}
        _FakeStt.echo_id = True
        r = self.client.decode("rec-1", b"RIFF")
        self.assertTrue(r.ok)
        self.assertEqual(r.text, "שלום")
        self.assertEqual(r.lang, "he")

    def test_late_reply_discarded_loudly(self):
        """scar 53: a reply with someone else's id never surfaces as ok."""
        _FakeStt.reply = {"ok": True, "text": "ghost", "request_id": "OTHER"}
        _FakeStt.echo_id = False
        r = self.client.decode("rec-2", b"RIFF")
        self.assertFalse(r.ok)
        self.assertEqual(r.reason, "late_reply")

    def test_dead_server_is_a_parkable_reason_not_a_crash(self):
        tok = pathlib.Path(self.td.name) / "stt-token"
        dead = SttClient("http://127.0.0.1:1", tok, timeout_s=1)
        r = dead.decode("rec-3", b"RIFF")
        self.assertFalse(r.ok)
        self.assertIn(r.reason, ("http", "timeout"))


if __name__ == "__main__":
    unittest.main()
