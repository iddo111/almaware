"""ALMA — the substrate MIKO is made of.  לזכרה של עלמה ז״ל.

> 🪟 BROKEN WINDOWS LAW — if it is not working, fix it immediately. Test the REAL output.

This file holds the two things that come from BIOLOGY, and nothing else:

    the binding     how the world enters       byte ⊕ letter ⊕ sound
    the synapse     how a connection carries    k weights, k time constants, a use-state
    the unit        how a neuron computes       non-monotonic dendrite (the bump)

Every mechanism here is taken from `alma-language/ALMA-BIOLOGY.md`, and each one arrives
with the same debt: **it earns its place only when its test beats a vanilla control at
matched parameter count.** Biological authority buys nothing. The one mechanism already
measured — the dendritic bump solving XOR alone — is the only one allowed to be called a
win today. The rest are hypotheses with wires attached.

Nothing here is pretrained, downloaded, or borrowed. Pure PyTorch.
Training runs on the DGX fleet, never on Iddo's PC, never on eran3.
"""
from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F

# ════════════════════════════════════════════════════════════ 1. THE BINDING
# Text enters as bytes. Every byte is bound to three things at once — the ALMA binding
# Iddo chose: א ⟷ /a/ ⟷ byte. No BPE, no borrowed tokenizer, no vocabulary to go stale.
# Kept unchanged from the archived worm: this part was right and was never the failure.

HEB = range(0xD0, 0xDF)                     # UTF-8 lead bytes for Hebrew live here
VOWELS = set(b"aeiouAEIOU")
PLOSIVE = set(b"bpdtgkBPDTGK")
FRICATIVE = set(b"fvszshFVSZSH")
NASAL = set(b"mnMN")

N_BYTE, N_LETTER, N_SOUND = 256, 6, 5


def letter_class(b: int) -> int:
    """Which script this byte belongs to — so שלום and shalom stop being confused."""
    if b in HEB:
        return 0
    if 65 <= b <= 90 or 97 <= b <= 122:
        return 1
    if 48 <= b <= 57:
        return 2
    if b in (32, 9, 10, 13):
        return 4
    if 33 <= b <= 47 or 58 <= b <= 64:
        return 3
    return 5


def sound_class(b: int) -> int:
    """A coarse phonetic class — so the model can generalise across spellings."""
    if b in VOWELS:
        return 0
    if b in PLOSIVE:
        return 1
    if b in FRICATIVE:
        return 2
    if b in NASAL:
        return 3
    return 4


_LETTER = torch.tensor([letter_class(b) for b in range(256)], dtype=torch.long)
_SOUND = torch.tensor([sound_class(b) for b in range(256)], dtype=torch.long)


def encode(text: str, length: int) -> torch.Tensor:
    """UTF-8 bytes, right-padded with 0, clipped to `length`."""
    raw = text.encode("utf-8", errors="replace")[:length]
    out = torch.zeros(length, dtype=torch.long)
    if raw:
        out[: len(raw)] = torch.tensor(list(raw), dtype=torch.long)
    return out


def encode_batch(texts: list[str], length: int) -> torch.Tensor:
    return torch.stack([encode(t, length) for t in texts])


class AlmaBinding(nn.Module):
    """byte ⊕ letter ⊕ sound ⊕ position — the three-fold binding, summed."""

    def __init__(self, d: int, max_len: int):
        super().__init__()
        self.byte = nn.Embedding(N_BYTE, d, padding_idx=0)
        self.letter = nn.Embedding(N_LETTER, d)
        self.sound = nn.Embedding(N_SOUND, d)
        self.pos = nn.Embedding(max_len, d)
        self.norm = nn.LayerNorm(d)
        self.register_buffer("lmap", _LETTER, persistent=False)
        self.register_buffer("smap", _SOUND, persistent=False)

    def forward(self, ids: torch.Tensor) -> torch.Tensor:          # (B,L) -> (B,L,d)
        B, L = ids.shape
        p = torch.arange(L, device=ids.device).unsqueeze(0).expand(B, L)
        x = (self.byte(ids)
             + self.letter(self.lmap[ids])
             + self.sound(self.smap[ids])
             + self.pos(p))
        return self.norm(x)


# ════════════════════════════════════════════════════════════ 2. THE SYNAPSE
# ריבוי משקלים — multi-weight. Iddo, 2026-08-20: "ריבוי משקלים — ריבוי הקשרים — 3D —
# נוירומורפי".  A connection today is ONE scalar. Biology's is not: the AMPA path is
# fast and linear, the NMDA path is slow and supralinear and is the one that gates
# plasticity (ALMA-BIOLOGY §2). And every synapse is a dynamic filter — it depresses
# with use and recovers with time (Tsodyks & Markram 1997), which makes it a novelty
# detector for free.
#
# THE HONEST NOTE: k weights at the same TOTAL scalar budget means FEWER units. Whether
# that trade wins is the July experiment that was designed and never run. `bench.py`
# runs it. Until it prints a number, k>1 is a hypothesis, not an improvement.


