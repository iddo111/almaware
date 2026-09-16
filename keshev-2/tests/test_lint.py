"""Lint gates: the repo is clean AND every gate can fire (self-test law)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import lint  # noqa: E402


class SelfTest(unittest.TestCase):

    def test_every_gate_fires_on_its_violation(self):
        """A lint gate that cannot fire is not shipped — mechanically."""
        fired = lint.self_test()
        dead = [name for name, hit in fired.items() if not hit]
        self.assertEqual(dead, [],
                         f"lint gates that CANNOT FIRE: {dead}")

    def test_every_gate_has_a_self_test_sample(self):
        self.assertEqual(set(lint.GATES), set(lint._SELF_TEST_SAMPLES),
                         "a gate without a firing sample is unprovable")


class RepoClean(unittest.TestCase):

    def test_production_passes_all_gates(self):
        results = lint.run()
        dirty = {k: v for k, v in results.items() if v}
        self.assertEqual(dirty, {})

    def test_production_surface_is_nonempty(self):
        """Guard the guard: if production_files() breaks and returns [],
        every gate 'passes' over nothing."""
        self.assertGreaterEqual(len(lint.production_files()), 7)


class AppEntry(unittest.TestCase):
    """The app assembles and halts honestly on bad config."""

    def test_config_halt_is_loud_exit_2(self):
        from unittest import mock
        from k2 import app, interlock
        with mock.patch.object(app, "CONFIG_PATH",
                               Path(r"C:\no\such\config.json")), \
             mock.patch.object(interlock, "acquire_own_mutex_or_exit",
                               lambda *a, **k: 1), \
             mock.patch.object(app.interlock, "acquire_own_mutex_or_exit",
                               lambda *a, **k: 1):
            rc = app.main([])
        self.assertEqual(rc, app.EXIT_CONFIG_HALT)


if __name__ == "__main__":
    unittest.main()
