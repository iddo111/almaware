# -*- coding: utf-8 -*-
"""miko_mouth_dims.py — the decisive question: does the learner ever earn its keep?

Two runs have now said the same thing: a random-mutation hill climber beats
MIKO's ThreeFactor on a 5-station mouth. That is a real finding, and it makes the
FIRST hardware much cheaper — a servo, a mic and accept-if-better is enough to
find a posture.

But five stations is a small mouth. A real Hebrew mouth is tongue back + tongue
tip + lateral + groove + lips + velum + folds + pharynx — twenty-odd degrees of
freedom. Random search degrades sharply with dimension; a learned
proprioception→motor map should not. THAT is where a learner earns its keep, if
it ever does.

So: hold everything else fixed and sweep ONLY the number of stations.

    flat gap, or random still ahead at 20  ->  do not build the learner. Build a
                                               hill climber and spend the money
                                               on sensing for the plosives.
    gap closes or reverses as D grows      ->  the learner is what the big mouth
                                               needs, and proprioception is why.

    python miko_mouth_dims.py
"""
from __future__ import annotations

import sys
import numpy as np
import torch

sys.path.insert(0, r"D:\CLAUDE\miko\model")
sys.path.insert(0, r"D:\CLAUDE\alma-larynx")

from loop import ThreeFactor
from simulate_voicebox import kl_filter

FS = 44100
N_SEC = 34
N_PROP = 12
TARGETS = 8
TRIALS = 60
THRESH = 0.10
SEEDS = 5
DIMS = [5, 10, 20]


def areas_from_motor(m):
    x = np.arange(N_SEC)
    A = np.full(N_SEC, 4.0)
    centres = np.linspace(3, N_SEC - 4, len(m))
    for depth, c in zip(m, centres):
        A *= 1.0 - 0.85 * float(np.clip(depth, 0, 1)) * np.exp(-((x - c) ** 2) / 8.0)
    return np.maximum(A, 0.06)


def formants(m):
    imp = np.zeros(512)
    imp[0] = 1.0
    y = kl_filter(imp, areas_from_motor(m))
    NFFT = 8192
    spec = np.abs(np.fft.rfft(y * np.hanning(len(y)), NFFT))
    freqs = np.fft.rfftfreq(NFFT, 1 / FS)
    sm = np.convolve(spec, np.ones(33) / 33, mode="same")
    band = (freqs > 200) & (freqs < 3200)
    f, s = freqs[band], sm[band]
    pk = [i for i in range(1, len(s) - 1) if s[i] > s[i - 1] and s[i] >= s[i + 1]]
    pk.sort(key=lambda i: -s[i])
    got = sorted(f[i] for i in pk[:2]) if len(pk) >= 2 else []
    while len(got) < 2:
        got.append(3200.0)
    return float(got[0]), float(got[1])


def err(m, target):
    f1, f2 = formants(m)
    return float(np.hypot(np.log(f1 / target[0]), np.log(f2 / target[1])))


def proprio(m, rng):
    A = areas_from_motor(m)
    sites = np.linspace(0, N_SEC - 1, N_PROP).astype(int)
    return (1.0 - A[sites] / 4.0) + rng.normal(0, 0.02, N_PROP)


class Net(torch.nn.Module):
    def __init__(self, D, hidden=24):
        super().__init__()
        self.W1 = torch.nn.Parameter(torch.randn(N_PROP, hidden) * 0.3)
        self.W2 = torch.nn.Parameter(torch.randn(hidden, D) * 0.3)

    def forward(self, p):
        h = torch.tanh(p @ self.W1)
        return torch.tanh(h @ self.W2), h


def run(arm, seed, D):
    rng = np.random.default_rng(seed)
    torch.manual_seed(seed)
    net = Net(D)
    tf = ThreeFactor(net, lr=6e-3, decay=0.85)
    params = {"W1": net.W1.data, "W2": net.W2.data}
    cost = []
    for _ in range(TARGETS):
        target = formants(rng.uniform(0.1, 0.9, D))
        m = rng.uniform(0.2, 0.8, D)
        base = err(m, target)
        used = TRIALS
        for t in range(TRIALS):
            if base <= THRESH:
                used = t
                break
            p = proprio(m, rng)
            pt = torch.tensor(p, dtype=torch.float32).unsqueeze(0)
            with torch.no_grad():
                delta, h = net(pt)
            step = (rng.normal(0, 0.12, D) if arm == "random"
                    else delta.numpy()[0] * 0.12)
            cand = np.clip(m + step + rng.normal(0, 0.03, D), 0, 1)
            e = err(cand, target)
            if arm == "miko":
                tf.observe(pt, h, "W1")
                tf.observe(h, delta, "W2")
                tf.apply(1.0 if e < base else -1.0, params)
            if e < base:
                m, base = cand, e
        cost.append(used)
    return float(np.mean(cost))


def main():
    print("DOES THE LEARNER EVER EARN ITS KEEP?  sweeping only the number of stations")
    print("=" * 78)
    print("%d seeds  ·  %d targets  ·  %d trials allowed  ·  everything else held fixed"
          % (SEEDS, TARGETS, TRIALS))
    print("-" * 78)
    print("%-8s %12s %12s %12s   %s" % ("stations", "miko", "random", "gap", "who wins"))
    for D in DIMS:
        mk = np.array([run("miko", s, D) for s in range(SEEDS)])
        rd = np.array([run("random", s, D) for s in range(SEEDS)])
        gap = mk.mean() - rd.mean()
        print("%-8d %12.1f %12.1f %+12.1f   %s"
              % (D, mk.mean(), rd.mean(), gap,
                 "random" if gap > 0 else "MIKO"), flush=True)
    print("=" * 78)
    print("trials-to-target, lower is better. TRIALS=%d means it never got there." % TRIALS)


if __name__ == "__main__":
    main()
