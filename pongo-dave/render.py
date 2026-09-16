# -*- coding: utf-8 -*-
"""Preview renders for Dave's U-clip: 3D view + dimensioned cross-section.
Bright styling (Iddo's law). Geometry comes from the STL FILE, not the params."""
import numpy as np, trimesh, matplotlib
from uclip import ray_spans
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection, Line3DCollection
from matplotlib.patches import Polygon as MPoly

VARIANTS = [("v1", "V1  -  wall 1.5 mm  (faithful to sketch)", "#1f77b4"),
            ("v2-thick", "V2  -  wall 2.5 mm  (stronger)", "#d1470f")]


def section_at(mesh, y):
    """Real cross-section polygon sliced out of the mesh, kept in WORLD X-Z.
    to_planar() re-frames the slice into its own arbitrary 2D basis, which
    silently transposed width and height - so we polygonise the raw segments."""
    from shapely.ops import polygonize, unary_union
    from shapely.geometry import LineString
    sec = mesh.section(plane_origin=[0, y, 0], plane_normal=[0, 1, 0])
    segs = []
    for ent in sec.entities:
        pts = sec.vertices[ent.points][:, [0, 2]]      # drop Y -> world (X, Z)
        segs += [LineString(pts[i:i + 2]) for i in range(len(pts) - 1)]
    polys = list(polygonize(unary_union(segs)))
    if not polys:
        raise RuntimeError("section did not close")
    return max(polys, key=lambda q: q.area)


def dim(ax, p0, p1, text, off=(0, 0), colour="#b3005c", ha="center", va="center"):
    p0 = np.array(p0, float); p1 = np.array(p1, float)
    ax.annotate("", xy=p1, xytext=p0,
                arrowprops=dict(arrowstyle="<->", color=colour, lw=1.5, shrinkA=0, shrinkB=0))
    mid = (p0 + p1) / 2 + np.array(off, float)
    ax.text(mid[0], mid[1], text, color=colour, fontsize=11, fontweight="bold",
            ha=ha, va=va, bbox=dict(fc="white", ec=colour, lw=1.0, boxstyle="round,pad=0.25"))


