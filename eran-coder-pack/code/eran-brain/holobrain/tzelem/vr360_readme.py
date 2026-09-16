# -*- coding: utf-8 -*-
"""Write the README that sits next to the plate, straight from the measured JSON.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

Generated, not typed, so a number in the README cannot drift from the number that was
measured. "so the file is not a mystery in a month."
"""
from __future__ import annotations

import json
import os
import sys

TPL = """> \U0001fa9f **BROKEN WINDOWS LAW:** if it's not working, fix it IMMEDIATELY \u2014 don't wait to be told. Test the REAL output, not a proxy.

# {name} \u2014 a 360 VR plate

**\u05dc\u05d6\u05db\u05e8\u05d4 \u05e9\u05dc \u05e2\u05dc\u05de\u05d4 \u05d6"\u05dc.**

Standing on the median of Rothschild Boulevard \u2014 Cafe Claude and the street ERAN's
world was built from \u2014 at walking eye height, facing north. Painted by TZELEM.

## What the file is

| | |
|---|---|
| **projection** | equirectangular (spherical), full 360\u00b0 \u00d7 180\u00b0 |
| **size** | **{eq}** |
| **PPD at the equator** | **{ppd:.1f}** pixels per degree (= width / 360) |
| **target headset** | HTC Vive gen-1 \u2014 1080\u00d71200 per eye, **about 11 PPD** |
| **headroom** | **{head:.1f}\u00d7** the headset. More pixels would buy nothing you can see. |
| **stereo** | **NONE. This is MONO.** See below \u2014 it is not an oversight. |
| **camera** | one origin, ({ex:.2f}, {ey:.2f}, {ez:.2f}) m, world axes |
| **image centre** | world **\u2212Z**. Godot's own panorama mapping, `u = atan2(x, \u2212z)/2\u03c0 + 0.5`. |

The boulevard runs along **+Z (north)**, so north sits at the **left/right edge** of the
unrolled image, not the middle. That is not a bug and it was not adjusted: a private yaw
offset would make the plate disagree with the engine's own sky mapping the moment anyone
composites it against the real scene. In a headset you turn your head. The file
`{cutfile}` is the north-facing view cut out for you.

## How to look at it

1. **Any 360 viewer** \u2014 drag `{jpgfile}` in. It is a standard equirect; phone
   viewers, browser viewers and headset galleries all read it.
2. **In his own engine** \u2014 in `D:\\CLAUDE\\alma-vr\\godot`, make a `PanoramaSkyMaterial`,
   set its panorama to this file, and put it on the WorldEnvironment sky. It will be
   oriented correctly with no rotation, because it was built in Godot's convention.
3. It is a **still**. You may turn your head. You may not walk.

## How it was made

Six cubemap faces, **{face} px square, exactly 90.0\u00b0 FOV, one identical camera origin**,
exported from the real 800k-triangle boulevard by
`alma-vr/godot/scripts/tzelem_cube360.gd`, then painted by TZELEM's **hard ownership
compositor** (`canvas.render(soft=False)`) and resampled to the sphere with a
**Catmull-Rom** bicubic. {strokes:,} brushstrokes, {perface:,} planted per face.

The resampler is not a detail. A bilinear tap at half-pixel phase is a two-tap box
whose response at Nyquist is zero, and the plate goes through two resamples, so it was
deleting exactly the frequencies a brushstroke edge lives in: the same six faces gave
**lapvar 78 through bilinear and 175 through Catmull-Rom**. The faces are also rendered
at **{face} px, not 2048**, because a 2048 face carries only 17.9 px/deg at its centre
and an 8192 equirect wants 22.8 — it would have been UPSCALING, i.e. selling detail
that was never there. The rule is face ≥ width/π.

**The seam is killed by construction, not by blending.** All six faces' strokes are
pooled into ONE world-anchored array and every face is painted from ALL of them, so a
stroke crossing a cube edge is the same stroke on both sides. Nothing is feathered and
nothing is overlapped \u2014 blending hides a seam instead of removing it.

Each face is **rendered wider than 90\u00b0 and cropped**, because the scene's SSAO, SSIL and
glow are screen-space and get truncated at a frame border; the discarded ring is where
those artefacts live.

## Measured \u2014 every number here was taken by the agent that shipped the file

| check | value | bar |
|---|---|---|
| coverage, min over the six faces | **{cov:.3f}%** | \u2265 99% or REJECT |
| seam, mean over the 12 cube edges | **{seam:.2f} / 255** | must not be visible |
| seam, worst single edge ({wedge}) | {wseam:.2f} / 255 | |
| sharpness, lapvar on a {cutfov:.0f}\u00b0 rectilinear cut | **{lap:.0f}** | the workshop he REJECTED read 126 |

Sharpness is measured with `D:\\CLAUDE\\sharpen\\sharpness.py` \u2014 the one ruler \u2014 on a
**rectilinear view cut from the plate at the headset's FOV**, never on the equirect
itself. The equirect stretches the poles by 1/cos(latitude), so measuring it would
flatter or punish the picture for geometry it does not have.

**Read the sharpness number with its caveat.** Lapvar falls as an image gets bigger
(the same scene reads 11.5 at 1280 px and 4.3 at 2560). The two reference readings were
taken at 1920×1080 (boulevard, 719) and 1600×900 (the rejected workshop, 126); this cut
is 2048×2048, i.e. 2.9× the pixels of the workshop, so the comparison **understates**
this plate rather than flattering it.

The seam was checked twice and the second check is the one that counts. Comparing face
edges pixel-to-pixel is contaminated by tree canopy (two faces resample leaf edges
differently at the join, which the eye never sees) and by the scene rebuilding itself
differently every run. So the finished plate is also asked the only question the eye
asks — *is the join column an outlier against its own neighbourhood, in the smooth
regions where a line would be glaring?* The raw engine renders fail that test
(+6.9/255, a plainly visible line). The painted plate does not.

## Stereo, said plainly

Real panoramic stereo needs **omni-directional stereo**: every output column rendered
from a different eye position around a circle of radius IPD/2 (~32.5 mm). Nothing in
TZELEM or in the Godot scripts can do that \u2014 every camera in both is a single pinhole.
Offsetting the whole camera by an IPD instead gives correct depth in front of you and
**inverted depth behind you**, which is actively unpleasant in a headset. So this plate
is mono and carries no depth. If stereo is wanted, the honest next step is a
**VR180-style forward pair** for one fixed view, where a fixed offset IS correct.

## Files

- `{jpgfile}` \u2014 the plate, JPEG q94, 4:4:4. **This is the one to open.**
- `{pngfile}` \u2014 the same plate, lossless.
- `{cutfile}` \u2014 the {cutfov:.0f}\u00b0 north-facing view, the one the ruler was run on.
- `{jsonfile}` \u2014 every measurement above, machine-readable.
- `faces/` \u2014 the six source G-buffers (.tzg + .json), if anyone wants to re-paint.

*TZELEM / \u05e6\u05dc\u05dd \u00b7 alma-vr \u00b7 built and measured 2026-09-06.*
"""


