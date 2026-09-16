# -*- coding: utf-8 -*-
"""
> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

THE A/B — same scene, same geometry, same anchors, same strokes, same seed.
The ONLY thing that changes is what a surface is made of.

FOUR ARMS, because two would have flattered the new organ
----------------------------------------------------------
  A  FLAT        the room's 105 authored RGB triples. Shadow + AO on, texture OFF.
                 This is "materials OFF" in the strict sense.
  B  PROCEDURAL  `occlusion.texture` at 0.30 — three octaves of world-space value
                 noise plus a grain and a scratch pass. This is the state of the
                 art as of 02:45 tonight and it already bought 326 -> 372 lit.
                 Comparing C only against A would have been a rigged fight.
  C  MATERIALS   Iddo's own photographs, triplanar at true world scale, the normal
                 map perturbing the shading normal, roughness driving a specular
                 lobe. Everything else — shadow, AO, exposure restore, tint, gain,
                 emissive override — is line-for-line the same as A and B.
  D  ABLATION    C with the normal map and the specular switched off, so the
                 report can say how much of C is the photograph and how much is
                 the lighting model.

WHAT IS HELD FIXED (and it is everything else)
-----------------------------------------------
  * the anchors: `workshop.anchors(0.0090, 1_200_000)` is called ONCE and its
    output is shared by all six arms, so not one stroke moves between them
  * the occlusion pass: computed ONCE on those anchors and reused
  * radius 0.021, seed 17, world tangents, `soft=False` (the hard, sharp path
    found tonight — and the one thing that must not be regressed)
  * camera `room.rail_camera(0.30)`, 1600x900, matching the published stills

THE RULER is `sharpness.lapvar_array` — Laplacian variance, greyscale, long edge
CAPPED at 2400 px, never upscaled. It reproduces `tzelem_boulevard.jpg` at 719
and `oneroom-workshop-lit.jpg` at 126, which are the two readings Iddo's
rejection was set on. `lapvar_norm` is reported beside it because raw lapvar
scales with the SQUARE of contrast and would otherwise reward a brighter picture.

Run:  python ab.py            (on eran1, ~20 min)
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
import resource
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")

import material as MAT                                     # noqa: E402
import occlusion                                           # noqa: E402
import room                                                # noqa: E402
import workshop as W                                       # noqa: E402
from sharpness import lapvar_array, lapvar_norm_array      # noqa: E402

OUT = os.path.join(HERE, "ab-out")
MATS = os.path.join(HERE, "mats")
WD, HT, T = 1600, 900, 0.30
VOXEL, MAXSTROKES, RADIUS = 0.0090, 1_200_000, 0.021
WORLD_MM = 1000.0            # the workshop is authored in METRES
FOOTPRINT_MM = RADIUS * 2.0 * WORLD_MM      # 42 mm: what ONE brushstroke covers


# WHICH PHOTOGRAPH EACH SURFACE OF THE WORKSHOP WEARS.
#
# Say the awkward part out loud: Iddo filmed his DESK, not a workshop. There is no
# plaster wall, no concrete floor and no painted steel cabinet anywhere in the
# footage, so `wall`, `ceiling` and `panel` are wearing the speckle of his vinyl
# floor tile and the cabinets are wearing the brushed steel of his rule. Every
# assignment below is a JUDGEMENT about which real surface is closest, and the
# room's own authored colour is kept as the tint, so a red toolbox stays red — it
# just stops being a flat red.
ASSIGN = {
    "wall": "floor_vinyl", "ceiling": "floor_vinyl", "panel": "floor_vinyl",
    "white": "paper_stack", "paper": "paper_stack",
    "bench": "wood_polished", "tool_wood": "wood_polished",
    "pegboard": "wood_polished", "wood": "wood_carved_dark",
    "cabinet": "steel_brushed", "steel": "steel_brushed",
    "tool": "steel_brushed", "alu": "steel_brushed",
    "black": "plastic_black", "glass": "plastic_black",
    "red": "plastic_black", "teal": "plastic_black", "orange": "plastic_black",
    "green": "plastic_black", "blue": "plastic_black",
    "__ground__": "floor_vinyl",
}

# PLACEMENT SIZE for arm E, and every one of these numbers is a DEPARTURE FROM
# TRUE SCALE that has to be declared. Arm C places every material at 1.0 — the
# size `calibrate.py` measured. Arm E enlarges the pattern until its texel is
# roughly a fifth of a brushstroke, because `material.lod_for` showed that at
# life size a 0.168 mm-texel photograph is a 4x4 map behind a 42 mm brush and
# cannot reach the picture at all. The photograph is still Iddo's; the SIZE is
# ours, and it is the only number in this run that is not measured.
SCALE_ROOM = {"wood_polished": 7.0, "wood_carved_dark": 6.0, "paper_stack": 5.0,
              "plastic_black": 11.0, "steel_brushed": 20.0, "floor_vinyl": 1.0}


def mat_ids(bx: np.ndarray) -> tuple[np.ndarray, list[str]]:
    """Anchor -> which of the room's material names it sits on. Ints, not strings."""
    names = ["__ground__"] + sorted({b["mat"] for b in room.BOXES})
    idx = {n: i for i, n in enumerate(names)}
    per_box = np.array([idx[b["mat"]] for b in room.BOXES], dtype=np.int64)
    ids = np.where(bx < 0, 0, per_box[np.clip(bx, 0, len(per_box) - 1)])
    return ids, names


