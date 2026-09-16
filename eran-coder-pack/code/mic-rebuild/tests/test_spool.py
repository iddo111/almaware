"""K8 TDD tests — client/spool.py (PHASE2-DESIGN.md section 2 spool.py row,
section 4.1 router pseudocode, section 4.4 lifecycle ledger; PHASE1-INQUIRY.md
scars 16/17, criterion 4).

THE mechanism under test: the spool directory is the ring buffer, the spill
AND the recovery, in one:

  * WRITE-AHEAD: every segment is on disk BEFORE any queue record exists —
    a crash between write and enqueue loses nothing (proven here with a real
    TerminateProcess kill between the two calls, in a subprocess).
  * EVICT-OLDEST drops the in-memory record ONLY — the file stays (scar 17:
    divert, don't drop; the evicted segment rides the recovery lane).
  * FRESH/STALE routing: fresh (age <= stale_sec) goes to the live path;
    stale is decoded but diverted to recovered.txt, NEVER the live typer
    (scar 16 — the 16<->17 contradiction resolution).
  * GC deletes a file only after a TERMINAL outcome is journaled + retention.

Criterion 4's "zero words lost counting both destinations" is proven
standalone with a null decoder. The "3 real reboots <= 10s to CAPTURING"
half of criterion 4 is DEFERRED to the live phase (wave guardrail: no boot
layer, no real devices) — it is NOT claimed here.

No audio device, no network, no alma-mic: pure files + synthetic PCM.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest
import wave
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from client.spool import (  # noqa: E402
    OUTCOME_VOCABULARY,
    RETENTION_S_DEFAULT,
    SPOOL_CAPACITY,
    TERMINAL_OUTCOMES,
    RecoveredTranscript,
    Spool,
    SpoolRecord,
    UnknownOutcomeError,
    is_stale,
)

RATE = 16000


def pcm_s16(n_samples: int = 1600, value: int = 1000) -> bytes:
    """Deterministic little s16le payload (0.1s @ 16k by default)."""
    return value.to_bytes(2, "little", signed=True) * n_samples


def make_spool(tmp: Path, **kw) -> Spool:
    return Spool(tmp / "spool", **kw)


def write_one(spool: Spool, seg_id: str, *, t_end: float | None = None,
              pcm: bytes | None = None) -> SpoolRecord:
    t = time.time() if t_end is None else t_end
    return spool.write_ahead(
        pcm if pcm is not None else pcm_s16(),
        seg_id=seg_id, t_start=t - 1.0, t_end=t,
        duration_ms=1000, rms_raw=0.01, gain=1.0,
    )


class CapacityAndOrder(unittest.TestCase):
    def test_capacity_constant_is_the_design_value(self):
        self.assertEqual(SPOOL_CAPACITY, 50)          # design sec 2: deque(50)
        self.assertEqual(RETENTION_S_DEFAULT, 3600)   # design sec 4.4: 1h retention

    def test_write_ahead_puts_file_on_disk_before_any_queue_record(self):
        """THE write-ahead law: after write_ahead() the WAV + sidecar exist
        and are complete, while the queue is still EMPTY."""
        with tempfile.TemporaryDirectory() as td:
            spool = make_spool(Path(td))
            rec = write_one(spool, "a3f9c2d1-000001", pcm=pcm_s16(3200, 777))
            # file reality first
            self.assertTrue(rec.wav_path.is_file())
            self.assertTrue(rec.sidecar_path.is_file())
            with wave.open(str(rec.wav_path), "rb") as w:
                self.assertEqual(w.getframerate(), RATE)
                self.assertEqual(w.getnchannels(), 1)
                self.assertEqual(w.getsampwidth(), 2)
                self.assertEqual(w.readframes(w.getnframes()), pcm_s16(3200, 777))
            side = json.loads(rec.sidecar_path.read_text(encoding="utf-8"))
            self.assertEqual(side["id"], "a3f9c2d1-000001")
            self.assertEqual(side["duration_ms"], 1000)
            # queue emptiness second — write_ahead NEVER enqueues
            self.assertEqual(spool.qsize(), 0)
            self.assertIsNone(spool.pop(timeout=0))

    def test_enqueue_then_pop_is_fifo(self):
        with tempfile.TemporaryDirectory() as td:
            spool = make_spool(Path(td))
            ids = [f"a3f9c2d1-{i:06d}" for i in range(1, 4)]
            for sid in ids:
                spool.enqueue(write_one(spool, sid))
            self.assertEqual(spool.qsize(), 3)
            popped = [spool.pop(timeout=0).id for _ in ids]
            self.assertEqual(popped, ids)
            self.assertIsNone(spool.pop(timeout=0))

    def test_pop_timeout_blocks_then_returns_none(self):
        with tempfile.TemporaryDirectory() as td:
            spool = make_spool(Path(td))
            t0 = time.monotonic()
            self.assertIsNone(spool.pop(timeout=0.2))
            self.assertGreaterEqual(time.monotonic() - t0, 0.15)

    def test_pop_wakes_on_concurrent_enqueue(self):
        with tempfile.TemporaryDirectory() as td:
            spool = make_spool(Path(td))
            got: list = []

            def consumer():
                got.append(spool.pop(timeout=5.0))

            th = threading.Thread(target=consumer)
            th.start()
            time.sleep(0.1)
            spool.enqueue(write_one(spool, "a3f9c2d1-000009"))
            th.join(timeout=5)
            self.assertFalse(th.is_alive())
            self.assertEqual(got[0].id, "a3f9c2d1-000009")

    def test_evict_oldest_drops_record_only_file_stays(self):
        """Scar 17: evict-oldest on full — the FILE STAYS (recovery lane),
        a SPILLED event is emitted, the newest record is present."""
        events: list = []
        with tempfile.TemporaryDirectory() as td:
            spool = make_spool(Path(td), capacity=5,
                               on_event=lambda evt, **f: events.append((evt, f)))
            recs = []
            for i in range(1, 7):   # 6 into capacity 5
                r = write_one(spool, f"a3f9c2d1-{i:06d}")
                spool.enqueue(r)
                recs.append(r)
            self.assertEqual(spool.qsize(), 5)
            queued = [spool.pop(timeout=0).id for _ in range(5)]
            self.assertEqual(queued, [r.id for r in recs[1:]])   # oldest evicted
            # THE law: evicted record's file is still on disk
            self.assertTrue(recs[0].wav_path.is_file())
            self.assertTrue(recs[0].sidecar_path.is_file())
            spilled = [f for evt, f in events if evt == "SPILLED"]
            self.assertEqual(len(spilled), 1)
            self.assertEqual(spilled[0]["id"], recs[0].id)
            # and the evicted id is NOT terminal -> it will be recovered
            self.assertIn(recs[0].id, {r.id for r in spool.orphans()})


class JournalAndGC(unittest.TestCase):
    def test_outcome_vocabulary_is_closed(self):
        with tempfile.TemporaryDirectory() as td:
            spool = make_spool(Path(td))
            rec = write_one(spool, "a3f9c2d1-000001")
            with self.assertRaises(UnknownOutcomeError):
                spool.journal_outcome(rec.id, "SHIPPED")   # not a KESHEV outcome
            self.assertIn("TYPED", TERMINAL_OUTCOMES)
            self.assertIn("RECOVERED", TERMINAL_OUTCOMES)
            self.assertNotIn("SPILLED", TERMINAL_OUTCOMES)  # spilled stays live
            self.assertTrue(TERMINAL_OUTCOMES <= OUTCOME_VOCABULARY)

    def test_journal_appends_jsonl(self):
        with tempfile.TemporaryDirectory() as td:
            spool = make_spool(Path(td))
            rec = write_one(spool, "a3f9c2d1-000001")
            spool.journal_outcome(rec.id, "TYPED")
            spool.journal_outcome(rec.id, "RECOVERED")
            lines = [json.loads(l) for l in
                     spool.journal_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual([l["outcome"] for l in lines], ["TYPED", "RECOVERED"])
            for l in lines:
                self.assertEqual(l["id"], rec.id)
                self.assertIn("ts", l)

    def test_gc_refuses_without_terminal_outcome(self):
        with tempfile.TemporaryDirectory() as td:
            spool = make_spool(Path(td))
            rec = write_one(spool, "a3f9c2d1-000001")
            self.assertFalse(spool.gc(rec.id))
            self.assertTrue(rec.wav_path.is_file())

    def test_gc_respects_retention_then_deletes(self):
        now = [1000.0]
        with tempfile.TemporaryDirectory() as td:
            spool = make_spool(Path(td), retention_s=3600, now_fn=lambda: now[0])
            rec = write_one(spool, "a3f9c2d1-000001", t_end=now[0])
            spool.journal_outcome(rec.id, "TYPED")
            self.assertFalse(spool.gc(rec.id))          # inside retention
            self.assertTrue(rec.wav_path.is_file())
            now[0] += 3601
            self.assertTrue(spool.gc(rec.id))            # retention elapsed
            self.assertFalse(rec.wav_path.exists())
            self.assertFalse(rec.sidecar_path.exists())

    def test_sweep_deletes_only_eligible(self):
        now = [1000.0]
        with tempfile.TemporaryDirectory() as td:
            spool = make_spool(Path(td), retention_s=100, now_fn=lambda: now[0])
            done = write_one(spool, "a3f9c2d1-000001", t_end=now[0])
            live = write_one(spool, "a3f9c2d1-000002", t_end=now[0])
            spool.journal_outcome(done.id, "TYPED")
            now[0] += 101
            removed = spool.sweep()
            self.assertEqual(removed, [done.id])
            self.assertFalse(done.wav_path.exists())
            self.assertTrue(live.wav_path.is_file())     # non-terminal: kept


class TerminalIndexCacheTests(unittest.TestCase):
    """The 15-second-stall scar (2026-08-18, measured live).

    events.jsonl showed SEG->DECODE spiking 13-26 s once a MINUTE while
    DECODE itself stayed ~0.4 s. Cause: _terminal_index() re-read and
    re-parsed the whole journal from disk on every call, and sweep() calls
    gc() once per sidecar — O(files x journal-lines) inside the router
    thread. On the live pile: 522 sidecars x 49 ms/scan = 25.6 s with the
    router blocked, every SWEEP_INTERVAL_S. The fix is an in-memory index
    seeded from disk at most once per process and kept current by
    journal_outcome(); these tests pin the disk-scan count itself, not a
    wall clock, so they cannot flake on a slow machine."""

    def test_sweep_parses_journal_from_disk_at_most_once(self):
        now = [1000.0]
        with tempfile.TemporaryDirectory() as td:
            spool = make_spool(Path(td), retention_s=100, now_fn=lambda: now[0])
            recs = [write_one(spool, f"a3f9c2d1-{i:06d}", t_end=now[0])
                    for i in range(1, 41)]
            for rec in recs:
                spool.journal_outcome(rec.id, "TYPED")
            now[0] += 101
            removed = spool.sweep()
            self.assertEqual(len(removed), 40)
            self.assertEqual(spool.journal_disk_scans, 1)   # was 40+ pre-fix
            spool.sweep()                                   # second pass
            self.assertEqual(spool.journal_disk_scans, 1)   # cache reused

    def test_outcome_after_seed_updates_cache_without_rescan(self):
        now = [1000.0]
        with tempfile.TemporaryDirectory() as td:
            spool = make_spool(Path(td), retention_s=100, now_fn=lambda: now[0])
            spool.orphans()                                 # seeds the cache
            self.assertEqual(spool.journal_disk_scans, 1)
            rec = write_one(spool, "a3f9c2d1-000001", t_end=now[0])
            spool.journal_outcome(rec.id, "TYPED")          # cache updated live
            now[0] += 101
            self.assertTrue(spool.gc(rec.id))
            self.assertFalse(rec.wav_path.exists())
            self.assertEqual(spool.journal_disk_scans, 1)   # never re-read

    def test_fresh_instance_seeds_from_disk_truth(self):
        # The journal on disk stays the durable truth: a new process (crash,
        # restart) must see outcomes an earlier instance journaled.
        with tempfile.TemporaryDirectory() as td:
            a = make_spool(Path(td), retention_s=0,
                           now_fn=lambda: 10.0 ** 9)
            rec = write_one(a, "a3f9c2d1-000001", t_end=1000.0)
            a.journal_outcome(rec.id, "TYPED")
            b = Spool(a.spool_dir, retention_s=0, now_fn=lambda: 10.0 ** 9)
            self.assertTrue(b.gc(rec.id))                   # seeded from disk
            self.assertEqual(b.journal_disk_scans, 1)

    def test_spilled_never_marks_terminal_in_cache(self):
        # SPILLED is journaled but NOT terminal — the segment is still owed
        # via the recovery lane; the cache must agree with the vocabulary.
        with tempfile.TemporaryDirectory() as td:
            spool = make_spool(Path(td), retention_s=0,
                               now_fn=lambda: 10.0 ** 9)
            spool.orphans()                                 # seed first
            rec = write_one(spool, "a3f9c2d1-000001", t_end=1000.0)
            spool.journal_outcome(rec.id, "SPILLED")
            self.assertFalse(spool.gc(rec.id))              # not terminal
            self.assertTrue(rec.wav_path.is_file())
            self.assertEqual([r.id for r in spool.orphans()], [rec.id])

    def test_sweep_of_tonights_shape_is_fast(self):
        # The live shape that stalled: hundreds of sidecars, thousands of
        # journal lines. Pre-fix this sweep re-parsed the journal once PER
        # sidecar (~6 s at this size, 25.6 s at the real 522x13337); the
        # generous 2 s bound only fails if that O(files x lines) behavior
        # comes back.
        now = [1000.0]
        with tempfile.TemporaryDirectory() as td:
            spool = make_spool(Path(td), retention_s=100, now_fn=lambda: now[0])
            recs = [write_one(spool, f"a3f9c2d1-{i:06d}", t_end=now[0])
                    for i in range(1, 301)]
            with open(spool.journal_path, "a", encoding="utf-8") as fh:
                for i in range(6000):                       # bulk history
                    fh.write(json.dumps({
                        "ts": 900.0, "iso": "epoch:900",
                        "id": f"deadbeef-{i:06d}", "outcome": "TYPED",
                    }) + "\n")
                for rec in recs:                            # tonight's pile
                    fh.write(json.dumps({
                        "ts": now[0], "iso": f"epoch:{now[0]:g}",
                        "id": rec.id, "outcome": "TYPED",
                    }) + "\n")
            now[0] += 101
            t0 = time.perf_counter()
            removed = spool.sweep()
            elapsed = time.perf_counter() - t0
            self.assertEqual(len(removed), 300)
            self.assertLess(elapsed, 2.0)
            self.assertEqual(spool.journal_disk_scans, 1)


class Recovery(unittest.TestCase):
    def test_orphans_are_nonterminal_files_sorted_by_time(self):
        with tempfile.TemporaryDirectory() as td:
            spool = make_spool(Path(td))
            r2 = write_one(spool, "a3f9c2d1-000002", t_end=200.0)
            r1 = write_one(spool, "a3f9c2d1-000001", t_end=100.0)
            r3 = write_one(spool, "a3f9c2d1-000003", t_end=300.0)
            spool.journal_outcome(r3.id, "TYPED")        # terminal -> excluded
            # a fresh Spool over the same directory (post-crash view)
            fresh = Spool(spool.spool_dir)
            orphan_ids = [r.id for r in fresh.orphans()]
            self.assertEqual(orphan_ids, [r1.id, r2.id])

    def test_orphan_record_round_trips_pcm(self):
        with tempfile.TemporaryDirectory() as td:
            spool = make_spool(Path(td))
            body = pcm_s16(4800, -1234)
            write_one(spool, "a3f9c2d1-000001", pcm=body)
            fresh = Spool(spool.spool_dir)
            (rec,) = fresh.orphans()
            self.assertEqual(rec.read_pcm(), body)

    def test_queued_records_are_not_orphans(self):
        with tempfile.TemporaryDirectory() as td:
            spool = make_spool(Path(td))
            spool.enqueue(write_one(spool, "a3f9c2d1-000001"))
            self.assertEqual(spool.orphans(), [])


class FreshStaleRouting(unittest.TestCase):
    """Scar 16 — the ONE fresh/stale gate (design sec 4.1)."""

    def test_fresh_routes_live_stale_routes_recovered(self):
        rec_fresh = SpoolRecord(id="a", wav_path=Path("x"), sidecar_path=Path("y"),
                                t_start=0.0, t_end=100.0, duration_ms=1000)
        rec_stale = SpoolRecord(id="b", wav_path=Path("x"), sidecar_path=Path("y"),
                                t_start=0.0, t_end=100.0, duration_ms=1000)
        self.assertFalse(is_stale(rec_fresh, stale_sec=25, now=125.0))   # == 25s: fresh
        self.assertTrue(is_stale(rec_stale, stale_sec=25, now=125.1))    # > 25s: stale

    def test_recovered_transcript_appends_and_takes_hebrew(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "recovered.txt"
            rt = RecoveredTranscript(path)
            rt.append("a3f9c2d1-000001", "שלום עולם", age_s=42.0)
            rt.append("a3f9c2d1-000002", "flying corals", age_s=99.9)
            text = path.read_text(encoding="utf-8")
            lines = text.splitlines()
            self.assertEqual(len(lines), 2)
            self.assertIn("שלום עולם", lines[0])
            self.assertIn("a3f9c2d1-000001", lines[0])
            self.assertIn("+42s", lines[0])
            self.assertIn("flying corals", lines[1])


class CrashInjection(unittest.TestCase):
    """The K8 headline: a REAL hard kill between write-ahead and enqueue
    loses nothing. TerminateProcess (proc.kill) is the Windows kill -9."""

    def _run_child(self, script: str, td: str) -> subprocess.Popen:
        child = Path(td) / "child.py"
        child.write_text(textwrap.dedent(script), encoding="utf-8")
        env = dict(os.environ, PYTHONPATH=str(REPO), PYTHONIOENCODING="utf-8")
        return subprocess.Popen(
            [sys.executable, str(child), td],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", env=env,
        )

    def test_kill_between_write_and_enqueue_loses_nothing(self):
        script = """
            import sys, time
            from pathlib import Path
            from client.spool import Spool
            td = Path(sys.argv[1])
            spool = Spool(td / "spool")
            pcm = (777).to_bytes(2, "little", signed=True) * 1600
            spool.write_ahead(pcm, seg_id="a3f9c2d1-000042", t_start=1.0,
                              t_end=2.0, duration_ms=100, rms_raw=0.01, gain=1.0)
            print("WROTE", flush=True)
            time.sleep(60)          # the crash window: written, NOT enqueued
            spool.enqueue           # (never reached)
        """
        with tempfile.TemporaryDirectory() as td:
            proc = self._run_child(script, td)
            try:
                line = proc.stdout.readline().strip()
                self.assertEqual(line, "WROTE")
                proc.kill()                              # hard kill in the window
                proc.wait(timeout=10)
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait(timeout=10)
            # recovery view: the segment is there, intact
            spool = Spool(Path(td) / "spool")
            orphans = spool.orphans()
            self.assertEqual([r.id for r in orphans], ["a3f9c2d1-000042"])
            self.assertEqual(orphans[0].read_pcm(),
                             (777).to_bytes(2, "little", signed=True) * 1600)

    def test_kill_mid_pipeline_recovers_exactly_the_unfinished(self):
        """5 segments written+enqueued, 2 journaled TYPED, then hard kill:
        recovery must surface exactly the 3 unfinished — no more, no less."""
        script = """
            import sys, time
            from pathlib import Path
            from client.spool import Spool
            td = Path(sys.argv[1])
            spool = Spool(td / "spool")
            pcm = (5).to_bytes(2, "little", signed=True) * 800
            for i in range(1, 6):
                rec = spool.write_ahead(pcm, seg_id=f"a3f9c2d1-{i:06d}",
                                        t_start=float(i), t_end=float(i) + 1,
                                        duration_ms=50, rms_raw=0.01, gain=1.0)
                spool.enqueue(rec)
            for i in (1, 2):
                spool.journal_outcome(f"a3f9c2d1-{i:06d}", "TYPED")
            print("STAGED", flush=True)
            time.sleep(60)          # crash before 3..5 reach any outcome
        """
        with tempfile.TemporaryDirectory() as td:
            proc = self._run_child(script, td)
            try:
                self.assertEqual(proc.stdout.readline().strip(), "STAGED")
                proc.kill()
                proc.wait(timeout=10)
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait(timeout=10)
            spool = Spool(Path(td) / "spool")
            self.assertEqual([r.id for r in spool.orphans()],
                             [f"a3f9c2d1-{i:06d}" for i in (3, 4, 5)])


class NullDecoder:
    """Criterion-4 stand-in engine: deterministic marker text per id."""

    def __call__(self, rec: SpoolRecord) -> str:
        return f"<decoded:{rec.id}>"


class Criterion4NullDecoder(unittest.TestCase):
    """Criterion 4 (standalone, null decoder): speech spoken while the
    recognizer is unavailable reaches the user — fresh segments to the live
    path, stale backlog to recovered.txt — ZERO words lost counting BOTH
    destinations, and NO stale segment on the live path (scar 16).

    (The criterion's reboot-timing half — 3 real reboots, <=10s to
    CAPTURING — is deferred to the live phase; not claimed by this test.)
    """

    def test_zero_lost_counting_both_destinations(self):
        events: list = []
        now = [10_000.0]
        with tempfile.TemporaryDirectory() as td:
            spool = Spool(Path(td) / "spool", now_fn=lambda: now[0],
                          on_event=lambda evt, **f: events.append((evt, f)))
            recovered = RecoveredTranscript(Path(td) / "recovered.txt")
            decode = NullDecoder()

            # --- warm-up outage: 8 segments arrive while nothing decodes.
            # 3 old ones (already >25s when the engine comes up) + 5 fresh.
            all_ids = []
            for i in range(1, 4):     # stale-to-be: captured 40s before drain
                rec = write_one(spool, f"a3f9c2d1-{i:06d}", t_end=now[0] - 40)
                spool.enqueue(rec)
                all_ids.append(rec.id)
            for i in range(4, 9):     # fresh: captured 1s before drain
                rec = write_one(spool, f"a3f9c2d1-{i:06d}", t_end=now[0] - 1)
                spool.enqueue(rec)
                all_ids.append(rec.id)

            # --- engine up: the router drain (design sec 4.1, null decoder)
            live: list[tuple[str, str]] = []
            while (rec := spool.pop(timeout=0)) is not None:
                text = decode(rec)                     # stale is still decoded…
                if is_stale(rec, stale_sec=25, now=now[0]):
                    recovered.append(rec.id, text, age_s=now[0] - rec.t_end)
                    spool.journal_outcome(rec.id, "RECOVERED")
                    spool.emit("STALE_DIVERT", id=rec.id)
                else:
                    live.append((rec.id, text))        # …but only fresh types
                    spool.journal_outcome(rec.id, "TYPED")

            # ZERO lost counting both destinations
            rec_text = (Path(td) / "recovered.txt").read_text(encoding="utf-8")
            live_ids = [i for i, _ in live]
            recovered_ids = [i for i in all_ids if i in rec_text]
            self.assertEqual(sorted(live_ids + recovered_ids), all_ids)
            self.assertEqual(len(live_ids) + len(recovered_ids), 8)
            # NO stale segment on the live path
            self.assertEqual(live_ids, [f"a3f9c2d1-{i:06d}" for i in range(4, 9)])
            # every diversion left a line (scar 18)
            stale_events = [f["id"] for evt, f in events if evt == "STALE_DIVERT"]
            self.assertEqual(stale_events, [f"a3f9c2d1-{i:06d}" for i in (1, 2, 3)])
            # every id reached a terminal outcome -> spool is GC-eligible later
            self.assertEqual(spool.orphans(), [])


class TelemetryIntegration(unittest.TestCase):
    def test_spool_events_land_in_real_telemetry_ledger(self):
        """The on_event wiring speaks the CLOSED K3 vocabulary — a spool
        eviction must land in events.jsonl without UnknownEventError."""
        from client.telemetry import Telemetry
        with tempfile.TemporaryDirectory() as td:
            tel = Telemetry(Path(td) / "state", session_id="a3f9c2d1")
            try:
                spool = Spool(Path(td) / "spool",
                              capacity=1,
                              on_event=lambda evt, **f: tel.event(evt, **f))
                spool.enqueue(write_one(spool, "a3f9c2d1-000001"))
                spool.enqueue(write_one(spool, "a3f9c2d1-000002"))  # evicts 1
                spool.emit("STALE_DIVERT", id="a3f9c2d1-000001")
            finally:
                tel.close()
            lines = [json.loads(l) for l in
                     (Path(td) / "state" / "events.jsonl")
                     .read_text(encoding="utf-8").splitlines()]
            evts = [l["evt"] for l in lines]
            self.assertIn("SPILLED", evts)
            self.assertIn("STALE_DIVERT", evts)


if __name__ == "__main__":
    unittest.main(verbosity=2)
