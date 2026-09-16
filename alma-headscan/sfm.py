r"""sfm.py -- incremental structure-from-motion over the head-scan keyframes.

Recovers camera poses (R, t per frame), shared intrinsics (f, k1), and a sparse
3D point cloud from the 60 sharpest keyframes of Iddo's 45 s selfie video, using
cv2 + numpy + scipy only (no COLMAP, no pycolmap, no torch -- workspace law).

WHY THIS SHAPE
--------------
* Frames decode PORTRAIT 1080x1920 (the container lies about orientation; the
  decoded JPEGs are the truth, verified: shape (1920,1080,3)).  Principal point
  is fixed at (540, 960); focal length is initialised at f = 1400 px.  The
  generic phone prior "f ~ 0.9-1.2 x width" gives 970-1300 px for a 1080-wide
  portrait frame, but the measured cross-check on THIS footage (detected eye
  separation 216-223 px at arm's length ~0.4-0.5 m, IPD ~63 mm) gives
  f ~ 1200-1600 px, and a measured per-pair focal sweep was flat (E-inliers
  rise monotonically 900->2400, no minimum) -- so no single pair can calibrate
  f.  We therefore init at 1400 and let f and one radial term k1 float as
  SHARED parameters inside global bundle adjustment, which over ~50 views is
  well-conditioned where a per-pair estimate is not.
* Correspondences: exhaustive pairwise SIFT (ratio 0.8) + F-RANSAC over all
  1770 keyframe pairs, keeping pairs with >= 40 inliers.  Measured: same-cluster
  pairs give 449-1334 inliers, but cluster transitions (front->crown 16->17,
  crown->front 21->22, front->profile 35->36) collapse to 10-13 inliers -- the
  noise floor.  Pairs below 40 inliers are therefore DROPPED, not trusted:
  a 10-inlier "bridge" is more likely to poison the pose graph than to link it.
  Consequence, stated up front: the crown and profile view-clusters may remain
  unregistered islands in this stage.  The agreed design closes that gap with
  KLT track chains through all 1128 raw video frames (stage S2); this module
  is written so merged tracks can be fed in later without touching the solver.
* Non-rigidity (he grins, talks): handled exactly as the design decided --
  poses treat the scene as rigid and rely on RANSAC gates + Huber loss (f_scale
  2 px) to downweight the deforming mouth/eye pixels.  Measured justification:
  head-only vs background-only relative pose on well-conditioned pairs agrees
  to 0.10-1.56 deg, so the skull+room genuinely move as one rigid body.
* Incremental SfM: findEssentialMat + recoverPose on a well-separated init pair
  (median flow gate >= 35 px -- a measured near-still pair with 0.15 deg baseline
  produced a garbage 180-deg E decomposition, so still pairs are banned),
  then solvePnPRansac growth, multi-view DLT triangulation (>= 1.5 deg parallax,
  <= 4 px reprojection pre-BA), local BA every 6 views, global BA + 4 px
  observation prune + re-BA at the end.
* Bundle adjustment: scipy.optimize.least_squares, loss='huber', f_scale=2,
  tr_solver='lsmr', finite-difference Jacobian with an explicit sparsity
  pattern built as scipy.sparse.lil_matrix.  Rejected: hand-coded analytic
  Jacobian (error-prone, and FD with column grouping over the BA sparsity
  pattern costs only ~n_groups residual evaluations).
* Rejected outright, with receipts from the probe phase: Haar-face frame
  filtering (fires on a bookshelf phantom at frame 27, misses the crown views
  we need most), skin-colour segmentation (92.4 % of the whole frame is 'skin'
  in CrCb), and trusting any single-pair self-calibration (flat sweep).

Outputs (D:\CLAUDE\alma-headscan\out\):
  sfm_poses.npz       R/t per registered frame, K, k1, sparse cloud, per-view RMS
  camera_topdown.png  top-down plot of camera centres -- must trace an arc
  sfm_report.json     all numbers quoted in the report

Run:  python sfm.py --step all      (or feats | match | sfm separately; feats
and matches are cached in the scratchpad so re-runs cost seconds)
"""

import argparse
import json
import os
import sys
import time

import cv2
import numpy as np
from scipy.optimize import least_squares
from scipy.sparse import lil_matrix

SCRATCH = r"C:\Users\<user>\AppData\Local\Temp\claude\D--CLAUDE\19ebf17c-40e0-4c38-9292-d19f3347d92e\scratchpad"
FRAMES_DIR = os.path.join(SCRATCH, "frames")
CACHE_DIR = os.path.join(SCRATCH, "sfmcache")
OUT_DIR = r"D:\CLAUDE\alma-headscan\out"

N_FRAMES = 60
IMG_W, IMG_H = 1080, 1920
CX, CY = 540.0, 960.0
F_INIT = 1400.0