# --------------------------------------------------------- the three colour paths

def colours_flat_or_proc(st, pt, nr, bx, state, occ, texture_strength):
    """Arms A and B: `workshop.colours` itself, with the texture knob at 0 or 0.30."""
    return W.colours(st, pt, nr, bx, state, occ,
                     texture_strength=texture_strength)


def colours_materials(st, pt, nr, bx, state, occ, mset, ids, names,
                      cam_eye, use_normal=True, use_spec=True,
                      spec_strength=0.18, detail_strength=1.0):
    """Arm C. `workshop.colours` line for line, with THREE substitutions.

    1. the procedural `occlusion.texture(...)` multiplier on albedo becomes the
       material's measured DETAIL (mean 1.0, so exposure does not move)
    2. Lambert is taken against the NORMAL-MAPPED normal, not the face normal —
       this is the line that turns 105 flat boxes into surfaces, because a wall
       stops being one grey and becomes thousands of greys that catch the light
       at slightly different angles
    3. a Blinn-Phong specular lobe whose exponent is read off the material's
       roughness map, so the polished desk has a sheen the pegboard does not

    Everything else — the checker on the ground, the exposure restore, the tint,
    the gain, the emissive override — is copied from `workshop.colours` verbatim
    so the arms differ by the material and by nothing else.
    """
    s = room.STATES[state]
    ld = np.asarray(s["light_dir"], dtype=np.float64)
    ld = ld / np.linalg.norm(ld)
    amb = float(s["ambient"])

    alb = np.zeros((len(pt), 3))
    for i, b in enumerate(st.boxes):
        m = bx == i
        if m.any():
            alb[m] = b.albedo
    gnd = bx < 0
    if gnd.any():
        chk = ((np.floor(pt[gnd, 0]) + np.floor(pt[gnd, 2])) % 2 == 0)
        alb[gnd] = np.where(chk[:, None], st.ground_albedo * 1.25,
                            st.ground_albedo * 0.72)

    surf = mset.surfaces(pt, nr, ids, names, world_scale_mm=WORLD_MM,
                         normal_strength=1.0 if use_normal else 0.0,
                         footprint_mm=FOOTPRINT_MM)
    # DETAIL STRENGTH, the same dial `occlusion.texture` already has. 1.0 is the
    # photograph as measured; 0.5 is half way to the flat colour. It exists because
    # at full strength the workshop's plaster picks up every stain of Iddo's floor
    # tile and reads as mould, which is more real but not necessarily better.
    det = 1.0 + detail_strength * (surf["detail"] - 1.0)
    alb = np.clip(alb * det, 0.0, 1.0)
    n_sh = surf["normal"] if use_normal else nr

    lam0 = np.clip(-(nr @ ld), 0.0, 1.0)                 # the geometric Lambert
    lam = np.clip(-(n_sh @ ld), 0.0, 1.0)                # the normal-mapped one
    lam_lit = lam
    sun = occ["sun_dark"] if state == "dark" else occ["sun_lit"]
    lam_lit = lam * (1.0 - 0.70 * (1.0 - sun))
    col = alb * (amb + (1.0 - amb) * lam_lit[:, None])
    col = col * (1.0 - 0.80 * (1.0 - occ["ao"]))[:, None]
    col = col * surf["ao"][:, None]                      # the material's own cavity

    # EXPOSURE RESTORE, identical in form to `workshop.colours`: occlusion can only
    # ever take light away, and raw Laplacian variance scales with contrast SQUARED,
    # so without this the arms would be compared at different brightnesses.
    ref = (alb * (amb + (1.0 - amb) * lam0[:, None])).mean()
    now = col.mean()
    if now > 1e-9:
        col = col * (ref / now)

    if use_spec:
        to_light = -ld
        v = np.asarray(cam_eye, dtype=np.float64)[None, :] - pt
        v = v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-12)
        h = to_light[None, :] + v
        h = h / np.maximum(np.linalg.norm(h, axis=1, keepdims=True), 1e-12)
        ndh = np.clip(np.einsum("ij,ij->i", n_sh, h), 0.0, 1.0)
        expo = np.clip(2.0 / np.maximum(surf["roughness"], 0.02) ** 2, 2.0, 512.0)
        f0 = 0.04 + 0.9 * surf["metallic"]
        lobe = f0 * ndh ** expo * (lam > 0) * sun
        tintc = np.where(surf["metallic"][:, None] > 0.5, alb, 1.0)
        col = col + spec_strength * lobe[:, None] * tintc

    col = col * np.asarray(s["tint"]) * s["gain"]

    which = 0 if state == "dark" else 1
    for i, e in enumerate(st.emit):
        if e is None or e[which] is None:
            continue
        m = bx == i
        if m.any():
            col[m] = e[which]
    return np.clip(col, 0.0, 1.0)


