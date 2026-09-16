"""Arm hotkey: a REAL binding or an honest refusal (guard species #5) —
including the app seam: the key must reach the switch."""
from __future__ import annotations

import json
import queue
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from k2 import hotkeys


class ParseHotkey(unittest.TestCase):

    def test_ctrl_alt_a(self):
        mods, vk = hotkeys.parse_hotkey("ctrl+alt+a")
        self.assertEqual(mods, hotkeys.MOD_CONTROL | hotkeys.MOD_ALT)
        self.assertEqual(vk, 0x41)

    def test_unknown_token_refused(self):
        with self.assertRaises(hotkeys.HotkeySpecError):
            hotkeys.parse_hotkey("ctrl+alt+banana")

    def test_bare_key_refused(self):
        """A bare key would eat normal typing."""
        with self.assertRaises(hotkeys.HotkeySpecError):
            hotkeys.parse_hotkey("a")

    def test_missing_key_refused(self):
        with self.assertRaises(hotkeys.HotkeySpecError):
            hotkeys.parse_hotkey("ctrl+alt")


class FakeApi:
    """Deterministic pump API: events come from a queue."""

    def __init__(self, register_ok=True):
        self.register_ok = register_ok
        self.registered = False
        self.unregistered = False
        self.q: "queue.Queue[str]" = queue.Queue()

    def register(self, mods, vk):
        self.registered = self.register_ok
        return self.register_ok

    def unregister(self):
        self.unregistered = True

    def pump_one(self):
        return self.q.get()

    def current_thread_id(self):
        return 1

    def post_quit(self, thread_id):
        self.q.put("quit")


class Pump(unittest.TestCase):

    def test_bind_success_fires_callback_per_hotkey(self):
        api = FakeApi()
        hits = []
        events = []
        hk = hotkeys.ArmHotkey("ctrl+alt+a", lambda: hits.append(1),
                               emit=lambda e, **f: events.append((e, f)),
                               api_factory=lambda: api)
        self.assertTrue(hk.start())
        self.assertEqual(events[0][0], "HOTKEY_BOUND")
        api.q.put("hotkey")
        api.q.put("hotkey")
        api.q.put("quit")
        hk._thread.join(timeout=5)
        self.assertEqual(len(hits), 2)
        self.assertTrue(api.unregistered)
        hk._thread = None                      # already joined

    def test_bind_failure_is_loud_and_false(self):
        """PROOF THE GUARD CAN FIRE: register refused -> start() False +
        HOTKEY_BIND_FAIL journalled."""
        api = FakeApi(register_ok=False)
        events = []
        hk = hotkeys.ArmHotkey("ctrl+alt+a", lambda: None,
                               emit=lambda e, **f: events.append((e, f)),
                               api_factory=lambda: api)
        self.assertFalse(hk.start(timeout_s=1.0))
        self.assertEqual(events[0][0], "HOTKEY_BIND_FAIL")

    def test_real_registration_smoke(self):
        """ENVIRONMENTAL: bind ctrl+alt+shift+a with the REAL user32 on a
        real pump thread, then stop. Skips honestly if the combo is taken
        on this machine."""
        hk = hotkeys.ArmHotkey("ctrl+alt+shift+a", lambda: None)
        bound = hk.start(timeout_s=5.0)
        if not bound:
            self.skipTest("ctrl+alt+shift+a already registered by another "
                          "app on this machine — honest skip")
        hk.stop()


class AppSeam(unittest.TestCase):
    """The key must reach the switch THROUGH the assembly (species #5)."""

    class _ActiveOwner:
        def idle_seconds(self):
            return 5.0

    def _cfg(self, td, **over):
        from k2 import configstore
        token = Path(td) / "tok"
        token.write_text("t\n", encoding="utf-8")
        data = {
            "server_url": "http://<lan-ip>:8737",
            "server_token_path": str(token),
            "lang_hint_default": "he",
            "armed_mode": True,
            "enter_idle_limit_s": 120,
            "type_idle_limit_s": 600,
            "arm_timeout_s": 900,
            "never_use_devices_extra": [],
            "revision": 1,
        }
        data.update(over)
        p = Path(td) / "k2.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        return configstore.ConfigStore(p).load()

    def test_bound_key_arms_the_assembled_decision(self):
        """armed config + working key: disarmed refuses, toggle permits."""
        from k2 import app, journal
        api = FakeApi()
        with TemporaryDirectory() as td:
            jr = journal.Journal(Path(td) / "state", "abcd1234")
            try:
                captured = {}

                def factory(cb, em):
                    captured["cb"] = cb
                    return hotkeys.ArmHotkey("ctrl+alt+a", cb, emit=em,
                                             api_factory=lambda: api)

                decide, typer, stt = app.build(
                    self._cfg(td), jr, idle_api=self._ActiveOwner(),
                    hotkey_factory=factory)
                self.assertFalse(decide().may_type)     # disarmed
                captured["cb"]()                        # the key press
                self.assertTrue(decide().may_type)      # armed
            finally:
                jr.close()

    def test_bind_failure_disables_arm_layer_loudly(self):
        """D-008: enabled-but-unarmable must not exist. Bind fails ->
        arm layer transparent + ARM_LAYER_DISABLED journalled; the
        presence gate still guards."""
        from k2 import app, journal
        with TemporaryDirectory() as td:
            jr = journal.Journal(Path(td) / "state", "abcd1234")
            try:
                decide, typer, stt = app.build(
                    self._cfg(td), jr, idle_api=self._ActiveOwner(),
                    hotkey_factory=lambda cb, em: hotkeys.ArmHotkey(
                        "ctrl+alt+a", cb, emit=em,
                        api_factory=lambda: FakeApi(register_ok=False)))
                self.assertTrue(decide().may_type,
                                "arm layer must fall open when unarmable")
            finally:
                jr.close()
            lines = (Path(td) / "state" / "events.jsonl").read_text(
                encoding="utf-8").splitlines()
            events = [json.loads(x) for x in lines]
            self.assertTrue(any(e["evt"] == "HOTKEY_BIND_FAIL"
                                for e in events))
            self.assertTrue(any(
                e["evt"] == "STATE"
                and e.get("state") == "ARM_LAYER_DISABLED"
                for e in events))


if __name__ == "__main__":
    unittest.main()
