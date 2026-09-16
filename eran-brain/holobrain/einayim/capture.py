"""EINAYIM / עֵינַיִם — REAL PHOTOS -> A MESH. (eran3, GPU)

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

score.py measures against a truth we own. This file is the other half: photos of a
REAL object, where there is no truth and the only honest thing to report is what
the model was confident about and how big the result is.

Two things are different from the ground-truth path and both are stated on purpose:

  * SCALE IS UNKNOWN. A feed-forward model returns a scene up to one similarity.
    The mesh that comes out of here is the right SHAPE and the wrong SIZE, and
    nothing in this file pretends otherwise — `scale_is_arbitrary: true` goes into
    the sidecar json. A ruler in the photograph, or a known camera baseline, is
    what fixes it. (A depth camera would fix it for free — see the report.)

  * THE VOLUME'S BOUNDS come from the model's own confident points, not from a
    truth cloud. That is the only choice available, and it means a bad prediction
    gets a bad bounding box too.
"""
from __future__ import annotations

import argparse
import json
import os

import numpy as np


def points_from_pred(P, conf_pct=50.0):
    """Per-pixel world points from the model's depth + camera, confidence-filtered."""
    depth, conf = P["depth"], P["depth_conf"]
    E, K = P["extrinsic"], P["intrinsic"]
    S, H, W = depth.shape
    thr = float(np.percentile(conf, conf_pct))
    pts, keep = [], []
    u, v = np.meshgrid(np.arange(W), np.arange(H))
    for k in range(S):
        z = depth[k]
        x = (u - K[k][0, 2]) / K[k][0, 0] * z
        y = (v - K[k][1, 2]) / K[k][1, 1] * z
        Xc = np.stack([x, y, z], -1)
        pts.append((Xc - E[k][:, 3]) @ E[k][:, :3])
        keep.append((conf[k] >= thr) & (z > 0))
    return np.stack(pts), np.stack(keep), thr


def centre_box(pts, keep, frac, grow=0.30):
    """Bound the volume to whatever is in the MIDDLE of the frame.

    EINAYIM does not segment anything, and a fused scene is mostly floor: the
    first drop test spent all 1,500 faces on a terraced floor and none on the
    object. When somebody walks around one thing, that thing is in the middle of
    every frame — so the central patch of view 0 chooses the box, and the rest of
    the room is simply outside it. Crude, stated, and much better than nothing.
    """
    H, W = keep.shape[1:]
    y0, y1 = int(H * (1 - frac) / 2), int(H * (1 + frac) / 2)
    x0, x1 = int(W * (1 - frac) / 2), int(W * (1 + frac) / 2)
    sel = np.zeros_like(keep[0]); sel[y0:y1, x0:x1] = True
    core = pts[0][keep[0] & sel]
    if len(core) < 200:
        return None
    lo, hi = np.percentile(core, 2, axis=0), np.percentile(core, 98, axis=0)
    pad = (hi - lo) * grow
    return lo - pad, hi + pad


def drop_dominant_plane(pts, tol_frac=0.012, iters=300, seed=0):
    """RANSAC away the biggest flat thing, because it is the table.

    Everything anyone photographs is standing ON something, and that something is
    usually the largest surface in the cloud. The centre-of-frame heuristic alone
    did not save the first drop test — the floor is in the middle of the frame too,
    and all 1,459 faces went to a terraced floor. Removing the dominant plane is
    what actually leaves the object. If less than 15% of the cloud is planar there
    is no table, and nothing is removed.
    """
    rng = np.random.default_rng(seed)
    n = len(pts)
    tol = tol_frac * float(np.linalg.norm(pts.max(0) - pts.min(0)))
    sub = pts[rng.choice(n, min(n, 60_000), replace=False)]
    best, best_pl = 0, None
    for _ in range(iters):
        q = sub[rng.choice(len(sub), 3, replace=False)]
        nrm = np.cross(q[1] - q[0], q[2] - q[0])
        ln = np.linalg.norm(nrm)
        if ln < 1e-12:
            continue
        nrm = nrm / ln
        d = -nrm @ q[0]
        c = int((np.abs(sub @ nrm + d) < tol).sum())
        if c > best:
            best, best_pl = c, (nrm, d)
    if best_pl is None or best < 0.15 * len(sub):
        return pts, {"plane_found": False}
    nrm, d = best_pl
    off = pts @ nrm + d
    keep = np.abs(off) >= tol
    # keep only the side of the plane the object is on (the fuller half)
    above, below = keep & (off > 0), keep & (off < 0)
    keep = above if above.sum() >= below.sum() else below
    if keep.sum() < 500:
        return pts, {"plane_found": True, "plane_kept": False}
    return pts[keep], {"plane_found": True, "plane_kept": True,
                       "plane_inlier_frac": best / len(sub),
                       "normal": nrm.tolist(), "offset": float(d), "tol": float(tol),
                       "side": 1.0 if above.sum() >= below.sum() else -1.0,
                       "removed_frac": 1 - float(keep.mean())}


