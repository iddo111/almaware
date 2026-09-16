from __future__ import annotations

import unittest
from pathlib import Path

from holobrain.colony import ColonyRuntime


ROOT = Path(__file__).resolve().parents[1]


class ColonyTests(unittest.TestCase):
    def test_queen_and_four_ants_are_independent(self) -> None:
        colony = ColonyRuntime(ROOT / "config" / "colony.json")
        inventory = colony.inventory()
        self.assertEqual(len(inventory["ants"]), 4)
        fingerprints = [inventory["queen"]["fingerprint"]]
        fingerprints.extend(item["fingerprint"] for item in inventory["ants"])
        self.assertEqual(len(set(fingerprints)), 5)
        self.assertFalse(inventory["pretrained_weights"])


if __name__ == "__main__":
    unittest.main()
