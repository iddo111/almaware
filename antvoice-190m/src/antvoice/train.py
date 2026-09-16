"""DGX-only resumable real-audio trainer with shadow-only checkpoints."""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if os.name == "nt":
    raise RuntimeError(
        "AntVoice neural training is blocked on Windows; run it on a DGX"
    )

import torch
from torch.utils.data import DataLoader

from .audio_data import ManifestWaveDataset, ResumablePermutationSampler
from .checkpoints import (
    RANDOM_INITIALIZATION_ORIGIN,
    SHADOW_ARTIFACT_TYPE,
    ShadowCheckpointStore,
    capture_rng_state,
    load_resume_checkpoint,
    model_state_sha256,
    restore_rng_state,
)
from .config import AntVoiceConfig, estimate_trainable_parameters
from .evaluation import autocast_context, evaluate_heldout
from .io_utils import atomic_write_json, canonical_json_sha256
from .labels import (
    BLOCKED_NOT_ANT_FARM_ACCEPTANCE,
    PARTIAL_NOT_ANT_FARM_ACCEPTANCE,
    SHADOW_TRAINING_CHECKPOINT_ONLY,
    TRUTH_PARTIAL,
    TRUTH_BLOCKED,
    TRUTH_VERIFIED,
)
from .manifest import load_validated_manifest
from .model import build_model
from .run_config import RunConfig
from .safety import (
    GuardSnapshot,
    HeartbeatWriter,
    SafetyBlock,
    assert_operational_guards,
)

COMPONENT_PREFIXES = (
    "encoder",
    "temporal",
    "boundary_head",
    "quantizer",
    "world_model",
    "decoder",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _component_for_parameter(name: str) -> str:
    for prefix in COMPONENT_PREFIXES:
        if name == prefix or name.startswith(prefix + "."):
            return prefix
    raise ValueError(f"trainable parameter is outside known components: {name}")


def _assert_full_parameter_contract(
    model: torch.nn.Module,
    optimizer: torch.optim.Optimizer,
) -> dict[str, set[str]]:
    named = dict(model.named_parameters())
    if not named:
        raise ValueError("model has no named parameters")
    frozen = sorted(name for name, parameter in named.items() if not parameter.requires_grad)
    if frozen:
        raise ValueError(f"full-weight training found frozen parameters: {frozen!r}")
    model_ids = {id(parameter) for parameter in named.values()}
    optimizer_ids = {
        id(parameter)
        for group in optimizer.param_groups
        for parameter in group["params"]
    }
    if optimizer_ids != model_ids:
        raise ValueError("optimizer parameter set does not equal all named parameters")
    totals = {prefix: set() for prefix in COMPONENT_PREFIXES}
    for name in named:
        totals[_component_for_parameter(name)].add(name)
    if any(not names for names in totals.values()):
        raise ValueError("one or more neural components has no named parameters")
    return totals


def _restore_gradient_coverage(
    raw: object,
    totals: dict[str, set[str]],
) -> dict[str, set[str]]:
    if not isinstance(raw, dict) or set(raw) != set(COMPONENT_PREFIXES):
        raise ValueError("checkpoint gradient coverage schema is invalid")
    restored: dict[str, set[str]] = {}
    for component, total_names in totals.items():
        values = raw.get(component)
        if not isinstance(values, list) or not all(
            isinstance(value, str) for value in values
        ):
            raise ValueError(f"gradient coverage is invalid for {component}")
        covered = set(values)
        if not covered <= total_names:
            raise ValueError(f"gradient coverage has unknown names for {component}")
        restored[component] = covered
    return restored


def _serialized_gradient_coverage(
    coverage: dict[str, set[str]],
) -> dict[str, list[str]]:
    return {
        component: sorted(names)
        for component, names in coverage.items()
    }


def _update_gradient_coverage(
    model: torch.nn.Module,
    coverage: dict[str, set[str]],
) -> None:
    for name, parameter in model.named_parameters():
        component = _component_for_parameter(name)
        if name in coverage[component] or parameter.grad is None:
            continue
        gradient = parameter.grad.detach()
        if bool(torch.isfinite(gradient).all()) and bool(
            torch.count_nonzero(gradient)
        ):
            coverage[component].add(name)


def _gradient_coverage_report(
    coverage: dict[str, set[str]],
    totals: dict[str, set[str]],
) -> dict[str, Any]:
    components: dict[str, Any] = {}
    all_covered = True
    for component in COMPONENT_PREFIXES:
        covered = len(coverage[component])
        total = len(totals[component])
        complete = covered == total
        all_covered = all_covered and complete
        components[component] = {
            "covered_named_parameters": covered,
            "total_named_parameters": total,
            "status": TRUTH_VERIFIED if complete else TRUTH_PARTIAL,
        }
    return {
        "all_named_parameters_require_grad": TRUTH_VERIFIED,
        "optimizer_covers_all_named_parameters": TRUTH_VERIFIED,
        "all_named_parameter_gradients_observed": (
            TRUTH_VERIFIED if all_covered else TRUTH_PARTIAL
        ),
        "claim": (
            "ALL_NAMED_PARAMETERS_RECEIVED_NONZERO_FINITE_GRADIENT"
            if all_covered
            else "PARTIAL_CUMULATIVE_GRADIENT_COVERAGE"
        ),
        "individual_tensor_change_measured": False,
        "components": components,
    }


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
    training_state: dict[str, Any],
    lineage: dict[str, Any],
) -> dict[str, Any]:
    model_config_dict = asdict(model_config)
    return {
        "schema_version": 1,
        "artifact_type": SHADOW_ARTIFACT_TYPE,
        "acceptance": SHADOW_TRAINING_CHECKPOINT_ONLY,
        "run_kind": "resumable_full_real_audio_training",
        "run_id": run_id,
        "created_utc": _utc_now(),
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
        "training_state": training_state,
    }


