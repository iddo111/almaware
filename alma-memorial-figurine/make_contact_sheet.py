import argparse
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parent

THUMB_W, THUMB_H = 360, 300
LABEL_H = 44
COLS = 4
MARGIN = 20
BG = "#202124"
FG = "#ffffff"


def load_font(size: int):
    candidates = [
        Path(r"C:\Windows\Fonts\arial.ttf"),
        Path(r"C:\Windows\Fonts\segoeui.ttf"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


parser = argparse.ArgumentParser()
parser.add_argument("--source", type=Path, default=ROOT / "private_sources")
parser.add_argument(
    "--output",
    type=Path,
    default=ROOT / "review" / "alma_labelled_contact_sheet.jpg",
)
args = parser.parse_args()

images = sorted(
    p for p in args.source.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"}
)
rows = (len(images) + COLS - 1) // COLS
sheet_w = MARGIN + COLS * (THUMB_W + MARGIN)
sheet_h = MARGIN + rows * (THUMB_H + LABEL_H + MARGIN)
sheet = Image.new("RGB", (sheet_w, sheet_h), BG)
draw = ImageDraw.Draw(sheet)
font = load_font(22)

for index, path in enumerate(images):
    col, row = index % COLS, index // COLS
    x = MARGIN + col * (THUMB_W + MARGIN)
    y = MARGIN + row * (THUMB_H + LABEL_H + MARGIN)
    with Image.open(path) as original:
        image = ImageOps.exif_transpose(original).convert("RGB")
        fitted = ImageOps.contain(image, (THUMB_W, THUMB_H))
    tile = Image.new("RGB", (THUMB_W, THUMB_H), "#111111")
    tile.paste(
        fitted,
        ((THUMB_W - fitted.width) // 2, (THUMB_H - fitted.height) // 2),
    )
    sheet.paste(tile, (x, y))
    draw.text((x, y + THUMB_H + 8), path.name, font=font, fill=FG)

args.output.parent.mkdir(parents=True, exist_ok=True)
sheet.save(args.output, quality=92, optimize=True)
print(args.output)
