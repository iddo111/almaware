"""build_cone_decor.py — dress the EXISTING 'Joint Case 115mm' cone with
barber/lighthouse spiral stripes + vertical 'iddoperez.ai' lettering.

Iddo 2026-08-20 19:38: "תיקח את הקייס הקיים ופשוט שני אותו קצת — הצבעוניות
נכונה, הרעיון נכון, אבל אצלי זה קונוס." The body/cap meshes are NOT rebuilt —
they are the original meshes from the 3mf; only decor is added, following the
cone's real radius profile r(z) measured from the mesh itself.

Outputs (same world frame, import all four as ONE multi-part object):
  cone_body.stl    -> filament 2 (light body)
  cone_stripes.stl -> filament 1 (orange spiral)
  cone_text.stl    -> filament 4 (blue lettering)
  cone_cap.stl     -> filament 3 (purple, its own world)
"""
import math
import numpy as np
import trimesh

SRC = (r"C:\Users\<user>\AppData\Roaming\Creality\Creality Print"
       r"\7.0\cloud_download_data\9613603730\3mfs\Joint Case 115mm.3mf")
OUT = r"D:\CLAUDE\joint-holder"

sc = trimesh.load(SRC)
meshes = sc.dump()                       # transforms applied -> world frame
meshes.sort(key=lambda m: -(m.bounds[1][2] - m.bounds[0][2]))
body, cap = meshes[0], meshes[1]

# ---- body axis + radius profile r(z) ----------------------------------------
c = body.bounds.mean(axis=0)
cx, cy = c[0], c[1]
z0, z1 = body.bounds[0][2], body.bounds[1][2]
V = body.vertices
rad = np.hypot(V[:, 0] - cx, V[:, 1] - cy)
zs = V[:, 2]
NB = 60
edges = np.linspace(z0, z1, NB + 1)
prof = np.zeros(NB)
for i in range(NB):
    m = (zs >= edges[i]) & (zs <= edges[i + 1])
    prof[i] = rad[m].max() if m.any() else np.nan
ok = ~np.isnan(prof)
prof_z = (edges[:-1] + edges[1:]) / 2


def r_at(z):
    return float(np.interp(z, prof_z[ok], prof[ok]))


print(f"body z {z0:.1f}..{z1:.1f}  r(bottom)={r_at(z0+2):.2f}  r(top)={r_at(z1-2):.2f}")

TRIS = {"stripes": [], "text": []}


def quad(buf, a, b, c2, d):
    buf.append((a, b, c2))
    buf.append((a, c2, d))


def surf_box(buf, z_lo, z_hi, th_lo, th_hi, embed=0.35, raise_=0.75, n_arc=4):
    """A radial box that follows the cone surface between two z and two angles."""
    ths = np.linspace(th_lo, th_hi, n_arc + 1)
    zc = (z_lo + z_hi) / 2

    def ring(th, z, dr):
        r = r_at(z) + dr
        return (cx + r * math.cos(th), cy + r * math.sin(th), z)

    for i in range(n_arc):
        t0, t1 = ths[i], ths[i + 1]
        for (za, zb) in [(z_lo, z_hi)]:
            io = -embed
            oo = raise_
            a0, a1 = ring(t0, za, io), ring(t1, za, io)
            b0, b1 = ring(t0, zb, io), ring(t1, zb, io)
            A0, A1 = ring(t0, za, oo), ring(t1, za, oo)
            B0, B1 = ring(t0, zb, oo), ring(t1, zb, oo)
            quad(buf, A0, A1, B1, B0)          # outer face
            quad(buf, a0, b0, b1, a1)          # inner face
            quad(buf, a0, a1, A1, A0)          # bottom rim
            quad(buf, b0, B0, B1, b1)          # top rim
        if i == 0:
            za_, zb_ = z_lo, z_hi
            p = [ring(t0, za_, -embed), ring(t0, zb_, -embed),
                 ring(t0, zb_, raise_), ring(t0, za_, raise_)]
            quad(buf, *p)
        if i == n_arc - 1:
            p = [ring(t1, za_, -embed), ring(t1, za_, raise_),
                 ring(t1, zb_, raise_), ring(t1, zb_, -embed)]
            quad(buf, *p)


# ---- spiral stripes: 2 helix starts, 2 turns, band 4.5mm --------------------
H = z1 - z0
TURNS, BAND, STEP = 2.0, 4.5, 140
for start in (0.0, math.pi):
    zsamp = np.linspace(z0 + 1.5, z1 - 1.5 - BAND, STEP)
    for i in range(STEP - 1):
        za, zb = zsamp[i], zsamp[i + 1]
        tha = start + TURNS * 2 * math.pi * (za - z0) / H
        thb = start + TURNS * 2 * math.pi * (zb - z0) / H
        surf_box(TRIS["stripes"], za, za + BAND, tha, thb, n_arc=1)

# ---- vertical lettering (chunky cell font, reads bottom -> top) -------------
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
cell = 1.15                                   # mm per font unit
ch_span, gap = 5 * cell, 1.6                  # char length along z
z_text = z0 + 6.0
TH0 = math.pi / 2                             # lettering meridian (front)
arc_mm = 1.15                                 # mm per font row along the arc
for ch in TEXT:
    for (fx, fz, w, h) in F[ch]:
        za = z_text + fx * cell
        zb = za + w * cell
        rm = r_at((za + zb) / 2)
        th_a = TH0 + ((fz - 3.5) * arc_mm) / rm
        th_b = TH0 + ((fz + h - 3.5) * arc_mm) / rm
        surf_box(TRIS["text"], za, zb, th_a, th_b, embed=0.35, raise_=0.85, n_arc=2)
    z_text += ch_span + gap
print(f"text ends at z={z_text:.1f} (top={z1:.1f})")


def save(tris, name):
    arr = np.array(tris)
    m = trimesh.Trimesh(vertices=arr.reshape(-1, 3),
                        faces=np.arange(len(arr) * 3).reshape(-1, 3))
    m.export(f"{OUT}\\{name}")
    print(name, len(arr), "tris")


save(TRIS["stripes"], "cone_stripes.stl")
save(TRIS["text"], "cone_text.stl")
body.export(f"{OUT}\\cone_body.stl")
cap.export(f"{OUT}\\cone_cap.stl")
print("body+cap exported unchanged (world frame)")
