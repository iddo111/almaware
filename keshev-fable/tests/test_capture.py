"""capture tests — interlock fails closed, healing is a loop, law re-checked."""
from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.capture import Capture, RivalAliveError  # noqa: E402


class _MemJournal:
    def __init__(self):
        self.events = []

    def event(self, name, **fields):
        self.events.append((name, fields))
        return {"evt": name, **fields}

    def names(self):
        return [n for n, _ in self.events]


def make_capture(j, *, rival=False, open_ok=True):
    opened = []

    def open_fn(name):
        if not open_ok:
            raise OSError("device busy")
        opened.append(name)
        return f"stream:{name}"

    c = Capture(j, rival_alive_fn=lambda: rival,
                open_stream_fn=open_fn, close_stream_fn=lambda s: None)
    c._opened = opened  # type: ignore[attr-defined]
    return c


class InterlockTests(unittest.TestCase):
    def setUp(self):
        self.j = _MemJournal()

    def test_rival_alive_refuses(self):
        c = make_capture(self.j, rival=True)
        with self.assertRaises(RivalAliveError):
            c.start("Microphone (Logitech BRIO)")
        self.assertIn("STATE", self.j.names())

    def test_unprovable_freedom_fails_closed(self):
        """None (can't prove) must refuse exactly like True — the mic-switch
        scar."""
        c = Capture(self.j, rival_alive_fn=lambda: None,
                    open_stream_fn=lambda n: "s", close_stream_fn=lambda s: None)
        with self.assertRaises(RivalAliveError):
            c.start("Microphone (Logitech BRIO)")

    def test_free_mic_opens(self):
        c = make_capture(self.j)
        self.assertTrue(c.start("Microphone (Logitech BRIO)"))
        self.assertIn("DEVICE_OPEN", self.j.names())

    def test_forbidden_device_is_idle_even_here(self):
        """Defense in depth: a headset name reaching capture still refuses."""
        c = make_capture(self.j)
        self.assertFalse(c.start("Microphone (WH-1000XM4 Hands-Free)"))
        self.assertIn("IDLE_NO_MIC", self.j.names())

    def test_no_device_is_structural_idle(self):
        c = make_capture(self.j)
        self.assertFalse(c.start(None))
        self.assertIn("IDLE_NO_MIC", self.j.names())


class HealingTests(unittest.TestCase):
    def setUp(self):
        self.j = _MemJournal()

    def test_device_error_backs_off_capped(self):
        c = make_capture(self.j)
        c.start("Microphone (Logitech BRIO)")
        backoffs = [c.on_device_error() for _ in range(10)]
        self.assertEqual(backoffs[0], 1.0)
        self.assertEqual(backoffs[1], 2.0)
        self.assertEqual(backoffs[-1], 60.0, "backoff must cap, not explode")
        self.assertEqual(self.j.names().count("DEVICE_LOST"), 10)

    def test_reopen_resets_backoff(self):
        c = make_capture(self.j)
        c.start("Microphone (Logitech BRIO)")
        c.on_device_error()
        c.on_device_error()
        c.reopened()
        self.assertEqual(c.on_device_error(), 1.0)
        self.assertIn("DEVICE_REOPEN", self.j.names())

    def test_error_never_raises(self):
        """Healing is a loop, not a crash — even close() failing is absorbed."""
        c = Capture(self.j, rival_alive_fn=lambda: False,
                    open_stream_fn=lambda n: "s",
                    close_stream_fn=lambda s: (_ for _ in ()).throw(OSError()))
        c.start("Microphone (Logitech BRIO)")
        try:
            c.on_device_error()
        except Exception as e:  # noqa: BLE001
            self.fail(f"on_device_error raised {e!r}")


class GrepLawTests(unittest.TestCase):
    def test_no_audio_import_exists_in_capture(self):
        """The ONE-MIC law is enforceable by grep: capture.py must not import
        any audio backend — it is injected."""
        src = (pathlib.Path(__file__).resolve().parents[1] / "app" /
               "capture.py").read_text(encoding="utf-8")
        for needle in ("sounddevice", "pyaudio", "winsound", "playsound"):
            self.assertNotIn(needle, src)


if __name__ == "__main__":
    unittest.main()
