"""Random-initialized waveform-to-units-to-waveform neural architecture.

This module is execution-blocked on Windows. It is staged for an approved DGX.
"""

from __future__ import annotations

import hashlib
import math
import os
from dataclasses import dataclass

if os.name == "nt":
    raise RuntimeError(
        "AntVoice neural runtime is blocked on Windows; execute it on an approved DGX"
    )

import torch
import torch.nn as nn
import torch.nn.functional as F

from .config import AntVoiceConfig


class WaveformEncoder(nn.Module):
    def __init__(self, config: AntVoiceConfig) -> None:
        super().__init__()
        layers: list[nn.Module] = []
        in_channels = 1
        for out_channels, kernel, stride in zip(
            config.encoder_channels,
            config.encoder_kernels,
            config.encoder_strides,
        ):
            layers.append(
                nn.Conv1d(
                    in_channels,
                    out_channels,
                    kernel_size=kernel,
                    stride=stride,
                    padding=(kernel - 1) // 2,
                )
            )
            in_channels = out_channels
        self.layers = nn.ModuleList(layers)
        self.projection = nn.Linear(in_channels, config.d_model)

    def forward(self, waveform: torch.Tensor) -> torch.Tensor:
        if waveform.ndim != 2:
            raise ValueError("waveform must have shape [batch, samples]")
        encoded = waveform.unsqueeze(1)
        for layer in self.layers:
            encoded = F.gelu(layer(encoded))
        return self.projection(encoded.transpose(1, 2))


def _sinusoidal_positions(
    length: int,
    width: int,
    *,
    device: torch.device,
    dtype: torch.dtype,
) -> torch.Tensor:
    positions = torch.arange(length, device=device, dtype=torch.float32).unsqueeze(1)
    even_width = (width + 1) // 2
    scales = torch.exp(
        torch.arange(even_width, device=device, dtype=torch.float32)
        * (-math.log(10_000.0) / max(even_width - 1, 1))
    )
    angles = positions * scales.unsqueeze(0)
    result = torch.zeros((length, width), device=device, dtype=torch.float32)
    result[:, 0::2] = torch.sin(angles[:, : result[:, 0::2].shape[1]])
    result[:, 1::2] = torch.cos(angles[:, : result[:, 1::2].shape[1]])
    return result.to(dtype=dtype)


def _feed_forward(width: int, hidden: int, dropout: float) -> nn.Sequential:
    return nn.Sequential(
        nn.Linear(width, hidden),
        nn.GELU(),
        nn.Dropout(dropout),
        nn.Linear(hidden, width),
        nn.Dropout(dropout),
    )


class TemporalConformerBlock(nn.Module):
    """A pre-norm attention/expanded-convolution/dual-FFN temporal block."""

    def __init__(self, config: AntVoiceConfig) -> None:
        super().__init__()
        width = config.d_model
        self.ffn1_norm = nn.LayerNorm(width)
        self.ffn1 = _feed_forward(width, config.temporal_ffn_dim, config.dropout)
        self.attention_norm = nn.LayerNorm(width)
        self.attention = nn.MultiheadAttention(
            width,
            config.temporal_heads,
            dropout=config.dropout,
            batch_first=True,
        )
        self.convolution_norm = nn.LayerNorm(width)
        self.pointwise_in = nn.Conv1d(width, 2 * width, kernel_size=1)
        self.depthwise = nn.Conv1d(
            2 * width,
            2 * width,
            kernel_size=config.temporal_conv_kernel,
            padding=(config.temporal_conv_kernel - 1) // 2,
            groups=2 * width,
        )
        self.pointwise_out = nn.Conv1d(2 * width, width, kernel_size=1)
        self.convolution_dropout = nn.Dropout(config.dropout)
        self.ffn2_norm = nn.LayerNorm(width)
        self.ffn2 = _feed_forward(width, config.temporal_ffn_dim, config.dropout)
        self.final_norm = nn.LayerNorm(width)

    def forward(self, encoded: torch.Tensor) -> torch.Tensor:
        encoded = encoded + 0.5 * self.ffn1(self.ffn1_norm(encoded))
        attention_input = self.attention_norm(encoded)
        attended, _ = self.attention(
            attention_input,
            attention_input,
            attention_input,
            need_weights=False,
        )
        encoded = encoded + attended
        convolved = self.convolution_norm(encoded).transpose(1, 2)
        convolved = F.gelu(self.pointwise_in(convolved))
        convolved = F.gelu(self.depthwise(convolved))
        convolved = self.pointwise_out(convolved).transpose(1, 2)
        encoded = encoded + self.convolution_dropout(convolved)
        encoded = encoded + 0.5 * self.ffn2(self.ffn2_norm(encoded))
        return self.final_norm(encoded)


