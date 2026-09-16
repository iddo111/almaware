"""DGX-only held-out real-audio evaluation helpers."""

from __future__ import annotations

import math
import os
from contextlib import nullcontext
from typing import Any

if os.name == "nt":
    raise RuntimeError(
        "AntVoice neural evaluation is blocked on Windows; run it on a DGX"
    )

import torch
from torch.utils.data import DataLoader

from .labels import PARTIAL_NOT_ANT_FARM_ACCEPTANCE, TRUTH_PARTIAL, TRUTH_VERIFIED


LOSS_NAMES = (
    "loss",
    "reconstruction_loss",
    "vq_loss",
    "world_loss",
    "boundary_loss",
)


def autocast_context(precision: str):
    if precision == "bf16":
        return torch.autocast(device_type="cuda", dtype=torch.bfloat16)
    if precision == "fp16":
        return torch.autocast(device_type="cuda", dtype=torch.float16)
    if precision == "fp32":
        return nullcontext()
    raise ValueError(f"unsupported precision {precision!r}")


@torch.no_grad()
def evaluate_heldout(
    model: torch.nn.Module,
    dataset,
    *,
    batch_size: int,
    max_batches: int,
    device: torch.device,
    precision: str,
) -> dict[str, Any]:
    if max_batches <= 0:
        raise ValueError("max_batches must be positive")
    was_training = model.training
    model.eval()
    loader = DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=0,
        drop_last=False,
    )
    sums = {name: 0.0 for name in LOSS_NAMES}
    examples = 0
    batches = 0
    unit_counts = torch.zeros(
        model.config.codebook_size,
        dtype=torch.int64,
    )
    try:
        for batch in loader:
            waveform = batch["waveform"].to(device=device, non_blocking=False)
            with autocast_context(precision):
                output = model(waveform)
            batch_size_actual = waveform.shape[0]
            for name in LOSS_NAMES:
                value = float(output[name].detach().float())
                if not math.isfinite(value):
                    raise RuntimeError(f"held-out {name} is not finite")
                sums[name] += value * batch_size_actual
            counts = torch.bincount(
                output["unit_ids"].detach().cpu().reshape(-1),
                minlength=model.config.codebook_size,
            )
            unit_counts += counts
            examples += batch_size_actual
            batches += 1
            if batches >= max_batches:
                break
    finally:
        model.train(was_training)
    if examples == 0:
        raise RuntimeError("held-out evaluator consumed no examples")
    used_units = int((unit_counts > 0).sum())
    return {
        "evaluation_status": TRUTH_VERIFIED,
        "truth_gate_status": TRUTH_PARTIAL,
        "acceptance": PARTIAL_NOT_ANT_FARM_ACCEPTANCE,
        "examples": examples,
        "batches": batches,
        "losses": {name: sums[name] / examples for name in LOSS_NAMES},
        "used_unit_count": used_units,
        "codebook_size": model.config.codebook_size,
    }
