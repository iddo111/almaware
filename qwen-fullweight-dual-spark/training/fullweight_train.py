"""DGX-only reference loop for bounded full-parameter qualification.

Never import or execute this module on the Windows PC. It performs local-only
model loading and contains no download path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
from pathlib import Path
from typing import Any, Iterable

import torch
from accelerate import Accelerator
from PIL import Image
from torch.utils.data import DataLoader, IterableDataset
from transformers import (
    Adafactor,
    AutoModelForCausalLM,
    AutoModelForImageTextToText,
    AutoProcessor,
    AutoTokenizer,
)
from transformers.integrations import HfDeepSpeedConfig

from gradient_probe import GradientCoverageProbe


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--model-key", required=True)
    parser.add_argument("--model-dir", required=True, type=Path)
    parser.add_argument("--dataset-manifest", required=True, type=Path)
    parser.add_argument("--training-config", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    return parser.parse_args()


def require_dgx_execution() -> None:
    if platform.system() != "Linux":
        raise RuntimeError("DGX Linux only")
    if os.environ.get("DGX_FULLWEIGHT_EXECUTION") != "YES":
        raise RuntimeError("DGX_FULLWEIGHT_EXECUTION=YES gate missing")
    if not Path("/proc/driver/nvidia/version").is_file():
        raise RuntimeError("NVIDIA driver evidence missing")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def configure_zero3_partitioned_loading(accelerator):
    """Enable partitioned from_pretrained loading for a non-Trainer ZeRO-3 loop."""
    plugin = getattr(accelerator.state, "deepspeed_plugin", None)
    if plugin is None:
        return None
    deepspeed_config = plugin.deepspeed_config
    stage = deepspeed_config.get("zero_optimization", {}).get("stage")
    if int(stage) != 3:
        raise RuntimeError(f"expected DeepSpeed ZeRO-3, got stage={stage!r}")
    # Keep the returned object alive until after model construction/preparation.
    return HfDeepSpeedConfig(deepspeed_config)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("modality") not in {"text", "image_text"}:
        raise RuntimeError("unsupported dataset modality")
    if not manifest.get("license", {}).get("training_allowed"):
        raise RuntimeError("dataset is not approved for training")
    if not manifest.get("consent", {}).get("sensitive_data_reviewed"):
        raise RuntimeError("sensitive-data review is missing")
    for split in ("train", "validation"):
        shards = manifest.get("splits", {}).get(split, [])
        if not shards:
            raise RuntimeError(f"dataset split is empty: {split}")
        for shard in shards:
            path = Path(shard["path"])
            if not path.is_absolute() or not path.is_file():
                raise RuntimeError(f"local shard missing: {path}")
            if path.stat().st_size != shard["bytes"]:
                raise RuntimeError(f"shard size mismatch: {path}")
            if sha256_file(path) != shard["sha256"]:
                raise RuntimeError(f"shard digest mismatch: {path}")
    if manifest["modality"] == "image_text":
        assets = manifest.get("assets", [])
        if not assets:
            raise RuntimeError("image_text manifest requires hashed assets")
        for asset in assets:
            path = Path(asset["path"])
            if not path.is_absolute() or not path.is_file():
                raise RuntimeError(f"local image asset missing: {path}")
            if path.stat().st_size != asset["bytes"]:
                raise RuntimeError(f"image asset size mismatch: {path}")
            if sha256_file(path) != asset["sha256"]:
                raise RuntimeError(f"image asset digest mismatch: {path}")


class JsonlRecords(IterableDataset):
    def __init__(
        self,
        shards: list[dict[str, Any]],
        modality: str,
        approved_assets: set[str],
    ):
        super().__init__()
        self.shards = shards
        self.modality = modality
        self.approved_assets = approved_assets

    def __iter__(self) -> Iterable[dict[str, Any]]:
        for shard in self.shards:
            with Path(shard["path"]).open("r", encoding="utf-8") as stream:
                for line_number, line in enumerate(stream, start=1):
                    record = json.loads(line)
                    if not isinstance(record.get("text"), str) or not record["text"]:
                        raise RuntimeError(
                            f"empty text in {shard['path']}:{line_number}"
                        )
                    if self.modality == "image_text":
                        if (
                            not isinstance(record.get("target"), str)
                            or not record["target"]
                        ):
                            raise RuntimeError(
                                f"empty assistant target in "
                                f"{shard['path']}:{line_number}"
                            )
                        image = Path(record.get("image", ""))
                        if not image.is_absolute() or not image.is_file():
                            raise RuntimeError(
                                f"local image missing in {shard['path']}:{line_number}"
                            )
                        if str(image) not in self.approved_assets:
                            raise RuntimeError(
                                f"image is not in hashed manifest assets: {image}"
                            )
                    yield record


def make_collator(
    modality: str,
    model_dir: Path,
    sequence_length: int,
    model_config,
):
    if modality == "text":
        tokenizer = AutoTokenizer.from_pretrained(
            model_dir, local_files_only=True, trust_remote_code=False
        )
        if tokenizer.pad_token_id is None:
            tokenizer.pad_token = tokenizer.eos_token

        def collate_text(records):
            batch = tokenizer(
                [record["text"] for record in records],
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=sequence_length,
            )
            batch["labels"] = batch["input_ids"].clone()
            batch["labels"][batch["attention_mask"] == 0] = -100
            return batch

        return collate_text

    processor = AutoProcessor.from_pretrained(
        model_dir, local_files_only=True, trust_remote_code=False
    )

    def collate_image_text(records):
        images = []
        conversations = []
        for record in records:
            with Image.open(record["image"]) as source:
                image = source.convert("RGB")
            images.append(image)
            conversations.append(
                [
                    {
                        "role": "user",
                        "content": [
                            {"type": "image", "image": image},
                            {"type": "text", "text": record["text"]},
                        ],
                    },
                    {
                        "role": "assistant",
                        "content": [
                            {"type": "text", "text": record["target"]},
                        ],
                    },
                ]
            )
        try:
            batch = processor.apply_chat_template(
                conversations,
                tokenize=True,
                add_generation_prompt=False,
                return_dict=True,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=sequence_length,
                return_assistant_tokens_mask=True,
            )
        finally:
            for image in images:
                image.close()
        required = {"input_ids", "attention_mask", "pixel_values", "image_grid_thw"}
        missing = required - set(batch)
        if missing:
            raise RuntimeError(
                f"multimodal processor omitted required tensors: {sorted(missing)}"
            )
        assistant_masks = batch.pop("assistant_masks", None)
        if assistant_masks is None:
            raise RuntimeError(
                "chat template did not return assistant_masks; target-only "
                "multimodal labels cannot be proven"
            )
        assistant_masks = torch.as_tensor(
            assistant_masks,
            dtype=torch.bool,
            device=batch["input_ids"].device,
        )
        if assistant_masks.ndim == 1:
            assistant_masks = assistant_masks.unsqueeze(0)
        if assistant_masks.shape != batch["input_ids"].shape:
            raise RuntimeError("assistant mask shape does not match input_ids")
        if not bool(assistant_masks.any(dim=1).all().item()):
            raise RuntimeError(
                "at least one multimodal record has no assistant target tokens "
                "after chat-template tokenization/truncation"
            )

        visual_token_ids = {
            int(value)
            for attribute in (
                "image_token_id",
                "video_token_id",
                "vision_start_token_id",
                "vision_end_token_id",
            )
            if isinstance((value := getattr(model_config, attribute, None)), int)
        }
        if not visual_token_ids:
            raise RuntimeError(
                "model config exposes no visual token IDs; visual-placeholder "
                "label masking cannot be proven"
            )
        labels = batch["input_ids"].clone()
        labels[~assistant_masks] = -100
        labels[batch["attention_mask"] == 0] = -100
        for token_id in visual_token_ids:
            labels[batch["input_ids"] == token_id] = -100
        batch["labels"] = labels
        return batch

    return collate_image_text


def load_model(
    model_dir: Path,
    modality: str,
    activation_checkpointing: bool,
):
    model_class = (
        AutoModelForImageTextToText if modality == "image_text" else AutoModelForCausalLM
    )
    model, loading_info = model_class.from_pretrained(
        model_dir,
        local_files_only=True,
        trust_remote_code=False,
        torch_dtype=torch.bfloat16,
        low_cpu_mem_usage=True,
        output_loading_info=True,
    )
    loading_problems = {}
    for key in ("missing_keys", "unexpected_keys", "mismatched_keys", "error_msgs"):
        values = loading_info.get(key, [])
        if values:
            loading_problems[key] = [str(value) for value in values[:20]]
    if loading_problems:
        raise RuntimeError(
            "checkpoint did not load exactly: "
            + json.dumps(loading_problems, sort_keys=True)
        )
    if activation_checkpointing:
        model.gradient_checkpointing_enable()
    model.config.use_cache = False
    for parameter in model.parameters():
        parameter.requires_grad_(True)
    frozen = [name for name, p in model.named_parameters() if not p.requires_grad]
    if frozen:
        raise RuntimeError(f"frozen parameters are forbidden: {frozen[:8]}")
    vision_names = [
        name
        for name, _ in model.named_parameters()
        if any(marker in name.lower() for marker in ("vision", "visual", "image"))
    ]
    if vision_names and modality != "image_text":
        raise RuntimeError(
            "checkpoint contains vision parameters; image_text data is required "
            "for whole-checkpoint gradient coverage"
        )
    return model


def verify_optimizer_coverage(model, optimizer) -> None:
    model_parameter_ids = [id(parameter) for parameter in model.parameters()]
    optimizer_parameter_ids = [
        id(parameter)
        for group in optimizer.param_groups
        for parameter in group["params"]
    ]
    if len(optimizer_parameter_ids) != len(set(optimizer_parameter_ids)):
        raise RuntimeError("optimizer contains duplicate model parameters")
    missing = set(model_parameter_ids) - set(optimizer_parameter_ids)
    extra = set(optimizer_parameter_ids) - set(model_parameter_ids)
    if missing or extra or len(model_parameter_ids) != len(optimizer_parameter_ids):
        raise RuntimeError(
            "optimizer does not cover the model parameter inventory exactly: "
            f"missing={len(missing)} extra={len(extra)}"
        )


def require_verified_runtime_capabilities(
    model_entry: dict[str, Any],
    modality: str,
    config: dict[str, Any],
) -> None:
    capabilities = config.get("runtime_capabilities", {})
    blocked = []
    if (
        modality == "image_text"
        and not capabilities.get("multimodal_preprocessing_verified")
    ):
        blocked.append("multimodal preprocessing")
    if (
        "sparse_moe" in model_entry["architecture"]
        and not capabilities.get("moe_router_probe_verified")
    ):
        blocked.append("sparse-MoE router/gradient proof")
    if not capabilities.get("distributed_state_save_restore_verified"):
        blocked.append("distributed checkpoint save/restore")
    if blocked:
        raise RuntimeError(
            "BLOCKED: runtime capability canaries have not passed: "
            + ", ".join(blocked)
        )


def main() -> None:
    require_dgx_execution()
    args = parse_args()
    catalog = load_json(args.catalog)
    model_entry = catalog["models"][args.model_key]
    manifest = load_json(args.dataset_manifest)
    config = load_json(args.training_config)
    verify_manifest(manifest)

    if manifest["modality"] not in model_entry["modalities"]:
        raise RuntimeError("dataset modality is incompatible with selected model")
    if args.model_key == "max_multimodal_35b_a3b" and manifest["modality"] != "image_text":
        raise RuntimeError("35B multimodal candidate requires image_text data")
    if not args.model_dir.is_absolute() or not args.model_dir.is_dir():
        raise RuntimeError("model-dir must be a staged local absolute directory")
    if not config.get("full_parameter_required"):
        raise RuntimeError("full_parameter_required gate is false")
    require_verified_runtime_capabilities(
        model_entry,
        manifest["modality"],
        config,
    )

    max_steps = int(os.environ.get("MAX_STEPS_OVERRIDE", config["max_steps"]))
    if max_steps < 1 or max_steps > 10:
        raise RuntimeError("qualification max_steps must be between 1 and 10")

    accelerator = Accelerator(
        mixed_precision="bf16",
        gradient_accumulation_steps=config["gradient_accumulation_steps"],
    )
    _zero3_loading_context = configure_zero3_partitioned_loading(accelerator)
    model = load_model(
        args.model_dir,
        manifest["modality"],
        bool(config["activation_checkpointing"]),
    )
    optimizer_cfg = config["optimizer"]
    optimizer = Adafactor(
        model.parameters(),
        lr=optimizer_cfg["learning_rate"],
        eps=(1e-30, 1e-3),
        clip_threshold=1.0,
        decay_rate=-0.8,
        beta1=optimizer_cfg["beta1"],
        weight_decay=optimizer_cfg["weight_decay"],
        relative_step=optimizer_cfg["relative_step"],
        scale_parameter=optimizer_cfg["scale_parameter"],
        warmup_init=optimizer_cfg["warmup_init"],
    )
    verify_optimizer_coverage(model, optimizer)
    approved_assets = {asset["path"] for asset in manifest.get("assets", [])}
    dataset = JsonlRecords(
        manifest["splits"]["train"], manifest["modality"], approved_assets
    )
    collator = make_collator(
        manifest["modality"],
        args.model_dir,
        config["sequence_length"],
        model.config,
    )
    loader = DataLoader(
        dataset,
        batch_size=config["micro_batch_size_per_rank"],
        collate_fn=collator,
        num_workers=config["dataloader_workers"],
    )
    model, optimizer, loader = accelerator.prepare(model, optimizer, loader)
    probe = GradientCoverageProbe(model, accelerator)
    model.train()

    optimizer_steps = 0
    running = True
    while running:
        for batch in loader:
            with accelerator.accumulate(model):
                outputs = model(**batch)
                loss = outputs.loss
                if not torch.isfinite(loss):
                    raise RuntimeError(f"non-finite loss: {loss.detach().float().item()}")
                accelerator.backward(loss)
                if accelerator.sync_gradients:
                    accelerator.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
                optimizer.zero_grad(set_to_none=True)
            if accelerator.sync_gradients:
                optimizer_steps += 1
                if accelerator.is_main_process:
                    print(
                        json.dumps(
                            {
                                "run_id": args.run_id,
                                "optimizer_step": optimizer_steps,
                                "loss": loss.detach().float().item(),
                                "world_size": accelerator.num_processes,
                            },
                            sort_keys=True,
                        ),
                        flush=True,
                    )
                if optimizer_steps >= max_steps:
                    running = False
                    break

    accelerator.wait_for_everyone()
    proof_path = args.output_dir / "proof" / "gradient-coverage.json"
    probe.write(proof_path, args.run_id, optimizer_steps)
    probe.close()

    state_dir = args.output_dir / "distributed-state"
    accelerator.save_state(output_dir=state_dir, safe_serialization=True)
    accelerator.wait_for_everyone()
    if accelerator.is_main_process:
        checkpoint_evidence = {
            "schema_version": 1,
            "run_id": args.run_id,
            "kind": "distributed_training_state",
            "same_parallelism_restore_required": True,
            "consolidated_model_exported": False,
            "reason": (
                "ZeRO-3/FSDP consolidation is blocked until a measured memory "
                "canary proves that gathering a full checkpoint is safe."
            ),
        }
        (args.output_dir / "checkpoint-evidence.json").write_text(
            json.dumps(checkpoint_evidence, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