SIFT_NFEAT = 8000
RATIO = 0.8
F_RANSAC_TH = 2.0
PAIR_MIN_INLIERS = 40          # measured noise floor is 10-13; 40 keeps real geometry only
INIT_MIN_FLOW = 35.0           # px; near-still pairs are degenerate (measured)
INIT_MIN_INLIERS = 150
PNP_REPROJ_TH = 6.0
PNP_MIN_INLIERS = 30
TRI_MIN_PARALLAX_DEG = 1.5
TRI_MAX_REPROJ_PRE = 4.0       # pre-BA gate
FINAL_MAX_REPROJ = 2.5         # final-cloud gate (stated in report)
LOCAL_BA_EVERY = 6
LOCAL_BA_PT_CAP = 15000
LOCAL_BA_NFEV = 50
FINAL_BA_PT_CAP = 40000
FINAL_BA_NFEV = 200
PRUNE_OBS_TH = 4.0
# loss NOTE: the design asked for Huber, but scipy TRF measurably STALLS with
# loss='huber' on this problem (synthetic 10-cam test: stuck at 23 px RMS,
# status=4, wrong k1 even with max_nfev=1000), while loss='soft_l1' at the same
# f_scale=2 converges 25.7 -> 0.46 px RMS and recovers f and k1.  soft_l1 is the
# smooth robust equivalent (huber has a discontinuous second derivative), so the
# design intent -- downweight non-rigid-face outlier pixels at ~2 px scale --
# is preserved.  x_scale='jac' is also required: x_scale=1 crawls (measured).
BA_LOSS = "soft_l1"

cv2.setRNGSeed(7)
np.random.seed(7)


def frame_path(i):
    return os.path.join(FRAMES_DIR, f"k{i:03d}.jpg")


def feat_path(i):
    return os.path.join(CACHE_DIR, f"feats_k{i:03d}.npz")


# ---------------------------------------------------------------- features
def step_feats():
    os.makedirs(CACHE_DIR, exist_ok=True)
    sift = cv2.SIFT_create(nfeatures=SIFT_NFEAT)
    t0 = time.time()
    for i in range(N_FRAMES):
        if os.path.exists(feat_path(i)):
            continue
        img = cv2.imread(frame_path(i), cv2.IMREAD_GRAYSCALE)
        assert img.shape == (IMG_H, IMG_W), f"frame {i} shape {img.shape}"
        kps, desc = sift.detectAndCompute(img, None)
        xy = np.array([k.pt for k in kps], dtype=np.float32)
        np.savez_compressed(feat_path(i), xy=xy, desc=desc.astype(np.float16))
        print(f"[feats] k{i:03d}: {len(kps)} keypoints", flush=True)
    print(f"[feats] done in {time.time()-t0:.1f} s", flush=True)


def load_feats():
    xys, descs = [], []
    for i in range(N_FRAMES):
        d = np.load(feat_path(i))
        xys.append(d["xy"].astype(np.float64))
        descs.append(d["desc"].astype(np.float32))
    return xys, descs


# ---------------------------------------------------------------- matching
def step_match():
    xys, descs = load_feats()
    out = {}
    meta = []
    t0 = time.time()
    for j in range(1, N_FRAMES):
        matcher = cv2.FlannBasedMatcher(dict(algorithm=1, trees=5), dict(checks=64))
        matcher.add([descs[j]])
        matcher.train()
        for i in range(j):
            knn = matcher.knnMatch(descs[i], k=2)
            good = [m for m, n in knn if m.distance < RATIO * n.distance]
            if len(good) < PAIR_MIN_INLIERS:
                continue
            p_i = np.array([xys[i][m.queryIdx] for m in good])
            p_j = np.array([xys[j][m.trainIdx] for m in good])
            F, mask = cv2.findFundamentalMat(p_i, p_j, cv2.FM_RANSAC, F_RANSAC_TH, 0.999)
            if F is None or mask is None:
                continue
            inl = mask.ravel().astype(bool)
            if inl.sum() < PAIR_MIN_INLIERS:
                continue
            idx = np.array([[good[k].queryIdx, good[k].trainIdx]
                            for k in np.flatnonzero(inl)], dtype=np.int32)
            flow = float(np.median(np.linalg.norm(p_i[inl] - p_j[inl], axis=1)))
            out[f"m_{i}_{j}"] = idx
            meta.append((i, j, int(inl.sum()), flow))
        print(f"[match] vs k{j:03d}: kept so far {len(out)} pairs "
              f"({time.time()-t0:.0f} s)", flush=True)
    np.savez_compressed(os.path.join(CACHE_DIR, "matches.npz"), **out)
    with open(os.path.join(CACHE_DIR, "matches_meta.json"), "w") as fh:
        json.dump(meta, fh)
    print(f"[match] {len(out)} pairs with >={PAIR_MIN_INLIERS} F-inliers "
          f"out of {N_FRAMES*(N_FRAMES-1)//2}; {time.time()-t0:.0f} s", flush=True)


