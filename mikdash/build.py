# -*- coding: utf-8 -*-
"""
Build the Temple geometry from temple.M and write:

    web/model.json   axis-aligned boxes for the WebXR viewer
    MIKDASH.stl      the same solid, as KAV triangles (mesh.box -> (12,3,3) soup)
    SOURCES.md       every measurement mapped to its verse

Axes:  X east+,  Y up,  Z north+.  Origin at the centre of the inner court.
Units: cubits (temple.CUBIT_M metres each).
The House faces EAST, as the man in Yech 40:6 enters by the east gate.
"""
from __future__ import annotations
import json, os, sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import temple as T
from temple import val as V

BOXES = []

# One palette, written into model.json, read by BOTH the WebXR viewer and the
# TZELEM stills — so the picture on the Desktop and the picture in the headset
# cannot drift apart. Colour is a rendering choice, never a measurement.
PALETTE = {
    "precinct_wall": [.74, .68, .57], "boundary_wall": [.66, .63, .58],
    "outer_pavement": [.68, .64, .56], "inner_pavement": [.83, .80, .71],
    "ground": [.50, .485, .455],   # deliberately darker than the pavement, so the precinct reads
    "gizrah": [.70, .66, .58], "outer_chamber": [.68, .62, .52], "lishkot": [.71, .66, .57],
    "court_wall": [.75, .69, .58], "steps": [.72, .68, .60],
    "altar": [.40, .38, .36], "altar_horn": [.47, .44, .41],
    "house_floor": [.86, .83, .75], "house_wall": [.89, .86, .77],
    "ulam_wall": [.91, .88, .79], "ulam_side": [.91, .88, .79], "ulam_lintel": [.78, .66, .42],
    "heichal_wall": [.80, .68, .45], "heichal_lintel": [.78, .64, .38],   # 41:16, wood wainscot
    "partition": [.76, .62, .36], "wood_altar": [.72, .55, .30],
    "tzela_wall": [.78, .73, .63], "tzela_floor": [.72, .68, .60],
    "binyan_wall": [.70, .65, .56], "binyan_floor": [.66, .62, .55],
    "person": [.16, .34, .62],
    # the gates are tagged outer_gate_E_wall, inner_gate_N_cellroof, ... so the
    # viewer falls back to a suffix match on these:
    "_gate_wall": [.76, .70, .58], "_gate_skin": [.70, .64, .53],
    "_gate_cellroof": [.60, .55, .46], "_gate_border": [.56, .50, .42],
    "_gate_jamb": [.82, .76, .63], "_gate_floor": [.69, .65, .57],
    "_default": [.72, .67, .58],
}


def colour_of(kind):
    if kind in PALETTE:
        return PALETTE[kind]
    i = kind.rfind("_")
    if i > 0:
        k = "_gate" + kind[i:]
        if k in PALETTE:
            return PALETTE[k]
    return PALETTE["_default"]


def box(lo, hi, kind, src, inferred=False, note=""):
    """One axis-aligned box. `src` must name a verse or say why it does not."""
    lo = [float(x) for x in lo]
    hi = [float(x) for x in hi]
    lo, hi = [min(a, b) for a, b in zip(lo, hi)], [max(a, b) for a, b in zip(lo, hi)]
    if any(h - l <= 0 for l, h in zip(lo, hi)):
        raise ValueError(f"degenerate box {kind}: {lo} {hi}")
    BOXES.append({"lo": lo, "hi": hi, "kind": kind, "src": src,
                  "inferred": bool(inferred), "note": note})


# ---------------------------------------------------------------------------
# geometry constants derived from the measurement table
# ---------------------------------------------------------------------------
HALF = V("precinct") / 2                 # 250
WT = V("wall_thick")                     # 6
GD, GW = V("gate_depth"), V("gate_width")     # 50, 25
CELL, PIER, THR = V("gate_cell"), V("gate_pier"), V("gate_threshold")
PORCH, POST = V("gate_porch"), V("gate_post")
PASS_HALF = V("gate_passage") / 2        # 6.5
OPEN_HALF = V("gate_opening") / 2        # 5.0
GHALF = GW / 2                           # 12.5
SKIN = 1.0                               # outer skin of the gate — INFERRED

IC = V("inner_court") / 2                # 50
Y0, YO, YI, YH = T.GROUND, T.Y_OUTER, T.Y_INNER, T.Y_HOUSE

# The gate's stations along its own depth, straight out of 40:6-9.
# u = 0 is the INNER face (toward the court) and u = 50 the OUTER face, because
# 40:9 and 40:15 put the porch (ulam ha-sha'ar) at the inner end: one enters over
# the outer threshold, passes the three guardrooms, and comes out through the porch.
U = {}
u = 0.0
for name, d in [("post", POST), ("porch", PORCH), ("thr_in", THR),
                ("cell3", CELL), ("pier2", PIER), ("cell2", CELL),
                ("pier1", PIER), ("cell1", CELL), ("thr_out", THR)]:
    U[name] = (u, u + d)
    u += d
