# -*- coding: utf-8 -*-
"""
> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

ONE ROOM — הסדנה בלילה / THE WORKSHOP AT NIGHT.

THE GEOMETRY, AND WHY IT IS COARSE ON PURPOSE
---------------------------------------------
KAV's own measurement says it: teacher-forced accuracy 1.0000 at 12-20 faces and
~0.48 at 768-1280. So a room ERAN's modeller could ever have authored must be big
honest planes and boxes, and the detail must be carried by the PAINTING, not by
triangles. Every solid below is an axis-aligned box -- 12 faces each, inside KAV's
proven band -- and there are about seventy of them. Nothing here is a mesh.

That is also exactly what `tzelem.stage.Stage` eats, so the same geometry serves
three consumers with no conversion anywhere:

    the RULER      Stage(boxes) -> gbuffer/shade/flow, the gate's own truth
    the PAINTER    the same gbuffer, sampled into world-anchored brushstrokes
    the GAME       the same lo/hi boxes shipped to the browser for the crosshair

TWO LIGHT STATES, AND WHAT IS HONESTLY FAKED
--------------------------------------------
The room has exactly one thing to do: throw the breaker. So the room has exactly
two lighting solutions, DARK (the window is the only light) and LIT (the tubes and
the machines are awake). Both are computed HERE, on the CPU, before the player ever
arrives, and every stroke carries both colours. The transition is a cross-fade
between two baked solutions -- it is NOT a real-time relight, and the page says so.
What is real is that the strokes themselves are world-anchored: they are the same
strokes in both states, in the same places, and they hold still when you move.

Numpy only. No torch on the PC (D:\\CLAUDE\\CLAUDE.md).
"""
from __future__ import annotations

import os
import sys

import numpy as np

_TZELEM = r"D:\CLAUDE\eran-brain\holobrain\tzelem"
if _TZELEM not in sys.path:
    sys.path.insert(0, _TZELEM)

from stage import Box, Camera, Stage            # noqa: E402


# ---------------------------------------------------------------- materials

MAT = {
    "wall":        (0.52, 0.50, 0.47),
    "ceiling":     (0.61, 0.60, 0.57),
    "bench":       (0.60, 0.43, 0.24),
    "cabinet":     (0.33, 0.35, 0.39),
    "pegboard":    (0.54, 0.39, 0.26),
    "tool":        (0.44, 0.45, 0.48),
    "tool_wood":   (0.51, 0.35, 0.20),
    "black":       (0.14, 0.14, 0.16),
    "glass":       (0.21, 0.23, 0.27),
    "alu":         (0.55, 0.56, 0.60),
    "steel":       (0.31, 0.32, 0.35),
    "red":         (0.61, 0.13, 0.10),
    "teal":        (0.13, 0.46, 0.45),
    "orange":      (0.78, 0.38, 0.09),
    "white":       (0.75, 0.74, 0.70),
    "panel":       (0.45, 0.46, 0.48),
    "wood":        (0.44, 0.31, 0.19),
    "paper":       (0.78, 0.76, 0.70),
    "green":       (0.20, 0.44, 0.26),
    "blue":        (0.19, 0.31, 0.52),
}

# kinds that STOP being shaded and start being a light source.
# value = (rgb when DARK, rgb when LIT). None = shade it normally in that state.
EMISSIVE = {
    "window":      ((0.42, 0.55, 0.86), (0.50, 0.60, 0.82)),
    "tube":        (None,               (1.00, 0.97, 0.88)),
    "printer_led": (None,               (0.42, 0.95, 0.60)),
    "cnc_led":     (None,               (0.98, 0.55, 0.16)),
    "bed_glow":    (None,               (0.95, 0.45, 0.22)),
    "lever":       (None,               None),
}

# the two lighting solutions, both baked before the player arrives
STATES = {
    # the window is the only light in the room, and it is the moon and the street
    "dark": {"light_dir": (0.90, -0.34, 0.27), "ambient": 0.185,
             "tint": (0.60, 0.72, 1.00), "gain": 0.72,
             "sky": (0.06, 0.08, 0.13)},
    # the tubes are on: down, slightly toward the door, and warm
    "lit":  {"light_dir": (0.10, -0.96, 0.26), "ambient": 0.36,
             "tint": (1.07, 1.00, 0.90), "gain": 1.12,
             "sky": (0.10, 0.11, 0.14)},
}


