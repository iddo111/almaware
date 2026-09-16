from pathlib import Path
import unittest

from antvoice.run_config import RunConfig


PROJECT = Path(__file__).resolve().parents[1]


class RunConfigTests(unittest.TestCase):
    def test_canary_is_hard_bounded_and_hebrew_verified(self) -> None:
        config = RunConfig.from_json(
            PROJECT / "configs" / "real_audio_canary.json"
        )
        self.assertLessEqual(config.steps_per_session, 64)
        self.assertLessEqual(config.max_wall_seconds, 900)
        self.assertTrue(config.require_verified_hebrew)
        self.assertEqual(config.num_workers, 0)

    def test_long_trainer_is_resumable_session_config(self) -> None:
        config = RunConfig.from_json(
            PROJECT / "configs" / "real_audio_train.json"
        )
        self.assertGreater(config.steps_per_session, 100_000)
        self.assertGreater(config.max_wall_seconds, 3_600)
        self.assertTrue(config.require_verified_hebrew)
        self.assertGreater(config.min_free_gib, 0)
        self.assertLessEqual(config.max_gpu_temp_c, 80.0)

    def test_nonzero_workers_are_rejected_for_exact_resume(self) -> None:
        raw = RunConfig.from_json(
            PROJECT / "configs" / "real_audio_canary.json"
        ).to_dict()
        raw["num_workers"] = 2
        with self.assertRaisesRegex(ValueError, "num_workers must remain 0"):
            RunConfig.from_dict(raw)


if __name__ == "__main__":
    unittest.main()
