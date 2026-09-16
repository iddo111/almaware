"""MIKO v1 -- the adapter head trained on top of FROZEN e5-small embeddings.

Small on purpose (distillation scaling, not pretraining scaling -- Busbridge et al.,
ICML'25): a couple of residual blocks over the 384-dim frozen vector, contrastively
fine-tuned on OUR split with OUR hard negatives. This is the "product" variant the
Chinchilla numbers argue for.
"""
from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F


class ResBlock(nn.Module):
    def __init__(self, d: int, hidden_mult: int = 2, p: float = 0.1):
        super().__init__()
        h = d * hidden_mult
        self.norm = nn.LayerNorm(d)          # over d (384 or so) -- not the scar
        self.fc1 = nn.Linear(d, h)
        self.fc2 = nn.Linear(h, d)
        self.drop = nn.Dropout(p)

    def forward(self, x):
        y = self.fc1(self.norm(x))
        y = F.gelu(y)
        y = self.drop(y)
        y = self.fc2(y)
        return x + y


class Adapter(nn.Module):
    """frozen e5 embedding (384) -> adapter -> final retrieval embedding, L2-normalised.

    residual=True (default, and d_in==d_out required) starts the adapter AT the frozen
    backbone: proj is zero-initialised, so output == input at step 0 (== the zero-shot
    column) and contrastive fine-tuning can only nudge it, never scramble it from a
    random init. This fixed the earlier collapse (a randomly-initialised linear/MLP
    head overfit 669 examples within one epoch and got WORSE than doing nothing)."""

    def __init__(self, d_in: int = 384, d_out: int = 256, depth: int = 2, residual: bool = True):
        super().__init__()
        self.residual = residual and (d_in == d_out)
        self.proj_in = nn.Linear(d_in, d_out)
        if self.residual:
            nn.init.zeros_(self.proj_in.weight)
            nn.init.zeros_(self.proj_in.bias)
        self.blocks = nn.ModuleList([ResBlock(d_out) for _ in range(depth)])
        self.out_norm = nn.LayerNorm(d_out) if not self.residual else nn.Identity()
        self.temp = nn.Parameter(torch.tensor(float(0.05)).log())

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if self.residual:
            y = self.proj_in(x)
            for blk in self.blocks:
                y = blk(y)
            out = x + y
        else:
            out = self.proj_in(x)
            for blk in self.blocks:
                out = blk(out)
            out = self.out_norm(out)
        return F.normalize(out, dim=-1)

    def logit_scale(self) -> torch.Tensor:
        return self.temp.exp().clamp(max=100.0)


def param_count(m: nn.Module) -> int:
    return sum(p.numel() for p in m.parameters())
