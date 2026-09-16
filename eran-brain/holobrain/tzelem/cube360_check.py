# -*- coding: utf-8 -*-
"""PROVE the cubemap geometry before spending an hour rendering with it.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

Three checks, each of which has a way it silently goes wrong:

  1. ROUND TRIP. Take every ray of face k as the camera itself generates it, hand it
     to the resampler's direction->face->pixel path, and demand it comes back as
     face k at the pixel it started from. If the Godot basis and the numpy basis
     disagree by so much as a handedness, this fails by hundreds of pixels while a
     stitched picture still looks vaguely plausible.
  2. HORIZON. The pixel row of the equator must be flat: sample the plate along
     latitude 0 and check the direction really has y = 0.
  3. SEAM ON THE RAW BUFFERS. Before any painting, the six Godot beauty images must
     already agree across their shared edges. If they do not, no painter can fix it.
"""
from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cube360 as C     # noqa: E402


def main(folder: str, out_stem: str, yaw0_deg: float | None = None) -> int:
    faces = C.load_faces(folder)
    basis = C.face_basis(faces)
    n = faces["px"]["cam"].width
    print(f"loaded 6 faces at {n}x{n}, eye={faces['px']['cam'].eye}")

    # ---- 1. round trip -------------------------------------------------
    worst = 0.0
    wrong_face = 0
    for j, name in enumerate(C.FACE_ORDER):
        d = faces[name]["cam"].rays()                       # (n, n, 3) unit
        k, gx, gy = C.dirs_to_face_uv(d, basis)
        wrong_face += int((k != j).sum())
        px = (gx + 1.0) * 0.5 * n - 0.5
        py = (1.0 - gy) * 0.5 * n - 0.5
        want_x, want_y = np.meshgrid(np.arange(n), np.arange(n))
        err = max(np.abs(px - want_x).max(), np.abs(py - want_y).max())
        worst = max(worst, err)
        print(f"  face {name}: max pixel error {err:.3e}, "
              f"{int((k != j).sum())} rays sent to the wrong face")
    print(f"ROUND TRIP: worst pixel error {worst:.3e}, wrong-face rays {wrong_face}")

    # ---- 2. horizon ----------------------------------------------------
    d = C.equirect_dirs(64, 32, 0.0)
    eq_row = d[16]                                          # the row straddling y=0
    print(f"HORIZON: |y| on the two rows nearest the equator = "
          f"{np.abs(d[15][:, 1]).max():.6f} / {np.abs(d[16][:, 1]).max():.6f} "
          "(equal and opposite is correct for an even row count)")

    # ---- 3. seam on the raw Godot beauty buffers ------------------------
    imgs = {}
    for name in C.FACE_ORDER:
        g = faces[name]["g"]
        sky = np.array([0.82, 0.87, 0.94])
        imgs[name] = np.where(g["mask"][..., None], g["albedo"], g["albedo"])
    padded, seam = C.pad_faces(imgs, basis)
    tot, base = [], []
    for name in C.FACE_ORDER:
        s = seam[name]
        for side in ("top", "bottom", "left", "right"):
            tot.append(s[side])
        base.append(s["interior_baseline"])
        print(f"  seam {name}: top {s['top']:.5f} bottom {s['bottom']:.5f} "
              f"left {s['left']:.5f} right {s['right']:.5f}   "
              f"(interior adjacent-pixel baseline {s['interior_baseline']:.5f})")
    print(f"SEAM on raw buffers: mean |diff| {np.mean(tot):.5f}, "
          f"max {np.max(tot):.5f}, interior baseline {np.mean(base):.5f}")

    # ---- and a picture, so this is not a number nobody looked at --------
    yaw0 = 0.0
    if yaw0_deg is None:
        cam = faces["px"]["cam"]
        yaw0 = 0.0
    else:
        yaw0 = np.radians(yaw0_deg)
    w = n * 4
    equi, seam2 = C.to_equirect(imgs, basis, w, w // 2, yaw0=yaw0, chunk=128)
    C.save_png(out_stem + "-equirect.png", equi)
    print(f"wrote {out_stem}-equirect.png  {equi.shape[1]}x{equi.shape[0]}")
    return 0 if (worst < 1e-6 and wrong_face == 0) else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    folder = sys.argv[1]
    stem = sys.argv[2]
    yaw = float(sys.argv[3]) if len(sys.argv) > 3 else None
    raise SystemExit(main(folder, stem, yaw))