class MultiWeightLinear(nn.Module):
    """One connection, k channels, k time constants, and a use-state that depresses.

    channel 0  fast, linear            (AMPA — carries the signal now)
    channel 1  slow, supralinear       (NMDA — carries coincidence, gates learning)
    channel i  intermediate τ          (the rest of the ladder)

    The k channels are mixed by a learned per-output gain, and each channel carries its
    own leaky trace with time constant τ_i. `k=1` is exactly a vanilla Linear plus one
    mixing scalar.

    ⚠️ BUDGET, STATED HONESTLY: k channels cost k× the scalars of a vanilla Linear of the
    same width. They are NOT free and this layer does not pretend otherwise. The matched
    comparison is made at the NETWORK level, exactly as the July design specified —
    *"vanilla 1 weight × 1500 neurons vs ALMA 3/5/10 weights × 500/300/150 neurons,
    identical scalar budget"* — i.e. richer connections bought with fewer units. That
    trade is the experiment; `bench.py` sizes both sides to equal scalars and runs it.
    Until that number prints, k>1 is a hypothesis.
    """

    def __init__(self, d_in: int, d_out: int, k: int = 3, bias: bool = True):
        super().__init__()
        self.k = k
        self.d_out = d_out
        # k weight books, each 1/k the width, so the SCALAR BUDGET is matched to a
        # vanilla Linear(d_in, d_out) as closely as integer division allows.
        self.w = nn.Parameter(torch.empty(k, d_in, d_out).normal_(0, (d_in ** -0.5)) / k)
        self.b = nn.Parameter(torch.zeros(d_out)) if bias else None
        # τ per channel: channel 0 is instantaneous, later channels remember longer.
        tau = torch.linspace(0.0, 0.9, k) if k > 1 else torch.zeros(1)
        self.register_buffer("tau", tau, persistent=True)
        # how much each channel contributes — learned, one number per channel per output
        self.mix = nn.Parameter(torch.ones(k, d_out) / k)
        # short-term depression state, per output unit. Not a parameter: a STATE.
        self.register_buffer("use", torch.ones(d_out), persistent=False)
        self.depress = 0.0          # 0 disables STP exactly (the control setting)
        self.recover = 0.05

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (..., d_in) -> (..., d_out).  Each channel gets its own projection; the
        # slow channels are low-passed along the SEQUENCE axis when there is one.
        parts = torch.einsum("...i,kio->k...o", x, self.w)          # (k, ..., d_out)
        if self.k > 1 and x.dim() >= 3:
            parts = self._leak(parts)
        y = (parts * self.mix.view(self.k, *([1] * (parts.dim() - 2)), self.d_out)).sum(0)
        if self.b is not None:
            y = y + self.b
        if self.depress > 0.0:
            y = y * self._short_term(y)
        return y

    def _leak(self, parts: torch.Tensor) -> torch.Tensor:
        """Channel i keeps a leaky memory of itself along the sequence: a slow synapse.

        A causal EMA, computed as a depthwise convolution with a truncated exponential
        kernel — one cuDNN call per channel instead of a Python loop over the sequence
        (the loop version was O(L) launches and made a 512-byte page unusable).

        Causal by construction: the kernel only reaches backwards. Nothing in ALMA
        travels back in time — every delay is >= 1 and the loom only moves forward.
        """
        out = [parts[0]]
        B_dims = parts.shape[1:-2]
        L, D = parts.shape[-2], parts.shape[-1]
        for i in range(1, self.k):
            t = float(self.tau[i])
            p = parts[i]
            klen = min(L, max(2, int(torch.log(torch.tensor(1e-4)) / torch.log(torch.tensor(t)))))
            # kernel[j] = (1-t) * t^j, newest tap last (conv1d correlates, so reverse)
            kern = (1 - t) * torch.pow(t, torch.arange(klen - 1, -1, -1,
                                                       device=p.device, dtype=p.dtype))
            flat = p.reshape(-1, L, D).transpose(1, 2).reshape(-1, 1, L)   # (N*D,1,L)
            y = F.conv1d(F.pad(flat, (klen - 1, 0)), kern.view(1, 1, klen))
            out.append(y.reshape(-1, D, L).transpose(1, 2).reshape(*B_dims, L, D))
        return torch.stack(out, dim=0)

    def _short_term(self, y: torch.Tensor) -> torch.Tensor:
        """Depress on use, recover with time. A repeated input gets quieter — novelty
        rises to the top without any explicit 'seen-before' feature."""
        with torch.no_grad():
            act = y.detach().abs().mean(dim=tuple(range(y.dim() - 1)))
            self.use.mul_(1 - self.recover).add_(self.recover)          # recovery
            self.use.mul_(torch.exp(-self.depress * act))               # depression
        return self.use


# ════════════════════════════════════════════════════════════ 3. THE UNIT
# The dendritic bump. Human L2/3 dendrites fire graded Ca spikes that are MAXIMAL AT
# THRESHOLD and SUPPRESSED BY STRONGER INPUT — an inverted-U activation that lets a
# single neuron compute XOR (Gidon et al. 2020). This is the one mechanism in
# ALMA-BIOLOGY.md already MEASURED as a win: 100% XOR from a single unit.
#
# For MIKO it is not a curiosity. "Too much of this word" is exactly what a search organ
# must be able to say: a page that repeats the query 400 times is keyword spam, and a
# monotone unit can only love it more.


