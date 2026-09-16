# -*- coding: utf-8 -*-
"""make_eran_tubes.py -- print ERAN'S OWN throat, at ERAN's own size.

לזכרה של עלמה ז״ל

WHY THIS EXISTS
===============
make_tract.py (2026-08-07, same folder) wrote the question down and was never
answered:

    "If the printed tube measures near 641/1117, the simulator is a real model
     of a real object ... If it does not, the model is a toy, and we would
     rather find that out now."

Nobody printed it. Meanwhile the mouth it read from (voice-ant-farm/head_sim,
17.15 cm, VOWELS dict) was RETIRED and replaced by MOUTH v2. So this script is
make_tract.py with exactly ONE thing swapped -- the source of the bore profile
-- and two things added: the child anatomy, and a glottis flange so a 12 cm
tube can stand on a print bed and take a palm seal.

  REUSED VERBATIM from make_tract.py:  ring(), band(), write_stl()
  SWAPPED:  bore profile now comes from eran-brain/voice/mouth2/geometry.py
            (Story & Bunton 2018 male child), not head_sim.tract_diameters.
  ADDED:    glottis flange + chamfer, and area-averaged ring radii.

THE THREE TUBES
===============
  TUBE-UNIFORM   uniform 1.5 cm^2 -- the EXACT object mouth2's gate (a)
                 certified (validate/v_a_tube_law.py line: `AREA = 1.5`).
                 A straight pipe with an exact closed-open answer: odd
                 multiples of c/4L. If this one does not ring at 1:3:5 the
                 RIG is wrong, and nothing else measured here means anything.
  TUBE-NEUTRAL   geometry.child_area(60) neutral -- ERAN's rest tract.
  TUBE-A         geometry.child_area(60, vowel='a') -- ERAN's /a/ posture.

BORE CONSTRUCTION -- and the defect the measuring script caught, 2026-09-01
==========================================================================
First cut averaged the two neighbouring element AREAS at each element
boundary (make_tract.py averages the two DIAMETERS). measure_eran_tubes.py
then sliced the exported solid and found the bore off the anatomy by +26% at
the /a/ constriction and +14% at the neutral glottis: averaging at boundaries
SMOOTHS AWAY EXTREMA, and on this anatomy the extremum IS the vowel.

Fixed: the bore radius is a PCHIP through the element-CENTRE radii -- the same
shape-preserving interpolant mouth2/geometry.py uses on its own 8 knots -- and
a ring is placed at every element centre and every boundary. So the area at
each element centre is the published area, and nothing between two rings has
to be guessed. Re-measured: worst error now well under 1%.

NOTHING HERE PRINTS ANYTHING. It writes STL files. Printing waits for Iddo.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from scipy.interpolate import PchipInterpolator

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "eran-brain" / "voice" / "mouth2"))

import geometry                                   # noqa: E402  MOUTH v2 anatomy
from make_tract import ring, band, write_stl      # noqa: E402  REUSED

AGE_MONTHS = 60
WALL_MM = 3.0        # rigid PLA wall; ~200x the air impedance, effectively hard
FLANGE_OD = 26.0     # mm, glottis-end disc: print foot + palm seal + clamp face
FLANGE_T = 3.0       # mm thick
CHAMFER = 0.8        # mm cone from flange OD down to the tube OD (no overhang)
OUT_DIR = HERE / "ERAN-TUBES-20260901"


def bore_radius_fn(areas_cm2: np.ndarray, length_mm: float):
    """r_in(z) in mm: PCHIP through the element-CENTRE radii, clamped at the ends.

    Shape preserving -- no overshoot, no invented constriction between knots.
    Evaluated at a clipped z so the flange face and the lip face inherit the
    first and last element instead of a cubic extrapolation.
    """
    a = np.asarray(areas_cm2, float)
    n = a.size
    dz = length_mm / n
    z_c = (np.arange(n) + 0.5) * dz
    r_c = np.sqrt(a / np.pi) * 10.0
    f = PchipInterpolator(z_c, r_c)

    def r_in(z):
        return float(f(np.clip(z, z_c[0], z_c[-1])))

    z_knots = np.unique(np.round(
        np.concatenate([z_c, np.arange(n + 1) * dz]), 6))
    return r_in, z_knots


def build_tube(areas_cm2: np.ndarray, length_mm: float):
    """Lofted annulus with a glottis flange. Returns (triangles, profile)."""
    r_in_at, z_anat = bore_radius_fn(areas_cm2, length_mm)
    r_fl = FLANGE_OD / 2.0
    z_ch = FLANGE_T + CHAMFER

    # Every anatomical z, plus the flange face, flange top, chamfer end and the
    # lip face. np.unique kills duplicates -- duplicate z is what makes
    # zero-area facets, the 2026-08-24 junk-block failure mode.
    z_knots = np.unique(np.round(np.concatenate(
        [z_anat, [0.0, FLANGE_T, z_ch, length_mm]]), 6))
    z_knots = z_knots[(z_knots >= 0.0) & (z_knots <= length_mm + 1e-9)]

    prof = []
    for z in z_knots:
        ri = r_in_at(z)
        if z <= FLANGE_T + 1e-9:
            ro = r_fl
        elif z < z_ch - 1e-9:
            t = (z - FLANGE_T) / CHAMFER          # linear chamfer, no overhang
            ro = (1.0 - t) * r_fl + t * (ri + WALL_MM)
        else:
            ro = ri + WALL_MM
        prof.append((float(z), ri, float(ro)))

    inner = [ring(p[1], p[0]) for p in prof]
    outer = [ring(p[2], p[0]) for p in prof]

    tris = []
    for i in range(len(prof) - 1):
        tris += band(inner[i], inner[i + 1], flip=True)    # bore faces inward
        tris += band(outer[i], outer[i + 1], flip=False)   # wall faces outward
    tris += band(inner[0], outer[0], flip=False)           # glottis annulus
    tris += band(inner[-1], outer[-1], flip=True)          # lip annulus
    return tris, prof


def main() -> int:
    OUT_DIR.mkdir(exist_ok=True)
    L_cm, neutral = geometry.child_area(AGE_MONTHS)
    _, a_vowel = geometry.child_area(AGE_MONTHS, vowel="a")
    L_mm = L_cm * 10.0
    uniform = np.full(neutral.size, 1.5)

    parts = [
        ("TUBE-UNIFORM-calibration.stl", uniform,
         "uniform 1.5 cm2 -- the object gate (a) certified"),
        ("TUBE-NEUTRAL.stl", neutral,
         "geometry.child_area(60) neutral"),
        ("TUBE-A.stl", a_vowel,
         "geometry.child_area(60, vowel='a')"),
    ]

    print("ERAN TUBES -- child anatomy from mouth2/geometry.py, "
          "age %d months" % AGE_MONTHS)
    print("tract length %.4f cm = %.2f mm, %d elements of %.4f mm"
          % (L_cm, L_mm, neutral.size, L_mm / neutral.size))
    print("=" * 78)
    for name, areas, note in parts:
        tris, prof = build_tube(areas, L_mm)
        write_stl(OUT_DIR / name, tris)
        bore = 2.0 * np.array([p[1] for p in prof])
        od = 2.0 * np.array([p[2] for p in prof])
        print("%-32s %6d tri   %s" % (name, len(tris), note))
        print("     bore %5.2f - %5.2f mm   OD max %5.2f mm   height %.2f mm"
              % (bore.min(), bore.max(), od.max(), prof[-1][0]))
    print("=" * 78)
    print("wrote to", OUT_DIR)
    print("NOW RUN measure_eran_tubes.py -- it reads the STL back and does not")
    print("trust one number printed above.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