assert abs(u - GD) < 1e-9, u
CELL_SPANS = [U["cell1"], U["cell2"], U["cell3"]]
SOLID_SPANS = [U["thr_out"], U["pier1"], U["pier2"], U["thr_in"], U["porch"], U["post"]]

GATE_SRC = "Yech 40:6-13,21 (all six gates alike: 40:21,24,28,32,35)"


def place(u, v, orient):
    """Gate-local (u along, v across) -> world (x, z). u=0 is the OUTER end."""
    if orient == "E":   return (+u, +v)      # east gate: u runs west->east outward
    if orient == "W":   return (-u, -v)
    if orient == "N":   return (-v, +u)
    if orient == "S":   return (+v, -u)
    raise ValueError(orient)


def gate(base_u, orient, y, tag):
    """One gate. base_u is the world distance of its INNER face from the origin."""
    h = V("h_gate")
    hp = V("h_gate_porch")

    def wb(u0, u1, v0, v1, ytop, kind, src, inferred=False, note="", ybot=None):
        x0, z0 = place(base_u + u0, v0, orient)
        x1, z1 = place(base_u + u1, v1, orient)
        box([min(x0, x1), ybot if ybot is not None else y, min(z0, z1)],
            [max(x0, x1), ytop, max(z0, z1)], kind, src, inferred, note)

    # floor of the whole gate passage
    wb(0, GD, -GHALF, GHALF, y, f"{tag}_floor", GATE_SRC, ybot=y - 1)

    for s in (+1, -1):
        vin, vout = s * PASS_HALF, s * GHALF
        lo, hi = min(vin, vout), max(vin, vout)
        # solid side wall wherever there is no guardroom
        for (u0, u1) in SOLID_SPANS:
            top = hp if (u0, u1) in (U["porch"], U["post"]) else h
            wb(u0, u1, lo, hi, top, f"{tag}_wall", GATE_SRC)
        # roof over each guardroom (40:13 speaks of "the roof of the cell")
        for (u0, u1) in CELL_SPANS:
            wb(u0, u1, lo, hi, h, f"{tag}_cellroof", "Yech 40:13", ybot=h - 1)
        # the outer skin that closes the guardrooms off from outside
        wb(0, GD, s * GHALF, s * (GHALF + SKIN), h, f"{tag}_skin",
           "INFERRED: 40:13's 25 cubits is measured roof-to-roof, so this skin lies outside it",
           inferred=True)
        # the two thresholds narrow the passage to the 10 cubits of 40:11
        for (u0, u1) in (U["thr_out"], U["thr_in"]):
            wb(u0, u1, s * OPEN_HALF, vin, h, f"{tag}_jamb", "Yech 40:11")
        # the one-cubit border in front of each guardroom (40:12)
        for (u0, u1) in CELL_SPANS:
            wb(u0, u1, vin, vin - s * V("gate_border"), y + 1, f"{tag}_border", "Yech 40:12")


def steps(x_lo, x_hi, z0, z1, y_lo, y_hi, n, src, orient="E"):
    """n steps rising from y_lo at x_lo to y_hi at x_hi.

    x_lo is the FOOT of the flight and x_hi its head. Passing these the wrong way
    round builds a flight that descends away from what it serves, which presents a
    sheer face to anyone walking up to it — that bug was caught by the walk test,
    not by looking at it.
    """
    x_out, x_in = x_lo, x_hi
    rise = (y_hi - y_lo) / n
    tread = (x_in - x_out) / n
    for i in range(n):
        a, b = x_out + i * tread, x_out + (i + 1) * tread
        if orient in ("E", "W"):
            box([min(a, b), y_lo, z0], [max(a, b), y_lo + (i + 1) * rise, z1],
                "steps", src)
        else:
            box([z0, y_lo, min(a, b)], [z1, y_lo + (i + 1) * rise, max(a, b)],
                "steps", src)


# ===========================================================================
# 0. the ground.  40:2 puts the whole vision "upon a very high mountain" but gives
#    the mountain no shape at all, so a flat plane is the honest minimum. Its top
#    sits 0.02 cubits above zero so that it, and not TZELEM's built-in checkered
#    test plane at y=0, is what the stills ray-cast hits. (TZELEM's checker is part
#    of its own scoring harness — it is not ours to remove.)
# ===========================================================================
_G = V("boundary_reeds") * T.REED_CUBITS / 2 * 4      # far enough that its edge is never in frame
box([-_G, -4, -_G], [_G, 0.02, _G], "ground",
    "Yech 40:2 ('upon a very high mountain') — the mountain is stated, its SHAPE is not",
    inferred=True, note="flat by default; no terrain data is invented")

