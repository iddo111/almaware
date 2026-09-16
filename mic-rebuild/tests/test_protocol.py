"""K10 acceptance tests for common/protocol.py — written FIRST (TDD).

PHASE2-DESIGN.md section 3 (API CONTRACT) — the ONE wire spec shared
client<->server (section 2: common/ is the single source of truth):

  * request-id format `<session8hex>-<seq:06d>` (scar 53 — THE dedup key):
    make/validate round-trip, malformed forms rejected
  * HTTP contract constants match the design verbatim: port 8737,
    /v1/transcribe, raw-PCM content type, 960,000-byte (30s) body cap,
    header names, DGX deadline 6s / local 10s (section 3.2 budget check:
    6s + ~2s local < the 10s ceiling of criterion 2)
  * worker IPC framing `4-byte LE length | UTF-8 JSON header | raw PCM
    payload` (section 3.2): golden vectors, round-trip with and without
    payload, EOF -> None, garbage length rejected
  * EVERY frame carries "gen" (scar 10 promoted to the process boundary) —
    pack_frame REFUSES a genless header
"""
from __future__ import annotations

import io
import struct
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from common import protocol  # noqa: E402


class TestRequestId(unittest.TestCase):
    def test_make_and_validate_round_trip(self):
        rid = protocol.make_request_id("a3f9c2d1", 123)
        self.assertEqual(rid, "a3f9c2d1-000123")
        self.assertTrue(protocol.valid_request_id(rid))

    def test_seq_wraps_are_not_silently_truncated(self):
        # 6-digit field; a 7-digit seq must still be a VALID unique id,
        # not a collision — the format widens rather than wraps.
        rid = protocol.make_request_id("a3f9c2d1", 1234567)
        self.assertTrue(rid.startswith("a3f9c2d1-"))
        self.assertNotEqual(rid, protocol.make_request_id("a3f9c2d1", 234567))

    def test_malformed_ids_rejected(self):
        bad = [
            "", "x", "a3f9c2d1", "a3f9c2d1-", "-000123",
            "A3F9C2D1-000123",          # uppercase hex — format is lowercase
            "a3f9c2d-000123",           # 7-hex session
            "a3f9c2d12-000123",         # 9-hex session
            "a3f9c2d1-00123",           # 5-digit seq
            "a3f9c2d1-0001235-",        # trailing junk
            "a3f9c2d1 000123",          # wrong separator
            "a3f9c2d1-00012g",          # non-digit seq
            None, 123,
        ]
        for b in bad:
            with self.subTest(bad=b):
                self.assertFalse(protocol.valid_request_id(b))

    def test_session_must_be_8_hex(self):
        with self.assertRaises(ValueError):
            protocol.make_request_id("nothexxx", 1)
        with self.assertRaises(ValueError):
            protocol.make_request_id("abcd", 1)


class TestHttpContractConstants(unittest.TestCase):
    """The design's numbers are LAW — a drive-by 'tune' must fail a test."""

    def test_port_and_paths(self):
        self.assertEqual(protocol.PORT, 8737)
        self.assertEqual(protocol.PATH_TRANSCRIBE, "/v1/transcribe")
        self.assertEqual(protocol.PATH_HEALTH, "/health")
        self.assertEqual(protocol.PATH_METRICS, "/metrics")
        self.assertEqual(protocol.PATH_DRAIN, "/admin/drain")
        self.assertEqual(protocol.PATH_UNDRAIN, "/admin/undrain")

    def test_pcm_contract(self):
        self.assertEqual(
            protocol.CONTENT_TYPE_PCM,
            "audio/pcm;rate=16000;encoding=s16le;channels=1")
        self.assertEqual(protocol.SAMPLE_RATE, 16000)
        # 30s * 16000 samples * 2 bytes
        self.assertEqual(protocol.MAX_BODY_BYTES, 960_000)

    def test_header_names(self):
        self.assertEqual(protocol.HDR_REQUEST_ID, "X-Request-Id")
        self.assertEqual(protocol.HDR_AUDIO_DURATION_MS, "X-Audio-Duration-Ms")
        self.assertEqual(protocol.HDR_LANG_HINT, "X-Lang-Hint")
        self.assertEqual(protocol.LANG_HINTS, ("auto", "he", "en"))

    def test_deadlines_fit_criterion_2_budget(self):
        self.assertEqual(protocol.DGX_DEADLINE_S, 6.0)
        self.assertEqual(protocol.LOCAL_DEADLINE_S, 10.0)
        self.assertEqual(protocol.SERVER_DECODE_WALL_S, 15.0)
        # section 3.2 budget check: worst-case failover 6s DGX + ~2s local < 10s
        self.assertLess(protocol.DGX_DEADLINE_S + 2.0, 10.0)

    def test_server_side_limits(self):
        self.assertEqual(protocol.INFLIGHT_CAP, 2)
        self.assertEqual(protocol.CANARY_INTERVAL_S, 300)
        self.assertEqual(protocol.CANARY_STALE_S, 900)


