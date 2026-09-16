"""K1 acceptance tests for client/configstore.py — written FIRST (TDD).

PHASE2-DESIGN.md K1 row + section 5, scars 39-42 (PHASE1-INQUIRY.md section 2):

  * CAS refuses stale revision (loud, file unchanged, no history line)
  * unknown keys survive a round-trip (read-as-dict, never dataclass)
  * corrupt/missing JSON -> HALT: MessageBox stub called + SystemExit(2);
    the defaults-fallback path DOES NOT EXIST (scar 40)
  * gate inside its own recorded noise band (or above measured speech) ->
    refused, on load AND on set (scar 41)
  * a knob change outside the recorded calibration band is refused unless
    the calibration record itself is updated
  * every `set` appends {ts,key,old,new,reason,author,revision} to the
    history JSONL (scar 39)
  * NO write-on-exit path exists (grep assert: json.dump only inside
    configstore, no atexit anywhere under client/)
  * owner_gate_typing flip refused without a PASS gate18-*.json report (5)
  * server_url validator rejects 0.0.0.0 and non-fleet hosts (5)
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

from client import configstore  # noqa: E402
from client.configstore import (  # noqa: E402
    CASError,
    CalibrationError,
    ConfigCorruptError,
    ConfigInvalidError,
    ConfigMissingError,
    ConfigStore,
    RefusedError,
)
import lint  # noqa: E402


def valid_config() -> dict:
    """A schema-valid 12-key config (mirrors design section 5 example)."""
    return {
        "revision": 0,
        "mic_name": "Logitech BRIO",
        "server_url": "http://<lan-ip>:8737/",
        "auth_token_file": "state\\stt-token",
        "gate_rms": {
            "value": 0.004,
            "calibrated_at": "2026-08-12T09:00:00+03:00",
            "method": "keshevctl calibrate",
            "measured_floor": 0.0009,
            "measured_speech": 0.0182,
            "author": "claude-cli",
        },
        "stale_sec": 25,
        "hotkey_pause": "ctrl+alt+m",
        "auto_enter": False,
        "clipboard_restore": False,
        "extra_avoid": [],
        "corpus_capture": False,
        "owner_gate_typing": False,
    }


class StoreCase(unittest.TestCase):
    """Base: a temp dir with a valid config + isolated history/reports paths."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory(prefix="keshev-cfg-")
        self.addCleanup(self._td.cleanup)
        self.dir = Path(self._td.name)
        self.cfg_path = self.dir / "client.json"
        self.hist_path = self.dir / "config_history.jsonl"
        self.reports_dir = self.dir / "reports"
        self.reports_dir.mkdir()
        self.write_cfg(valid_config())
        self.store = ConfigStore(
            self.cfg_path, history_path=self.hist_path, reports_dir=self.reports_dir
        )

    def write_cfg(self, obj) -> None:
        self.cfg_path.write_text(
            json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def raw(self) -> dict:
        return json.loads(self.cfg_path.read_text(encoding="utf-8"))

    def history_lines(self) -> list[dict]:
        if not self.hist_path.exists():
            return []
        return [
            json.loads(ln)
            for ln in self.hist_path.read_text(encoding="utf-8").splitlines()
            if ln.strip()
        ]


# ---------------------------------------------------------------- load

class TestLoad(StoreCase):
    def test_load_valid_returns_all_keys(self):
        cfg = self.store.load()
        for key in valid_config():
            self.assertIn(key, cfg)
        self.assertEqual(cfg["stale_sec"], 25)

    def test_load_preserves_unknown_keys(self):
        obj = valid_config()
        obj["future_knob"] = {"nested": True}
        self.write_cfg(obj)
        cfg = self.store.load()
        self.assertEqual(cfg["future_knob"], {"nested": True})

    def test_load_corrupt_json_raises(self):
        self.cfg_path.write_text("{ this is not json", encoding="utf-8")
        with self.assertRaises(ConfigCorruptError):
            self.store.load()

    def test_load_missing_file_raises(self):
        self.cfg_path.unlink()
        with self.assertRaises(ConfigMissingError):
            self.store.load()

    def test_load_missing_required_key_raises(self):
        obj = valid_config()
        del obj["stale_sec"]
        self.write_cfg(obj)
        with self.assertRaises(ConfigInvalidError):
            self.store.load()

    def test_load_type_violation_raises(self):
        obj = valid_config()
        obj["stale_sec"] = "25"  # string, not int
        self.write_cfg(obj)
        with self.assertRaises(ConfigInvalidError):
            self.store.load()

    def test_load_range_violation_raises(self):
        obj = valid_config()
        obj["stale_sec"] = 900
        self.write_cfg(obj)
        with self.assertRaises(ConfigInvalidError):
            self.store.load()

    def test_load_bool_key_rejects_int(self):
        obj = valid_config()
        obj["auto_enter"] = 1  # int is not bool (isinstance trap)
        self.write_cfg(obj)
        with self.assertRaises(ConfigInvalidError):
            self.store.load()

    def test_load_gate_inside_noise_band_raises(self):
        obj = valid_config()
        obj["gate_rms"]["value"] = 0.0005  # below measured_floor 0.0009
        self.write_cfg(obj)
        with self.assertRaises(CalibrationError):
            self.store.load()

    def test_load_gate_above_measured_speech_raises(self):
        obj = valid_config()
        obj["gate_rms"]["value"] = 0.070  # scar 40's deaf gate, above 0.0182
        self.write_cfg(obj)
        with self.assertRaises(CalibrationError):
            self.store.load()


# ---------------------------------------------------------------- HALT

class TestHalt(StoreCase):
    """Corrupt/missing config -> MessageBox + exit 2. No defaults fallback."""

    def setUp(self):
        super().setUp()
        self.boxes: list[tuple[str, str]] = []
        self._orig_box = configstore._message_box
        configstore._message_box = lambda title, text: self.boxes.append((title, text))
        self.addCleanup(setattr, configstore, "_message_box", self._orig_box)

    def test_corrupt_config_halts_exit_2_and_shows_box(self):
        self.cfg_path.write_text("### not json ###", encoding="utf-8")
        with self.assertRaises(SystemExit) as cm:
            self.store.load_or_halt()
        self.assertEqual(cm.exception.code, 2)
        self.assertEqual(len(self.boxes), 1)
        self.assertIn("KESHEV", self.boxes[0][0])

    def test_missing_config_halts_exit_2_never_defaults(self):
        self.cfg_path.unlink()
        with self.assertRaises(SystemExit) as cm:
            self.store.load_or_halt()
        self.assertEqual(cm.exception.code, 2)
        self.assertEqual(len(self.boxes), 1)

    def test_invalid_schema_halts_exit_2(self):
        obj = valid_config()
        obj["gate_rms"]["value"] = 0.070
        self.write_cfg(obj)
        with self.assertRaises(SystemExit) as cm:
            self.store.load_or_halt()
        self.assertEqual(cm.exception.code, 2)

    def test_no_defaults_fallback_path_exists_in_source(self):
        src = (REPO / "client" / "configstore.py").read_text(encoding="utf-8")
        self.assertNotIn("DEFAULT_CONFIG", src)
        self.assertNotIn("fallback_config", src)


# ---------------------------------------------------------------- CAS + set

class TestSetCAS(StoreCase):
    def test_set_happy_path_bumps_revision(self):
        cfg = self.store.set(
            "stale_sec", 30, reason="test bump", author="pytest", expected_revision=0
        )
        self.assertEqual(cfg["stale_sec"], 30)
        self.assertEqual(cfg["revision"], 1)
        self.assertEqual(self.raw()["revision"], 1)

    def test_cas_refuses_stale_revision(self):
        self.store.set("stale_sec", 30, reason="r1", author="a", expected_revision=0)
        with self.assertRaises(CASError):
            self.store.set("stale_sec", 40, reason="r2", author="b", expected_revision=0)
        # file unchanged by the refused write, and no history line for it
        self.assertEqual(self.raw()["stale_sec"], 30)
        self.assertEqual(len(self.history_lines()), 1)

    def test_unknown_keys_survive_a_set_roundtrip(self):
        obj = valid_config()
        obj["beam_size"] = 5  # THE scar-39 key that vanished in alma-mic
        obj["en_model"] = "whisper-small"
        self.write_cfg(obj)
        self.store.set("stale_sec", 20, reason="r", author="a", expected_revision=0)
        after = self.raw()
        self.assertEqual(after["beam_size"], 5)
        self.assertEqual(after["en_model"], "whisper-small")

    def test_set_unknown_key_refused(self):
        with self.assertRaises(RefusedError):
            self.store.set("brand_new_knob", 1, reason="r", author="a", expected_revision=0)

    def test_set_revision_directly_refused(self):
        with self.assertRaises(RefusedError):
            self.store.set("revision", 99, reason="r", author="a", expected_revision=0)

    def test_set_requires_nonempty_reason_and_author(self):
        with self.assertRaises(RefusedError):
            self.store.set("stale_sec", 30, reason="", author="a", expected_revision=0)
        with self.assertRaises(RefusedError):
            self.store.set("stale_sec", 30, reason="r", author="", expected_revision=0)

    def test_set_validates_type(self):
        with self.assertRaises(ConfigInvalidError):
            self.store.set("stale_sec", "30", reason="r", author="a", expected_revision=0)

    def test_set_refuses_on_corrupt_config(self):
        self.cfg_path.write_text("broken{", encoding="utf-8")
        with self.assertRaises(ConfigCorruptError):
            self.store.set("stale_sec", 30, reason="r", author="a", expected_revision=0)


# ---------------------------------------------------------------- history

class TestHistory(StoreCase):
    def test_every_set_appends_history_line(self):
        self.store.set("stale_sec", 30, reason="first", author="pytest", expected_revision=0)
        self.store.set("auto_enter", True, reason="second", author="pytest", expected_revision=1)
        lines = self.history_lines()
        self.assertEqual(len(lines), 2)
        first, second = lines
        self.assertEqual(first["key"], "stale_sec")
        self.assertEqual(first["old"], 25)
        self.assertEqual(first["new"], 30)
        self.assertEqual(first["reason"], "first")
        self.assertEqual(first["author"], "pytest")
        self.assertEqual(first["revision"], 1)
        self.assertIn("ts", first)
        self.assertEqual(second["key"], "auto_enter")
        self.assertEqual(second["revision"], 2)

    def test_history_is_append_only_across_sets(self):
        for i in range(3):
            self.store.set("stale_sec", 26 + i, reason=f"r{i}", author="a", expected_revision=i)
        revs = [ln["revision"] for ln in self.history_lines()]
        self.assertEqual(revs, [1, 2, 3])


# ---------------------------------------------------------------- calibration band

class TestCalibrationBand(StoreCase):
    def test_scalar_gate_change_inside_band_ok_and_preserves_record(self):
        self.store.set("gate_rms", 0.006, reason="r", author="a", expected_revision=0)
        rec = self.raw()["gate_rms"]
        self.assertEqual(rec["value"], 0.006)
        self.assertEqual(rec["measured_floor"], 0.0009)  # calibration kept
        self.assertEqual(rec["measured_speech"], 0.0182)
        self.assertEqual(rec["calibrated_at"], "2026-08-12T09:00:00+03:00")

    def test_scalar_gate_change_below_band_refused(self):
        with self.assertRaises(CalibrationError):
            self.store.set("gate_rms", 0.0005, reason="r", author="a", expected_revision=0)
        self.assertEqual(self.raw()["gate_rms"]["value"], 0.004)

    def test_scalar_gate_change_above_band_refused(self):
        with self.assertRaises(CalibrationError):
            self.store.set("gate_rms", 0.05, reason="r", author="a", expected_revision=0)

    def test_full_recalibration_with_new_band_accepted(self):
        new_rec = {
            "value": 0.03,
            "calibrated_at": "2026-08-13T09:00:00+03:00",
            "method": "keshevctl calibrate",
            "measured_floor": 0.008,
            "measured_speech": 0.09,
            "author": "pytest",
        }
        self.store.set("gate_rms", new_rec, reason="recalibrated", author="pytest",
                       expected_revision=0)
        self.assertEqual(self.raw()["gate_rms"]["value"], 0.03)

    def test_full_record_with_value_outside_its_own_band_refused(self):
        new_rec = {
            "value": 0.004,  # inside its own floor band below
            "calibrated_at": "2026-08-13T09:00:00+03:00",
            "method": "keshevctl calibrate",
            "measured_floor": 0.008,
            "measured_speech": 0.09,
            "author": "pytest",
        }
        with self.assertRaises(CalibrationError):
            self.store.set("gate_rms", new_rec, reason="r", author="a", expected_revision=0)

    def test_calibration_record_missing_fields_refused(self):
        with self.assertRaises(ConfigInvalidError):
            self.store.set("gate_rms", {"value": 0.005}, reason="r", author="a",
                           expected_revision=0)

    def test_drift_check_warns_when_live_floor_reaches_gate(self):
        cfg = self.store.load()
        self.assertIsNone(self.store.drift_check(cfg, live_floor=0.001))  # healthy
        warn = self.store.drift_check(cfg, live_floor=0.006)  # floor above gate
        self.assertIsNotNone(warn)
        self.assertIn("drift", warn.lower())


# ---------------------------------------------------------------- guarded knobs

class TestGuardedKnobs(StoreCase):
    def test_owner_gate_typing_refused_without_gate18_report(self):
        with self.assertRaises(RefusedError):
            self.store.set("owner_gate_typing", True, reason="r", author="a",
                           expected_revision=0)

    def test_owner_gate_typing_refused_with_fail_report(self):
        (self.reports_dir / "gate18-20260812.json").write_text(
            json.dumps({"verdict": "FAIL", "frr": 0.09}), encoding="utf-8")
        with self.assertRaises(RefusedError):
            self.store.set("owner_gate_typing", True, reason="r", author="a",
                           expected_revision=0)

    def test_owner_gate_typing_allowed_with_pass_report(self):
        (self.reports_dir / "gate18-20260812.json").write_text(
            json.dumps({"verdict": "PASS", "frr": 0.007, "theta": 0.62}),
            encoding="utf-8")
        cfg = self.store.set("owner_gate_typing", True, reason="gate18 passed",
                             author="pytest", expected_revision=0)
        self.assertTrue(cfg["owner_gate_typing"])

    def test_owner_gate_typing_false_never_needs_report(self):
        cfg = self.store.set("owner_gate_typing", False, reason="stay off",
                             author="pytest", expected_revision=0)
        self.assertFalse(cfg["owner_gate_typing"])

    def test_server_url_rejects_0000(self):
        with self.assertRaises(ConfigInvalidError):
            self.store.set("server_url", "http://0.0.0.0:8737/", reason="r",
                           author="a", expected_revision=0)

    def test_server_url_rejects_non_fleet_host(self):
        with self.assertRaises(ConfigInvalidError):
            self.store.set("server_url", "http://evil.example.com:8737/", reason="r",
                           author="a", expected_revision=0)

    def test_server_url_accepts_fleet_hosts(self):
        cfg = self.store.set("server_url", "http://<lan-ip>:8737/",
                             reason="eran2 fallback host", author="pytest",
                             expected_revision=0)
        self.assertEqual(cfg["server_url"], "http://<lan-ip>:8737/")


# ---------------------------------------------------------------- structural

class TestStructural(unittest.TestCase):
    """The 'no write-on-exit path exists' grep asserts (scar 39 + K0 G3)."""

    def test_json_dump_only_inside_configstore(self):
        self.assertEqual(lint.gate_json_dump(REPO), [])

    def test_no_atexit_under_client(self):
        for p in sorted((REPO / "client").glob("*.py")):
            self.assertNotIn("atexit", p.read_text(encoding="utf-8"),
                             f"atexit (write-on-exit vector) found in {p.name}")

    def test_repo_lint_gates_all_pass(self):
        self.assertEqual(lint.run_all(REPO), [])

    def test_schema_file_matches_code_constant(self):
        """config/client.schema.json is generated from the code truth."""
        on_disk = json.loads(
            (REPO / "config" / "client.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(on_disk, configstore.schema_as_json())

    def test_tracked_client_json_is_valid(self):
        """The git-tracked config must itself load cleanly."""
        store = ConfigStore(REPO / "config" / "client.json")
        cfg = store.load()
        self.assertEqual(sorted(k for k in cfg if k in configstore.SCHEMA),
                         sorted(configstore.SCHEMA))


class TestOptionalKeys(StoreCase):
    """lang_hint (2026-08-16, the transliteration scar) is the first OPTIONAL
    schema key: configs written before it exist and must stay loadable — a
    required new key would HALT the running mic at its next restart, which is
    scar 40's halt firing on the wrong target."""

    def test_config_without_lang_hint_still_loads(self):
        # valid_config() predates lang_hint on purpose — this IS the test.
        cfg = self.store.load()
        self.assertNotIn("lang_hint", cfg)

    def test_lang_hint_value_is_validated_when_present(self):
        cfg = valid_config()
        cfg["lang_hint"] = "auto"
        self.write_cfg(cfg)
        self.assertEqual(self.store.load()["lang_hint"], "auto")

    def test_lang_hint_off_menu_value_refused_at_startup(self):
        """An off-menu hint would raise per-utterance inside langpolicy
        (ValueError on every decode) — the config layer refuses it ONCE,
        loudly, at load instead."""
        cfg = valid_config()
        cfg["lang_hint"] = "icelandic"
        self.write_cfg(cfg)
        with self.assertRaises(ConfigInvalidError):
            self.store.load()

    def test_lang_hint_settable_via_the_one_write_path(self):
        cfg = self.store.set("lang_hint", "he",
                             reason="hebrew-only session", author="pytest",
                             expected_revision=0)
        self.assertEqual(cfg["lang_hint"], "he")
        self.assertEqual(self.raw()["lang_hint"], "he")

    def test_required_keys_still_halt_when_missing(self):
        """`optional` must not have softened the scar-40 law for anyone else."""
        cfg = valid_config()
        del cfg["gate_rms"]
        self.write_cfg(cfg)
        with self.assertRaises(ConfigInvalidError):
            self.store.load()


if __name__ == "__main__":
    unittest.main()
