import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from foxalien_control.config import load_config


class ConfigTests(unittest.TestCase):
    def write_config(self, value):
        handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(value, handle)
        handle.close()
        self.addCleanup(lambda: os.unlink(handle.name))
        return Path(handle.name)

    def test_missing_config_defaults_to_simulation(self):
        config = load_config(Path("definitely-missing-machine-config.json"))
        self.assertTrue(config.simulation)
        self.assertFalse(config.hardware_gate_open)

    def test_serial_mode_fails_closed_without_physical_gates(self):
        path = self.write_config({"transport": {"mode": "serial"}})
        with self.assertRaisesRegex(ValueError, "Serial mode is locked"):
            load_config(path)

    def test_serial_mode_needs_process_phrase_and_all_gates(self):
        path = self.write_config(
            {
                "transport": {"mode": "serial"},
                "safety": {
                    "physical_estop_tested": True,
                    "spindle_power_isolated": True,
                    "motion_controller_verified": True,
                },
            }
        )
        with patch.dict(os.environ, {"FOXALIEN_HARDWARE_ENABLE": "I_ACCEPT_PHYSICAL_RISK"}):
            config = load_config(path)
            self.assertTrue(config.hardware_gate_open)

    def test_remote_bind_is_rejected(self):
        path = self.write_config({"server": {"host": "0.0.0.0"}})
        with self.assertRaisesRegex(ValueError, "localhost-only"):
            load_config(path)


if __name__ == "__main__":
    unittest.main()
