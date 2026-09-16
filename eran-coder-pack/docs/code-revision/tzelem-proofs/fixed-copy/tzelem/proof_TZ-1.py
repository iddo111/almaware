# -*- coding: utf-8 -*-
"""PROOF TZ-1 — the CEILING coherence number is gone, and the warp is computed once

Run it against the code on disk:      python proof_TZ-1.py
Run it against the pre-fix backup:    python proof_TZ-1.py <dir-with-the-old-modules>
It must FAIL on the old code and PASS on the new. That is the whole point of it.
"""
import os
import sys
import warnings

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import numpy as np
import canvas
import ruler


def main():
    seen = {"warp": 0}
    real = canvas.warp
    canvas.warp = lambda *a, **k: (seen.__setitem__("warp", seen["warp"] + 1),
                                   real(*a, **k))[1]
    try:
        r = ruler.measure(width=120, height=90, n_strokes=600, sweep_deg=4.0)
    finally:
        canvas.warp = real

    co = r["coherence"]
    zeros = {k: v for k, v in co.items() if v == 0.0}
    assert not zeros, (
        f"the coherence dict still carries a number that is exactly 0.0 on a "
        f"non-degenerate input: {zeros}. It is 0 BY IDENTITY (the same array scored "
        f"against itself) and it was printed as a PASS.")
    assert "CEILING_warp_only" not in co, (
        "CEILING_warp_only is still in the coherence dict; a number that cannot vary "
        "must not sit beside two that can.")
    assert seen["warp"] == 1, (
        f"canvas.warp ran {seen['warp']} times for one gate; it only ever needed to "
        f"run once (all three roles are the same array).")
    assert co["TZELEM_world_anchored"] > 0 and co["FLOOR_repaint_every_frame"] > 0
    print(f"PASS  {ROOT}")
    print(f"      coherence keys = {sorted(co)}")
    print(f"      canvas.warp calls per gate = {seen['warp']}")
    print(f"      TZELEM {co['TZELEM_world_anchored']:.5f}  "
          f"FLOOR {co['FLOOR_repaint_every_frame']:.5f}")


if __name__ == "__main__":
    try:
        main()
    except BaseException as e:                                    # noqa: BLE001
        print(f"FAIL  {ROOT}\n      {type(e).__name__}: {e}")
        sys.exit(1)
    sys.exit(0)
