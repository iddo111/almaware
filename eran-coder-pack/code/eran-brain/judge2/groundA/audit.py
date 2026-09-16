#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""audit.py -- two checks Ground A owes before anyone trains on these features.

1. BURST DESCRIPTOR at 1 ms resolution (the 10 ms envelope in groundA.py is too
   coarse to describe a 2-15 ms release). For each clip: the largest rise in dB
   across any 10 ms window inside the first 100 ms after onset. Proves RAMP60
   really destroys the release and CUT60 really manufactures a sharper one.

2. DEGENERATE-DIM AUDIT of the 996-d vector over the 100 human ba takes:
   near-constant dims (the nn.LayerNorm(1) scar, from the other side), and the
   per-dim std range inside each block (scale traps for a learned judge).
"""
from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.expanduser("~/ear-v3"))
sys.path.insert(0, os.path.expanduser("~/judge2-groundA"))
from ear3 import features as F     # noqa: E402
from groundA import (CORPUS, OUT, FS, cut60, ramp60, onset_sample,  # noqa: E402
                     FINE, auc)

MS = 16          # 1 ms at 16 kHz


def env1ms(x):
    nf = x.size // MS
    if nf == 0:
        return np.zeros(0)
    return np.sqrt((x[:nf * MS].reshape(nf, MS) ** 2).mean(axis=1)) + 1e-9


def burst_db(x, win_ms=10, look_ms=100):
    """Largest dB rise over any `win_ms` window in the `look_ms` after onset."""
    e = env1ms(x)
    a = onset_sample(x) // MS
    lo = max(0, a - 10)
    hi = min(e.size - 1, a + look_ms)
    if hi - lo <= win_ms:
        return float("nan")
    seg = e[lo:hi]
    r = 20.0 * np.log10(seg[win_ms:] / seg[:-win_ms])
    return float(r.max())


def main():
    print("=" * 78)
    print("1. BURST DESCRIPTOR -- max dB rise over any 10 ms window in the")
    print("   100 ms after onset, 1 ms envelope. n=100 per unit.")
    print("=" * 78)
    print("   %-6s%12s%12s%12s" % ("unit", "intact", "CUT60", "RAMP60"))
    keep = {}
    for unit in ("ba", "ah"):
        files = sorted(f for f in os.listdir(CORPUS)
                       if f.startswith(unit + "_t06_") and f.endswith(".wav"))[:100]
        I, C, R = [], [], []
        for f in files:
            x = F.read_wav(os.path.join(CORPUS, f))
            I.append(burst_db(x))
            C.append(burst_db(cut60(x)[0]))
            R.append(burst_db(ramp60(x)[0]))
        I, C, R = np.array(I), np.array(C), np.array(R)
        keep[unit] = (I, C, R)
        print("   %-6s%12s%12s%12s"
              % (unit, "%.1f dB" % np.nanmedian(I), "%.1f dB" % np.nanmedian(C),
                 "%.1f dB" % np.nanmedian(R)))
    print("   ba vs ah on the INTACT clips: AUC %.3f  (does the descriptor see"
          " a stop at all?)" % auc(keep["ba"][0], keep["ah"][0]))
    print("   ba intact vs ba RAMP60:      AUC %.3f  (did the ramp remove it?)"
          % auc(keep["ba"][0], keep["ba"][2]))
    print("   ba intact vs ba CUT60:       AUC %.3f  (<0.5 = the splice is"
          " SHARPER than the real release)" % auc(keep["ba"][0], keep["ba"][1]))

    print()
    print("=" * 78)
    print("2. DEGENERATE-DIM AUDIT -- 100 human ba takes, the 996-d vector")
    print("=" * 78)
    z = np.load(os.path.join(OUT, "probe-ba.npz"))
    V = z["intact"]
    s = V.std(axis=0)
    m = np.abs(V.mean(axis=0))
    dead = np.where(s < 1e-12)[0]
    print("   exactly-constant dims (std < 1e-12): %d %s"
          % (dead.size, dead[:20].tolist()))
    tiny = np.where(s < 1e-6)[0]
    print("   near-constant dims  (std < 1e-6):    %d" % tiny.size)
    rel = s / np.maximum(m, 1e-12)
    print("   dims with std/|mean| < 1e-3:         %d"
          % int((rel < 1e-3).sum()))
    print()
    print("   %-15s%5s%12s%12s%12s%12s" % ("block", "d", "std min", "std p50",
                                           "std max", "max/p50"))
    for name, lo, hi in FINE:
        b = s[lo:hi]
        print("   %-15s%5d%12.3e%12.3e%12.3e%12.1f"
              % (name, hi - lo, b.min(), np.median(b), b.max(),
                 b.max() / max(np.median(b), 1e-30)))
    print()
    print("   worst 8 scale outliers over all 996 dims (dim, block, std):")
    order = np.argsort(-s)[:8]
    for d in order:
        nm = next(n for n, lo, hi in FINE if lo <= d < hi)
        print("     dim %4d  %-15s std=%.4f  mean=%.4f" % (d, nm, s[d], V[:, d].mean()))
    print()
    print("   legacy192 sanity: per-clip L2 norm p50=%.6f (it is a POINT ON A"
          % np.median(np.linalg.norm(V[:, 0:192], axis=1)))
    print("   UNIT SPHERE -- its mean and std are constants by construction,")
    print("   %d effective dof, and it is level-free by design)." % 191)


if __name__ == "__main__":
    main()