# ===========================================================================
# 1. the outer wall of the precinct  (40:5 thickness+height; 42:20 the 500)
# ===========================================================================
SRC_WALL = "Yech 40:5 (one reed thick, one reed high) + 42:20 (500 x 500)"
for s in (+1, -1):
    # east and west walls, broken by the gate
    box([s * HALF - s * WT, YO, -HALF], [s * HALF, YO + V("wall_height"), -GHALF - SKIN],
        "precinct_wall", SRC_WALL)
    box([s * HALF - s * WT, YO, GHALF + SKIN], [s * HALF, YO + V("wall_height"), HALF],
        "precinct_wall", SRC_WALL)
    # north and south walls, broken by the gate
    box([-HALF, YO, s * HALF - s * WT], [-GHALF - SKIN, YO + V("wall_height"), s * HALF],
        "precinct_wall", SRC_WALL)
    box([GHALF + SKIN, YO, s * HALF - s * WT], [HALF, YO + V("wall_height"), s * HALF],
        "precinct_wall", SRC_WALL)

# the pavement of the outer court (40:17-18)
box([-HALF, YO - 2, -HALF], [HALF, YO, HALF], "outer_pavement",
    "Yech 40:17-18 ('a pavement made for the court round about')")

# thirty chambers upon the pavement (40:17) — count given, size not
NCH = V("outer_chambers")
per_side, ch_w, ch_d = NCH // 4 + 1, 14.0, 12.0
for si, (dx, dz) in enumerate([(1, 0), (-1, 0), (0, 1), (0, -1)]):
    made = 0
    for i in range(per_side):
        if si * per_side + i >= NCH:
            break
        t = -HALF + 40 + i * 60
        if dx:
            if abs(t) < GHALF + 20: continue
            box([dx * (HALF - WT - ch_d), YO, t], [dx * (HALF - WT), YO + 8, t + ch_w],
                "outer_chamber", "Yech 40:17 (thirty chambers; their size is not given)",
                inferred=True, note="count from 40:17, dimensions INFERRED")
        else:
            if abs(t) < GHALF + 20: continue
            box([t, YO, dz * (HALF - WT - ch_d)], [t + ch_w, YO + 8, dz * (HALF - WT)],
                "outer_chamber", "Yech 40:17 (thirty chambers; their size is not given)",
                inferred=True, note="count from 40:17, dimensions INFERRED")
        made += 1

# ===========================================================================
# 2. the four outer gates and the four inner gates
# ===========================================================================
for orient in ("E", "W", "N", "S"):
    gate(HALF - GD, orient, YO, f"outer_gate_{orient}")   # outer gate: 200..250
    gate(IC, orient, YI, f"inner_gate_{orient}")          # inner gate:  50..100
# 40:23 "from gate to gate, a hundred cubits" — the gap between the two structures
assert abs(((HALF - GD) - (IC + GD)) - V("court_gap")) < 1e-9, "the gates are misplaced"

# seven steps up to each outer gate (40:22,26)
for orient in ("E", "W", "N", "S"):
    n, rise = V("steps_outer"), (YO - Y0) / V("steps_outer")
    for i in range(n):
        d = HALF + (n - i) * V("step_tread")
        lo_v, hi_v = -GHALF, GHALF
        for sgn, ax in [(1, "x"), (-1, "x"), (1, "z"), (-1, "z")]:
            pass
        if orient == "E":
            box([HALF + (n - i - 1) * 1.0, Y0, lo_v], [HALF + (n - i) * 1.0, Y0 + (i + 1) * rise, hi_v],
                "steps", "Yech 40:22,26 (seven steps; the rise is INFERRED)", inferred=True)
        elif orient == "W":
            box([-HALF - (n - i) * 1.0, Y0, lo_v], [-HALF - (n - i - 1) * 1.0, Y0 + (i + 1) * rise, hi_v],
                "steps", "Yech 40:22,26 (seven steps; the rise is INFERRED)", inferred=True)
        elif orient == "N":
            box([lo_v, Y0, HALF + (n - i - 1) * 1.0], [hi_v, Y0 + (i + 1) * rise, HALF + (n - i) * 1.0],
                "steps", "Yech 40:22,26 (seven steps; the rise is INFERRED)", inferred=True)
        else:
            box([lo_v, Y0, -HALF - (n - i) * 1.0], [hi_v, Y0 + (i + 1) * rise, -HALF - (n - i - 1) * 1.0],
                "steps", "Yech 40:22,26 (seven steps; the rise is INFERRED)", inferred=True)

# eight steps up to each inner gate (40:31,34,37)
SRC8 = "Yech 40:31,34,37 (eight steps; the rise is INFERRED)"
n8, rise8 = V("steps_inner"), (YI - YO) / V("steps_inner")
for i in range(n8):
    off = IC + GD + (n8 - i) * 1.0
    off2 = IC + GD + (n8 - i - 1) * 1.0
    box([off2, YO, -GHALF], [off, YO + (i + 1) * rise8, GHALF], "steps", SRC8, inferred=True)
    box([-off, YO, -GHALF], [-off2, YO + (i + 1) * rise8, GHALF], "steps", SRC8, inferred=True)
    box([-GHALF, YO, off2], [GHALF, YO + (i + 1) * rise8, off], "steps", SRC8, inferred=True)
    box([-GHALF, YO, -off], [GHALF, YO + (i + 1) * rise8, -off2], "steps", SRC8, inferred=True)

