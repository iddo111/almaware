from __future__ import annotations

import unittest
from unittest import mock

import ramchat_acceptance


class AcceptanceTests(unittest.TestCase):
    def test_pass_requires_every_participant_and_both_mappings(self) -> None:
        roster = {
            name: {"status": "alive", "detail": "ok", "fails": 0}
            for name in ramchat_acceptance.REQUIRED_AI
        }
        with mock.patch.object(ramchat_acceptance.roster_probe, "probe_all", return_value=roster), mock.patch.object(
            ramchat_acceptance, "validate_mapping", return_value={"status": "PASS"}
        ):
            self.assertEqual(ramchat_acceptance.build_result()["status"], "PASS")

    def test_one_unverified_participant_fails_full_house(self) -> None:
        roster = {
            name: {"status": "alive", "detail": "ok", "fails": 0}
            for name in ramchat_acceptance.REQUIRED_AI
        }
        roster["deskclod"] = {"status": "unknown", "detail": "nonce missing", "fails": 1}
        with mock.patch.object(ramchat_acceptance.roster_probe, "probe_all", return_value=roster), mock.patch.object(
            ramchat_acceptance, "validate_mapping", return_value={"status": "PASS"}
        ):
            result = ramchat_acceptance.build_result()
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["missing_or_unverified"], ["deskclod"])


if __name__ == "__main__":
    unittest.main()
