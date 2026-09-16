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

    residual=True (default; d_in == d_out is REQUIRED and now raises if violated) starts
    the adapter AT the frozen backbone: the whole residual branch is zero-initialised, so
    output == input EXACTLY at step 0 (== the zero-shot column) and contrastive fine-tuning
    can only nudge it, never scramble it from a random init. This is what fixes the earlier
    collapse (a randomly-initialised linear/MLP head overfit 669 examples within one epoch
    and got WORSE than doing nothing).

    2026-09-06: until today only proj_in was zeroed, which is NOT enough (see MIKO-02 in
    __init__) -- adapter-v1.pt is therefore e5 zero-shot plus one constant offset."""

    def __init__(self, d_in: int = 384, d_out: int = 384, depth: int = 1, residual: bool = True):
        super().__init__()
        # MIKO-08 (code revision 2026-09-06): this used to be `residual and (d_in == d_out)`,
        # so asking for residual=True with d_out != d_in SILENTLY dropped to the random-init
        # head the 09-03 report itself found "worse than doing nothing" -- and the file's own
        # defaults (d_out=256) did exactly that. Refuse loudly instead of degrading quietly.
        if residual and d_in != d_out:
            raise ValueError(
                f"Adapter(residual=True) requires d_in == d_out; got d_in={d_in} d_out={d_out}. "
                "Pass residual=False explicitly if you really want the random-init head."
            )
        self.residual = bool(residual)
        self.proj_in = nn.Linear(d_in, d_out)
        self.blocks = nn.ModuleList([ResBlock(d_out) for _ in range(depth)])
        if self.residual:
            # MIKO-02 (code revision 2026-09-06): zeroing proj_in ALONE did not make the
            # adapter an identity at step 0 -- every ResBlock's fc1/fc2 biases are randomly
            # initialised, so blk(0) != 0 and the whole 09-03 run amounted to adding ONE
            # constant vector (|c| = 0.448 measured from adapter-v1.pt) to every frozen e5
            # embedding. Zero the residual branch END-TO-END (proj_in AND every block's fc2)
            # so out == x EXACTLY at step 0, which is what the docstring below claims.
            # Gradient still flows: dL/d(proj_in) rides the blocks' identity path.
            nn.init.zeros_(self.proj_in.weight)
            nn.init.zeros_(self.proj_in.bias)
            for blk in self.blocks:
                nn.init.zeros_(blk.fc2.weight)
                nn.init.zeros_(blk.fc2.bias)
        self.out_norm = nn.LayerNorm(d_out) if not self.residual else nn.Identity()
        # MIKO-01 (code revision 2026-09-06): was `log(0.05)` -> logit_scale() = 0.05, which
        # adapter_train.py MULTIPLIES into the logits. CLIP's convention is 1/T = 20.0.
        self.temp = nn.Parameter(torch.tensor(1.0 / 0.05).log())  # log INVERSE temperature

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