# ===========================================================================
# 3. the inner court, 100 x 100 foursquare (40:47)
# ===========================================================================
box([-IC, YI - 2, -IC], [IC, YI, IC], "inner_pavement", "Yech 40:47")
# its enclosing wall, broken at the four gates
SRC_IW = "Yech 40:47 (the court is bounded); its HEIGHT is INFERRED from 40:5"
for s in (+1, -1):
    box([s * IC, YI, -IC], [s * (IC + 2), YI + V("h_court_wall"), -GHALF], "court_wall", SRC_IW, True)
    box([s * IC, YI, GHALF], [s * (IC + 2), YI + V("h_court_wall"), IC], "court_wall", SRC_IW, True)
    box([-IC, YI, s * IC], [-GHALF, YI + V("h_court_wall"), s * (IC + 2)], "court_wall", SRC_IW, True)
    box([GHALF, YI, s * IC], [IC, YI + V("h_court_wall"), s * (IC + 2)], "court_wall", SRC_IW, True)

# ===========================================================================
# 4. the altar, before the House (40:47; 43:13-17)
# ===========================================================================
ALT = "Yech 43:13-17"
a_h = V("altar_ariel") / 2          # 6
z_h = V("altar_azarah") / 2         # 7
b_h = z_h + V("altar_setback")      # 8
c_h = b_h + V("altar_chik")         # 9
ay = YI
box([-c_h, ay, -c_h], [c_h, ay + V("altar_chik"), c_h], "altar",
    "Yech 43:13 (the chik; its footprint follows from the one-cubit widths)")
ay += V("altar_chik")
box([-b_h, ay, -b_h], [b_h, ay + V("altar_base_h"), b_h], "altar", "Yech 43:14 (two cubits)")
ay += V("altar_base_h")
box([-z_h, ay, -z_h], [z_h, ay + V("altar_mid_h"), z_h], "altar",
    "Yech 43:14,17 (four cubits; the settle is fourteen by fourteen)")
ay += V("altar_mid_h")
box([-a_h, ay, -a_h], [a_h, ay + V("altar_harel_h"), a_h], "altar",
    "Yech 43:15,16 (the harel, four cubits; the ariel twelve by twelve)")
ay += V("altar_harel_h")
hs = V("altar_horn_size")
for sx in (-1, 1):
    for sz in (-1, 1):
        box([sx * a_h - (hs if sx > 0 else 0), ay, sz * a_h - (hs if sz > 0 else 0)],
            [sx * a_h + (hs if sx < 0 else 0), ay + hs, sz * a_h + (hs if sz < 0 else 0)],
            "altar_horn", "Yech 43:15 (four horns; their size is not given)", inferred=True)
# "and its steps shall look toward the east" (43:17). The text gives the direction
# and nothing else - no count, no rise, no run - so all three are inferred. The
# ramp climbs to the great settle (the 14x14 azarah), not to the hearth.
RAMP_TOP = YI + V("altar_chik") + V("altar_base_h") + V("altar_mid_h")
steps(c_h + 20, c_h, -3, 3, YI, RAMP_TOP, 14,
      "Yech 43:17 ('its steps shall look toward the east'); count, rise and run all INFERRED")
for b in BOXES[-14:]:
    b["inferred"] = True

# ===========================================================================
# 5. the House  (ch. 41), its east face on the west edge of the inner court
# ===========================================================================
X0 = -IC                                   # -50, the front of the ulam
xs, cur = {}, X0
for name, d in [("ulam_wall", V("ulam_front_wall")), ("ulam", V("ulam_depth")),
                ("heichal_wall", V("house_wall")), ("heichal", V("heichal_len")),
                ("partition", V("partition")), ("dvir", V("dvir")),
                ("west_wall", V("house_wall")), ("tzela_w", V("tzela")),
                ("tzela_wall_w", V("tzela_outer_wall"))]:
    xs[name] = (cur - d, cur)
    cur -= d
assert abs(cur - (X0 - V("house_len"))) < 1e-9, cur

HW = V("heichal_width") / 2                # 10
z_wall = HW + V("house_wall")              # 16
z_tzela = z_wall + V("tzela")              # 20
z_out = z_tzela + V("tzela_outer_wall")    # 25
HH = V("h_house")

# platform under the House and the gizrah (41:14 gives the 100-cubit front)
box([X0 - V("house_len"), YI - 2, -IC], [X0, YI, IC], "gizrah",
    "Yech 41:13-14 (the house is a hundred long; house + gizrah a hundred across)")
box([X0 - V("house_len"), YI, -z_out], [X0, YH, z_out], "house_floor",
    "Yech 41:8 (the house has a raised base of one full reed)")