class TestIpcFraming(unittest.TestCase):
    def test_golden_vector_no_payload(self):
        frame = protocol.pack_frame({"gen": 1, "cmd": "ping"})
        n = struct.unpack("<I", frame[:4])[0]
        hdr = frame[4:4 + n]
        self.assertEqual(len(frame), 4 + n)
        import json
        # n_bytes is auto-filled by pack (the payload length lives in the header)
        self.assertEqual(json.loads(hdr.decode("utf-8")),
                         {"gen": 1, "cmd": "ping", "n_bytes": 0})

    def test_round_trip_with_pcm_payload(self):
        pcm = bytes(range(256)) * 4
        frame = protocol.pack_frame(
            {"gen": 7, "cmd": "decode", "id": "a3f9c2d1-000123",
             "engine": "dgx", "lang_hint": "auto", "deadline_ms": 6000},
            payload=pcm)
        hdr, payload = protocol.read_frame(io.BytesIO(frame))
        self.assertEqual(hdr["id"], "a3f9c2d1-000123")
        self.assertEqual(hdr["gen"], 7)
        self.assertEqual(hdr["n_bytes"], len(pcm))  # auto-filled by pack
        self.assertEqual(payload, pcm)

    def test_round_trip_no_payload(self):
        frame = protocol.pack_frame({"gen": 3, "event": "pong", "rss_mb": 1042})
        hdr, payload = protocol.read_frame(io.BytesIO(frame))
        self.assertEqual(hdr["event"], "pong")
        self.assertEqual(payload, b"")

    def test_two_frames_back_to_back(self):
        buf = io.BytesIO(
            protocol.pack_frame({"gen": 1, "cmd": "ping"})
            + protocol.pack_frame({"gen": 1, "cmd": "decode"}, payload=b"\x01\x02"))
        h1, p1 = protocol.read_frame(buf)
        h2, p2 = protocol.read_frame(buf)
        self.assertEqual(h1["cmd"], "ping")
        self.assertEqual(h2["cmd"], "decode")
        self.assertEqual(p2, b"\x01\x02")

    def test_eof_returns_none(self):
        self.assertIsNone(protocol.read_frame(io.BytesIO(b"")))

    def test_truncated_frame_raises(self):
        good = protocol.pack_frame({"gen": 1, "cmd": "decode"}, payload=b"abcdef")
        for cut in (2, 5, len(good) - 3):
            with self.subTest(cut=cut):
                with self.assertRaises(protocol.FrameError):
                    protocol.read_frame(io.BytesIO(good[:cut]))

    def test_garbage_length_rejected(self):
        # a frame claiming a 512MB JSON header is corruption, not a header
        with self.assertRaises(protocol.FrameError):
            protocol.read_frame(io.BytesIO(struct.pack("<I", 512 * 1024 * 1024) + b"x"))

    def test_every_frame_must_carry_gen(self):
        # scar 10 at the process boundary: a genless frame is unrepresentable
        with self.assertRaises(protocol.FrameError):
            protocol.pack_frame({"cmd": "ping"})

    def test_payload_length_mismatch_refused(self):
        # an n_bytes lying about the payload is a corrupt frame at PACK time
        with self.assertRaises(protocol.FrameError):
            protocol.pack_frame({"gen": 1, "cmd": "decode", "n_bytes": 999},
                                payload=b"abc")


if __name__ == "__main__":
    unittest.main(verbosity=2)
