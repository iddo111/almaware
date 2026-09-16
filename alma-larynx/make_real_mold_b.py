# -*- coding: utf-8 -*-
"""make_real_mold_b.py — REV B: an open TRAY mold for the thin-leaf fold.

WHY REV B (all measured 2026-08-25):
  * rev-A solid M5 block: SILENT at 2 kPa; 75 Hz at 5 kPa (simulate_voicebox.py).
  * design_sweep.py, 79 winners at 2 kPa; champion (Ecoflex 00-30 in hand):
    leaf thickness 1.2 mm, length 12 mm, free height 2.5 mm (set by the
    collar), rest gap ~0.2 mm (collar shims), ONE servo tensioner:
    F0 230 Hz at mid-tension, servo span 140-260 Hz, full-depth buzz.

THE INSIGHT THAT KILLED THE COMPLICATED MOLD: the winning fold is not a
sculpted block — it is a FLAT LEAF of 1.2 mm silicone (Sawada's cords are
thin sheets too). The collar clamps its bottom 4 mm; the free height above
the clamp line is what vibrates, and the servo string tensions it. So the
mold is an open TRAY: pour, screed flat with a card, cure, peel. A first
core-and-slot design died in review — T-section undercut, the cast could
never pull through its own 1.2 mm slot. Straight walls or no mold.

CAST: leaf 12 x 10 x 1.2 mm  (10 = 4 clamped + up to 6 free, trimmed at
assembly). Tray holds TWO leaf pockets — cast the pair in one pour, pick the
better one (pour defects happen at 1.2 mm).

ACCEPTANCE (before any print — the rev-A law, adapted to a tray):
  watertight; pockets open to the top; pocket volume == leaf volume; no
  geometry overhangs the pockets (demold = peel).

  python make_real_mold_b.py  ->  THROAT-MOLD-B.stl + acceptance numbers
"""
import trimesh

LEAF_X, LEAF_Y, LEAF_T = 12.0, 10.0, 1.2   # mm — the champion leaf
PLATE_T = 4.0                               # tray plate thickness
RIM = 4.0                                   # margin around pockets
GAP = 6.0                                   # between the two pockets

def box(sx, sy, sz, cx, cy, cz):
    b = trimesh.creation.box(extents=(sx, sy, sz))
    b.apply_translation((cx, cy, cz))
    return b

def main():
    px = 2 * LEAF_X + GAP + 2 * RIM        # plate size
    py = LEAF_Y + 2 * RIM
    floor_t = PLATE_T - LEAF_T             # solid under the pockets

    # REV B.1 (2026-08-29): real boolean difference, not concatenated boxes.
    # The concatenated version exported watertight=False and carried internal
    # walls — it sliced, but it rendered as a shredded block and any strict
    # slicer could mis-read it. plate MINUS two pockets is one clean manifold.
    plate = box(px, py, PLATE_T, 0, 0, PLATE_T / 2)
    x1 = -(GAP / 2 + LEAF_X / 2)
    x2 = +(GAP / 2 + LEAF_X / 2)
    cuts = [box(LEAF_X, LEAF_Y, LEAF_T + 2, xc, 0, PLATE_T - LEAF_T / 2 + 1)
            for xc in (x1, x2)]
    mold = trimesh.boolean.difference([plate] + cuts)
    out = r"D:/CLAUDE/alma-larynx/THROAT-MOLD-B.stl"
    mold.export(out)

    wt = mold.is_watertight
    vol = mold.volume
    bb = mold.bounding_box.volume
    pocket_expected = LEAF_X * LEAF_Y * LEAF_T * 2
    pocket_actual = px * py * PLATE_T - vol
    print(f"mold watertight       : {wt}")
    print(f"plate                 : {px:.0f} x {py:.0f} x {PLATE_T:.0f} mm")
    print(f"pockets (2 leaves)    : {LEAF_X} x {LEAF_Y} x {LEAF_T} mm each")
    print(f"pocket volume check   : expected {pocket_expected:.0f} mm^3, "
          f"actual {pocket_actual:.0f} mm^3 "
          f"({'MATCH' if abs(pocket_actual - pocket_expected) < 1 else 'MISMATCH'})")
    print(f"solid fraction        : {vol / bb * 100:.1f}% (tray: high by design; "
          f"the acceptance here is open pockets + volume match)")
    print(f"overhangs above pocket: none by construction (nothing above z={PLATE_T})")
    print(f"print estimate        : ~15 min PLA, no supports, pockets up")
    print(f"saved -> {out}")

if __name__ == "__main__":
    main()
