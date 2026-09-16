#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""claude_plush.py -- the cute orange one.

Iddo, 2026-08-27 07:05: "התכוונתי הכתום החמוד לא התפוז המכני הרע."
An ORIGINAL soft plush character in Claude's coral -- not a copy of Anthropic's
official plush, which is theirs. Flat shapes and one seam, so it screen-prints.
"""
from PIL import Image, ImageDraw

CORAL = (214, 111, 78, 255)
CORAL_D = (176, 82, 54, 255)
CORAL_L = (238, 160, 128, 255)
INK = (28, 26, 30, 255)
CREAM = (252, 248, 242, 255)


def plush(size=1400):
    S = size
    img = Image.new("RGBA", (S, int(S * 1.06)), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    u = S / 1400.0

    def R(x, y, w, h, r, fill):
        d.rounded_rectangle([x * u, y * u, (x + w) * u, (y + h) * u],
                            radius=r * u, fill=fill)

    def C(cx, cy, r, fill):
        d.ellipse([(cx - r) * u, (cy - r) * u, (cx + r) * u, (cy + r) * u], fill=fill)

    # --- little legs, behind the body
    R(470, 1150, 170, 190, 85, CORAL_D)
    R(760, 1150, 170, 190, 85, CORAL_D)

    # --- arms, behind the body
    C(345, 900, 118, CORAL_D)
    C(1055, 900, 118, CORAL_D)

    # --- ears: soft plush nubs
    C(430, 355, 128, CORAL)
    C(970, 355, 128, CORAL)
    C(430, 355, 66, CORAL_L)
    C(970, 355, 66, CORAL_L)

    # --- body: one round pillow
    R(300, 330, 800, 900, 380, CORAL)

    # --- belly patch, lighter, the way a plush is sewn
    d.ellipse([470 * u, 800 * u, 930 * u, 1170 * u], fill=CORAL_L)

    # --- the seam
    for k in range(11):
        yy = 372 + k * 26
        d.line([(700 - 6) * u, yy * u, (700 + 6) * u, (yy + 14) * u],
               fill=CORAL_D, width=int(6 * u) or 1)

    # --- face
    C(578, 690, 62, INK)
    C(822, 690, 62, INK)
    C(600, 668, 22, CREAM)
    C(844, 668, 22, CREAM)
    # cheeks
    C(455, 790, 52, (233, 138, 108, 160))
    C(945, 790, 52, (233, 138, 108, 160))
    # a small, closed, contented smile
    d.arc([640 * u, 760 * u, 760 * u, 850 * u], 20, 160, fill=INK, width=int(15 * u) or 2)
    return img


if __name__ == "__main__":
    p = plush()
    p.save("claude-plush.png")
    bg = Image.new("RGB", p.size, (255, 255, 255)); bg.paste(p, (0, 0), p)
    bg.save("claude-plush-proof.jpg", quality=94)
    print("plush drawn", p.size)
