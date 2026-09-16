from __future__ import annotations

import unittest

import torch

from holobrain.model import DevelopmentStage, HolobrainConfig, TinyHolobrain


class ModelTests(unittest.TestCase):
    def test_individual_seeds_produce_distinct_weights(self) -> None:
        a = TinyHolobrain(HolobrainConfig("a", 1))
        b = TinyHolobrain(HolobrainConfig("b", 2))
        self.assertNotEqual(a.fingerprint(), b.fingerprint())

    def test_same_seed_is_reproducible(self) -> None:
        a = TinyHolobrain(HolobrainConfig("a", 3))
        b = TinyHolobrain(HolobrainConfig("a", 3))
        self.assertEqual(a.fingerprint(), b.fingerprint())

    def test_voice_stage_forbids_symbols_and_disables_motor(self) -> None:
        model = TinyHolobrain(HolobrainConfig("a", 4))
        audio = torch.randn(2, 1, 4096)
        output = model(audio=audio)
        self.assertEqual(output["vocal_controls"].shape, (2, 16))
        self.assertFalse(output["vision_enabled"])
        self.assertFalse(output["reasoning_enabled"])
        self.assertFalse(output["motor_enabled"])
        with self.assertRaisesRegex(ValueError, "forbidden"):
            model(audio=audio, symbols=torch.ones(2, 3, dtype=torch.long))

    def test_later_stage_enables_all_modalities(self) -> None:
        model = TinyHolobrain(
            HolobrainConfig(
                "a", 5, stage=DevelopmentStage.REASONING_MOTOR
            )
        )
        output = model(
            audio=torch.randn(2, 1, 4096),
            vision=torch.randn(2, 3, 64, 64),
            symbols=torch.ones(2, 3, dtype=torch.long),
        )
        self.assertTrue(output["vision_enabled"])
        self.assertTrue(output["symbols_enabled"])
        self.assertTrue(output["reasoning_enabled"])
        self.assertTrue(output["motor_enabled"])
        self.assertEqual(output["motor_actions"].shape, (2, 12))


if __name__ == "__main__":
    unittest.main()
