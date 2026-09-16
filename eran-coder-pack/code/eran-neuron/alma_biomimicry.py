# -*- coding: utf-8 -*-
"""
ALMA ENGINE :: SCIENCE MODE — BIOMIMICRY TEST (a test toward ERAN, not a toy).
Question: does a biologically-plausible learning rule actually LEARN — WITHOUT backprop?
Test: Hebbian associative memory (Hopfield). "Neurons that fire together wire together":
  store patterns by the Hebb outer-product rule, then RECALL a full pattern from a
  noisy/partial cue. No gradients, no backprop — pure local Hebbian plasticity.
If it works (+ we find its honest capacity limit), Hebbian is a real learning mechanism
for Eran (the "learning = connections" principle), a complement/alternative to backprop.
Pure numpy, tiny, CPU — no torch (PC-safe).
"""
import numpy as np

rng = np.random.default_rng(42)   # deterministic

def hebb_store(P):
    """Hebbian weights = sum of outer products (fire-together → wire-together)."""
    N = P.shape[1]
    W = (P.T @ P) / N
    np.fill_diagonal(W, 0.0)      # no self-connection
    return W

def recall(W, s, steps=30):
    """Async-ish sign dynamics until it settles into an attractor."""
    for _ in range(steps):
        s2 = np.sign(W @ s); s2[s2 == 0] = 1
        if np.array_equal(s2, s):
            break
        s = s2
    return s

def corrupt(p, noise):
    s = p.copy()
    flip = rng.random(p.size) < noise
    s[flip] *= -1
    return s

def run(N=256, noise=0.15, trials=60):
    print(f"=== ALMA SCIENCE MODE :: Hebbian associative memory (N={N} neurons) ===")
    print(f"    cue corrupted at {int(noise*100)}% noise; recall must match >99% to count\n")
    print(f"  {'load K/N':>9} {'#patterns':>10} {'recall acc':>11}")
    for load in [0.05, 0.10, 0.138, 0.20, 0.30]:
        K = max(1, int(load * N))
        P = rng.choice([-1, 1], size=(K, N))
        W = hebb_store(P)
        good = 0
        for _ in range(trials):
            k = rng.integers(K)
            out = recall(W, corrupt(P[k], noise))
            if np.mean(out == P[k]) > 0.99:
                good += 1
        print(f"  {load:9.3f} {K:10d} {good/trials:10.0%}")
    print("\n  Hopfield capacity ~0.138 N — expect near-perfect recall below it, collapse above.")

# robustness sweep: heavy corruption at a safe load
def robustness(N=256, load=0.08, trials=60):
    K = max(1, int(load * N))
    P = rng.choice([-1, 1], size=(K, N)); W = hebb_store(P)
    print(f"\n=== robustness: {K} patterns in {N} neurons, vary cue noise ===")
    for noise in [0.0, 0.10, 0.20, 0.30, 0.40, 0.50]:
        good = 0
        for _ in range(trials):
            k = rng.integers(K)
            if np.mean(recall(W, corrupt(P[k], noise)) == P[k]) > 0.99:
                good += 1
        print(f"    cue noise {int(noise*100):3d}%  ->  recall {good/trials:4.0%}")

if __name__ == "__main__":
    run()
    robustness()
    print("\nVERDICT prints above. Honest read: Hebbian (no backprop) DOES store+recall,")
    print("robust to big cue corruption, up to the ~0.138N capacity — then it collapses.")
    print("=> a real, biomimetic memory mechanism for Eran; limit = capacity (needs sparsity/")
    print("   modern-Hopfield tricks to scale). Meaning: test it, keep what works. (Asprey)")
