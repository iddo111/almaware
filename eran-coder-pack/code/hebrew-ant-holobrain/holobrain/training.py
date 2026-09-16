from __future__ import annotations

import copy
from dataclasses import dataclass

import torch
from torch import Tensor

from .model import TinyHolobrain


@dataclass(frozen=True)
class PromotionDecision:
    promoted: bool
    reason: str
    old_fingerprint: str
    candidate_fingerprint: str


class AutonomousAnt:
    """Inference stays on active weights while the shadow learns."""

    def __init__(self, model: TinyHolobrain, *, learning_rate: float = 1e-3) -> None:
        self.identity = model.config.model_id
        self.active = model
        self.shadow = copy.deepcopy(model)
        self.optimizer = torch.optim.AdamW(
            self.shadow.parameters(), lr=learning_rate, weight_decay=1e-4
        )
        self.rollback_state: dict[str, Tensor] | None = None
        self.training_steps = 0
        self.checkpoint_version = 0

    @torch.no_grad()
    def infer(self, *, audio: Tensor, vision: Tensor | None = None) -> dict:
        self.active.eval()
        return self.active(audio=audio, vision=vision)

    def self_supervised_step(
        self, *, audio: Tensor, vision: Tensor | None = None
    ) -> float:
        self.shadow.train()
        output = self.shadow(audio=audio, vision=vision)
        prediction = output["world_prediction"]
        target = output["audio_latent"].detach()
        vocal = output["vocal_controls"]
        loss = torch.nn.functional.mse_loss(prediction, target)
        loss = loss + 0.01 * vocal.square().mean()
        self.optimizer.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.shadow.parameters(), max_norm=1.0)
        self.optimizer.step()
        self.training_steps += 1
        return float(loss.detach())

    def promote(
        self,
        *,
        active_metric: float,
        candidate_metric: float,
        provenance_passed: bool,
        safety_passed: bool,
        minimum_relative_gain: float = 0.02,
    ) -> PromotionDecision:
        old = self.active.fingerprint()
        candidate = self.shadow.fingerprint()
        if not provenance_passed:
            return PromotionDecision(False, "provenance failed", old, candidate)
        if not safety_passed:
            return PromotionDecision(False, "safety evaluation failed", old, candidate)
        required = active_metric * (1.0 + minimum_relative_gain)
        if candidate_metric < required:
            return PromotionDecision(False, "evaluation gain too small", old, candidate)

        self.rollback_state = copy.deepcopy(self.active.state_dict())
        self.active.load_state_dict(self.shadow.state_dict())
        if self.active.config.model_id != self.identity:
            raise RuntimeError("checkpoint promotion attempted to replace identity")
        self.shadow = copy.deepcopy(self.active)
        self.optimizer = torch.optim.AdamW(
            self.shadow.parameters(),
            lr=self.optimizer.param_groups[0]["lr"],
            weight_decay=1e-4,
        )
        self.checkpoint_version += 1
        return PromotionDecision(True, "candidate promoted atomically", old, candidate)
