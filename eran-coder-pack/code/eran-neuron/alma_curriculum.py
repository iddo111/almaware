# -*- coding: utf-8 -*-
"""
ALMA ENGINE :: SCIENCE MODE — does ProtoEran need a CURRICULUM, or is raw IMMERSION fine?
Iddo's hypothesis: DON'T curriculum-train — do the OPPOSITE (throw everything in raw),
then DISTILL. Test it (Asprey). Toy proxy: a 2-layer MLP (vectorized mini-batch backprop)
on a noisy classification with an easy->hard difficulty gradient. Compare 3 orderings.
"""
import numpy as np


def make_data(n, D, w, rng, noise_hard=0.30):
    X = rng.standard_normal((n, D))
    margin = X @ w
    y = (margin > 0).astype(float)
    diff = 1.0 / (1.0 + np.abs(margin))              # ~1 hard (near boundary), ~0 easy
    flip = rng.random(n) < noise_hard * diff
    y[flip] = 1.0 - y[flip]
    return X, y, diff


def sigmoid(z): return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


def train_eval(Xtr, ytr, diff, Xte, yte, order, D, H, epochs, bs, seed):
    r = np.random.default_rng(seed)
    W1 = r.standard_normal((D, H)) * 0.1; b1 = np.zeros(H)
    W2 = r.standard_normal((H, 1)) * 0.1; b2 = np.zeros((1,))
    lr = 0.1; n = len(Xtr)
    order_idx = np.argsort(diff)                     # easy -> hard
    early = None
    for ep in range(epochs):
        if order == "curriculum":   idx = order_idx
        elif order == "anti":       idx = order_idx[::-1]
        else:                       idx = r.permutation(n)
        for b in range(0, n, bs):
            bi = idx[b:b + bs]
            Xb = Xtr[bi]; yb = ytr[bi][:, None]; B = len(bi)
            Hh = np.tanh(Xb @ W1 + b1)
            O = sigmoid(Hh @ W2 + b2)
            dO = (O - yb) / B
            dW2 = Hh.T @ dO; db2 = dO.sum(0)
            dH = (dO @ W2.T) * (1 - Hh ** 2)
            dW1 = Xb.T @ dH; db1 = dH.sum(0)
            W1 -= lr * dW1; b1 -= lr * db1; W2 -= lr * dW2; b2 -= lr * db2
        if ep == 0:
            early = acc(Xte, yte, W1, b1, W2, b2)
    return acc(Xte, yte, W1, b1, W2, b2), early


def acc(X, y, W1, b1, W2, b2):
    O = sigmoid(np.tanh(X @ W1 + b1) @ W2 + b2)[:, 0]
    return float(np.mean((O > 0.5) == (y > 0.5)))


def run():
    D, H, N, epochs, bs, seeds = 20, 32, 2000, 15, 64, 5
    print("=== ALMA SCIENCE MODE :: curriculum vs immersion vs anti-curriculum ===")
    print(f"    2-layer MLP D={D} H={H}, N={N}, {epochs} epochs, avg of {seeds} seeds\n")
    print(f"  {'ordering':>14} {'FINAL (clean test)':>19} {'EARLY (1 epoch)':>17}")
    for order in ["curriculum", "immersion", "anti"]:
        fs, es = [], []
        for s in range(seeds):
            rng = np.random.default_rng(100 + s)
            w = rng.standard_normal(D)
            Xtr, ytr, diff = make_data(N, D, w, rng)
            Xte, yte, _ = make_data(1000, D, w, rng, noise_hard=0.0)
            f, e = train_eval(Xtr, ytr, diff, Xte, yte, order, D, H, epochs, bs, s)
            fs.append(f); es.append(e)
        print(f"  {order:>14} {np.mean(fs):16.1%} {np.mean(es):16.1%}")
    print("\n  final = clean held-out accuracy; early = after 1 epoch")


if __name__ == "__main__":
    run()
    print("\nHonest read: if the three FINALs are ~equal, ORDER barely matters ->")
    print("'immerse raw, no curriculum, then distill' is sound. Distillation (a clean student")
    print("trained on the messy model) is the standard quality step AFTER immersion.")
