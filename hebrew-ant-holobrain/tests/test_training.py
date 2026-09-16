from __future__ import annotations

import unittest

import torch

from holobrain.model import HolobrainConfig, TinyHolobrain
from holobrain.training import AutonomousAnt


class TrainingTests(unittest.TestCase):
    def test_shadow_trains_while_active_stays_immutable(self) -> None:
        ant = AutonomousAnt(TinyHolobrain(HolobrainConfig("ant", 11)))
        active_before = ant.active.fingerprint()
        shadow_before = ant.shadow.fingerprint()
        loss = ant.self_supervised_step(audio=torch.randn(2, 1, 4096))
        self.assertGreater(loss, 0)
        self.assertEqual(ant.active.fingerprint(), active_before)
        self.assertNotEqual(ant.shadow.fingerprint(), shadow_before)

    def test_promotion_requires_provenance_safety_and_gain(self) -> None:
        ant = AutonomousAnt(TinyHolobrain(HolobrainConfig("ant", 12)))
        ant.self_supervised_step(audio=torch.randn(2, 1, 4096))
        denied = ant.promote(
            active_metric=1.0,
            candidate_metric=1.1,
            provenance_passed=False,
            safety_passed=True,
        )
        self.assertFalse(denied.promoted)
        accepted = ant.promote(
            active_metric=1.0,
            candidate_metric=1.1,
            provenance_passed=True,
            safety_passed=True,
        )
        self.assertTrue(accepted.promoted)
        self.assertIsNotNone(ant.rollback_state)


if __name__ == "__main__":
    unittest.main()