# ---------------------------------------------------------------- tracks
class UnionFind:
    def __init__(self, n):
        self.p = np.arange(n, dtype=np.int64)

    def find(self, a):
        p = self.p
        while p[a] != a:
            p[a] = p[p[a]]
            a = p[a]
        return a

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def build_tracks(xys, matches, meta):
    offs = np.zeros(N_FRAMES + 1, dtype=np.int64)
    for i in range(N_FRAMES):
        offs[i + 1] = offs[i] + len(xys[i])
    uf = UnionFind(offs[-1])
    for i, j, _, _ in meta:
        for qi, tj in matches[f"m_{i}_{j}"]:
            uf.union(offs[i] + qi, offs[j] + tj)

    groups = {}
    for i, j, _, _ in meta:
        for qi, tj in matches[f"m_{i}_{j}"]:
            for node in (offs[i] + qi, offs[j] + tj):
                r = uf.find(node)
                groups.setdefault(r, set()).add(node)

    tracks = []
    n_conflict = 0
    for nodes in groups.values():
        if len(nodes) < 2:
            continue
        frames = np.searchsorted(offs, sorted(nodes), side="right") - 1
        feats = np.array(sorted(nodes)) - offs[frames]
        if len(set(frames.tolist())) != len(frames):
            n_conflict += 1          # one track, two features in same image: bad merge
            continue
        order = np.argsort(frames)
        tracks.append((frames[order].astype(np.int16), feats[order].astype(np.int32)))
    print(f"[tracks] {len(tracks)} consistent tracks "
          f"({n_conflict} dropped for same-frame conflicts)", flush=True)
    return tracks


# ---------------------------------------------------------------- geometry helpers
def K_of(f):
    return np.array([[f, 0, CX], [0, f, CY], [0, 0, 1.0]])


def dist_of(k1):
    return np.array([k1, 0, 0, 0, 0.0])


def project(pts, R, t, f, k1):
    P = pts @ R.T + t
    z = np.where(np.abs(P[:, 2]) < 1e-9, 1e-9, P[:, 2])
    xn, yn = P[:, 0] / z, P[:, 1] / z
    d = 1.0 + k1 * (xn * xn + yn * yn)
    return np.stack([f * xn * d + CX, f * yn * d + CY], axis=1), P[:, 2]


def undistort_norm(uv, f, k1):
    out = cv2.undistortPoints(uv.reshape(-1, 1, 2).astype(np.float64),
                              K_of(f), dist_of(k1))
    return out.reshape(-1, 2)


def triangulate_track(views, uvs, poses, f, k1):
    """Multi-view DLT on normalized coords; returns X or None with gates applied."""
    norm = undistort_norm(np.array(uvs), f, k1)
    A = []
    for (R, t), (x, y) in zip((poses[v] for v in views), norm):
        P = np.hstack([R, t.reshape(3, 1)])
        A.append(x * P[2] - P[0])
        A.append(y * P[2] - P[1])
    A = np.stack(A)
    _, _, Vt = np.linalg.svd(A, full_matrices=False)
    X = Vt[-1]
    if abs(X[3]) < 1e-12:
        return None
    X = X[:3] / X[3]
    centers = [-poses[v][0].T @ poses[v][1] for v in views]
    rays = [X - c for c in centers]
    rays = [r / (np.linalg.norm(r) + 1e-12) for r in rays]
    max_par = 0.0
    for a in range(len(rays)):
        for b in range(a + 1, len(rays)):
            ang = np.degrees(np.arccos(np.clip(rays[a] @ rays[b], -1, 1)))
            max_par = max(max_par, ang)
    if max_par < TRI_MIN_PARALLAX_DEG:
        return None
    for v, uv in zip(views, uvs):
        R, t = poses[v]
        proj, z = project(X.reshape(1, 3), R, t, f, k1)
        if z[0] <= 0 or np.linalg.norm(proj[0] - uv) > TRI_MAX_REPROJ_PRE:
            return None
    return X


# ---------------------------------------------------------------- bundle adjustment
def gather_obs(state, sel_tracks):
    """Observation arrays over registered views for the given track ids."""
    xys, tracks = state["xys"], state["tracks"]
    reg = state["registered"]
    banned = state["banned"]
    obs_cam, obs_pt, obs_uv = [], [], []
    for pi, tid in enumerate(sel_tracks):
        frames, feats = tracks[tid]
        bad = banned.get(tid, ())
        for fr, ft in zip(frames, feats):
            if fr in reg and fr not in bad:
                obs_cam.append(fr)
                obs_pt.append(pi)
                obs_uv.append(xys[fr][ft])
    return (np.array(obs_cam, dtype=np.int32), np.array(obs_pt, dtype=np.int32),
            np.array(obs_uv, dtype=np.float64))


