from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import IntEnum

import torch
from torch import Tensor, nn


class DevelopmentStage(IntEnum):
    VOICE_BABBLE = 0
    AUDIO_VISION = 1
    SYMBOL_GROUNDING = 2
    REASONING_MOTOR = 3


@dataclass(frozen=True)
class HolobrainConfig:
    model_id: str
    seed: int
    latent_dim: int = 96
    vocal_controls: int = 16
    motor_actions: int = 12
    symbol_vocabulary: int = 128
    reasoning_steps: int = 4
    stage: DevelopmentStage = DevelopmentStage.VOICE_BABBLE
    queen: bool = False


class TinyHolobrain(nn.Module):
    """A small multimodal neural core with no pretrained components."""

    def __init__(self, config: HolobrainConfig) -> None:
        super().__init__()
        self.config = config
        width = config.latent_dim

        # fork_rng prevents one ant's initialization from changing another
        # model's global random stream.
        with torch.random.fork_rng(devices=[]):
            torch.manual_seed(config.seed)
            self.audio_encoder = nn.Sequential(
                nn.Conv1d(1, 32, kernel_size=9, stride=4, padding=4),
                nn.GELU(),
                nn.Conv1d(32, width, kernel_size=7, stride=4, padding=3),
                nn.GELU(),
                nn.AdaptiveAvgPool1d(1),
            )
            self.vision_encoder = nn.Sequential(
                nn.Conv2d(3, 24, kernel_size=5, stride=2, padding=2),
                nn.GELU(),
                nn.Conv2d(24, width, kernel_size=3, stride=2, padding=1),
                nn.GELU(),
                nn.AdaptiveAvgPool2d((1, 1)),
            )
            self.symbol_embedding = nn.Embedding(config.symbol_vocabulary, width)
            self.sensory_fusion = nn.Sequential(
                nn.Linear(width * 3, width),
                nn.LayerNorm(width),
                nn.GELU(),
            )
            self.workspace_cell = nn.GRUCell(width, width)
            self.reasoning_cell = nn.GRUCell(width, width)
            self.world_predictor = nn.Linear(width, width)
            self.vocal_head = nn.Sequential(
                nn.Linear(width, width),
                nn.GELU(),
                nn.Linear(width, config.vocal_controls),
                nn.Tanh(),
            )
            self.motor_head = nn.Sequential(
                nn.Linear(width, width),
                nn.GELU(),
                nn.Linear(width, config.motor_actions),
                nn.Tanh(),
            )
            self.queen_curriculum_head = (
                nn.Linear(width, 8) if config.queen else None
            )

    def forward(
        self,
        *,
        audio: Tensor,
        vision: Tensor | None = None,
        symbols: Tensor | None = None,
        previous_workspace: Tensor | None = None,
    ) -> dict[str, Tensor | bool]:
        if not torch.is_floating_point(audio) or audio.ndim != 3 or audio.shape[1] != 1:
            raise ValueError("audio must be floating tensor [batch, 1, samples]")

        audio_latent = self.audio_encoder(audio).squeeze(-1)
        batch, width = audio_latent.shape

        vision_enabled = self.config.stage >= DevelopmentStage.AUDIO_VISION
        if vision_enabled and vision is not None:
            if vision.ndim != 4 or vision.shape[1] != 3:
                raise ValueError("vision must be tensor [batch, 3, height, width]")
            vision_latent = self.vision_encoder(vision).flatten(1)
        else:
            vision_latent = torch.zeros_like(audio_latent)

        symbols_enabled = self.config.stage >= DevelopmentStage.SYMBOL_GROUNDING
        if symbols is not None and not symbols_enabled:
            raise ValueError("symbols are forbidden before SYMBOL_GROUNDING")
        if symbols_enabled and symbols is not None:
            if symbols.ndim != 2:
                raise ValueError("symbols must be integer tensor [batch, sequence]")
            symbol_latent = self.symbol_embedding(symbols).mean(dim=1)
        else:
            symbol_latent = torch.zeros_like(audio_latent)

        sensory = self.sensory_fusion(
            torch.cat((audio_latent, vision_latent, symbol_latent), dim=-1)
        )
        if previous_workspace is None:
            previous_workspace = torch.zeros(
                batch, width, dtype=sensory.dtype, device=sensory.device
            )
        workspace = self.workspace_cell(sensory, previous_workspace)

        reasoning_enabled = self.config.stage >= DevelopmentStage.REASONING_MOTOR
        if reasoning_enabled:
            for _ in range(self.config.reasoning_steps):
                workspace = self.reasoning_cell(sensory, workspace)

        motor_enabled = reasoning_enabled
        motor = (
            self.motor_head(workspace)
            if motor_enabled
            else torch.zeros(
                batch,
                self.config.motor_actions,
                dtype=workspace.dtype,
                device=workspace.device,
            )
        )

        result: dict[str, Tensor | bool] = {
            "audio_latent": audio_latent,
            "workspace": workspace,
            "world_prediction": self.world_predictor(workspace),
            "vocal_controls": self.vocal_head(workspace),
            "motor_actions": motor,
            "vision_enabled": vision_enabled,
            "symbols_enabled": symbols_enabled,
            "reasoning_enabled": reasoning_enabled,
            "motor_enabled": motor_enabled,
        }
        if self.queen_curriculum_head is not None:
            result["curriculum_scores"] = self.queen_curriculum_head(workspace)
        return result

    def fingerprint(self) -> str:
        digest = hashlib.sha256()
        for name, tensor in sorted(self.state_dict().items()):
            digest.update(name.encode("utf-8"))
            digest.update(tensor.detach().cpu().contiguous().numpy().tobytes())
        return digest.hexdigest()

    @property
    def parameter_count(self) -> int:
        return sum(parameter.numel() for parameter in self.parameters())