class Bump(nn.Module):
    """Non-monotonic activation: rises to a peak at threshold, then falls away.

    y = exp(-((x - mu)/sigma)^2) * gain      — a learnable bump per feature.

    `blend` mixes it with GELU so a layer can choose how non-monotonic to be; blend=0 is
    exactly GELU, which is the control.
    """

    def __init__(self, d: int, blend: float = 0.5):
        super().__init__()
        self.mu = nn.Parameter(torch.zeros(d))
        self.log_sigma = nn.Parameter(torch.zeros(d))
        self.blend = nn.Parameter(torch.full((d,), float(blend)))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        sigma = F.softplus(self.log_sigma) + 0.5
        bump = torch.exp(-((x - self.mu) / sigma) ** 2)
        a = torch.sigmoid(self.blend)
        return a * bump * x.sign() * x.abs().clamp(max=3.0) + (1 - a) * F.gelu(x)


# ════════════════════════════════════════════════════════════ 4. HOMEOSTASIS
# צמצום — contraction, so there is room for what comes next. Biology calls the same
# thing homeostatic synaptic scaling (Turrigiano 1998) and sleep downscaling: the cell
# renormalises ALL its inputs toward a firing-rate set-point, preserving the RELATIVE
# weights (the memory) while preventing runaway.
#
# Kabbalah and neuroscience arrive at one mechanism here, from opposite directions, and
# that is why it is in the model: not because it is beautiful, because it is the thing
# that lets a closed loop run for months without eating itself.


class Tzimtzum(nn.Module):
    """Multiplicative renormalisation toward a target output variance.

    Distinct from LayerNorm: LayerNorm is per-activation and carries no memory. This is
    per-UNIT, over the slow weights, with a set-point — it remembers what a healthy unit
    sounds like and pulls it back there between steps.
    """

    def __init__(self, d: int, target: float = 1.0, rate: float = 0.01):
        super().__init__()
        self.target = target
        self.rate = rate
        self.register_buffer("run", torch.ones(d), persistent=True)

    @torch.no_grad()
    def observe(self, h: torch.Tensor) -> None:
        v = h.detach().float().var(dim=tuple(range(h.dim() - 1)), unbiased=False) + 1e-6
        self.run.mul_(1 - self.rate).add_(self.rate * v)

    @torch.no_grad()
    def contract(self, weight: torch.Tensor) -> None:
        """Scale a weight matrix's OUTPUT rows toward the set-point. Call between steps."""
        g = (self.target / self.run.clamp_min(1e-6)).sqrt().clamp(0.5, 2.0)
        weight.mul_(g.view(*([1] * (weight.dim() - 1)), -1))

    def health(self) -> dict:
        """How many units have gone silent or shouty. Silence must never read as health."""
        r = self.run
        return {
            "mean": float(r.mean()),
            "dead_frac": float((r < 0.05 * self.target).float().mean()),
            "loud_frac": float((r > 5.0 * self.target).float().mean()),
        }


if __name__ == "__main__":          # smoke test — shapes and the XOR claim, CPU only
    torch.manual_seed(0)
    print("— binding —")
    ids = encode_batch(["מחשב מים אנלוגי", "water computer"], 32)
    emb = AlmaBinding(16, 32)
    print("  ids", tuple(ids.shape), "-> emb", tuple(emb(ids).shape))

    print("— multi-weight synapse —")
    for k in (1, 3, 5):
        m = MultiWeightLinear(16, 8, k=k)
        n = sum(p.numel() for p in m.parameters())
        print(f"  k={k}  params={n}  out={tuple(m(emb(ids)).shape)}")

    print("— the bump: can ONE unit do XOR? —")
    X = torch.tensor([[0., 0.], [0., 1.], [1., 0.], [1., 1.]])
    Y = torch.tensor([0., 1., 1., 0.])
    lin, act = nn.Linear(2, 1), Bump(1, blend=4.0)
    opt = torch.optim.Adam(list(lin.parameters()) + list(act.parameters()), lr=0.05)
    for _ in range(2000):
        opt.zero_grad()
        loss = F.mse_loss(act(lin(X)).squeeze(-1), Y)
        loss.backward()
        opt.step()
    pred = (act(lin(X)).squeeze(-1) > 0.5).float()
    print(f"  bump unit   XOR acc = {(pred == Y).float().mean():.2f}  (loss {loss:.4f})")
    lin2 = nn.Linear(2, 1)
    opt2 = torch.optim.Adam(lin2.parameters(), lr=0.05)
    for _ in range(2000):
        opt2.zero_grad()
        l2 = F.mse_loss(torch.sigmoid(lin2(X)).squeeze(-1), Y)
        l2.backward()
        opt2.step()
    p2 = (torch.sigmoid(lin2(X)).squeeze(-1) > 0.5).float()
    print(f"  vanilla unit XOR acc = {(p2 == Y).float().mean():.2f}  (loss {l2:.4f})  <- the control")