def select_ba_tracks(state, cap):
    tp = state["track_point"]
    have = np.flatnonzero(tp >= 0)
    reg = state["registered"]
    lengths = np.array([sum(1 for fr in state["tracks"][t][0] if fr in reg)
                        for t in have])
    order = have[np.argsort(-lengths)]
    if len(order) <= cap:
        return order
    sel = list(order[:cap])
    # keep every registered view observed >= 60 times in the BA subset
    count = {v: 0 for v in reg}
    sset = set(sel)
    for t in sel:
        for fr in state["tracks"][t][0]:
            if fr in count:
                count[fr] += 1
    for t in order[cap:]:
        needy = [fr for fr in state["tracks"][t][0] if fr in count and count[fr] < 60]
        if needy:
            sel.append(t)
            sset.add(t)
            for fr in state["tracks"][t][0]:
                if fr in count:
                    count[fr] += 1
    return np.array(sel)


def bundle_adjust(state, pt_cap, max_nfev, tag):
    reg_list = sorted(state["registered"])
    ref = state["ref_view"]
    cams = [v for v in reg_list if v != ref]
    cam_idx = {v: k for k, v in enumerate(cams)}

    sel = select_ba_tracks(state, pt_cap)
    pt_map = {int(t): k for k, t in enumerate(sel)}
    obs_cam, obs_pt, obs_uv = gather_obs(state, sel)
    pts0 = np.stack([state["points"][state["track_point"][t]] for t in sel])

    x0 = np.concatenate([
        [state["f"], state["k1"]],
        np.concatenate([np.concatenate([state["rvec"][v], state["tvec"][v]])
                        for v in cams]) if cams else np.zeros(0),
        pts0.ravel(),
    ])
    n_obs = len(obs_cam)
    ncam_p = 2 + 6 * len(cams)

    def unpack(x):
        f, k1 = x[0], x[1]
        rt = x[2:ncam_p].reshape(-1, 6)
        pts = x[ncam_p:].reshape(-1, 3)
        return f, k1, rt, pts

    Rref, tref = cv2.Rodrigues(state["rvec"][ref])[0], state["tvec"][ref]

    def fun(x):
        f, k1, rt, pts = unpack(x)
        res = np.empty((n_obs, 2))
        for v in reg_list:
            m = obs_cam == v
            if not m.any():
                continue
            if v == ref:
                R, t = Rref, tref
            else:
                R = cv2.Rodrigues(rt[cam_idx[v], :3])[0]
                t = rt[cam_idx[v], 3:]
            proj, _ = project(pts[obs_pt[m]], R, t, f, k1)
            res[m] = proj - obs_uv[m]
        return res.ravel()

    # sparsity pattern assembled in COO (vectorized) then converted to LIL,
    # because per-element lil assignment over ~1M rows is minutes of Python loop
    from scipy.sparse import coo_matrix
    cidx = np.array([cam_idx.get(int(c), -1) for c in obs_cam])
    rr, cc = [], []
    both = np.repeat(np.arange(n_obs) * 2, 2) + np.tile([0, 1], n_obs)
    for col in (0, 1):
        rr.append(both)
        cc.append(np.full(2 * n_obs, col))
    m = np.repeat(cidx >= 0, 2)
    for k in range(6):
        rr.append(both[m])
        cc.append(2 + 6 * np.repeat(cidx, 2)[m] + k)
    for k in range(3):
        rr.append(both)
        cc.append(ncam_p + 3 * np.repeat(obs_pt, 2) + k)
    A = coo_matrix((np.ones(sum(len(r) for r in rr), dtype=np.uint8),
                    (np.concatenate(rr), np.concatenate(cc))),
                   shape=(2 * n_obs, len(x0))).tolil()
    assert isinstance(A, lil_matrix)

    r0 = fun(x0)
    rms0 = np.sqrt(np.mean((r0.reshape(-1, 2) ** 2).sum(axis=1)))
    t0 = time.time()
    sol = least_squares(fun, x0, jac_sparsity=A, loss=BA_LOSS, f_scale=2.0,
                        x_scale="jac", tr_solver="lsmr", max_nfev=max_nfev,
                        verbose=0)
    r1 = sol.fun
    rms1 = np.sqrt(np.mean((r1.reshape(-1, 2) ** 2).sum(axis=1)))
    med1 = np.median(np.linalg.norm(r1.reshape(-1, 2), axis=1))
    print(f"[BA:{tag}] cams={len(reg_list)} pts={len(sel)} obs={n_obs} "
          f"reproj RMS {rms0:.2f} -> {rms1:.2f} px (median {med1:.2f}), "
          f"f={sol.x[0]:.1f}, k1={sol.x[1]:+.4f}, status={sol.status} "
          f"nfev={sol.nfev} ({time.time()-t0:.0f} s)", flush=True)

    f, k1, rt, pts = unpack(sol.x)
    state["f"], state["k1"] = float(f), float(k1)
    for v in cams:
        state["rvec"][v] = rt[cam_idx[v], :3].copy()
        state["tvec"][v] = rt[cam_idx[v], 3:].copy()
    for t_id, k in pt_map.items():
        state["points"][state["track_point"][t_id]] = pts[k]
    return rms1


