from __future__ import annotations

import unittest
from pathlib import Path

from holobrain.society import SocietyRuntime


ROOT = Path(__file__).resolve().parents[1]


class SocietyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.society = SocietyRuntime(ROOT / "config" / "communities.json")

    def test_identities_are_fixed_unique_and_not_reproducible(self) -> None:
        inventory = self.society.inventory()
        self.assertFalse(inventory["allow_spawn"])
        self.assertFalse(inventory["allow_delete_identity"])
        self.assertEqual(len(inventory["fixed_identities"]), 6)
        self.assertEqual(len(set(inventory["fixed_identities"])), 6)
        with self.assertRaisesRegex(RuntimeError, "reproduction"):
            self.society.spawn_ant("new-ant")
        with self.assertRaisesRegex(RuntimeError, "deletion"):
            self.society.delete_identity("nema-aleph")

    def test_communities_have_separate_queens_and_namespaces(self) -> None:
        inventory = self.society.inventory()
        self.assertEqual(len(inventory["communities"]), 2)
        namespaces = {
            item["storage_namespace"] for item in inventory["communities"]
        }
        queens = {
            item["queen"]["model_id"] for item in inventory["communities"]
        }
        self.assertEqual(len(namespaces), 2)
        self.assertEqual(len(queens), 2)

    def test_cross_community_bridge_is_closed(self) -> None:
        decision = self.society.exchange(
            source_community="modern-hebrew-home",
            target_community="traditional-hebrew-home",
            payload_kind="reviewed_event_summary",
        )
        self.assertFalse(decision.delivered)
        self.assertIn("closed", decision.reason)

    def test_weight_and_private_replay_are_forbidden_even_if_opened_later(self) -> None:
        self.society.bridge_policy["enabled"] = True
        for kind in ("weights", "optimizer_state", "private_replay", "raw_audio"):
            decision = self.society.exchange(
                source_community="modern-hebrew-home",
                target_community="traditional-hebrew-home",
                payload_kind=kind,
            )
            self.assertFalse(decision.delivered)


if __name__ == "__main__":
    unittest.main()
