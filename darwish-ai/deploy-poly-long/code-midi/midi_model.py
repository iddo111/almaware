# -*- coding: utf-8 -*-
"""midi_model.py — DarwishMIDI: the small ALMA-stack model over the lean MIDI tokens.

WHY SMALL, AND WHY THAT IS THE POINT
------------------------------------
The 271.7M audio brain spends hundreds of tokens per second on TIMBRE, so it can
never hold a whole track in context and can only learn texture. midi_lean.py spends
~10 tokens per second on STRUCTURE. At that rate an 8192-token window is ~13.4
minutes of music — a whole single track, BOS to EOS. So this model is small not to
be cheap but to be able to look at FORM: build, drop, breakdown, and back.

Context length is the deliverable. Parameter count is the price.

SEQ_T = 8192 was chosen from the corpus, not from the GPU (see survey): on the
clean 173-track corpus 8192 holds 122 tracks whole (100% of the singles). 16384
buys only 4 more. 65536 would hold a whole 3-hour DJ set but there are only 51
clean sets, so a 64k window gives ~51 examples of "what a set looks like" — that
memorises, it does not generalise.

THE VOCABULARY (from midi_lean.py, verified against all 191 corpus files)
-------------------------------------------------------------------------
    token = drums * 13 + deg,   drums 0..7 (kick|body|hat bits), deg 0..12
    104 BAR   (after every 16 grid steps)      105 PHRASE (every 16 bars)
    106 BOS   107 EOS                          -> VOCAB = 108

HOW LONG IS A BAR, IN TOKENS — COMPUTED, NOT GUESSED
-----------------------------------------------------
midi_lean.py emits one token per 16th note and a BAR token after every 16 of them
(`if i % 16 == 15`). 16 sixteenth notes = 4 beats = one musical bar. So

    one bar = 16 grid tokens + 1 BAR token = 17 tokens.

Time cross-check at the corpus median 143.55 BPM: a 4-beat bar is 4*60/143.55 =
1.6720 s; 17 tokens / 1.6720 s = 10.17 tok/s, and the measured corpus median is
10.20 tok/s. Every 16th bar also carries a PHRASE token, so it is 18; measured
BAR-to-BAR gaps over the corpus are 17 in 186,544 cases and 18 in 12,340 cases,
mean 17.0625. BAR_TOKENS = 17 below is that nominal value.

BUT THE MODEL DOES NOT USE A FIXED STRIDE. It reads the actual BAR tokens out of
the stream (`bar_index()`), which is exact and handles 17 and 18 identically. The
constant is documentation and a fallback, nothing else depends on it.

THE THREE ALMA PIECES, AS REAL LAYERS
--------------------------------------
1. BEIT DIN (`BeitDin`) — three opinions, one ruling, per element.
   thesis and antithesis are independent MLP branches on the same input.
   synthesis is a third branch that ALSO sees the disagreement (thesis - antithesis):
   the third judge hears the argument before it rules. The output is the element-wise
   MEDIAN of the three. Three is odd, so a middle value always exists — there is
   always a ruling — and no single branch, however extreme, can carry the vote.
   Median-of-3 is computed as clamp(a, min(b,c), max(b,c)), which is exact, dtype-safe
   and differentiable almost everywhere.
   WHAT IT BUYS: an outlier branch is bounded by the other two, so one branch blowing
   up cannot move the layer output past them. WHAT IT COSTS: ~1.75x the parameters and
   FLOPs of a standard 4x GELU MLP, and the gradient of each element reaches exactly
   ONE branch. You pay for three opinions and use one. That is the honest trade, and
   whether it beats a plain MLP on this corpus is an OPEN EMPIRICAL QUESTION — this
   file implements it, it does not claim it wins.

2. GIST3D++ (`BarMemory`) — coarse bar-level memory, strictly causal.
   Hidden states are mean-pooled per bar into one gist vector per bar, and every
   position cross-attends over that coarse memory in addition to its fine-grained
   causal self-attention. CAUSALITY RULE, enforced by the mask:

       a position inside bar s may read memory slots 0..s-1 ONLY.

   Bar s is still in progress at that position, so its pooled gist contains tokens
   from the future; slot s is therefore forbidden. Slots < s are bars that have already
   been closed by a BAR token, so they lie entirely in the past. A learned SINK slot is
   always visible so that positions in bar 0 have something to attend to instead of an
   all-masked softmax. RoPE is applied in BAR units (query at bar s, key at bar j), so
   the memory has a real sense of "how many bars ago", not just content.
   `test_causality.py` breaks this on purpose and shows the test fails.

3. JEPA (`loss_fn`) — predict the GIST of the next span, not its tokens.
   At every position the model predicts the MEAN INPUT EMBEDDING of the NEXT BAR
   (bar s+1 while inside bar s), trained with a cosine loss at weight 0.1 — the same
   objective the big audio model uses, with BAR taken from the real token stream.
   The target is computed under no_grad from the input embedding table, so the gist
   term cannot collapse the representation by pulling target and prediction together.
   Only positions whose target bar is CLOSED (i.e. a later bar exists in the window)
   are scored, so a truncated final bar never becomes a target.

AUTO-EVOLVE — WHAT IS REAL AND WHAT IS NOT
-------------------------------------------
REAL, in this file and the trainer built around it: nothing is ever frozen, training
is resumable and can run forever, and the frozen by-track heldout split exists so that
forgetting or collapse would SHOW UP as a rising heldout loss.
NOT SOLVED, and not claimed: catastrophic forgetting, and collapse under self-training
on the model's own output. This file contains no mechanism that fixes either. Held-out
tracking DETECTS the symptom; it does not prevent the disease.

MEASURED ON eran4 (GB10, torch 2.13.0+cu130) — not estimates
-------------------------------------------------------------
  parameters              24,773,120  (24.773 M)
     BEIT DIN triad       17,210,880  69.5%
     self-attention        4,922,880  19.9%
     GIST3D++ bar memory   2,467,200  10.0%
     embed / head / gist     171,560   0.6%
  B=2, T=8192 fwd+bwd     2.58 s, peak 4.89 GiB, grad-norm 0.92, all 197 tensors got grad
  CE at init              4.6821 = ln(108) exactly (head is zero-initialised)
  gist at init            0.9837 (~1.0 = cosine of unrelated vectors, as it should be)
  400 steps, B=4 T=2048, real train split, heldout CE 4.6821 -> 2.9948, gist 0.984 -> 0.465
     for scale: uniform ln(108) = 4.6821, corpus unigram = 4.2753 nats (6.168 bits/tok),
     so it is 1.28 nats past unigram after 400 steps — it is using context, not just
     token frequencies. 400 steps proves the machine turns; it proves nothing about form.
  BEIT DIN ruling census  ~0.33 / 0.33 / 0.33 per branch, mean spread 0.16 — the three
     branches genuinely disagree and each one carries about a third of the elements.

House style follows ~/darwish-ai/code/model.py: pre-norm blocks, RoPE,
F.scaled_dot_product_attention, and a loss_fn(model, tokens) -> (loss, {"ce","gist"}).
"""
from __future__ import annotations

