# -*- coding: utf-8 -*-
"""make_leaf_farm.py — REV B at Iddo's scale: a maximum-size LEAF FARM.

Iddo's order (2026-08-25 11:30): "scale it to the maximum printable size —
spread it across several plates." Engineering translation that keeps the
physics honest: NOT a scaled-up leaf (size sets F0 — a giant leaf is a bass),
but a plate-sized TRAY holding DOZENS of leaf pockets in the winning
thickness variants from design_sweep.py. One pour floods them all; one
screed pass levels them all (the plate top is one flat plane; pocket FLOORS
sit at different depths, so each pocket yields its own thickness). Physical
testing then picks the true champion — which also collapses the Ecoflex
E = x0.5..x2 literature uncertainty with real parts.

Rows by leaf thickness (the winner corners of the 79-design sweep):
    t = 0.8 / 1.0 / 1.2 / 1.5 mm  (row pattern repeats)
Row labeling that needs no font: RAISED BARS on the left rim margin next to
each row — count the bars: 1 bar = 0.8, 2 = 1.0, 3 = 1.2, 4 = 1.5 mm.

Plate: 280 x 200 x 3.6 mm (fits the K2 Plus 350x350 bed with margin), floor
under the deepest pocket >= 2.1 mm. TWO identical plates = "several plates";
each yields ~60 leaves -> ~120 leaves per pour session.

Acceptance before printing (the rev-A law): watertight parts; per-variant
pocket-volume checks; nothing overhangs a pocket; section proof rendered.

  python make_leaf_farm.py -> THROAT-LEAF-FARM.stl + acceptance numbers
"""
import numpy as np
import trimesh

LEAF_X, LEAF_Y = 12.0, 10.0
THICKNESSES = [0.8, 1.0, 1.2, 1.5]      # mm, row cycle; bars = index+1
PLATE_X, PLATE_Y = 280.0, 200.0
PLATE_T = 3.6                            # top plane; deepest pocket floor 2.1
CELL_X, CELL_Y = 22.0, 26.0              # pocket pitch
RIM = 10.0                               # outer margin (bars live here)
BAR = (2.0, 6.0, 0.6)                    # raised bar size (x, y, height)

def box(sx, sy, sz, cx, cy, cz):
    b = trimesh.creation.box(extents=(sx, sy, sz))
    b.apply_translation((cx, cy, cz))
    return b

def main():
    cols = int((PLATE_X - 2 * RIM) // CELL_X)          # 11
    rows = int((PLATE_Y - 2 * RIM) // CELL_Y)          # 6
    x0 = -(cols - 1) * CELL_X / 2
    y0 = -(rows - 1) * CELL_Y / 2

    parts = []
    pocket_report = {}
    # Build the plate as: full floor slab + per-cell "walls" filling everything
    # in the top layer except the pockets. Simpler and exactly verifiable:
    # top layer = grid of cell blocks, each cell block = cell frame around its
    # pocket, built from 4 boxes.
    floor_t = PLATE_T - max(THICKNESSES)               # 2.1 solid everywhere
    parts.append(box(PLATE_X, PLATE_Y, floor_t, 0, 0, floor_t / 2))

    top_h = PLATE_T - floor_t                          # 1.5 top layer
    ztop = floor_t + top_h / 2
    # outer rim ring of the top layer
    gx = cols * CELL_X; gy = rows * CELL_Y
    parts.append(box((PLATE_X - gx) / 2, PLATE_Y, top_h, -(PLATE_X - (PLATE_X - gx) / 2) / 2 + 0, 0, ztop))
    parts.append(box((PLATE_X - gx) / 2, PLATE_Y, top_h,  (PLATE_X - (PLATE_X - gx) / 2) / 2 - 0, 0, ztop))
    parts.append(box(gx, (PLATE_Y - gy) / 2, top_h, 0, -(PLATE_Y - (PLATE_Y - gy) / 2) / 2, ztop))
    parts.append(box(gx, (PLATE_Y - gy) / 2, top_h, 0,  (PLATE_Y - (PLATE_Y - gy) / 2) / 2, ztop))

    for r in range(rows):
        t = THICKNESSES[r % len(THICKNESSES)]
        cy = y0 + r * CELL_Y
        pocket_report.setdefault(t, 0)
        for c in range(cols):
            cx = x0 + c * CELL_X
            # cell frame: fill the cell's top layer except the pocket, but the
            # pocket is only `t` deep — under it sits (top_h - t) of fill.
            fx, fy = (CELL_X - LEAF_X) / 2, (CELL_Y - LEAF_Y) / 2
            parts.append(box(fx, CELL_Y, top_h, cx - (LEAF_X + fx) / 2, cy, ztop))
            parts.append(box(fx, CELL_Y, top_h, cx + (LEAF_X + fx) / 2, cy, ztop))
            parts.append(box(LEAF_X, fy, top_h, cx, cy - (LEAF_Y + fy) / 2, ztop))
            parts.append(box(LEAF_X, fy, top_h, cx, cy + (LEAF_Y + fy) / 2, ztop))
            under = top_h - t
            if under > 1e-6:
                parts.append(box(LEAF_X, LEAF_Y, under, cx, cy, floor_t + under / 2))
            pocket_report[t] += 1
        # row label: raised bars on the left rim margin
        nbars = THICKNESSES.index(t) + 1
        for b in range(nbars):
            parts.append(box(BAR[0], BAR[1], BAR[2],
                             -(gx / 2 + RIM / 2) + 0,
                             cy - (nbars - 1) * (BAR[1] + 2) / 2 + b * (BAR[1] + 2),
                             PLATE_T + BAR[2] / 2))

    mold = trimesh.util.concatenate(parts)
    out = r"D:\CLAUDE\alma-larynx\THROAT-LEAF-FARM.stl"
    mold.export(out)

    wt = all(p.is_watertight for p in parts)
    vol = sum(p.volume for p in parts)
    # expected pocket volume total
    expect = sum(LEAF_X * LEAF_Y * t * n for t, n in pocket_report.items())
    slab = PLATE_X * PLATE_Y * PLATE_T
    bars_vol = sum(p.volume for p in parts if p.volume < 20)  # the bars are tiny
    actual = slab - (vol - bars_vol)
    print(f"components watertight : {wt}")
    print(f"plate                 : {PLATE_X:.0f} x {PLATE_Y:.0f} x {PLATE_T} mm, "
          f"{cols} x {rows} = {cols*rows} pockets")
    for t in THICKNESSES:
        print(f"  t={t}mm pockets      : {pocket_report.get(t,0)}  "
              f"(row bars: {THICKNESSES.index(t)+1})")
    print(f"pocket volume check   : expected {expect:.0f} mm^3, actual {actual:.0f} mm^3 "
          f"({'MATCH' if abs(actual-expect) < expect*0.02 else 'MISMATCH'})")
    print(f"PLA volume            : {vol/1000:.0f} cm^3 (~{vol/1000*1.24:.0f} g)")
    print(f"saved -> {out}")

if __name__ == "__main__":
    main()
