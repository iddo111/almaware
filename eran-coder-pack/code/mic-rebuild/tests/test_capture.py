"""K7 acceptance tests for client/capture.py — written FIRST (TDD).

PHASE2-DESIGN.md K7 row + section 2 capture.py spec; PHASE1-INQUIRY.md
section 2 scars 24/25/45 and criterion 22:

  scar 24       format negotiation: try 16k mono -> native -> 48k/44.1k;
                downmix; resample in-callback (resampler tested separately).
  scar 25       silent-but-open devices trigger PERIODIC re-resolve (the 69%
                capture-level reset deafened the RMS gate with zero errors).
  scar 45       ABOVE_NORMAL priority for the capture thread only, NEVER
                realtime — asserted at runtime, not assumed (criterion 22).
  design sec 2  copy-out in callback; bounded 200-frame queue,
                drop-on-full + visible counter.

ALL tests run against synthetic streams and injected callables — no
sounddevice import, no real device is enumerated or opened, no audio output
exists (wave guardrails 1-3). Thread-priority tests touch only the test's
own worker thread — never a device, never another process.
"""
from __future__ import annotations

import sys
import threading
import unittest
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from client import capture  # noqa: E402
from client.capture import (  # noqa: E402
    BoundedFrameQueue,
    CapturePipeline,
    FormatNegotiationError,
    PriorityAssertError,
    SilentOpenWatch,
    assert_capture_thread_priority,
    negotiate_format,
    set_capture_thread_priority,
)


# ---------------------------------------------------------------- fixtures

def stereo(x: np.ndarray) -> np.ndarray:
    return np.stack([x, x], axis=1).astype(np.float32)


def mono2d(x: np.ndarray) -> np.ndarray:
    return x.reshape(-1, 1).astype(np.float32)


def tone(freq_hz: float, dur_s: float, fs: int, amp: float = 0.5) -> np.ndarray:
    t = np.arange(int(dur_s * fs), dtype=np.float64) / fs
    return (amp * np.sin(2.0 * np.pi * freq_hz * t)).astype(np.float32)


class AcceptTable:
    """Fake check_input_settings: accepts only listed (rate, channels)."""

    def __init__(self, accepted):
        self.accepted = set(accepted)
        self.tried: list[tuple[int, int]] = []

    def __call__(self, rate: int, channels: int) -> None:
        self.tried.append((rate, channels))
        if (rate, channels) not in self.accepted:
            raise RuntimeError(f"format refused: {rate}Hz/{channels}ch")


# ---------------------------------------------------------------- format negotiation

class NegotiateFormatTests(unittest.TestCase):
    """scar 24: 16k mono -> native -> 48k/44.1k, mono before native channels."""

    def test_prefers_16k_mono(self):
        chk = AcceptTable({(16_000, 1), (48_000, 2)})
        self.assertEqual(negotiate_format(chk, native_rate=48_000, native_channels=2),
                         (16_000, 1))

    def test_brio_case_rejects_16k_takes_native(self):
        # the BRIO rejects forced 16kHz (-9997) — must land on its native rate
        chk = AcceptTable({(48_000, 1), (48_000, 2)})
        self.assertEqual(negotiate_format(chk, native_rate=48_000, native_channels=2),
                         (48_000, 1))

    def test_stereo_only_device(self):
        chk = AcceptTable({(48_000, 2)})
        self.assertEqual(negotiate_format(chk, native_rate=48_000, native_channels=2),
                         (48_000, 2))

    def test_44100_fallback(self):
        chk = AcceptTable({(44_100, 1)})
        self.assertEqual(negotiate_format(chk, native_rate=96_000, native_channels=2),
                         (44_100, 1))

    def test_try_order_rate_major_mono_first(self):
        chk = AcceptTable(set())   # refuses everything; we inspect the order
        with self.assertRaises(FormatNegotiationError):
            negotiate_format(chk, native_rate=96_000, native_channels=2)
        # 16k first, then native, then 48k, then 44.1k; mono before native ch
        self.assertEqual(chk.tried[:2], [(16_000, 1), (16_000, 2)])
        rates_in_order = [r for r, _ in chk.tried]
        self.assertEqual(sorted(set(rates_in_order), key=rates_in_order.index),
                         [16_000, 96_000, 48_000, 44_100])

    def test_all_refused_is_loud(self):
        # no hopeful open with an unvalidated format — loud failure (scar 6 ethos)
        with self.assertRaises(FormatNegotiationError):
            negotiate_format(AcceptTable(set()), native_rate=48_000, native_channels=2)

    def test_no_duplicate_tries(self):
        chk = AcceptTable(set())
        with self.assertRaises(FormatNegotiationError):
            negotiate_format(chk, native_rate=48_000, native_channels=1)
        self.assertEqual(len(chk.tried), len(set(chk.tried)))