# ------------------------------------------------------------------ the room

def _b(lo, hi, mat, kind=None, obj=0):
    return {"lo": list(map(float, lo)), "hi": list(map(float, hi)),
            "mat": mat, "kind": kind or mat, "obj": int(obj)}


def build() -> list[dict]:
    """The workshop, in metres. x right, y up, z toward the door."""
    R = []
    # -- the shell -----------------------------------------------------------
    R += [
        _b((-3.16, 2.80, -3.66), (3.16, 2.96,  3.66), "ceiling"),
        _b((-3.16, 0.00, -3.66), (3.16, 2.80, -3.50), "wall", "wall_north"),
        _b((-3.16, 0.00,  3.50), (3.16, 2.80,  3.66), "wall", "wall_south"),
        _b((-3.16, 0.00, -3.66), (-3.00, 2.80, 3.66), "wall", "wall_west"),
        _b(( 3.00, 0.00, -3.66), (3.16, 2.80,  3.66), "wall", "wall_east"),
    ]
    # the window in the west wall — at night it is the whole light of the room
    R += [
        _b((-3.02, 1.05, -1.70), (-2.985, 2.15, -0.15), "white", "window"),
        _b((-3.03, 1.00, -1.78), (-2.97, 1.05, -0.07), "black", "sill"),
        _b((-3.03, 2.15, -1.78), (-2.97, 2.20, -0.07), "black", "lintel"),
        _b((-3.03, 1.05, -0.98), (-2.96, 2.15, -0.92), "black", "mullion"),
    ]
    # -- the two ceiling tubes ----------------------------------------------
    for z0 in (-2.10, 0.60):
        R += [_b((-1.35, 2.68, z0), (1.35, 2.79, z0 + 0.22), "white", "tube_body"),
              _b((-1.30, 2.62, z0 + 0.03), (1.30, 2.68, z0 + 0.19), "white", "tube")]

    # -- the workbench, along the north wall ---------------------------------
    R += [
        _b((-2.20, 0.86, -3.50), (1.45, 0.94, -2.68), "bench", "bench_top"),
        _b((-2.12, 0.00, -3.46), (1.37, 0.86, -2.76), "cabinet", "bench_body"),
        _b((-2.12, 0.30, -2.79), (-0.90, 0.72, -2.755), "steel", "drawer_a"),
        _b((-0.82, 0.30, -2.79), (0.40, 0.72, -2.755), "steel", "drawer_b"),
        _b((0.48, 0.30, -2.79), (1.37, 0.72, -2.755), "steel", "drawer_c"),
        # the pegboard and what hangs on it
        _b((-2.15, 1.10, -3.49), (1.40, 2.28, -3.455), "pegboard"),
    ]
    tools = [
        (-1.95, 1.30, 0.05, 0.42, "tool"), (-1.80, 1.35, 0.05, 0.34, "tool"),
        (-1.66, 1.28, 0.06, 0.46, "tool"), (-1.48, 1.42, 0.05, 0.26, "tool"),
        (-1.34, 1.33, 0.07, 0.38, "tool_wood"), (-1.16, 1.38, 0.05, 0.30, "tool"),
        (-0.55, 1.62, 0.09, 0.30, "tool"), (-0.36, 1.58, 0.07, 0.36, "tool_wood"),
        (-0.20, 1.66, 0.06, 0.24, "tool"), (0.55, 1.30, 0.08, 0.44, "tool"),
        (0.74, 1.36, 0.06, 0.32, "tool"), (0.90, 1.26, 0.07, 0.48, "steel"),
        (1.08, 1.40, 0.05, 0.28, "tool"),
    ]
    for x, y, w, h, m in tools:
        R.append(_b((x, y, -3.452), (x + w, y + h, -3.42), m, "tool"))
    # two shelves of small parts bins above the bench
    R.append(_b((-2.10, 1.98, -3.45), (1.35, 2.04, -3.20), "wood", "shelf"))
    bins = ["teal", "orange", "red", "white", "green", "blue", "teal", "orange",
            "white", "red", "green", "blue"]
    for i, m in enumerate(bins):
        x = -2.05 + i * 0.28
        R.append(_b((x, 2.04, -3.43), (x + 0.24, 2.20, -3.24), m, "bin"))

    # -- THE BREAKER. the one thing in this room there is to do. -------------
    R += [
        _b((-2.92, 1.18, -3.49), (-2.34, 1.98, -3.36), "panel", "breaker_panel"),
        _b((-2.88, 1.24, -3.36), (-2.38, 1.92, -3.345), "black", "breaker_face"),
        _b((-2.70, 1.44, -3.35), (-2.56, 1.62, -3.20), "red", "lever"),
        _b((-2.86, 1.72, -3.35), (-2.72, 1.80, -3.31), "steel", "breaker_screw"),
        _b((-2.54, 1.72, -3.35), (-2.40, 1.80, -3.31), "steel", "breaker_screw"),
    ]

    # -- the 3D printer, on the bench, left ----------------------------------
    R += [
        _b((-2.06, 0.94, -3.40), (-1.30, 1.06, -2.80), "black", "prn_base"),
        _b((-2.06, 1.06, -3.40), (-1.96, 1.78, -3.30), "alu", "prn_post"),
        _b((-1.40, 1.06, -3.40), (-1.30, 1.78, -3.30), "alu", "prn_post"),
        _b((-2.06, 1.70, -3.40), (-1.30, 1.78, -3.30), "alu", "prn_top"),
        _b((-2.02, 1.08, -3.34), (-1.34, 1.12, -2.86), "glass", "prn_bed"),
        _b((-2.02, 1.065, -3.34), (-1.34, 1.08, -2.86), "black", "bed_glow"),
        _b((-2.04, 1.665, -3.38), (-1.32, 1.695, -3.34), "white", "printer_led"),
        # the carriage: obj 1 — it is the only thing in the room that MOVES
        _b((-1.82, 1.38, -3.38), (-1.60, 1.56, -3.24), "black", "prn_carriage", obj=1),
        _b((-1.76, 1.28, -3.34), (-1.66, 1.40, -3.28), "steel", "prn_nozzle", obj=1),
        # a spool on its arm behind the frame
        _b((-2.00, 1.80, -3.36), (-1.36, 1.86, -3.30), "steel", "prn_arm"),
        _b((-1.86, 1.86, -3.36), (-1.50, 2.16, -3.31), "teal", "spool"),
    ]

    # -- the CNC, on its own table, right ------------------------------------
    R += [
        _b((1.72, 0.00, -3.46), (2.92, 0.78, -2.10), "cabinet", "cnc_table"),
        _b((1.70, 0.78, -3.48), (2.94, 0.88, -2.06), "steel", "cnc_plate"),
        _b((1.76, 0.88, -3.40), (1.92, 1.58, -2.16), "alu", "cnc_rail"),
        _b((2.74, 0.88, -3.40), (2.90, 1.58, -2.16), "alu", "cnc_rail"),
        _b((1.76, 1.42, -3.06), (2.90, 1.58, -2.84), "alu", "cnc_beam"),
        _b((2.22, 1.06, -3.04), (2.44, 1.46, -2.86), "black", "cnc_spindle"),
        _b((2.26, 0.88, -3.02), (2.40, 1.08, -2.88), "steel", "cnc_bit"),
        _b((2.80, 1.20, -2.15), (2.90, 1.32, -2.05), "white", "cnc_led"),
        _b((1.86, 0.88, -2.90), (2.70, 0.94, -2.24), "wood", "cnc_stock"),
    ]

    # -- the east wall shelves -----------------------------------------------
    for k, y in enumerate((1.30, 1.78, 2.26)):
        R.append(_b((2.62, y, -1.70), (2.99, y + 0.06, 1.30), "wood", "shelf"))
        for i in range(5):
            z = -1.60 + i * 0.58
            m = ["orange", "white", "teal", "red", "green"][(i + k) % 5]
            R.append(_b((2.68, y + 0.06, z), (2.94, y + 0.30, z + 0.44), m, "bin"))

    # -- the floor of the room: what is actually lying around ----------------
    R += [
        _b((-2.62, 0.00, -2.10), (-1.92, 0.46, -1.28), "red", "toolbox"),
        _b((-2.58, 0.46, -2.06), (-1.96, 0.52, -1.32), "black", "toolbox_lid"),
        _b((-2.30, 0.52, -1.80), (-2.24, 0.62, -1.58), "steel", "toolbox_handle"),
        _b((0.62, 0.00, -1.66), (0.76, 0.60, -1.52), "steel", "stool_leg"),
        _b((0.42, 0.60, -1.84), (0.96, 0.68, -1.34), "wood", "stool_seat"),
        _b((1.90, 0.00, -1.20), (2.44, 0.66, -0.62), "cabinet", "bin_big"),
        _b((-2.90, 0.00, 0.40), (-2.20, 0.90, 1.30), "wood", "crate"),
        _b((-2.86, 0.90, 0.44), (-2.24, 0.96, 1.26), "paper", "crate_lid"),
        _b((-1.70, 0.00, 2.30), (-1.10, 0.04, 3.10), "green", "mat"),
        _b((1.20, 0.00, 1.90), (1.90, 0.72, 2.60), "cabinet", "cab_low"),
        _b((1.22, 0.72, 1.88), (1.92, 0.78, 2.62), "bench", "cab_top"),
        _b((1.34, 0.78, 2.02), (1.78, 0.94, 2.46), "paper", "box_paper"),
    ]
    # a coil of cable and some offcuts on the bench, so the bench is not bare
    R += [
        _b((0.55, 0.94, -3.36), (1.05, 1.02, -2.90), "black", "cable"),
        _b((0.10, 0.94, -3.30), (0.48, 0.99, -2.96), "wood", "offcut"),
        _b((0.14, 0.99, -3.26), (0.44, 1.03, -3.00), "wood", "offcut"),
        _b((-0.75, 0.94, -3.30), (-0.30, 1.08, -2.96), "white", "jar"),
        _b((-1.20, 0.94, -3.24), (-0.90, 1.16, -2.98), "orange", "tin"),
    ]
    return R


