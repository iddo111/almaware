"""Generate a clean, recognizable ORANGE microphone .ico (multi-size) for the mic shortcut."""
from PIL import Image, ImageDraw

S = 256
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

# ---- capsule with a vertical gradient (light amber -> deep orange) ----
grad = Image.new("RGBA", (S, S), (0, 0, 0, 0))
gd = ImageDraw.Draw(grad)
top = (0xFF, 0xC4, 0x6B)   # light amber
bot = (0xE2, 0x55, 0x0C)   # deep orange
y0, y1 = 26, 150
for yy in range(y0, y1 + 1):
    t = (yy - y0) / (y1 - y0)
    col = tuple(int(top[i] * (1 - t) + bot[i] * t) for i in range(3)) + (255,)
    gd.line([0, yy, S, yy], fill=col)
mask = Image.new("L", (S, S), 0)
ImageDraw.Draw(mask).rounded_rectangle([96, y0, 160, y1], radius=32, fill=255)
img.paste(grad, (0, 0), mask)

d = ImageDraw.Draw(img)
DARK = (0x3A, 0x28, 0x16, 255)   # warm dark bracket / stand
WHITE = (255, 255, 255, 235)

# soft left highlight on the capsule (sheen)
d.rounded_rectangle([105, 38, 121, 138], radius=8, fill=(255, 255, 255, 80))
# grille lines
for yy in (58, 80, 102, 124):
    d.line([106, yy, 150, yy], fill=WHITE, width=7)

# U-bracket around the lower capsule
d.arc([66, 70, 190, 198], start=0, end=180, fill=DARK, width=13)
# stand
d.line([128, 196, 128, 226], fill=DARK, width=13)
# base
d.rounded_rectangle([96, 224, 160, 240], radius=8, fill=DARK)

img.save(r"D:\CLAUDE\voice-input\mic_icon_orange.ico",
         sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("mic_icon_orange.ico saved")
