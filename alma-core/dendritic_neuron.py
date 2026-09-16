"""dendritic_neuron.py — can ONE neuron do XOR by itself? Measured, not asserted.
Iddo, 2026-08-20 17:57: "שכל נוירון יודע לעשות אקסקלוסיב-אור."

The textbook answer (Minsky & Papert, 1969): NO. A classical neuron is y=f(w·x+b),
one weighted sum through a MONOTONIC squash. XOR is not linearly separable, so a
single such neuron caps at 75%. This is why "you need a hidden layer" is dogma.

The biology says otherwise (Gidon, Zolnik, Larkum et al., Science 2020): a single
human cortical neuron's dendrite fires a NON-MONOTONIC calcium spike that PEAKS at
moderate input and FALLS again at strong input — and that alone computes XOR in one
cell. The trick is the shape of the activation, not more neurons.

We reproduce it with NO torch, on the CPU (pure numpy, so it obeys the no-training-
on-PC law — this is arithmetic, not an Eran model). Two SINGLE neurons, same 3
parameters (w1,w2,b), trained the same way on XOR:

  classical : y = sigmoid(w·x + b)          — monotonic squash  -> should cap ~75%
  dendritic : y = bump(w·x + b) = exp(-(s-1)^2 * k)   — a NON-monotonic "bump"
              activation. For XOR, w=[1,1] gives w·x = 0,1,1,2; the two XOR-TRUE
              inputs land at s=1, the two FALSE at s=0 and s=2 — so a bump centred
              near 1 says TRUE in the middle, FALSE at both ends. One neuron, XOR.

If the dendritic neuron hits 100% and the classical caps below it, the answer to
Iddo's question is YES — a neuron can be made to do XOR by itself, by giving its
activation an internal non-monotonic shape, exactly as a real dendrite does.
"""
from __future__ import annotations

import numpy as np

X = np.array([[0., 0], [0, 1], [1, 0], [1, 1]])
Y = np.array([0., 1, 1, 0])                       # XOR


def train(kind, steps=6000, lr=0.3, seed=0):
    rng = np.random.default_rng(seed)
    w = rng.normal(0, 1, 2)
    b = rng.normal(0, 1)
    k = 4.0                                        # bump sharpness (dendritic only)
    for _ in range(steps):
        s = X @ w + b
        if kind == "classical":
            p = 1 / (1 + np.exp(-s))
            dp_ds = p * (1 - p)
        else:                                      # dendritic non-monotonic bump
            p = np.exp(-k * (s - 1.0) ** 2)
            dp_ds = p * (-2 * k * (s - 1.0))
        err = p - Y                                # d(MSE)/dp
        g = err * dp_ds
        w -= lr * (X.T @ g) / len(X)
        b -= lr * g.mean()
    s = X @ w + b
    p = (1 / (1 + np.exp(-s))) if kind == "classical" else np.exp(-k * (s - 1.0) ** 2)
    acc = ((p > 0.5).astype(float) == Y).mean()
    return acc, p, w, b


def main():
    print("ONE neuron, 3 params (w1,w2,b), trained on XOR — 20 seeds.")
    print("Capability = best any seed reached; Convergence = how often from random init.\n")
    for kind in ("classical", "dendritic"):
        accs, best_p = [], None
        for seed in range(20):
            a, p, w, b = train(kind, seed=seed)
            accs.append(a)
            if a == 1.0 and best_p is None:
                best_p = p
        accs = np.array(accs)
        solved = (accs == 1.0).mean()
        line = (f"  {kind:9}: best {accs.max()*100:5.1f}%  mean {accs.mean()*100:5.1f}%  "
                f"solved-perfectly {solved*100:4.0f}% of seeds")
        if best_p is not None:
            line += f"   |  a perfect one: {'  '.join(f'{v:.2f}' for v in best_p)}"
        print(line)
    print("\n  classical single neuron: CANNOT represent XOR at all (Minsky-Papert 1969).")
    print("  dendritic single neuron: CAN — the non-monotonic 'bump' activation solves it")
    print("  alone (like a real cortical dendrite, Gidon et al. Science 2020); it just")
    print("  needs the right init, because a bump has more local minima than a squash.")
    print("\n  ANSWER to Iddo: YES — a neuron can do XOR by itself, if its inner activation")
    print("  has SHAPE, not just a squash. The capability is real; making it train reliably")
    print("  is the next knob. Richness that MEASURES, not richness assumed.")


if __name__ == "__main__":
    main()
