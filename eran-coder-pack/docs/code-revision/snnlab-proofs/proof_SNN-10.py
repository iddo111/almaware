"""proof_SNN-10 — the gain that decides whether the network fires must be
measured, not a literal.

DEFAULT_GAIN carried 13.86, correct only because the percept is exactly 8x24
(sqrt(8*24) = 13.856, and the real cached percepts have RMS 0.072169 => 13.856).
Cochlea() is parameterised on n_bands and slices, and the same literal was also
applied to `static` on MNIST. The file's own comment records the 2.27%
below-chance run with a silent hidden layer from getting this wrong.

  FAILS on train.py.bak-rev-20260906   PASSES on the fixed train.py
"""
import argparse
import os
import sys

import numpy as np

from _proofcommon import HERE, Quiet, load, tiny_cfg, fake_percepts, verdict


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.path.join(HERE, "train.py"))
    a = ap.parse_args()
    T = load(a.src, "train_under_test")

    dg = getattr(T, "derived_gain", None)
    if dg is None:
        print("train.py has no derived_gain(): the only knob that decides "
              "whether the hidden layer fires is a hand-written 13.86")
        return verdict(False, "derive it from the data or it is a guess")

    # Against the REAL percepts, read straight from the cache (no re-hearing).
    cache = os.path.join(HERE, "data", "syllables_cochlea.npz")
    if os.path.exists(cache):
        xr = np.load(cache)["xtr"]
        g = dg(xr, "cochlea-time")
        print(f"real cached percepts {xr.shape}: RMS "
              f"{float(np.sqrt(np.mean(xr.astype(np.float64) ** 2))):.6f} "
              f"-> derived gain {g:.4f} (literal in the file: 13.86)")
    print(f"rate coding is left alone: derived_gain(x,'rate') = "
          f"{dg(np.ones((4, 8, 24), dtype=np.float32), 'rate')}")

    # An ear with a different shape/scale: the literal goes silent, the derived
    # value keeps the network alive. 100x smaller percepts stand in for it.
    xtr, ytr = fake_percepts(128, seed=1, scale=0.01)
    xte, yte = fake_percepts(44, seed=2, scale=0.01)
    lit = T.run(tiny_cfg(epochs=1, run_id="p10-literal", input_gain=13.86),
                Quiet(), log=lambda *a: None,
                data=(xtr, ytr, xte, yte), install_signals=False)
    der = T.run(tiny_cfg(epochs=1, run_id="p10-derived", input_gain=None),
                Quiet(), log=lambda *a: None,
                data=(xtr, ytr, xte, yte), install_signals=False)
    print(f"literal 13.86 on a 100x quieter ear: hidden_rate="
          f"{lit['hidden_rate']} dead={lit.get('dead')}")
    print(f"derived gain {der['input_gain']:.1f}:              hidden_rate="
          f"{der['hidden_rate']} dead={der.get('dead')}")

    # The literal does not go to exactly zero — the hidden layer still twitches
    # on its own bias — but it sits an order of magnitude below a living rate.
    ratio = der["hidden_rate"] / max(1e-9, lit["hidden_rate"])
    print(f"firing rate, derived vs literal: {ratio:.0f}x")
    ok = (abs(g - 13.856) < 0.01
          and dg(np.ones((4, 8, 24), np.float32), "rate") is None
          and lit["hidden_rate"] < 0.01 and der["hidden_rate"] > 0.05
          and ratio >= 10)
    return verdict(ok, "the input gain is measured off the data now, and a "
                       "changed ear can no longer silence the network")


if __name__ == "__main__":
    sys.exit(main())