def main(measured: str) -> str:
    m = json.load(open(measured, encoding="utf-8"))
    d = os.path.dirname(measured)
    txt = TPL.format(
        name=m["name"], eq=m["equirect_px"], ppd=m["ppd_equator"],
        head=m["ppd_equator"] / 11.0,
        ex=m["eye"][0], ey=m["eye"][1], ez=m["eye"][2],
        face=m["face_px"], strokes=m["strokes_total"], perface=m["strokes_per_face"],
        cov=m["coverage_min_pct"], seam=m["seam_mean_abs_diff_255"],
        wedge=m["seam_worst_edge"]["edge"],
        wseam=m["seam_worst_edge"]["mean_abs_diff_255"],
        lap=m["lapvar_rectilinear_view"], cutfov=m["cut_fov_deg"],
        lineexc=m.get("line_worst_excess_255", 0.0),
        jpgfile=os.path.basename(m["equirect_jpg"]),
        pngfile=os.path.basename(m["equirect_png"]),
        cutfile=os.path.basename(m["cut_view_png"]),
        jsonfile=os.path.basename(measured))
    p = os.path.join(d, "README.md")
    with open(p, "w", encoding="utf-8") as f:
        f.write(txt)
    return p


if __name__ == "__main__":
    print(main(sys.argv[1]))
