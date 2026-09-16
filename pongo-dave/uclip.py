#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DAVE'S U-CLIP  (Pongo Shirts) - parametric, print-ready.
Source of truth: Iddo's paper sketch 2026-09-01, dave-sketch-rotated.jpg
  total height 40 | solid spine 20 | slot depth 20 | outer width 15 | slot 12 | length 70

BROKEN WINDOWS LAW: measure the OUTPUT, never trust the code.
Every dimension printed by this script is read back off the triangle mesh
by ray-casting, not echoed from the parameters.

NOT FOR PRINTING until Iddo says so.
"""
import json, sys
import numpy as np
import shapely.geometry as sg
import trimesh

R = lambda v: float(np.round(v, 4))


def profile(outer_w, slot_w, slot_depth, total_h, fillet_r):
    """Closed 2D U-profile in the X-Z plane. Slot opens toward -Z.
    Fillet is a concave-corner fillet: it ADDS material at the two inner
    corners where the leg inner face meets the slot ceiling - exactly where
    a spring clip cracks."""
    wall = (outer_w - slot_w) / 2.0
    xl, xr = wall, outer_w - wall          # inner faces of the two legs
    r = fillet_r
    if r > 0 and (slot_w <= 2 * r or slot_depth <= r):
        raise ValueError("fillet too large for this slot")

    pts = [(0.0, 0.0), (0.0, total_h), (outer_w, total_h), (outer_w, 0.0), (xr, 0.0)]

    if r > 0:
        # right leg inner face up to the fillet tangent
        pts.append((xr, slot_depth - r))
        cx, cz = xr - r, slot_depth - r                    # right fillet centre
        for a in np.linspace(0.0, np.pi / 2, 33)[1:]:      # 0deg -> 90deg
            pts.append((cx + r * np.cos(a), cz + r * np.sin(a)))
        # slot ceiling, travelling -X
        cx2, cz2 = xl + r, slot_depth - r                  # left fillet centre
        for a in np.linspace(np.pi / 2, np.pi, 33)[1:]:    # 90deg -> 180deg
            pts.append((cx2 + r * np.cos(a), cz2 + r * np.sin(a)))
        pts.append((xl, 0.0))
    else:
        pts += [(xr, slot_depth), (xl, slot_depth), (xl, 0.0)]

    poly = sg.Polygon(pts)
    if not poly.is_valid:
        raise ValueError("profile self-intersects")
    return poly, wall


def build(outer_w, slot_w, slot_depth, total_h, fillet_r, length):
    poly, wall = profile(outer_w, slot_w, slot_depth, total_h, fillet_r)
    m = trimesh.creation.extrude_polygon(poly, height=length)   # extrudes along +Z
    # re-orient: profile X->X, profile Y(height) -> Z, extrusion -> Y (length)
    # +pi/2 (NOT -pi/2): maps profile height -> +Z so the slot opens toward z=0.
    # -pi/2 silently built the clip upside down; the ray measurement caught it.
    m.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
    m.apply_translation(-m.bounds[0])                            # park on the origin
    m.process(validate=True)
    m.fix_normals()
    return m, wall


def ray_spans(mesh, y, z):
    """Cast a ray straight through the part in +X and return the solid spans
    it crosses. This is the MEASUREMENT - it reads the mesh, not the params."""
    xmin, xmax = mesh.bounds[0][0], mesh.bounds[1][0]
    origin = np.array([[xmin - 10.0, y, z]])
    direction = np.array([[1.0, 0.0, 0.0]])
    locs, _, _ = mesh.ray.intersects_location(origin, direction, multiple_hits=True)
    if len(locs) == 0:
        return []
    xs = np.sort(locs[:, 0])
    xs = xs[np.concatenate(([True], np.diff(xs) > 1e-6))]        # dedup edge hits
    return [(R(xs[i]), R(xs[i + 1])) for i in range(0, len(xs) - 1, 2)]


def measure(mesh, name, nominal):
    lo, hi = mesh.bounds
    bb = hi - lo
    ymid = float(lo[1] + bb[1] / 2)
    zmid_slot = float(lo[2] + 5.0)          # 5 mm up inside the slot, clear of the fillet
    zspine = float(hi[2] - 10.0)            # 10 mm down from the top, in the solid spine

    slot_spans = ray_spans(mesh, ymid, zmid_slot)
    spine_spans = ray_spans(mesh, ymid, zspine)

    rep = {
        "variant": name,
        "watertight": bool(mesh.is_watertight),
        "winding_consistent": bool(mesh.is_winding_consistent),
        "volume_positive": bool(mesh.volume > 0),
        "euler_number": int(mesh.euler_number),
        "genus0_prism": bool(mesh.euler_number == 2),
        "triangles": int(len(mesh.faces)),
        "vertices": int(len(mesh.vertices)),
        "bbox_mm_XxYxZ": [R(bb[0]), R(bb[1]), R(bb[2])],
        "volume_mm3": R(mesh.volume),
        "petg_mass_g_at_1.27": R(mesh.volume * 1.27e-3),
        "ray_at_z+5_solid_spans_X": slot_spans,
        "ray_at_top-10_solid_spans_X": spine_spans,
        "nominal": nominal,
    }
    if len(slot_spans) == 2:
        rep["measured_slot_width_mm"] = R(slot_spans[1][0] - slot_spans[0][1])
        rep["measured_wall_left_mm"] = R(slot_spans[0][1] - slot_spans[0][0])
        rep["measured_wall_right_mm"] = R(slot_spans[1][1] - slot_spans[1][0])
    # Which end is open? The slot MUST open at z=0 (mouth down), spine solid at the top.
    mouth = ray_spans(mesh, ymid, float(lo[2] + 1.0))
    rep["ray_at_z+1_solid_spans_X"] = mouth
    rep["slot_opens_at_z0"] = bool(len(mouth) == 2)
    rep["spine_is_solid"] = bool(len(spine_spans) == 1)
    if len(spine_spans) == 1:
        rep["measured_spine_width_mm"] = R(spine_spans[0][1] - spine_spans[0][0])
    return rep


VARIANTS = {
    "v1": dict(slot_w=12.4, wall=1.5, slot_depth=20.0, total_h=40.0, fillet_r=3.0, length=70.0,
               title="v1 - faithful to sketch (1.5 mm wall)"),
    "v2-thick": dict(slot_w=12.4, wall=2.5, slot_depth=20.0, total_h=40.0, fillet_r=3.0, length=70.0,
                     title="v2 - stronger (2.5 mm wall)"),
    # DAVE'S SKETCH, EXACTLY. Iddo, 2026-09-02: "תשנה את V2 שיהיה בדיוק לפי מה
    # שדייב שלח לי ואל תמציא המצאות". He was right, and there were THREE
    # inventions in what I had built, none of which Dave asked for:
    #   slot 12.4  - I added 0.4 mm of "print tolerance" to a 12 mm dimension
    #   wall 2.5   - I doubled it because 1.5 looked thin to me
    #   fillet 3.0 - I added a radius the sketch does not have
    # The sketch says: outer 15, slot 12, height 40, arms 20, length 70.
    # Wall follows from those: (15 - 12) / 2 = 1.5. Nothing else.
    "v2-exact": dict(slot_w=12.0, wall=1.5, slot_depth=20.0, total_h=40.0, fillet_r=0.0,
                     length=70.0, title="v2 - EXACTLY Dave's sketch, no additions"),
}

if __name__ == "__main__":
    out = {}
    for key, p in VARIANTS.items():
        outer = p["slot_w"] + 2 * p["wall"]
        mesh, wall = build(outer, p["slot_w"], p["slot_depth"], p["total_h"], p["fillet_r"], p["length"])
        path = f"D:/CLAUDE/pongo-dave/dave-uclip-{key}.stl"
        mesh.export(path)
        # STL stores 3 unshared verts per facet by format - must merge before
        # judging watertightness, or every mesh looks broken.
        reloaded = trimesh.load(path, process=True)   # measure the FILE, not the object in RAM
        reloaded.merge_vertices()
        rep = measure(reloaded, key, dict(p, outer_w=outer))
        rep["stl"] = path
        rep["title"] = p["title"]
        out[key] = rep
        print(json.dumps(rep, indent=2, ensure_ascii=False))
    with open("D:/CLAUDE/pongo-dave/measured.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
