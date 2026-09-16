# -*- coding: utf-8 -*-
"""PROOF TZ-3 — both verdicts answer the same question with the same bar

Run it against the code on disk:      python proof_TZ-3.py
Run it against the pre-fix backup:    python proof_TZ-3.py <dir-with-the-old-modules>
It must FAIL on the old code and PASS on the new. That is the whole point of it.
"""
import os
import sys
import warnings

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import godot_gate
import ruler

# hold is 1.5x steadier than boil: it beats the floor, but not CLEARLY (gate 1 asks
# for 2x). The two verdicts used to disagree about exactly this band.
CO = {"FLOOR_repaint_every_frame": 0.060, "TZELEM_world_anchored": 0.040,
      "CEILING_warp_only": 0.0}
FI = {"BLANK_best_flat_colour": 0.060, "FLOOR_repaint_every_frame": 0.020,
      "TZELEM_world_anchored": 0.019, "CEILING_warp_only": 0.090}


def main():
    ok_g, why_g = godot_gate.verdict(dict(CO), dict(FI))
    ok_r, why_r = ruler.verdict({"coherence": dict(CO), "fidelity_mse": dict(FI)})
    assert ok_g == ok_r, (
        f"the two verdicts disagree on identical numbers: godot_gate={ok_g}, "
        f"ruler={ok_r}. godot_gate says 'the same two questions gate 1 asks' and "
        f"then asks a bar twice as loose (`hold < boil` against `hold < boil*0.5`), "
        f"and oneroom/gate.py imports it verbatim.")
    assert hasattr(ruler, "COHERENCE_MARGIN"), (
        "the coherence bar is still a bare literal retyped in each verdict")
    src = open(os.path.join(ROOT, "godot_gate.py"), encoding="utf-8").read()
    assert "ruler.COHERENCE_MARGIN" in src, (
        "godot_gate still types its own coherence bar instead of importing gate 1's")
    print(f"PASS  {ROOT}")
    print(f"      identical input -> godot_gate={ok_g}  ruler={ok_r}  "
          f"(COHERENCE_MARGIN={ruler.COHERENCE_MARGIN})")
    print("      " + [l for l in why_g if "coherence" in l][0])


if __name__ == "__main__":
    try:
        main()
    except BaseException as e:                                    # noqa: BLE001
        print(f"FAIL  {ROOT}\n      {type(e).__name__}: {e}")
        sys.exit(1)
    sys.exit(0)
