from PIL import Image, ImageDraw
from pathlib import Path

OUT = Path(r"D:\NEWCLAUDE\EMDR\emdr.ico")
size = 256
img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
# red SOS circle
d.ellipse((8, 8, size - 8, size - 8), fill=(160, 10, 10, 255), outline=(40, 0, 0, 255), width=6)
# small white orb (the EMDR point)
orb_r = 28
cx, cy = size // 2 + 50, size // 2
d.ellipse((cx - orb_r, cy - orb_r, cx + orb_r, cy + orb_r), fill=(255, 245, 220, 255), outline=(80, 40, 0, 255), width=3)
# subtle sweep trail dots
for i, dx in enumerate((-60, -30, 0, 30, 60)):
    a = 60 + i * 30
    r = 10
    d.ellipse((cx + dx - r, cy - r, cx + dx + r, cy + r), fill=(255, 245, 220, a))
# SOS text
try:
    from PIL import ImageFont
    font = ImageFont.truetype("arialbd.ttf", 54)
except Exception:
    font = None
txt = "SOS"
if font:
    bbox = d.textbbox((0, 0), txt, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text((size // 2 - w // 2 - 40, size // 2 - h // 2 - 4), txt, fill=(255, 255, 255, 255), font=font)
img.save(OUT, sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
print(f"icon written: {OUT}  exists={OUT.exists()}  size={OUT.stat().st_size}")