def _write_evaluation_report(
    *,
    store: ShadowCheckpointStore,
    checkpoint: Path,
    checkpoint_sha256: str,
    run_id: str,
    global_step: int,
    manifest_sha256: str,
    baseline_eval: dict[str, Any],
    current_eval: dict[str, Any],
    lineage: dict[str, Any],
    full_weight_training: dict[str, Any],
) -> Path:
    baseline_loss = float(baseline_eval["losses"]["loss"])
    current_loss = float(current_eval["losses"]["loss"])
    improved = current_loss < baseline_loss
    report = {
        "schema_version": 1,
        "artifact_type": "REAL_AUDIO_HELDOUT_EVALUATION_REPORT",
        "evaluation_status": TRUTH_VERIFIED,
        "truth_gate_status": TRUTH_PARTIAL,
        "acceptance": PARTIAL_NOT_ANT_FARM_ACCEPTANCE,
        "reason_not_full_acceptance": (
            "A training checkpoint is not spoken Hebrew conversation acceptance."
        ),
        "run_id": run_id,
        "initialization_origin": RANDOM_INITIALIZATION_ORIGIN,
        "lineage": lineage,
        "full_weight_training": full_weight_training,
        "global_step": global_step,
        "manifest_sha256": manifest_sha256,
        "checkpoint": str(checkpoint.relative_to(store.run_root)),
        "checkpoint_sha256": checkpoint_sha256,
        "baseline": baseline_eval,
        "current": current_eval,
        "heldout_loss_delta": current_loss - baseline_loss,
        "promotion_eligible": improved,
        "promotion_scope": (
            "IMMUTABLE_MODEL_ARTIFACT_ONLY"
            if improved
            else "BLOCKED_NO_HELDOUT_IMPROVEMENT"
        ),
        "automatic_promotion_performed": False,
        "real_audio_only": True,
        "transcripts_or_text_used": False,
        "pretrained_components_used": False,
        "created_utc": _utc_now(),
    }
    path = store.reports / f"evaluation-step-{global_step:012d}.json"
    atomic_write_json(path, report)
    return path


