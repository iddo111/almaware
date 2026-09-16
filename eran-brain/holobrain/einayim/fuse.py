"""EINAYIM / עֵינַיִם — DEPTH MAPS -> ONE SURFACE.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

open3d has no aarch64 wheel for the GB10, so there is no Poisson and no prebuilt
TSDF here. That is fine: a truncated signed-distance volume is twenty lines of
tensor arithmetic, marching cubes comes from scikit-image, and writing a binary
STL is a struct.pack. Ours end to end, and it runs on the GPU.

The one thing that matters and is easy to get wrong: the depth a camera stores is
distance ALONG THE OPTICAL AXIS (z), not distance from the eye. sdf = d(u,v) - z.
"""
from __future__ import annotations

import struct

import numpy as np


def tsdf_mesh(cams, truth_points, voxels=224, trunc_voxels=4.0, pad=0.06,
              min_weight=1.0, device=None):
    """Fuse (K, R, t, depth, conf) views into one mesh.

    cams: list of (K (3,3), R (3,3) world->cam, t (3,), depth (H,W), conf (H,W))
    truth_points: only used to choose the volume's bounds honestly (the box the
                  answer lives in is not a thing the model has to guess).
    """
    import torch
    from skimage.measure import marching_cubes

    dev = device or ("cuda" if torch.cuda.is_available() else "cpu")
    lo = truth_points.min(0) - pad * np.ptp(truth_points, axis=0)
    hi = truth_points.max(0) + pad * np.ptp(truth_points, axis=0)
    span = hi - lo
    vs = float(span.max()) / voxels
    n = np.maximum(np.ceil(span / vs).astype(int), 2)
    trunc = trunc_voxels * vs

    ax = [torch.arange(int(n[i]), device=dev, dtype=torch.float32) * vs + lo[i] + vs * 0.5
          for i in range(3)]
    gx, gy, gz = torch.meshgrid(ax[0], ax[1], ax[2], indexing="ij")
    P = torch.stack([gx, gy, gz], -1).reshape(-1, 3)

    acc = torch.zeros(len(P), device=dev)
    wsum = torch.zeros(len(P), device=dev)

    for K, R, t, depth, conf in cams:
        Kt = torch.as_tensor(K, dtype=torch.float32, device=dev)
        Rt = torch.as_tensor(R, dtype=torch.float32, device=dev)
        tt = torch.as_tensor(t, dtype=torch.float32, device=dev)
        D = torch.as_tensor(np.ascontiguousarray(depth), dtype=torch.float32, device=dev)
        C = torch.as_tensor(np.ascontiguousarray(conf), dtype=torch.float32, device=dev)
        H, W = D.shape

        Xc = P @ Rt.T + tt
        z = Xc[:, 2]
        u = (Xc[:, 0] / z.clamp(min=1e-6)) * Kt[0, 0] + Kt[0, 2]
        v = (Xc[:, 1] / z.clamp(min=1e-6)) * Kt[1, 1] + Kt[1, 2]
        ui = u.round().long(); vi = v.round().long()
        ok = (z > 1e-6) & (ui >= 0) & (ui < W) & (vi >= 0) & (vi < H)
        ui = ui.clamp(0, W - 1); vi = vi.clamp(0, H - 1)
        d = D[vi, ui]
        w = C[vi, ui].clamp(min=0.0)
        sdf = d - z
        ok = ok & (d > 1e-6) & (sdf >= -trunc)
        val = (sdf / trunc).clamp(-1.0, 1.0)
        w = torch.where(ok, w, torch.zeros_like(w))
        acc += val * w
        wsum += w

    tsdf = torch.where(wsum > 0, acc / wsum.clamp(min=1e-9), torch.ones_like(acc))
    tsdf = tsdf.reshape(int(n[0]), int(n[1]), int(n[2])).cpu().numpy()
    seen = (wsum.reshape(int(n[0]), int(n[1]), int(n[2])).cpu().numpy() >= min_weight)
    tsdf = np.where(seen, tsdf, 1.0)

    if not ((tsdf < 0).any() and (tsdf > 0).any()):
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=int)
    verts, faces, _, _ = marching_cubes(tsdf, level=0.0)
    verts = verts * vs + lo + vs * 0.5
    return verts, faces


# ------------------------------------------------------------------- mesh i/o

def write_stl(path, verts, faces, name=b"EINAYIM"):
    tris = np.asarray(verts, dtype=np.float64)[np.asarray(faces, dtype=int)]
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    n = n / np.maximum(ln, 1e-12)
    rec = np.zeros(len(tris), dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)),
                                              ("a", "<u2")]))
    rec["n"] = n; rec["v"] = tris
    with open(path, "wb") as f:
        f.write(name.ljust(80, b" ")[:80] + struct.pack("<I", len(tris)) + rec.tobytes())
    return path


def decimate_faces(verts, faces, target):
    """Vertex-clustering decimation onto a grid, so a 300k-face marching-cubes
    surface can become the <=2000 faces KAV and TZELEM can actually chew.

    The grid resolution is found by BISECTION, not by nudging. The first version
    stepped the divisor down by hand and sailed straight past the target — a
    123,156-face room came out with 110 faces and still called itself a success.
    Face count is monotone in the grid resolution, so bisection is both correct
    and the obvious thing; the nudge was just wrong.
    """
    faces = np.asarray(faces, dtype=np.int64)
    if len(faces) <= target:
        return verts, faces

    lo = verts.min(0)
    span = float(np.linalg.norm(verts.max(0) - lo)) or 1.0

    def cluster(n):
        cell = span / n
        q = np.round((verts - lo) / cell).astype(np.int64)
        key, inv = np.unique(q, axis=0, return_inverse=True)
        nv = lo + key * cell
        nf = inv.ravel()[faces]
        nf = nf[(nf[:, 0] != nf[:, 1]) & (nf[:, 1] != nf[:, 2]) & (nf[:, 0] != nf[:, 2])]
        nf = np.unique(np.sort(nf, axis=1), axis=0)
        return nv, nf

    a, b = 2, 8                                   # grow b until it overshoots
    best = cluster(a)
    while b <= 4096:
        v, f = cluster(b)
        if len(f) > target:
            break
        best, a = (v, f), b
        b *= 2
    while a + 1 < b:                              # bisect on the resolution
        m = (a + b) // 2
        v, f = cluster(m)
        if len(f) <= target:
            best, a = (v, f), m
        else:
            b = m
    return best


def watertight(verts, faces):
    """Every edge used by exactly two triangles, and Euler characteristic."""
    if len(faces) == 0:
        return {"watertight": False, "reason": "empty"}
    e = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    e = np.sort(e, axis=1)
    _, cnt = np.unique(e, axis=0, return_counts=True)
    V, F, E = len(np.unique(faces)), len(faces), len(cnt)
    return {"watertight": bool((cnt == 2).all()),
            "boundary_edges": int((cnt == 1).sum()),
            "nonmanifold_edges": int((cnt > 2).sum()),
            "euler": int(V - E + F)}