class TemporalStack(nn.Module):
    def __init__(self, config: AntVoiceConfig) -> None:
        super().__init__()
        self.blocks = nn.ModuleList(
            TemporalConformerBlock(config) for _ in range(config.temporal_layers)
        )

    def forward(self, encoded: torch.Tensor) -> torch.Tensor:
        positions = _sinusoidal_positions(
            encoded.shape[1],
            encoded.shape[2],
            device=encoded.device,
            dtype=encoded.dtype,
        )
        encoded = encoded + positions.unsqueeze(0)
        for block in self.blocks:
            encoded = block(encoded)
        return encoded


@dataclass(frozen=True)
class QuantizerOutput:
    straight_through: torch.Tensor
    unit_ids: torch.Tensor
    loss: torch.Tensor
    codebook_loss: torch.Tensor
    commitment_loss: torch.Tensor


class VectorQuantizer(nn.Module):
    def __init__(self, codebook_size: int, width: int, commitment_cost: float) -> None:
        super().__init__()
        self.codebook = nn.Parameter(torch.empty(codebook_size, width))
        self.commitment_cost = commitment_cost

    def forward(self, encoded: torch.Tensor) -> QuantizerOutput:
        flat = encoded.reshape(-1, encoded.shape[-1])
        distances = (
            flat.square().sum(dim=1, keepdim=True)
            + self.codebook.square().sum(dim=1).unsqueeze(0)
            - 2.0 * flat @ self.codebook.transpose(0, 1)
        )
        unit_ids = distances.argmin(dim=1)
        quantized = F.embedding(unit_ids, self.codebook).view_as(encoded)
        codebook_loss = F.mse_loss(quantized, encoded.detach())
        commitment_loss = F.mse_loss(encoded, quantized.detach())
        loss = codebook_loss + self.commitment_cost * commitment_loss
        straight_through = encoded + (quantized - encoded).detach()
        return QuantizerOutput(
            straight_through=straight_through,
            unit_ids=unit_ids.view(encoded.shape[0], encoded.shape[1]),
            loss=loss,
            codebook_loss=codebook_loss,
            commitment_loss=commitment_loss,
        )


class CausalUnitWorldModel(nn.Module):
    def __init__(self, config: AntVoiceConfig) -> None:
        super().__init__()
        self.max_frames = config.max_frames
        self.unit_embedding = nn.Embedding(config.codebook_size, config.world_dim)
        self.bos = nn.Parameter(torch.empty(config.world_dim))
        self.position_embedding = nn.Embedding(config.max_frames, config.world_dim)
        layer = nn.TransformerEncoderLayer(
            d_model=config.world_dim,
            nhead=config.world_heads,
            dim_feedforward=config.world_ffn_dim,
            dropout=config.dropout,
            activation="gelu",
            batch_first=True,
            norm_first=True,
        )
        self.layers = nn.TransformerEncoder(
            layer,
            num_layers=config.world_layers,
            norm=nn.LayerNorm(config.world_dim),
        )
        self.unit_head = nn.Linear(config.world_dim, config.codebook_size)

    def forward(self, unit_ids: torch.Tensor) -> torch.Tensor:
        batch, frames = unit_ids.shape
        if frames > self.max_frames:
            raise ValueError(
                f"encoded sequence has {frames} frames, maximum is {self.max_frames}"
            )
        previous = self.unit_embedding(unit_ids[:, :-1])
        bos = self.bos.view(1, 1, -1).expand(batch, 1, -1)
        world_input = torch.cat((bos, previous), dim=1)
        positions = torch.arange(frames, device=unit_ids.device)
        world_input = world_input + self.position_embedding(positions).unsqueeze(0)
        causal_mask = torch.ones(
            (frames, frames), device=unit_ids.device, dtype=torch.bool
        ).triu(1)
        hidden = self.layers(world_input, mask=causal_mask)
        return self.unit_head(hidden)


class WaveformDecoder(nn.Module):
    def __init__(self, config: AntVoiceConfig) -> None:
        super().__init__()
        last_channel = config.encoder_channels[-1]
        self.projection = nn.Linear(config.d_model, last_channel)
        layers: list[nn.Module] = []
        for index in range(len(config.encoder_channels) - 1, -1, -1):
            in_channel = config.encoder_channels[index]
            out_channel = 1 if index == 0 else config.encoder_channels[index - 1]
            layers.append(
                nn.ConvTranspose1d(
                    in_channel,
                    out_channel,
                    kernel_size=config.encoder_kernels[index],
                    stride=config.encoder_strides[index],
                    padding=(config.encoder_kernels[index] - 1) // 2,
                    output_padding=config.encoder_strides[index] - 1,
                )
            )
        self.layers = nn.ModuleList(layers)

    def forward(self, latent: torch.Tensor, target_samples: int) -> torch.Tensor:
        decoded = self.projection(latent).transpose(1, 2)
        for index, layer in enumerate(self.layers):
            decoded = layer(decoded)
            decoded = torch.tanh(decoded) if index == len(self.layers) - 1 else F.gelu(decoded)
        decoded = decoded.squeeze(1)
        if decoded.shape[1] < target_samples:
            decoded = F.pad(decoded, (0, target_samples - decoded.shape[1]))
        return decoded[:, :target_samples]


