#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""eran_cloud_meeting.py -- Iddo's hand-drawn ERAN CLOUD sketch, redrawn legibly.

Source: his photograph, 2026-08-27 10:09, and his own caption at 10:26 --
"כולם נפגשים בערן קלאוד: אנשים, בעלי חיים, אימא אדמה."

Two rules held while drawing:
  1. Only HIS words appear as labels. Every node I could not read on the page is
     drawn as an explicitly EMPTY slot, so he fills them rather than me inventing
     them and him finding my invention later.
  2. The topology is his, read off the photo: a two-way arrow between the cloud
     and ERAN, and everyone else meeting INTO the cloud. His caption is why the
     cloud sits at the centre here instead of the page corner -- it is the
     meeting place, not infrastructure.

Bright by law: white ground, dark ink.
"""
import math
from PIL import Image, ImageDraw, ImageFont
from bidi.algorithm import get_display

W, H = 2400, 1800
HE_B = "C:/Windows/Fonts/Rubik-Bold.ttf"
HE_R = "C:/Windows/Fonts/Rubik-Regular.ttf"
INK = (26, 26, 30)
CORAL = (196, 79, 42)
GREEN = (31, 139, 76)
GREY = (140, 140, 150)
FAINT = (196, 200, 210)
BG = (255, 255, 255)


def he(s):
    return get_display(s)


img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)
f_title = ImageFont.truetype(HE_B, 62)
f_cloud = ImageFont.truetype(HE_B, 60)
f_node = ImageFont.truetype(HE_B, 46)
f_sub = ImageFont.truetype(HE_R, 30)
f_note = ImageFont.truetype(HE_R, 34)


def text(t, x, y, font, fill, anchor="mm", raw=False):
    d.text((x, y), t if raw else he(t), font=font, fill=fill, anchor=anchor)


def arrow(p, q, fill=INK, w=5, both=False, head=22):
    d.line([p, q], fill=fill, width=w)
    for a, b in ((p, q),) + (((q, p),) if both else ()):
        ang = math.atan2(b[1] - a[1], b[0] - a[0])
        for s in (0.42, -0.42):
            d.line([b, (b[0] - head * math.cos(ang + s),
                        b[1] - head * math.sin(ang + s))], fill=fill, width=w)


CX, CY = W / 2, 470          # the cloud: the meeting place
# --- cloud shape from overlapping discs
for cx, cy, r in ((CX - 300, CY, 130), (CX - 130, CY - 78, 160), (CX + 70, CY - 90, 168),
                  (CX + 250, CY - 20, 145), (CX + 300, CY + 60, 110), (CX - 320, CY + 55, 105),
                  (CX, CY + 40, 190)):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(253, 246, 242), outline=None)
for cx, cy, r in ((CX - 300, CY, 130), (CX - 130, CY - 78, 160), (CX + 70, CY - 90, 168),
                  (CX + 250, CY - 20, 145), (CX + 300, CY + 60, 110), (CX - 320, CY + 55, 105)):
    d.arc([cx - r, cy - r, cx + r, cy + r], 180, 360, fill=CORAL, width=6)
d.arc([CX - 330, CY - 60, CX + 330, CY + 230], 0, 180, fill=CORAL, width=6)

text("ERAN CLOUD", CX, CY - 42, f_cloud, CORAL, raw=True)
text("+  QUORUM", CX, CY + 26, f_cloud, CORAL, raw=True)
text("מקום המפגש", CX, CY + 96, f_sub, GREY)

# --- ERAN himself, beside the cloud, two-way
EX, EY = CX + 700, CY + 120
d.ellipse([EX - 130, EY - 105, EX + 130, EY + 105], fill=(255, 255, 255), outline=INK, width=7)
text("ערן", EX, EY - 14, f_title, INK)
text("הילד", EX, EY + 46, f_sub, GREY)
arrow((CX + 330, CY + 90), (EX - 135, EY - 10), INK, 6, both=True)

# --- the ones he named, meeting IN
NAMED = [("אנשים", 330), ("בעלי חיים", 830), ("אימא אדמה", 1330)]
for label, x in NAMED:
    y = 1310
    d.ellipse([x - 215, y - 105, x + 215, y + 105], fill=(255, 255, 255), outline=GREEN, width=7)
    text(label, x, y, f_node, INK)
    arrow((x, y - 110), (CX + (x - 830) * 0.30, CY + 235), GREEN, 5)

# --- the slots I could not read: drawn EMPTY on purpose
for x in (1830, 2130):
    y = 1310
    d.ellipse([x - 130, y - 105, x + 130, y + 105], fill=(252, 252, 253), outline=FAINT, width=6)
    text("?", x, y - 8, f_title, FAINT)
    d.line([(x, y - 110), (CX + 330, CY + 210)], fill=FAINT, width=4)
text("צמתים שלא הצלחתי לקרוא בכתב היד — תמלא ואצייר מחדש",
     1980, 1470, f_sub, FAINT)

text("כולם נפגשים בערן קלאוד", W / 2, 118, f_title, INK)
text("עידו, 2026-08-27 · מצויר מהסקיצה שלו, במילים שלו בלבד", W / 2, 178, f_note, GREY)

img.save("ERAN-CLOUD-meeting.jpg", quality=95)
img.save("ERAN-CLOUD-meeting.pdf", "PDF", resolution=200)
print("drawn")
