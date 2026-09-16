# -*- coding: utf-8 -*-
"""PROOF TZ-11 — gate 1 no longer re-derives a picture it already holds

Run it against the code on disk:      python proof_TZ-11.py
Run it against the pre-fix backup:    python proof_TZ-11.py <dir-with-the-old-modules>
It must FAIL on the old code and PASS on the new. That is the whole point of it.
"""
import os
import sys
import warnings

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import numpy as np


def main():
    import canvas
    import ruler
    n = {"render": 0, "warp": 0}
    r_real, w_real = canvas.render, canvas.warp
    canvas.render = lambda *a, **k: (n.__setitem__("render", n["render"] + 1),
                                     r_real(*a, **k))[1]
    canvas.warp = lambda *a, **k: (n.__setitem__("warp", n["warp"] + 1),
                                   w_real(*a, **k))[1]
    try:
        res = ruler.measure(width=120, height=90, n_strokes=600)
    finally:
        canvas.render, canvas.warp = r_real, w_real
    assert n["render"] <= 3, (
        f"{n['render']} full renders for one gate. FLOOR's frame a is the same "
        f"scatter, same seed, same camera as TZELEM's — bit for bit the picture the "
        f"run already holds.")
    assert n["warp"] <= 1, f"{n['warp']} warps for one gate; one is enough."
    assert res["coherence"]["TZELEM_world_anchored"] > 0
    print(f"PASS  {ROOT}")
    print(f"      canvas.render calls per gate = {n['render']} (was 4)")
    print(f"      canvas.warp   calls per gate = {n['warp']} (was 3)")


if __name__ == "__main__":
    try:
        main()
    except BaseException as e:                                    # noqa: BLE001
        print(f"FAIL  {ROOT}\n      {type(e).__name__}: {e}")
        sys.exit(1)
    sys.exit(0)
