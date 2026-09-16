"""Unit tests that inspect source/configuration without importing Torch."""

from __future__ import annotations

import ast
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


def load_tool(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ScaffoldTests(unittest.TestCase):
    def test_training_sources_parse_but_are_not_imported(self):
        for path in (ROOT / "training").glob("*.py"):
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    def test_no_offload_in_deepspeed(self):
        config = json.loads(
            (ROOT / "configs" / "deepspeed-zero3-adafactor.json").read_text(
                encoding="utf-8"
            )
        )
        zero = config["zero_optimization"]
        self.assertEqual(zero["stage"], 3)
        self.assertNotIn("offload_optimizer", zero)
        self.assertNotIn("offload_param", zero)
        self.assertFalse(zero["stage3_gather_16bit_weights_on_model_save"])
        self.assertTrue(
            any(
                "Qwen3_5MoeSparseMoeBlock" in name
                for name in zero["leaf_module"]["classes"]
            )
        )

    def test_factored_adafactor_policy(self):
        config = json.loads(
            (ROOT / "configs" / "training-defaults.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(config["optimizer"]["name"], "Adafactor")
        self.assertTrue(config["optimizer"]["factored"])
        self.assertIsNone(config["optimizer"]["beta1"])
        self.assertFalse(config["offload"]["cpu"])
        self.assertFalse(config["offload"]["nvme"])

    def test_checkpoint_compare_requires_every_tensor(self):
        tool = load_tool(
            "checkpoint_hash_tool",
            ROOT / "tools" / "checkpoint-tensor-hashes.py",
        )
        before = {
            "tensors": {
                "a": {"sha256": "one", "dtype": "BF16", "shape": [1]},
                "b": {"sha256": "two", "dtype": "BF16", "shape": [1]},
            }
        }
        after = {
            "tensors": {
                "a": {"sha256": "changed", "dtype": "BF16", "shape": [1]},
                "b": {"sha256": "two", "dtype": "BF16", "shape": [1]},
            }
        }
        result = tool.compare(before, after, require_all_changed=True)
        self.assertFalse(result["pass"])
        self.assertEqual(result["unchanged_count"], 1)

    def test_checkpoint_compare_detects_unchanged_expert_slice(self):
        tool = load_tool(
            "checkpoint_hash_tool_experts",
            ROOT / "tools" / "checkpoint-tensor-hashes.py",
        )
        common = {
            "dtype": "BF16",
            "shape": [2, 4, 4],
            "sha256": "whole-before",
            "expert_axis0_sha256": ["expert-zero", "expert-one"],
        }
        before = {"tensors": {"layer.experts.weight": common}}
        after = {
            "tensors": {
                "layer.experts.weight": {
                    **common,
                    "sha256": "whole-after",
                    "expert_axis0_sha256": ["expert-zero-changed", "expert-one"],
                }
            }
        }
        result = tool.compare(before, after, require_all_changed=True)
        self.assertFalse(result["pass"])
        self.assertEqual(result["unchanged_expert_slice_count"], 1)

    def test_qwen35_full_checkpoints_require_images(self):
        catalog = json.loads(
            (ROOT / "configs" / "model-catalog.json").read_text(encoding="utf-8")
        )
        for key in ("smoke_2b", "target_9b", "max_multimodal_35b_a3b"):
            self.assertEqual(catalog["models"][key]["modalities"], ["image_text"])

    def test_qualification_does_not_gather_full_zero3_checkpoint(self):
        source = (ROOT / "training" / "fullweight_train.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("accelerator.save_state", source)
        self.assertNotIn("accelerator.get_state_dict", source)

    def test_multimodal_targets_and_exact_model_load_are_guarded(self):
        source = (ROOT / "training" / "fullweight_train.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('record.get("target")', source)
        self.assertIn("return_assistant_tokens_mask=True", source)
        self.assertIn("output_loading_info=True", source)
        self.assertIn("verify_optimizer_coverage", source)

    def test_gradient_proof_rejects_nonfinite_and_rank_drift(self):
        source = (ROOT / "training" / "gradient_probe.py").read_text(
            encoding="utf-8"
        )
        verifier = (ROOT / "tools" / "gradient-coverage-proof.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("nonfinite_gradient_seen", source)
        self.assertIn("parameter_inventory_sha256", source)
        self.assertIn("nonfinite_gradient_seen", verifier)
        self.assertIn('payload.get("schema_version") == 3', verifier)

    def test_fsdp_does_not_double_checkpoint_activations(self):
        config = (ROOT / "configs" / "accelerate-fsdp.yaml").read_text(
            encoding="utf-8"
        )
        self.assertIn("fsdp_activation_checkpointing: false", config)

    def test_unverified_runtime_paths_are_hard_blocked(self):
        config = json.loads(
            (ROOT / "configs" / "training-defaults.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertTrue(config["runtime_capabilities"])
        self.assertFalse(any(config["runtime_capabilities"].values()))
        launcher = (ROOT / "launch" / "two-node.sh").read_text(encoding="utf-8")
        self.assertIn("runtime execution remains BLOCKED", launcher)
        source = (ROOT / "training" / "fullweight_train.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("require_verified_runtime_capabilities", source)

    def test_examples_are_nonlaunchable_placeholders(self):
        for path in (ROOT / "examples").glob("*.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["dataset_id"], "REPLACE_ME")
            for split in ("train", "validation"):
                self.assertTrue(payload["splits"][split][0]["path"].startswith("/REPLACE"))


if __name__ == "__main__":
    unittest.main()
