# -*- coding: utf-8 -*-
"""PROOF TZ-12 — gate 2 runs the ownership pass once per resolution

Run it against the code on disk:      python proof_TZ-12.py
Run it against the pre-fix backup:    python proof_TZ-12.py <dir-with-the-old-modules>
It must FAIL on the old code and PASS on the new. That is the whole point of it.
"""
import os
import sys
import warnings

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

def main():
    import canvas
    import gate2
    n = {"own": 0}
    real = canvas.ownership

    def counted(*a, **k):
        n["own"] += 1
        return real(*a, **k)

    canvas.ownership = counted
    gate2.canvas.ownership = counted
    try:
        out = gate2.resolution_free(n_strokes=400, factor=2, verbose=False)
    finally:
        canvas.ownership = real
        gate2.canvas.ownership = real
    assert n["own"] <= 2, (
        f"canvas.ownership ran {n['own']} times for two resolutions. render() calls "
        f"ownership() internally, so the splat loop over every stroke's bounding box "
        f"was running twice per resolution for one answer.")
    assert 0.0 <= out["ownership_agreement"] <= 1.0
    print(f"PASS  {ROOT}")
    print(f"      canvas.ownership calls for a 2-resolution gate = {n['own']} (was 4)")
    print(f"      ownership_agreement {out['ownership_agreement']:.6f}  "
          f"fidelity_ratio {out['fidelity_ratio']:.6f}")


if __name__ == "__main__":
    try:
        main()
    except BaseException as e:                                    # noqa: BLE001
        print(f"FAIL  {ROOT}\n      {type(e).__name__}: {e}")
        sys.exit(1)
    sys.exit(0)
