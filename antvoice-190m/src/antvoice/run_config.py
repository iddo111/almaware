"""Pure-Python training configuration validation."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .io_utils import canonical_json_sha256


@dataclass(frozen=True)
class RunConfig:
    name: str
    seed: int
    segment_samples: int
    batch_size: int
    learning_rate: float
    weight_decay: float
    grad_clip_norm: float
    steps_per_session: int
    max_wall_seconds: int
    checkpoint_every_steps: int
    eval_every_steps: int
    guard_every_steps: int
    heartbeat_every_steps: int
    max_eval_batches: int
    precision: str
    num_workers: int
    min_free_gib: float
    min_free_percent: float
    max_gpu_temp_c: float
    require_verified_hebrew: bool

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "RunConfig":
        config = cls(**raw)
        config.validate()
        return config

    @classmethod
    def from_json(cls, path: str | Path) -> "RunConfig":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("run configuration root must be an object")
        return cls.from_dict(raw)

    def validate(self) -> None:
        if not self.name.strip():
            raise ValueError("name must not be empty")
        if self.seed < 0:
            raise ValueError("seed must be non-negative")
        if self.segment_samples < 4_000:
            raise ValueError("segment_samples must cover at least 250 ms at 16 kHz")
        positive_integers = {
            "batch_size": self.batch_size,
            "steps_per_session": self.steps_per_session,
            "max_wall_seconds": self.max_wall_seconds,
            "checkpoint_every_steps": self.checkpoint_every_steps,
            "eval_every_steps": self.eval_every_steps,
            "guard_every_steps": self.guard_every_steps,
            "heartbeat_every_steps": self.heartbeat_every_steps,
            "max_eval_batches": self.max_eval_batches,
        }
        for name, value in positive_integers.items():
            if value <= 0:
                raise ValueError(f"{name} must be positive")
        if self.learning_rate <= 0.0:
            raise ValueError("learning_rate must be positive")
        if self.weight_decay < 0.0:
            raise ValueError("weight_decay must be non-negative")
        if self.grad_clip_norm <= 0.0:
            raise ValueError("grad_clip_norm must be positive")
        if self.precision not in {"bf16", "fp16", "fp32"}:
            raise ValueError("precision must be bf16, fp16, or fp32")
        if self.num_workers != 0:
            raise ValueError(
                "num_workers must remain 0 so sampler checkpoints exactly match "
                "consumed batches"
            )
        if self.min_free_gib <= 0.0:
            raise ValueError("min_free_gib must be positive")
        if not 0.0 < self.min_free_percent < 100.0:
            raise ValueError("min_free_percent must be in (0, 100)")
        if not 40.0 <= self.max_gpu_temp_c <= 90.0:
            raise ValueError("max_gpu_temp_c must be in [40, 90]")
        if not isinstance(self.require_verified_hebrew, bool):
            raise ValueError("require_verified_hebrew must be boolean")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def sha256(self) -> str:
        return canonical_json_sha256(self.to_dict())
