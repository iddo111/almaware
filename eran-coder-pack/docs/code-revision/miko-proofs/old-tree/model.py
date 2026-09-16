"""MIKO v1 -- the real neural retriever.  לזכרה של עלמה ז"ל.

Iddo, 2026-09-03 19:20: "I want MIKO to finally be a REAL neural network."

Honest and small, per the brief:
  (a) tokenizer  = hashed char n-grams (hashvocab.py) -- no external vocab
  (b) bi-encoder = ONE tower (query and doc share every weight), a few residual
                   MLP blocks over mean-pooled n-gram embeddings, L2-normalised output
  loss           = InfoNCE, in-batch negatives + mined BM25 hard negatives (train.py)

This deliberately does NOT reuse miko/model's court/Beit-Din machinery: that
architecture's own first experiment (2026-08-29) found the court and the three-factor
loop contributed nothing over a vanilla net. This net IS the vanilla net, trained
properly this time, with a real gradient and a real contrastive objective.

SCAR GUARD (see scar_guard.py): the 2026-08-29 catastrophe was `nn.LayerNorm(1)`,
which normalises over a one-element axis and is therefore identically zero for every
input -- any scalar head ending in LayerNorm is a constant. This model has no
LayerNorm over a size-1 axis anywhere; scar_guard.py asserts that by inspection AND
by running two different inputs through the score head and checking they differ.
"""
from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F

from hashvocab import ngram_ids

VOCAB_SIZE = 1 << 18   # 262144 hash buckets


class ResBlock(nn.Module):
    def __init__(self, d: int, hidden_mult: int = 2, p: float = 0.1):
        super().__init__()
        h = d * hidden_mult
        self.fc1 = nn.Linear(d, h)
        self.fc2 = nn.Linear(h, d)
        self.norm = nn.LayerNorm(d)          # normalises over d (>1) -- not the scar
        self.drop = nn.Dropout(p)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        y = self.fc1(self.norm(x))
        y = F.gelu(y)
        y = self.drop(y)
        y = self.fc2(y)
        return x + y


class MikoBiEncoder(nn.Module):
    """One tower, shared for query and document. Ranking = one dot product."""

    def __init__(self, d: int = 192, depth: int = 3, vocab_size: int = VOCAB_SIZE,
                 ns=(3, 4, 5), max_grams: int = 512):
        super().__init__()
        self.d = d
        self.vocab_size = vocab_size
        self.ns = ns
        self.max_grams = max_grams
        self.emb = nn.EmbeddingBag(vocab_size, d, mode="mean")
        self.blocks = nn.ModuleList([ResBlock(d) for _ in range(depth)])
        self.out_norm = nn.LayerNorm(d)      # d-dim, not the scar
        self.temp = nn.Parameter(torch.tensor(float(0.07)).log())  # log-temperature

    # ---- tokenizing is outside autograd, done once per text ----
    def tokenize(self, texts: list[str]) -> tuple[torch.Tensor, torch.Tensor]:
        flat, offsets = [], [0]
        for t in texts:
            ids = ngram_ids(t, self.vocab_size, self.ns, self.max_grams)
            flat.extend(ids)
            offsets.append(offsets[-1] + len(ids))
        idx = torch.tensor(flat, dtype=torch.long)
        off = torch.tensor(offsets[:-1], dtype=torch.long)
        return idx, off

    def encode(self, texts: list[str], device=None) -> torch.Tensor:
        idx, off = self.tokenize(texts)
        if device is not None:
            idx, off = idx.to(device), off.to(device)
        x = self.emb(idx, off)               # (B, d)  mean-pooled n-gram embedding
        for blk in self.blocks:
            x = blk(x)
        x = self.out_norm(x)
        return F.normalize(x, dim=-1)

    def score(self, texts_a: list[str], texts_b: list[str], device=None) -> torch.Tensor:
        """Score head for the scar guard: cosine sim of a pair, as a (B,) vector."""
        a = self.encode(texts_a, device)
        b = self.encode(texts_b, device)
        return (a * b).sum(-1)

    def logit_scale(self) -> torch.Tensor:
        return self.temp.exp().clamp(max=100.0)


def param_count(m: nn.Module) -> int:
    return sum(p.numel() for p in m.parameters())
