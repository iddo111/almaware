#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ARMY MAN — rotate 90 degrees and scale to a real toy-soldier size.
חייל צעצוע — סיבוב 90 מעלות והקטנה לגודל אמיתי.

Source: the Army Man 1.3mf sitting in Creality Print's cloud cache.
3MF is a zip; the geometry is XML inside 3D/Objects/object_1.model (83 MB), so
it is streamed with iterparse rather than loaded whole.

The classic toy soldiers were 1:32 scale, about 54 mm tall. That is the default.

    python make_soldier.py [--height 54] [--rot-x 90]
"""
from __future__ import annotations

import argparse
import math
import os
import struct
import sys
import zipfile
from xml.etree import ElementTree as ET

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SRC = (r"C:\Users\<user>\AppData\Roaming\Creality\Creality Print\7.0"
       r"\cloud_download_data\9613603730\3mfs\Army Man 1.3mf")
OUT_DIR = os.path.dirname(os.path.abspath(__file__))


def load_mesh(path):
    """Stream the 3MF mesh out without holding the 83 MB XML in memory twice."""
    zf = zipfile.ZipFile(path)
    part = next((n for n in zf.namelist() if n.endswith("object_1.model")), None)
    if part is None:
        part = next(n for n in zf.namelist() if n.endswith(".model"))
    verts, tris = [], []
    with zf.open(part) as fh:
        for _event, el in ET.iterparse(fh, events=("end",)):
            tag = el.tag.rsplit("}", 1)[-1]
            if tag == "vertex":
                verts.append((float(el.get("x")), float(el.get("y")), float(el.get("z"))))
                el.clear()
            elif tag == "triangle":
                tris.append((int(el.get("v1")), int(el.get("v2")), int(el.get("v3"))))
                el.clear()
    return verts, tris


def transform(verts, rot_x_deg, target_h):
    """Rotate about X, drop to Z=0, centre in XY, then scale to target height."""
    a = math.radians(rot_x_deg)
    ca, sa = math.cos(a), math.sin(a)
    r = [(x, y * ca - z * sa, y * sa + z * ca) for x, y, z in verts]

    xs = [p[0] for p in r]
    ys = [p[1] for p in r]
    zs = [p[2] for p in r]
    h = max(zs) - min(zs)
    if h <= 0:
        raise SystemExit("model has no height after rotation")
    s = target_h / h
    cx = (max(xs) + min(xs)) / 2.0
    cy = (max(ys) + min(ys)) / 2.0
    z0 = min(zs)
    return [((x - cx) * s, (y - cy) * s, (z - z0) * s) for x, y, z in r], h, s


def write_stl(path, verts, tris, name="army_man"):
    with open(path, "wb") as f:
        f.write(struct.pack("<80s", name.encode()[:80]))
        f.write(struct.pack("<I", len(tris)))
        for i1, i2, i3 in tris:
            a, b, c = verts[i1], verts[i2], verts[i3]
            ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
            vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
            nx, ny, nz = (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)
            L = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
            f.write(struct.pack("<3f", nx / L, ny / L, nz / L))
            for p in (a, b, c):
                f.write(struct.pack("<3f", *p))
            f.write(struct.pack("<H", 0))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--height", type=float, default=54.0,
                    help="finished height in mm (54 = classic 1:32 toy soldier)")
    ap.add_argument("--rot-x", type=float, default=90.0)
    ap.add_argument("--src", default=SRC)
    a = ap.parse_args()

    print("reading %s" % os.path.basename(a.src))
    verts, tris = load_mesh(a.src)
    print("  mesh: %d vertices, %d triangles" % (len(verts), len(tris)))

    xs = [p[0] for p in verts]; ys = [p[1] for p in verts]; zs = [p[2] for p in verts]
    print("  original: %.1f x %.1f x %.1f mm"
          % (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)))

    out, h_after_rot, scale = transform(verts, a.rot_x, a.height)
    ox = [p[0] for p in out]; oy = [p[1] for p in out]; oz = [p[2] for p in out]
    print("  rotated %.0f deg about X -> height %.1f mm, scaled x%.4f"
          % (a.rot_x, h_after_rot, scale))
    print("  FINAL   : %.1f x %.1f x %.1f mm"
          % (max(ox) - min(ox), max(oy) - min(oy), max(oz) - min(oz)))
    print("  sits on bed: z min = %.3f" % min(oz))

    name = "ArmyMan-%.0fmm-rot%.0f.stl" % (a.height, a.rot_x)
    p = os.path.join(OUT_DIR, name)
    write_stl(p, out, tris)
    print("  wrote %s  (%.1f MB)" % (name, os.path.getsize(p) / 1e6))
    return p


if __name__ == "__main__":
    main()
