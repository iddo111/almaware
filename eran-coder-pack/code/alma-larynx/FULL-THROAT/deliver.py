# -*- coding: utf-8 -*-
"""Put the throat sheets on Iddo's Desktop as JPEG + PDF. Never a raw .html."""
import os
from PIL import Image

DESK = r"C:\Users\<user>\Desktop"
SRC = [
    (r"D:\CLAUDE\alma-larynx\FULL-THROAT\THE-LOOP.png", "ERAN-THROAT-1-the-loop"),
    (r"D:\CLAUDE\alma-larynx\FULL-THROAT\SCAFFOLD-what-to-print.png", "ERAN-THROAT-2-what-to-print"),
]

pages = []
for src, name in SRC:
    im = Image.open(src).convert("RGB")
    # white matte, a little breathing room
    pad = 40
    canvas = Image.new("RGB", (im.width + 2 * pad, im.height + 2 * pad), "white")
    canvas.paste(im, (pad, pad))
    jpg = os.path.join(DESK, name + ".jpg")
    canvas.save(jpg, "JPEG", quality=93, optimize=True)
    print("jpg :", jpg, canvas.size)
    pages.append(canvas)

pdf = os.path.join(DESK, "ERAN-FULL-SILICONE-THROAT-CORRECTED.pdf")
pages[0].save(pdf, "PDF", resolution=150, save_all=True, append_images=pages[1:])
print("pdf :", pdf, "pages:", len(pages))
