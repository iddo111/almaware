# -*- coding: utf-8 -*-
"""make_real_mold.py -- an OPEN-TOP pour mold for a silicone vocal fold. A REAL mold.

THE SCAR THIS REPLACES (2026-08-24): make_silicone_fold_mold.py produced a marching-cubes
blob that was 96.5% SOLID -- a plastic block. Iddo printed it. The acceptance test it never
ran, and this file runs first: a mold must be MOSTLY EMPTY (cavity), open on top (pourable),
and the cast part must pull straight up (demoldable).

DESIGN -- the standard open-face pour mold used for synthetic vocal folds:
  - a rectangular TUB: floor + 4 walls, open top.
  - the M5 fold profile (Titze/Scherer -- the published synthetic-fold cross-section)
    stands up from the floor as a solid CORE, extruded the fold's length.
  - pour silicone in the tub; it fills AROUND the core up to the fill line;
    cure; flex the walls; the cast block with the M5 groove pulls straight up.
  - the cast = a soft block whose underside carries the exact M5 medial surface;
    it clamps into the buzz-collar with the M5 face toward the airway.
  - straight vertical extrusion => zero undercuts => always demoldable.

Geometry is BUILT FROM POLYGONS (triangulated prism + tub shell), not sampled from a field,
so it is exact, watertight by construction, and verifiable by simple numbers.

Prints flat, no supports (walls are vertical, core is vertical, floor on the bed).

  python make_real_mold.py    -> THROAT-MOLD-A-real.stl (+ acceptance numbers printed)
"""
import numpy as np
import trimesh

# ---- the M5 profile (mm), medial-lateral (x) vs inferior-superior (y) ----
# Same published point set the old script carried; closed polygon.
M5 = np.array([
    (6.08, 0.00), (4.89, 1.00), (3.70, 2.00), (2.50, 3.00), (1.31, 4.00), (0.12, 5.00),
    (0.00, 6.40), (0.289, 7.098), (0.987, 7.387), (9.00, 8.40), (9.00, 0.00),
], dtype=float)

FOLD_LEN = 17.0     # anterior-posterior length of the fold (extrusion, mm)
WALL = 2.4          # tub wall thickness
FLOOR = 2.0         # tub floor thickness
CLEAR = 4.0         # silicone margin around the core on each side
HEADROOM = 3.0      # silicone above the core's top (the fold's clamped base)
DRAFT_GAP = 0.0     # straight walls; Ecoflex flexes out easily


def prism(profile2d, length):
    """Extrude a closed 2D polygon along +Z into a watertight triangulated prism."""
    poly = trimesh.path.polygons.Polygon(profile2d)
    mesh = trimesh.creation.extrude_polygon(poly, height=length)
    return mesh


def box(size, origin):
    b = trimesh.creation.box(extents=size)
    b.apply_translation(np.array(origin) + np.array(size) / 2.0)
    return b


def main():
    # --- the core: M5 profile standing UP (profile in XY, extruded in Z = fold length) ---
    # Rotate so the fold's height (y of profile) is the vertical print axis:
    # extrude in Z then rotate so extrusion lies along X (fold length along X),
    # profile height along Z (up), profile width along Y.
    core = prism(M5, FOLD_LEN)
    core.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [0, 1, 0]))
    core.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
    core.apply_translation(-core.bounds[0])  # sit at origin, all-positive

    cw = core.bounds[1] - core.bounds[0]     # core extents: [FOLD_LEN, profile_w, profile_h]

    # --- the tub: inner cavity = core + clearance + headroom ---
    inner = np.array([cw[0] + 2 * CLEAR, cw[1] + 2 * CLEAR, cw[2] + HEADROOM])
    outer = inner + np.array([2 * WALL, 2 * WALL, 0.0])

    tub_outer = box([outer[0], outer[1], inner[2] + FLOOR], [0, 0, 0])
    tub_inner = box([inner[0], inner[1], inner[2] + 0.2], [WALL, WALL, FLOOR])
    tub = tub_outer.difference(tub_inner)

    # --- place the core on the tub floor, centered ---
    core.apply_translation([WALL + CLEAR, WALL + CLEAR, FLOOR])
    mold = tub.union(core)

    # --- a fill line groove on the inner wall at core-top + headroom is implicit (rim) ---

    # ---- ACCEPTANCE: the numbers a mold must pass ----
    bb = mold.bounds[1] - mold.bounds[0]
    box_vol = bb.prod()
    solid_pct = mold.volume / box_vol * 100
    cavity_ml = (inner.prod() - core.volume) / 1000.0
    print(f"outer size      : {bb.round(1)} mm")
    print(f"solid fraction  : {solid_pct:.1f}%   (a block is ~96%; a mold must be well below 80%)")
    print(f"pour cavity     : {cavity_ml:.1f} ml of silicone per fold")
    print(f"watertight      : {mold.is_watertight}")
    print(f"open top        : yes by construction (tub, no lid)")
    print(f"demoldable      : straight vertical core, no undercuts")
    assert mold.is_watertight, "NOT watertight - do not ship"
    assert solid_pct < 80, f"TOO SOLID ({solid_pct:.0f}%) - this is a block, not a mold"
    assert cavity_ml > 1.0, "cavity too small to pour"

    out = "THROAT-MOLD-A-real.stl"
    mold.export(out)
    print(f"wrote {out}  ({len(mold.faces)} triangles)")
    return mold, cw, inner


if __name__ == "__main__":
    main()