# ---------------------------------------------------------------- incremental SfM
def pick_init_pair(meta, xys, matches):
    cands = []
    for i, j, ninl, flow in meta:
        if ninl >= INIT_MIN_INLIERS and flow >= INIT_MIN_FLOW:
            cands.append((min(ninl, 800) * min(flow / 80.0, 1.0), i, j, ninl, flow))
    cands.sort(reverse=True)
    return cands[:10]


def try_init(i, j, xys, matches, f):
    idx = matches[f"m_{i}_{j}"]
    p_i = xys[i][idx[:, 0]]
    p_j = xys[j][idx[:, 1]]
    K = K_of(f)
    E, mask = cv2.findEssentialMat(p_i, p_j, K, cv2.RANSAC, 0.9999, 1.5)
    if E is None or E.shape != (3, 3):
        return None
    n, R, t, mask2 = cv2.recoverPose(E, p_i, p_j, K, mask=mask)
    if n < 100:
        return None
    inl = mask2.ravel() > 0
    P1 = K @ np.hstack([np.eye(3), np.zeros((3, 1))])
    P2 = K @ np.hstack([R, t])
    X4 = cv2.triangulatePoints(P1, P2, p_i[inl].T, p_j[inl].T)
    X = (X4[:3] / X4[3]).T
    z1 = X[:, 2]
    z2 = (X @ R.T + t.ravel())[:, 2]
    ok = (z1 > 0) & (z2 > 0)
    if ok.sum() < 100:
        return None
    c2 = (-R.T @ t).ravel()
    r1 = X[ok] / np.linalg.norm(X[ok], axis=1, keepdims=True)
    r2 = X[ok] - c2
    r2 /= np.linalg.norm(r2, axis=1, keepdims=True)
    par = np.degrees(np.arccos(np.clip((r1 * r2).sum(axis=1), -1, 1)))
    med_par = float(np.median(par))
    if med_par < TRI_MIN_PARALLAX_DEG:
        return None
    return R, t.ravel(), idx[inl][ok], X[ok], med_par


def register_view(state, v):
    xys, tracks = state["xys"], state["tracks"]
    tp = state["track_point"]
    tofv = state["track_of"][v]
    valid = np.flatnonzero(tofv >= 0)
    tids = tofv[valid]
    has_pt = tp[tids] >= 0
    if has_pt.sum() < PNP_MIN_INLIERS:
        return False, int(has_pt.sum())
    feat_ids = valid[has_pt]
    X = np.asarray(state["points"])[tp[tofv[feat_ids]]]
    x2d = xys[v][feat_ids]
    K, dist = K_of(state["f"]), dist_of(state["k1"])
    ok, rvec, tvec, inl = cv2.solvePnPRansac(
        X.astype(np.float64), x2d.astype(np.float64), K, dist,
        iterationsCount=3000, reprojectionError=PNP_REPROJ_TH,
        confidence=0.9999, flags=cv2.SOLVEPNP_EPNP)
    if not ok or inl is None or len(inl) < PNP_MIN_INLIERS:
        return False, int(has_pt.sum())
    inl = inl.ravel()
    rvec, tvec = cv2.solvePnPRefineLM(X[inl], x2d[inl], K, dist, rvec, tvec)
    state["rvec"][v] = rvec.ravel().copy()
    state["tvec"][v] = tvec.ravel().copy()
    state["registered"].add(v)
    print(f"[sfm] registered k{v:03d}: {len(inl)}/{len(feat_ids)} PnP inliers",
          flush=True)
    return True, len(inl)


def triangulate_new(state, v):
    """Try to triangulate tracks that touch view v and have no 3D point yet."""
    tracks, tp = state["tracks"], state["track_point"]
    reg = state["registered"]
    poses = {u: (cv2.Rodrigues(state["rvec"][u])[0], state["tvec"][u]) for u in reg}
    tofv = state["track_of"][v]
    n_new = 0
    for tid in tofv[tofv >= 0]:
        if tp[tid] >= 0:
            continue
        frames, feats = tracks[tid]
        views = [int(fr) for fr in frames if fr in reg]
        if len(views) < 2:
            continue
        uvs = [state["xys"][fr][ft] for fr, ft in zip(frames, feats) if fr in reg]
        X = triangulate_track(views, uvs, poses, state["f"], state["k1"])
        if X is None:
            continue
        state["points"].append(X)
        tp[tid] = len(state["points"]) - 1
        n_new += 1
    return n_new


