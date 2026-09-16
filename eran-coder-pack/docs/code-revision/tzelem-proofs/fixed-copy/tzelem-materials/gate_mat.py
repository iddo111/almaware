# -*- coding: utf-8 -*-
"""
> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

DOES THE MATERIALS ORGAN BREAK THE GATE?

A sharper picture that shimmers when the camera moves is worse than a blurry one
that holds still, and TZELEM exists to make exactly the coherence claim that
shimmer would destroy. So the organ is run through `gate_hard.py` itself — same
`one_pair`, same `verdict`, same `ruler._mse` and `ruler._resid`, same 1920x1080,
same 5 rail poses, same 30,000 strokes, same seeds — with ONE substitution:

    room.plain_stage(state)          ->   the same boxes wearing materials

Nothing else in this file is mine. `run()` is imported from `gate_hard` and
monkey-patched at exactly one place, `room.plain_stage`, so a difference in the
numbers cannot be a difference in the measurement.

The material is baked into the G-BUFFER by `material.MaterialStage`, so
`Stage.shade` — the fidelity ruler — is untouched, and the painter and the ruler
receive the material from the same line of code.
"""
from __future__ import annotations

# TZ-8 (2026-09-06): FIRST, BEFORE NUMPY. Caps the BLAS/OpenMP thread pools (they
# size themselves once, at numpy import) and drops this process's priority. The
# materials track had NO nice, no priority class and no thread cap anywhere while
# every other TZELEM entry point has set BELOW_NORMAL since the 2026-09-03 KESHEV
# starvation — and it was run on eran1, the box that serves ERAN's live microphone.
import courtesy                                             # noqa: E402,F401

import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")

import gate_hard                                          # noqa: E402
import material as MAT                                    # noqa: E402
import room                                               # noqa: E402
from ab import ASSIGN, SCALE_ROOM                         # noqa: E402
from stage import Box, Stage                              # noqa: E402

OUT = os.path.join(HERE, "gate-out")
FOOTPRINT_MM = 0.006 * 2.0 * 1000.0     # the GATE's brush is size 0.006, not 0.021


class MatStage(MAT.MaterialStage, Stage):
    """`room.plain_stage`'s Stage, wearing materials. Nothing else differs."""


def make(state: str, scale: dict | None, detail: float = 1.0) -> MatStage:
    s = room.STATES[state]
    mset = MAT.MaterialSet.from_dir(os.path.join(HERE, "mats"), ASSIGN,
                                    scale=scale or {})
    return MatStage(
        [Box(np.array(b["lo"]), np.array(b["hi"]), np.array(room.MAT[b["mat"]]))
         for b in room.BOXES],
        ground_albedo=(0.40, 0.395, 0.38),
        light_dir=s["light_dir"], ambient=s["ambient"],
        mset=mset, mat_of_box=[b["mat"] for b in room.BOXES],
        ground_mat="__ground__", footprint_mm=FOOTPRINT_MM,
        world_scale_mm=1000.0, detail_strength=detail)


def reach(scale: dict | None) -> dict:
    """TZ-7: DOES THE MATERIAL REACH THE PICTURE AT THIS BRUSH, OR ONLY THE MANIFEST?

    A material finer than the brush collapses to a 1x1 or 2x2 map -- a constant -- and
    the old pipeline went on reporting it as an active material at 100% coverage. This
    is printed before every arm so "MATERIALS ON" cannot mean "a .tzm was assigned".
    """
    mset = MAT.MaterialSet.from_dir(os.path.join(HERE, "mats"), ASSIGN,
                                    scale=scale or {})
    out, flat = {}, 0
    for name in sorted(set(ASSIGN.values())):
        m = mset.for_surface(next(k for k, v in ASSIGN.items() if v == name))
        if m is None:
            continue
        mult = float(mset.scale.get(m.name, 1.0))
        px = MAT.effective_map_px(m, FOOTPRINT_MM / mult)
        out[name] = px
        flat += int(px < MAT.FLAT_TEXELS)
    frac = flat / max(len(out), 1)
    print(f"  REACH at {FOOTPRINT_MM:.0f} mm: " +
          "  ".join(f"{k}={v}x{v}" for k, v in out.items()), flush=True)
    print(f"  {flat}/{len(out)} materials have collapsed below {MAT.FLAT_TEXELS} "
          f"texels — they are CONSTANTS at this brush", flush=True)
    if frac > MAT.FLAT_FRAC_BAR:
        print(f"  NOT HONESTLY 'MATERIALS ON': {frac*100:.0f}% of the assigned "
              f"materials do not reach the picture (bar "
              f"{MAT.FLAT_FRAC_BAR*100:.0f}%)", flush=True)
    return {"effective_map_px": out, "flat_materials": flat,
            "flat_frac": round(frac, 4),
            "materials_really_on": bool(frac <= MAT.FLAT_FRAC_BAR)}


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    rec = {"when": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "footprint_mm": FOOTPRINT_MM, "runs": []}
    orig = room.plain_stage
    arms = [("OFF   (the committed baseline)", None, None),
            ("ON  true scale", {}, 1.0),
            ("ON  7x room scale", SCALE_ROOM, 1.0)]
    try:
        for label, scale, detail in arms:
            for state in ("lit", "dark"):
                if scale is None:
                    room.plain_stage = orig
                else:
                    room.plain_stage = (
                        lambda st, _s=scale, _d=detail: make(st, _s, _d))
                print(f"\n===== MATERIALS {label} / {state} =====", flush=True)
                reach_rec = ({"effective_map_px": {}, "flat_materials": 0,
                              "flat_frac": 0.0, "materials_really_on": False}
                             if scale is None else reach(scale))
                r = gate_hard.run(state, soft=False)
                r["arm"] = label
                r["reach"] = reach_rec           # TZ-7
                rec["runs"].append(r)
    finally:
        room.plain_stage = orig
    p = os.path.join(OUT, "gate-materials.json")
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, indent=2, ensure_ascii=False)
    print("\n" + "=" * 78)
    for r in rec["runs"]:
        print(f"  {r['arm']:<32} {r['state']:<5} pass={r['pass']}  "
              f"steadier x{r['steadier_than_floor']:.2f}  "
              f"vs blank x{r['better_than_blank']:.2f}  "
              f"lapvar {r['lapvar_tzelem']:.1f}  "
              f"reach {(1 - r['reach']['flat_frac'])*100:.0f}%", flush=True)
    print("\nwrote " + p, flush=True)


if __name__ == "__main__":
    main()
