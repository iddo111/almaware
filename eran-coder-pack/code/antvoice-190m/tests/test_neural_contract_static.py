import ast
from pathlib import Path
import unittest


PROJECT = Path(__file__).resolve().parents[1]
MODEL = PROJECT / "src" / "antvoice" / "model.py"
SMOKE = PROJECT / "src" / "antvoice" / "smoke_train.py"


def _class_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
    }


class NeuralContractStaticTests(unittest.TestCase):
    def test_model_source_has_every_required_neural_component(self) -> None:
        self.assertLessEqual(
            {
                "WaveformEncoder",
                "TemporalConformerBlock",
                "TemporalStack",
                "VectorQuantizer",
                "CausalUnitWorldModel",
                "WaveformDecoder",
                "AntVoiceModel",
            },
            _class_names(MODEL),
        )

    def test_model_has_no_pretrained_or_adapter_loading_route(self) -> None:
        source = MODEL.read_text(encoding="utf-8").lower()
        forbidden = {
            "from_pretrained",
            "load_state_dict",
            "load_state_dict_from_url",
            "torch.hub",
            "transformers",
            "torchaudio",
            "speech_recognition",
            "lora",
            "qlora",
        }
        self.assertFalse({token for token in forbidden if token in source})

    def test_explicit_seed_initializer_and_windows_runtime_block_are_present(
        self,
    ) -> None:
        source = MODEL.read_text(encoding="utf-8")
        self.assertIn("initialize_from_explicit_seed(model, config.seed)", source)
        self.assertIn("generator.manual_seed(_subseed(seed, name))", source)
        self.assertIn('if os.name == "nt":', source)

    def test_smoke_contract_is_synthetic_and_rejected_for_acceptance(self) -> None:
        source = SMOKE.read_text(encoding="utf-8")
        self.assertIn("SYNTHETIC_AUDIO_NEURAL_SMOKE_TEST", source)
        self.assertIn("REJECTED_FOR_ANT_FARM_ACCEPTANCE", source)
        self.assertIn("changed_tensor_count", source)
        self.assertIn("component_gradient_norms", source)
        self.assertIn("checkpoint_before_sha256", source)
        self.assertIn("checkpoint_after_sha256", source)
        self.assertIn("model_state_before_sha256", source)
        self.assertIn("model_state_after_sha256", source)
        self.assertIn('if os.name == "nt":', source)

    def test_all_python_sources_parse_without_importing_neural_runtime(self) -> None:
        for path in sorted((PROJECT / "src").rglob("*.py")):
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


if __name__ == "__main__":
    unittest.main()