import math

import torch
import torch.nn as nn
import torch.nn.functional as F

VOCAB = 108
TOK_BAR, TOK_PHRASE, TOK_BOS, TOK_EOS = 104, 105, 106, 107

BAR_TOKENS = 17          # 16 grid tokens + the BAR token. Nominal; see module docstring.
SEQ_T = 8192             # ~13.4 min of music ~ 482 bars ~ 30 phrase blocks


# ---------------------------------------------------------------- rotary

def _rope(x: torch.Tensor, pos: torch.Tensor) -> torch.Tensor:
    """Rotary embedding at EXPLICIT positions.

    x   [B, H, N, Dh]
    pos [B, N]  — the position of each element. For self-attention this is
                  arange(T); for the bar memory it is the BAR INDEX, which is what
                  makes the memory attention aware of "how many bars ago".
    """
    dh = x.shape[-1]
    half = dh // 2
    freqs = torch.exp(
        -math.log(10000.0)
        * torch.arange(half, device=x.device, dtype=torch.float32) / half
    )
    ang = pos.to(torch.float32)[..., None] * freqs           # [B, N, half]
    cos, sin = ang.cos()[:, None], ang.sin()[:, None]        # [B, 1, N, half]
    x1, x2 = x[..., :half], x[..., half:]
    return torch.cat([x1 * cos - x2 * sin, x1 * sin + x2 * cos], dim=-1).to(x.dtype)


# ---------------------------------------------------------------- bar structure

