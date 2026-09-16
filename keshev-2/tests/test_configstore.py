"""Configstore: HALT on corrupt, CAS, additive-only schema, the explicit
no-hot-reload contract — and 'auto' refused at the schema."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from k2 import configstore

VALID = {
    "server_url": "http://<lan-ip>:8737",
    "server_token_path": "state\\stt-token",
    "lang_hint_default": "he",
    "armed_mode": False,
    "enter_idle_limit_s": 120,
    "type_idle_limit_s": 600,
    "arm_timeout_s": 900,
    "never_use_devices_extra": [],
    "revision": 1,
}


def write(td, data) -> Path:
    p = Path(td) / "k2.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


class Halt(unittest.TestCase):

    def test_missing_file_halts(self):
        with TemporaryDirectory() as td:
            store = configstore.ConfigStore(Path(td) / "absent.json")
            with self.assertRaises(configstore.ConfigHaltError):
                store.load()

    def test_corrupt_json_halts(self):
        with TemporaryDirectory() as td:
            p = Path(td) / "k2.json"
            p.write_text("{broken", encoding="utf-8")
            with self.assertRaises(configstore.ConfigHaltError):
                configstore.ConfigStore(p).load()

    def test_missing_key_halts_no_defaults(self):
        """scar 40: there is no defaults path."""
        with TemporaryDirectory() as td:
            data = dict(VALID)
            del data["enter_idle_limit_s"]
            with self.assertRaises(configstore.ConfigHaltError):
                configstore.ConfigStore(write(td, data)).load()

    def test_cross_field_law(self):
        """type limit must exceed enter limit or the type-without-Enter
        band is empty (D-003)."""
        with TemporaryDirectory() as td:
            data = dict(VALID, enter_idle_limit_s=600, type_idle_limit_s=600)
            with self.assertRaises(configstore.ConfigHaltError):
                configstore.ConfigStore(write(td, data)).load()

    def test_valid_loads_readonly(self):
        with TemporaryDirectory() as td:
            cfg = configstore.ConfigStore(write(td, VALID)).load()
            self.assertEqual(cfg["lang_hint_default"], "he")
            with self.assertRaises(TypeError):
                cfg["armed_mode"] = True         # snapshot is immutable


class AutoRefused(unittest.TestCase):

    def test_auto_hint_halts_on_load(self):
        """D-004: a config FILE cannot re-open the transliteration scar."""
        with TemporaryDirectory() as td:
            data = dict(VALID, lang_hint_default="auto")
            with self.assertRaises(configstore.ConfigHaltError) as ctx:
                configstore.ConfigStore(write(td, data)).load()
            self.assertIn("auto", str(ctx.exception))

    def test_auto_hint_refused_on_write(self):
        with TemporaryDirectory() as td:
            store = configstore.ConfigStore(write(td, VALID))
            with self.assertRaises(configstore.ConfigValueError):
                store.set_key("lang_hint_default", "auto",
                              reason="test", author="t", expected_revision=1)


class Writes(unittest.TestCase):

    def test_cas_refuses_stale_writer(self):
        with TemporaryDirectory() as td:
            store = configstore.ConfigStore(write(td, VALID))
            store.set_key("armed_mode", True, reason="r", author="a",
                          expected_revision=1)
            with self.assertRaises(configstore.ConfigCasError):
                store.set_key("armed_mode", False, reason="r", author="b",
                              expected_revision=1)      # stale

    def test_unknown_keys_ride_through(self):
        """scar 39: unknown keys are structurally incapable of vanishing."""
        with TemporaryDirectory() as td:
            data = dict(VALID, future_key={"nested": True})
            p = write(td, data)
            store = configstore.ConfigStore(p)
            store.set_key("armed_mode", True, reason="r", author="a",
                          expected_revision=1)
            after = json.loads(p.read_text(encoding="utf-8"))
            self.assertEqual(after["future_key"], {"nested": True})
            self.assertEqual(after["revision"], 2)

    def test_unknown_key_not_settable(self):
        with TemporaryDirectory() as td:
            store = configstore.ConfigStore(write(td, VALID))
            with self.assertRaises(configstore.ConfigValueError):
                store.set_key("new_knob", 1, reason="r", author="a",
                              expected_revision=1)

    def test_revision_never_set_directly(self):
        with TemporaryDirectory() as td:
            store = configstore.ConfigStore(write(td, VALID))
            with self.assertRaises(configstore.ConfigValueError):
                store.set_key("revision", 99, reason="r", author="a",
                              expected_revision=1)

    def test_reason_required(self):
        """scar 42: 22 unlabeled interventions in 23 days."""
        with TemporaryDirectory() as td:
            store = configstore.ConfigStore(write(td, VALID))
            with self.assertRaises(configstore.ConfigValueError):
                store.set_key("armed_mode", True, reason="  ", author="a",
                              expected_revision=1)

    def test_history_appended(self):
        with TemporaryDirectory() as td:
            p = write(td, VALID)
            store = configstore.ConfigStore(p)
            store.set_key("armed_mode", True, reason="night test",
                          author="fable", expected_revision=1)
            hist = (Path(td) / "config_history.jsonl").read_text(
                encoding="utf-8").splitlines()
            entry = json.loads(hist[0])
            self.assertEqual(entry["key"], "armed_mode")
            self.assertEqual(entry["old"], False)
            self.assertEqual(entry["new"], True)
            self.assertEqual(entry["reason"], "night test")

    def test_no_bak_files_ever(self):
        with TemporaryDirectory() as td:
            p = write(td, VALID)
            store = configstore.ConfigStore(p)
            store.set_key("armed_mode", True, reason="r", author="a",
                          expected_revision=1)
            leftovers = [f.name for f in Path(td).iterdir()
                         if f.suffix not in (".json", ".jsonl")]
            self.assertEqual(leftovers, [])

    def test_write_refuses_cross_field_violation(self):
        with TemporaryDirectory() as td:
            store = configstore.ConfigStore(write(td, VALID))
            with self.assertRaises(configstore.ConfigValueError):
                store.set_key("enter_idle_limit_s", 700, reason="r",
                              author="a", expected_revision=1)


class NoHotReload(unittest.TestCase):
    """D-005: the contract is explicit and journalled."""

    def test_receipt_says_restart(self):
        with TemporaryDirectory() as td:
            store = configstore.ConfigStore(write(td, VALID))
            r = store.set_key("armed_mode", True, reason="r", author="a",
                              expected_revision=1)
            self.assertEqual(r.takes_effect, "restart")

    def test_config_stale_journalled(self):
        rec = []
        with TemporaryDirectory() as td:
            store = configstore.ConfigStore(
                write(td, VALID), emit=lambda e, **f: rec.append((e, f)))
            store.set_key("armed_mode", True, reason="r", author="a",
                          expected_revision=1)
        self.assertEqual(rec[0][0], "CONFIG_STALE")
        self.assertEqual(rec[0][1]["takes_effect"], "restart")

    def test_loaded_snapshot_untouched_by_write(self):
        """A live process keeps its OLD values — provably."""
        with TemporaryDirectory() as td:
            store = configstore.ConfigStore(write(td, VALID))
            cfg = store.load()
            store.set_key("armed_mode", True, reason="r", author="a",
                          expected_revision=1)
            self.assertEqual(cfg["armed_mode"], False)   # old snapshot
            self.assertEqual(store.load()["armed_mode"], True)


if __name__ == "__main__":
    unittest.main()
