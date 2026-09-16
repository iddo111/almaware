# -*- coding: utf-8 -*-
"""PROOF TZ-16 — gate 2\'s bars can state a distance instead of a preference

Run it against the code on disk:      python proof_TZ-16.py
Run it against the pre-fix backup:    python proof_TZ-16.py <dir-with-the-old-modules>
It must FAIL on the old code and PASS on the new. That is the whole point of it.
"""
import os
import sys
import warnings

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

def main():
    import gate2
    assert hasattr(gate2, "spread"), (
        "gate 2 measures ONE seed at ONE camera pose and its two bars are bare "
        "constants, so nothing can say whether the stored margin is one sigma or "
        "ten. Gate 1 has had ruler.sweep since the day it was written.")
    one = gate2.resolution_free(n_strokes=300, factor=2, verbose=False)
    assert one.get("samples") == 1, one.get("samples")
    s = gate2.spread(n_strokes=300, factor=2, seeds=(7, 11), angles=(0.0, 6.0),
                     verbose=False)
    assert s["samples"] == 4, s["samples"]
    for k in ("ownership_agreement", "fidelity_ratio"):
        assert {"mean", "std", "min", "max", "n"} <= set(s[k]), s[k]
    assert set(s["sigmas_from_bar"]) == {"ownership", "fidelity"}
    print(f"PASS  {ROOT}")
    o, f = s["ownership_agreement"], s["fidelity_ratio"]
    print(f"      ownership {o['mean']:.5f} +- {o['std']:.5f} over {o['n']} samples "
          f"({s['sigmas_from_bar']['ownership']:.1f} sigma above the "
          f"{s['bars']['ownership']} bar)")
    print(f"      fidelity  {f['mean']:.5f} +- {f['std']:.5f} "
          f"({s['sigmas_from_bar']['fidelity']:.1f} sigma below the "
          f"{s['bars']['fidelity']} bar)")


if __name__ == "__main__":
    try:
        main()
    except BaseException as e:                                    # noqa: BLE001
        print(f"FAIL  {ROOT}\n      {type(e).__name__}: {e}")
        sys.exit(1)
    sys.exit(0)