def bar_index(tokens: torch.Tensor) -> torch.Tensor:
    """[B, T] tokens -> [B, T] bar id.

    The id is the number of BAR tokens emitted up to and INCLUDING this position,
    so bar j is the run [BAR_j, its 16 grid tokens, (PHRASE)] and bar 0 is
    [BOS, first 16 grid tokens]. Exact for both 17- and 18-token bars.
    """
    return (tokens == TOK_BAR).to(torch.long).cumsum(dim=1)


def bar_pooling(seg: torch.Tensor, n_bar: int) -> tuple[torch.Tensor, torch.Tensor]:
    """Row-normalised pooling matrix P [B, n_bar, T] and occupancy counts [B, n_bar].

    P @ x is the per-bar MEAN of x. Built once per forward pass and reused by every
    memory layer and by the JEPA target, and deterministic (scatter_, then bmm) —
    unlike scatter_add_, which uses atomics and would make the causality test flaky.
    Cost is O(B * T * n_bar); fine at T=8192 (n_bar ~ 483), not fine at T=65536.
    """
    b, t = seg.shape
    onehot = torch.zeros(b, t, n_bar, device=seg.device, dtype=torch.float32)
    onehot.scatter_(2, seg.unsqueeze(-1), 1.0)
    counts = onehot.sum(dim=1)                                # [B, n_bar]
    p = onehot.transpose(1, 2) / counts.clamp(min=1.0).unsqueeze(-1)
    return p, counts


def bar_visibility(seg: torch.Tensor, n_bar: int, strict: bool = True) -> torch.Tensor:
    """Causal mask over the bar memory: [B, 1, T, n_bar + 1], True = may attend.

    Column 0 is the always-visible learned SINK. Column j+1 is bar j, visible to a
    position in bar s only when j < s — bar s has not ended yet, so its gist contains
    the future. `strict=False` is the OFF-BY-ONE BUG (j <= s) and exists only so that
    test_causality.py can prove the test has teeth. Never set it in training.
    """
    j = torch.arange(n_bar, device=seg.device)
    vis = (j[None, None, :] < seg[..., None]) if strict else (j[None, None, :] <= seg[..., None])
    sink = torch.ones(seg.shape[0], seg.shape[1], 1, dtype=torch.bool, device=seg.device)
    return torch.cat([sink, vis], dim=-1).unsqueeze(1)


# ---------------------------------------------------------------- layers

class SelfAttention(nn.Module):
    """Fine-grained causal attention over tokens. Same idiom as code/model.py."""

    def __init__(self, d: int, n_head: int):
        super().__init__()
        self.n_head = n_head
        self.ln = nn.LayerNorm(d)
        self.qkv = nn.Linear(d, 3 * d, bias=False)
        self.proj = nn.Linear(d, d, bias=False)

    def forward(self, x, pos):
        b, t, d = x.shape
        q, k, v = self.qkv(self.ln(x)).chunk(3, dim=-1)
        q = q.view(b, t, self.n_head, -1).transpose(1, 2)
        k = k.view(b, t, self.n_head, -1).transpose(1, 2)
        v = v.view(b, t, self.n_head, -1).transpose(1, 2)
        q, k = _rope(q, pos), _rope(k, pos)
        y = F.scaled_dot_product_attention(q, k, v, is_causal=True)
        return x + self.proj(y.transpose(1, 2).reshape(b, t, d))


class BarMemory(nn.Module):
    """GIST3D++ — cross-attention over the coarse, causal, bar-level memory."""

    def __init__(self, d: int, n_head: int):
        super().__init__()
        self.n_head = n_head
        self.ln_x = nn.LayerNorm(d)
        self.ln_m = nn.LayerNorm(d)
        self.q = nn.Linear(d, d, bias=False)
        self.kv = nn.Linear(d, 2 * d, bias=False)
        self.proj = nn.Linear(d, d, bias=False)
        self.sink = nn.Parameter(torch.zeros(1, 1, d))

    def forward(self, x, pool, mask, q_bar_pos, k_bar_pos):
        b, t, d = x.shape
        mem = torch.bmm(pool.to(x.dtype), self.ln_m(x))                 # [B, n_bar, D]
        mem = torch.cat([self.sink.expand(b, -1, -1).to(x.dtype), mem], dim=1)
        s = mem.shape[1]

        q = self.q(self.ln_x(x)).view(b, t, self.n_head, -1).transpose(1, 2)
        k, v = self.kv(mem).chunk(2, dim=-1)
        k = k.view(b, s, self.n_head, -1).transpose(1, 2)
        v = v.view(b, s, self.n_head, -1).transpose(1, 2)
        q = _rope(q, q_bar_pos)                                          # position = bar id
        k = _rope(k, k_bar_pos.expand(b, -1))
        y = F.scaled_dot_product_attention(q, k, v, attn_mask=mask)
        return x + self.proj(y.transpose(1, 2).reshape(b, t, d))