# ---------------------------------------------------------------- bounded queue

class BoundedFrameQueueTests(unittest.TestCase):
    """design sec 2: bounded 200-frame queue, drop-on-full + VISIBLE counter."""

    def test_default_bound_is_200(self):
        self.assertEqual(capture.CAPTURE_QUEUE_FRAMES, 200)
        self.assertEqual(BoundedFrameQueue().maxsize, 200)

    def test_accepts_until_full(self):
        q = BoundedFrameQueue(maxsize=3)
        f = np.zeros(480, dtype=np.float32)
        self.assertTrue(all(q.put(f) for _ in range(3)))
        self.assertEqual(q.qsize(), 3)
        self.assertEqual(q.dropped, 0)

    def test_drop_on_full_counts_and_returns_false(self):
        q = BoundedFrameQueue(maxsize=2)
        f = np.zeros(480, dtype=np.float32)
        q.put(f), q.put(f)
        self.assertFalse(q.put(f))
        self.assertFalse(q.put(f))
        self.assertEqual(q.dropped, 2)      # the visible counter
        self.assertEqual(q.qsize(), 2)      # never grows past the bound

    def test_get_returns_frames_in_order(self):
        q = BoundedFrameQueue(maxsize=4)
        for i in range(3):
            q.put(np.full(4, float(i), dtype=np.float32))
        self.assertEqual(float(q.get(timeout=0.1)[0]), 0.0)
        self.assertEqual(float(q.get(timeout=0.1)[0]), 1.0)

    def test_get_timeout_returns_none(self):
        self.assertIsNone(BoundedFrameQueue(maxsize=2).get(timeout=0.01))

    def test_accepted_counter(self):
        q = BoundedFrameQueue(maxsize=2)
        f = np.zeros(4, dtype=np.float32)
        q.put(f), q.put(f), q.put(f)
        self.assertEqual(q.accepted, 2)
        self.assertEqual(q.dropped, 1)


# ---------------------------------------------------------------- pipeline

class _Status:
    def __init__(self, input_overflow=False):
        self.input_overflow = input_overflow


