# -*- coding: utf-8 -*-
"""FULL-THROAT / make_scaffold.py - the PA12-CF skeleton and the tract mould.

Iddo, 2026-08-29 21:55: a FULL silicone throat on a PA12-CF scaffold, with a
tension servo, an air pump, and an ordinary microphone closing a training loop;
then play a target voice on a speaker beside the mic and let ERAN repeat and
train by himself.

EVERY DIMENSION HERE IS SAWADA-MEASURED, not invented. Source:
alma-larynx/sawada-talking-robot/BUILD-NOTES.md, which cites his papers:
  * tract 180 mm long, bore 36 mm (10.2 cm2)      [JRM2002 p.455 Fig.4]
  * FIVE pinch points already gave him vowels     [JRM2002 p.455]
  * formant sensitivity per pinch station         [JCMSI2016 4.3]
        lip-end    F2 +50 Hz/mm, F3 +40 Hz/mm
        middle     F2 +20 Hz/mm, F3 +20 Hz/mm
        throat-end F1 +15 Hz/mm, F2 +10 Hz/mm
  * design point +200 hPa at 10-16 l/min -> blower, NOT a compressor
  * 125 motor units = 2 mm of pinch               [JCMSI2016 4.3]

WHAT THIS SCRIPT MAKES (parts that do NOT depend on the open fold question):
  1. TRACT-MOULD-core / -shellA / -shellB - cast the soft silicone tract
  2. PINCH-RAIL      - the PA12-CF spine, 5 servo stations, tube cradle
  3. PINCH-BAR       - the press bar a servo drives into the tube (x5)
  4. PINCH-LEVER     - servo horn to bar linkage (x5)

The larynx block that holds the folds is deliberately NOT here: whether it
holds ONE fold against a wall or TWO opposed folds is still open (BUILD-NOTES
Q3, and Sawada's own winner was TWO layered cords). Building it now would be
guessing, and guessing is what the mistake ledger is full of.
"""
import numpy as np
import trimesh

# ---------------- Sawada-derived tract numbers ----------------
BORE = 36.0           # mm, inner diameter of the soft tract
WALL = 4.0            # mm, wall thickness - OPEN QUESTION Q1, this is a start point
LEN = 180.0           # mm, working length
OD = BORE + 2 * WALL  # 44 mm

# five pinch stations, glottis end = 0, lips = 180
STATIONS = [22.0, 57.0, 92.0, 127.0, 158.0]
STATION_ROLE = ["throat F1", "throat/mid", "middle F2/F3", "lip F2/F3", "lip F2/F3"]

# hobby servo envelope (MG996R class, the torque end of what he owns)
SERVO_L, SERVO_W, SERVO_H = 40.7, 19.7, 42.9
SERVO_SCREW_DX = 49.5  # between the two mounting screws

OUT = {}


def box(sx, sy, sz, c=(0, 0, 0)):
    b = trimesh.creation.box(extents=(sx, sy, sz))
    b.apply_translation(c)
    return b


def cyl(r, h, c=(0, 0, 0), axis="z"):
    m = trimesh.creation.cylinder(radius=r, height=h, sections=96)
    if axis == "x":
        m.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [0, 1, 0]))
    elif axis == "y":
        m.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
    m.apply_translation(c)
    return m


# ============================================================
# 1. TRACT MOULD - cast the soft silicone tube
# ============================================================
def tract_mould():
    """Core rod + two shell halves. Silicone is elastic: a straight core rod
    pulls out of a 4 mm wall with release agent. No undercuts anywhere."""
    over = 16.0  # core sticks out both ends to sit in the shell end seats
    total = LEN + 2 * over
    core = cyl(BORE / 2, total, (0, 0, total / 2))
    # a flat on the core so the cast tract has a registration key and cannot spin
    core = trimesh.boolean.difference(
        [core, box(2.0, BORE, total + 4, (BORE / 2 - 0.6, 0, total / 2))])
    OUT["TRACT-MOULD-core.stl"] = core

    shell_od = OD + 2 * 5.0  # 5 mm mould wall -> 54 mm
    body = cyl(shell_od / 2, total, (0, 0, total / 2))
    cavity = cyl(OD / 2, LEN, (0, 0, over + LEN / 2))
    seat_a = cyl(BORE / 2 + 0.15, over + 0.5, (0, 0, over / 2 - 0.25))
    seat_b = cyl(BORE / 2 + 0.15, over + 0.5, (0, 0, LEN + over + over / 2 + 0.25))
    sprue = cyl(5.0, 60, (0, 0, over + 12), axis="y")
    vent = cyl(3.0, 60, (0, 0, over + LEN - 12), axis="y")
    flange = box(shell_od + 26, 9, total, (0, 0, total / 2))
    body = trimesh.boolean.union([body, flange])
    holes = []
    for z in np.linspace(14, total - 14, 6):
        for x in (-(shell_od / 2 + 6), (shell_od / 2 + 6)):
            holes.append(cyl(2.2, 20, (x, 0, z), axis="y"))
    body = trimesh.boolean.difference([body, cavity, seat_a, seat_b, sprue, vent] + holes)
    big = 500
    OUT["TRACT-MOULD-shellA.stl"] = trimesh.boolean.intersection(
        [body, box(big, big, big, (0, big / 2, 0))])
    OUT["TRACT-MOULD-shellB.stl"] = trimesh.boolean.intersection(
        [body, box(big, big, big, (0, -big / 2, 0))])