class BeitDin(nn.Module):
    """בית דין — three branches deliberate, the element-wise MEDIAN rules.

    thesis / antithesis: independent MLPs on the same normed input, so they really
    can disagree (different init, no shared weights).
    synthesis: a third MLP that also reads (thesis - antithesis), the מחלוקת itself.
    ruling: median of the three = clamp(thesis, min(anti,syn), max(anti,syn)).

    Three is odd, so the median is always one of the values: there is always a ruling.
    A branch that goes to +/-inf is clamped by the other two and cannot carry it.
    """

    def __init__(self, d: int, mult: int = 2):
        super().__init__()
        h = mult * d
        self.ln = nn.LayerNorm(d)
        self.thesis = nn.Sequential(
            nn.Linear(d, h, bias=False), nn.GELU(), nn.Linear(h, d, bias=False)
        )
        self.antithesis = nn.Sequential(
            nn.Linear(d, h, bias=False), nn.GELU(), nn.Linear(h, d, bias=False)
        )
        self.synthesis = nn.Sequential(
            nn.Linear(2 * d, h, bias=False), nn.GELU(), nn.Linear(h, d, bias=False)
        )
        self.track_dissent = False
        self.vote = None      # [3] fraction of elements each branch ruled
        self.spread = None    # mean (max - min) across the three opinions

    def forward(self, x):
        h = self.ln(x)
        a = self.thesis(h)
        b = self.antithesis(h)
        c = self.synthesis(torch.cat([h, a - b], dim=-1))
        lo = torch.minimum(b, c)
        hi = torch.maximum(b, c)
        ruling = torch.clamp(a, min=lo, max=hi)          # == median(a, b, c)
        if self.track_dissent:
            with torch.no_grad():
                v = torch.stack([(ruling == a), (ruling == b), (ruling == c)]).float()
                self.vote = (v.sum(dim=(1, 2, 3)) / v.sum()).detach().float().cpu()
                self.spread = float(
                    (torch.maximum(a, hi) - torch.minimum(a, lo)).float().mean()
                )
        return x + ruling


class Block(nn.Module):
    def __init__(self, d: int, n_head: int, with_memory: bool, mlp_mult: int):
        super().__init__()
        self.attn = SelfAttention(d, n_head)
        self.memory = BarMemory(d, n_head) if with_memory else None
        self.council = BeitDin(d, mlp_mult)

    def forward(self, x, ctx):
        x = self.attn(x, ctx["pos"])
        if self.memory is not None:
            x = self.memory(x, ctx["pool"], ctx["mask"], ctx["q_bar"], ctx["k_bar"])
        return self.council(x)


# ---------------------------------------------------------------- model

