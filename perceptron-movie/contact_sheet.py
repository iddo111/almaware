#!/usr/bin/env python3
"""Build contact sheets of every rendered clip so the footage can actually be
looked at before it goes into the film. One frame per clip, 6 across."""
import glob
import math
import os
import subprocess

from PIL import Image, ImageDraw, ImageFont

COLS, ROWS, TW = 6, 6, 340
FONT = "C:/Windows/Fonts/arialbd.ttf"


def main():
    clips = sorted(glob.glob("clips/perceptron/*.mp4"))
    os.makedirs("render/sheet/thumbs", exist_ok=True)
    thumbs = []
    for c in clips:
        t = "render/sheet/thumbs/%s.jpg" % os.path.basename(c)[:-4]
        if not os.path.exists(t):
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "2.2", "-i", c,
                            "-vframes", "1", "-vf", "scale=%d:-2" % TW,
                            "-q:v", "4", t], check=False)
        if os.path.exists(t):
            thumbs.append((os.path.basename(c)[:-10], t))

    per = COLS * ROWS
    sheets = math.ceil(len(thumbs) / per)
    print("%d clips -> %d sheets" % (len(thumbs), sheets))
    try:
        font = ImageFont.truetype(FONT, 17)
    except Exception:
        font = ImageFont.load_default()
    for s in range(sheets):
        batch = thumbs[s * per:(s + 1) * per]
        im0 = Image.open(batch[0][1])
        tw, th = im0.size
        sheet = Image.new("RGB", (COLS * tw, ROWS * th), (12, 12, 12))
        d = ImageDraw.Draw(sheet)
        for i, (name, path) in enumerate(batch):
            x, y = (i % COLS) * tw, (i // COLS) * th
            sheet.paste(Image.open(path).resize((tw, th)), (x, y))
            d.rectangle([x + 3, y + 3, x + 3 + 9 * 10, y + 24], fill=(0, 0, 0))
            d.text((x + 7, y + 5), name, fill=(255, 220, 60), font=font)
        out = "render/sheet/sheet%02d.jpg" % s
        sheet.save(out, quality=82)
        print("wrote", out, sheet.size)


if __name__ == "__main__":
    main()
