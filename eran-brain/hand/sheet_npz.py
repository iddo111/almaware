"""Render a bag of 22-letter pages (ceiling.npz) so a person can LOOK at them.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

A ceiling reached by scattering blobs is not a ceiling worth climbing. The only way to
know which one this is, is to look at it.
"""
from __future__ import annotations

import argparse
import json
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--npz", default=os.path.join(HERE, "ceiling.npz"))
    ap.add_argument("--meta", default=os.path.join(HERE, "..", "eye", "corpus",
                                                   "letters.json"))
    ap.add_argument("--json", default=os.path.join(HERE, "state", "ceiling.json"))
    ap.add_argument("--out", default=os.path.join(HERE, "ceilings.png"))
    a = ap.parse_args(argv)

    d = np.load(a.npz)
    keys = list(d.keys())
    letters = json.load(open(a.meta, encoding="utf-8"))["letters"]
    rows_meta = {}
    if os.path.exists(a.json):
        for r in json.load(open(a.json))["rows"]:
            rows_meta["%dx%d%s" % (r["strokes"], r["points"],
                                   "P" if r["pressure"] else "")] = r

    T, PADX, LAB = 78, 8, 30
    W = PADX * 2 + 240 + 22 * T
    H = 40 + len(keys) * (T + LAB)
    im = Image.new("RGB", (W, H), (255, 255, 255))
    dr = ImageDraw.Draw(im)
    try:
        f = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 15)
        fb = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 17)
    except Exception:                                            # noqa: BLE001
        f = fb = ImageFont.load_default()
    dr.text((PADX, 10), "The CEILING of each pen — Adam straight onto the points, "
                        "no learning rule. This is the best each pen can ever do.",
            font=fb, fill=(20, 20, 30))

    for r, k in enumerate(keys):
        yy = 40 + r * (T + LAB)
        m = rows_meta.get(k, {})
        dr.text((PADX, yy + T // 2 - 8),
                "%-8s cos %.4f  eye %.0f%%  ink %.3f"
                % (k, m.get("cos", 0), 100 * m.get("eye_reads_back", 0),
                   m.get("cover", 0)), font=f, fill=(30, 30, 40))
        page = d[k]
        for i in range(page.shape[0]):
            t = Image.fromarray((255 - (page[i] * 255)).astype(np.uint8)).resize(
                (T - 6, T - 6), Image.LANCZOS)
            im.paste(t, (PADX + 240 + i * T, yy))
        for i, l in enumerate(letters):
            dr.text((PADX + 240 + i * T + 2, yy + T - 4), l["name"][:5], font=f,
                    fill=(140, 140, 155))
    im.save(a.out)
    print("-> %s" % a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
