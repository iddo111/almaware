# -*- coding: utf-8 -*-
"""
> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

THE COMPARISON SHEET: before and after, with the number under each panel and a
1:1 crop beside it, because a downscaled thumbnail of a sharpness claim is a
contradiction in terms.

Deliverable format is JPEG (+PDF), never a raw .html -- D:\\CLAUDE\\CLAUDE.md.
"""
from __future__ import annotations

import argparse
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")

from sharpness import lapvar_file                          # noqa: E402

PANEL_W = 900
CROP = 380


def font(sz):
    for p in (r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\arial.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if os.path.isfile(p):
            return ImageFont.truetype(p, sz)
    return ImageFont.load_default()


def panel(path: str, title: str, note: str) -> Image.Image:
    im = Image.open(path).convert("RGB")
    lv = lapvar_file(path)
    w, h = im.size
    small = im.resize((PANEL_W, round(h * PANEL_W / w)), Image.LANCZOS)
    cx, cy = w // 2, int(h * 0.52)
    crop = im.crop((max(0, cx - CROP // 2), max(0, cy - CROP // 2),
                    min(w, cx + CROP // 2), min(h, cy + CROP // 2)))
    out = Image.new("RGB", (PANEL_W + CROP + 24, max(small.height, CROP) + 96),
                    (250, 249, 246))
    out.paste(small, (0, 74))
    out.paste(crop, (PANEL_W + 24, 74))
    d = ImageDraw.Draw(out)
    d.text((4, 6), title, font=font(28), fill=(20, 20, 24))
    d.text((4, 42), f"Laplacian variance {lv:,.1f}     {note}",
           font=font(20), fill=(90, 90, 96))
    d.text((PANEL_W + 24, 48), "1:1 crop, no resampling",
           font=font(15), fill=(120, 120, 126))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", default="TZELEM / the workshop at night")
    ap.add_argument("panels", nargs="+",
                    help="path::title::note triples")
    a = ap.parse_args()

    ps = []
    for spec in a.panels:
        bits = spec.split("::")
        ps.append(panel(bits[0], bits[1], bits[2] if len(bits) > 2 else ""))
    W = max(p.width for p in ps) + 32
    H = sum(p.height for p in ps) + 90 + 16 * len(ps)
    sheet = Image.new("RGB", (W, H), (250, 249, 246))
    d = ImageDraw.Draw(sheet)
    d.text((16, 16), a.title, font=font(38), fill=(16, 16, 20))
    d.text((16, 62), "ruler: Laplacian variance, greyscale, long edge capped at "
                     "2400 px.  reference: his document pages 1,868-4,038  |  "
                     "TZELEM boulevard 719  |  the workshop he rejected 126",
           font=font(17), fill=(110, 110, 118))
    y = 90
    for p in ps:
        sheet.paste(p, (16, y))
        y += p.height + 16
    sheet.save(a.out, quality=94, subsampling=0)
    print("wrote " + a.out)
    pdf = os.path.splitext(a.out)[0] + ".pdf"
    sheet.save(pdf, "PDF", resolution=150.0)
    print("wrote " + pdf)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
