"""DGX-only synthetic mechanics test; never Ant Farm acceptance evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from dataclasses import asdict
from pathlib import Path

if os.name == "nt":
    raise RuntimeError(
        "AntVoice neural smoke training is blocked on Windows; run it on a DGX"
    )

import torch

from .config import AntVoiceConfig, estimate_trainable_parameters
from .model import build_model


COMPONENT_PREFIXES = (
    "encoder",
    "temporal",
    "boundary_head",
    "quantizer",
    "world_model",
    "decoder",
)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _model_state_sha256(model: torch.nn.Module) -> str:
    """Hash tensor names, types, shapes, and bytes independently of serialization."""

    digest = hashlib.sha256()
    for name, tensor in sorted(model.state_dict().items()):
        contiguous = tensor.detach().cpu().contiguous()
        digest.update(name.encode("utf-8"))
        digest.update(str(contiguous.dtype).encode("ascii"))
        digest.update(json.dumps(list(contiguous.shape)).encode("ascii"))
        digest.update(contiguous.numpy().tobytes())
    return digest.hexdigest()


def _synthetic_audio(
    *,
    batch_size: int,
    samples: int,
    sample_rate: int,
    seed: int,
    device: torch.device,
) -> torch.Tensor:
    generator = torch.Generator(device="cpu")
    generator.manual_seed(seed)
    time = torch.arange(samples, dtype=torch.float32) / float(sample_rate)
    rows = []
    for index in range(batch_size):
        frequency = 170.0 + 37.0 * index
        signal = (
            0.45 * torch.sin(2.0 * math.pi * frequency * time)
            + 0.18 * torch.sin(2.0 * math.pi * frequency * 2.1 * time)
            + 0.02 * torch.randn(samples, generator=generator)
        )
        rows.append(signal.clamp(-1.0, 1.0))
    return torch.stack(rows).to(device=device)


def _gradient_norms(model: torch.nn.Module) -> dict[str, float]:
    totals = {prefix: 0.0 for prefix in COMPONENT_PREFIXES}
    for name, parameter in model.named_parameters():
        if parameter.grad is None:
            continue
        for prefix in COMPONENT_PREFIXES:
            if name == prefix or name.startswith(prefix + "."):
                totals[prefix] += float(parameter.grad.detach().float().square().sum())
                break
    return {name: math.sqrt(total) for name, total in totals.items()}


def _save_checkpoint(
    path: Path,
    *,
    model: torch.nn.Module,
    config: AntVoiceConfig,
    stage: str,
) -> str:
    torch.save(
        {
            "artifact_type": "synthetic_audio_neural_smoke_checkpoint",
            "acceptance": "REJECTED_FOR_ANT_FARM_ACCEPTANCE",
            "stage": stage,
            "initialization_seed": config.seed,
            "config": asdict(config),
            "model": model.state_dict(),
        },
        path,
    )
    return _file_sha256(path)


def run_smoke(
    config: AntVoiceConfig,
    output_dir: Path,
    *,
    device_name: str,
    seconds: float,
) -> dict[str, object]:
    if seconds <= 0.25:
        raise ValueError("seconds must be greater than 0.25")
    device = torch.device(device_name)
    if device.type != "cuda" or not torch.cuda.is_available():
        raise RuntimeError("this staged neural smoke test requires a CUDA DGX")

    torch.manual_seed(config.seed)
    torch.cuda.manual_seed_all(config.seed)
    torch.use_deterministic_algorithms(True)
    model = build_model(config).to(device)
    model.train()
    output_dir.mkdir(parents=True, exist_ok=True)

    before_tensors = {
        name: parameter.detach().cpu().clone()
        for name, parameter in model.named_parameters()
    }
    before_path = output_dir / "smoke-before.pt"
    model_state_before_hash = _model_state_sha256(model)
    before_hash = _save_checkpoint(
        before_path,
        model=model,
        config=config,
        stage="before_optimizer_step",
    )

    waveform = _synthetic_audio(
        batch_size=2,
        samples=round(config.sample_rate * seconds),
        sample_rate=config.sample_rate,
        seed=config.seed + 1,
        device=device,
    )
    optimizer = torch.optim.AdamW(model.parameters(), lr=2.0e-4)
    optimizer.zero_grad(set_to_none=True)
    output = model(waveform)
    output["loss"].backward()
    gradient_norms = _gradient_norms(model)
    missing_gradients = [
        component
        for component, norm in gradient_norms.items()
        if not math.isfinite(norm) or norm <= 0.0
    ]
    if missing_gradients:
        raise RuntimeError(
            f"zero or invalid component gradients: {sorted(missing_gradients)!r}"
        )
    optimizer.step()

    changed_tensors = [
        name
        for name, parameter in model.named_parameters()
        if not torch.equal(before_tensors[name], parameter.detach().cpu())
    ]
    if not changed_tensors:
        raise RuntimeError("optimizer step did not change any trainable tensor")

    after_path = output_dir / "smoke-after.pt"
    model_state_after_hash = _model_state_sha256(model)
    after_hash = _save_checkpoint(
        after_path,
        model=model,
        config=config,
        stage="after_optimizer_step",
    )
    if before_hash == after_hash:
        raise RuntimeError("before/after checkpoint hashes are identical")
    if model_state_before_hash == model_state_after_hash:
        raise RuntimeError("before/after model-state hashes are identical")

    report: dict[str, object] = {
        "artifact_type": "SYNTHETIC_AUDIO_NEURAL_SMOKE_TEST",
        "truth_gate_status": "REJECTED",
        "acceptance": "REJECTED_FOR_ANT_FARM_ACCEPTANCE",
        "reason": (
            "Synthetic tones are not real Hebrew recordings and do not provide "
            "held-out real-audio improvement or spoken conversation evidence."
        ),
        "synthetic_audio": True,
        "random_initialization_seed": config.seed,
        "config_name": config.name,
        "estimated_trainable_parameters": estimate_trainable_parameters(config),
        "device": str(device),
        "loss": float(output["loss"].detach()),
        "component_gradient_norms": gradient_norms,
        "changed_tensor_count": len(changed_tensors),
        "changed_tensors": changed_tensors,
        "checkpoint_before_sha256": before_hash,
        "checkpoint_after_sha256": after_hash,
        "model_state_before_sha256": model_state_before_hash,
        "model_state_after_sha256": model_state_after_hash,
    }
    report_path = output_dir / "smoke-report.json"
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps(report, sort_keys=True))
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/tiny.json")
    parser.add_argument("--output", default="artifacts/dgx-smoke")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--seconds", type=float, default=0.5)
    args = parser.parse_args()
    run_smoke(
        AntVoiceConfig.from_json(args.config),
        Path(args.output),
        device_name=args.device,
        seconds=args.seconds,
    )


if __name__ == "__main__":
    main()