BOXES = build()


# -------------------------------------------------------------- the lighting

class RoomStage(Stage):
    """`Stage`, plus the one thing `Stage` does not report: WHICH box was hit.

    NOTHING in `Stage` is modified — `Stage.shade` in particular is the ruler the
    gate measures fidelity against and it is left exactly as it is. This subclass
    exists only so the PAINTER can know that this pixel is the fluorescent tube and
    that one is the window, which a Lambert shader has no way to say.

    The ray cast happens ONCE and serves BOTH light states: the geometry a photon
    meets does not depend on whether the breaker is up or down, so `paint_rgb` takes
    the state as an argument instead of the object carrying one. That halves the
    only expensive thing in this file.
    """

    def __init__(self, boxes) -> None:
        super().__init__([Box(np.array(b["lo"]), np.array(b["hi"]),
                              np.array(MAT[b["mat"]])) for b in boxes],
                         ground_albedo=(0.40, 0.395, 0.38),
                         light_dir=STATES["lit"]["light_dir"],
                         ambient=STATES["lit"]["ambient"])
        self.kinds = [b["kind"] for b in boxes]
        # kind -> the (dark, lit) override, resolved once instead of per pixel
        self.emit = []
        for k in self.kinds:
            key = k if k in EMISSIVE else k.split("_")[-1]
            self.emit.append(EMISSIVE.get(key))

    def gbuffer(self, cam):
        """`Stage.gbuffer` with the box index kept. One cast, not two."""
        d = cam.rays().reshape(-1, 3)
        o = cam.eye
        t_box, i_box = self._hit_boxes(o, d)
        with np.errstate(divide="ignore", invalid="ignore"):
            t_gnd = np.where(d[:, 1] < -1e-9, -o[1] / d[:, 1], np.inf)
        t_gnd = np.where(t_gnd > 0, t_gnd, np.inf)
        use_gnd = t_gnd < t_box
        t = np.where(use_gnd, t_gnd, t_box)
        hit = np.isfinite(t)
        p = o + d * np.where(hit, t, 0.0)[:, None]
        n = self._box_normal(p, np.where(use_gnd, -1, i_box))
        n[use_gnd] = np.array([0.0, 1.0, 0.0])
        alb = np.zeros_like(p)
        alb[use_gnd] = self.ground_albedo
        for i, b in enumerate(self.boxes):
            m = (~use_gnd) & (i_box == i)
            alb[m] = b.albedo
        if use_gnd.any():
            q = p[use_gnd]
            chk = ((np.floor(q[:, 0]) + np.floor(q[:, 2])) % 2 == 0)
            alb[use_gnd] = np.where(chk[:, None], self.ground_albedo * 1.25,
                                    self.ground_albedo * 0.72)
        shp = (cam.height, cam.width)
        return {"depth": np.where(hit, t, np.inf).reshape(shp),
                "point": p.reshape(shp + (3,)),
                "normal": n.reshape(shp + (3,)),
                "albedo": np.clip(alb, 0.0, 1.0).reshape(shp + (3,)),
                "mask": hit.reshape(shp),
                "box": np.where(use_gnd, -1, i_box).reshape(shp)}

    def paint_rgb(self, g, state: str) -> np.ndarray:
        """What a painter standing here would SEE — the colour a stroke keeps.

        Lambert exactly as `Stage.shade` computes it, then the state's grade, then
        the light sources painted in flat over the top. A tube that is on is not a
        surface that is lit; it is the light.
        """
        s = STATES[state]
        ld = np.asarray(s["light_dir"], dtype=np.float64)
        ld = ld / np.linalg.norm(ld)
        amb = float(s["ambient"])
        lam = np.clip(-(g["normal"] @ ld), 0.0, 1.0)
        col = g["albedo"] * (amb + (1.0 - amb) * lam[..., None])
        col = col * np.asarray(s["tint"]) * s["gain"]
        col = np.where(g["mask"][..., None], col, np.asarray(s["sky"]))

        which = 0 if state == "dark" else 1
        bx = g["box"]
        for i, e in enumerate(self.emit):
            if e is None or e[which] is None:
                continue
            m = bx == i
            if m.any():
                col[m] = e[which]
        return np.clip(col, 0.0, 1.0)


