"""EINAYIM / עֵינַיִם — THE RULER.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

We own the scene, so every number here is against TRUTH, not against another
estimator. What is measured:

  DEPTH   median absolute relative error, and the fraction of pixels within 5%
          and 10%. A feed-forward model is scale-free, so one global scale is
          fitted by the median ratio over the whole set — one scalar for N views,
          never one per view (that would hide a model that cannot keep a scene
          consistent). A FLAT baseline (every pixel = the median truth depth) is
          printed next to it; a model that cannot beat the flat baseline has told
          us nothing.

  POSE    relative rotation error and translation-direction error between every
          pair of views — scale-free, and the only pose metric that is meaningful
          with just two cameras. Plus, when there are >= 3 views, absolute centre
          error after a sim(3) fit.

  3D      one sim(3) fitted on the per-pixel correspondences (we know them: it is
          the same camera, the same pixel), then point error and a two-sided
          Chamfer distance, both as a percentage of the scene diameter.

  MESH    TSDF fusion of the predicted depths in the truth frame, marching cubes,
          then Chamfer accuracy/completeness against the truth surface.

Runs on eran3 (numpy/scipy/skimage/torch).
"""
from __future__ import annotations

import argparse
import json
import os

import numpy as np

# ------------------------------------------------------------------ alignment

def umeyama(X, Y):
    """s, R, t minimising |s R x + t - y|. Umeyama 1991."""
    X = np.asarray(X, float); Y = np.asarray(Y, float)
    mx, my = X.mean(0), Y.mean(0)
    Xc, Yc = X - mx, Y - my
    C = (Yc.T @ Xc) / len(X)
    U, S, Vt = np.linalg.svd(C)
    D = np.eye(3)
    if np.linalg.det(U @ Vt) < 0:
        D[2, 2] = -1.0
    R = U @ D @ Vt
    var = (Xc ** 2).sum() / len(X)
    s = float(np.trace(np.diag(S) @ D) / var) if var > 0 else 1.0
    t = my - s * R @ mx
    return s, R, t


def rot_angle_deg(A, B):
    c = (np.trace(A.T @ B) - 1.0) * 0.5
    return float(np.degrees(np.arccos(np.clip(c, -1.0, 1.0))))


# ------------------------------------------------------------------ truth side

def load_truth(truth_dir, idx):
    meta = json.load(open(os.path.join(truth_dir, "cams.json"), encoding="utf-8"))
    v = [meta["views"][i] for i in idx]
    out = []
    for i, vi in zip(idx, v):
        out.append({
            "K": np.array(vi["K"]), "R": np.array(vi["R"]), "t": np.array(vi["t"]),
            "eye": np.array(vi["eye"]), "W": vi["width"], "H": vi["height"],
            "depth": np.load(os.path.join(truth_dir, f"depth_{i:02d}.npy")),
            "mask": np.load(os.path.join(truth_dir, f"mask_{i:02d}.npy")),
            "point": np.load(os.path.join(truth_dir, f"point_{i:02d}.npy")),
        })
    return out


def resample_truth(tr, Hp, Wp):
    """Put the truth on the model's pixel grid, exactly.

    The preprocessing was a plain PIL resize of the whole image rect onto the whole
    output rect, so the map is affine per axis. Depth and masks are sampled NEAREST
    — averaging depth across a silhouette invents a surface that is not there.
    """
    sx, sy = Wp / tr["W"], Hp / tr["H"]
    xs = np.clip(np.rint((np.arange(Wp) + 0.5) / sx - 0.5), 0, tr["W"] - 1).astype(int)
    ys = np.clip(np.rint((np.arange(Hp) + 0.5) / sy - 0.5), 0, tr["H"] - 1).astype(int)
    gy, gx = np.meshgrid(ys, xs, indexing="ij")
    K = tr["K"].copy()
    K[0, 0] *= sx; K[0, 2] = sx * (K[0, 2] + 0.5) - 0.5
    K[1, 1] *= sy; K[1, 2] = sy * (K[1, 2] + 0.5) - 0.5
    return {"K": K, "R": tr["R"], "t": tr["t"], "eye": tr["eye"],
            "depth": tr["depth"][gy, gx], "mask": tr["mask"][gy, gx],
            "point": tr["point"][gy, gx]}


# ------------------------------------------------------------------- the score