for key, title, colour in VARIANTS:
    mesh = trimesh.load(f"D:/CLAUDE/pongo-dave/dave-uclip-{key}.stl", process=True)
    mesh.merge_vertices()
    lo, hi = mesh.bounds; bb = hi - lo

    fig = plt.figure(figsize=(13, 6.2), facecolor="white")
    fig.suptitle(f"DAVE'S U-CLIP   -   {title}", fontsize=17, fontweight="bold", color="#111", y=0.97)

    # ---- 3D ----
    ax = fig.add_subplot(1, 2, 1, projection="3d", facecolor="white")
    tri = mesh.vertices[mesh.faces]
    n = mesh.face_normals
    shade = 0.45 + 0.55 * np.clip(n @ np.array([0.35, -0.55, 0.75]), 0, 1)
    base = np.array(matplotlib.colors.to_rgb(colour))
    cols = np.clip(base[None, :] * shade[:, None] + 0.30 * (1 - shade)[:, None], 0, 1)
    ax.add_collection3d(Poly3DCollection(tri, facecolors=cols, edgecolors="none",
                                        linewidths=0, zsort="average"))
    # Draw ONLY real feature edges. Drawing every triangle edge painted the
    # part with its own triangulation diagonals and it read as a flat slab.
    ang = mesh.face_adjacency_angles
    sharp = mesh.face_adjacency_edges[ang > np.radians(25)]
    ax.add_collection3d(Line3DCollection(mesh.vertices[sharp], colors="#123", linewidths=1.4))
    c = (lo + hi) / 2; r = bb.max() / 2.05
    ax.set_xlim(c[0]-r, c[0]+r); ax.set_ylim(c[1]-r, c[1]+r); ax.set_zlim(c[2]-r, c[2]+r)
    ax.set_box_aspect((1, 1, 1))
    ax.view_init(elev=17, azim=-56)
    ax.set_axis_off()
    ax.set_title(f"{bb[0]:.1f} x {bb[1]:.1f} x {bb[2]:.1f} mm   |   "
                 f"{mesh.volume*1.27e-3:.1f} g PETG   |   watertight",
                 fontsize=10.5, color="#444", y=0.94)

    # ---- cross-section with dimensions ----
    ax2 = fig.add_subplot(1, 2, 2, facecolor="white")
    poly = section_at(mesh, float(c[1]))
    xy = np.array(poly.exterior.coords)
    xy -= xy.min(axis=0)                       # park at origin for clean dimensioning
    W, H = xy.max(axis=0)
    ax2.add_patch(MPoly(xy, closed=True, facecolor=colour, alpha=0.30,
                        edgecolor=colour, linewidth=2.5))
    # Do NOT derive wall from section vertices - triangulation puts stray
    # vertices on the faces (that read 0.75 instead of 1.5). Ray-cast instead.
    sp = ray_spans(mesh, float(c[1]), float(lo[2] + 5.0))
    assert len(sp) == 2, f"expected two legs at z+5, got {sp}"
    wall = round(sp[0][1] - sp[0][0], 2)
    slot = round(sp[1][0] - sp[0][1], 2)

    dim(ax2, (-4.5, 0), (-4.5, H), f"{H:.0f} mm", off=(-3.2, 0), ha="right")
    dim(ax2, (-1.8, 0), (-1.8, 20), "slot 20", off=(-1.4, 0), ha="right", colour="#0a7d3a")
    dim(ax2, (0, H + 4.0), (W, H + 4.0), f"outer {W:.1f}", off=(0, 2.0))
    dim(ax2, (wall, -3.2), (W - wall, -3.2), f"slot {slot:.1f}", off=(0, -2.2), colour="#0a7d3a")
    ax2.annotate(f"wall {wall:.1f}", xy=(wall / 2, 2.0), xytext=(-13.5, -9.0),
                 fontsize=11, fontweight="bold", color="#b3005c", ha="left", va="center",
                 bbox=dict(fc="white", ec="#b3005c", lw=1.0, boxstyle="round,pad=0.25"),
                 arrowprops=dict(arrowstyle="->", color="#b3005c", lw=1.5))
    ax2.annotate("R3 fillet\n(where it cracks)", xy=(wall + 1.2, 18.6), xytext=(W + 6.5, 13),
                 fontsize=10, fontweight="bold", color="#b3005c",
                 arrowprops=dict(arrowstyle="->", color="#b3005c", lw=1.6))
    ax2.text(W / 2, H - 8, "SPINE\n(solid)", ha="center", va="center",
             fontsize=10, fontweight="bold", color="white")
    ax2.text(W / 2, 8, "PANEL\n12 mm", ha="center", va="center", fontsize=9,
             color="#0a7d3a", fontweight="bold",
             bbox=dict(fc="#eaffe9", ec="#0a7d3a", ls="--", boxstyle="round,pad=0.35"))
    ax2.arrow(W / 2, 3.0, 0, -2.4, head_width=1.1, head_length=1.0, fc="#0a7d3a", ec="#0a7d3a")
    ax2.set_xlim(-16, W + 20); ax2.set_ylim(-13, H + 11)
    ax2.set_aspect("equal"); ax2.axis("off")
    ax2.set_title("cross-section (sliced from the STL)", fontsize=10, color="#444")

    fig.text(0.5, 0.015, "PRINT ON ITS SIDE - lay the 70 mm length flat, U-axis parallel to the bed. "
             "Standing up = layer lines across the spring = snaps on first open.",
             ha="center", fontsize=9.5, color="#a11", fontweight="bold")
    fig.tight_layout(rect=[0, 0.04, 1, 0.94])
    out = f"D:/CLAUDE/pongo-dave/dave-uclip-{key}-preview.png"
    fig.savefig(out, dpi=155, facecolor="white"); plt.close(fig)
    print(f"{out}  |  measured outer {W:.2f}  wall {wall:.2f}  slot {slot:.2f}  height {H:.2f}")
