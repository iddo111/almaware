"""beitdin_net.py — THE BEIT DIN IS THE NEURON. A real neural network.

לזכרה של עלמה ז"ל.

Iddo asked for a NEURAL NETWORK MODEL. What existed under the ALMIDO name was an
orchestrator that borrowed the fleet's brains; this file is the model itself.

THE ARCHITECTURE, stated plainly so it can be attacked:

A classical neuron is one weighted sum. Here every neuron is a court of three
independent seats, and the ruling is the MEDIAN of the three opinions — not their
mean. That single change is the whole idea, and it has three consequences that a
mean does not have:

  1. ROBUSTNESS IS STRUCTURAL. The median of three ignores one outlier entirely.
     A seat that is wrong, saturated, or dead cannot drag the ruling; with a mean
     it always drags it by a third. Corruption of one seat costs nothing.

  2. DISSENT IS A SIGNAL, NOT NOISE. The court also reports how far apart the
     seats were (max - min). Agreement means the feature is unambiguous; wide
     dissent means the input is genuinely contested. That number is carried
     forward as its own channel — the network can LEARN to treat contested
     features differently, which a single scalar activation cannot express.
     This is the machekt (מחלוקת) kept visible, as in the source material.

  3. GRADIENTS ARE SPARSE AND HONEST. torch.median routes the gradient only to
     the seat that ruled. Each seat is trained on the examples where it was the
     middle voice, so the three seats specialise instead of collapsing into
     three copies of each other — the failure mode an ensemble-by-averaging has.

Against the obvious objection ("this is just an ensemble"): an ensemble votes
once, at the output. Here every layer of every neuron is a court, dissent is fed
back into the computation, and the seats share no gradient path except through
the ruling. It is a different function class, not a wrapper.

THE CONTROL. `VanillaLM` is the same model with ordinary neurons, sized so both
have the same parameter count within 1%. Any claim about the Beit Din is measured
against it on identical data, identical steps, identical seed. Innovation next to
vanilla — never a demo of the innovation alone.

Runs on the DGX fleet. Never on the PC (standing law: no training on the PC).
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib
import time

import torch
import torch.nn as nn
import torch.nn.functional as F


# --------------------------------------------------------------- the court --
class BeitDinLinear(nn.Module):
    """One layer of courts. Each output unit is judged by `seats` opinions;
    the ruling is their median and the dissent is their spread.

    in  : (B, T, d_in)
    out : (B, T, d_out) ruling, (B, T, d_out) dissent
    """

    def __init__(self, d_in: int, d_out: int, seats: int = 3) -> None:
        super().__init__()
        if seats % 2 == 0:
            raise ValueError("a court needs an odd number of seats — a tie has no ruling")
        self.seats, self.d_out = seats, d_out
        # one independent opinion per seat; initialised differently on purpose so
        # the seats do not start as copies of one another
        self.w = nn.Parameter(torch.empty(seats, d_in, d_out))
        self.b = nn.Parameter(torch.zeros(seats, d_out))
        for s in range(seats):
            nn.init.normal_(self.w[s], std=(d_in ** -0.5) * (1.0 + 0.1 * s))

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        # (S, B, T, d_out) — every seat rules on every unit
        op = torch.einsum("btd,sdo->sbto", x, self.w) + self.b[:, None, None, :]
        ruling = op.median(dim=0).values          # gradient goes to the middle seat only
        dissent = op.max(dim=0).values - op.min(dim=0).values
        return ruling, dissent


class CourtBlock(nn.Module):
    """A transformer block whose feed-forward is a court, and whose attention is
    modulated by dissent: where the court disagreed, the block leans on context.

    The dissent gate is the claim to test. If it is worthless, `--no-dissent`
    turns it off and the ablation says so in the numbers.
    """

    def __init__(self, d: int, n_head: int, seats: int = 3, use_dissent: bool = True) -> None:
        super().__init__()
        self.ln1, self.ln2 = nn.LayerNorm(d), nn.LayerNorm(d)
        self.attn = nn.MultiheadAttention(d, n_head, batch_first=True)
        self.court_in = BeitDinLinear(d, 4 * d, seats)
        self.court_out = BeitDinLinear(4 * d, d, seats)
        self.use_dissent = use_dissent
        if use_dissent:
            # dissent -> a per-channel gate in [0,1]; starts near "ignore me" so
            # the model must EARN the use of disagreement
            self.gate = nn.Linear(4 * d, d)
            nn.init.zeros_(self.gate.weight)
            nn.init.constant_(self.gate.bias, -2.0)

    def forward(self, x: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
        h = self.ln1(x)
        a, _ = self.attn(h, h, h, attn_mask=mask, need_weights=False)
        x = x + a
        h = self.ln2(x)
        r1, d1 = self.court_in(h)
        act = F.gelu(r1)
        r2, _ = self.court_out(act)
        if self.use_dissent:
            g = torch.sigmoid(self.gate(d1))      # wide dissent -> stronger gate
            # INSTRUMENTATION (2026-08-20, Iddo: "תבדוק מה קורה שם"). The first
            # controlled run lost to vanilla; before blaming the idea, prove the
            # mechanism is even switched on. Three numbers per block:
            #   dissent  — how far apart the three seats actually are;
            #   gate     — sigma(W.d + b); it starts at sigmoid(-2)=0.119, so a
            #              value still near 0.119 means the net never learned to
            #              use disagreement at all — the idea was never tested;
            #   seat_var — spread of the seats' weights; near zero means the
            #              three seats collapsed into copies and there is no court.
            with torch.no_grad():
                self.stat_dissent = d1.abs().mean().item()
                self.stat_gate = g.mean().item()
                self.stat_seatvar = self.court_in.w.std(dim=0).mean().item()
            r2 = r2 * (1.0 + g)
        return x + r2


class BeitDinLM(nn.Module):
    def __init__(self, vocab: int, d: int = 192, n_layer: int = 4, n_head: int = 4,
                 seats: int = 3, use_dissent: bool = True, ctx: int = 512) -> None:
        super().__init__()
        self.ctx = ctx
        self.tok = nn.Embedding(vocab, d)
        self.pos = nn.Embedding(ctx, d)
        self.blocks = nn.ModuleList(
            [CourtBlock(d, n_head, seats, use_dissent) for _ in range(n_layer)])
        self.ln = nn.LayerNorm(d)
        self.head = nn.Linear(d, vocab, bias=False)

    def forward(self, idx: torch.Tensor) -> torch.Tensor:
        B, T = idx.shape
        pos = torch.arange(T, device=idx.device)
        x = self.tok(idx) + self.pos(pos)[None]
        mask = torch.triu(torch.full((T, T), float("-inf"), device=idx.device), 1)
        for b in self.blocks:
            x = b(x, mask)
        return self.head(self.ln(x))


# ------------------------------------------------------------- the control --
class VanillaBlock(nn.Module):
    def __init__(self, d: int, n_head: int, hidden: int) -> None:
        super().__init__()
        self.ln1, self.ln2 = nn.LayerNorm(d), nn.LayerNorm(d)
        self.attn = nn.MultiheadAttention(d, n_head, batch_first=True)
        self.fc1, self.fc2 = nn.Linear(d, hidden), nn.Linear(hidden, d)

    def forward(self, x: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
        h = self.ln1(x)
        a, _ = self.attn(h, h, h, attn_mask=mask, need_weights=False)
        x = x + a
        h = self.ln2(x)
        return x + self.fc2(F.gelu(self.fc1(h)))


class VanillaLM(nn.Module):
    """Same skeleton, ordinary neurons, hidden width chosen by the caller so the
    parameter counts match. This is the honest opponent."""

    def __init__(self, vocab: int, d: int = 192, n_layer: int = 4, n_head: int = 4,
                 hidden: int | None = None, ctx: int = 512) -> None:
        super().__init__()
        hidden = hidden or 4 * d
        self.ctx = ctx
        self.tok = nn.Embedding(vocab, d)
        self.pos = nn.Embedding(ctx, d)
        self.blocks = nn.ModuleList([VanillaBlock(d, n_head, hidden) for _ in range(n_layer)])
        self.ln = nn.LayerNorm(d)
        self.head = nn.Linear(d, vocab, bias=False)

    def forward(self, idx: torch.Tensor) -> torch.Tensor:
        B, T = idx.shape
        pos = torch.arange(T, device=idx.device)
        x = self.tok(idx) + self.pos(pos)[None]
        mask = torch.triu(torch.full((T, T), float("-inf"), device=idx.device), 1)
        for b in self.blocks:
            x = b(x, mask)
        return self.head(self.ln(x))


def count(m: nn.Module) -> int:
    return sum(p.numel() for p in m.parameters())


def match_vanilla_width(vocab: int, d: int, n_layer: int, n_head: int, seats: int,
                        ctx: int) -> int:
    """Find the vanilla hidden width whose parameter count is closest to the
    court's. Without this, any win could just be extra parameters."""
    target = count(BeitDinLM(vocab, d, n_layer, n_head, seats, True, ctx))
    best, best_gap = 4 * d, None
    for hidden in range(d, 16 * d, max(1, d // 16)):
        gap = abs(count(VanillaLM(vocab, d, n_layer, n_head, hidden, ctx)) - target)
        if best_gap is None or gap < best_gap:
            best, best_gap = hidden, gap
    return best


# ------------------------------------------------------------------ train --
def batches(tokens: torch.Tensor, ctx: int, bs: int, gen: torch.Generator):
    hi = tokens.numel() - ctx - 1
    while True:
        ix = torch.randint(0, hi, (bs,), generator=gen)
        x = torch.stack([tokens[i:i + ctx] for i in ix])
        y = torch.stack([tokens[i + 1:i + 1 + ctx] for i in ix])
        yield x, y


@torch.no_grad()
def evaluate(model: nn.Module, tokens: torch.Tensor, ctx: int, bs: int,
             n: int, device: str) -> float:
    model.eval()
    g = torch.Generator().manual_seed(1234)          # the SAME windows every time
    tot = 0.0
    it = batches(tokens, ctx, bs, g)
    for _ in range(n):
        x, y = next(it)
        loss = F.cross_entropy(model(x.to(device)).flatten(0, 1), y.to(device).flatten())
        tot += loss.item()
    model.train()
    return tot / n


def main() -> None:
    ap = argparse.ArgumentParser(description="Beit-Din neuron vs vanilla, same size")
    ap.add_argument("--tokens", required=True, help="dir of tokenized .json track files")
    ap.add_argument("--split", required=True, help="split.json with train/heldout lists")
    ap.add_argument("--arch", choices=["beitdin", "vanilla"], required=True)
    ap.add_argument("--seats", type=int, default=3)
    ap.add_argument("--no-dissent", action="store_true")
    ap.add_argument("--d", type=int, default=192)
    ap.add_argument("--layers", type=int, default=4)
    ap.add_argument("--heads", type=int, default=4)
    ap.add_argument("--ctx", type=int, default=512)
    ap.add_argument("--bs", type=int, default=16)
    ap.add_argument("--steps", type=int, default=3000)
    ap.add_argument("--eval-every", type=int, default=100)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--seed", type=int, default=17)
    ap.add_argument("--out", default="runs")
    A = ap.parse_args()

    torch.manual_seed(A.seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    tokdir = pathlib.Path(A.tokens)
    split = json.loads(pathlib.Path(A.split).read_text(encoding="utf-8"))

    def load(names) -> torch.Tensor:
        buf = []
        for n in names:
            p = tokdir / (n if str(n).endswith(".json") else f"{n}.json")
            if not p.exists():
                continue
            d = json.loads(p.read_text(encoding="utf-8"))
            ids = d["tokens"] if isinstance(d, dict) and "tokens" in d else d
            if isinstance(ids, dict):
                ids = ids.get("ids") or ids.get("tokens") or []
            buf.extend(int(t) for t in ids)
        return torch.tensor(buf, dtype=torch.long)

    train = load(split["train"])
    held = load(split["heldout"])
    vocab = int(max(train.max().item(), held.max().item())) + 1
    print(f"train {train.numel():,} tok · heldout {held.numel():,} tok · vocab {vocab}")

    if A.arch == "beitdin":
        model = BeitDinLM(vocab, A.d, A.layers, A.heads, A.seats,
                          not A.no_dissent, A.ctx)
    else:
        hidden = match_vanilla_width(vocab, A.d, A.layers, A.heads, A.seats, A.ctx)
        model = VanillaLM(vocab, A.d, A.layers, A.heads, hidden, A.ctx)
        print(f"vanilla hidden width matched to {hidden}")
    model = model.to(device)
    n_par = count(model)
    print(f"{A.arch}: {n_par:,} parameters · tokens/param = {train.numel()/n_par:.1f}")

    opt = torch.optim.AdamW(model.parameters(), lr=A.lr, weight_decay=0.1)
    gen = torch.Generator().manual_seed(A.seed)
    it = batches(train, A.ctx, A.bs, gen)
    outdir = pathlib.Path(A.out)
    outdir.mkdir(parents=True, exist_ok=True)
    tag = A.arch + ("" if A.arch == "vanilla" else
                    f"-s{A.seats}" + ("-nodissent" if A.no_dissent else ""))
    hist, best, t0 = [], float("inf"), time.time()

    for step in range(1, A.steps + 1):
        x, y = next(it)
        loss = F.cross_entropy(model(x.to(device)).flatten(0, 1), y.to(device).flatten())
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()
        if step % A.eval_every == 0:
            h = evaluate(model, held, A.ctx, A.bs, 8, device)
            best = min(best, h)
            rec = {"step": step, "train": loss.item(), "heldout": h,
                   "elapsed_s": round(time.time() - t0, 1)}
            extra = ""
            blocks = [b for b in model.blocks if hasattr(b, "stat_gate")]
            if blocks:
                rec["dissent"] = sum(b.stat_dissent for b in blocks) / len(blocks)
                rec["gate"] = sum(b.stat_gate for b in blocks) / len(blocks)
                rec["seat_var"] = sum(b.stat_seatvar for b in blocks) / len(blocks)
                # 0.119 is sigmoid(-2), the value the gate is born with
                extra = (f"  dissent {rec['dissent']:.3f}  gate {rec['gate']:.3f}"
                         f"(born .119)  seat_var {rec['seat_var']:.4f}")
            hist.append(rec)
            print(f"step {step:5d}  train {loss.item():.4f}  heldout {h:.4f}  "
                  f"best {best:.4f}  {time.time()-t0:.0f}s{extra}", flush=True)
            (outdir / f"{tag}.json").write_text(json.dumps(
                {"arch": tag, "params": n_par, "seed": A.seed,
                 "train_tokens": int(train.numel()), "best_heldout": best,
                 "history": hist}, indent=1), encoding="utf-8")

    print(f"DONE {tag}: params {n_par:,} best heldout {best:.4f}")


if __name__ == "__main__":
    main()