class DarwishMIDI(nn.Module):
    """Single-stream transformer over vocab-108 lean MIDI tokens.

    Defaults: 12 layers, d=320, 5 heads (head dim 64), Beit Din in every block,
    GIST3D++ bar memory in every other block (1, 3, 5, 7, 9, 11).
    """

    def __init__(
        self,
        vocab: int = VOCAB,
        n_layer: int = 12,
        d: int = 320,
        n_head: int = 5,
        mem_every: int = 2,
        mlp_mult: int = 2,
    ):
        super().__init__()
        self.vocab = vocab
        self.d = d
        self.strict_bar_causality = True    # flip only in tests; see bar_visibility()
        self.embed = nn.Embedding(vocab, d)
        self.blocks = nn.ModuleList(
            Block(d, n_head, with_memory=(i % mem_every == mem_every - 1), mlp_mult=mlp_mult)
            for i in range(n_layer)
        )
        self.ln_f = nn.LayerNorm(d)
        self.head = nn.Linear(d, vocab, bias=False)
        self.gist_head = nn.Linear(d, d, bias=False)
        self.apply(self._init)
        # Zero the output head so the model starts at EXACTLY the uniform prior,
        # CE = ln(108) = 4.6821. With a random head it starts slightly WORSE than
        # uniform (sigma^2/2 nats), which makes the first steps look like progress
        # when they are only undoing the initialisation.
        nn.init.zeros_(self.head.weight)

    @staticmethod
    def _init(m):
        if isinstance(m, nn.Linear):
            nn.init.normal_(m.weight, std=0.02)
        elif isinstance(m, nn.Embedding):
            nn.init.normal_(m.weight, std=0.02)

    def n_params(self) -> int:
        return sum(p.numel() for p in self.parameters())

    def set_dissent_tracking(self, on: bool):
        for m in self.modules():
            if isinstance(m, BeitDin):
                m.track_dissent = on

    def dissent_report(self):
        out = []
        for i, blk in enumerate(self.blocks):
            if blk.council.vote is not None:
                out.append((i, blk.council.vote.tolist(), blk.council.spread))
        return out

    def forward(self, tokens: torch.Tensor):
        """tokens [B, T] int64 -> (logits [B, T, vocab], gist_pred [B, T, D], ctx)."""
        b, t = tokens.shape
        seg = bar_index(tokens)                              # [B, T] bar id
        n_bar = int(seg.max().item()) + 1
        pool, counts = bar_pooling(seg, n_bar)
        ctx = {
            "seg": seg,
            "n_bar": n_bar,
            "pool": pool,
            "counts": counts,
            "pos": torch.arange(t, device=tokens.device).expand(b, t),
            # memory RoPE lives in BAR units: sink at 0, bar j at j+1, query at s+1,
            # so the relative offset a position sees is exactly (s - j) bars.
            "q_bar": (seg + 1).to(torch.float32),
            "k_bar": torch.arange(n_bar + 1, device=tokens.device).to(torch.float32)[None],
            "mask": bar_visibility(seg, n_bar, strict=self.strict_bar_causality),
        }
        x = self.embed(tokens)
        for blk in self.blocks:
            x = blk(x, ctx)
        x = self.ln_f(x)
        return self.head(x), self.gist_head(x), ctx


# ---------------------------------------------------------------- loss

def _gist_loss(model, inp, gist_pred, ctx, pad_id):
    """JEPA: cosine loss between gist_pred[t] and the mean INPUT EMBEDDING of bar s+1.

    Target is detached (no_grad on the embedding table) so the gist term cannot make
    prediction and target collapse onto each other. Only positions whose target bar is
    already CLOSED are scored, so a truncated last bar is never a target.
    """
    seg, pool, counts, n_bar = ctx["seg"], ctx["pool"], ctx["counts"], ctx["n_bar"]
    with torch.no_grad():
        emb = model.embed(inp)                                    # [B, T, D]
        bar_emb = torch.bmm(pool.to(emb.dtype), emb)              # [B, n_bar, D]

    last_bar = counts.gt(0).sum(dim=1) - 1                        # [B] highest bar id in row
    nxt = seg + 1
    valid = (nxt + 1) <= last_bar[:, None]                        # bar nxt is closed
    if pad_id is not None:
        valid = valid & (inp != pad_id)
    if not bool(valid.any()):
        return gist_pred.sum() * 0.0

    idx = nxt.clamp(max=n_bar - 1).unsqueeze(-1).expand(-1, -1, bar_emb.shape[-1])
    target = torch.gather(bar_emb, 1, idx)                        # [B, T, D]
    return 1.0 - F.cosine_similarity(
        gist_pred[valid].float(), target[valid].float(), dim=-1
    ).mean()


def loss_fn(model, tokens, gist_weight: float = 0.1, pad_id: int | None = None):
    """tokens [B, T] int64 -> (loss, {"ce": float, "gist": float}).

    Next-token cross-entropy over the 108-token vocabulary + JEPA gist cosine loss.
    Matches the call signature the house trainer already uses.
    """
    inp, tgt = tokens[:, :-1], tokens[:, 1:]
    logits, gist_pred, ctx = model(inp)

    flat = tgt.reshape(-1)
    if pad_id is not None:
        flat = torch.where(flat == pad_id, torch.full_like(flat, -100), flat)
    ce = F.cross_entropy(logits.reshape(-1, model.vocab).float(), flat, ignore_index=-100)

    gist = _gist_loss(model, inp, gist_pred, ctx, pad_id)
    return ce + gist_weight * gist, {"ce": float(ce.detach()), "gist": float(gist.detach())}
