from pathlib import Path
import unittest

from antvoice.config import AntVoiceConfig, estimate_trainable_parameters


PROJECT = Path(__file__).resolve().parents[1]


class ConfigTests(unittest.TestCase):
    def test_tiny_config_is_valid_and_small(self) -> None:
        config = AntVoiceConfig.from_json(PROJECT / "configs" / "tiny.json")
        self.assertEqual(config.seed, 190071)
        self.assertEqual(config.encoder_downsample_factor, 16)
        self.assertLess(estimate_trainable_parameters(config), 1_000_000)

    def test_production_config_is_190m_scale_without_allocating_model(self) -> None:
        config = AntVoiceConfig.from_json(PROJECT / "configs" / "antvoice_190m.json")
        self.assertEqual(config.seed, 190071)
        self.assertEqual(config.encoder_downsample_factor, 32)
        self.assertEqual(estimate_trainable_parameters(config), 188_665_858)

    def test_config_rejects_even_temporal_kernel(self) -> None:
        raw = {
            "name": "invalid",
            "seed": 1,
            "sample_rate": 16000,
            "encoder_channels": [8],
            "encoder_kernels": [7],
            "encoder_strides": [4],
            "d_model": 16,
            "temporal_layers": 1,
            "temporal_heads": 4,
            "temporal_ffn_dim": 32,
            "temporal_conv_kernel": 4,
            "codebook_size": 8,
            "vq_commitment_cost": 0.25,
            "world_dim": 16,
            "world_layers": 1,
            "world_heads": 4,
            "world_ffn_dim": 32,
            "max_frames": 64,
            "dropout": 0.0,
            "boundary_target_rate": 0.1,
            "reconstruction_weight": 1.0,
            "vq_weight": 1.0,
            "world_weight": 1.0,
            "boundary_weight": 1.0,
        }
        with self.assertRaisesRegex(ValueError, "must be odd"):
            AntVoiceConfig.from_dict(raw)


if __name__ == "__main__":
    unittest.main()
