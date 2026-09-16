"""KESHEV-4D dispatch — the king's messenger.

Sends each worker its round order through the 4D router (eran1:8010, OpenAI
chat API), saves the raw reply under submissions/, and extracts the code
blocks into the paths the order names. Pure stdlib. No audio, no torch.

Usage:
    python dispatch.py round1            # dispatch all four round-1 orders
    python dispatch.py round1 --only glm-4.7-flash
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
ROUTER = "http://<lan-ip>:8010/v1/chat/completions"
TIMEOUT_S = 600

SCARS_CORE = """You are building ONE module of a from-scratch Windows dictation app
(KESHEV-4D). Hard laws, all paid for with real failures:
- Python 3.12, STDLIB ONLY. No torch, no pip installs, no audio device opens.
- Windows paths; the app dir is D:\\CLAUDE\\keshev-4d.
- Every guard needs (a) a reachability test proving it CAN fire on realistic
  input and (b) a wiring test proving the public API calls it.
- Every drop/refusal must call journal.event(...) exactly once - never lose
  speech silently.
- Return EXACTLY two fenced python code blocks, in this order, nothing else
  between them but one blank line:
  1. the module file
  2. the test file (unittest, runnable via `python -m unittest`)
- No prose before, between, or after the blocks. No markdown headers.
- Tests must not touch the network, audio devices, or the registry.
"""

ORDERS: dict[str, dict[str, dict[str, str]]] = {
    "round5fix": {
        "nemotron-3-super": {
            "module": "app/gates.py",
            "test": "tests/test_gates.py",
            "spec": """SO CLOSE. One reason: your __init__ stores self.hang_ms
(and friends) but feed() reads self._hang_ms - AttributeError on every
close. Pick ONE naming convention for ALL attributes (hang_ms, min_ms,
max_ms, gate, and your state fields) and use it consistently in both
__init__ and feed. Change NOTHING else about your logic. Resubmit the
complete module, one code block.""",
        },
    },
    "round5": {
        "nemotron-3-super": {
            "module": "app/gates.py",
            "test": "tests/test_gates.py",
            "spec": "THE LAST CHAIR, SIXTH ATTEMPT, YOU ARE THE BENCH'S LAST NAME.\nYour predecessors' deaths, in one line each - do not repeat any:\ngpt-oss counted the hang into the segment; glm closed nothing; qwen\nimported a journal that does not exist (this module is PURE: zero imports\nbeyond dataclasses/typing if you even need those; NO journal, NO IO).\n\nMODULE ONLY: one fenced python code block, app/gates.py complete. The\nking's test file is law, already on disk. It imports:\nfrom app.gates import GATE_RMS, Segmenter, energy_ok\n\nGATE_RMS = 0.008. energy_ok(rms, gate=GATE_RMS) -> rms >= gate.\nSegmenter(min_ms=280, max_ms=15000, hang_ms=420, gate=GATE_RMS) with ONE\nmethod: feed(frame_ms, rms) -> None | (start_ms, end_ms, forced).\n\nTHE EXACT TRACE (hang case) your code must reproduce:\nfeed(200,0.028) t:0->200 open at 0, last_speech=200, sil=0\nfeed(200,0.028) t->400 last_speech=400\nfeed(200,0.028) t->600 last_speech=600\nfeed(200,0.028) t->800 last_speech=800\nfeed(140,0.001) t->940  sil=140 stay open\nfeed(140,0.001) t->1080 sil=280 stay open\nfeed(140,0.001) t->1220 sil=420 >= hang_ms: RETURN (0, 800, False) NOW\nfeed(100,0.001) -> None\n\nOther cases: a 100ms speech blip then silence -> when it closes,\nlast_speech-start=100 < min_ms -> return None. Continuous speech reaching\n(t-start)>=max_ms -> return (start, t, True). A 200ms silence pause then\nspeech again -> still ONE segment (sil resets on speech). After any close,\nreset fully; next speech opens a new segment.\n\nWrite the module, then execute the trace above line by line against your\nown code on paper. Only submit when it produces exactly those returns.",
        },
    },
    "round4fix": {
        "qwen3-coder-next-fp8": {
            "module": "app/gates.py",
            "test": "tests/test_gates.py",
            "spec": """REJECTED, one reason: your Segmenter closes NOTHING on
hang. Here is the EXACT trace your code must reproduce for
test_hang_excluded_exact_tuple (min_ms=280, max_ms=15000, hang_ms=420,
gate=0.008, SPEECH=0.028, SILENCE=0.001):

feed(200,SPEECH) t:0->200 opens at 0, last_speech_end=200, silence=0
feed(200,SPEECH) t->400  last_speech_end=400
feed(200,SPEECH) t->600  last_speech_end=600
feed(200,SPEECH) t->800  last_speech_end=800
feed(140,SILENCE) t->940  silence=140  (140 < 420: stay open)
feed(140,SILENCE) t->1080 silence=280  (280 < 420: stay open)
feed(140,SILENCE) t->1220 silence=420  (420 >= 420: CLOSE NOW)
  -> return (0, 800, False)   # end = last_speech_end, hang EXCLUDED
feed(100,SILENCE) -> None (closed, nothing open)