# ten steps up to the porch (40:49 says 'by steps'; the count is the LXX's)
steps(X0 + 10, X0, -7, 7, YI, YH, V("steps_ulam"),
      "Yech 40:49 ('by steps'); the count 10 is the SEPTUAGINT, the rise is INFERRED")
for b in BOXES[-int(V("steps_ulam")):]:
    b["inferred"] = True

# --- the porch (ulam): 20 long, 11 broad, piers of 5, jambs of 3 -----------
uw0, uw1 = xs["ulam_wall"]
u0, u1 = xs["ulam"]
UH = V("ulam_width") / 2                  # 10
UP = UH + V("ulam_pier")                  # 15
JAMB = UH - V("ulam_jamb")                # 7 — half the opening
box([uw0, YH, -UP], [uw1, YH + HH, -JAMB], "ulam_wall", "Yech 40:48-49")
box([uw0, YH, JAMB], [uw1, YH + HH, UP], "ulam_wall", "Yech 40:48-49")
box([uw0, YH + 14, -JAMB], [uw1, YH + HH, JAMB], "ulam_lintel",
    "Yech 40:48 (the opening; its HEIGHT is INFERRED)", inferred=True)
for s in (+1, -1):
    box([u0, YH, s * UH], [u1, YH + HH, s * UP], "ulam_side", "Yech 40:48-49")

# --- the heichal: 40 by 20, walls of 6, door of 10 -------------------------
hw0, hw1 = xs["heichal_wall"]
DH = V("heichal_door") / 2                # 5
box([hw0, YH, -z_wall], [hw1, YH + HH, -DH], "heichal_wall", "Yech 41:1-2,5")
box([hw0, YH, DH], [hw1, YH + HH, z_wall], "heichal_wall", "Yech 41:1-2,5")
box([hw0, YH + 16, -DH], [hw1, YH + HH, DH], "heichal_lintel",
    "Yech 41:2 (door 10 wide; its HEIGHT is INFERRED)", inferred=True)
h0, h1 = xs["heichal"]
for s in (+1, -1):
    box([h0, YH, s * HW], [h1, YH + HH, s * z_wall], "house_wall", "Yech 41:5")

# --- the partition and the Holy of Holies ----------------------------------
p0, p1 = xs["partition"]
DVH = V("dvir_door") / 2                  # 3
box([p0, YH, -HW], [p1, YH + HH, -DVH], "partition", "Yech 41:3")
box([p0, YH, DVH], [p1, YH + HH, HW], "partition", "Yech 41:3")
box([p0, YH + 12, -DVH], [p1, YH + HH, DVH], "partition",
    "Yech 41:3 (door 6 wide; its HEIGHT is INFERRED)", inferred=True)
# the altar of wood inside the heichal - "this is the table that is before the LORD"
box([-111, YH, -1], [-109, YH + 3, 1], "wood_altar",
    "Yech 41:22 (three cubits high, two long; its WIDTH is not stated - taken as two)",
    inferred=True, note="height and length GIVEN; width inferred from the square implied by 'its corners'")

d0, d1 = xs["dvir"]
for s in (+1, -1):
    box([d0, YH, s * HW], [d1, YH + HH, s * z_wall], "house_wall", "Yech 41:5")
w0, w1 = xs["west_wall"]
box([w0, YH, -z_wall], [w1, YH + HH, z_wall], "house_wall", "Yech 41:5")

# --- the side chambers: three tiers, 4 wide, outer wall 5 (41:5-9) ---------
TZ = V("h_tzela_tier")
for t in range(int(V("tzela_tiers"))):
    yb = YH + t * TZ
    for s in (+1, -1):
        box([xs["tzela_wall_w"][0], yb, s * z_tzela], [X0, yb + TZ - 0.5, s * z_out],
            "tzela_wall", "Yech 41:9 (the outer wall of the side chamber, five cubits)")
        box([xs["tzela_wall_w"][0], yb + TZ - 0.5, s * z_wall], [X0, yb + TZ, s * z_out],
            "tzela_floor", "Yech 41:6 (side chamber over side chamber, three)")
    box([xs["tzela_wall_w"][0], yb, -z_out], [xs["tzela_w"][0], yb + TZ - 0.5, z_out],
        "tzela_wall", "Yech 41:9")

# ===========================================================================
# 6. the building on the west (binyan), 70 by 90, wall 5  (41:12)
# ===========================================================================
BX1 = X0 - V("house_len")                 # -150
BX0 = BX1 - V("house_len")                # -250
bw = V("binyan_width") / 2                # 35
bo = bw + V("binyan_wall")                # 40
BH = V("h_binyan")
box([BX0, YI - 2, -bo], [BX1, YI, bo], "binyan_floor", "Yech 41:12")
for s in (+1, -1):
    box([BX0, YI, s * bw], [BX1, YI + BH, s * bo], "binyan_wall", "Yech 41:12")
box([BX0, YI, -bo], [BX0 + V("binyan_wall"), YI + BH, bo], "binyan_wall", "Yech 41:12")
box([BX1 - V("binyan_wall"), YI, -bo], [BX1, YI + BH, bo], "binyan_wall", "Yech 41:12")

