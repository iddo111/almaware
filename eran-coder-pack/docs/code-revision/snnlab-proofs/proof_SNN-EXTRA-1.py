"""proof_SNN-EXTRA-1 — an accuracy above 100% is not an accuracy.

Found while proving SNN-3, not in the original trace. evaluate() capped the
SAMPLE COUNT with `limit` but not the SLICE: `for s in range(0, n, batch)` then
`X[s:s + batch]` reads a full batch past the limit and the hits are divided by
n. With --eval-train-n 2000 and batch 256 that counts 2048 items against a
denominator of 2000, so every MNIST run in results/ reports a train accuracy up
to 2.4% too high. Measured here: 4.0, i.e. "400%".

Harmless on syllables only because 396 < 2000 makes n == len(X).

  FAILS on train.py.bak-rev-20260906   PASSES on the fixed train.py
"""
import argparse
import os
import sys

import numpy as np
import torch

from _proofcommon import HERE, load, tiny_cfg, fake_percepts, verdict


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.path.join(HERE, "train.py"))
    a = ap.parse_args()
    T = load(a.src, "train_under_test")

    # A deterministic 100%-correct answer, with no training at all: a silent
    # network emits no output spikes, argmax of all-zeros is class 0, and every
    # label here IS class 0. So the true accuracy is exactly 1.0 and anything
    # above that is the arithmetic being wrong, not the network being good.
    x, _ = fake_percepts(440, seed=1)
    y = np.zeros(len(x), dtype=np.int64)
    cfg = tiny_cfg(threshold=50.0, input_gain=0.0)
    net = T.build_net(cfg, 24, 22) if hasattr(T, "build_net") else T.SpikingNet(
        24, cfg["hidden"], 22, cfg["beta"], cfg["threshold"],
        T.SURROGATES[cfg["surrogate"]]())
    dev = torch.device("cpu")
    net.to(dev)

    acc_limited = T.evaluate(net, x, y, cfg, dev, batch=256, limit=64)
    acc_full = T.evaluate(net, x, y, cfg, dev, batch=256)
    print(f"evaluate(limit=64,  batch=256) on 440 samples -> {acc_limited}")
    print(f"evaluate(no limit,  batch=256) on 440 samples -> {acc_full:.4f}")

    print(f"(the true accuracy of this network on this data is exactly 1.0)")
    ok = (abs(acc_limited - 1.0) < 1e-12 and abs(acc_full - 1.0) < 1e-12)
    return verdict(ok, "an accuracy must lie in [0, 1] and count what it divides by")


if __name__ == "__main__":
    sys.exit(main())
