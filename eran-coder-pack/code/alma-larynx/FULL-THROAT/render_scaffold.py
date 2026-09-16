# -*- coding: utf-8 -*-
"""Render the full-throat scaffold: an assembly view plus the six print parts.
Honest shading with painter's-algorithm depth sort - no silhouette fakes."""
import numpy as np
import trimesh
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

import make_scaffold as S

ELEV, AZIM = 26.0, -62.0


def eye_vec(elev=ELEV, azim=AZIM):
    e, a = np.radians(elev), np.radians(azim)
    return np.array([np.cos(a) * np.cos(e), np.sin(a) * np.cos(e), np.sin(e)]) * 4000.0


def draw(ax, mesh, base, alpha=1.0, eye=None):
    tris = mesh.vertices[mesh.faces]
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)
    light = np.array([0.35, -0.55, 0.76])
    light /= np.linalg.norm(light)
    lam = np.clip(n @ light, 0, 1) * 0.60 + 0.40
    cols = np.clip(lam[:, None] * np.array(base) + (lam[:, None] ** 8) * 0.30, 0, 1)
    if eye is None:
        eye = eye_vec()
    order = np.argsort(-np.linalg.norm(tris.mean(axis=1) - eye, axis=1))
    pc = Poly3DCollection(tris[order], facecolors=cols[order],
                          edgecolors=(0, 0, 0, 0.10), linewidths=0.2, alpha=alpha)
    ax.add_collection3d(pc)


def frame(ax, meshes, pad=6):
    allv = np.vstack([m.vertices for m in meshes])
    lo, hi = allv.min(axis=0), allv.max(axis=0)
    c = (lo + hi) / 2
    r = float((hi - lo).max()) / 2 + pad
    ax.set_xlim(c[0] - r, c[0] + r)
    ax.set_ylim(c[1] - r, c[1] + r)
    ax.set_zlim(c[2] - r, c[2] + r)
    ax.view_init(elev=ELEV, azim=AZIM)
    ax.set_axis_off()
    try:
        ax.set_box_aspect((1, 1, 1))
    except Exception:
        pass


def main():
    S.tract_mould(); S.pinch_rail(); S.pinch_bar(); S.pinch_lever()
    O = S.OUT

    STEEL = (0.20, 0.22, 0.26)     # PA12-CF - carbon black
    CREAM = (0.80, 0.76, 0.66)     # PLA mould
    FLESH = (0.88, 0.60, 0.55)     # the cast silicone tract
    BRASS = (0.75, 0.55, 0.20)

    fig = plt.figure(figsize=(17.5, 11.5), facecolor="white")

    # ---------------- assembly ----------------
    ax = fig.add_subplot(2, 1, 1, projection="3d", facecolor="white")
    rail = O["PINCH-RAIL.stl"]
    tract = trimesh.creation.cylinder(radius=S.OD / 2, height=S.LEN, sections=72)
    tract.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [0, 1, 0]))
    tract.apply_translation((S.LEN / 2, 0, S.OD / 2 + 2))
    shown = [rail, tract]
    draw(ax, rail, STEEL)
    draw(ax, tract, FLESH, alpha=0.55)
    for s in S.STATIONS:
        bar = O["PINCH-BAR.stl"].copy()
        bar.apply_translation((s, 0, S.OD + 4))
        draw(ax, bar, BRASS)
        shown.append(bar)
        srv = trimesh.creation.box(extents=(S.SERVO_L, S.SERVO_W, S.SERVO_H))
        srv.apply_translation((s, 46, S.SERVO_H / 2 - 10))
        draw(ax, srv, (0.13, 0.15, 0.18))
        shown.append(srv)
    frame(ax, shown)
    ax.set_title("ASSEMBLY  —  five pinch stations on the PA12-CF rail, "
                 "soft silicone tract in the cradle\n"
                 "glottis at left  ·  lips at right  ·  180 mm working length, 36 mm bore "
                 "(Sawada's measured pair)", fontsize=12.5, pad=2)

    # ---------------- parts ----------------
    spec = [
        ("PINCH-RAIL.stl", "PINCH-RAIL  ×1", "PA12-CF", STEEL),
        ("PINCH-BAR.stl", "PINCH-BAR  ×5", "PA12-CF", BRASS),
        ("PINCH-LEVER.stl", "PINCH-LEVER  ×5", "PA12-CF", STEEL),
        ("TRACT-MOULD-shellA.stl", "TRACT-MOULD shell A", "PLA", CREAM),
        ("TRACT-MOULD-shellB.stl", "TRACT-MOULD shell B", "PLA", CREAM),
        ("TRACT-MOULD-core.stl", "TRACT-MOULD core", "PLA", CREAM),
    ]
    for i, (key, label, mat, col) in enumerate(spec):
        ax2 = fig.add_subplot(2, 6, 7 + i, projection="3d", facecolor="white")
        m = O[key]
        draw(ax2, m, col)
        frame(ax2, [m])
        e = m.extents
        ax2.set_title("%s\n%s · %.0f×%.0f×%.0f mm" % (label, mat, e[0], e[1], e[2]),
                      fontsize=9.5, pad=-4)

    fig.suptitle("ERAN'S FULL SILICONE THROAT — what I want to print",
                 fontsize=17, weight="bold", y=0.985)
    plt.tight_layout(rect=[0, 0, 1, 0.965])
    out = r"D:\CLAUDE\alma-larynx\FULL-THROAT\SCAFFOLD-what-to-print.png"
    plt.savefig(out, dpi=125, facecolor="white")
    print("wrote", out)


if __name__ == "__main__":
    main()