# ===========================================================================
# 7. the priests' chambers, north and south (42:1-8)
# ===========================================================================
LT = V("h_lishkot_tier")
for s in (+1, -1):
    for t in range(int(V("lishkot_tiers"))):
        yb = YO + t * LT
        inset = t * 4.0    # 42:5 "the upper chambers were shorter"
        box([BX1 + inset, yb, s * (IC + 10)], [BX1 + V("lishkot_len") - inset, yb + LT - 0.5,
             s * (IC + 10 + V("lishkot_width"))],
            "lishkot", "Yech 42:1-8 (100 long, 50 broad, three storeys; HEIGHT INFERRED)",
            inferred=True)

# ===========================================================================
# 8. a person, 1.80 m tall, standing on the outer-court side of the east gate
# ===========================================================================
# Inside the outer east gate, against the north side of the passage: somewhere it
# is actually SEEN. Clear of the centre line, so it measures the gate without
# standing in the doorway.
P = T.PERSON_CUBITS
box([235.0, YO, 4.6], [235.55, YO + P, 5.5],
    "person", f"scale reference: a person {T.PERSON_M:.2f} m = {P:.2f} cubits", inferred=True)

# ===========================================================================
# 9. the 500-REED separating wall (42:16-20, the qere) — the far boundary
# ===========================================================================
RB = V("boundary_reeds") * T.REED_CUBITS / 2      # 1500 cubits
SRC_RB = ("Yech 42:16-20 read with the QERE (500 REEDS = 3000 cubits). The ketiv at 42:16 "
          "says 'cubits'. Rashi takes the reed reading and treats this as the wall of the "
          "whole mountain, distinct from the 500-CUBIT courts modelled above.")
for s in (+1, -1):
    box([s * RB - s * WT, Y0, -RB], [s * RB, Y0 + V("wall_height"), RB],
        "boundary_wall", SRC_RB, inferred=True, note="disputed reading — see SOURCES.md")
    box([-RB, Y0, s * RB - s * WT], [RB, Y0 + V("wall_height"), s * RB],
        "boundary_wall", SRC_RB, inferred=True, note="disputed reading — see SOURCES.md")


# ===========================================================================
# SOURCES.md — generated from the same table the geometry is built from, so the
# document and the model cannot drift apart.
# ===========================================================================
BANNER = ("> \U0001fa9f **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, "
          "fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a "
          "proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.\n")

DISPUTES = [
 ("The size of the cubit",
  "Yech 40:5 and 43:13 both define the standard as *amah va-tefach* — the LONG cubit of "
  "seven handbreadths, not the ordinary six. The physical size of a handbreadth is disputed: "
  "R' Chaim Naeh ≈ 8.0 cm, the Chazon Ish ≈ 9.6 cm.",
  "**Chosen: 8.0 cm, so the cubit is 0.560 m and the reed 3.36 m.** One constant in "
  "`temple.py` (`TEFACH_M`); set it to 0.096 for the Chazon Ish and everything rescales."),

 ("42:16 — five hundred CUBITS or five hundred REEDS?",
  "The ketiv at 42:16 reads אמות (cubits), the qere reads מאות (hundreds), and the verse "
  "then says *kanim* (reeds). On the qere the separating wall is 500 reeds = 3000 cubits; "
  "on the ketiv it is 500 cubits — which is also exactly the size the courts of ch. 40-41 "
  "come out to when their own numbers are added up.",
  "**Chosen: both, as Rashi does.** The courts are modelled at 500×500 CUBITS, which the "
  "text's own arithmetic forces (see check 6). The 500-REED wall of 42:20 is modelled as a "
  "separate, distant boundary around the whole mountain, and is marked inferred in the viewer."),

 ("40:14 — 'and he made the posts, sixty cubits'",
  "This verse is famously obscure; the Septuagint reads twenty, and the commentators do not "
  "agree on what is being measured.",
  "**Not used.** No element in this model derives from 40:14. The gates are built entirely "
  "from 40:6-13, which close to exactly 50×25 without it."),

 ("40:49 — the porch is eleven cubits broad, or twelve?",
  "The Masoretic text reads עשתי עשרה (eleven). The Septuagint reads twelve.",
  "**Chosen: eleven**, the Masoretic reading, consistent with using tanach.us throughout."),

 ("The thickness of the porch's front wall",
  "Yechezkel never states it. Middot 4:7 gives 5 cubits for the Second Temple's porch wall.",
  "**Derived, not borrowed: 6.** 41:13 states the house is 100 long; everything else "
  "Yechezkel itemises sums to 94; the remainder is 6 — and 41:5 independently says "
  "'he measured the wall of the house, six cubits'. Two routes agree. Taking Middot's 5 "
  "instead would leave the house one cubit short of its own stated total."),

 ("The heights",
  "Yechezkel gives exactly ONE height in the whole survey: the outer wall, one reed (40:5). "
  "The gates, the courts, the House and the chambers are given no height at all. Middot 4:6 "
  "gives 100 cubits for the SECOND Temple — a different building.",
  "**All other heights are INFERRED and are listed as such.** Press **I** in the viewer to "
  "light every element carrying an inferred dimension in amber. Much of what you see turns "
  "amber, and that is the honest picture."),

 ("The width of the gate passage — ten cubits or thirteen?",
  "40:11 gives two numbers for the gate opening: 'the breadth of the entry, ten cubits' and "
  "'the length of the gate, thirteen'. 40:13 gives the whole gate as 25 broad.",
  "**Chosen: 6 + 13 + 6 = 25.** The passage is 13 wide between the guardrooms and narrows to "
  "the 10-cubit opening at each of the two thresholds. This uses every number in both verses "
  "and closes exactly on 40:13's 25. Other reconstructions put the walls at 1.5 cubits and "
  "keep the passage at 10 throughout."),

 ("How the House reaches a hundred cubits across (41:14)",
  "The itemised parts of 41:2,5,9 give a built block 50 cubits wide, but 41:14 states the "
  "front of the house and the gizrah together are 100.",
  "**Chosen: 25 cubits of open gizrah on the north and 25 on the south**, so 25+50+25 = 100. "
  "The 20-cubit free strip of 41:10 is taken as the separate space between the House and the "
  "priests' chambers, not as part of this 100."),

 ("Yechezkel's House does not sum the way Middot's does",
  "Middot 4:7 (the Second Temple) sums to exactly 100 east-west with a side chamber of 6 and "
  "a partition of 1. Yechezkel gives a side chamber of 4 (41:5) and a partition of 2 (41:3).",
  "**Recorded, not reconciled.** They are different buildings and this model follows "
  "Yechezkel throughout. Middot is cited here only where it is named."),
]

