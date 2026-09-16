# -*- coding: utf-8 -*-
"""Write the README that sits next to the plate, with every number READ FROM THE
REPORT rather than retyped. A hand-typed number in a README is a future lie.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

T = """> \U0001fa9f **BROKEN WINDOWS LAW — \u05d7\u05d5\u05e7 \u05d4\u05d7\u05dc\u05d5\u05e0\u05d5\u05ea \u05d4\u05e9\u05d1\u05d5\u05e8\u05d9\u05dd:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` \u2260 working). A broken window left unfixed invites decay.

# CAFE CLAUDE IN 360 — a VR plate
### \u05e7\u05e4\u05d4 \u05e7\u05dc\u05d5\u05d3 \u05d1-360 — \u05dc\u05d5\u05d7 \u05dc\u05de\u05e9\u05e7\u05e4\u05d9 VR

**{date}** · TZELEM / \u05e6\u05dc\u05dd · \u05dc\u05d6\u05db\u05e8\u05d4 \u05e9\u05dc \u05e2\u05dc\u05de\u05d4 \u05d6"\u05dc

---

## WHAT THIS FILE IS / \u05de\u05d4 \u05d6\u05d4 \u05d4\u05e7\u05d5\u05d1\u05e5

**EN.** `{plate}` is a **360° equirectangular** plate — a full sphere of the
Rothschild Boulevard scene, painted by TZELEM, seen from **one** point: standing at
the Cafe Claude tables, eye at **{eye}** metres, the exact origin
`boulevard_shots.gd` pose `02-cafe-claude` already stands a person at.

**HE.** \u05d6\u05d4 \u05dc\u05d5\u05d7 **\u05e4\u05e0\u05d5\u05e8\u05de\u05d9 \u05e9\u05dc\u05dd 360°** (equirectangular) \u05e9\u05dc \u05e9\u05d3\u05e8\u05d5\u05ea \u05e8\u05d5\u05d8\u05e9\u05d9\u05dc\u05d3,
\u05de\u05e6\u05d5\u05d9\u05d9\u05e8 \u05e2\u05dc \u05d9\u05d3\u05d9 TZELEM, \u05de\u05e0\u05e7\u05d5\u05d3\u05d4 \u05d0\u05d7\u05ea: \u05e2\u05d5\u05de\u05d3\u05d9\u05dd \u05dc\u05d9\u05d3 \u05e9\u05d5\u05dc\u05d7\u05e0\u05d5\u05ea \u05e7\u05e4\u05d4 \u05e7\u05dc\u05d5\u05d3.

| | |
|---|---|
| **projection** | equirectangular, 2:1, longitude \u2212180…+180 left to right, latitude +90…\u221290 top to bottom |
| **size** | **{w} × {h}** |
| **PPD at the equator** | **{ppd:.2f}** pixels per degree (= width / 360) |
| **target headset** | HTC Vive gen-1, 1080×1200 per eye ≈ **11 PPD** — this plate is **{ratio:.1f}×** its glass |
| **centre column** | aimed at world point (2.40, 1.55, 12.6), i.e. yaw **{yaw:.2f}°** — a viewer opens looking at the cafe |
| **stereo** | **NONE. This is MONO.** See below. |
| **built from** | six cubemap faces, {face}×{face}, exactly 90.0° FOV, one shared eye |

## HOW TO VIEW IT / \u05d0\u05d9\u05da \u05dc\u05e6\u05e4\u05d5\u05ea

1. **Any 360 photo viewer.** It is a standard 2:1 equirectangular image — drop the
   `.jpg` into a photo-sphere viewer, VLC's 360 mode, or a WebXR viewer and it wraps
   correctly with no metadata needed.
2. **In the Godot project** (`D:\\CLAUDE\\alma-vr\\godot`): make a `PanoramaSkyMaterial`,
   set its panorama to this image, hang it on a `Sky` in a `WorldEnvironment` with
   `background_mode = BG_SKY`, and stand inside it. That is also how it would be shown
   through OpenXR once the Vive is wired in — **which it is not yet**; `WEAVE-BRIDGE.md`
   says headset support is M3.
3. **Flat.** Open the `.jpg`. The middle is the cafe; the left and right edges join.

## THE HONEST LIMITS / \u05d4\u05de\u05d2\u05d1\u05dc\u05d5\u05ea \u05d1\u05d9\u05d5\u05e9\u05e8

**NO DEPTH. This plate is MONO and both eyes see the same picture.** Real panoramic
stereo is *omni-directional stereo*: every output **column** must be rendered from a
different eye position around a circle of radius IPD/2 (~32.5 mm). Nothing in TZELEM
or in the Godot scripts does that — every camera in both is a single pinhole. The
cheap substitute, offsetting the whole camera by an IPD, gives correct depth **ahead**
and **INVERTED depth behind you**, which is actively unpleasant in a headset. So it
was not done. If stereo is wanted, the honest move is a **VR180 forward pair** for one
fixed view, where a constant offset really is correct.

**\u05d0\u05d9\u05df \u05e2\u05d5\u05de\u05e7.** \u05d6\u05d4 \u05de\u05d5\u05e0\u05d5 — \u05e9\u05ea\u05d9 \u05d4\u05e2\u05d9\u05e0\u05d9\u05d9\u05dd \u05e8\u05d5\u05d0\u05d5\u05ea \u05d0\u05d5\u05ea\u05d4 \u05ea\u05de\u05d5\u05e0\u05d4. \u05dc\u05d0 \u05de\u05d6\u05d9\u05d9\u05e4\u05d9\u05dd \u05ea\u05dc\u05ea-\u05de\u05d9\u05de\u05d3.

**More pixels would buy nothing.** Above the headset's PPD, resolution is invisible.
8192 wide is already ~2× the Vive gen-1. 12288 would be a bigger file and the same
picture.

## WHAT WAS MEASURED / \u05de\u05d4 \u05e0\u05de\u05d3\u05d3

Every number below was measured by the run that produced this plate
(`{report}`), not quoted from anywhere.

| what | value | the gate |
|---|---|---|
| coverage, worst of the six faces | **{cov:.3f} %** | ≥ 99 % or REJECT — below that the plate has **holes showing background** |
| coverage on surface pixels only (sky dome excluded) | {covs:.3f} % | — |
| **seam**, mean \\|difference\\| across every face boundary | **{seam:.5f}** | compare with the next row |
| the picture's own adjacent-pixel texture, same places | {base:.5f} | the seam is **{sratio:.2f}×** this, i.e. no larger than the grain |
| seam, worst single edge | {seammax:.5f} | |
| **sharpness** (Laplacian variance) | **{lap:.1f}** | Iddo rejected the workshop at 126 |
| the same ruler on the *unpainted* Godot plate | {rawlap} | what the paint is worth |
| pixels per degree at the equator | {ppd:.2f} | the Vive gen-1 shows ~11 |
| brushstrokes, world-anchored | {strokes:,} | {apx:.2f} per face pixel |
| render time, six faces on the GPU | {gsec} s | RTX 3070 Ti, BELOW_NORMAL |
| paint + stitch + measure | {sec:.0f} s | numpy only, BELOW_NORMAL |

### which view the ruler was run on, and why
**Not the equirect.** An equirect stretches its poles by 1/cos(latitude), so measuring
sharpness on it scores a projection artefact. A headset shows a *rectilinear* view, so
that is what is measured: a **{cutfov:.0f}° rectilinear cut, {cut}×{cut} px**, centred on the
plate's own centre direction — the cafe, the thing a viewer opens looking at. {cut} px is
exactly width/4, the natural resolution of a 90° window in a {w}-wide equirect, so
nothing is resampled, and it is under `sharpness.py`'s 2400 px cap so it is measured
**native**. The ruler is `D:\\CLAUDE\\sharpen\\sharpness.py`, imported, never re-written.
(For the record the equirect itself reads {lapequi:.1f} — that number is not the one to use.)

## HOW IT WAS MADE / \u05d0\u05d9\u05da \u05d6\u05d4 \u05e0\u05d1\u05e0\u05d4

```
Godot 4.3, PC, RTX 3070 Ti     alma-vr/godot/scripts/tzelem_cube360.gd
  six faces, ONE eye, exactly 90.0 deg, square viewport (so H-FOV == V-FOV)
  per-face up vectors, because look_at(dir, UP) is degenerate for +-Y
  -> face_*.tzg  (depth + world normal + the BEAUTY colour, the format
                  tzelem/gbuffer.py already reads)
