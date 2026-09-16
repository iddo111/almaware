# -*- coding: utf-8 -*-
"""PROOF TZ-2 — coherence bought with fidelity is FAILED, not passed

Run it against the code on disk:      python proof_TZ-2.py
Run it against the pre-fix backup:    python proof_TZ-2.py <dir-with-the-old-modules>
It must FAIL on the old code and PASS on the new. That is the whole point of it.
"""
import os
import sys
import warnings

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import godot_gate
import ruler

# The boulevard's OWN stored numbers, out-night/godot-gate1.json, which the file
# records as "pass": true.
CO = {"FLOOR_repaint_every_frame": 0.06305337175323517,
      "TZELEM_world_anchored": 0.013867577991897658,
      "CEILING_warp_only": 0.0}
FI = {"BLANK_best_flat_colour": 0.06555384068841175,
      "FLOOR_repaint_every_frame": 0.012934,
      "TZELEM_world_anchored": 0.01983569156894489,
      "CEILING_warp_only": 0.09}


def main():
    ok_g, why_g = godot_gate.verdict(dict(CO), dict(FI))
    ok_r, why_r = ruler.verdict({"coherence": dict(CO), "fidelity_mse": dict(FI)})
    for name, ok, why in (("godot_gate", ok_g, why_g), ("ruler", ok_r, why_r)):
        assert not ok, (
            f"{name}.verdict still says PASS on the stored boulevard numbers, where "
            f"TZELEM's fidelity 0.019836 is 53% WORSE than the repaint floor's "
            f"0.012934. The steadiness is being bought with fidelity and nothing "
            f"gates the trade.")
        assert any("fidelity vs FLOOR" in l for l in why), (
            f"{name}.verdict does not even mention the FLOOR fidelity it computes "
            f"and stores in every JSON.")
    print(f"PASS  {ROOT}")
    for l in why_g:
        if "FLOOR" in l:
            print("      godot_gate:", l)
    for l in why_r:
        if "FLOOR" in l:
            print("      ruler     :", l)


if __name__ == "__main__":
    try:
        main()
    except BaseException as e:                                    # noqa: BLE001
        print(f"FAIL  {ROOT}\n      {type(e).__name__}: {e}")
        sys.exit(1)
    sys.exit(0)