def prune_observations(state, th):
    """Ban single observations with reprojection error > th px; drop points left
    with < 2 registered observations."""
    tracks, tp = state["tracks"], state["track_point"]
    reg = state["registered"]
    poses = {u: (cv2.Rodrigues(state["rvec"][u])[0], state["tvec"][u]) for u in reg}
    n_ban, n_drop = 0, 0
    for tid in np.flatnonzero(tp >= 0):
        frames, feats = tracks[tid]
        X = np.array(state["points"][tp[tid]]).reshape(1, 3)
        left = 0
        for fr, ft in zip(frames, feats):
            if fr not in reg or fr in state["banned"].get(tid, ()):
                continue
            R, t = poses[fr]
            proj, z = project(X, R, t, state["f"], state["k1"])
            err = np.linalg.norm(proj[0] - state["xys"][fr][ft])
            if z[0] <= 0 or err > th:
                state["banned"].setdefault(int(tid), set()).add(int(fr))
                n_ban += 1
            else:
                left += 1
        if left < 2:
            tp[tid] = -1
            n_drop += 1
    print(f"[prune] banned {n_ban} observations >{th} px, dropped {n_drop} points",
          flush=True)


def step_sfm():
    os.makedirs(OUT_DIR, exist_ok=True)
    xys, _ = load_feats()
    matches = dict(np.load(os.path.join(CACHE_DIR, "matches.npz")))
    with open(os.path.join(CACHE_DIR, "matches_meta.json")) as fh:
        meta = [tuple(m) for m in json.load(fh)]
    tracks = build_tracks(xys, matches, meta)

    track_of = [np.full(len(xys[v]), -1, dtype=np.int64) for v in range(N_FRAMES)]
    for tid, (frames, feats) in enumerate(tracks):
        for fr, ft in zip(frames, feats):
            track_of[fr][ft] = tid

    state = dict(xys=xys, tracks=tracks, track_of=track_of,
                 f=F_INIT, k1=0.0,
                 rvec={}, tvec={}, registered=set(), banned={},
                 points=[], track_point=np.full(len(tracks), -1, dtype=np.int64),
                 ref_view=None)

    init_ok = False
    for score, i, j, ninl, flow in pick_init_pair(meta, xys, matches):
        got = try_init(i, j, xys, matches, state["f"])
        if got is None:
            continue
        R, t, idx_ok, X, med_par = got
        print(f"[init] pair (k{i:03d},k{j:03d}): {ninl} F-inliers, "
              f"median flow {flow:.0f} px, {len(X)} points, "
              f"median parallax {med_par:.2f} deg", flush=True)
        state["ref_view"] = i
        state["rvec"][i] = np.zeros(3)
        state["tvec"][i] = np.zeros(3)
        rj, _ = cv2.Rodrigues(R)
        state["rvec"][j] = rj.ravel()
        state["tvec"][j] = t.copy()
        state["registered"] = {i, j}
        # scene-scale gauge: median init depth = 5 units
        s = 5.0 / np.median(X[:, 2])
        X = X * s
        state["tvec"][j] = state["tvec"][j] * s
        for (qi, tj), Xp in zip(idx_ok, X):
            tid = track_of[i][qi]
            if tid >= 0 and tid == track_of[j][tj] and state["track_point"][tid] < 0:
                state["points"].append(Xp)
                state["track_point"][tid] = len(state["points"]) - 1
        init_ok = True
        break
    if not init_ok:
        print("[FAIL] no valid init pair", flush=True)
        sys.exit(1)

    print(f"[init] {len(state['points'])} seed points", flush=True)

    n_added = 0
    fail_count = {}
    while True:
        tp = state["track_point"]
        best_v, best_n = -1, 0
        for v in range(N_FRAMES):
            if v in state["registered"]:
                continue
            tofv = state["track_of"][v]
            tids = tofv[tofv >= 0]
            n = int((tp[tids] >= 0).sum())
            if n > best_n and n > fail_count.get(v, 0) * 1.25:
                best_v, best_n = v, n
        if best_v < 0 or best_n < PNP_MIN_INLIERS:
            break
        ok, n = register_view(state, best_v)
        if not ok:
            fail_count[best_v] = best_n
            continue
        n_new = triangulate_new(state, best_v)
        n_added += 1
        if n_added % LOCAL_BA_EVERY == 0:
            bundle_adjust(state, LOCAL_BA_PT_CAP, LOCAL_BA_NFEV,
                          f"local@{len(state['registered'])}")

    print(f"[sfm] registered {len(state['registered'])}/{N_FRAMES} views, "
          f"{int((state['track_point'] >= 0).sum())} points", flush=True)

    bundle_adjust(state, FINAL_BA_PT_CAP, FINAL_BA_NFEV, "global-1")
    prune_observations(state, PRUNE_OBS_TH)
    rms_final = bundle_adjust(state, FINAL_BA_PT_CAP, FINAL_BA_NFEV // 2, "global-2")

    finalize(state, rms_final)


# ---------------------------------------------------------------- finalize
def finalize(state, ba_rms):
    reg = sorted(state["registered"])
    poses = {u: (cv2.Rodrigues(state["rvec"][u])[0], state["tvec"][u]) for u in reg}
    f, k1 = state["f"], state["k1"]

    # rebuild the FULL cloud from scratch with final poses (gates stated in report)
    pts, errs, obs_rows = [], [], []
    per_view_se = {v: [] for v in reg}
    n_reject = 0
    for tid, (frames, feats) in enumerate(state["tracks"]):
        views, uvs = [], []
        for fr, ft in zip(frames, feats):
            if fr in state["registered"] and fr not in state["banned"].get(tid, ()):
                views.append(int(fr))
                uvs.append(state["xys"][fr][ft])
        if len(views) < 2:
            continue
        X = triangulate_track(views, uvs, poses, f, k1)
        if X is None:
            n_reject += 1
            continue
        e_this = []
        ok = True
        for v, uv in zip(views, uvs):
            R, t = poses[v]
            proj, z = project(X.reshape(1, 3), R, t, f, k1)
            e = float(np.linalg.norm(proj[0] - uv))
            if z[0] <= 0 or e > FINAL_MAX_REPROJ:
                ok = False
                break
            e_this.append((v, e, uv))
        if not ok:
            n_reject += 1
            continue
        pi = len(pts)
        pts.append(X)
        for v, e, uv in e_this:
            errs.append(e)
            per_view_se[v].append(e)
            obs_rows.append((pi, v, uv[0], uv[1]))
    pts = np.array(pts)
    errs = np.array(errs)
    per_view = {v: (float(np.sqrt(np.mean(np.array(e) ** 2))) if e else None,
                    len(e)) for v, e in per_view_se.items()}

    R_all = np.full((N_FRAMES, 3, 3), np.nan)
    t_all = np.full((N_FRAMES, 3), np.nan)
    rvec_all = np.full((N_FRAMES, 3), np.nan)
    registered = np.zeros(N_FRAMES, dtype=bool)
    for v in reg:
        R_all[v] = poses[v][0]
        t_all[v] = poses[v][1]
        rvec_all[v] = state["rvec"][v]
        registered[v] = True

    obs_arr = np.array(obs_rows, dtype=np.float64)
    np.savez_compressed(
        os.path.join(OUT_DIR, "sfm_poses.npz"),
        frame_names=np.array([f"k{i:03d}.jpg" for i in range(N_FRAMES)]),
        registered=registered, R=R_all, t=t_all, rvec=rvec_all,
        K=K_of(f), k1=np.float64(k1),
        points3d=pts, obs=obs_arr,
        per_view_rms=np.array([per_view.get(v, (np.nan, 0))[0]
                               if v in per_view and per_view[v][0] is not None
                               else np.nan for v in range(N_FRAMES)]))

    # head vs room: 2-means on point distance to the mean camera centre.
    # The head is the compact near cluster (~0.4-0.5 m); the room is >1.5 m.
    Cmean = np.mean([-poses[v][0].T @ poses[v][1] for v in reg], axis=0)
    d = np.linalg.norm(pts - Cmean, axis=1)
    c0, c1 = np.percentile(d, 10), np.percentile(d, 90)
    for _ in range(30):
        near = np.abs(d - c0) < np.abs(d - c1)
        if near.all() or not near.any():
            break
        c0, c1 = d[near].mean(), d[~near].mean()
    head_pts = pts[near]
    head_centroid = np.median(head_pts, axis=0) if len(head_pts) else np.median(pts, axis=0)

    arc_deg, plot_path = render_topdown(state, pts, reg, poses, head_centroid, near)

    report = dict(
        registered_views=len(reg),
        total_views=N_FRAMES,
        registered_list=[int(v) for v in reg],
        unregistered_list=[int(v) for v in range(N_FRAMES) if v not in state["registered"]],
        focal_px=round(f, 1), k1=round(k1, 5),
        ba_rms_px=round(float(ba_rms), 3),
        final_cloud_points=int(len(pts)),
        final_cloud_obs=int(len(errs)),
        final_mean_reproj_px=round(float(errs.mean()), 3),
        final_median_reproj_px=round(float(np.median(errs)), 3),
        final_rms_reproj_px=round(float(np.sqrt((errs ** 2).mean())), 3),
        final_gates=f"reproj<={FINAL_MAX_REPROJ}px all obs, parallax>={TRI_MIN_PARALLAX_DEG}deg, cheirality",
        tracks_rejected_by_gates=int(n_reject),
        head_points=int(near.sum()),
        room_points=int(len(pts) - near.sum()),
        head_dist_units=round(float(np.median(d[near])), 2),
        room_dist_units=round(float(np.median(d[~near])), 2) if (~near).any() else None,
        per_view_rms_px={f"k{v:03d}": [round(per_view[v][0], 2), per_view[v][1]]
                         for v in reg if per_view[v][0] is not None},
        camera_arc_deg=round(arc_deg, 1),
    )
    with open(os.path.join(OUT_DIR, "sfm_report.json"), "w") as fh:
        json.dump(report, fh, indent=1)
    print(json.dumps({k: v for k, v in report.items() if k != "per_view_rms_px"},
                     indent=1), flush=True)
    print(f"[done] poses -> sfm_poses.npz, plot -> {plot_path}", flush=True)


def render_topdown(state, pts, reg, poses, head_centroid, near_mask):
    from PIL import Image, ImageDraw, ImageFont
    up = np.zeros(3)
    for v in reg:
        up -= poses[v][0][1]        # camera +y is image-down => world up ~ -sum(R[1])
    up /= np.linalg.norm(up) + 1e-12
    a = np.array([1.0, 0, 0]) if abs(up[0]) < 0.9 else np.array([0, 0, 1.0])
    e1 = a - up * (a @ up)
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(up, e1)

    centers = {v: -poses[v][0].T @ poses[v][1] for v in reg}
    C2 = {v: np.array([c @ e1, c @ e2]) for v, c in centers.items()}
    if len(pts):
        d = np.linalg.norm(pts - np.median(pts, axis=0), axis=1)
        keep_mask = d < 4 * np.median(d)
        keep = pts[keep_mask]
        P2 = np.stack([keep @ e1, keep @ e2], axis=1)
    else:
        keep_mask = np.zeros(0, bool)
        P2 = np.zeros((0, 2))

    allxy = np.vstack([np.stack(list(C2.values())), P2]) if len(P2) else np.stack(list(C2.values()))
    lo, hi = allxy.min(axis=0), allxy.max(axis=0)
    span = max((hi - lo).max(), 1e-6)
    S = 1200
    pad = 90

    def to_px(p):
        q = (p - (lo + hi) / 2) / span * (S - 2 * pad)
        return int(S / 2 + q[0]), int(S / 2 - q[1])

    img = Image.new("RGB", (S, S + 90), "white")
    dr = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 15)
        fbig = ImageFont.truetype(r"C:\Windows\Fonts\arialbd.ttf", 20)
    except OSError:
        font = fbig = ImageFont.load_default()
    keep_near = near_mask[keep_mask] if len(pts) else np.zeros(0, bool)
    for p, ishead in zip(P2, keep_near):
        x, y = to_px(p)
        dr.point((x, y + 90), fill=(230, 150, 60) if ishead else (190, 190, 190))

    # yaw arc around the HEAD centroid (2-means near cluster), not the room
    if len(pts):
        h2 = np.array([head_centroid @ e1, head_centroid @ e2])
        angs = sorted(np.degrees(np.arctan2(*(C2[v] - h2)[::-1])) for v in reg)
        gaps = [angs[k + 1] - angs[k] for k in range(len(angs) - 1)]
        gaps.append(360 - (angs[-1] - angs[0]))
        arc = 360 - max(gaps)
        x, y = to_px(h2)
        dr.ellipse([x - 6, y + 84, x + 6, y + 96], outline=(200, 100, 0), width=3)
        dr.text((x + 10, y + 84), "HEAD centroid", fill=(200, 100, 0), font=font)
    else:
        arc = 0.0

    for v in reg:
        col = (200, 30, 30) if 17 <= v <= 25 else \
              (30, 140, 30) if 36 <= v <= 37 else (30, 60, 220)
        x, y = to_px(C2[v])
        y += 90
        z = poses[v][0][2]          # optical axis, world coords
        z2 = np.array([z @ e1, z @ e2])
        n = np.linalg.norm(z2)
        if n > 1e-6:
            z2 = z2 / n * 32
            dr.line([x, y, x + z2[0], y - z2[1]], fill=(170, 170, 170), width=1)
        dr.ellipse([x - 4, y - 4, x + 4, y + 4], fill=col)
        dr.text((x + 5, y - 18), str(v), fill=col, font=font)

    dr.text((15, 10), "SfM camera centres, top-down (gravity-aligned plane)", fill="black", font=fbig)
    dr.text((15, 38), f"blue=frontal  red=crown(17-25)  green=profile(36-37)   "
                      f"registered {len(reg)}/{N_FRAMES}   yaw arc about head {arc:.0f} deg",
            fill="black", font=font)
    dr.text((15, 60), "orange dots = head cluster   grey dots = room   grey ticks = view directions",
            fill="black", font=font)
    path = os.path.join(OUT_DIR, "camera_topdown.png")
    img.save(path)
    return float(arc), path


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", default="all", choices=["feats", "match", "sfm", "all"])
    args = ap.parse_args()
    if args.step in ("feats", "all"):
        step_feats()
    if args.step in ("match", "all"):
        step_match()
    if args.step in ("sfm", "all"):
        step_sfm()