def score(truth_dir, pred_npz, conf_q=0.0, far_factor=3.0):
    P = np.load(pred_npz, allow_pickle=True)
    idx = list(P["view_index"])
    depth_p = P["depth"]                    # (S,H,W)
    conf_p = P["depth_conf"]
    E = P["extrinsic"]                      # (S,3,4) world->cam
    K_p = P["intrinsic"]                    # (S,3,3)
    S, Hp, Wp = depth_p.shape

    T = [resample_truth(t, Hp, Wp) for t in load_truth(truth_dir, idx)]

    # ---------------------------------------------------------------- depth
    # THE FAR CAP. stage.py's floor is an INFINITE mathematical plane, so a ray
    # grazing it returns a point tens of kilometres away. Those pixels are an
    # artifact of the toy stage, not of the scene, and left in they set the scene
    # diameter, the sim(3) scale and the TSDF bounds all by themselves — the first
    # run of this ruler reported a 49 km living room. Every depth benchmark caps
    # (KITTI 80 m, NYU 10 m); ours is scene-relative: 3x the median true depth.
    hit0 = np.stack([t["mask"] for t in T])
    dt_all = np.stack([t["depth"] for t in T])
    far = far_factor * float(np.median(dt_all[hit0]))
    valid = np.stack([t["mask"] & (depth_p[k] > 0) & (t["depth"] <= far)
                      for k, t in enumerate(T)])
    if conf_q > 0:
        thr = np.quantile(conf_p[valid], conf_q)
        valid &= conf_p >= thr
    dt = np.stack([t["depth"] for t in T])
    s_depth = float(np.median(dt[valid] / depth_p[valid]))
    rel = np.abs(s_depth * depth_p[valid] - dt[valid]) / dt[valid]
    flat = np.abs(np.median(dt[valid]) - dt[valid]) / dt[valid]

    res = {
        "views": len(idx), "view_index": [int(i) for i in idx],
        "pred_hw": [int(Hp), int(Wp)], "valid_px": int(valid.sum()),
        "depth_scale_fitted": s_depth,
        "depth_absrel_median": float(np.median(rel)),
        "depth_absrel_mean": float(rel.mean()),
        "depth_within_5pct": float((rel < 0.05).mean()),
        "depth_within_10pct": float((rel < 0.10).mean()),
        "flat_baseline_absrel_median": float(np.median(flat)),
        "flat_baseline_within_5pct": float((flat < 0.05).mean()),
        "far_cap": far,
    }

    # THE FAIR COMPARISON. Each configuration otherwise gets scored on its own set
    # of pixels — 2 near views see a small, easy slice of the room and 8 views see
    # all of it, so "2 views beat 8" was an artifact of the question changing with
    # the answer. view 0 is in every configuration; scoring it alone asks the only
    # comparable question: what do the EXTRA cameras do to the SAME picture?
    k0 = 0
    v0 = valid[k0]
    if v0.any():
        s0 = float(np.median(dt[k0][v0] / depth_p[k0][v0]))
        r0 = np.abs(s_depth * depth_p[k0][v0] - dt[k0][v0]) / dt[k0][v0]
        res.update({
            "v0_depth_absrel_median": float(np.median(r0)),
            "v0_depth_within_5pct": float((r0 < 0.05).mean()),
            "v0_depth_within_10pct": float((r0 < 0.10).mean()),
            "v0_own_scale": s0, "v0_valid_px": int(v0.sum()),
            "v0_scale_drift_pct": float(abs(s0 - s_depth) / s_depth * 100),
        })

    # ----------------------------------------------------------------- pose
    Cp = np.stack([-E[k][:, :3].T @ E[k][:, 3] for k in range(S)])
    Ct = np.stack([t["eye"] for t in T])
    rre, rte = [], []
    for a in range(S):
        for b in range(a + 1, S):
            Rrel_p = E[b][:, :3] @ E[a][:, :3].T
            Rrel_t = T[b]["R"] @ T[a]["R"].T
            rre.append(rot_angle_deg(Rrel_p, Rrel_t))
            # The baseline direction must be compared in a SHARED frame. Camera
            # centres live in each reconstruction's own world frame, and VGGT's
            # world frame is its first camera — comparing those directly measured
            # nothing but the frame difference (it read 71 deg while the centres
            # were exact). The relative translation of the pair, expressed in
            # camera a, is frame-free: t_ab = t_b - (R_b R_a^T) t_a.
            vp = E[b][:, 3] - Rrel_p @ E[a][:, 3]
            vt = T[b]["t"] - Rrel_t @ T[a]["t"]
            cs = float(vp @ vt / max(np.linalg.norm(vp) * np.linalg.norm(vt), 1e-12))
            rte.append(float(np.degrees(np.arccos(np.clip(cs, -1, 1)))))
    truth_pts = np.concatenate([t["point"][valid[k]] for k, t in enumerate(T)])
    diam = float(np.linalg.norm(truth_pts.max(0) - truth_pts.min(0)))
    res.update({
        "pose_rel_rot_err_deg_median": float(np.median(rre)),
        "pose_rel_rot_err_deg_max": float(np.max(rre)),
        "pose_rel_trans_dir_err_deg_median": float(np.median(rte)),
        "scene_diameter": diam,
    })
    if S >= 3:
        sc, Rc, tc = umeyama(Cp, Ct)
        err = np.linalg.norm((sc * (Rc @ Cp.T).T + tc) - Ct, axis=1)
        res["pose_centre_err_pct_diam_median"] = float(np.median(err) / diam * 100)
        res["pose_centre_err_pct_diam_max"] = float(err.max() / diam * 100)

    # ------------------------------------------------------------------- 3D
    # predicted world point per pixel, from its own depth + its own camera
    Pw = []
    for k in range(S):
        R, t = E[k][:, :3], E[k][:, 3]
        K = K_p[k]
        u, v = np.meshgrid(np.arange(Wp), np.arange(Hp))
        z = depth_p[k]
        x = (u - K[0, 2]) / K[0, 0] * z
        y = (v - K[1, 2]) / K[1, 1] * z
        Xc = np.stack([x, y, z], -1)
        Pw.append((Xc - t) @ R)                       # R^T (Xc - t)
    Pw = np.stack(Pw)
    Tw = np.stack([t["point"] for t in T])

    sub = np.flatnonzero(valid.ravel())
    if len(sub) > 250_000:
        sub = np.random.default_rng(0).choice(sub, 250_000, replace=False)
    A = Pw.reshape(-1, 3)[sub]; B = Tw.reshape(-1, 3)[sub]
    s3, R3, t3 = umeyama(A, B)
    Aal = (s3 * (R3 @ Pw.reshape(-1, 3).T).T + t3).reshape(Pw.shape)
    perr = np.linalg.norm(Aal[valid] - Tw[valid], axis=1)
    res.update({
        "point_err_pct_diam_median": float(np.median(perr) / diam * 100),
        "point_err_pct_diam_p90": float(np.percentile(perr, 90) / diam * 100),
        "point_err_units_median": float(np.median(perr)),
        "sim3_scale": s3,
    })
    p0 = np.linalg.norm(Aal[k0][v0] - Tw[k0][v0], axis=1)
    res["v0_point_err_units_median"] = float(np.median(p0))
    res["v0_point_err_pct_diam_median"] = float(np.median(p0) / diam * 100)

    from scipy.spatial import cKDTree
    rng = np.random.default_rng(1)
    a = Aal[valid]; b = Tw[valid]
    ia = rng.choice(len(a), min(120_000, len(a)), replace=False)
    ib = rng.choice(len(b), min(120_000, len(b)), replace=False)
    da, _ = cKDTree(b[ib]).query(a[ia])
    db, _ = cKDTree(a[ia]).query(b[ib])
    res.update({
        "chamfer_pct_diam": float((da.mean() + db.mean()) * 0.5 / diam * 100),
        "chamfer_units": float((da.mean() + db.mean()) * 0.5),
        "chamfer_acc_pct_diam_median": float(np.median(da) / diam * 100),
        "chamfer_comp_pct_diam_median": float(np.median(db) / diam * 100),
    })

    # ----------------------------------------------------------------- mesh
    try:
        from fuse import tsdf_mesh
        # move the predicted cameras into the truth frame (see fuse.py)
        cams = []
        for k in range(S):
            Rp, tp = E[k][:, :3], E[k][:, 3]
            cams.append((K_p[k], Rp @ R3.T, s3 * tp - Rp @ R3.T @ t3,
                         s3 * depth_p[k], conf_p[k]))
        V, F = tsdf_mesh(cams, truth_pts, voxels=224)
        res["mesh_vertices"], res["mesh_faces"] = int(len(V)), int(len(F))
        if len(F):
            mp = V[F].reshape(-1, 3)
            ia = rng.choice(len(mp), min(120_000, len(mp)), replace=False)
            da, _ = cKDTree(b[ib]).query(mp[ia])
            db, _ = cKDTree(mp[ia]).query(b[ib])
            res["mesh_chamfer_pct_diam"] = float((da.mean() + db.mean()) * 0.5 / diam * 100)
            res["mesh_chamfer_units"] = float((da.mean() + db.mean()) * 0.5)
            from fuse import watertight
            res["mesh_watertight"] = watertight(V, F)
            res["mesh_acc_pct_diam_median"] = float(np.median(da) / diam * 100)
            res["mesh_comp_pct_diam_median"] = float(np.median(db) / diam * 100)
            res["_mesh"] = (V, F)
    except Exception as e:                                  # noqa: BLE001
        res["mesh_error"] = f"{type(e).__name__}: {e}"

    res["timing_infer_s"] = float(str(P["meta"]).split("'t_infer_s': ")[1].split(",")[0]) \
        if "t_infer_s" in str(P["meta"]) else None
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("truth_dir")
    ap.add_argument("pred_npz")
    ap.add_argument("--stl", default=None)
    ap.add_argument("--json", default=None)
    ap.add_argument("--far-factor", type=float, default=3.0, dest="far_factor")
    a = ap.parse_args()
    r = score(a.truth_dir, a.pred_npz, far_factor=a.far_factor)
    mesh = r.pop("_mesh", None)
    if a.stl and mesh is not None:
        from fuse import write_stl
        write_stl(a.stl, mesh[0], mesh[1])
        print("stl ->", a.stl)
    print(json.dumps(r, indent=1))
    if a.json:
        json.dump(r, open(a.json, "w"), indent=1)