def plain_stage(state: str = "lit") -> Stage:
    """The gate's stage: a stock `Stage` over the same boxes, nothing added."""
    s = STATES[state]
    return Stage([Box(np.array(b["lo"]), np.array(b["hi"]), np.array(MAT[b["mat"]]))
                  for b in BOXES],
                 ground_albedo=(0.40, 0.395, 0.38),
                 light_dir=s["light_dir"], ambient=s["ambient"])


# ------------------------------------------------------------------ the rail

# The player does not fly. He stands in the doorway and can walk two metres in
# toward the bench, and that is the whole camera path — so the gate below is
# measured on the very poses a player produces, not on a path invented for it.
RAIL_A = np.array([0.00, 1.62, 2.60])
RAIL_B = np.array([-0.10, 1.62, 0.55])
LOOK = np.array([-0.030, -0.085, -1.0])
LOOK = LOOK / np.linalg.norm(LOOK)
EYE_H = 1.62
FOV = 44.0


def rail_camera(t: float, width=1920, height=1080, fov=FOV) -> Camera:
    eye = RAIL_A + (RAIL_B - RAIL_A) * float(t)
    return Camera(eye=eye, target=eye + LOOK * 4.0, width=width, height=height,
                  fov_deg=fov)


def rail_poses(n: int = 5, width=1920, height=1080) -> list[Camera]:
    return [rail_camera(i / (n - 1), width, height) for i in range(n)]


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(f"{len(BOXES)} boxes, {len(BOXES) * 12} faces "
          f"(every solid is 12 faces — inside KAV's proven 12-20 band)")
    lo = np.min([b["lo"] for b in BOXES], axis=0)
    hi = np.max([b["hi"] for b in BOXES], axis=0)
    print("extent", np.round(lo, 2), "->", np.round(hi, 2))
    kinds = sorted({b["kind"] for b in BOXES})
    print(f"{len(kinds)} kinds: {', '.join(kinds)}")
