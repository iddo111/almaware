"""DGX-only bounded real-audio learning canary.

This is not Ant Farm acceptance. It can verify only the real-audio, acoustic
learner, changed-artifact, and held-out-loss layers.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

if os.name == "nt":
    raise RuntimeError(
        "AntVoice real-audio canary is blocked on Windows; run it on a DGX"
    )

import torch
from torch.utils.data import DataLoader

from .audio_data import ManifestWaveDataset, ResumablePermutationSampler
from .checkpoints import (
    RANDOM_INITIALIZATION_ORIGIN,
    SHADOW_ARTIFACT_TYPE,
    ShadowCheckpointStore,
    capture_rng_state,
    model_state_sha256,
)
from .config import AntVoiceConfig, estimate_trainable_parameters
from .evaluation import autocast_context, evaluate_heldout
from .io_utils import atomic_write_json, canonical_json_sha256
from .labels import (
    BLOCKED_NOT_ANT_FARM_ACCEPTANCE,
    PARTIAL_NOT_ANT_FARM_ACCEPTANCE,
    REAL_AUDIO_CANARY_BLOCKED,
    REAL_AUDIO_CANARY_VERIFIED,
    SHADOW_TRAINING_CHECKPOINT_ONLY,
    TRUTH_BLOCKED,
    TRUTH_PARTIAL,
    TRUTH_VERIFIED,
)
from .manifest import load_validated_manifest
from .model import build_model
from .run_config import RunConfig
from .safety import HeartbeatWriter, assert_operational_guards


COMPONENT_PREFIXES = (
    "encoder",
    "temporal",
    "boundary_head",
    "quantizer",
    "world_model",
    "decoder",
)
MAX_CANARY_PARAMETERS = 5_000_000
MAX_CANARY_STEPS = 64
MAX_CANARY_WALL_SECONDS = 900


def _gradient_norms(model: torch.nn.Module) -> dict[str, float]:
    totals = {prefix: 0.0 for prefix in COMPONENT_PREFIXES}
    for name, parameter in model.named_parameters():
        if parameter.grad is None:
            continue
        for prefix in COMPONENT_PREFIXES:
            if name == prefix or name.startswith(prefix + "."):
                totals[prefix] += float(
                    parameter.grad.detach().float().square().sum()
                )
                break
    return {name: math.sqrt(value) for name, value in totals.items()}


def _checkpoint_payload(
    *,
    model: torch.nn.Module,
    optimizer: torch.optim.Optimizer,
    scaler: torch.amp.GradScaler,
    sampler: ResumablePermutationSampler,
    model_config: AntVoiceConfig,
    run_config: RunConfig,
    manifest_sha256: str,
    run_id: str,
    global_step: int,
    stage: str,
    baseline_eval: dict[str, Any],
    lineage: dict[str, Any],
) -> dict[str, Any]:
    model_config_dict = asdict(model_config)
    return {
        "schema_version": 1,
        "artifact_type": SHADOW_ARTIFACT_TYPE,
        "acceptance": SHADOW_TRAINING_CHECKPOINT_ONLY,
        "run_kind": "bounded_real_audio_canary",
        "run_id": run_id,
        "stage": stage,
        "initialization_origin": RANDOM_INITIALIZATION_ORIGIN,
        "lineage": lineage,
        "manifest_sha256": manifest_sha256,
        "model_config": model_config_dict,
        "model_config_sha256": canonical_json_sha256(model_config_dict),
        "run_config": run_config.to_dict(),
        "run_config_sha256": run_config.sha256,
        "model_state_sha256": model_state_sha256(model),
        "model": model.state_dict(),
        "optimizer": optimizer.state_dict(),
        "scaler": scaler.state_dict(),
        "rng": capture_rng_state(),
        "sampler": sampler.state_dict(),
        "training_state": {
            "global_step": global_step,
            "baseline_eval": baseline_eval,
        },
    }


def run_canary(
    *,
    model_config: AntVoiceConfig,
    run_config: RunConfig,
    manifest_path: Path,
    audio_root: Path,
    run_root: Path,
) -> dict[str, Any]:
    parameter_count = estimate_trainable_parameters(model_config)
    if parameter_count > MAX_CANARY_PARAMETERS:
        raise ValueError(
            f"canary model has {parameter_count:,} parameters; "
            f"hard limit is {MAX_CANARY_PARAMETERS:,}"
        )
    if run_config.steps_per_session > MAX_CANARY_STEPS:
        raise ValueError(
            f"canary steps_per_session exceeds hard limit {MAX_CANARY_STEPS}"
        )
    if run_config.max_wall_seconds > MAX_CANARY_WALL_SECONDS:
        raise ValueError(
            "canary max_wall_seconds exceeds hard limit "
            f"{MAX_CANARY_WALL_SECONDS}"
        )
    encoded_frames = math.ceil(
        run_config.segment_samples / model_config.encoder_downsample_factor
    )
    if encoded_frames > model_config.max_frames:
        raise ValueError("segment length exceeds model max_frames")

    validated = load_validated_manifest(
        manifest_path,
        audio_root,
        required_sample_rate=model_config.sample_rate,
        require_verified_hebrew=run_config.require_verified_hebrew,
    )
    device = torch.device("cuda")
    if not torch.cuda.is_available():
        raise RuntimeError("real-audio canary requires a CUDA DGX")

    random.seed(run_config.seed)
    torch.manual_seed(run_config.seed)
    torch.cuda.manual_seed_all(run_config.seed)
    torch.use_deterministic_algorithms(True)
    store = ShadowCheckpointStore(run_root)
    run_id = f"real-canary-{uuid.uuid4().hex}"
    heartbeat = HeartbeatWriter(
        store.shadow_root / "heartbeat.json",
        run_id=run_id,
    )
    guard = assert_operational_guards(
        store.shadow_root,
        min_free_gib=run_config.min_free_gib,
        min_free_percent=run_config.min_free_percent,
        max_gpu_temp_c=run_config.max_gpu_temp_c,
    )

    train_dataset = ManifestWaveDataset(
        validated,
        audio_root,
        split="train",
        segment_samples=run_config.segment_samples,
        crop_seed=run_config.seed,
    )
    eval_dataset = ManifestWaveDataset(
        validated,
        audio_root,
        split="eval",
        segment_samples=run_config.segment_samples,
        crop_seed=run_config.seed,
    )
    sampler = ResumablePermutationSampler(
        train_dataset,
        seed=run_config.seed,
    )
    model = build_model(model_config).to(device)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=run_config.learning_rate,
        weight_decay=run_config.weight_decay,
    )
    scaler = torch.amp.GradScaler(
        "cuda",
        enabled=run_config.precision == "fp16",
    )
    model.train()

    baseline_eval = evaluate_heldout(
        model,
        eval_dataset,
        batch_size=run_config.batch_size,
        max_batches=run_config.max_eval_batches,
        device=device,
        precision=run_config.precision,
    )
    before_tensors = {
        name: parameter.detach().cpu().clone()
        for name, parameter in model.named_parameters()
    }
    before_state_hash = model_state_sha256(model)
    root_lineage = {
        "initialization_origin": RANDOM_INITIALIZATION_ORIGIN,
        "root_initialization_seed": model_config.seed,
        "root_model_state_sha256": before_state_hash,
        "parent_checkpoint_sha256": None,
        "chain_depth": 0,
    }
    before_checkpoint, before_checkpoint_hash = store.save(
        _checkpoint_payload(
            model=model,
            optimizer=optimizer,
            scaler=scaler,
            sampler=sampler,
            model_config=model_config,
            run_config=run_config,
            manifest_sha256=validated.summary.manifest_sha256,
            run_id=run_id,
            global_step=0,
            stage="before_real_audio_optimizer_steps",
            baseline_eval=baseline_eval,
            lineage=root_lineage,
        ),
        global_step=0,
    )
    heartbeat.write(
        global_step=0,
        state="ACTIVE_REAL_AUDIO_CANARY",
        latest_shadow_checkpoint=str(before_checkpoint),
        guard_snapshot=guard,
    )

    started = time.monotonic()
    global_step = 0
    gradient_norms: dict[str, float] = {}
    while (
        global_step < run_config.steps_per_session
        and time.monotonic() - started < run_config.max_wall_seconds
    ):
        train_dataset.set_epoch(sampler.epoch)
        loader = DataLoader(
            train_dataset,
            batch_size=run_config.batch_size,
            sampler=sampler,
            num_workers=0,
            drop_last=False,
        )
        consumed_batch = False
        for batch in loader:
            consumed_batch = True
            if time.monotonic() - started >= run_config.max_wall_seconds:
                break
            waveform = batch["waveform"].to(device=device, non_blocking=False)
            optimizer.zero_grad(set_to_none=True)
            with autocast_context(run_config.precision):
                output = model(waveform)
            loss = output["loss"]
            if not bool(torch.isfinite(loss)):
                raise RuntimeError("real-audio canary training loss is not finite")
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            gradient_norms = _gradient_norms(model)
            invalid_gradients = [
                name
                for name, value in gradient_norms.items()
                if not math.isfinite(value) or value <= 0.0
            ]
            if invalid_gradients:
                raise RuntimeError(
                    "real-audio canary has zero or invalid component gradients: "
                    f"{sorted(invalid_gradients)!r}"
                )
            torch.nn.utils.clip_grad_norm_(
                model.parameters(),
                run_config.grad_clip_norm,
            )
            scaler.step(optimizer)
            scaler.update()
            global_step += 1
            if global_step % run_config.guard_every_steps == 0:
                guard = assert_operational_guards(
                    store.shadow_root,
                    min_free_gib=run_config.min_free_gib,
                    min_free_percent=run_config.min_free_percent,
                    max_gpu_temp_c=run_config.max_gpu_temp_c,
                )
            if global_step % run_config.heartbeat_every_steps == 0:
                heartbeat.write(
                    global_step=global_step,
                    state="ACTIVE_REAL_AUDIO_CANARY",
                    latest_shadow_checkpoint=str(before_checkpoint),
                    guard_snapshot=guard,
                )
            if global_step >= run_config.steps_per_session:
                break
        if not consumed_batch:
            raise RuntimeError("real-audio canary consumed no training batches")

    if global_step == 0:
        raise RuntimeError("real-audio canary completed no optimizer steps")
    after_eval = evaluate_heldout(
        model,
        eval_dataset,
        batch_size=run_config.batch_size,
        max_batches=run_config.max_eval_batches,
        device=device,
        precision=run_config.precision,
    )
    changed_tensors = [
        name
        for name, parameter in model.named_parameters()
        if not torch.equal(before_tensors[name], parameter.detach().cpu())
    ]
    after_state_hash = model_state_sha256(model)
    after_lineage = {
        "initialization_origin": RANDOM_INITIALIZATION_ORIGIN,
        "root_initialization_seed": model_config.seed,
        "root_model_state_sha256": before_state_hash,
        "parent_checkpoint_sha256": before_checkpoint_hash,
        "chain_depth": 1,
    }
    after_checkpoint, after_checkpoint_hash = store.save(
        _checkpoint_payload(
            model=model,
            optimizer=optimizer,
            scaler=scaler,
            sampler=sampler,
            model_config=model_config,
            run_config=run_config,
            manifest_sha256=validated.summary.manifest_sha256,
            run_id=run_id,
            global_step=global_step,
            stage="after_real_audio_optimizer_steps",
            baseline_eval=baseline_eval,
            lineage=after_lineage,
        ),
        global_step=global_step,
    )
    weight_change_verified = bool(changed_tensors) and (
        before_state_hash != after_state_hash
    )
    artifact_change_verified = before_checkpoint_hash != after_checkpoint_hash
    before_loss = float(baseline_eval["losses"]["loss"])
    after_loss = float(after_eval["losses"]["loss"])
    heldout_improvement_verified = after_loss < before_loss
    verified = (
        weight_change_verified
        and artifact_change_verified
        and heldout_improvement_verified
        and after_eval["used_unit_count"] > 0
    )
    report: dict[str, Any] = {
        "schema_version": 1,
        "artifact_type": "REAL_AUDIO_NEURAL_CANARY_REPORT",
        "truth_gate_status": TRUTH_PARTIAL if verified else TRUTH_BLOCKED,
        "acceptance": (
            PARTIAL_NOT_ANT_FARM_ACCEPTANCE
            if verified
            else BLOCKED_NOT_ANT_FARM_ACCEPTANCE
        ),
        "canary_status": (
            REAL_AUDIO_CANARY_VERIFIED
            if verified
            else REAL_AUDIO_CANARY_BLOCKED
        ),
        "reason_not_full_acceptance": (
            "The spoken Hebrew reasoning, approved memory, and generated "
            "waveform-response gate is not implemented."
        ),
        "run_id": run_id,
        "manifest": validated.summary.to_dict(),
        "real_audio_only": True,
        "transcripts_or_text_used": False,
        "pretrained_components_used": False,
        "random_initialization_seed": model_config.seed,
        "initialization_origin": RANDOM_INITIALIZATION_ORIGIN,
        "lineage": after_lineage,
        "model_parameters": parameter_count,
        "optimizer_steps": global_step,
        "elapsed_seconds": time.monotonic() - started,
        "component_gradient_norms": gradient_norms,
        "changed_tensor_count": len(changed_tensors),
        "model_state_before_sha256": before_state_hash,
        "model_state_after_sha256": after_state_hash,
        "checkpoint_before": str(before_checkpoint),
        "checkpoint_after": str(after_checkpoint),
        "checkpoint_before_sha256": before_checkpoint_hash,
        "checkpoint_after_sha256": after_checkpoint_hash,
        "heldout_before": baseline_eval,
        "heldout_after": after_eval,
        "heldout_loss_delta": after_loss - before_loss,
        "evidence": {
            "weight_change": (
                TRUTH_VERIFIED if weight_change_verified else TRUTH_BLOCKED
            ),
            "artifact_change": (
                TRUTH_VERIFIED if artifact_change_verified else TRUTH_BLOCKED
            ),
            "heldout_improvement": (
                TRUTH_VERIFIED
                if heldout_improvement_verified
                else TRUTH_BLOCKED
            ),
        },
        "truth_gate": {
            "real_audio_capture": TRUTH_VERIFIED,
            "acoustic_learner_unit_ids": (
                TRUTH_VERIFIED
                if after_eval["used_unit_count"] > 0
                else TRUTH_BLOCKED
            ),
            "learning_changed_artifact": (
                TRUTH_VERIFIED if weight_change_verified else TRUTH_BLOCKED
            ),
            "heldout_before_after": (
                TRUTH_VERIFIED
                if heldout_improvement_verified
                else TRUTH_BLOCKED
            ),
            "spoken_conversation": TRUTH_BLOCKED,
        },
    }
    report_path = store.reports / "real-audio-canary-report.json"
    atomic_write_json(report_path, report)
    heartbeat.write(
        global_step=global_step,
        state="CANARY_VERIFIED" if verified else "CANARY_BLOCKED",
        latest_shadow_checkpoint=str(after_checkpoint),
        guard_snapshot=guard,
    )
    print(json.dumps(report, sort_keys=True))
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-config", default="configs/tiny.json")
    parser.add_argument("--run-config", default="configs/real_audio_canary.json")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--audio-root", required=True)
    parser.add_argument("--run-root", required=True)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="required acknowledgement; launch wrappers are dry-run by default",
    )
    args = parser.parse_args()
    if not args.execute:
        parser.error("--execute is required")
    report = run_canary(
        model_config=AntVoiceConfig.from_json(args.model_config),
        run_config=RunConfig.from_json(args.run_config),
        manifest_path=Path(args.manifest),
        audio_root=Path(args.audio_root),
        run_root=Path(args.run_root),
    )
    if report["canary_status"] != REAL_AUDIO_CANARY_VERIFIED:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
