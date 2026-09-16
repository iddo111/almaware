# model.py — DarwishLM: compact from-scratch audio-token transformer + JEPA-style gist head.
# DAC gives [9 codebooks, T] tokens @ ~86 steps/sec, vocab 1024 per codebook.
# Parallel-codebook scheme: one position per timestep; embeddings summed across
# codebooks on the way in, 9 independent heads on the way out (MusicGen-parallel,
# the simplest scheme that trains well at this scale).
# Gist head: from each position, predict the MEAN input embedding of the next BAR
# (128 steps = 1.486s at 86.13 Hz — a fixed lookahead, NOT beat-aligned; it equals
# one 4/4 bar only at ~161.5 BPM, above the project's own 120-160 BPM band).
# predict-the-gist, Eran holobrain DNA.
import math

import torch
import torch.nn as nn
import torch.nn.functional as F

N_CODEBOOKS = 9
VOCAB = 1024
BAR = 128  # timesteps = 1.486s fixed lookahead (NOT a true, beat-aligned bar; see header note)


def _rope(q, k):
    """Rotary position embedding applied to q,k: [B, H, T, Dh]."""
    dh = q.shape[-1]
    t = q.shape[-2]
    half = dh // 2
    freqs = torch.exp(
        -math.log(10000.0) * torch.arange(0, half, device=q.device, dtype=torch.float32) / half
    )
    angles = torch.arange(t, device=q.device, dtype=torch.float32)[:, None] * freqs[None, :]
    cos, sin = angles.cos()[None, None], angles.sin()[None, None]

    def rot(x):
        x1, x2 = x[..., :half], x[..., half:]
        return torch.cat([x1 * cos - x2 * sin, x1 * sin + x2 * cos], dim=-1)

    return rot(q), rot(k)


class Block(nn.Module):
    def __init__(self, d, n_head):
        super().__init__()
        self.n_head = n_head
        self.ln1 = nn.LayerNorm(d)
        self.qkv = nn.Linear(d, 3 * d, bias=False)
        self.proj = nn.Linear(d, d, bias=False)
        self.ln2 = nn.LayerNorm(d)
        self.mlp = nn.Sequential(
            nn.Linear(d, 4 * d, bias=False), nn.GELU(), nn.Linear(4 * d, d, bias=False)
        )

    def forward(self, x):
        b, t, d = x.shape
        q, k, v = self.qkv(self.ln1(x)).chunk(3, dim=-1)
        q = q.view(b, t, self.n_head, -1).transpose(1, 2)
        k = k.view(b, t, self.n_head, -1).transpose(1, 2)
        v = v.view(b, t, self.n_head, -1).transpose(1, 2)
        q, k = _rope(q, k)
        y = F.scaled_dot_product_attention(q, k, v, is_causal=True)
        y = y.transpose(1, 2).reshape(b, t, d)
        x = x + self.proj(y)
        return x + self.mlp(self.ln2(x))


class DarwishLM(nn.Module):
    def __init__(self, vocab=VOCAB, n_layer=20, d=1024, n_head=16, n_codebooks=N_CODEBOOKS):
        super().__init__()
        self.n_codebooks = n_codebooks
        self.vocab = vocab
        self.embed = nn.ModuleList(nn.Embedding(vocab, d) for _ in range(n_codebooks))
        self.blocks = nn.ModuleList(Block(d, n_head) for _ in range(n_layer))
        self.ln_f = nn.LayerNorm(d)
        self.heads = nn.Linear(d, n_codebooks * vocab, bias=False)
        self.gist_head = nn.Linear(d, d, bias=False)

    def embed_tokens(self, tokens):
        """tokens [B, K, T] -> summed embedding [B, T, D]."""
        return sum(self.embed[k](tokens[:, k]) for k in range(self.n_codebooks))

    def forward(self, tokens):
        """tokens [B, K, T] -> (logits [B, K, T, vocab], gist_pred [B, T, D])."""
        x = self.embed_tokens(tokens)
        for blk in self.blocks:
            x = blk(x)
        x = self.ln_f(x)
        b, t, d = x.shape
        logits = self.heads(x).view(b, t, self.n_codebooks, self.vocab).permute(0, 2, 1, 3)
        return logits, self.gist_head(x)


def loss_fn(model, tokens, gist_weight=0.1):
    """tokens [B, K, T] int64. Next-token CE across codebooks + gist cosine loss."""
    inp, tgt = tokens[..., :-1], tokens[..., 1:]
    logits, gist_pred = model(inp)
    ce = F.cross_entropy(logits.reshape(-1, model.vocab), tgt.reshape(-1))

    # Gist target: mean input embedding of the NEXT BAR at each bar boundary.
    with torch.no_grad():
        emb = model.embed_tokens(tokens)  # [B, T, D]
    t = inp.shape[-1]
    n_bars = (t - 1) // BAR
    gist = torch.tensor(0.0, device=tokens.device)
    if n_bars >= 1:
        preds, tgts = [], []
        for i in range(n_bars):
            end = (i + 1) * BAR - 1          # position predicting from
            nxt = emb[:, end + 1 : end + 1 + BAR].mean(dim=1)  # next bar's mean gist
            preds.append(gist_pred[:, end])
            tgts.append(nxt)
        gist = 1.0 - F.cosine_similarity(
            torch.stack(preds, 1), torch.stack(tgts, 1), dim=-1
        ).mean()
    return ce + gist_weight * gist, {"ce": float(ce), "gist": float(gist)}
