# -*- coding: utf-8 -*-
"""verify_lif.py — prove the numpy LIF is snnTorch, not a story about snnTorch.

> BROKEN WINDOWS LAW: test the REAL output, never a proxy.

Runs the same random input through
  (a) our numpy LIFNet, and
  (b) an snnTorch net built from snn.Leaky / snn.RLeaky with the SAME weights,
and reports the max absolute difference in the output membrane trace. If that
is not ~1e-12 the arena is measuring something other than a spiking network and
must not be run.
"""
import numpy as np
import torch
import torch.nn as nn
import snntorch as snn

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lif import LIFNet


def build_torch(n_in, n_h, n_out, beta, thr, recurrent, W1, b1, V, W2, b2):
    fc1 = nn.Linear(n_in, n_h)
    fc2 = nn.Linear(n_h, n_out)
    with torch.no_grad():
        fc1.weight.copy_(torch.tensor(W1.T))
        fc1.bias.copy_(torch.tensor(b1))
        fc2.weight.copy_(torch.tensor(W2.T))
        fc2.bias.copy_(torch.tensor(b2))
    if recurrent:
        lif1 = snn.RLeaky(beta=beta, threshold=thr, linear_features=n_h,
                          all_to_all=True, learn_recurrent=False)
        with torch.no_grad():
            lif1.recurrent.weight.copy_(torch.tensor(V.T))
            if lif1.recurrent.bias is not None:
                lif1.recurrent.bias.zero_()
    else:
        lif1 = snn.Leaky(beta=beta, threshold=thr)
    lif2 = snn.Leaky(beta=beta, threshold=thr)
    return fc1, lif1, fc2, lif2


def run(recurrent):
    rng = np.random.default_rng(0)
    n_in, n_h, n_out, T = 7, 9, 3, 40
    beta, thr, gain = 0.9, 1.0, 3.0

    net = LIFNet(n_in, n_h, n_out, recurrent=recurrent, beta=beta,
                 threshold=thr, in_gain=gain)
    theta = rng.normal(0, 0.5, net.n_params())
    net.set_params(theta)
    V = net.V if recurrent else None

    fc1, lif1, fc2, lif2 = build_torch(n_in, n_h, n_out, beta, thr, recurrent,
                                       net.W1, net.b1, V, net.W2, net.b2)
    X = rng.normal(0, 1.0, (T, n_in))

    ours = np.stack([net.forward(X[t]) for t in range(T)])

    torch.set_default_dtype(torch.float64)
    if recurrent:
        spk1, mem1 = lif1.init_rleaky()
    else:
        mem1 = lif1.init_leaky()
    mem2 = lif2.init_leaky()
    theirs = []
    for t in range(T):
        cur1 = fc1(torch.tensor(gain * X[t]))
        if recurrent:
            spk1, mem1 = lif1(cur1, spk1.double(), mem1.double())
        else:
            spk1, mem1 = lif1(cur1, mem1.double())
        cur2 = fc2(spk1.double())
        _, mem2 = lif2(cur2, mem2.double())
        theirs.append(mem2.detach().numpy().copy())
    theirs = np.stack(theirs)

    d = float(np.max(np.abs(ours - theirs)))
    tag = "RECURRENT (snn.RLeaky)" if recurrent else "FEEDFORWARD (snn.Leaky)"
    ok = d < 1e-9
    print(f"{tag:<26} max|numpy - snnTorch| = {d:.3e}   "
          f"{'MATCH' if ok else 'MISMATCH'}")
    return ok, d


if __name__ == "__main__":
    torch.set_default_dtype(torch.float64)
    a, da = run(False)
    b, db = run(True)
    print("\nVERDICT:", "numpy LIF == snnTorch LIF" if (a and b)
          else "NOT EQUIVALENT — do not run the arena")
    import json
    print(json.dumps({"feedforward_maxdiff": da, "recurrent_maxdiff": db,
                      "equivalent": bool(a and b)}))
    sys.exit(0 if (a and b) else 1)