def run_training(
    *,
    model_config: AntVoiceConfig,
    run_config: RunConfig,
    manifest_path: Path,
    audio_root: Path,
    run_root: Path,
    resume_latest: bool,
) -> dict[str, Any]:
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
        raise RuntimeError("full real-audio training requires a CUDA DGX")

    random.seed(run_config.seed)
    torch.manual_seed(run_config.seed)
    torch.cuda.manual_seed_all(run_config.seed)
    store = ShadowCheckpointStore(run_root)
    guard: GuardSnapshot | None = assert_operational_guards(
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
    parameter_totals = _assert_full_parameter_contract(model, optimizer)
    model_config_sha256 = canonical_json_sha256(asdict(model_config))
    latest = store.latest() if resume_latest else None
    latest_checkpoint_path: Path | None = None
    latest_checkpoint_sha256: str | None = None
    last_checkpoint_step = -1
    lineage: dict[str, Any]

    if latest is not None:
        latest_checkpoint_path, latest_checkpoint_sha256 = latest
        payload = load_resume_checkpoint(
            latest_checkpoint_path,
            expected_sha256=latest_checkpoint_sha256,
            expected_manifest_sha256=validated.summary.manifest_sha256,
            expected_model_config_sha256=model_config_sha256,
            expected_run_config_sha256=run_config.sha256,
            expected_initialization_seed=model_config.seed,
        )
        if payload.get("run_kind") != "resumable_full_real_audio_training":
            raise ValueError("latest shadow checkpoint is not a full-training resume")
        store.verify_resume_lineage(
            payload,
            checkpoint_sha256=latest_checkpoint_sha256,
        )
        model.load_state_dict(payload["model"], strict=True)
        optimizer.load_state_dict(payload["optimizer"])
        scaler.load_state_dict(payload["scaler"])
        sampler.load_state_dict(payload["sampler"])
        restore_rng_state(payload["rng"])
        training_state = payload["training_state"]
        if not isinstance(training_state, dict):
            raise ValueError("resume training_state is invalid")
        run_id = str(payload["run_id"])
        lineage = payload["lineage"]
        last_checkpoint_step = int(training_state["global_step"])
    else:
        run_id = f"real-train-{uuid.uuid4().hex}"
        baseline_eval = evaluate_heldout(
            model,
            eval_dataset,
            batch_size=run_config.batch_size,
            max_batches=run_config.max_eval_batches,
            device=device,
            precision=run_config.precision,
        )
        training_state = {
            "global_step": 0,
            "examples_seen": 0,
            "baseline_eval": baseline_eval,
            "best_eval_loss": float(baseline_eval["losses"]["loss"]),
            "started_utc": _utc_now(),
            "gradient_coverage": {
                component: [] for component in COMPONENT_PREFIXES
            },
        }
        root_model_state_hash = model_state_sha256(model)
        lineage = {
            "initialization_origin": RANDOM_INITIALIZATION_ORIGIN,
            "root_initialization_seed": model_config.seed,
            "root_model_state_sha256": root_model_state_hash,
            "parent_checkpoint_sha256": None,
            "chain_depth": 0,
        }
        latest_checkpoint_path, latest_checkpoint_sha256 = store.save(
            _checkpoint_payload(
                model=model,
                optimizer=optimizer,
                scaler=scaler,
                sampler=sampler,
                model_config=model_config,
                run_config=run_config,
                manifest_sha256=validated.summary.manifest_sha256,
                run_id=run_id,
                training_state=training_state,
                lineage=lineage,
            ),
            global_step=0,
        )
        last_checkpoint_step = 0

    required_training_state = {
        "global_step",
        "examples_seen",
        "baseline_eval",
        "best_eval_loss",
        "started_utc",
        "gradient_coverage",
    }
    missing_training_state = required_training_state - training_state.keys()
    if missing_training_state:
        raise ValueError(
            "training_state is incomplete: "
            f"{sorted(missing_training_state)!r}"
        )
    global_step = int(training_state["global_step"])
    examples_seen = int(training_state["examples_seen"])
    baseline_eval = training_state["baseline_eval"]
    best_eval_loss = float(training_state["best_eval_loss"])
    gradient_coverage = _restore_gradient_coverage(
        training_state["gradient_coverage"],
        parameter_totals,
    )
    if global_step < 0 or examples_seen < 0 or not isinstance(baseline_eval, dict):
        raise ValueError("training_state counters or baseline are invalid")

    heartbeat = HeartbeatWriter(
        store.shadow_root / "heartbeat.json",
        run_id=run_id,
    )
    heartbeat.write(
        global_step=global_step,
        state="ACTIVE_REAL_AUDIO_TRAINING",
        latest_shadow_checkpoint=(
            str(latest_checkpoint_path)
            if latest_checkpoint_path is not None
            else None
        ),
        guard_snapshot=guard,
    )
    model.train()
    session_started = time.monotonic()
    session_start_step = global_step
    last_eval: dict[str, Any] | None = None
    last_eval_report: Path | None = None

    try:
        while (
            global_step - session_start_step < run_config.steps_per_session
            and time.monotonic() - session_started
            < run_config.max_wall_seconds
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
                if (
                    time.monotonic() - session_started
                    >= run_config.max_wall_seconds
                ):
                    break
                waveform = batch["waveform"].to(
                    device=device,
                    non_blocking=False,
                )
                optimizer.zero_grad(set_to_none=True)
                with autocast_context(run_config.precision):
                    output = model(waveform)
                loss = output["loss"]
                if not bool(torch.isfinite(loss)):
                    raise RuntimeError("training loss is not finite")
                scaler.scale(loss).backward()
                scaler.unscale_(optimizer)
                _update_gradient_coverage(model, gradient_coverage)
                gradient_norm = torch.nn.utils.clip_grad_norm_(
                    model.parameters(),
                    run_config.grad_clip_norm,
                )
                if not bool(torch.isfinite(gradient_norm)):
                    raise RuntimeError("training gradient norm is not finite")
                scaler.step(optimizer)
                scaler.update()
                global_step += 1
                examples_seen += int(waveform.shape[0])

                if global_step % run_config.guard_every_steps == 0:
                    guard = assert_operational_guards(
                        store.shadow_root,
                        min_free_gib=run_config.min_free_gib,
                        min_free_percent=run_config.min_free_percent,
                        max_gpu_temp_c=run_config.max_gpu_temp_c,
                    )
                evaluation_due = global_step % run_config.eval_every_steps == 0
                checkpoint_due = (
                    global_step % run_config.checkpoint_every_steps == 0
                )
                if evaluation_due:
                    last_eval = evaluate_heldout(
                        model,
                        eval_dataset,
                        batch_size=run_config.batch_size,
                        max_batches=run_config.max_eval_batches,
                        device=device,
                        precision=run_config.precision,
                    )
                    best_eval_loss = min(
                        best_eval_loss,
                        float(last_eval["losses"]["loss"]),
                    )
                if evaluation_due or checkpoint_due:
                    training_state = {
                        "global_step": global_step,
                        "examples_seen": examples_seen,
                        "baseline_eval": baseline_eval,
                        "best_eval_loss": best_eval_loss,
                        "started_utc": training_state["started_utc"],
                        "gradient_coverage": _serialized_gradient_coverage(
                            gradient_coverage
                        ),
                    }
                    next_lineage = {
                        "initialization_origin": RANDOM_INITIALIZATION_ORIGIN,
                        "root_initialization_seed": lineage[
                            "root_initialization_seed"
                        ],
                        "root_model_state_sha256": lineage[
                            "root_model_state_sha256"
                        ],
                        "parent_checkpoint_sha256": latest_checkpoint_sha256,
                        "chain_depth": int(lineage["chain_depth"]) + 1,
                    }
                    latest_checkpoint_path, latest_checkpoint_sha256 = store.save(
                        _checkpoint_payload(
                            model=model,
                            optimizer=optimizer,
                            scaler=scaler,
                            sampler=sampler,
                            model_config=model_config,
                            run_config=run_config,
                            manifest_sha256=validated.summary.manifest_sha256,
                            run_id=run_id,
                            training_state=training_state,
                            lineage=next_lineage,
                        ),
                        global_step=global_step,
                    )
                    lineage = next_lineage
                    last_checkpoint_step = global_step
                    if evaluation_due and last_eval is not None:
                        last_eval_report = _write_evaluation_report(
                            store=store,
                            checkpoint=latest_checkpoint_path,
                            checkpoint_sha256=latest_checkpoint_sha256,
                            run_id=run_id,
                            global_step=global_step,
                            manifest_sha256=validated.summary.manifest_sha256,
                            baseline_eval=baseline_eval,
                            current_eval=last_eval,
                            lineage=lineage,
                            full_weight_training=_gradient_coverage_report(
                                gradient_coverage,
                                parameter_totals,
                            ),
                        )
                if global_step % run_config.heartbeat_every_steps == 0:
                    heartbeat.write(
                        global_step=global_step,
                        state="ACTIVE_REAL_AUDIO_TRAINING",
                        latest_shadow_checkpoint=(
                            str(latest_checkpoint_path)
                            if latest_checkpoint_path is not None
                            else None
                        ),
                        guard_snapshot=guard,
                    )
                if (
                    global_step - session_start_step
                    >= run_config.steps_per_session
                ):
                    break
            if not consumed_batch:
                raise RuntimeError("trainer consumed no real-audio batches")
    except SafetyBlock:
        try:
            heartbeat.write(
                global_step=global_step,
                state="BLOCKED_OPERATIONAL_GUARD",
                latest_shadow_checkpoint=(
                    str(latest_checkpoint_path)
                    if latest_checkpoint_path is not None
                    else None
                ),
                guard_snapshot=guard,
            )
        finally:
            raise

    if global_step > last_checkpoint_step:
        guard = assert_operational_guards(
            store.shadow_root,
            min_free_gib=run_config.min_free_gib,
            min_free_percent=run_config.min_free_percent,
            max_gpu_temp_c=run_config.max_gpu_temp_c,
        )
        last_eval = evaluate_heldout(
            model,
            eval_dataset,
            batch_size=run_config.batch_size,
            max_batches=run_config.max_eval_batches,
            device=device,
            precision=run_config.precision,
        )
        best_eval_loss = min(
            best_eval_loss,
            float(last_eval["losses"]["loss"]),
        )
        training_state = {
            "global_step": global_step,
            "examples_seen": examples_seen,
            "baseline_eval": baseline_eval,
            "best_eval_loss": best_eval_loss,
            "started_utc": training_state["started_utc"],
            "gradient_coverage": _serialized_gradient_coverage(
                gradient_coverage
            ),
        }
        next_lineage = {
            "initialization_origin": RANDOM_INITIALIZATION_ORIGIN,
            "root_initialization_seed": lineage["root_initialization_seed"],
            "root_model_state_sha256": lineage["root_model_state_sha256"],
            "parent_checkpoint_sha256": latest_checkpoint_sha256,
            "chain_depth": int(lineage["chain_depth"]) + 1,
        }
        latest_checkpoint_path, latest_checkpoint_sha256 = store.save(
            _checkpoint_payload(
                model=model,
                optimizer=optimizer,
                scaler=scaler,
                sampler=sampler,
                model_config=model_config,
                run_config=run_config,
                manifest_sha256=validated.summary.manifest_sha256,
                run_id=run_id,
                training_state=training_state,
                lineage=next_lineage,
            ),
            global_step=global_step,
        )
        lineage = next_lineage
        last_checkpoint_step = global_step
        last_eval_report = _write_evaluation_report(
            store=store,
            checkpoint=latest_checkpoint_path,
            checkpoint_sha256=latest_checkpoint_sha256,
            run_id=run_id,
            global_step=global_step,
            manifest_sha256=validated.summary.manifest_sha256,
            baseline_eval=baseline_eval,
            current_eval=last_eval,
            lineage=lineage,
            full_weight_training=_gradient_coverage_report(
                gradient_coverage,
                parameter_totals,
            ),
        )

    heartbeat.write(
        global_step=global_step,
        state="STOPPED_AT_CONFIGURED_BOUND",
        latest_shadow_checkpoint=(
            str(latest_checkpoint_path)
            if latest_checkpoint_path is not None
            else None
        ),
        guard_snapshot=guard,
    )
    session_steps = global_step - session_start_step
    summary = {
        "schema_version": 1,
        "artifact_type": "REAL_AUDIO_TRAINING_SESSION_SUMMARY",
        "truth_gate_status": (
            TRUTH_PARTIAL if session_steps > 0 else TRUTH_BLOCKED
        ),
        "acceptance": (
            PARTIAL_NOT_ANT_FARM_ACCEPTANCE
            if session_steps > 0
            else BLOCKED_NOT_ANT_FARM_ACCEPTANCE
        ),
        "run_id": run_id,
        "initialization_origin": RANDOM_INITIALIZATION_ORIGIN,
        "lineage": lineage,
        "resumed": latest is not None,
        "global_step": global_step,
        "session_steps": session_steps,
        "examples_seen": examples_seen,
        "model_parameters": estimate_trainable_parameters(model_config),
        "full_weight_training": _gradient_coverage_report(
            gradient_coverage,
            parameter_totals,
        ),
        "manifest": validated.summary.to_dict(),
        "latest_shadow_checkpoint": (
            str(latest_checkpoint_path)
            if latest_checkpoint_path is not None
            else None
        ),
        "latest_shadow_checkpoint_sha256": latest_checkpoint_sha256,
        "latest_evaluation_report": (
            str(last_eval_report) if last_eval_report is not None else None
        ),
        "automatic_promotion_performed": False,
        "active_tree_written_by_trainer": False,
        "stopped_reason": (
            "SESSION_STEP_BOUND"
            if (
                global_step - session_start_step
                >= run_config.steps_per_session
            )
            else "MAX_WALL_SECONDS"
        ),
    }
    atomic_write_json(store.reports / "latest-session-summary.json", summary)
    print(json.dumps(summary, sort_keys=True))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-config", default="configs/antvoice_190m.json")
    parser.add_argument("--run-config", default="configs/real_audio_train.json")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--audio-root", required=True)
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--resume-latest", action="store_true")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="required acknowledgement; launch wrappers are dry-run by default",
    )
    args = parser.parse_args()
    if not args.execute:
        parser.error("--execute is required")
    run_training(
        model_config=AntVoiceConfig.from_json(args.model_config),
        run_config=RunConfig.from_json(args.run_config),
        manifest_path=Path(args.manifest),
        audio_root=Path(args.audio_root),
        run_root=Path(args.run_root),
        resume_latest=args.resume_latest,
    )


if __name__ == "__main__":
    main()
