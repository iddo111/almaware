import csv
from pathlib import Path

from PIL import ExifTags, Image


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "private_sources"
OUTPUT = ROOT / "review" / "labelled_sources_inventory.csv"

rows = []
for path in sorted(SOURCE.iterdir()):
    if path.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
        continue
    with Image.open(path) as image:
        exif = {
            ExifTags.TAGS.get(key, key): value
            for key, value in image.getexif().items()
        }
        rows.append(
            {
                "file": path.name,
                "width": image.width,
                "height": image.height,
                "date_time_original": exif.get(
                    "DateTimeOriginal", exif.get("DateTime", "")
                ),
                "camera_make": exif.get("Make", ""),
                "camera_model": exif.get("Model", ""),
            }
        )

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
with OUTPUT.open("w", newline="", encoding="utf-8-sig") as handle:
    writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)

for row in rows:
    print(
        f"{row['file']}\t{row['width']}x{row['height']}\t"
        f"{row['date_time_original']}\t"
        f"{row['camera_make']} {row['camera_model']}".rstrip()
    )
