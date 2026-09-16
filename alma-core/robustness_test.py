"""robustness_test.py — the Beit-Din's ONE untested claim, finally measured.

All session long the court LOST as a neuron on accuracy (music 2.65 vs 2.56; Pong
last). But accuracy was never its argument. Its argument is ROBUSTNESS: the ruling
is a MEDIAN of three seats, so one corrupted seat cannot drag the verdict — while a
MEAN is dragged by exactly one third. That claim was never run. This runs it.

Setup, matched and fair:
  * one trained task (2-class, learnable), three aggregators over 3 seats:
      median  (the Beit Din),  mean  (the naive ensemble),  single (one seat, k=1).
  * train each cleanly, then CORRUPT ONE SEAT at inference three ways — zero it,
    invert it, saturate it to a large constant — and measure the accuracy DROP.
  * the claim is falsifiable: if the median's drop is not smaller than the mean's,
    the Beit-Din's robustness thesis fails and we say so.
No PC training (law). Runs on the fleet.
"""
from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F


class Seats(nn.Module):
    """`seats` independent opinions of shape (S,B,d_out). Aggregation is chosen at
    inference, and one seat can be corrupted in place."""
    def __init__(self, d_in, d_out, seats=3):
        super().__init__()
        self.w = nn.Parameter(torch.empty(seats, d_in, d_out))
        self.b = nn.Parameter(torch.zeros(seats, d_out))
        for s in range(seats):
            nn.init.normal_(self.w[s], std=(d_in ** -0.5) * (1 + 0.1 * s))
        self.seats = seats

    def opinions(self, x):
        return torch.einsum("bd,sdo->sbo", x, self.w) + self.b[:, None, :]

    def forward(self, x, agg="median", corrupt=None):
        op = self.opinions(x)                       # (S,B,d_out)
        if corrupt is not None:
            kind, seat = corrupt
            if kind == "zero":     op = op.clone(); op[seat] = 0.0
            elif kind == "invert": op = op.clone(); op[seat] = -op[seat]
            elif kind == "sat":    op = op.clone(); op[seat] = 50.0
        if agg == "median": return op.median(0).values
        if agg == "mean":   return op.mean(0)
        return op[0]                                # single seat


class Net(nn.Module):
    def __init__(self, d_in, d_hid, d_out, seats, agg):
        super().__init__()
        self.l1 = Seats(d_in, d_hid, seats)
        self.l2 = Seats(d_hid, d_out, seats)
        self.agg = agg

    def forward(self, x, corrupt=None):
        h = F.gelu(self.l1(x, self.agg, corrupt))
        return self.l2(h, self.agg, corrupt)


def make_data(n, dev, seed):
    g = torch.Generator(device=dev).manual_seed(seed)
    X = torch.randn(n, 8, generator=g, device=dev)
    # a nonlinear 2-class rule
    y = ((X[:, 0] * X[:, 1] + X[:, 2] - X[:, 3] ** 2) > 0).long()
    return X, y


def run(agg, seats, dev, seed):
    torch.manual_seed(seed)
    Xtr, ytr = make_data(4000, dev, seed)
    Xte, yte = make_data(2000, dev, seed + 1)
    net = Net(8, 32, 2, seats, agg).to(dev)
    opt = torch.optim.Adam(net.parameters(), lr=0.01)
    for _ in range(600):
        loss = F.cross_entropy(net(Xtr), ytr)
        opt.zero_grad(set_to_none=True); loss.backward(); opt.step()

    @torch.no_grad()
    def acc(corrupt=None):
        return (net(Xte, corrupt).argmax(-1) == yte).float().mean().item()

    clean = acc()
    drops = {}
    if agg != "single":
        for kind in ("zero", "invert", "sat"):
            worst = min(acc((kind, s)) for s in range(seats))   # adversary picks the worst seat
            drops[kind] = clean - worst
    else:
        for kind in ("zero", "invert", "sat"):
            drops[kind] = clean - acc((kind, 0))
    return clean, drops


def main():
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"{'aggregator':10} {'clean':>6}   drop when ONE seat is corrupted (worst-case)")
    print(f"{'':10} {'':>6}   {'zero':>7} {'invert':>7} {'sat':>7}")
    rows = {}
    for agg in ("median", "mean", "single"):
        cs, ds = [], {"zero": [], "invert": [], "sat": []}
        for seed in (1, 2, 3):
            c, d = run(agg, 3 if agg != "single" else 1, dev, seed)
            cs.append(c); [ds[k].append(v) for k, v in d.items()]
        clean = sum(cs) / 3
        dd = {k: sum(v) / 3 for k, v in ds.items()}
        rows[agg] = dd
        print(f"{agg:10} {clean*100:5.1f}%   {dd['zero']*100:6.1f}% {dd['invert']*100:6.1f}% {dd['sat']*100:6.1f}%")
    # verdict
    print()
    for kind in ("zero", "invert", "sat"):
        med, mean = rows["median"][kind], rows["mean"][kind]
        v = "MEDIAN more robust" if med < mean - 0.005 else \
            ("tie" if abs(med - mean) <= 0.005 else "mean more robust")
        print(f"  {kind:6}: median drop {med*100:.1f}% vs mean {mean*100:.1f}%  -> {v}")


if __name__ == "__main__":
    main()
