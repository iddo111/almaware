# -*- coding: utf-8 -*-
"""measure_eran_tubes.py -- read the EXPORTED STL back and believe only it.

SCAR 2026-08-24: make_real_mold.py printed `check() OK` while the exported
object was a 96.5% solid block -- the generator measured its own intention.
SCAR still open today: make_silicone_fold_mold.py prints `0 open edges` while
the exported mesh carries non-manifold edges and zero-area facets.

So this script imports NOTHING from make_eran_tubes.py. It opens the .stl
files as a stranger would, and it does four things the generator cannot fake:

  1. mesh health   -- watertight, non-manifold edges, zero-area facets,
                      solid fraction (volume / bounding box) -- the junk-block
                      detector.
  2. bore, measured -- slices the SOLID at 44 heights and takes the area of
                      the HOLE in each slice (shapely). This is the bore of
                      the object, not of the plan.
  3. anatomy error  -- measured bore areas vs geometry.child_area(60), the
                      published Story & Bunton child.
  4. THE PREDICTION -- feeds the MEASURED areas into analytic2 and prints the
                      resonances this OBJECT should have in air, with the
                      open-end correction bracket. That bracket is the
                      acceptance band for the microphone.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import trimesh

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "eran-brain" / "voice" / "mouth2"))
import analytic2                      # noqa: E402
import geometry                       # noqa: E402

OUT_DIR = HERE / "ERAN-TUBES-20260901"
K2_BED = (352.5, 352.0, 360.0)
PLA_DENSITY = 1.24                    # g/cm^3


def bore_areas_mm2(mesh: trimesh.Trimesh, zs) -> np.ndarray:
    """Area of the hole in the solid at each height z. Measured, not assumed."""
    out = []
    for z in zs:
        sec = mesh.section(plane_origin=[0, 0, float(z)], plane_normal=[0, 0, 1])
        if sec is None:
            out.append(np.nan)
            continue
        planar, _ = sec.to_planar()
        polys = planar.polygons_full
        if not polys:
            out.append(np.nan)
            continue
        poly = max(polys, key=lambda p: p.area)
        hole = sum(abs(trimesh.path.polygons.Polygon(r).area) for r in poly.interiors)
        out.append(hole)
    return np.array(out, dtype=float)


def report(path: Path, target_areas_cm2, label: str) -> bool:
    # process=True MERGES coincident vertices. An STL has no shared vertices
    # by definition, so this is the only honest way to ask whether the SOLID
    # is closed -- it is also exactly what a slicer does. Loading with
    # process=False reports every edge as non-manifold and is meaningless.
    m = trimesh.load_mesh(path, process=True)
    ok = True
    ext = m.extents
    bbox_vol = float(np.prod(ext))
    vol = float(m.volume)
    frac = vol / bbox_vol

    zero_area = int((m.area_faces <= 1e-12).sum())
    # an edge of a closed manifold solid is shared by EXACTLY two faces
    uniq, counts = np.unique(m.edges_sorted, axis=0, return_counts=True)
    nonmanifold = int((counts != 2).sum())

    print("\n" + "=" * 78)
    print("%s   [%s]" % (path.name, label))
    print("=" * 78)
    print("  triangles          %d" % len(m.faces))
    print("  bounding box       %.2f x %.2f x %.2f mm" % tuple(ext))
    print("  watertight         %s" % m.is_watertight)
    print("  winding consistent %s" % m.is_winding_consistent)
    print("  volume             %.0f mm3   (%.1f g in PLA)"
          % (vol, vol / 1000.0 * PLA_DENSITY))
    print("  solid fraction     %.1f%% of its bounding box   "
          "(JUNK-block 2026-08-24 was 96.5%%)" % (frac * 100))
    print("  zero-area facets   %d" % zero_area)
    print("  non-manifold edges %d" % nonmanifold)
    print("  fits K2 Plus       %s  (bed %.0f x %.0f x %.0f)"
          % (all(ext[i] < K2_BED[i] for i in range(3)), *K2_BED))

    for cond, why in ((m.is_watertight, "not watertight"),
                      (zero_area == 0, "zero-area facets"),
                      (nonmanifold == 0, "non-manifold edges"),
                      (frac < 0.60, "solid fraction >= 60%% -- LOOKS LIKE A BLOCK"),
                      (all(ext[i] < K2_BED[i] for i in range(3)), "does not fit K2")):
        if not cond:
            ok = False
            print("  *** FAIL: %s" % why)

    # ---- bore measured off the solid ----
    n = len(target_areas_cm2)
    height = float(ext[2])
    dz = height / n
    zs = (np.arange(n) + 0.5) * dz
    hole_mm2 = bore_areas_mm2(m, zs)
    meas_cm2 = hole_mm2 / 100.0
    if np.isnan(meas_cm2).any():
        ok = False
        print("  *** FAIL: %d slices had no measurable bore"
              % int(np.isnan(meas_cm2).sum()))
        return ok

    tgt = np.asarray(target_areas_cm2, float)
    err = (meas_cm2 - tgt) / tgt * 100.0
    print("  bore measured      %.3f - %.3f cm2  (= %.2f - %.2f mm diameter)"
          % (meas_cm2.min(), meas_cm2.max(),
             2 * np.sqrt(meas_cm2.min() / np.pi) * 10,
             2 * np.sqrt(meas_cm2.max() / np.pi) * 10))
    print("  vs anatomy         median %+.2f%%, worst %+.2f%%   "
          "(faceting of a 64-gon bore is -0.16%% by itself)"
          % (np.median(err), err[np.argmax(np.abs(err))]))
    if np.abs(err).max() > 2.0:
        ok = False
        print("  *** FAIL: bore departs from the anatomy by more than 2%")

    # ---- the acceptance band, from the MEASURED object ----
    L_cm = height / 10.0
    hard = analytic2.resonances_physical(meas_cm2, L_cm, n=3)
    r_lip = np.sqrt(meas_cm2[-1] / np.pi)          # cm
    dL = 0.6 * r_lip                                # unflanged open-end
    soft = analytic2.resonances_physical(
        np.append(meas_cm2, meas_cm2[-1]), L_cm + dL, n=3)
    print("  --- WHAT THE MICROPHONE SHOULD SEE (predicted from the mesh) ---")
    print("  rigid open end     %s Hz" % ["%.0f" % x for x in hard])
    print("  + end correction   %s Hz   (open end adds %.2f mm)"
          % (["%.0f" % x for x in soft], dL * 10))
    print("  ACCEPT F1 in       %.0f - %.0f Hz  (band + 5%% either side: %.0f - %.0f)"
          % (soft[0], hard[0], soft[0] * 0.95, hard[0] * 1.05))
    print("  ratios F2/F1 %.3f  F3/F1 %.3f" % (hard[1] / hard[0], hard[2] / hard[0]))
    return ok


def main() -> int:
    L_cm, neutral = geometry.child_area(60)
    _, a_vowel = geometry.child_area(60, vowel="a")
    uniform = np.full(neutral.size, 1.5)
    jobs = [("TUBE-UNIFORM-calibration.stl", uniform, "uniform 1.5 cm2 -- rig check"),
            ("TUBE-NEUTRAL.stl", neutral, "ERAN neutral"),
            ("TUBE-A.stl", a_vowel, "ERAN /a/")]
    print("MEASURED OFF THE EXPORTED STL -- nothing here is taken from the generator")
    print("anatomy authority: mouth2/geometry.py child_area(60), L = %.2f cm" % L_cm)
    allok = True
    for name, tgt, lab in jobs:
        allok &= report(OUT_DIR / name, tgt, lab)
    print("\n" + "=" * 78)
    print("ALL PARTS PASS:", allok)
    print("NOT PRINTED. Printing waits for Iddo's word.")
    return 0 if allok else 1


if __name__ == "__main__":
    raise SystemExit(main())
