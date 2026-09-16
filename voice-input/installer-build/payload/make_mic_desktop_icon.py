"""Generate a clear microphone-shaped desktop icon (.ico) for launching the Hebrew mic.
Bright/light per Iddo's preference: white card, teal mic glyph. 
"""
from PIL import Image, ImageDraw
import os

S = 256
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# bright white rounded card
d.rounded_rectangle([8, 8, S - 8, S - 8], radius=52,
                    fill=(255, 255, 255, 255), outline=(221, 230, 241, 255), width=3)

teal = (15, 182, 196, 255)
teal_dk = (8, 129, 140, 255)
cx = S // 2

# mic capsule (rounded vertical pill)
cap_w, cap_top, cap_bot = 56, 60, 150
d.rounded_rectangle([cx - cap_w // 2, cap_top, cx + cap_w // 2, cap_bot],
                    radius=cap_w // 2, fill=teal)
# capsule grille lines (white)
for gy in range(cap_top + 18, cap_bot - 8, 18):
    d.line([cx - cap_w // 2 + 12, gy, cx + cap_w // 2 - 12, gy], fill=(255, 255, 255, 200), width=4)

# the U-shaped cradle (arc) around the capsule
d.arc([cx - 58, cap_top + 22, cx + 58, cap_bot + 30], start=20, end=160,
      fill=teal_dk, width=11)

# stand + base
d.line([cx, cap_bot + 30, cx, 198], fill=teal_dk, width=11)
d.line([cx - 38, 200, cx + 38, 200], fill=teal_dk, width=11)

# little red "live" dot top-right
d.ellipse([S - 56, 24, S - 30, 50], fill=(239, 68, 68, 255))

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mic.ico")
img.save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("ICON:", out)
