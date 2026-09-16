"""K3 acceptance tests for client/telemetry.py — written FIRST (TDD).

PHASE2-DESIGN.md K3 row + section 8, scars 18/20 (PHASE1-INQUIRY.md section 2):

  * rotation ACTUALLY rotates at the size cap (files created, cap honored,
    at most 14 files retained — oldest deleted)
  * the event vocabulary is a CLOSED enum — an unknown event name raises
    TypeError; DEVICE_* is the one sanctioned prefix family
  * heartbeat lines carry the complete field set (queue depth / decode
    p50/p95 / engine state / rss / vram / drop counter) and PARSE back
    from both sinks
  * events.jsonl append is ATOMIC — concurrent writers never interleave
    a line (every line parses as complete JSON)
  * both sinks stay in step: same events, same order, same session id
  * every line carries a FULL ISO date with timezone (scar 20 — no more
    inferring days from midnight rollovers) and the session id
  * privacy: transcript text / window titles are unrepresentable — a
    `text=` / `title=` / `transcript=` field raises TypeError (section 8:
    lengths + logprobs only, EXE names never titles)
  * WORKER_KILL requires vram_before/vram_after (section 8 vocabulary)
  * SESSION_BEGIN / SESSION_END markers with session id (scar 20)
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
import threading
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from client.telemetry import (  # noqa: E402
    EVENT_VOCABULARY,
    HEARTBEAT_FIELDS,
    Telemetry,
    TelemetryFieldError,
    UnknownEventError,
)

ISO_FULL = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}[+-]\d{2}:\d{2}$"
)


class TelemetryCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.state = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def make(self, **kw) -> Telemetry:
        t = Telemetry(self.state, session_id="a3f9c2d1", **kw)
        self.addCleanup(t.close)
        return t

    # ------------------------------------------------------------ helpers

    def ledger_lines(self) -> list[dict]:
        p = self.state / "events.jsonl"
        return [json.loads(l) for l in p.read_text("utf-8").splitlines() if l]

    def log_files(self) -> list[Path]:
        return sorted((self.state / "logs").glob("mic-*.log*"))

    def human_lines(self) -> list[str]:
        out: list[str] = []
        for f in self.log_files():
            out.extend(f.read_text("utf-8").splitlines())
        return out

    # ---------------------------------------------------- closed vocabulary

    def test_unknown_event_raises_typeerror(self):
        t = self.make()
        with self.assertRaises(TypeError):
            t.event("TOTALLY_MADE_UP")
        # nothing was written by the refused event
        self.assertEqual(self.ledger_lines(), [])

    def test_unknown_event_error_is_typeerror_subclass(self):
        self.assertTrue(issubclass(UnknownEventError, TypeError))

    def test_every_vocabulary_event_accepted(self):
        t = self.make()
        required = {
            "WORKER_KILL": dict(vram_before=4200, vram_after=3100),
            "OWNER_REJ": dict(score=0.31, theta=0.62, mode="shadow", len_ms=1800),
            "TYPING_COLLISION": dict(action="held", wait_ms=1800),
        }
        for evt in sorted(EVENT_VOCABULARY):
            t.event(evt, **required.get(evt, {}))
        self.assertEqual(len(self.ledger_lines()), len(EVENT_VOCABULARY))

    def test_device_prefix_family_allowed(self):
        t = self.make()
        t.event("DEVICE_OPEN", name="Logitech BRIO")
        t.event("DEVICE_LOST")
        with self.assertRaises(TypeError):
            t.event("DEVICE")  # bare prefix is not an event

    def test_free_text_event_names_rejected(self):
        t = self.make()
        for bad in ("typed", "Typed", "TYPED ", "EVT", "device_open", ""):
            with self.assertRaises(TypeError):
                t.event(bad)

    def test_vocabulary_matches_design_section_8(self):
        design = {
            "SESSION_BEGIN", "SESSION_END", "STATE", "SEG", "GATED", "EMPTY",
            "DECODE", "TYPED", "DIVERTED", "SPILLED", "STALE_DIVERT",
            "GUARD_DROP", "LANG_DROP", "DUP_DISCARD", "TYPE_FAIL_PARKED",
            "FOCUS_BLOCK", "OWNER_REJ", "GATE_UNAVAILABLE", "PRESENCE_REJ",
            "ARM_ON", "ARM_OFF", "ARM_REJ",   # the arm switch (2026-08-17)
            "TYPING_COLLISION",               # hold-while-typing gate (08-17)
            "DEMOTE", "PROMOTE", "PLANNED_DEMOTION", "PIN_FLAKY", "UNPIN",
            "DEAF", "DEAF_DROP", "VRAM_DEGRADE", "LOCAL_UNAVAILABLE",
            "WORKER_KILL", "WORKER_RESPAWN", "BREAKER_TRIP", "UIPI_SELFTEST",
            "CONFIG_HALT", "DRILL_BEGIN", "DRILL_END",
            "ACCEPTANCE_BEGIN", "ACCEPTANCE_END", "HEARTBEAT",
        }
        self.assertEqual(EVENT_VOCABULARY, frozenset(design))

    # ------------------------------------------------------ required fields

    def test_worker_kill_requires_vram_fields(self):
        t = self.make()
        with self.assertRaises(TypeError):
            t.event("WORKER_KILL")
        with self.assertRaises(TypeError):
            t.event("WORKER_KILL", vram_before=4200)
        t.event("WORKER_KILL", vram_before=4200, vram_after=3100)  # ok

    def test_owner_rej_requires_score_fields(self):
        t = self.make()
        with self.assertRaises(TypeError):
            t.event("OWNER_REJ")
        t.event("OWNER_REJ", score=0.31, theta=0.62, mode="shadow", len_ms=1800)

    # ------------------------------------------------------------- privacy

    def test_transcript_and_title_fields_unrepresentable(self):
        t = self.make()
        for bad in ("text", "title", "transcript"):
            with self.assertRaises(TypeError):
                t.event("TYPED", **{bad: "secret words"})
        self.assertEqual(self.ledger_lines(), [])

    # ------------------------------------------------------------ two sinks

    def test_sinks_stay_in_step(self):
        t = self.make()
        t.event("SEG", seq="000001", ms=3200, rms=0.013)
        t.event("TYPED", seq="000001", eng="dgx", ms=812, lp=-0.35, len=42,
                exe="WindowsTerminal.exe")
        ledger = self.ledger_lines()
        human = self.human_lines()
        self.assertEqual(len(ledger), 2)
        self.assertEqual(len(human), 2)
        self.assertEqual([e["evt"] for e in ledger], ["SEG", "TYPED"])
        self.assertIn("evt=SEG", human[0])
        self.assertIn("evt=TYPED", human[1])
        for e in ledger:
            self.assertEqual(e["sid"], "a3f9c2d1")
        for line in human:
            self.assertIn("sid=a3f9c2d1", line)

    def test_full_iso_dates_with_timezone_everywhere(self):
        t = self.make()
        t.event("STATE", state="READY")
        ts = self.ledger_lines()[0]["ts"]
        self.assertRegex(ts, ISO_FULL)
        human_ts = self.human_lines()[0].split(" ", 1)[0]
        self.assertRegex(human_ts, ISO_FULL)

    def test_session_markers(self):
        t = self.make()
        t.session_begin(version="abc1234")
        t.session_end(reason="quit")
        evts = [e["evt"] for e in self.ledger_lines()]
        self.assertEqual(evts, ["SESSION_BEGIN", "SESSION_END"])
        self.assertTrue(all(e["sid"] == "a3f9c2d1" for e in self.ledger_lines()))

    # ------------------------------------------------------------ heartbeat

    def test_heartbeat_fields_complete_and_parse(self):
        t = self.make()
        t.heartbeat(q=0, spool_n=2, spool_mb=3.1, eng="dgx", state="READY",
                    p50=640, p95=1830, rss_mb=210, worker_rss_mb=1042,
                    worker_vram_mb=1010, drop_frames=0)
        entry = self.ledger_lines()[0]
        self.assertEqual(entry["evt"], "HEARTBEAT")
        for field in HEARTBEAT_FIELDS:
            self.assertIn(field, entry, f"heartbeat missing {field}")
        # human line parses back key=value
        line = self.human_lines()[0]
        self.assertIn("evt=HEARTBEAT", line)
        kv = dict(p.split("=", 1) for p in line.split(" ")[2:])
        for field in HEARTBEAT_FIELDS:
            self.assertIn(field, kv)
        self.assertEqual(kv["state"], "READY")
        self.assertEqual(int(kv["p50"]), 640)

    def test_heartbeat_missing_field_raises(self):
        t = self.make()
        with self.assertRaises(TypeError):
            t.heartbeat(q=0, spool_n=0, spool_mb=0, eng="dgx", state="READY",
                        p50=1, p95=2, rss_mb=3, worker_rss_mb=4,
                        worker_vram_mb=5)  # drop_frames missing

    def test_heartbeat_loop_fires(self):
        t = self.make()
        stats = dict(q=0, spool_n=0, spool_mb=0.0, eng="local",
                     state="DEGRADED", p50=900, p95=2100, rss_mb=200,
                     worker_rss_mb=1000, worker_vram_mb=1000, drop_frames=0)
        fired = threading.Event()

        def stats_fn():
            fired.set()
            return stats

        t.start_heartbeat(stats_fn, interval_s=0.05)
        self.assertTrue(fired.wait(2.0), "heartbeat loop never called stats_fn")
        t.stop_heartbeat()
        beats = [e for e in self.ledger_lines() if e["evt"] == "HEARTBEAT"]
        self.assertGreaterEqual(len(beats), 1)
        self.assertEqual(beats[0]["state"], "DEGRADED")

    # ------------------------------------------------------------- rotation

    def test_rotation_rotates_at_size_cap(self):
        t = self.make(max_bytes=4096)
        for i in range(200):
            t.event("SEG", seq=f"{i:06d}", ms=3200, rms=0.0131, note="x" * 40)
        files = self.log_files()
        self.assertGreater(len(files), 1, "size cap never triggered a rotation")
        for f in files:
            self.assertLessEqual(f.stat().st_size, 4096 + 512,
                                 f"{f.name} grew past the cap")
        # nothing lost across rotation: all 200 events present across files
        seg_lines = [l for l in self.human_lines() if "evt=SEG" in l]
        self.assertEqual(len(seg_lines), 200)

    def test_rotation_retains_at_most_backup_count(self):
        t = self.make(max_bytes=512, backups=3)
        for i in range(400):
            t.event("SEG", seq=f"{i:06d}", ms=1, rms=0.01)
        self.assertLessEqual(len(self.log_files()), 3)

    def test_default_cap_is_10mb_x14(self):
        t = self.make()
        self.assertEqual(t.max_bytes, 10 * 1024 * 1024)
        self.assertEqual(t.backups, 14)

    def test_log_filename_carries_full_date(self):
        t = self.make()
        t.event("STATE", state="READY")
        names = [f.name for f in self.log_files()]
        self.assertTrue(any(re.match(r"mic-\d{8}\.log$", n) for n in names),
                        names)

    # -------------------------------------------------------- atomic ledger

    def test_ledger_append_is_atomic_under_concurrency(self):
        t = self.make()
        n_threads, per_thread = 8, 100

        def hammer(tid: int) -> None:
            for i in range(per_thread):
                t.event("DECODE", seq=f"{tid}-{i:04d}", eng="dgx", ms=100)

        threads = [threading.Thread(target=hammer, args=(k,))
                   for k in range(n_threads)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()
        raw = (self.state / "events.jsonl").read_text("utf-8")
        lines = [l for l in raw.splitlines() if l]
        self.assertEqual(len(lines), n_threads * per_thread)
        seqs = set()
        for l in lines:
            entry = json.loads(l)  # any torn/interleaved line explodes here
            self.assertEqual(entry["evt"], "DECODE")
            seqs.add(entry["seq"])
        self.assertEqual(len(seqs), n_threads * per_thread)

    def test_ledger_survives_reopen(self):
        t = Telemetry(self.state, session_id="s1")
        t.event("STATE", state="READY")
        t.close()
        t2 = Telemetry(self.state, session_id="s2")
        self.addCleanup(t2.close)
        t2.event("STATE", state="READY")
        entries = self.ledger_lines()
        self.assertEqual(len(entries), 2)
        self.assertEqual([e["sid"] for e in entries], ["s1", "s2"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
