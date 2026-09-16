"""Tests for client/hotkeys.py — the binding that finally exists.

The guard-species lesson: `hotkey_pause` lived in config since K1,
`parse_hotkey` refused malformed specs with a lecture about silent
non-binding — and no production code ever called RegisterHotKey. A guard
around a mechanism that does not exist. These tests drive the REAL pump
logic through a deterministic fake API (the same seam pattern as focus_api /
input_api / the presence idle api): no user32, no threads, no global chords
grabbed while Iddo works.
"""
from __future__ import annotations

import unittest

from client.hotkeys import WM_HOTKEY, WM_QUIT, HotkeyListener
from client.tray import parse_hotkey


class RecordingEmit:
    def __init__(self):
        self.events = []

    def __call__(self, name, **kw):
        self.events.append((name, kw))

    def states(self):
        return [kw.get("state") for n, kw in self.events if n == "STATE"]


class FakeApi:
    """Deterministic hotkey API: scripted registration outcomes + messages."""

    def __init__(self, messages, refuse=()):
        self._messages = list(messages)
        self._refuse = set(refuse)          # hotkey ids that fail to register
        self.registered = []
        self.unregistered = []

    def thread_id(self):
        return 4242

    def register(self, hk_id, mods, vk):
        if hk_id in self._refuse:
            return False
        self.registered.append((hk_id, mods, vk))
        return True

    def unregister(self, hk_id):
        self.unregistered.append(hk_id)

    def get_message(self):
        if self._messages:
            return self._messages.pop(0)
        return (WM_QUIT, 0)

    def post_quit(self, thread_id):
        pass


def listener(emit=None):
    return HotkeyListener(emit=emit or RecordingEmit(),
                          api_factory=lambda: None)  # tests drive _pump directly


class PumpTests(unittest.TestCase):

    def test_hotkey_message_fires_the_action(self):
        fired = []
        li = listener()
        li.add(parse_hotkey("ctrl+alt+m"), lambda: fired.append("pause"))
        li._pump(FakeApi([(WM_HOTKEY, 1), (WM_QUIT, 0)]))
        self.assertEqual(fired, ["pause"])

    def test_two_bindings_route_by_id(self):
        fired = []
        li = listener()
        li.add(parse_hotkey("ctrl+alt+m"), lambda: fired.append("pause"))
        li.add(parse_hotkey("ctrl+alt+a"), lambda: fired.append("arm"))
        li._pump(FakeApi([(WM_HOTKEY, 2), (WM_HOTKEY, 1), (WM_HOTKEY, 2),
                          (WM_QUIT, 0)]))
        self.assertEqual(fired, ["arm", "pause", "arm"])

    def test_registration_failure_is_loud_and_partial(self):
        """The chord another app owns: its binding is reported dead, the
        OTHER binding keeps working — no silent all-or-nothing."""
        emit = RecordingEmit()
        fired = []
        li = listener(emit)
        li.add(parse_hotkey("ctrl+alt+m"), lambda: fired.append("pause"))
        li.add(parse_hotkey("ctrl+alt+a"), lambda: fired.append("arm"))
        li._pump(FakeApi([(WM_HOTKEY, 1), (WM_HOTKEY, 2), (WM_QUIT, 0)],
                         refuse={2}))
        self.assertEqual(fired, ["pause"])          # id 2 never registered
        self.assertEqual(li.bound, ["Ctrl+Alt+M"])
        self.assertEqual(li.failed, ["Ctrl+Alt+A"])
        self.assertIn("HOTKEY_BIND_FAIL", emit.states())

    def test_action_exception_does_not_kill_the_pump(self):
        """One bad action must not take every other hotkey down with it —
        the _spawn lesson (a thread of this program may not die quietly)
        applied inside the pump."""
        emit = RecordingEmit()
        fired = []
        li = listener(emit)
        li.add(parse_hotkey("ctrl+alt+m"),
               lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        li.add(parse_hotkey("ctrl+alt+a"), lambda: fired.append("arm"))
        li._pump(FakeApi([(WM_HOTKEY, 1), (WM_HOTKEY, 2), (WM_QUIT, 0)]))
        self.assertEqual(fired, ["arm"])
        self.assertIn("HOTKEY_ACTION_ERROR", emit.states())

    def test_everything_registered_is_unregistered_on_exit(self):
        li = listener()
        li.add(parse_hotkey("ctrl+alt+m"), lambda: None)
        li.add(parse_hotkey("ctrl+alt+a"), lambda: None)
        api = FakeApi([(WM_QUIT, 0)])
        li._pump(api)
        self.assertEqual(sorted(api.unregistered), [1, 2])

    def test_bound_chords_are_journalled(self):
        """A hotkey that DID bind is a fact in the ledger — the exact inverse
        of the silent non-binding parse_hotkey lectures about."""
        emit = RecordingEmit()
        li = listener(emit)
        li.add(parse_hotkey("ctrl+alt+m"), lambda: None)
        li._pump(FakeApi([(WM_QUIT, 0)]))
        self.assertEqual(emit.states(), ["HOTKEY_BOUND"])

    def test_add_after_start_refuses(self):
        li = HotkeyListener(emit=RecordingEmit(), api_factory=lambda: FakeApi([]))
        li.add(parse_hotkey("ctrl+alt+m"), lambda: None)
        li.start()
        try:
            with self.assertRaises(RuntimeError):
                li.add(parse_hotkey("ctrl+alt+a"), lambda: None)
        finally:
            li.stop()

    def test_start_with_no_bindings_is_a_no_op(self):
        li = HotkeyListener(emit=RecordingEmit(), api_factory=lambda: FakeApi([]))
        li.start()                                   # no thread, no pump
        self.assertIsNone(li._thread)
        li.stop()                                    # and stop is safe


class VocabularyTests(unittest.TestCase):

    def test_listener_states_ride_the_STATE_event(self):
        """The listener journals through STATE (an open state field), so no
        new vocabulary entries were needed — assert the assumption holds."""
        from client.telemetry import EVENT_VOCABULARY
        self.assertIn("STATE", EVENT_VOCABULARY)


if __name__ == "__main__":
    unittest.main()