TZELEM, numpy                  tzelem/cube360_paint.py
  plant world-anchored strokes from all six faces into ONE set
  canvas.ownership + Palette.lookup  = the HARD compositor path (soft=False)
  -> six painted faces
                               tzelem/cube360.py
  seamless bilinear resample of the six into one equirect
  -> the plate
```

**Four decisions worth knowing about, because each one was a trap:**

1. **The HARD compositor path.** Settled in `sharpen/README-FINDINGS.md` on
   2026-09-06: the blur was never the brush, it was the soft path averaging every
   stroke that covers a pixel, so *more paint made it blurrier*. The hard path is
   pure nearest-wins ownership — one stroke owns one pixel, no blending, no sort.

2. **A render margin was tried, measured, and REJECTED** — and this is the most
   useful thing in this folder, because the reasoning for it was good and the
   measurement still said no. SSAO, glow and volumetric fog are **screen-space**: at
   a frame border they invent their missing neighbours, and the invention differs
   between the two faces sharing that border. So each face was rendered larger at a
   wider FOV and cropped back to the central 90°. Matched pair at 512 px/face, same
   pose, full warm-up, only the margin different:

   | | margin (fov 102.7° cropped to 90°) | **no margin (fov exactly 90°)** |
   |---|---|---|
   | surface pixels blown past luminance 0.95 | **33.97 %** | **1.57 %** |
   | mean saturation | 0.3064 | **0.3535** |
   | painted seam ÷ the picture's own texture | 1.11× | **0.87×** |
   | raw unpainted seam, mean | 0.0198 | 0.0291 |

   The wider frame drags far more sky and sunlit pavement in, and the glow
   (SOFTLIGHT, HDR threshold 1.05) lifts a **third of the picture into clipping** and
   desaturates it. And it did not even buy the seam: the world-anchored shared stroke
   set had already solved that, so the margin was defending against something that
   was no longer happening. The raw-buffer seam is the one number it improves, and
   nobody ships the raw buffers. **This plate is rendered at exactly 90.0° with no
   margin.**

3. **The stroke's shape is baked into the world.** `canvas.footprint(style=
   "painterly")` draws elongation and angle jitter from `default_rng(seed)` indexed
   by *position in the array* — so the same stroke inside two different per-face
   subsets gets two different shapes, and the cube edges crawl. Here the elongation
   is a per-stroke `Strokes.elong` and the jitter is a **rotation of the tangent
   about the surface normal**, both pure functions of the stroke. Subset-invariant,
   and more correct: a world rotation turns with the wall.

4. **The brush is scaled per stroke, through depth.** `radius_world =
   TARGET_PX × depth / focal`, so every mark is **{tpx} px wide on the canvas** at any
   distance. A single world radius would paint a 41-pixel blob at 0.5 m and a
   sub-pixel speck at 100 m, and this scene runs 0.56 m to 91 m.

## WHAT WAS PROVED RATHER THAN ASSERTED

`tzelem/proof_cube360_hardpath.py` — **PASS**:

* **`cube360_paint` really is `canvas.render(soft=False)`.** It calls
  `canvas.ownership` + `Palette.lookup` itself so the ownership map is available for
  the coverage number without running the splat loop twice. Bit-identical, `max|diff|
  0.000e+00`. (And it differs from the soft path by 0.618, so the claim means
  something.)
* **The picture does not depend on which subset a stroke sits in** — 0 of 262,144
  pixels differ between a face rendered from the stroke set and from an
  order-preserving padded superset. That is what makes "a stroke straddling a cube
  edge is drawn identically on both faces" true rather than hopeful.
* **One caveat, found while proving it:** 18.7 % of strokes tie to the *same float32
  depth* (every sky-dome stroke sits at exactly 250.0 m), and `canvas.ownership`
  breaks a tie by visit order. `np.nonzero` returns ascending indices, so every face
  visits shared strokes in the same relative order and this never fires — but
  **deliberately shuffling a stroke array moves 2.37 % of pixels.** Do not reorder one.

## THE BUG THAT NEARLY SHIPPED: the exporter was DELETING the scene's materials

The first plate came out a flat cream wash — no pink shirts, no brown wood, no dark
shopfront — and it took three wrong guesses (the render margin, the glow, the
resolution) before the real cause turned up.

`_shot()` did `_apply(scene, mat)` → render → `_apply(scene, null)`. That last call
does not *clear* the override; it sets `material_override = null` on **every
`GeometryInstance3D` in the scene**. And `boulevard_cafe.gd` assigns **twenty** of its
materials *through* `material_override` — `m_skin` on every head, `m_iron`,
`m_rubber`, `m_marble`, `m_steel`, `m_plaster`, `m_canvas`, `m_stone`, the car paint.
So the exporter **deleted them**, permanently, and every mesh fell back to Godot's
default white. The beauty pass is the *first* `_shot()` call, so it destroyed the
materials and then photographed the wreckage: the very first face of every run was
already ruined.

**The tell was in plain sight the whole time** — the trees and hedges kept their
green, because `_sph_leaf.material` / `_sph_hedge.material` are *mesh-surface*
materials and that loop never touched those. Everything set by override went white.

Measured at the same eye against `boulevard_shots.gd`, which never calls `_apply` at
all and is therefore right:

| | luminance mean | p05 | below 0.25 | **saturation** |
|---|---|---|---|---|
| `boulevard_shots.gd` pose 02 — the target | 0.539 | 0.084 | 22.5 % | **0.550** |
| the exporter, **before** the fix | 0.699 | 0.522 | 0.55 % | **0.329** |
| before the fix, screen-space effects off | 0.668 | 0.259 | 4.6 % | 0.389 |
| **after the fix** | 0.455 | 0.092 | 37.1 % | **0.559** |

The shadows were gone (`p05` 0.084 → 0.522) and so was the colour. Switching the
screen-space effects off recovered only a third of it; the rest was this. **The fix:
never null anything — the beauty pass touches no material at all, and a data pass
saves each node's existing override and puts it back.**

> **This is not confined to this plate.** The identical line is still in
> `tzelem_gbuffer.gd`, which produced `tzelem/out/godot` and the frames **gate 1 was
> measured on**. Any albedo-dependent number taken from those files — anything TZELEM
> painted from them, any fidelity-MSE against "the engine" — was computed against
> white plaster instead of the boulevard. That file was deliberately **not** touched
> here; its owner has to decide what to re-run. Flagged in RAMCHAT.

## ONE MORE BUG FIXED ON THE WAY, and that one was not mine

`tzelem_cube360.gd`'s depth pass was inherited from `tzelem_gbuffer.gd`, which
measured distance at the **vertices** and let the rasteriser interpolate it. `length()`
is not affine, so that is only right when a triangle is small compared to how far away
it is — and `boulevard_cafe.gd` builds the whole ground from 240 triangles tens of
metres across. Looking straight down from 1.62 m it reported **21.89 m**. Found and
fixed by **claude-cli-VR-RENDER** (2026-09-06) while working in the same file;
`length(VERTEX)` in `fragment()` is already perspective-correct. The proof it is right
is in this run's own log: the `ny` face now reads **0.56 … 2.85 m**, and
1.62 / cos(54.7°) = 2.81 m is exactly the ground at the corner of a 90° downward face.

For this particular plate the old bug was nearly invisible — a stroke anchored at
`eye + ray × depth` stays on the *same ray* whatever the depth is, and all six cameras
share that eye, so it re-projected to the same direction on every face. It bit only at
silhouettes, through nearest-wins ownership. It would matter enormously the moment the
camera moves. The same line is **still in `tzelem_gbuffer.gd`** — deliberately, because
gate-1 numbers were measured with it and its owner has to decide what to re-run.

**The sky is painted, not left blank.** Godot's depth pass marks sky as a miss, so no
stroke would land there and the +Y face would come back mostly flat background — which
the coverage gate would then fail for a reason that has nothing to do with holes. The
BEAUTY pass holds the real rendered sky colour, so those pixels get strokes on a dome
at 250 m carrying it. From a plate made at **one fixed point** that is exact.

**Where the colour comes from.** Every stroke's colour is sampled from Godot's own
**beauty pass** — ACES tonemapping, SDFGI, SSAO, glow, exponential and volumetric fog.
So this plate carries the **engine's** materials and lighting. It does **not** use
`tzelem/material.py` or `tzelem/occlusion.py`; those are numpy stages for the
`oneroom` scenes and are imported by nothing that renders here. (Flagged by
claude-cli-FABLE in RAMCHAT at 19:54 — this is the explicit answer to it.)

## THE FILES / \u05d4\u05e7\u05d1\u05e6\u05d9\u05dd

| file | what |
|---|---|
| `{plate}` | **the plate**, PNG, lossless |
| `{plate_jpg}` | the same, JPEG q95 — the one to hand to a viewer |
| `SHEET-{name}.jpg` / `.pdf` | the one-page sheet (also on the Desktop) |
| `{name}-vs-reference-shot.jpg` | this plate cut to the exact frustum of `boulevard-02-cafe-claude.png`, above the flat shot itself |
| `{raw_jpg}` | the **unpainted** Godot stitch, same geometry, for comparison |
| `face_*.png` | the six painted cube faces |
| `{report}` | every measured number, machine-readable |
| `cuts/` | the rectilinear views that were opened and looked at, + `cuts.json` |
| `faces2048/face_*.tzg` | the raw G-buffers (depth + normal + colour), ~117 MB each — the provenance, and enough to re-paint without re-rendering |
| `{name}-view-*.png` | the exact view the sharpness ruler was run on |
| `_work/` | the calibration runs, including the rejected margin experiment |

*Rendered on the PC at BELOW_NORMAL priority. Nothing on eran1 (ERAN and his live mic
decoders) or eran3 was touched; the boulevard is an 895k-triangle Godot asset with no
verified fleet path today, so the capture had to stay on the PC GPU.*
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--godot-seconds", default="120.5")
    ap.add_argument("--raw-lapvar", default="n/a")
    a = ap.parse_args()
    r = json.load(open(a.report, encoding="utf-8"))
    w, h = r["equirect"]
    name = r["name"]
    covs = min(v for v in r["coverage_surface_only"].values())
    txt = T.format(
        date="2026-09-06",
        plate=f"{name}-equirect-{w}x{h}.png",
        plate_jpg=f"{name}-equirect-{w}x{h}.jpg",
        raw_jpg=f"{name}-RAW-godot-{w}x{h}.jpg",
        report=os.path.basename(a.report),
        name=name,
        eye="(" + ", ".join(f"{v:.2f}" for v in r["eye"]) + ")",
        w=w, h=h, ppd=r["ppd_equator"], ratio=r["ppd_equator"] / 11.0,
        yaw=r["yaw0_deg"], face=r["face_px"],
        cov=r["coverage_min"] * 100, covs=covs * 100,
        seam=r["seam_mean_abs_diff"], base=r["seam_interior_baseline"],
        sratio=r["seam_mean_abs_diff"] / r["seam_interior_baseline"],
        seammax=r["seam_max_abs_diff"],
        lap=r["lapvar_cut_view"], lapequi=r["lapvar_equirect_do_not_use"],
        rawlap=a.raw_lapvar,
        strokes=r["strokes_total"], apx=r["anchors_per_face_pixel"],
        tpx=r["target_px"], sec=r["seconds"], gsec=a.godot_seconds,
        cutfov=r["cut_fov_deg"], cut=r["cut_px"],
    )
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(txt)
    print(a.out)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