# --------------------------------------------------------------------- the run

rows: list[dict] = []


def shot(tag, pt, nr, rgb, state, owner_ref=None):
    from PIL import Image
    img, secs, cov = W.paint(pt, nr, rgb, RADIUS, WD, HT, state, t=T,
                             soft=False, kwargs_tangent=True)
    p = os.path.join(OUT, f"{tag}.jpg")
    Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).save(
        p, quality=94, subsampling=0)
    r = {"tag": tag, "state": state, "file": p,
         "lapvar": round(lapvar_array(img), 1),
         "lapvar_norm": round(lapvar_norm_array(img), 1),
         "coverage": round(cov, 4), "render_s": round(secs, 1),
         "mean": round(float(img.mean()), 5)}
    rows.append(r)
    print(f"  {tag:<34} lapvar {r['lapvar']:8.1f}  (norm {r['lapvar_norm']:7.1f})"
          f"  mean {r['mean']:.4f}  cov {cov*100:5.1f}%  {secs:5.1f}s", flush=True)
    del img
    return r


def rss_gb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    t0 = time.time()
    print(f"anchors: voxel {VOXEL} max {MAXSTROKES:,}", flush=True)
    a = W.anchors(VOXEL, MAXSTROKES)
    st = a.pop("stage")
    pt, nr, bx = a["point"], a["normal"], a["box"]
    plant_s = a["plant_seconds"]
    print(f"    {len(pt):,} anchors, {plant_s:.0f}s", flush=True)

    t = time.time()
    occ = W.occlude_anchors(st, pt, nr)
    occ_s = time.time() - t

    ids, names = mat_ids(bx)
    mset = MAT.MaterialSet.from_dir(MATS, ASSIGN)
    mroom = MAT.MaterialSet.from_dir(MATS, ASSIGN, scale=SCALE_ROOM)
    lods = {}
    for nm, m in mset.materials.items():
        for lbl, k in (("true", 1.0), ("room", SCALE_ROOM.get(nm, 1.0))):
            lod = MAT.lod_for(m, FOOTPRINT_MM / k)
            lods[f"{nm}@{lbl}"] = {"placed_mm": round(m.physical_size_mm * k, 1),
                                   "lod": round(lod, 2),
                                   "effective_map": m.size >> int(np.floor(lod))}
    print(f"\nWHAT THE BRUSH CAN CARRY (footprint {FOOTPRINT_MM:.0f} mm):",
          flush=True)
    for k, v in lods.items():
        print(f"    {k:28s} placed {v['placed_mm']:7.1f} mm  LOD {v['lod']:5.2f}"
              f"  -> a {v['effective_map']}x{v['effective_map']} map", flush=True)
    cov_names = {n: int((ids == i).sum()) for i, n in enumerate(names)}
    have = {n for n in names if mset.for_surface(n) is not None}
    covered = sum(v for k, v in cov_names.items() if k in have)
    print(f"\nmaterial coverage: {covered:,}/{len(pt):,} anchors "
          f"= {covered/len(pt)*100:.1f}%   "
          f"({len(have)}/{len(names)} of the room's surface names)", flush=True)

    # TZ-7 (2026-09-06): COVERAGE IS NOT REACH. `material_coverage_frac: 1.0` was true
    # and meaningless at the same time: at this brush most of these materials clip to
    # the top of the mip pyramid and become a CONSTANT. Measured at 42 mm --
    # steel_brushed a 1x1 map with sampled detail std 0.001578 about a mean of 0.9737,
    # i.e. a flat multiplier of ~1.0 and literally nothing, plastic_black 1x1,
    # wood_polished 2x2; only floor_vinyl (1.5 mm/texel) survives. Those two dead
    # materials wear ~118,000 of the 1.2M anchors. The number that matters is not
    # "is a material assigned" but "does it reach the picture".
    flat_names = {n for n in have
                  if MAT.effective_map_px(mset.for_surface(n),
                                          FOOTPRINT_MM / float(
                                              mset.scale.get(
                                                  mset.for_surface(n).name, 1.0)))
                  < MAT.FLAT_TEXELS}
    flat = sum(v for k, v in cov_names.items() if k in flat_names)
    flat_frac = flat / max(len(pt), 1)
    print(f"material REACH: {flat:,} anchors ({flat_frac*100:.1f}%) wear a material "
          f"that has collapsed below {MAT.FLAT_TEXELS} texels at this brush and is a "
          f"CONSTANT, not a texture: {sorted(flat_names)}", flush=True)
    if flat_frac > MAT.FLAT_FRAC_BAR:
        print(f"REFUSING to call this run 'MATERIALS ON': {flat_frac*100:.1f}% of the "
              f"anchors carry a collapsed material (bar {MAT.FLAT_FRAC_BAR*100:.0f}%). "
              f"Harvest inside the band the brush can carry — a {FOOTPRINT_MM:.0f} mm "
              f"brush wants texels around 1.5-5 mm, which is exactly why floor_vinyl "
              f"is the only one that survives — instead of reaching for scale_room.",
              flush=True)

    cam_eye = room.rail_camera(T, WD, HT).eye
    timings = {"plant_s": round(plant_s, 1), "occlusion_s": round(occ_s, 1),
               "colour_s": {}}

    for state in ("lit", "dark"):
        print(f"\n===== {state.upper()} =====", flush=True)

        t = time.time()
        rgbA = colours_flat_or_proc(st, pt, nr, bx, state, occ, 0.0)
        timings["colour_s"][f"A-{state}"] = round(time.time() - t, 2)
        shot(f"A-{state}-flat", pt, nr, rgbA, state)
        del rgbA

        t = time.time()
        rgbB = colours_flat_or_proc(st, pt, nr, bx, state, occ, 0.30)
        timings["colour_s"][f"B-{state}"] = round(time.time() - t, 2)
        shot(f"B-{state}-procedural", pt, nr, rgbB, state)
        del rgbB

        t = time.time()
        rgbC = colours_materials(st, pt, nr, bx, state, occ, mset, ids, names,
                                 cam_eye)
        timings["colour_s"][f"C-{state}"] = round(time.time() - t, 2)
        shot(f"C-{state}-materials", pt, nr, rgbC, state)
        del rgbC

        t = time.time()
        rgbD = colours_materials(st, pt, nr, bx, state, occ, mset, ids, names,
                                 cam_eye, use_normal=False, use_spec=False)
        timings["colour_s"][f"D-{state}"] = round(time.time() - t, 2)
        shot(f"D-{state}-albedo-only", pt, nr, rgbD, state)
        del rgbD

        t = time.time()
        rgbE = colours_materials(st, pt, nr, bx, state, occ, mroom, ids, names,
                                 cam_eye)
        timings["colour_s"][f"E-{state}"] = round(time.time() - t, 2)
        shot(f"E-{state}-materials-roomscale", pt, nr, rgbE, state)
        del rgbE

        t = time.time()
        rgbF = colours_materials(st, pt, nr, bx, state, occ, mroom, ids, names,
                                 cam_eye, detail_strength=0.5)
        timings["colour_s"][f"F-{state}"] = round(time.time() - t, 2)
        shot(f"F-{state}-roomscale-half", pt, nr, rgbF, state)
        del rgbF

    with open(os.path.join(OUT, "ab.json"), "w", encoding="utf-8") as fh:
        json.dump({"when": time.strftime("%Y-%m-%dT%H:%M:%S"),
                   "anchors": int(len(pt)), "voxel": VOXEL, "radius": RADIUS,
                   "size": [WD, HT], "camera_t": T, "soft": False,
                   "world_mm_per_unit": WORLD_MM,
                   "assignment": ASSIGN, "scale_room": SCALE_ROOM,
                   "footprint_mm": FOOTPRINT_MM, "lods": lods,
                   "material_coverage_frac": round(covered / len(pt), 4),
                   # TZ-7: the half of the story `covered` cannot tell.
                   "material_flat_frac": round(flat_frac, 4),
                   "material_flat_names": sorted(flat_names),
                   "materials_really_on": bool(flat_frac <= MAT.FLAT_FRAC_BAR),
                   "anchors_per_surface_name": cov_names,
                   "timings": timings, "peak_rss_gb": round(rss_gb(), 2),
                   "total_seconds": round(time.time() - t0, 1),
                   "rows": rows}, fh, indent=1)
    print(f"\npeak RSS {rss_gb():.2f} GB, total {time.time()-t0:.0f}s", flush=True)
    print("wrote " + os.path.join(OUT, "ab.json"), flush=True)


if __name__ == "__main__":
    main()
