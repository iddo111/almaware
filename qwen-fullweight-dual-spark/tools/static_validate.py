"""Non-Torch static validation for the Windows authoring host."""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).parents[1]
BANNER_PREFIX = "> 🪟 **BROKEN WINDOWS LAW"
REQUIRED_MODEL_IDS = {
    "Qwen/Qwen3.5-2B-Base",
    "Qwen/Qwen3.5-9B-Base",
    "Qwen/Qwen3-30B-A3B-Base",
    "Qwen/Qwen3.5-35B-A3B-Base",
}
FORBIDDEN_IMPORTS = {"peft"}


def fail(message: str) -> None:
    raise AssertionError(message)


def validate_markdown() -> int:
    files = list(ROOT.rglob("*.md"))
    for path in files:
        first_line = path.read_text(encoding="utf-8").splitlines()[0]
        if not first_line.startswith(BANNER_PREFIX):
            fail(f"Broken Windows banner missing: {path}")
    return len(files)


def validate_json() -> int:
    files = list(ROOT.rglob("*.json"))
    for path in files:
        json.loads(path.read_text(encoding="utf-8"))
    return len(files)


def validate_python() -> int:
    files = list(ROOT.rglob("*.py"))
    for path in files:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = {alias.name.split(".")[0] for alias in node.names}
                if names & FORBIDDEN_IMPORTS:
                    fail(f"forbidden import in {path}: {names & FORBIDDEN_IMPORTS}")
            elif isinstance(node, ast.ImportFrom):
                module = (node.module or "").split(".")[0]
                if module in FORBIDDEN_IMPORTS:
                    fail(f"forbidden import in {path}: {module}")
            elif isinstance(node, ast.Call):
                if (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr == "requires_grad_"
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and node.args[0].value is False
                ):
                    fail(f"parameter freezing call in {path}:{node.lineno}")
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                value = node.value
                for target in targets:
                    if (
                        isinstance(target, ast.Attribute)
                        and target.attr == "requires_grad"
                        and isinstance(value, ast.Constant)
                        and value.value is False
                    ):
                        fail(f"parameter freezing assignment in {path}:{node.lineno}")
    return len(files)


def validate_catalog() -> None:
    catalog = json.loads(
        (ROOT / "configs" / "model-catalog.json").read_text(encoding="utf-8")
    )
    models = catalog["models"]
    ids = {entry["upstream_id"] for entry in models.values()}
    if ids != REQUIRED_MODEL_IDS:
        fail(f"qualification ladder mismatch: {sorted(ids)}")
    if models["max_text_30b_a3b"]["modalities"] != ["text"]:
        fail("30B candidate must be text-only")
    if models["smoke_2b"]["modalities"] != ["image_text"]:
        fail("Qwen3.5 2B full checkpoint must require image_text")
    if models["target_9b"]["modalities"] != ["image_text"]:
        fail("Qwen3.5 9B full checkpoint must require image_text")
    if models["max_multimodal_35b_a3b"]["modalities"] != ["image_text"]:
        fail("35B candidate must require image_text")


def validate_training_guards() -> None:
    source = (ROOT / "training" / "fullweight_train.py").read_text(encoding="utf-8")
    required = [
        "local_files_only=True",
        "trust_remote_code=False",
        "parameter.requires_grad_(True)",
        "DGX_FULLWEIGHT_EXECUTION",
        "max_steps > 10",
        "max_multimodal_35b_a3b",
        'manifest["modality"] != "image_text"',
        "HfDeepSpeedConfig",
        "configure_zero3_partitioned_loading",
        "processor.apply_chat_template",
        "return_assistant_tokens_mask=True",
        "output_loading_info=True",
        "verify_optimizer_coverage",
        "require_verified_runtime_capabilities",
        "accelerator.save_state",
    ]
    for marker in required:
        if marker not in source:
            fail(f"training safety marker missing: {marker}")
    if re.search(r"from_pretrained\([^)]*(?:https?://|revision=)", source, re.DOTALL):
        fail("network/revision model loading path found")
    if "accelerator.get_state_dict" in source:
        fail("full-rank checkpoint gather is forbidden in qualification loop")

    probe = (ROOT / "training" / "gradient_probe.py").read_text(encoding="utf-8")
    if 'reduction="sum"' not in probe or 'reduction="max"' in probe:
        fail("gradient proof must use portable sum-then-boolean reduction")
    for marker in (
        "nonfinite_gradient_seen",
        "parameter_inventory_sha256",
        "expert_route_observations",
    ):
        if marker not in probe:
            fail(f"gradient truth marker missing: {marker}")


def validate_launchers() -> None:
    launcher = (ROOT / "launch" / "two-node.sh").read_text(encoding="utf-8")
    required = [
        'DRY_RUN="${DRY_RUN:-1}"',
        "ALLOW_FULLWEIGHT_TRAINING",
        "ACK_NO_EXISTING_WORKLOAD_DISPLACEMENT",
        "ACK_MODEL_AND_DATA_DIGESTS_MATCH",
        "APPROVED_RUN_ID",
        "MAX_STEPS_OVERRIDE",
        "NCCL_SOCKET_IFNAME",
    ]
    for marker in required:
        if marker not in launcher:
            fail(f"launcher gate missing: {marker}")
    if "runtime execution remains BLOCKED" not in launcher:
        fail("non-dry-run execution must remain hard-blocked")
    fabric = (ROOT / "launch" / "fabric.env").read_text(encoding="utf-8")
    if "EXPECTED_LINK_MBPS=200000" not in fabric:
        fail("200G evidence expectation missing")
    deepspeed = json.loads(
        (ROOT / "configs" / "deepspeed-zero3-adafactor.json").read_text(
            encoding="utf-8"
        )
    )
    zero = deepspeed["zero_optimization"]
    if zero.get("stage3_gather_16bit_weights_on_model_save") is not False:
        fail("ZeRO-3 full-rank checkpoint gather must default false")
    leaf_classes = zero.get("leaf_module", {}).get("classes", [])
    if not any("Qwen3_5MoeSparseMoeBlock" in item for item in leaf_classes):
        fail("Qwen3.5 MoE ZeRO-3 leaf class is missing")
    fsdp = (ROOT / "configs" / "accelerate-fsdp.yaml").read_text(encoding="utf-8")
    if "fsdp_activation_checkpointing: false" not in fsdp:
        fail("FSDP must not duplicate model-native activation checkpointing")
    training = json.loads(
        (ROOT / "configs" / "training-defaults.json").read_text(encoding="utf-8")
    )
    capabilities = training.get("runtime_capabilities", {})
    if not capabilities or any(capabilities.values()):
        fail("unverified runtime capability flags must all remain false")


def main() -> None:
    counts = {
        "markdown": validate_markdown(),
        "json": validate_json(),
        "python_ast": validate_python(),
        "shell": len(list(ROOT.rglob("*.sh"))),
    }
    validate_catalog()
    validate_training_guards()
    validate_launchers()
    print(json.dumps({"status": "PASS", "counts": counts}, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}), file=sys.stderr)
        raise