Rules your last version broke: silence accumulates PER FRAME while open;
close fires the moment silence_run >= hang_ms INSIDE feed (not on the next
speech); end_ms = last_speech_end. A mid-sentence pause SHORTER than
hang_ms must not close (test_breath: 200ms silence then speech again ->
one segment 0..1000). Blip: if last_speech_end - start < min_ms at close
-> return None. Force-close when (t - start) >= max_ms -> (start, t, True).
MODULE ONLY, one code block; the king's test file is law and stays.""",
        },
    },
    "round4": {
        "qwen3-coder-next-fp8": {
            "module": "app/gates.py",
            "test": "tests/test_gates.py",
            "spec": 'MODULE ONLY - one fenced python code block. The king\'s test file\nbelow is LAW, already on disk, immutable. Your module must pass it\nVERBATIM - method names, signatures, constants exactly as the tests call\nthem. Trace each test against your code before submitting.\n\nYour module: app/gates.py - THE SEAT THAT BROKE TWO WORKERS (4 rejections). The law:\n\n```python\n"""KING\'S CANONICAL TESTS — gates/segmenter. Workers may not edit this file.\n\nThe law: a segment ends where SPEECH ended (hang excluded); blips below\nmin_ms yield None; monologues force-close at max_ms; silence never opens.\n"""\nfrom __future__ import annotations\n\nimport pathlib\nimport sys\nimport unittest\n\nsys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))\n\nfrom app.gates import GATE_RMS, Segmenter, energy_ok  # noqa: E402\n\nSPEECH = GATE_RMS + 0.02\nSILENCE = 0.001\n\n\ndef run(seg, frames):\n    out = []\n    for ms, rms in frames:\n        r = seg.feed(ms, rms)\n        if r is not None:\n            out.append(r)\n    return out\n\n\nclass EnergyTests(unittest.TestCase):\n    def test_gate_between_the_populations(self):\n        self.assertGreater(GATE_RMS, 0.0060)   # noise p90\n        self.assertLess(GATE_RMS, 0.0276)      # speech median\n        self.assertFalse(energy_ok(0.003))\n        self.assertTrue(energy_ok(0.0276))\n\n\nclass SegmenterTests(unittest.TestCase):\n    def test_silence_never_opens(self):\n        seg = Segmenter()\n        self.assertEqual(run(seg, [(100, SILENCE)] * 50), [])\n\n    def test_blip_below_min_yields_none(self):\n        seg = Segmenter(min_ms=280, max_ms=15000, hang_ms=420)\n        out = run(seg, [(100, SPEECH)] + [(100, SILENCE)] * 6)\n        self.assertEqual(out, [])\n\n    def test_hang_excluded_exact_tuple(self):\n        seg = Segmenter(min_ms=280, max_ms=15000, hang_ms=420)\n        out = run(seg, [(200, SPEECH)] * 4 + [(140, SILENCE)] * 3 + [(100, SILENCE)])\n        self.assertEqual(len(out), 1)\n        start, end, forced = out[0]\n        self.assertEqual((start, end, forced), (0, 800, False))\n\n    def test_monologue_force_closes(self):\n        seg = Segmenter(min_ms=280, max_ms=15000, hang_ms=420)\n        out = run(seg, [(500, SPEECH)] * 40)\n        self.assertEqual(len(out), 1)\n        start, end, forced = out[0]\n        self.assertTrue(forced)\n        self.assertLessEqual(end - start, 15000)\n\n    def test_two_utterances_two_segments(self):\n        seg = Segmenter(min_ms=280, max_ms=15000, hang_ms=420)\n        frames = ([(200, SPEECH)] * 3 + [(500, SILENCE)] +\n                  [(200, SPEECH)] * 3 + [(500, SILENCE)])\n        out = run(seg, frames)\n        self.assertEqual(len(out), 2)\n\n    def test_breath_inside_sentence_does_not_split(self):\n        seg = Segmenter(min_ms=280, max_ms=15000, hang_ms=420)\n        out = run(seg, [(200, SPEECH)] * 2 + [(200, SILENCE)] +\n                       [(200, SPEECH)] * 2 + [(500, SILENCE)])\n        self.assertEqual(len(out), 1)\n\n\nif __name__ == "__main__":\n    unittest.main()\n\n```',
        },
        "gpt-oss-120b": {
            "module": "app/sttclient.py",
            "test": "tests/test_sttclient.py",
            "spec": 'MODULE ONLY - one fenced python code block. The king\'s test file\nbelow is LAW, already on disk, immutable. Your module must pass it\nVERBATIM - method names, signatures, constants exactly as the tests call\nthem. Trace each test against your code before submitting.\n\nYour module: app/sttclient.py. The law:\n\n```python\n"""KING\'S CANONICAL TESTS - sttclient. Workers may not edit this file.\n\nThe law: one attempt, deadline, late replies discarded loudly, dead servers\nreturn a parkable reason and never an exception; token read per call.\n"""\nfrom __future__ import annotations\n\nimport json\nimport pathlib\nimport sys\nimport tempfile\nimport threading\nimport unittest\nfrom http.server import BaseHTTPRequestHandler, HTTPServer\n\nsys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))\n\nfrom app.sttclient import DecodeResult, SttClient  # noqa: E402\n\n\nclass _FakeStt(BaseHTTPRequestHandler):\n    reply: dict = {}\n    echo_id: bool = True\n\n    def do_POST(self):  # noqa: N802\n        n = int(self.headers.get("Content-Length") or 0)\n        self.rfile.read(n)\n        body = dict(self.reply)\n        if self.echo_id:\n            body.setdefault("request_id", self.headers.get("X-Request-Id"))\n        data = json.dumps(body).encode()\n        self.send_response(200)\n        self.send_header("Content-Type", "application/json")\n        self.send_header("Content-Length", str(len(data)))\n        self.end_headers()\n        self.wfile.write(data)\n\n    def do_GET(self):  # noqa: N802 - /health\n        self.send_response(200)\n        self.send_header("Content-Length", "2")\n        self.end_headers()\n        self.wfile.write(b"ok")\n\n    def log_message(self, *a):\n        pass\n\n\nclass SttClientTests(unittest.TestCase):\n    @classmethod\n    def setUpClass(cls):\n        cls.server = HTTPServer(("127.0.0.1", 0), _FakeStt)\n        cls.port = cls.server.server_address[1]\n        threading.Thread(target=cls.server.serve_forever, daemon=True).start()\n        cls.td = tempfile.TemporaryDirectory()\n        cls.tok = pathlib.Path(cls.td.name) / "stt-token"\n        cls.tok.write_text("test-token\\n", encoding="utf-8")\n        cls.client = SttClient(f"http://127.0.0.1:{cls.port}", cls.tok,\n                               timeout_s=3)\n\n    @classmethod\n    def tearDownClass(cls):\n        cls.server.shutdown()\n        cls.td.cleanup()\n\n    def test_good_decode_round_trips(self):\n        _FakeStt.reply = {"ok": True, "text": "shalom", "lang": "he",\n                          "avg_logprob": -0.2, "decode_ms": 300}\n        _FakeStt.echo_id = True\n        r = self.client.decode("rec-1", b"RIFF")\n        self.assertTrue(r.ok)\n        self.assertEqual(r.text, "shalom")\n        self.assertEqual(r.lang, "he")\n\n    def test_late_reply_discarded_loudly(self):\n        _FakeStt.reply = {"ok": True, "text": "ghost", "request_id": "OTHER"}\n        _FakeStt.echo_id = False\n        r = self.client.decode("rec-2", b"RIFF")\n        self.assertFalse(r.ok)\n        self.assertEqual(r.reason, "late_reply")\n\n    def test_dead_server_parkable_never_raises(self):\n        dead = SttClient("http://127.0.0.1:1", self.tok, timeout_s=1)\n        r = dead.decode("rec-3", b"RIFF")\n        self.assertFalse(r.ok)\n        self.assertIn(r.reason, ("http", "timeout"))\n\n    def test_health_true_on_200(self):\n        self.assertTrue(self.client.health())\n\n    def test_token_read_per_call(self):\n        _FakeStt.reply = {"ok": True, "text": "x"}\n        _FakeStt.echo_id = True\n        self.tok.write_text("rotated\\n", encoding="utf-8")\n        r = self.client.decode("rec-4", b"RIFF")\n        self.assertTrue(r.ok, "a rotated token must not require a restart")\n        self.tok.write_text("test-token\\n", encoding="utf-8")\n\n    def test_result_defaults(self):\n        r = DecodeResult(ok=False, reason="timeout")\n        self.assertEqual((r.text, r.lang, r.ms), ("", None, 0))\n\n\nif __name__ == "__main__":\n    unittest.main()\n\n```',
        },
    },
    "round3fix": {
        "qwen3-coder-next-fp8": {
            "module": "app/sttclient.py",
            "test": "tests/test_sttclient.py",
            "spec": """REJECTED by the king, one reason: threading.Lock() at
class scope with NO import threading - the file dies at import, the same
missing-import disease as your round-1 journal tests. Resubmit the complete
module (ONE code block, module only; the king's test file is law and stays).
Add every import you use. The client must pass tests/test_sttclient.py
verbatim: DecodeResult(ok, text='', lang=None, avg_logprob=None, ms=0,
reason=''), SttClient(base_url, token_file, timeout_s=8.0), token read PER
CALL, POST /v1/transcribe with Authorization Bearer + X-Request-Id +
X-Lang-Hint, request_id mismatch -> reason='late_reply', timeout->'timeout',
URLError->'http' ('timeout' if 'timed out' in str), bad json->'server', ONE
attempt, .health() GET /health -> bool.""",
        },
    },
    "round3": {
        "glm-4.7-flash": {
            "module": "app/gates.py",
            "test": "tests/test_gates.py",
            "spec": 'PROTOCOL CHANGE BY THE KING: you submit the MODULE ONLY -\nONE fenced python code block, nothing else. The test file below is the\nLAW, already on disk, immutable by you. Your module must make it pass\nverbatim. Trace every test frame-by-frame against your code BEFORE\nsubmitting; every previous rejection tonight was a worker who did not.\n\nYour module file: app/gates.py\n\nTHE LAW (already at its path, do not resubmit it):\n\n```python\n"""KING\'S CANONICAL TESTS — gates/segmenter. Workers may not edit this file.\n\nThe law: a segment ends where SPEECH ended (hang excluded); blips below\nmin_ms yield None; monologues force-close at max_ms; silence never opens.\n"""\nfrom __future__ import annotations\n\nimport pathlib\nimport sys\nimport unittest\n\nsys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))\n\nfrom app.gates import GATE_RMS, Segmenter, energy_ok  # noqa: E402\n\nSPEECH = GATE_RMS + 0.02\nSILENCE = 0.001\n\n\ndef run(seg, frames):\n    out = []\n    for ms, rms in frames:\n        r = seg.feed(ms, rms)\n        if r is not None:\n            out.append(r)\n    return out\n\n\nclass EnergyTests(unittest.TestCase):\n    def test_gate_between_the_populations(self):\n        self.assertGreater(GATE_RMS, 0.0060)   # noise p90\n        self.assertLess(GATE_RMS, 0.0276)      # speech median\n        self.assertFalse(energy_ok(0.003))\n        self.assertTrue(energy_ok(0.0276))\n\n\nclass SegmenterTests(unittest.TestCase):\n    def test_silence_never_opens(self):\n        seg = Segmenter()\n        self.assertEqual(run(seg, [(100, SILENCE)] * 50), [])\n\n    def test_blip_below_min_yields_none(self):\n        seg = Segmenter(min_ms=280, max_ms=15000, hang_ms=420)\n        out = run(seg, [(100, SPEECH)] + [(100, SILENCE)] * 6)\n        self.assertEqual(out, [])\n\n    def test_hang_excluded_exact_tuple(self):\n        seg = Segmenter(min_ms=280, max_ms=15000, hang_ms=420)\n        out = run(seg, [(200, SPEECH)] * 4 + [(140, SILENCE)] * 3 + [(100, SILENCE)])\n        self.assertEqual(len(out), 1)\n        start, end, forced = out[0]\n        self.assertEqual((start, end, forced), (0, 800, False))\n\n    def test_monologue_force_closes(self):\n        seg = Segmenter(min_ms=280, max_ms=15000, hang_ms=420)\n        out = run(seg, [(500, SPEECH)] * 40)\n        self.assertEqual(len(out), 1)\n        start, end, forced = out[0]\n        self.assertTrue(forced)\n        self.assertLessEqual(end - start, 15000)\n\n    def test_two_utterances_two_segments(self):\n        seg = Segmenter(min_ms=280, max_ms=15000, hang_ms=420)\n        frames = ([(200, SPEECH)] * 3 + [(500, SILENCE)] +\n                  [(200, SPEECH)] * 3 + [(500, SILENCE)])\n        out = run(seg, frames)\n        self.assertEqual(len(out), 2)\n\n    def test_breath_inside_sentence_does_not_split(self):\n        seg = Segmenter(min_ms=280, max_ms=15000, hang_ms=420)\n        out = run(seg, [(200, SPEECH)] * 2 + [(200, SILENCE)] +\n                       [(200, SPEECH)] * 2 + [(500, SILENCE)])\n        self.assertEqual(len(out), 1)\n\n\nif __name__ == "__main__":\n    unittest.main()\n\n```\n\nReturn exactly ONE python code block: the complete module.',
        },
        "gpt-oss-120b": {
            "module": "app/presence.py",
            "test": "tests/test_presence.py",
            "spec": 'PROTOCOL CHANGE BY THE KING: you submit the MODULE ONLY -\nONE fenced python code block, nothing else. The test file below is the\nLAW, already on disk, immutable by you. Your module must make it pass\nverbatim. Trace every test frame-by-frame against your code BEFORE\nsubmitting; every previous rejection tonight was a worker who did not.\n\nYour module file: app/presence.py\n\nTHE LAW (already at its path, do not resubmit it):\n\n```python\n"""KING\'S CANONICAL TESTS - presence. Workers may not edit this file.\n\nThe law: 120s idle kills Enter, 600s kills typing; unreadable clock types\nbut never Enters; armed strictly BEFORE arm_time+ARM_TTL_S, expired AT it.\n"""\nfrom __future__ import annotations\n\nimport pathlib\nimport sys\nimport unittest\n\nsys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))\n\nfrom app.presence import (ARM_TTL_S, IDLE_NO_ENTER_S, IDLE_NO_TYPE_S,  # noqa: E402\n                          Presence)\n\n\nclass ConstantsTests(unittest.TestCase):\n    def test_the_d003_ruling(self):\n        self.assertEqual((IDLE_NO_ENTER_S, IDLE_NO_TYPE_S, ARM_TTL_S),\n                         (120, 600, 900))\n\n\nclass IdleTests(unittest.TestCase):\n    def test_present_types_and_enters(self):\n        p = Presence(idle_fn=lambda: 5.0)\n        self.assertEqual(p.verdict(), (True, True, "ok"))\n\n    def test_idle_540_types_never_enters(self):\n        p = Presence(idle_fn=lambda: 540.0)\n        self.assertEqual(p.verdict(), (True, False, "idle_no_enter"))\n\n    def test_idle_700_types_nothing(self):\n        p = Presence(idle_fn=lambda: 700.0)\n        self.assertEqual(p.verdict(), (False, False, "idle_no_type"))\n\n    def test_boundaries_inclusive(self):\n        self.assertEqual(Presence(idle_fn=lambda: 120.0).verdict()[2],\n                         "idle_no_enter")\n        self.assertEqual(Presence(idle_fn=lambda: 600.0).verdict()[2],\n                         "idle_no_type")\n\n    def test_unreadable_clock_fails_open_type_closed_enter(self):\n        p = Presence(idle_fn=lambda: None)\n        self.assertEqual(p.verdict(), (True, False, "clock_unreadable"))\n\n\nclass ArmTests(unittest.TestCase):\n    def test_armed_mode_blocks_without_arm(self):\n        p = Presence(idle_fn=lambda: 0.0, armed_mode=True)\n        self.assertEqual(p.verdict(now=1000.0),\n                         (False, False, "arm_required"))\n\n    def test_armed_strictly_before_ttl_expired_at_ttl(self):\n        p = Presence(idle_fn=lambda: 0.0, armed_mode=True)\n        p.arm(now=1000.0)\n        self.assertEqual(p.verdict(now=1000.0 + ARM_TTL_S - 1)[2], "armed")\n        self.assertEqual(p.verdict(now=1000.0 + ARM_TTL_S)[2], "arm_required")\n\n    def test_disarm_immediate(self):\n        p = Presence(idle_fn=lambda: 0.0, armed_mode=True)\n        p.arm(now=1000.0)\n        p.disarm()\n        self.assertEqual(p.verdict(now=1001.0)[2], "arm_required")\n\n    def test_rearm_extends(self):\n        p = Presence(idle_fn=lambda: 0.0, armed_mode=True)\n        p.arm(now=1000.0)\n        p.arm(now=1000.0 + 800)\n        self.assertEqual(p.verdict(now=1000.0 + ARM_TTL_S + 100)[2], "armed")\n\n\nif __name__ == "__main__":\n    unittest.main()\n\n```\n\nReturn exactly ONE python code block: the complete module.',
        },
        "qwen3-coder-next-fp8": {
            "module": "app/sttclient.py",
            "test": "tests/test_sttclient.py",
            "spec": 'PROTOCOL CHANGE BY THE KING: you submit the MODULE ONLY -\nONE fenced python code block, nothing else. The test file below is the\nLAW, already on disk, immutable by you. Your module must make it pass\nverbatim. Trace every test frame-by-frame against your code BEFORE\nsubmitting; every previous rejection tonight was a worker who did not.\n\nYour module file: app/sttclient.py\n\nTHE LAW (already at its path, do not resubmit it):\n\n```python\n"""KING\'S CANONICAL TESTS - sttclient. Workers may not edit this file.\n\nThe law: one attempt, deadline, late replies discarded loudly, dead servers\nreturn a parkable reason and never an exception; token read per call.\n"""\nfrom __future__ import annotations\n\nimport json\nimport pathlib\nimport sys\nimport tempfile\nimport threading\nimport unittest\nfrom http.server import BaseHTTPRequestHandler, HTTPServer\n\nsys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))\n\nfrom app.sttclient import DecodeResult, SttClient  # noqa: E402\n\n\nclass _FakeStt(BaseHTTPRequestHandler):\n    reply: dict = {}\n    echo_id: bool = True\n\n    def do_POST(self):  # noqa: N802\n        n = int(self.headers.get("Content-Length") or 0)\n        self.rfile.read(n)\n        body = dict(self.reply)\n        if self.echo_id:\n            body.setdefault("request_id", self.headers.get("X-Request-Id"))\n        data = json.dumps(body).encode()\n        self.send_response(200)\n        self.send_header("Content-Type", "application/json")\n        self.send_header("Content-Length", str(len(data)))\n        self.end_headers()\n        self.wfile.write(data)\n\n    def do_GET(self):  # noqa: N802 - /health\n        self.send_response(200)\n        self.send_header("Content-Length", "2")\n        self.end_headers()\n        self.wfile.write(b"ok")\n\n    def log_message(self, *a):\n        pass\n\n\nclass SttClientTests(unittest.TestCase):\n    @classmethod\n    def setUpClass(cls):\n        cls.server = HTTPServer(("127.0.0.1", 0), _FakeStt)\n        cls.port = cls.server.server_address[1]\n        threading.Thread(target=cls.server.serve_forever, daemon=True).start()\n        cls.td = tempfile.TemporaryDirectory()\n        cls.tok = pathlib.Path(cls.td.name) / "stt-token"\n        cls.tok.write_text("test-token\n", encoding="utf-8")\n        cls.client = SttClient(f"http://127.0.0.1:{cls.port}", cls.tok,\n                               timeout_s=3)\n\n    @classmethod\n    def tearDownClass(cls):\n        cls.server.shutdown()\n        cls.td.cleanup()\n\n    def test_good_decode_round_trips(self):\n        _FakeStt.reply = {"ok": True, "text": "shalom", "lang": "he",\n                          "avg_logprob": -0.2, "decode_ms": 300}\n        _FakeStt.echo_id = True\n        r = self.client.decode("rec-1", b"RIFF")\n        self.assertTrue(r.ok)\n        self.assertEqual(r.text, "shalom")\n        self.assertEqual(r.lang, "he")\n\n    def test_late_reply_discarded_loudly(self):\n        _FakeStt.reply = {"ok": True, "text": "ghost", "request_id": "OTHER"}\n        _FakeStt.echo_id = False\n        r = self.client.decode("rec-2", b"RIFF")\n        self.assertFalse(r.ok)\n        self.assertEqual(r.reason, "late_reply")\n\n    def test_dead_server_parkable_never_raises(self):\n        dead = SttClient("http://127.0.0.1:1", self.tok, timeout_s=1)\n        r = dead.decode("rec-3", b"RIFF")\n        self.assertFalse(r.ok)\n        self.assertIn(r.reason, ("http", "timeout"))\n\n    def test_health_true_on_200(self):\n        self.assertTrue(self.client.health())\n\n    def test_token_read_per_call(self):\n        _FakeStt.reply = {"ok": True, "text": "x"}\n        _FakeStt.echo_id = True\n        self.tok.write_text("rotated\n", encoding="utf-8")\n        r = self.client.decode("rec-4", b"RIFF")\n        self.assertTrue(r.ok, "a rotated token must not require a restart")\n        self.tok.write_text("test-token\n", encoding="utf-8")\n\n    def test_result_defaults(self):\n        r = DecodeResult(ok=False, reason="timeout")\n        self.assertEqual((r.text, r.lang, r.ms), ("", None, 0))\n\n\nif __name__ == "__main__":\n    unittest.main()\n\n```\n\nReturn exactly ONE python code block: the complete module.',
        },
    },
    "round2b": {
        "glm-4.7-flash": {
            "module": "app/gates.py",
            "test": "tests/test_gates.py",
            "spec": """REASSIGNED TO YOU after gpt-oss failed it twice. Their
deaths, do not repeat: (1) counting the hang window into the segment;
(2) fix-round tests that expect segments their own module returns None
for. Spec:

GATE_RMS=0.008 (speech median 0.0276, noise p90 0.0060 - keep all three
numbers as constants with the comment). energy_ok(rms, gate=GATE_RMS) ->
bool (rms >= gate). Segmenter(min_ms=280, max_ms=15000, hang_ms=420,
gate=GATE_RMS): .feed(frame_ms:int, rms:float) -> None | (start_ms,
end_ms, forced:bool). Internal running clock starts at 0 and advances by
frame_ms per call. Opens at the frame where energy_ok first True. While
open: speech frames update last_speech_end; silence accumulates
silence_run. Close when silence_run >= hang_ms -> end_ms =
last_speech_end (HANG EXCLUDED), forced=False; or when (t - start) >=
max_ms -> end_ms = current t, forced=True. After close reset so it can
reopen. If end_ms - start_ms < min_ms -> return None instead of the
tuple. PURE: no IO. Tests (each MUST pass against your own module -
run them in your head frame by frame before submitting): 100ms speech
blip + 600ms silence -> None; 800ms speech + hang -> (0, 800, False)
exactly; 20s continuous speech -> forced=True and end-start <= 15000;
all-silence -> no open; two utterances -> two segments.""",
        },
        "qwen3-coder-next-fp8": {
            "module": "app/presence.py",
            "test": "tests/test_presence.py",
            "spec": """REJECTED by the king, one reason: your two expiry tests
use OPPOSITE boundary conventions (one asserts armed AT arm_time+TTL, the
other asserts expired past it while the module answers armed). THE
CONVENTION: is_armed(now) is True strictly BEFORE arm_time+ARM_TTL_S and
False AT and after arm_time+ARM_TTL_S. Align the module and BOTH tests to
that sentence. Everything else in your submission was fine - keep it.
Constants IDLE_NO_ENTER_S=120, IDLE_NO_TYPE_S=600, ARM_TTL_S=900; idle
boundaries stay INCLUSIVE (idle>=600 no_type, idle>=120 no_enter).""",
        },
    },
    "round2reassign": {
        "qwen3-coder-next-fp8": {
            "module": "app/presence.py",
            "test": "tests/test_presence.py",
            "spec": """REASSIGNED TO YOU after glm failed it twice. Their two
deaths, do not repeat: (1) tests that time.sleep(900) for real; (2) tests
that rebind idle_fn AFTER constructing Presence, so the object holds the
old callable and the tests exercise nothing - inject a MUTABLE holder or
construct per-case. Spec:

Constants IDLE_NO_ENTER_S=120, IDLE_NO_TYPE_S=600, ARM_TTL_S=900.
Presence(idle_fn, armed_mode=False). .verdict(now=None) ->
(may_type, may_enter, reason), reasons ok|idle_no_enter|idle_no_type|
clock_unreadable|arm_required|armed. Rules: armed_mode -> armed/arm_required
by .is_armed(now) with ARM_TTL_S expiry via .arm(now)/.disarm(); else
idle_fn() None -> (True,False,'clock_unreadable'); idle>=600 ->
(False,False,'idle_no_type'); idle>=120 -> (True,False,'idle_no_enter');
else (True,True,'ok'). Boundaries INCLUSIVE. Production idle_fn reads
GetLastInputInfo wrap-safe ((now-last)&0xFFFFFFFF) but tests inject
lambdas. Reachability: every reason fires; arm expires at
now=arm_time+ARM_TTL_S+1; NO test sleeps more than 1s.""",
        },
    },
    "round2fix": {
        "glm-4.7-flash": {
            "module": "app/presence.py",
            "test": "tests/test_presence.py",
            "spec": """REJECTED by the king, one reason: your tests call
time.sleep(ARM_TTL_S + 0.1) - a REAL 900-second sleep, six times, a
ninety-minute suite. verdict(now)/is_armed(now)/arm(now) take a now
parameter precisely so tests INJECT time: arm(now=1000.0) then
verdict(now=1000.0+901) proves expiry with ZERO sleeping. No test may
sleep more than one second. Resubmit BOTH files. Original spec:

Constants IDLE_NO_ENTER_S=120, IDLE_NO_TYPE_S=600, ARM_TTL_S=900.
Presence(idle_fn, armed_mode=False). .verdict(now=None) ->
(may_type, may_enter, reason) with reasons ok|idle_no_enter|idle_no_type|
clock_unreadable|arm_required|armed. idle>=600 -> (False,False);
idle>=120 -> (True,False); idle_fn None -> (True,False,'clock_unreadable').
armed_mode: .arm(now)/.disarm()/.is_armed(now), expiry after ARM_TTL_S.
Production idle_fn reads GetLastInputInfo, wrap-safe (now-last)&0xFFFFFFFF.""",
        },
        "gpt-oss-120b": {
            "module": "app/gates.py",
            "test": "tests/test_gates.py",
            "spec": """REJECTED by the king, one reason: a 100ms blip followed
by silence returned (0, 520, False) - you count the hang window into the
segment and never re-check min_ms at close. The segment ENDS where speech
ended (before the hang silence), and if that speech span is shorter than
min_ms the close yields None. Resubmit BOTH files. Original spec:

GATE_RMS=0.008 (speech median 0.0276, noise p90 0.0060). energy_ok(rms,
gate)->bool. Segmenter(min_ms=280, max_ms=15000, hang_ms=420):
feed(frame_ms, rms, now_ms optional) -> None | (start_ms, end_ms, forced).
Opens on energy_ok; closes after hang_ms below gate (end = last SPEECH ms,
hang excluded) or force-closes at max_ms (forced=True). Speech span <
min_ms at close -> return None. PURE, no IO. Tests: blip yields None;
speech+hang closes with hang EXCLUDED from end_ms; 20s monologue
force-closes forced=True; silence never opens.""",
        },
        "nemotron-3-super": {
            "module": "app/sttclient.py",
            "test": "tests/test_sttclient.py",
            "spec": """REJECTED by the king, one reason: line 7 is
`import journal  # assumed to be provided elsewhere`. Nothing is provided
elsewhere - the import fails and every test dies at import time. The
client is PURE: it RETURNS reasons, the CALLER journals. Remove every
journal reference. Resubmit BOTH files. Original spec:

DecodeResult dataclass: ok, text='', lang=None, avg_logprob=None, ms=0,
reason='' ('' | timeout | http | late_reply | server).
SttClient(base_url, token_file, timeout_s=8.0), token read PER CALL.
.decode(rec_id, body_bytes, lang_hint='auto'): POST /v1/transcribe,
Authorization Bearer, X-Request-Id, X-Lang-Hint. Reply request_id !=
rec_id -> reason='late_reply'. timeout->'timeout'; URLError->'http'
(or 'timeout' if 'timed out' in str); bad json->'server'. ONE attempt.
.health()->bool. Tests: local http.server on 127.0.0.1:0 in a thread;
good decode; late_reply; dead port -> http/timeout, never an exception.""",
        },
    },
    "round2": {
        "qwen3-coder-next-fp8": {
            "module": "app/typer.py",
            "test": "tests/test_typer.py",
            "spec": """Module: typer.py - text into the owner's window ONLY.
Import from app.journal (your accepted module). API:
FocusInfo(hwnd:int, pid:int, exe:str) dataclass with
.same_window(other)->bool comparing hwnd+pid+exe (exe case-insensitive) -
NEVER window title. Typer(journal, presence_verdict, focus_fn, send_text,
send_enter, avoid_exes=()) - all callables injected, tests need no desktop.
.deliver(rec_id, text)->(ok, reason): reason in
ok|dup|presence|no_focus|avoided_exe|send_failed. Dedup: a rec_id that
already typed can NEVER type again (structural, a set). presence_verdict()
returns (may_type, may_enter, why); refused -> journal one line, refuse.
.enter(rec_id, focus_at_type)->(ok, reason): presence RE-asked (may_enter),
focus RE-read and must be same_window(focus_at_type) else refuse
window_changed - Enter must never land in a different window than the text.
Every refusal journals EXACTLY one line using journal.event with names from
its VOCAB (TYPED, DROP, GATED, STATE). No clipboard code of any kind.
Reachability tests: dup refuses on second deliver; presence refusal blocks;
window_changed blocks enter; happy path journals TYPED.""",
        },
        "glm-4.7-flash": {
            "module": "app/presence.py",
            "test": "tests/test_presence.py",
            "spec": """Module: presence.py - is the OWNER at the machine.
Constants IDLE_NO_ENTER_S=120, IDLE_NO_TYPE_S=600, ARM_TTL_S=900.
Presence(idle_fn, armed_mode=False): idle_fn injected (tests pass lambdas;
production reads GetLastInputInfo with 32-bit wrap-safe subtraction:
(now - last) & 0xFFFFFFFF). .verdict(now=None) ->
(may_type: bool, may_enter: bool, reason: str), reasons:
ok | idle_no_enter | idle_no_type | clock_unreadable | arm_required | armed.
Rules: idle>=600 -> (False,False); idle>=120 -> (True,False) - typing junk
is recoverable, SUBMITTING as the owner is not; idle_fn returns None ->
(True,False,'clock_unreadable') fail-open type / fail-closed Enter.
armed_mode=True: verdict ignores idle; .arm(now)/.disarm();
.is_armed(now) expires after ARM_TTL_S - an arm that never expires is the
09:46 scar again. Reachability tests: 540s idle types but never Enters;
700s types nothing; None clock; arm expiry at the boundary.""",
        },
        "gpt-oss-120b": {
            "module": "app/gates.py",
            "test": "tests/test_gates.py",
            "spec": """Module: gates.py - pre-GPU energy gate + segment policy.
GATE_RMS=0.008 (measured: speech median 0.0276, noise p90 0.0060 - the gate
sits in the gap; keep these three numbers as constants with a comment).
energy_ok(rms, gate=GATE_RMS)->bool. Segmenter(min_ms=280, max_ms=15000,
hang_ms=420): feed(frame_ms, rms, now_ms) -> None | (start_ms, end_ms):
opens a segment when energy_ok, closes after hang_ms below the gate or at
max_ms (forced close journals nothing here - pure module, returns
('forced' flag) in the tuple as third element). Segments shorter than
min_ms return None (blips are not speech). PURE: no IO, no journal - the
caller journals SEG. Reachability tests: a blip below min_ms yields None;
speech+hang closes once with correct bounds; a 20s monologue force-closes
at max_ms with forced=True; silence never opens.""",
        },
        "nemotron-3-super": {
            "module": "app/sttclient.py",
            "test": "tests/test_sttclient.py",
            "spec": """Module: sttclient.py - the decode HTTP client contract.
DecodeResult dataclass: ok, text='', lang=None, avg_logprob=None, ms=0,
reason='' (reason in ''|timeout|http|late_reply|server).
SttClient(base_url, token_file, timeout_s=8.0): token READ PER CALL from
token_file (rotation without restart). .decode(rec_id, wav_bytes,
lang_hint='auto') -> DecodeResult: POST base_url+'/v1/transcribe', headers
Authorization Bearer, X-Request-Id=rec_id, X-Lang-Hint. On reply: if
payload request_id differs from rec_id -> (ok=False, reason='late_reply')
LOUDLY - a late reply must never surface under another record. timeout ->
'timeout'; URLError -> 'http' (or 'timeout' if 'timed out' in str);
bad json -> 'server'. ONE attempt only - the router owns retries.
.health()->bool GET /health with token, 3s. Tests: use
http.server.HTTPServer on 127.0.0.1:0 in a thread as a fake (no real
network); good decode round-trips; late_reply fires; dead port ->
http/timeout reason, never an exception.""",
        },
    },
    "round1fix3": {
        "nemotron-3-super": {
            "module": "app/textguard.py",
            "test": "tests/test_textguard.py",
            "spec": """REJECTED by the king, one reason: your tests
mock.patch('app.textguard.journal', ...) but your module never imports or
exposes any journal symbol - 10 of 12 tests error. Do NOT reference a
journal in this module at all: verdict() is PURE - it returns the reason,
the CALLER journals. Resubmit BOTH files complete. Original spec:

Module: textguard.py. verdict(text, avg_logprob, lang) ->
tuple[bool, str]. Rules in order: empty/whitespace -> (False,'empty');
lang not in WHITELIST=('he','en') -> (False,'lang') and None is NOT a
member; avg_logprob is not None and < FLOOR=-0.6 -> (False,'logprob');
normalized text in HALLUCINATIONS frozenset ('thank you.', 'thanks for
watching!', 'you', 'תודה רבה.', 'תודה שצפיתם') -> (False,'hallucination');
else (True,'ok'). Reachability tests: every branch fires on realistic
input incl. -0.7 caught and -0.1 passing. PURE MODULE: no journal, no IO,
no globals mutated.""",
        },
    },
    "round1fix2": {
        "gpt-oss-120b": {
            "module": "app/spool.py",
            "test": "tests/test_spool.py",
            "spec": """REJECTED by the king, one reason: your own test breaks.
test_sweep_recovers_orphans_and_is_idempotent does
`c[1][0].endswith(".json")` on a mock-call argument that is a WindowsPath -
Path objects have no .endswith. Wrap with str(...) or compare .suffix.
Resubmit BOTH files complete; keep everything that worked. Original spec:

Module: spool.py - write-ahead audio spool.
Spool(dir, max_records=500). .admit(rec_id, wav_bytes, meta) writes
<rec_id>.wav and <rec_id>.json sidecar to disk FIRST, then registers in
memory; returns the paths. .complete(rec_id) removes from pending (files
stay). .evict_oldest() drops the OLDEST pending record (keeps files),
returns its id; auto-called when pending > max_records. .pending() ordered
ids. .sweep() finds sidecars on disk not in memory (crash recovery), O(new):
never re-reads an already-seen sidecar. Tests: admit writes both files
before returning; evict never deletes files; sweep after simulated crash
finds exactly the orphans; second sweep opens no already-seen sidecar.""",
        },
    },
    "round1fix": {
        "qwen3-coder-next-fp8": {
            "module": "app/journal.py",
            "test": "tests/test_journal.py",
            "spec": """REJECTED by the king, one reason: your tests don't run.
test_concurrent_events_no_race uses `threading` WITHOUT IMPORTING IT, and
test_rotation_triggers_at_boundary calls os.path.getsize on the journal file
BEFORE any event created it (FileNotFoundError). A test suite that errors
proves nothing.
Resubmit BOTH files complete (module + tests). Fix the two broken tests;
keep everything else that worked. Original spec follows.

Module: journal.py - the append-only event journal.
API: Journal(path) with .event(name, **fields) appending ONE json line
{ts, evt, **fields}. CLOSED vocabulary VOCAB frozenset (SESSION_BEGIN,
DEVICE_OPEN, SEG, DECODE, TYPED, DROP, GATED, HEARTBEAT, STATE, WORKER_DIED,
WORKER_RESPAWN, ALARM). Unknown name raises JournalVocabError. Thread-safe
(lock). File opened per-write. rotate(max_bytes) renames to .1, never
deletes. Reachability tests: unknown-name raises; round-trip json.loads;
rotation at the boundary keeps the old file.""",
        },
        "glm-4.7-flash": {
            "module": "app/devicelaw.py",
            "test": "tests/test_devicelaw.py",
            "spec": """REJECTED by the king, one reason: choose_device returned
the LOWERCASED name; the caller must receive the device's ORIGINAL name
exactly as the OS lists it (casefold for MATCHING only). Also your
test_choose_device_non_string_entry expected 'Valid Device' to be chosen,
but no allowlist substring matches it - a test that contradicts your own
module. Resubmit BOTH files complete. Original spec follows.

Module: devicelaw.py. _NEVER_MIC = ("WH-1000","Hands-Free","Headset",
"Bluetooth") SOURCE-LEVEL tuple, no merge logic, outranks every parameter.
ALLOWED_SUBSTRINGS default ("BRIO","Scarlett","USBAudio").
choose_device(device_names, allowed=ALLOWED_SUBSTRINGS) -> first ORIGINAL
name that matches allowed AND is not forbidden (case-insensitive substring
matching); None when nothing qualifies (caller journals IDLE_NO_MIC, opens
NOTHING). is_forbidden(name) -> bool. Non-string entries in the list are
skipped. Reachability tests: BRIO passes AND KEEPS ITS ORIGINAL CASING;
'Microphone (WH-1000XM4 Hands-Free AG Audio)' refused even with
allowed=('WH-1000',); empty list -> None.""",
        },
    },
    "round1": {
        "qwen3-coder-next-fp8": {
            "module": "app/journal.py",
            "test": "tests/test_journal.py",
            "spec": """Module: journal.py - the append-only event journal.
API: Journal(path) with .event(name, **fields) appending ONE json line
{ts, evt, **fields} (ts = ISO8601 with +03:00 offset). A CLOSED vocabulary:
VOCAB = frozenset of event names (SESSION_BEGIN, DEVICE_OPEN, SEG, DECODE,
TYPED, DROP, GATED, HEARTBEAT, STATE, WORKER_DIED, WORKER_RESPAWN, ALARM).
.event() with an unknown name raises JournalVocabError - a typo'd event name
must fail the writer, not vanish from dashboards. Concurrent-safe within one
process (a lock). File opened per-write (append), never held. Include a
rotate(max_bytes) that renames to .1 when exceeded - never deletes.
Reachability tests: unknown-name raises; a written line round-trips through
json.loads; rotation triggers at the boundary and the old file survives.""",
        },
        "glm-4.7-flash": {
            "module": "app/devicelaw.py",
            "test": "tests/test_devicelaw.py",
            "spec": """Module: devicelaw.py - which capture device is ALLOWED.
_NEVER_MIC = ("WH-1000", "Hands-Free", "Headset", "Bluetooth") as a SOURCE
LEVEL tuple - a function argument or config can never override it (no merge
logic anywhere). ALLOWED_SUBSTRINGS default ("BRIO", "Scarlett", "USBAudio").
API: choose_device(device_names: list[str], allowed=ALLOWED_SUBSTRINGS) ->
str | None. Returns the first name that matches allowed AND does not match
_NEVER_MIC (case-insensitive substring). None when nothing qualifies - the
caller must then journal IDLE_NO_MIC and open NOTHING (structural idle, not
an error). Also is_forbidden(name) -> bool. Reachability tests: a BRIO
passes; 'Microphone (WH-1000XM4 Hands-Free AG Audio)' is refused EVEN IF
allowed=('WH-1000',) is passed maliciously; empty list -> None.""",
        },
        "gpt-oss-120b": {
            "module": "app/spool.py",
            "test": "tests/test_spool.py",
            "spec": """Module: spool.py - write-ahead audio spool.
API: Spool(dir, max_records=500). .admit(rec_id, wav_bytes, meta: dict) ->
writes <rec_id>.wav and <rec_id>.json SIDECAR to disk FIRST, then registers
in memory; returns the paths. .complete(rec_id) removes from the pending
index (files stay - the archive is not the spool's to delete).
.evict_oldest() drops the OLDEST pending RECORD (keeps its files) and
returns its id - called when len(pending) > max_records. .pending() ->
ordered ids. .sweep() -> ids found on disk but not in memory (crash
recovery), and it must be O(new files): it reads ONLY sidecar files not yet
seen, never re-parses everything (a previous app stalled 15s per sidecar by
re-reading a whole journal). Every evict returns info the caller can
journal. Reachability tests: admit writes both files before returning;
evict_oldest never deletes files; sweep after simulated crash finds exactly
the orphaned ids; sweep twice reads no already-seen sidecar (track opens via
monkeypatched open counter).""",
        },
        "nemotron-3-super": {
            "module": "app/textguard.py",
            "test": "tests/test_textguard.py",
            "spec": """Module: textguard.py - is this decode real speech worth typing.
API: verdict(text: str, avg_logprob: float | None, lang: str | None) ->
tuple[bool, str] (ok, reason). Rules, in order:
1. empty/whitespace text -> (False, 'empty').
2. lang not in WHITELIST=('he','en') -> (False, 'lang') - and None is NOT a
   member: language must be a concrete value, None is unrepresentable.
3. avg_logprob is not None and avg_logprob < FLOOR -> (False, 'logprob').
   FLOOR = -0.6 (calibrated from 138 real decodes; -1.0 sat below the whole
   real distribution and never fired once - a floor nothing can reach is a
   dead guard).
4. text (stripped, casefolded) in HALLUCINATIONS frozenset -> (False,
   'hallucination'). Seed the set with the classic whisper ghosts: 'thank
   you.', 'thanks for watching!', 'you', subtitle-credit strings, and their
   Hebrew equivalents ('תודה רבה.', 'תודה שצפיתם').
5. otherwise (True, 'ok').
Reachability tests: EVERY branch fires on a realistic input, including a
logprob of -0.7 (must be caught - that is the point of the calibrated
floor) and a perfect -0.1 decode passing.""",
        },
    },
}