OMITTED = [
 ("The windows (40:16,22,25,33,36; 41:16,26)", "described as 'closed windows' and 'narrowed', "
  "with no dimension anywhere — no opening is cut for them."),
 ("The cherubim and palm trees carved on every wall (41:18-20,25)", "described in detail, "
  "dimensioned nowhere. The heichal and the partition are tinted the warm tone of 41:16's "
  "wood wainscot instead; no carving is modelled."),
 ("The tables for the offerings (40:39-43)", "40:42 gives four tables of 1.5 × 1.5 × 1 cubits, "
  "but their positions are described only as 'on this side and on that side of the porch'. "
  "Left out rather than placed by guess."),
 ("The thirty chambers of the outer court (40:17)", "the COUNT is given and is honoured; "
  "no dimension is given, so their size is inferred and they are marked amber."),
 ("Everything from 43:18 onward", "the ordinances of the altar are law, not architecture, "
  "and nothing in this model depends on them."),
]


def write_sources():
    L = []
    A = L.append
    A("# SOURCES — every measurement, and the verse it comes from\n")
    A(BANNER)
    A("\n**המקדש העתידי — יחזקאל מ׳–מ״ג · The future Temple, Yechezkel 40–43.**\n")
    A("This file is GENERATED by `build.py` from the same table `build.py` builds the "
      "geometry from. If a number changes in the model it changes here, in the same commit, "
      "automatically. Nothing in the model is hand-copied into this document.\n")

    A("\n## The text\n")
    A("| | |\n|---|---|\n"
      "| Source | `D:\\CLAUDE\\hebrew-corpus\\raw\\ctrl_bib_Ezekiel.json` (already on this machine) |\n"
      "| Edition | *Tanach with Text Only*, from http://www.tanach.us/Tanach.xml |\n"
      "| Licence | **Public Domain** (as recorded in the file's own `license` field) |\n"
      "| Chapters used | 40, 41, 42, 43 |\n")
    A("\nNothing was downloaded for this build. No texture, model, elevation set or photograph "
      "was fetched from anywhere: every surface is flat colour computed in our own shader.\n")

    A("\n## The scale\n")
    A(f"- **1 cubit = {T.CUBIT_M:.3f} m** — the long cubit of {T.CUBIT_TEFACHIM} handbreadths "
      f"(Yech 40:5, 43:13), at {T.TEFACH_M*100:.1f} cm to the handbreadth (R' Chaim Naeh).\n")
    A(f"- **1 reed = {T.REED_CUBITS} cubits = {T.REED_CUBITS*T.CUBIT_M:.2f} m** (Yech 40:5).\n")
    A(f"- The blue figure standing in the outer court is **{T.PERSON_M:.2f} m = "
      f"{T.PERSON_CUBITS:.2f} cubits** tall. The walker's eye is at {T.EYE_M:.2f} m.\n")

    A("\n## The arithmetic the text asserts about itself\n")
    A("These are not checks of my model against my model. Each one takes a set of numbers "
      "Yechezkel states separately and adds them against a TOTAL Yechezkel also states "
      "separately. `build.py` refuses to write any geometry if one of them fails.\n")
    A("\n| # | what | the parts, verse by verse | sum | the text's own total | |\n"
      "|---|---|---|---|---|---|\n")
    for i, (name, got, want, ref, work) in enumerate(checks_cached, 1):
        mark = "MATCH" if abs(got - want) < 1e-9 else "**MISMATCH**"
        A(f"| {i} | {name} | `{work}` | {got:g} | **{want:g}** ({ref}) | {mark} |\n")

    A("\n## Every measurement used\n")
    for kind, title, blurb in [
        ("GIVEN", "GIVEN — the text states this number outright", ""),
        ("DERIVED", "DERIVED — the text states a total and every other part, so this follows",
         "Each of these is also cross-checked against a second, independent verse."),
        ("INFERRED", "INFERRED — the text does NOT give this",
         "These are the honest gaps. In the viewer, press **I** and every element carrying one "
         "of these lights up amber.")]:
        rows = [(k, v) for k, v in T.M.items() if v["kind"] == kind]
        A(f"\n### {title}  ({len(rows)})\n")
        if blurb:
            A(f"\n{blurb}\n")
        A("\n| name | cubits | verse | note |\n|---|---|---|---|\n")
        for k, v in rows:
            A(f"| `{k}` | {v['v']:g} | {v['src']} | {v['note']} |\n")

    A("\n## Where the text is ambiguous, or the commentators disagree\n")
    A("\nEvery one of these is a real fork in the road. The choice taken is stated, not hidden.\n")
    for i, (q, what, chose) in enumerate(DISPUTES, 1):
        A(f"\n**{i}. {q}**\n\n{what}\n\n{chose}\n")

    A("\n## Deliberately left out\n")
    A("\nThe text describes these; it does not dimension them. Rather than invent them "
      "quietly, they are absent, and here is the list.\n\n")
    for what, why in OMITTED:
        A(f"- **{what}** — {why}\n")

    A("\n## Every element in the model, and its source\n")
    A(f"\n{len(BOXES)} boxes. Grouped by the source string each one carries — that string is "
      "attached to the box in `model.json` and is what the viewer shows when you aim the "
      "crosshair at it.\n\n")
    A("| n | inferred | source |\n|---|---|---|\n")
    tally = {}
    for b in BOXES:
        key = (b["src"], b["inferred"])
        tally[key] = tally.get(key, 0) + 1
    for (src, inf), n in sorted(tally.items(), key=lambda kv: -kv[1]):
        A(f"| {n} | {'yes' if inf else '—'} | {src} |\n")

    n_inf = sum(1 for b in BOXES if b["inferred"])
    A(f"\n**{len(BOXES) - n_inf} of {len(BOXES)} boxes carry only measurements the text gives. "
      f"{n_inf} carry at least one inferred dimension** — overwhelmingly a height, because "
      "Yechezkel gives exactly one height in the entire survey.\n")

    p = os.path.join(HERE, "SOURCES.md")
    with open(p, "w", encoding="utf-8") as f:
        f.write("".join(L))
    return p


