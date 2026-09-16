# -*- coding: utf-8 -*-
"""THE GATE THAT WOULD HAVE CAUGHT IT: does the export still have the scene's colour?

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

On 2026-09-06 the cube exporter spent an hour producing beautiful, geometrically
perfect, completely COLOURLESS plates, because `_apply(scene, null)` deleted the
twenty materials `boulevard_cafe.gd` assigns through `material_override`. Every
existing check passed: hit fraction fine, depth range fine, luminance SPREAD fine
(white against black sky is a big spread), seam fine, coverage 99.999%, sharpness
above the threshold. Not one of them could see that the picture had no colour in it.

That is the pattern RAMCHAT calls out: a liveness check survives, a usefulness check
dies. So this is a USEFULNESS gate, and it is written to REFUSE, not to reassure:

    a face full of surfaces whose mean chroma has collapsed is a face whose
    materials were wiped, and it does not ship.

THE THRESHOLD IS MEASURED, NOT GUESSED. `boulevard_shots.gd` -- which never touches
material_override, and is therefore the ground truth for what this world looks like --
gives mean saturation 0.550 at pose 02. The broken export gave 0.329, the fixed one
0.544. A floor of 0.42 sits between them with room on both sides, and it is applied
only to faces that are mostly SURFACE: a face pointing at the sky is legitimately
unsaturated and must not be failed for it.

Run:  python gate_cube360_colour.py <folder of face_*.tzg>
Exit 0 = PASS, 1 = REFUSED.
"""
from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gbuffer                                   # noqa: E402

FACES = ("px", "nx", "py", "ny", "pz", "nz")
SAT_FLOOR = 0.42          # boulevard_shots.gd measures 0.550; the wiped export 0.329
SURFACE_MIN = 0.60        # only judge faces that are mostly surface, not sky
LUM = np.array([0.2126, 0.7152, 0.0722])


def chroma(rgb: np.ndarray) -> np.ndarray:
    mx, mn = rgb.max(-1), rgb.min(-1)
    return np.where(mx > 1e-6, (mx - mn) / np.maximum(mx, 1e-6), 0.0)


def main(folder: str) -> int:
    print(f"colour gate on {folder}")
    judged, failed = 0, []
    for name in FACES:
        g, cam = gbuffer.load(os.path.join(folder, f"face_{name}"))
        m = g["mask"]
        surf = float(m.mean())
        rgb = g["albedo"][m] if m.any() else g["albedo"].reshape(-1, 3)
        sat = float(chroma(rgb).mean())
        lum = rgb @ LUM
        dark = float((lum < 0.25).mean())
        verdict = "-- not judged (mostly sky)"
        if surf >= SURFACE_MIN:
            judged += 1
            ok = sat >= SAT_FLOOR
            verdict = "PASS" if ok else "*** REFUSED: chroma collapsed ***"
            if not ok:
                failed.append(name)
        print(f"  {name}: surface {surf*100:5.1f}%  saturation {sat:.3f}  "
              f"dark<0.25 {dark*100:5.1f}%   {verdict}")
    if judged == 0:
        print("REFUSED: no face had enough surface to judge -- this is not a "
              "verdict on the colour, it is a refusal to pretend there was one")
        return 1
    if failed:
        print(f"REFUSED: {len(failed)} of {judged} judged faces are below the "
              f"{SAT_FLOOR} chroma floor: {failed}")
        print("  The likeliest cause, because it has happened: something nulled "
              "material_override. boulevard_cafe.gd sets 20 materials that way, and "
              "wiping them leaves Godot's default white. Check that the trees still "
              "have their green -- their material is on the MESH and survives, which "
              "is what makes the failure look plausible instead of obviously broken.")
        return 1
    print(f"PASS: all {judged} surface-bearing faces carry the scene's colour "
          f"(floor {SAT_FLOOR}, boulevard_shots.gd measures 0.550)")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main(sys.argv[1]))
