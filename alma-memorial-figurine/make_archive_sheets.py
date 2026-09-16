import json
import math
import gc
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


ARCHIVE = Path(
    r"C:\Users\<user>\.grok\worktrees\claude"
    r"\subagent-019f700d-e1cb-7283-8d9c-b23b01b668ce"
    r"\archive\_pages_stage\iddoperez-alma"
)
SOURCE = ARCHIVE / "thumbs"
ROTATIONS = ARCHIVE / "_rotation_cache.json"
OUTPUT = Path(__file__).resolve().parent / "review" / "archive_sheets"

COLS = 10
ROWS = 10
PER_SHEET = COLS * ROWS
THUMB_W = 240
THUMB_H = 200
LABEL_H = 28
MARGIN = 8


def load_font(size: int):
    for candidate in (
        Path(r"C:\Windows\Fonts\arial.ttf"),
        Path(r"C:\Windows\Fonts\segoeui.ttf"),
    ):
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


rotation_data = json.loads(ROTATIONS.read_text(encoding="utf-8"))
files = sorted(
    p for p in SOURCE.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"}
)
font = load_font(16)
OUTPUT.mkdir(parents=True, exist_ok=True)

sheet_w = MARGIN + COLS * (THUMB_W + MARGIN)
sheet_h = MARGIN + ROWS * (THUMB_H + LABEL_H + MARGIN)

for sheet_number in range(math.ceil(len(files) / PER_SHEET)):
    output = OUTPUT / f"alma_archive_{sheet_number + 1:02d}.jpg"
    if output.exists() and output.stat().st_size > 0:
        continue
    page_files = files[sheet_number * PER_SHEET : (sheet_number + 1) * PER_SHEET]
    sheet = Image.new("RGB", (sheet_w, sheet_h), "#202124")
    draw = ImageDraw.Draw(sheet)
    for index, path in enumerate(page_files):
        col, row = index % COLS, index // COLS
        x = MARGIN + col * (THUMB_W + MARGIN)
        y = MARGIN + row * (THUMB_H + LABEL_H + MARGIN)
        try:
            with Image.open(path) as source:
                image = ImageOps.exif_transpose(source).convert("RGB")
                angle = rotation_data.get(path.name, {}).get("best_rotation", 0)
                if angle:
                    rotated = image.rotate(-angle, expand=True)
                    image.close()
                    image = rotated
                fitted = ImageOps.contain(image, (THUMB_W, THUMB_H))
                image.close()
        except Exception as exc:
            fitted = Image.new("RGB", (THUMB_W, THUMB_H), "#550000")
            print(f"SKIP {path}: {exc}", flush=True)
        tile = Image.new("RGB", (THUMB_W, THUMB_H), "#111111")
        tile.paste(
            fitted,
            ((THUMB_W - fitted.width) // 2, (THUMB_H - fitted.height) // 2),
        )
        sheet.paste(tile, (x, y))
        draw.text((x, y + THUMB_H + 4), path.stem, font=font, fill="#ffffff")
        fitted.close()
        tile.close()
    sheet.save(output, quality=90, optimize=True)
    sheet.close()
    del draw
    gc.collect()
    print(output, flush=True)