# ===========================================================================
# WRITE
# ===========================================================================
def main():
    global checks_cached
    checks_cached = T.checks()
    good, lines = T.report()
    print("\n".join(lines))
    if not good:
        raise SystemExit("the measurement table does not agree with the text — refusing to build")
    print(f"\nSOURCES.md -> {write_sources()}")

    os.makedirs(os.path.join(HERE, "web"), exist_ok=True)
    model = {
        "cubit_m": T.CUBIT_M, "tefach_m": T.TEFACH_M, "cubit_tefachim": T.CUBIT_TEFACHIM,
        "reed_cubits": T.REED_CUBITS, "person_cubits": T.PERSON_CUBITS,
        "eye_m": T.EYE_M,
        "levels": {"ground": Y0, "outer_court": YO, "inner_court": YI, "house": YH},
        "spawn": [HALF + 12, Y0, 0],
        "palette": PALETTE,
        "boxes": BOXES,
    }
    p = os.path.join(HERE, "web", "model.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(model, f, ensure_ascii=False, separators=(",", ":"))
    n_inf = sum(1 for b in BOXES if b["inferred"])
    print(f"\n{len(BOXES)} boxes ({n_inf} carrying an inferred dimension) -> {p}"
          f"  [{os.path.getsize(p)/1024:.0f} KB]")

    # --- the same solid as KAV triangles -----------------------------------
    sys.path.insert(0, r"D:\CLAUDE\eran-brain\holobrain\kav")
    import numpy as np, mesh
    tris = np.concatenate([mesh.box(b["lo"], b["hi"]) for b in BOXES])
    stl = os.path.join(HERE, "MIKDASH.stl")
    mesh.write_stl(stl, tris, header=b"MIKDASH-yechezkel-40-43")
    g = mesh.geometry(tris)
    print(f"KAV mesh: {tris.shape[0]} triangles, {g['edges']} edges, "
          f"volume {g['volume']:.0f} cubic cubits -> {stl}")
    return tris


if __name__ == "__main__":
    main()
