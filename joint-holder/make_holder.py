"""make_holder.py — a two-color desk stand for pre-rolls, iddoperez.ai branding.

Iddo, 2026-08-20 10:29-10:31 (via the live mic, reassembled from three garbled
utterances): "תכין לי מחזיק ג'וינטים... משהו מגניב עם כמה צבעים... שה-iddoperez.ai
יהיה בצבע אחד והרקע בצבע אחר" — like a barbershop pole.

DESIGN — a display stand, all additive boxes (no booleans -> watertight, slices
anywhere):
  * base slab with SIX cradle slots formed by seven divider fins + a front lip:
    joints lie in the slots leaning on the back plate, shop-window style;
  * a back plate carrying the raised text "iddoperez.ai" (+1.6 mm proud) built
    from a chunky segment font;
  * barbershop stripes: five raised diagonal-look bars across the base front.

TWO-COLOR PRINT, the way that actually works on the K2 Plus:
  * body.stl  = base + fins + back plate         -> filament A (background)
  * decor.stl = raised text + stripes            -> filament B (the pop color)
  Same coordinate space. In Creality Print: import BOTH in one plate ("add as
  parts"/assembly), assign a CFS slot to each part, Send & Print FROM CREALITY
  PRINT — the documented safe launch path (the API-launch pause scar of 08-11/14
  does not apply to Send & Print; and the screen is alive again as of 10:23).

Print: PLA is fine here (a desk object, no permanent moisture). 0.2 mm layers,
15 % infill, no supports — every feature is vertical or ≤45°.
"""
from __future__ import annotations

import math
import pathlib
import struct

# ------------------------------------------------------------------ params --
BASE_W, BASE_D, BASE_H = 128.0, 46.0, 8.0
PLATE_T, PLATE_H = 6.0, 64.0            # back plate thickness/height
FIN_T, FIN_H, FIN_D = 3.0, 16.0, 30.0   # slot divider fins
SLOTS = 6
LIP_T, LIP_H = 3.0, 10.0                # front lip keeps tips from rolling out
TEXT_RAISE = 1.6                        # how proud the letters sit
STRIPE_RAISE = 1.4

BODY: list[tuple] = []
DECOR: list[tuple] = []


def _tri(buf, a, b, c) -> None:
    u = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    v = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
    ln = math.sqrt(sum(t * t for t in n)) or 1.0
    buf.append(((n[0] / ln, n[1] / ln, n[2] / ln), a, b, c))


def box(buf, x0, y0, z0, w, d, h) -> None:
    x1, y1, z1 = x0 + w, y0 + d, z0 + h
    p = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    faces = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7),
             (0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5),
             (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7)]
    for a, b, c in faces:
        _tri(buf, p[a], p[b], p[c])


# --------------------------------------------------------------- the font --
# Chunky 5-wide × 7-tall cell font, each glyph = filled (col,row,w,h) rects.
# Rows count upward from the glyph baseline. Only the glyphs "iddoperez.a" needs.
F = {
    "i": [(2, 0, 1, 5), (2, 6, 1, 1)],
    "d": [(3, 0, 1, 7), (0, 0, 4, 1), (0, 4, 4, 1), (0, 0, 1, 5)],
    "o": [(0, 0, 4, 1), (0, 4, 4, 1), (0, 0, 1, 5), (3, 0, 1, 5)],
    "p": [(0, -2, 1, 7), (0, 4, 4, 1), (0, 1, 4, 1), (3, 1, 1, 4)],
    "e": [(0, 0, 4, 1), (0, 2, 3, 1), (0, 4, 4, 1), (0, 0, 1, 5)],
    "r": [(0, 0, 1, 5), (0, 4, 4, 1), (3, 3, 1, 1)],
    "z": [(0, 4, 4, 1), (0, 0, 4, 1), (2, 2, 1, 1), (1, 1, 1, 1), (3, 3, 1, 1)],
    "a": [(0, 0, 4, 1), (0, 2, 4, 1), (0, 4, 4, 1), (0, 0, 1, 3), (3, 0, 1, 5)],
    ".": [(1, 0, 2, 1)],
}
TEXT = "iddoperez.ai"


def emit_text() -> None:
    """Raised letters on the back plate's front face, centred."""
    cell = 1.55                                   # mm per font unit
    ch_w, gap = 5 * cell, 1.9
    total = len(TEXT) * ch_w + (len(TEXT) - 1) * gap
    x = (BASE_W - total) / 2
    z0 = BASE_H + (PLATE_H - BASE_H) * 0.52       # vertically centred on plate
    y_face = BASE_D - PLATE_T - TEXT_RAISE        # plate front, text sticks out
    for ch in TEXT:
        for (cx, cz, w, h) in F[ch]:
            box(DECOR, x + cx * cell, y_face, z0 + cz * cell,
                w * cell, TEXT_RAISE + 0.4, h * cell)   # +0.4 embeds into plate
        x += ch_w + gap


def emit_stripes() -> None:
    """Barbershop bars across the base front — five raised parallelograms
    (stepped boxes; at this size the diagonal reads clearly)."""
    y_face = -STRIPE_RAISE
    w, s = 9.0, 24.0
    for k in range(5):
        x = 8 + k * s
        for step in range(4):                     # 4 steps of 2mm = the slant
            box(DECOR, x + step * 2.0, y_face, step * 2.0,
                w, STRIPE_RAISE + 0.4, 2.0)       # +0.4 embeds into base front


def emit_body() -> None:
    """Base slab + back plate + seven divider fins + front lip."""
    box(BODY, 0, 0, 0, BASE_W, BASE_D, BASE_H)                        # base
    box(BODY, 0, BASE_D - PLATE_T, 0, BASE_W, PLATE_T, PLATE_H)       # plate
    pitch = (BASE_W - FIN_T) / SLOTS
    for i in range(SLOTS + 1):                                        # 7 fins
        box(BODY, i * pitch, BASE_D - PLATE_T - FIN_D, BASE_H,
            FIN_T, FIN_D, FIN_H)
    box(BODY, 0, 0, BASE_H, BASE_W, LIP_T, LIP_H)                     # lip


# --------------------------------------------------------------- STL write --
def write_stl(path: pathlib.Path, tris: list[tuple]) -> None:
    with open(path, "wb") as f:
        f.write(b"joint-holder iddoperez.ai".ljust(80, b" "))
        f.write(struct.pack("<I", len(tris)))
        for n, a, b, c in tris:
            f.write(struct.pack("<12f", *n, *a, *b, *c))
            f.write(struct.pack("<H", 0))


def main() -> None:
    emit_body()
    emit_text()
    emit_stripes()
    here = pathlib.Path(__file__).parent
    write_stl(here / "body.stl", BODY)
    write_stl(here / "decor.stl", DECOR)
    print(f"body.stl  {len(BODY):5d} tris  (base+fins+plate, filament A)")
    print(f"decor.stl {len(DECOR):5d} tris  (text+stripes,   filament B)")


if __name__ == "__main__":
    main()