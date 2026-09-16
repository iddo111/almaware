import ast
from pathlib import Path
import unittest


PROJECT = Path(__file__).resolve().parents[1]
SOURCE = PROJECT / "src" / "antvoice"
NEURAL_FILES = (
    "model.py",
    "smoke_train.py",
    "audio_data.py",
    "evaluation.py",
    "checkpoints.py",
    "canary_train.py",
    "train.py",
)


class RealAudioPilotStaticTests(unittest.TestCase):
    def test_every_neural_file_blocks_windows_before_torch_import(self) -> None:
        for name in NEURAL_FILES:
            source = (SOURCE / name).read_text(encoding="utf-8")
            self.assertIn('if os.name == "nt":', source, name)
            self.assertIn("import torch", source, name)
            self.assertLess(
                source.index('if os.name == "nt":'),
                source.index("import torch"),
                name,
            )

    def test_long_trainer_checkpoints_every_required_resume_state(self) -> None:
        source = (SOURCE / "train.py").read_text(encoding="utf-8")
        for token in (
            '"model": model.state_dict()',
            '"optimizer": optimizer.state_dict()',
            '"scaler": scaler.state_dict()',
            '"rng": capture_rng_state()',
            '"sampler": sampler.state_dict()',
            '"training_state": training_state',
            "restore_rng_state",
            "sampler.load_state_dict",
            '"gradient_coverage": _serialized_gradient_coverage',
        ):
            self.assertIn(token, source)

    def test_resume_lineage_and_full_weight_contract_are_fail_closed(self) -> None:
        checkpoint_source = (
            SOURCE / "checkpoints.py"
        ).read_text(encoding="utf-8")
        trainer_source = (SOURCE / "train.py").read_text(encoding="utf-8")
        for token in (
            'RANDOM_INITIALIZATION_ORIGIN = "random_explicit_seed"',
            "resume checkpoint does not descend from random explicit seed",
            "resume parent artifact hash mismatch",
            "resume parent sidecar lineage mismatch",
            "verify_resume_lineage",
        ):
            self.assertIn(token, checkpoint_source)
        for token in (
            "_assert_full_parameter_contract",
            "optimizer parameter set does not equal all named parameters",
            "_update_gradient_coverage",
            "ALL_NAMED_PARAMETERS_RECEIVED_NONZERO_FINITE_GRADIENT",
            '"individual_tensor_change_measured": False',
        ):
            self.assertIn(token, trainer_source)

    def test_checkpoint_store_is_shadow_only_and_atomic(self) -> None:
        source = (SOURCE / "checkpoints.py").read_text(encoding="utf-8")
        self.assertIn('self.shadow_root = self.run_root / "shadow"', source)
        self.assertIn('self.active_root = self.run_root / "active"', source)
        self.assertIn("os.replace(temporary_name, destination)", source)
        self.assertIn("trainer must never write inside active", source)
        self.assertIn("immutable shadow checkpoint already exists", source)

    def test_promotion_is_separate_and_dry_run_by_default(self) -> None:
        train_source = (SOURCE / "train.py").read_text(encoding="utf-8")
        promote_source = (SOURCE / "promote.py").read_text(encoding="utf-8")
        self.assertNotIn("from .promote", train_source)
        self.assertIn('"execution": "EXECUTED" if execute else "DRY_RUN"', promote_source)
        self.assertIn('active_root / "releases"', promote_source)
        self.assertIn("promotion_eligible", promote_source)

    def test_launchers_default_to_dry_run(self) -> None:
        for name in (
            "run_real_canary.sh",
            "run_full_train.sh",
            "promote_shadow.sh",
        ):
            source = (PROJECT / "scripts" / name).read_text(encoding="utf-8")
            self.assertIn('EXECUTE="${EXECUTE:-0}"', source, name)
            self.assertIn("DRY_RUN", source, name)

    def test_systemd_examples_are_not_installable_by_default(self) -> None:
        systemd = PROJECT / "ops" / "systemd"
        for path in systemd.glob("*.example"):
            source = path.read_text(encoding="utf-8")
            self.assertIn("EXAMPLE ONLY", source, path.name)
            self.assertNotIn("[Install]", source, path.name)
        trainer = (
            systemd / "antvoice-trainer.service.example"
        ).read_text(encoding="utf-8")
        self.assertIn("ConditionPathExists=/etc/antvoice/ENABLE_TRAINING", trainer)
        self.assertIn("Environment=EXECUTE=0", trainer)

    def test_no_text_or_pretrained_learning_dependency(self) -> None:
        runtime_sources = "\n".join(
            (SOURCE / name).read_text(encoding="utf-8").lower()
            for name in ("audio_data.py", "canary_train.py", "train.py")
        )
        for forbidden in (
            "from_pretrained",
            "transformers",
            "torchaudio",
            "speech_recognition",
            "lora",
            "qlora",
        ):
            self.assertNotIn(forbidden, runtime_sources)
        self.assertIn('"transcripts_or_text_used": false', runtime_sources)
        self.assertIn('"pretrained_components_used": false', runtime_sources)

    def test_all_new_python_sources_parse_without_import(self) -> None:
        for path in sorted(SOURCE.glob("*.py")):
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


if __name__ == "__main__":
    unittest.main()