# ============================================================
# 2. PINCH RAIL - the PA12-CF spine
# ============================================================
def pinch_rail():
    """A spine under the tract carrying five servo stations. The tract lies in
    a half-round cradle; each servo swings a lever that drives a bar down into
    the tube from above. A 10 mm PA12-CF plate is the point: stiff, so the
    reaction force does not steal the pinch depth."""
    rail_len = LEN + 60
    cx = rail_len / 2 - 30
    parts = [box(rail_len, 78, 10, (cx, 0, -5))]
    cuts = [cyl(OD / 2 + 0.4, rail_len + 10, (cx, 0, OD / 2 + 2), axis="x")]
    for s in STATIONS:
        for y in (-(OD / 2 + 9), (OD / 2 + 9)):
            parts.append(box(14, 8, OD + 26, (s, y, (OD + 26) / 2 - 10)))
        cuts.append(cyl(1.6, 140, (s, 0, OD + 10), axis="y"))
        cuts.append(box(SERVO_L + 0.6, SERVO_W + 0.6, 30, (s, 46, -2)))
        for dx in (-SERVO_SCREW_DX / 2, SERVO_SCREW_DX / 2):
            cuts.append(cyl(1.5, 40, (s + dx, 46, -5)))
        parts.append(box(6, OD + 18, OD / 2 + 12, (s + 20, 0, (OD / 2 + 12) / 2 - 10)))
    body = trimesh.boolean.union(parts)
    body = trimesh.boolean.difference([body] + cuts)
    OUT["PINCH-RAIL.stl"] = body


# ============================================================
# 3 + 4. PINCH BAR and LEVER
# ============================================================
def pinch_bar():
    """Sawada pressed with stainless bars radially from outside. Ours is a
    rounded bar, rounded so it deforms the tube instead of cutting it."""
    bar = cyl(3.0, OD + 16, (0, 0, 0), axis="y")
    stem = box(8, 10, 22, (0, 0, 11))
    eye = trimesh.boolean.difference(
        [box(12, 10, 12, (0, 0, 26)), cyl(1.6, 40, (0, 0, 26), axis="y")])
    OUT["PINCH-BAR.stl"] = trimesh.boolean.union([bar, stem, eye])


def pinch_lever():
    """Servo horn to bar, 3:1, so a 9 kg.cm servo has force to spare and the
    horn travel maps onto a few mm of pinch."""
    arm = box(46, 8, 5, (23, 0, 0))
    hub = trimesh.boolean.difference([cyl(7, 5), cyl(2.6, 20)])
    tip = trimesh.boolean.difference([cyl(6, 5, (46, 0, 0)), cyl(1.6, 20, (46, 0, 0))])
    OUT["PINCH-LEVER.stl"] = trimesh.boolean.union([arm, hub, tip])


def main():
    tract_mould()
    pinch_rail()
    pinch_bar()
    pinch_lever()
    print("FULL THROAT SCAFFOLD - printable parts")
    print("=" * 78)
    ok = True
    for name, m in OUT.items():
        e = m.extents
        fits = all(e[i] < 340 for i in range(3))
        wt = m.is_watertight
        if not (fits and wt):
            ok = False
        m.export(name)
        print("%-26s %7d tri  %6.1f x %6.1f x %6.1f mm  watertight=%-5s K2fit=%s"
              % (name, len(m.faces), e[0], e[1], e[2], wt, fits))
    print("=" * 78)
    print("PA12-CF (pacf12 profile, 280C nozzle, 110C bed, SIDE-LOAD external spool,")
    print("         launch from the touchscreen, never the API): RAIL, BAR x5, LEVER x5")
    print("PLA    : TRACT-MOULD-core / shellA / shellB. PLA does not inhibit")
    print("         platinum-cure silicone. Keep latex away from the pour.")
    print("acceptance - all parts watertight and inside the K2 Plus envelope:", ok)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