class AntVoiceModel(nn.Module):
    def __init__(self, config: AntVoiceConfig) -> None:
        super().__init__()
        config.validate()
        self.config = config
        self.encoder = WaveformEncoder(config)
        self.temporal = TemporalStack(config)
        self.boundary_head = nn.Linear(config.d_model, 1)
        self.quantizer = VectorQuantizer(
            config.codebook_size,
            config.d_model,
            config.vq_commitment_cost,
        )
        self.world_model = CausalUnitWorldModel(config)
        self.decoder = WaveformDecoder(config)
        self.register_buffer(
            "initialization_seed",
            torch.tensor(config.seed, dtype=torch.int64),
            persistent=True,
        )

    def _boundary_targets(self, encoded: torch.Tensor) -> torch.Tensor:
        novelty = torch.zeros(
            encoded.shape[:2], device=encoded.device, dtype=encoded.dtype
        )
        novelty[:, 1:] = (encoded[:, 1:] - encoded[:, :-1]).abs().mean(dim=-1)
        threshold = torch.quantile(
            novelty.detach(),
            1.0 - self.config.boundary_target_rate,
            dim=1,
            keepdim=True,
        )
        targets = (novelty.detach() >= threshold).to(dtype=encoded.dtype)
        targets[:, 0] = 1.0
        return targets

    def forward(self, waveform: torch.Tensor) -> dict[str, torch.Tensor]:
        if not waveform.is_floating_point():
            raise ValueError("waveform tensor must be floating point")
        encoded = self.temporal(self.encoder(waveform))
        boundary_logits = self.boundary_head(encoded).squeeze(-1)
        boundary_probabilities = torch.sigmoid(boundary_logits)
        quantized = self.quantizer(encoded)

        decoder_input = quantized.straight_through * (
            1.0 + 0.1 * boundary_probabilities.unsqueeze(-1)
        )
        reconstruction = self.decoder(decoder_input, waveform.shape[1])
        unit_logits = self.world_model(quantized.unit_ids)

        reconstruction_loss = F.l1_loss(reconstruction, waveform)
        world_loss = F.cross_entropy(
            unit_logits.reshape(-1, self.config.codebook_size),
            quantized.unit_ids.reshape(-1),
        )
        boundary_loss = F.binary_cross_entropy_with_logits(
            boundary_logits,
            self._boundary_targets(encoded),
        )
        total_loss = (
            self.config.reconstruction_weight * reconstruction_loss
            + self.config.vq_weight * quantized.loss
            + self.config.world_weight * world_loss
            + self.config.boundary_weight * boundary_loss
        )
        return {
            "loss": total_loss,
            "reconstruction_loss": reconstruction_loss,
            "vq_loss": quantized.loss,
            "codebook_loss": quantized.codebook_loss,
            "commitment_loss": quantized.commitment_loss,
            "world_loss": world_loss,
            "boundary_loss": boundary_loss,
            "reconstruction": reconstruction,
            "unit_ids": quantized.unit_ids,
            "unit_logits": unit_logits,
            "boundary_probabilities": boundary_probabilities,
        }


def _subseed(seed: int, parameter_name: str) -> int:
    encoded = f"{seed}:{parameter_name}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(encoded).digest()[:8], "little") % (
        2**63 - 1
    )


def initialize_from_explicit_seed(model: nn.Module, seed: int) -> None:
    """Overwrite every trainable tensor from stable name-derived random seeds."""

    with torch.no_grad():
        for name, parameter in sorted(model.named_parameters()):
            generator = torch.Generator(device=parameter.device)
            generator.manual_seed(_subseed(seed, name))
            lowered = name.lower()
            if parameter.ndim >= 2:
                fan_in = math.prod(parameter.shape[1:])
                parameter.normal_(
                    mean=0.0,
                    std=math.sqrt(2.0 / max(fan_in, 1)),
                    generator=generator,
                )
            elif name.endswith("weight") and "norm" in lowered:
                parameter.uniform_(0.98, 1.02, generator=generator)
            else:
                parameter.uniform_(-0.02, 0.02, generator=generator)


def build_model(config: AntVoiceConfig) -> AntVoiceModel:
    config.validate()
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(config.seed)
        model = AntVoiceModel(config)
        initialize_from_explicit_seed(model, config.seed)
    return model