def capture_mesh(pred_npz, out_stem, conf_pct=50.0, voxels=256, target_faces=2000,
                 trim=1.5, centre_frac=0.0, drop_plane=False):
    from fuse import tsdf_mesh, write_stl, decimate_faces, watertight
    P = np.load(pred_npz, allow_pickle=True)
    pts, keep, thr = points_from_pred(P, conf_pct)
    good = pts[keep]
    if len(good) < 1000:
        raise SystemExit("the model was confident about almost nothing")

    # Trim the long tail before choosing the volume: a handful of runaway points
    # would otherwise set a bounding box a hundred times too big and the voxels
    # would be coarser than the object.
    c = np.median(good, axis=0)
    r = np.linalg.norm(good - c, axis=1)
    good = good[r <= np.percentile(r, 99.0) * trim]
    plane = {"plane_found": None}
    if drop_plane:
        good, plane = drop_dominant_plane(good)
    box = centre_box(pts, keep, centre_frac) if centre_frac > 0 else None
    if box is not None:
        inside = np.all((good >= box[0]) & (good <= box[1]), axis=1)
        if inside.sum() > 1000:
            good = good[inside]

    cams = [(P["intrinsic"][k], P["extrinsic"][k][:, :3], P["extrinsic"][k][:, 3],
             P["depth"][k], np.where(P["depth_conf"][k] >= thr, P["depth_conf"][k], 0.0))
            for k in range(len(P["depth"]))]
    V, F = tsdf_mesh(cams, good, voxels=voxels)
    raw = (len(V), len(F))
    if len(F) == 0:
        raise SystemExit("TSDF fusion produced no surface")
    # Bounding the VOLUME away from the table is not enough: the TSDF still carves
    # whatever slab of table passes through the box, and the first plane-removal
    # run came out as a neat wooden staircase. The fused SURFACE has to be cut by
    # the same plane.
    if plane.get("plane_kept"):
        nrm = np.array(plane["normal"]); d = plane["offset"]
        off = (V[F].mean(axis=1) @ nrm + d) * plane["side"]
        F = F[off >= plane["tol"]]
        used = np.unique(F)
        remap = np.full(len(V), -1, np.int64); remap[used] = np.arange(len(used))
        V, F = V[used], remap[F]
        plane["faces_after_cut"] = int(len(F))
        if len(F) == 0:
            raise SystemExit("cutting the table away left no surface")
    Vd, Fd = decimate_faces(V, F, target_faces)
    write_stl(out_stem + ".stl", Vd, Fd)

    lo, hi = Vd.min(0), Vd.max(0)
    meta = {
        "source": os.path.basename(pred_npz),
        "views": int(len(P["depth"])),
        "conf_percentile": conf_pct, "conf_threshold": thr,
        "centre_frac": centre_frac, "plane_removal": plane,
        "centre_box": None if box is None else [box[0].tolist(), box[1].tolist()],
        "confident_points": int(keep.sum()),
        "voxels": voxels,
        "mesh_raw_vertices": raw[0], "mesh_raw_faces": raw[1],
        "mesh_vertices": int(len(Vd)), "mesh_faces": int(len(Fd)),
        "bbox_lo": lo.tolist(), "bbox_hi": hi.tolist(),
        "bbox_size": (hi - lo).tolist(),
        "watertight": watertight(Vd, Fd),
        "scale_is_arbitrary": True,
        "note": ("shape only. A feed-forward multi-view model returns the scene up "
                 "to one similarity transform, so these units are not metres."),
    }
    json.dump(meta, open(out_stem + ".json", "w"), indent=1)
    np.save(out_stem + "-points.npy", good.astype(np.float32))
    return meta


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("pred_npz"); ap.add_argument("out_stem")
    ap.add_argument("--conf-pct", type=float, default=50.0, dest="conf_pct")
    ap.add_argument("--voxels", type=int, default=256)
    ap.add_argument("--faces", type=int, default=2000)
    ap.add_argument("--centre-frac", type=float, default=0.0, dest="centre_frac",
                    help="keep only what the middle of view 0 sees, e.g. 0.5")
    ap.add_argument("--drop-plane", action="store_true", dest="drop_plane",
                    help="RANSAC the table/floor away and keep the object")
    a = ap.parse_args()
    print(json.dumps(capture_mesh(a.pred_npz, a.out_stem, a.conf_pct, a.voxels,
                                  a.faces, centre_frac=a.centre_frac,
                                  drop_plane=a.drop_plane), indent=1))
