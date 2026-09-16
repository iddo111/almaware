"""resistance_keychain.py — generate resistance-is-fruitful-keychain.stl

A chunky axial-resistor keychain:
  - body: ~60 mm long x 14 mm dia, rounded (capsule) ends
  - 4 raised color bands, ~1 mm proud of the body (single-material relief)
  - two short axial lead stubs
  - flat keyring tab with a 5 mm hole at one end
  - bottom face flattened for FDM printing (part sits at z=0)

Run:  python resistance_keychain.py
Outputs resistance-is-fruitful-keychain.stl next to this script, then
reloads it and verifies watertightness + prints the bounding box in mm.
"""

import os

import numpy as np
import trimesh
from shapely.geometry import Point, box as shapely_box
from trimesh.creation import cylinder, capsule, extrude_polygon
from trimesh.transformations import rotation_matrix

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_STL = os.path.join(HERE, "resistance-is-fruitful-keychain.stl")

# ---------------------------------------------------------------- dimensions
BODY_LEN = 60.0          # total body length incl. rounded ends
BODY_R = 7.0             # body radius (14 mm dia)
BAND_R = BODY_R + 1.0    # bands 1 mm proud
BAND_W = 3.5             # band width along axis
BAND_X = [-16.0, -9.0, -2.0, 12.0]   # classic 3 grouped + offset tolerance band
LEAD_R = 1.6             # lead stub radius (3.2 mm dia — printable)
LEAD_X0, LEAD_X1 = 28.0, 38.0        # +X lead span (2 mm embedded, 8 mm exposed)
TAB_THICK = 8.0          # keyring tab thickness (chunky = strong), z -6..+2
TAB_HALF_W = 7.0         # tab half-width in Y
TAB_ROOT_X = -36.5       # tab root — lead tip (-38) embeds 1.5 mm into it
HOLE_X = -49.0           # keyring hole center = center of rounded tip (tip at -56)
HOLE_R = 2.5             # 5 mm hole
FLAT_Z = -6.0            # everything below this plane is cut off (1 mm off body)

# rotate a +Z-axis primitive onto the +X axis
ROT_Z_TO_X = rotation_matrix(np.pi / 2.0, [0, 1, 0])


def centered_on_x(mesh, x_center=0.0):
    """Rotate a Z-axis primitive onto X and center it at x_center on the axis."""
    mesh.apply_transform(ROT_Z_TO_X)
    c = mesh.bounds.mean(axis=0)
    mesh.apply_translation([x_center - c[0], -c[1], -c[2]])
    return mesh


def build():
    parts = []

    # --- resistor body: capsule, axis on X, centered at origin
    body = capsule(height=BODY_LEN - 2 * BODY_R, radius=BODY_R, count=[48, 48])
    parts.append(centered_on_x(body, 0.0))

    # --- 4 raised color bands
    for bx in BAND_X:
        band = cylinder(radius=BAND_R, height=BAND_W, sections=96)
        parts.append(centered_on_x(band, bx))

    # --- two short axial lead stubs
    lead_len = LEAD_X1 - LEAD_X0
    for sign in (+1.0, -1.0):
        lead = cylinder(radius=LEAD_R, height=lead_len, sections=48)
        parts.append(centered_on_x(lead, sign * (LEAD_X0 + LEAD_X1) / 2.0))

    # --- flat keyring tab with 5 mm hole (extruded 2D outline, hole built in)
    #     rounded tip centered on the hole; -X lead tip embeds into the root
    outline = Point(HOLE_X, 0).buffer(TAB_HALF_W, resolution=48)
    outline = outline.union(
        shapely_box(HOLE_X, -TAB_HALF_W, TAB_ROOT_X, TAB_HALF_W)
    )
    outline = outline.difference(Point(HOLE_X, 0).buffer(HOLE_R, resolution=48))
    tab = extrude_polygon(outline, height=TAB_THICK)   # z: 0 .. TAB_THICK
    tab.apply_translation([0, 0, FLAT_Z])              # bottom sits on the flat plane
    parts.append(tab)

    # --- bottom bridge: ties tab root to body under the exposed -X lead
    #     (strength joint + prints from the bed; lead's top half stays visible)
    parts.append(
        trimesh.creation.box(bounds=[[-38.0, -4.0, FLAT_Z], [-26.0, 4.0, -1.0]])
    )

    # --- thin support rib under the +X lead so the stub prints without supports
    parts.append(
        trimesh.creation.box(bounds=[[29.0, -1.2, FLAT_Z], [37.5, 1.2, -1.0]])
    )

    # --- union everything into one solid (manifold engine)
    solid = trimesh.boolean.union(parts, engine="manifold")

    # --- flatten the bottom: subtract a slab below FLAT_Z
    lo, hi = solid.bounds
    pad = 5.0
    slab = trimesh.creation.box(
        bounds=[
            [lo[0] - pad, lo[1] - pad, lo[2] - pad],
            [hi[0] + pad, hi[1] + pad, FLAT_Z],
        ]
    )
    solid = trimesh.boolean.difference([solid, slab], engine="manifold")

    # --- rest the flat face on z=0 for printing
    solid.apply_translation([0, 0, -solid.bounds[0][2]])
    solid.process(validate=True)
    return solid


def main():
    solid = build()
    assert solid.is_watertight, "generated mesh is not watertight"
    assert solid.is_winding_consistent, "winding inconsistent"
    assert solid.volume > 0, "non-positive volume"
    solid.export(OUT_STL)
    print(f"wrote {OUT_STL}")

    # --- verify by loading the STL back
    check = trimesh.load(OUT_STL, force="mesh")
    check.process(validate=True)
    assert check.is_watertight, "reloaded STL is not watertight"
    ext = check.bounding_box.extents
    print(f"watertight: {check.is_watertight}")
    print(f"bounding box (mm): {ext[0]:.2f} x {ext[1]:.2f} x {ext[2]:.2f}")
    print(f"faces: {len(check.faces)}  volume: {check.volume:.1f} mm^3")


if __name__ == "__main__":
    main()