class CapturePipelineTests(unittest.TestCase):
    """The in-callback body: copy-out -> downmix -> resample -> frame -> enqueue."""

    def _pipe(self, **kw):
        kw.setdefault("cap_rate", 48_000)
        kw.setdefault("cap_channels", 2)
        return CapturePipeline(**kw)

    def _feed_all(self, pipe, x2d, chunk=1440):
        for i in range(0, len(x2d), chunk):
            pipe.on_audio(x2d[i:i + chunk])

    def test_frames_are_block_sized_16k(self):
        pipe = self._pipe()
        self._feed_all(pipe, stereo(tone(1000.0, 1.0, 48_000)))
        frames = []
        while (f := pipe.read(timeout=0.0)) is not None:
            frames.append(f)
        self.assertGreater(len(frames), 25)
        self.assertTrue(all(len(f) == pipe.block == 480 for f in frames))  # 30ms @ 16k

    def test_total_duration_preserved(self):
        pipe = self._pipe()
        self._feed_all(pipe, stereo(tone(1000.0, 2.0, 48_000)))
        n = 0
        while pipe.read(timeout=0.0) is not None:
            n += 1
        # 2s of audio -> ~66 x 30ms frames (framing remainder allowed)
        self.assertAlmostEqual(n, 66, delta=2)

    def test_mono_input_supported(self):
        pipe = self._pipe(cap_channels=1)
        pipe.on_audio(mono2d(tone(1000.0, 0.5, 48_000)))
        self.assertIsNotNone(pipe.read(timeout=0.0))

    def test_downmix_stereo_to_mono_mean(self):
        x = tone(1000.0, 0.5, 48_000)
        left_only = np.stack([x, np.zeros_like(x)], axis=1)
        pipe = self._pipe()
        pipe.on_audio(left_only)
        f = pipe.read(timeout=0.0)
        # mean of (x, 0) halves the amplitude
        self.assertAlmostEqual(float(np.max(np.abs(f))), 0.25, delta=0.03)

    def test_copy_out_in_callback(self):
        # design sec 2: copy-out in callback — mutating the driver buffer
        # after the callback returns must not corrupt queued frames.
        pipe = self._pipe(cap_rate=16_000, cap_channels=1)
        buf = mono2d(np.full(480, 0.25, dtype=np.float32))
        pipe.on_audio(buf)
        buf[:] = -1.0
        f = pipe.read(timeout=0.0)
        self.assertIsNotNone(f)
        self.assertAlmostEqual(float(f[0]), 0.25, places=5)

    def test_queue_drop_on_full_visible(self):
        pipe = self._pipe(queue_maxsize=5)
        self._feed_all(pipe, stereo(tone(1000.0, 2.0, 48_000)))
        self.assertEqual(pipe.queue.qsize(), 5)
        self.assertGreater(pipe.frames_dropped, 0)
        snap = pipe.snapshot()
        self.assertEqual(snap["drop_frames"], pipe.frames_dropped)
        self.assertEqual(snap["q"], 5)

    def test_overflow_counter_from_status(self):
        # criterion 22: overflow verified from the capture layer's OWN counters
        pipe = self._pipe()
        chunk = stereo(tone(1000.0, 0.03, 48_000))
        pipe.on_audio(chunk, status=_Status(input_overflow=True))
        pipe.on_audio(chunk, status=_Status(input_overflow=False))
        pipe.on_audio(chunk, status=_Status(input_overflow=True))
        self.assertEqual(pipe.overflow_count, 2)
        self.assertEqual(pipe.snapshot()["overflow"], 2)

    def test_callback_counter(self):
        pipe = self._pipe()
        chunk = stereo(tone(1000.0, 0.03, 48_000))
        for _ in range(4):
            pipe.on_audio(chunk)
        self.assertEqual(pipe.callbacks, 4)


# ---------------------------------------------------------------- thread priority

class ThreadPriorityTests(unittest.TestCase):
    """scar 45 / criterion 22: ABOVE_NORMAL asserted at RUNTIME, never realtime.
    Touches only this test's own worker thread — no device, no other process."""

    def _run_in_thread(self, fn):
        box: dict = {}

        def wrapper():
            try:
                box["result"] = fn()
            except Exception as e:  # surfaced to the test thread, loudly
                box["error"] = e

        t = threading.Thread(target=wrapper)
        t.start()
        t.join(timeout=10)
        if "error" in box:
            raise box["error"]
        return box.get("result")

    def test_constant_is_above_normal_not_realtime(self):
        self.assertEqual(capture.THREAD_PRIORITY_ABOVE_NORMAL, 1)
        # NEVER realtime: the module must not even define a time-critical constant
        self.assertFalse(hasattr(capture, "THREAD_PRIORITY_TIME_CRITICAL"))

    def test_set_then_assert_passes(self):
        def body():
            got = set_capture_thread_priority()
            self.assertEqual(got, capture.THREAD_PRIORITY_ABOVE_NORMAL)
            return assert_capture_thread_priority()   # must not raise
        self.assertEqual(self._run_in_thread(body),
                         capture.THREAD_PRIORITY_ABOVE_NORMAL)

    def test_assert_fails_on_normal_priority_thread(self):
        def body():
            with self.assertRaises(PriorityAssertError):
                assert_capture_thread_priority()   # fresh thread = NORMAL (0)
        self._run_in_thread(body)

    def test_assert_fails_on_realtime_readback(self):
        # injected getter: even if something ELSE raised us to time-critical,
        # the assert must refuse — ABOVE_NORMAL exactly, never realtime
        with self.assertRaises(PriorityAssertError):
            assert_capture_thread_priority(get_priority=lambda: 15)

    def test_pipeline_asserts_priority_on_first_callback(self):
        # the runtime assert lives in the capture path itself, not in hope
        def body():
            pipe = CapturePipeline(cap_rate=16_000, cap_channels=1)
            pipe.on_audio(mono2d(np.zeros(160, dtype=np.float32)))
            return pipe.thread_priority
        self.assertEqual(self._run_in_thread(body),
                         capture.THREAD_PRIORITY_ABOVE_NORMAL)

    def test_pipeline_priority_failure_is_visible_not_fatal(self):
        # capture must SURVIVE a priority failure (audio > priority) but the
        # failure must be visible on the counters, never silent
        events = []
        pipe = CapturePipeline(cap_rate=16_000, cap_channels=1,
                               set_priority_fn=lambda: (_ for _ in ()).throw(
                                   PriorityAssertError("denied")),
                               on_event=lambda evt, **kw: events.append(evt))
        pipe.on_audio(mono2d(np.full(480, 0.1, dtype=np.float32)))
        self.assertIsNotNone(pipe.read(timeout=0.0))       # capture continued
        self.assertEqual(pipe.priority_failures, 1)
        self.assertIn("DEVICE_PRIORITY_FAIL", events)


