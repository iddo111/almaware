"""lane tests — ONE worker thread owns every decode; the audio thread only
hands over record ids. Born 2026-08-20: until then router.process_one ran
INSIDE the 100 ms sounddevice callback (~350 ms decode + ~175 ms LANG_FLIP +
owner-gate), so every utterance cost the NEXT utterance its first frames; and
the 60 s beat thread drained the same spool concurrently — two lanes, the
exact shape INSIGHTS §1.11 names as how the same audio types twice."""
from __future__ import annotations

import pathlib
import sys
import threading
import time
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.lane import Lane  # noqa: E402


class _Router:
    def __init__(self, delay=0.0, boom=()):
        self.delay = delay
        self.boom = set(boom)
        self.seen = []            # (rec_id, thread name)
        self.drains = 0
        self.lock = threading.Lock()
        self.active = 0
        self.max_active = 0

    def _enter(self):
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)

    def _leave(self):
        with self.lock:
            self.active -= 1

    def process_one_safe(self, rec_id):
        self._enter()
        try:
            time.sleep(self.delay)
            self.seen.append((rec_id, threading.current_thread().name))
            if rec_id in self.boom:
                raise RuntimeError("should have been caught by _safe, but isn't here")
            return "typed"
        finally:
            self._leave()

    def drain(self, max_records=50):
        self._enter()
        try:
            time.sleep(self.delay)
            self.drains += 1
            return {"typed": 0}
        finally:
            self._leave()


class LaneTests(unittest.TestCase):
    def test_submit_returns_immediately_and_processes_in_order_off_thread(self):
        r = _Router(delay=0.02)
        outcomes = []
        lane = Lane(r, on_outcome=lambda rid, st: outcomes.append((rid, st)))
        lane.start()
        try:
            t0 = time.monotonic()
            for i in range(5):
                lane.submit(f"r-{i}")
            self.assertLess(time.monotonic() - t0, 0.01, "submit must not block the audio thread")
            self.assertTrue(lane.wait_idle(timeout=2.0))
        finally:
            lane.stop()
        self.assertEqual([rid for rid, _ in r.seen], [f"r-{i}" for i in range(5)], "in order")
        self.assertTrue(all(name == "lane" for _, name in r.seen), "never on the caller's thread")
        self.assertEqual(outcomes, [(f"r-{i}", "typed") for i in range(5)])

    def test_drain_runs_on_the_same_single_lane(self):
        r = _Router(delay=0.02)
        lane = Lane(r)
        lane.start()
        try:
            for i in range(4):
                lane.submit(f"r-{i}")
                lane.request_drain()
            self.assertTrue(lane.wait_idle(timeout=2.0))
        finally:
            lane.stop()
        self.assertEqual(r.drains, 4)
        self.assertEqual(r.max_active, 1, "ONE lane: decode and drain never overlap")

    def test_a_raising_record_does_not_kill_the_lane(self):
        r = _Router(boom={"r-1"})
        alarms = []
        lane = Lane(r, on_error=lambda rid, err: alarms.append((rid, err)))
        lane.start()
        try:
            lane.submit("r-0"); lane.submit("r-1"); lane.submit("r-2")
            self.assertTrue(lane.wait_idle(timeout=2.0))
            self.assertTrue(lane.alive)
        finally:
            lane.stop()
        self.assertEqual([rid for rid, _ in r.seen], ["r-0", "r-1", "r-2"])
        self.assertEqual(len(alarms), 1)
        self.assertEqual(alarms[0][0], "r-1")
        self.assertIn("RuntimeError", alarms[0][1])

    def test_stop_is_clean_and_idempotent(self):
        lane = Lane(_Router())
        lane.start()
        lane.stop(); lane.stop()
        self.assertFalse(lane.alive)

    def test_depth_is_visible(self):
        r = _Router(delay=0.05)
        lane = Lane(r)
        lane.start()
        try:
            for i in range(3):
                lane.submit(f"r-{i}")
            self.assertGreaterEqual(lane.depth(), 1)
            self.assertTrue(lane.wait_idle(timeout=2.0))
            self.assertEqual(lane.depth(), 0)
        finally:
            lane.stop()


if __name__ == "__main__":
    unittest.main()
