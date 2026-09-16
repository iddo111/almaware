"""Configuration and parameter accounting without importing a neural runtime."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AntVoiceConfig:
    name: str
    seed: int
    sample_rate: int
    encoder_channels: tuple[int, ...]
    encoder_kernels: tuple[int, ...]
    encoder_strides: tuple[int, ...]
    d_model: int
    temporal_layers: int
    temporal_heads: int
    temporal_ffn_dim: int
    temporal_conv_kernel: int
    codebook_size: int
    vq_commitment_cost: float
    world_dim: int
    world_layers: int
    world_heads: int
    world_ffn_dim: int
    max_frames: int
    dropout: float
    boundary_target_rate: float
    reconstruction_weight: float
    vq_weight: float
    world_weight: float
    boundary_weight: float

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "AntVoiceConfig":
        converted = dict(raw)
        for key in ("encoder_channels", "encoder_kernels", "encoder_strides"):
            converted[key] = tuple(int(value) for value in converted[key])
        config = cls(**converted)
        config.validate()
        return config

    @classmethod
    def from_json(cls, path: str | Path) -> "AntVoiceConfig":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("configuration root must be an object")
        return cls.from_dict(raw)

    def validate(self) -> None:
        if not self.name.strip():
            raise ValueError("name must not be empty")
        if self.seed < 0:
            raise ValueError("seed must be a non-negative integer")
        if self.sample_rate != 16_000:
            raise ValueError("this scaffold currently requires 16 kHz audio")
        layer_lengths = {
            len(self.encoder_channels),
            len(self.encoder_kernels),
            len(self.encoder_strides),
        }
        if len(layer_lengths) != 1 or not self.encoder_channels:
            raise ValueError("encoder channel/kernel/stride lists must have equal nonzero length")
        if any(value <= 0 for value in self.encoder_channels):
            raise ValueError("encoder channels must be positive")
        if any(value <= 0 or value % 2 == 0 for value in self.encoder_kernels):
            raise ValueError("encoder kernels must be positive odd numbers")
        if any(value <= 0 for value in self.encoder_strides):
            raise ValueError("encoder strides must be positive")
        if self.d_model <= 0 or self.d_model % self.temporal_heads:
            raise ValueError("d_model must be positive and divisible by temporal_heads")
        if self.world_dim <= 0 or self.world_dim % self.world_heads:
            raise ValueError("world_dim must be positive and divisible by world_heads")
        integer_positives = {
            "temporal_layers": self.temporal_layers,
            "temporal_ffn_dim": self.temporal_ffn_dim,
            "temporal_conv_kernel": self.temporal_conv_kernel,
            "codebook_size": self.codebook_size,
            "world_layers": self.world_layers,
            "world_ffn_dim": self.world_ffn_dim,
            "max_frames": self.max_frames,
        }
        if any(value <= 0 for value in integer_positives.values()):
            raise ValueError("layer, width, codebook, and frame values must be positive")
        if self.temporal_conv_kernel % 2 == 0:
            raise ValueError("temporal_conv_kernel must be odd")
        if not 0.0 <= self.dropout < 1.0:
            raise ValueError("dropout must be in [0, 1)")
        if not 0.0 < self.boundary_target_rate < 1.0:
            raise ValueError("boundary_target_rate must be in (0, 1)")
        nonnegative = (
            self.vq_commitment_cost,
            self.reconstruction_weight,
            self.vq_weight,
            self.world_weight,
            self.boundary_weight,
        )
        if any(value < 0.0 for value in nonnegative):
            raise ValueError("loss weights and commitment cost must be non-negative")

    @property
    def encoder_downsample_factor(self) -> int:
        factor = 1
        for stride in self.encoder_strides:
            factor *= stride
        return factor


def estimate_trainable_parameters(config: AntVoiceConfig) -> int:
    """Return the exact count implied by ``antvoice.model`` layer definitions.

    This arithmetic-only estimator exists so the production configuration can
    be checked without importing or allocating the neural runtime.
    """

    d_model = config.d_model
    encoder = 0
    in_channels = 1
    for out_channels, kernel in zip(config.encoder_channels, config.encoder_kernels):
        encoder += out_channels * in_channels * kernel + out_channels
        in_channels = out_channels
    encoder += d_model * in_channels + d_model

    # Five LayerNorms; two FFNs; one MHA; expanded pointwise/depthwise conv.
    conformer_block = (
        8 * d_model * d_model
        + 4 * d_model * config.temporal_ffn_dim
        + 2 * config.temporal_ffn_dim
        + 2 * d_model * config.temporal_conv_kernel
        + 21 * d_model
    )
    temporal = config.temporal_layers * conformer_block
    boundary = d_model + 1
    quantizer = config.codebook_size * d_model

    world_dim = config.world_dim
    world_block = (
        4 * world_dim * world_dim
        + 2 * world_dim * config.world_ffn_dim
        + config.world_ffn_dim
        + 9 * world_dim
    )
    world = (
        config.codebook_size * world_dim
        + world_dim
        + config.max_frames * world_dim
        + config.world_layers * world_block
        + 2 * world_dim
        + world_dim * config.codebook_size
        + config.codebook_size
    )

    last_channel = config.encoder_channels[-1]
    decoder = d_model * last_channel + last_channel
    for index in range(len(config.encoder_channels) - 1, -1, -1):
        in_channel = config.encoder_channels[index]
        out_channel = 1 if index == 0 else config.encoder_channels[index - 1]
        decoder += (
            in_channel * out_channel * config.encoder_kernels[index] + out_channel
        )

    return encoder + temporal + boundary + quantizer + world + decoder
