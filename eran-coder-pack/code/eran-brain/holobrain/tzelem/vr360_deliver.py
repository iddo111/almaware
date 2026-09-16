# -*- coding: utf-8 -*-
"""The contact sheet Iddo actually opens: JPEG + PDF, bright, no raw .html.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

CLICKABLE-ACCESS LAW: a C:\\ or D:\\ path is not a link in his app. So this writes a
JPEG and a PDF and the caller drops them on the Desktop, where he can double-click.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

Image.MAX_IMAGE_PIXELS = None


def _rtl(t: str) -> str:
    """Hebrew for PIL, which has no bidi shaper.

    ImageDraw lays glyphs out left to right, so a correct logical-order Hebrew string
    is DRAWN MIRRORED -- the first render of this sheet said 'ל"ז המלע לש הרכזל'
    where it should have said 'לזכרה של עלמה ז"ל'. Reversing the run before drawing
    puts it right. Getting a memorial line backwards is worse than omitting it, so
    this is not cosmetic.
    """
    return t[::-1]


def _font(size: int):
    for n in ("segoeui.ttf", "arial.ttf", "calibri.ttf"):
        p = os.path.join(r"C:\Windows\Fonts", n)
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def build(measured_json: str, out_stem: str) -> tuple[str, str]:
    m = json.load(open(measured_json, encoding="utf-8"))
    d = os.path.dirname(measured_json)

    W, H = 2000, 2200
    sheet = Image.new("RGB", (W, H), (255, 255, 255))
    dr = ImageDraw.Draw(sheet)
    f_h1, f_h2, f_b, f_s = _font(58), _font(34), _font(26), _font(21)

    dr.text((60, 46), "360 VR PLATE - Rothschild Boulevard, on the median",
            font=f_h1, fill=(15, 15, 20))
    dr.text((60, 118),
            "TZELEM, painted. Equirectangular %s, %.1f pixels per degree at the "
            "equator. MONO - no depth." % (m["equirect_px"], m["ppd_equator"]),
            font=f_h2, fill=(70, 70, 80))

    y = 178
    equi = Image.open(m["equirect_jpg"])
    thumb = equi.resize((1880, 940), Image.LANCZOS)
    sheet.paste(thumb, (60, y))
    dr.rectangle([60, y, 60 + 1880, y + 940], outline=(200, 200, 205), width=2)
    y += 960
    dr.text((60, y), "the whole sphere, unrolled  (centre of the image = world -Z)",
            font=f_s, fill=(120, 120, 130))
    y += 46

    cut = Image.open(m["cut_view_png"]).resize((920, 920), Image.LANCZOS)
    sheet.paste(cut, (60, y))
    dr.rectangle([60, y, 980, y + 920], outline=(200, 200, 205), width=2)
    dr.text((60, y + 928),
            "the RULER'S VIEW: %.0f deg rectilinear, cut from the plate, looking "
            "north up the boulevard" % m["cut_fov_deg"], font=f_s, fill=(120, 120, 130))

    tx = 1030
    ty = y
    rows = [
        ("HEADSET", "HTC Vive gen-1, 1080x1200 per eye, about 11 PPD"),
        ("PLATE", "%s equirectangular = %.1f PPD at the equator" %
         (m["equirect_px"], m["ppd_equator"])),
        ("HEADROOM", "%.1fx the headset. More pixels would buy nothing." %
         (m["ppd_equator"] / 11.0)),
        ("BUILT FROM", "6 cube faces, %d px square, exactly 90.0 deg FOV,"
         % m["face_px"]),
        ("", "one camera origin (%.2f, %.2f, %.2f)" % tuple(m["eye"])),
        ("PAINT", "%s strokes, hard ownership path, %s planted per face" %
         (f"{m['strokes_total']:,}", f"{m['strokes_per_face']:,}")),
        ("COVERAGE", "min %.3f%% across the six faces  (under 99%% = REJECT)" %
         m["coverage_min_pct"]),
        ("SEAM", "%.2f / 255 mean across the 12 cube edges" %
         m["seam_mean_abs_diff_255"]),
        ("", "worst edge %s at %.2f" % (m["seam_worst_edge"]["edge"],
                                        m["seam_worst_edge"]["mean_abs_diff_255"])),
        ("SHARPNESS", "lapvar %.0f on the %.0f deg view" %
         (m["lapvar_rectilinear_view"], m["cut_fov_deg"])),
        ("", "(TZELEM boulevard flat shot 719; the workshop he"),
        ("", " REJECTED 126 - same ruler, sharpness.py)"),
        ("STEREO", "NONE, and not faked. Real 360 stereo needs a"),
        ("", "different eye per column (ODS); TZELEM has one"),
        ("", "pinhole. A fixed IPD offset would inverse the"),
        ("", "depth behind you, which hurts in a headset."),
    ]
    dr.text((tx, ty), "MEASURED", font=f_h2, fill=(15, 15, 20))
    ty += 58
    for k, v in rows:
        if k:
            dr.text((tx, ty), k, font=f_b, fill=(150, 60, 40))
        dr.text((tx + 190, ty), v, font=f_b, fill=(35, 35, 45))
        ty += 40

    ty += 20
    dr.text((tx, ty), "HOW TO SEE IT", font=f_h2, fill=(15, 15, 20))
    ty += 58
    for line in ("drag the .jpg into any 360 viewer, or set it as a",
                 "PanoramaSkyMaterial in the alma-vr Godot project",
                 "and put the headset on. It is a still: you may",
                 "turn your head, not walk."):
        dr.text((tx, ty), line, font=f_b, fill=(35, 35, 45))
        ty += 40

    foot = "TZELEM / %s  -  alma-vr  -  %s  -  measured %s, %.0f s" % (
        _rtl("צלם"), _rtl("לזכרה של עלמה ז\"ל"), "2026-09-06", m["seconds"])
    dr.text((60, H - 58), foot, font=f_s, fill=(140, 140, 150))

    jpg = out_stem + ".jpg"
    pdf = out_stem + ".pdf"
    sheet.save(jpg, quality=93)
    sheet.save(pdf, "PDF", resolution=150.0)
    return jpg, pdf


if __name__ == "__main__":
    a, b = build(sys.argv[1], sys.argv[2])
    print(a)
    print(b)