def build_prompt(worker: str, order: dict[str, str]) -> str:
    return (
        SCARS_CORE
        + f"\nYour module file: {order['module']}\nYour test file: {order['test']}\n\n"
        + order["spec"]
        + "\n\nRemember: exactly two python code blocks, module then tests, no prose."
    )


def call_router(model: str, prompt: str) -> str:
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 8000,
        "temperature": 0.2,
    }).encode()
    req = urllib.request.Request(
        ROUTER, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
        out = json.load(r)
    return out["choices"][0]["message"]["content"] or ""


CODE_RE = re.compile(r"```(?:python)?\s*\n(.*?)```", re.S)


def extract_two_blocks(reply: str) -> tuple[str, str] | None:
    blocks = CODE_RE.findall(reply)
    if len(blocks) < 2:
        return None
    return blocks[0], blocks[1]


def dispatch(round_name: str, only: str | None) -> int:
    orders = ORDERS[round_name]
    subs = ROOT / "submissions" / round_name
    subs.mkdir(parents=True, exist_ok=True)
    failures = 0
    for worker, order in orders.items():
        if only and worker != only:
            continue
        t0 = time.time()
        print(f"[{worker}] dispatching {order['module']} ...", flush=True)
        try:
            reply = call_router(worker, build_prompt(worker, order))
        except Exception as e:  # noqa: BLE001 - report and continue to next worker
            print(f"[{worker}] ROUTER ERROR: {e}")
            failures += 1
            continue
        raw = subs / f"{worker}.md"
        raw.write_text(reply, encoding="utf-8")
        module_only = round_name.startswith(("round3", "round4", "round5"))
        blocks = CODE_RE.findall(reply)
        if module_only:
            if not blocks:
                print(f"[{worker}] REJECT: no code block; raw at {raw}")
                failures += 1
                continue
            pair = (blocks[0], None)
        else:
            pair = extract_two_blocks(reply)
            if not pair:
                print(f"[{worker}] REJECT: reply had <2 code blocks "
                      f"({len(blocks)}); raw saved to {raw}")
                failures += 1
                continue
        mod_path = ROOT / order["module"]
        mod_path.parent.mkdir(parents=True, exist_ok=True)
        mod_path.write_text(pair[0], encoding="utf-8")
        if pair[1] is not None:
            # king's-canonical rounds never touch the test file
            test_path = ROOT / order["test"]
            test_path.parent.mkdir(parents=True, exist_ok=True)
            test_path.write_text(pair[1], encoding="utf-8")
        tests_part = f" + tests ({len(pair[1])}ch)" if pair[1] is not None else ""
        print(f"[{worker}] submitted {order['module']} "
              f"({len(pair[0])}ch){tests_part} in {time.time() - t0:.0f}s")
    return failures


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("round", choices=list(ORDERS))
    ap.add_argument("--only")
    a = ap.parse_args()
    return dispatch(a.round, a.only)


if __name__ == "__main__":
    sys.exit(main())
