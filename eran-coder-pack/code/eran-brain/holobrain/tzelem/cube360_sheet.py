# -*- coding: utf-8 -*-
"""The one-page sheet for Iddo: JPEG + PDF, bright, no raw .html anywhere.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

Built with PIL directly rather than by rendering HTML in a browser: fewer moving
parts, no headless-Chrome dependency, and the same pixels go into the .jpg and the
.pdf so the two cannot disagree.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

Image.MAX_IMAGE_PIXELS = None

W = 2000
BG = (255, 255, 255)
INK = (24, 24, 28)
GREY = (110, 110, 118)
GOOD = (18, 122, 62)
WARN = (176, 96, 8)


def font(size: int, bold: bool = False):
    for name in (("seguisb.ttf", "segoeuib.ttf", "arialbd.ttf") if bold
                 else ("segoeui.ttf", "arial.ttf")):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def fit(path: str, w: int) -> Image.Image:
    im = Image.open(path).convert("RGB")
    h = max(1, round(im.height * w / im.width))
    return im.resize((w, h), Image.LANCZOS)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True)
    ap.add_argument("--plate", required=True)
    ap.add_argument("--cuts", required=True, help="folder of cut-*.png")
    ap.add_argument("--out", required=True, help="output stem, no extension")
    a = ap.parse_args()
    r = json.load(open(a.report, encoding="utf-8"))

    pad = 48
    inner = W - 2 * pad
    hero = fit(a.plate, inner)
    thumb_w = (inner - 2 * 16) // 3
    picks = [("cut-centre.png", "CENTRE -- what a viewer opens on (90 deg)"),
             ("cut-edge-45.png", "ACROSS A CUBE EDGE -- a seam would run down"),
             ("cut-nadir.png", "NADIR -- straight down, the equirect pole")]
    thumbs = []
    for fn, cap in picks:
        p = os.path.join(a.cuts, fn)
        if os.path.exists(p):
            thumbs.append((fit(p, thumb_w), cap))

    f_h1, f_h2, f_b, f_s = font(52, True), font(30, True), font(25), font(21)
    th = max((t.height for t, _ in thumbs), default=0)
    H = pad + 70 + 44 + hero.height + 34 + (th + 62 if thumbs else 0) + 700
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    y = pad

    d.text((pad, y), "CAFE CLAUDE IN 360 -- a VR plate", INK, f_h1)
    y += 62
    d.text((pad, y), "Rothschild Boulevard, standing at the cafe tables. "
                     "Equirectangular, mono, for the HTC Vive.", GREY, f_b)
    y += 52
    img.paste(hero, (pad, y))
    d.rectangle([pad, y, pad + hero.width - 1, y + hero.height - 1],
                outline=(210, 210, 216))
    y += hero.height + 14
    d.text((pad, y), f"{r['equirect'][0]} x {r['equirect'][1]} equirectangular  --  "
                     f"{r['ppd_equator']:.1f} pixels per degree at the equator",
           GREY, f_s)
    y += 40

    for i, (t, cap) in enumerate(thumbs):
        x = pad + i * (thumb_w + 16)
        img.paste(t, (x, y))
        d.rectangle([x, y, x + t.width - 1, y + t.height - 1],
                    outline=(210, 210, 216))
        d.text((x, y + t.height + 8), cap, GREY, f_s)
    if thumbs:
        y += th + 54

    d.line([pad, y, W - pad, y], fill=(220, 220, 226), width=2)
    y += 26
    d.text((pad, y), "MEASURED", INK, f_h2)
    y += 44

    cov = r["coverage_min"] * 100
    seam = r["seam_mean_abs_diff"]
    base = r["seam_interior_baseline"]
    lines = [
        (f"coverage, worst of the six faces", f"{cov:.3f} %",
         "floor is 99 %; below that the plate has holes showing background",
         GOOD if cov >= 99 else WARN),
        (f"seam, mean |difference| across every face boundary", f"{seam:.4f}",
         f"the picture's own adjacent-pixel texture is {base:.4f}, "
         f"so the seam is {seam/base:.2f}x that -- not a line, just the grain",
         GOOD if seam <= 2.0 * base else WARN),
        ("sharpness (Laplacian variance, sharpen/sharpness.py)",
         f"{r['lapvar_cut_view']:.0f}",
         f"measured on a {r['cut_fov_deg']:.0f}-degree RECTILINEAR cut at "
         f"{r['cut_px']} px, never on the equirect (the poles would flatter it)",
         GOOD),
        ("pixels per degree at the equator", f"{r['ppd_equator']:.1f}",
         f"the HTC Vive gen-1 shows about 11, so this is "
         f"{r['ppd_equator']/11.0:.1f}x its glass"
         + ("" if r["ppd_equator"] >= 11 else " -- BELOW the headset"),
         GOOD if r["ppd_equator"] >= 11 else WARN),
        ("brushstrokes, world-anchored", f"{r['strokes_total']:,}",
         f"{r['anchors_per_face_pixel']:.2f} per face pixel, "
         f"every mark {r['target_px']} px wide on the canvas", GOOD),
        ("compositor", "HARD", "nearest-wins ownership, no blending -- the fix "
         "that took the workshop 124 -> 465 on 2026-09-06", GOOD),
        ("stereo", "NONE -- MONO", "real panoramic stereo needs omni-directional "
         "stereo; nothing here does that, and faking it inverts depth behind you",
         WARN),
    ]
    # the note column WRAPS. On the first build it ran off the right edge and the
    # ends of three sentences were simply not on the page.
    import textwrap
    f_n = font(19)
    note_x = pad + 1120
    wrap_chars = 62
    for label, value, note, col in lines:
        d.text((pad, y), label, INK, f_b)
        d.text((pad + 880, y), value, col, font(25, True))
        parts = textwrap.wrap(note, wrap_chars) or [""]
        for i, ln in enumerate(parts[:2]):
            d.text((note_x, y + 2 + i * 22), ln, GREY, f_n)
        y += 46 if len(parts) < 2 else 52

    y += 8
    d.line([pad, y, W - pad, y], fill=(220, 220, 226), width=2)
    y += 22
    d.text((pad, y), "HOW TO SEE IT:  open the .jpg in any 360 viewer and it will "
                     "wrap correctly -- it is a standard 2:1 equirectangular plate.",
           GREY, f_s)
    y += 30
    d.text((pad, y), "The centre of the image is the direction the shot list already "
                     "stands a person at, so a viewer opens looking at the cafe.",
           GREY, f_s)
    y += 38
    d.text((pad, y), "FOUND WHILE MAKING THIS:  the G-buffer exporter was DELETING "
                     "the boulevard's materials before photographing it.", INK,
           font(23, True))
    y += 30
    d.text((pad, y), "It nulled material_override on every mesh to \"clear\" its own "
                     "override -- but boulevard_cafe.gd assigns 20 of its materials "
                     "THAT WAY.", GREY, f_s)
    y += 28
    d.text((pad, y), "Skin, wood, iron, plaster, marble all fell back to white; only "
                     "the trees survived, because their material is on the mesh. "
                     "Saturation 0.33 -> 0.56.", GREY, f_s)
    y += 28
    d.text((pad, y), "The same line is still in tzelem_gbuffer.gd, so every .tzg the "
                     "boulevard has exported -- gate 1's frames included -- has the "
                     "wrong colour in it.", GREY, f_s)

    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
    img.save(a.out + ".jpg", quality=93, subsampling=0)
    img.save(a.out + ".pdf", "PDF", resolution=150.0)
    print(a.out + ".jpg")
    print(a.out + ".pdf")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