# ---------------------------------------------------------------- silent-open watch

class SilentOpenWatchTests(unittest.TestCase):
    """scar 25: silent-but-open triggers PERIODIC re-resolve. Duration is
    counted from the audio itself (samples/rate) — deterministic, no clock."""

    RATE = 16_000

    def _silence(self, dur_s: float) -> np.ndarray:
        return np.zeros(int(dur_s * self.RATE), dtype=np.float32)

    def _speech(self, dur_s: float) -> np.ndarray:
        return tone(300.0, dur_s, self.RATE, amp=0.05)

    def test_window_constant_pinned(self):
        self.assertEqual(capture.SILENT_OPEN_WINDOW_S, 30.0)

    def test_fires_after_window_of_silence(self):
        w = SilentOpenWatch(rate=self.RATE)
        fired = [w.feed(self._silence(5.0)) for _ in range(7)]   # 35s total
        self.assertIn(True, fired)
        self.assertEqual(fired.index(True), 5)   # at >=30s, not before

    def test_live_audio_never_fires(self):
        w = SilentOpenWatch(rate=self.RATE)
        self.assertFalse(any(w.feed(self._speech(5.0)) for _ in range(10)))

    def test_speech_resets_accumulated_silence(self):
        w = SilentOpenWatch(rate=self.RATE)
        for _ in range(5):                     # 25s silence — under the window
            self.assertFalse(w.feed(self._silence(5.0)))
        self.assertFalse(w.feed(self._speech(1.0)))   # reset
        for _ in range(5):                     # 25s again — still under
            self.assertFalse(w.feed(self._silence(5.0)))
        self.assertTrue(w.feed(self._silence(5.0)))   # now 30s

    def test_periodic_refire_while_still_silent(self):
        # scar 25 says PERIODIC: still-silent after a re-resolve must fire again
        w = SilentOpenWatch(rate=self.RATE)
        fires = sum(w.feed(self._silence(5.0)) for _ in range(12))  # 60s
        self.assertEqual(fires, 2)

    def test_floor_matches_devices_liveness_floor(self):
        # one source of truth with the K6 device law
        from client import devices
        self.assertEqual(capture.SILENT_RMS_FLOOR, devices.RMS_LIVENESS_FLOOR)

    def test_pipeline_emits_silent_open_event(self):
        # integration: the pipeline itself feeds the watch and surfaces the
        # re-resolve trigger as a visible DEVICE_ event + flag
        events = []
        pipe = CapturePipeline(cap_rate=16_000, cap_channels=1,
                               set_priority_fn=lambda: 1,
                               on_event=lambda evt, **kw: events.append((evt, kw)))
        for _ in range(7):                    # 35s of silent-but-open audio
            pipe.on_audio(mono2d(np.zeros(5 * 16_000, dtype=np.float32)))
        names = [e for e, _ in events]
        self.assertIn("DEVICE_SILENT_REOPEN", names)
        kw = [k for e, k in events if e == "DEVICE_SILENT_REOPEN"][0]
        self.assertGreaterEqual(kw["silent_s"], 30.0)

    def test_pipeline_live_audio_no_event(self):
        events = []
        pipe = CapturePipeline(cap_rate=16_000, cap_channels=1,
                               set_priority_fn=lambda: 1,
                               on_event=lambda evt, **kw: events.append(evt))
        for _ in range(8):
            pipe.on_audio(mono2d(tone(300.0, 5.0, 16_000, amp=0.05)))
        self.assertNotIn("DEVICE_SILENT_REOPEN", events)


if __name__ == "__main__":
    unittest.main(verbosity=2)
