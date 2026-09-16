"""Synthetic BA test: does the sfm.py bundle_adjust code path actually optimize,
and does max_nfev starve it when the FD Jacobian evals are counted?"""
import numpy as np, cv2, time
from scipy.optimize import least_squares
from scipy.sparse import coo_matrix

rng = np.random.default_rng(0)
NC, NP = 10, 400
f_true, k1_true = 1400.0, -0.05
CX, CY = 540.0, 960.0

pts = rng.normal([0, 0, 5], [0.5, 0.7, 0.4], (NP, 3))
poses = []
for i in range(NC):
    ang = np.radians(-30 + 6 * i)
    R = cv2.Rodrigues(np.array([0, ang, 0.0]))[0]
    C = np.array([5 * np.sin(ang), 0, 5 - 5 * np.cos(ang)])
    t = -R @ C
    poses.append((R, t))

def project(P3, R, t, f, k1):
    P = P3 @ R.T + t
    xn, yn = P[:, 0] / P[:, 2], P[:, 1] / P[:, 2]
    d = 1 + k1 * (xn**2 + yn**2)
    return np.stack([f * xn * d + CX, f * yn * d + CY], 1)

obs_cam, obs_pt, obs_uv = [], [], []
for ci, (R, t) in enumerate(poses):
    uv = project(pts, R, t, f_true, k1_true) + rng.normal(0, 0.5, (NP, 2))
    obs_cam += [ci] * NP; obs_pt += list(range(NP)); obs_uv += list(uv)
obs_cam = np.array(obs_cam); obs_pt = np.array(obs_pt); obs_uv = np.array(obs_uv)
n_obs = len(obs_cam)

# perturb: f off by 100, k1 zeroed, poses jittered, points jittered
cams0 = []
for i in range(1, NC):
    rv = cv2.Rodrigues(poses[i][0])[0].ravel() + rng.normal(0, 0.02, 3)
    tv = poses[i][1] + rng.normal(0, 0.05, 3)
    cams0.append(np.concatenate([rv, tv]))
x0 = np.concatenate([[1300.0, 0.0], np.concatenate(cams0),
                     (pts + rng.normal(0, 0.05, pts.shape)).ravel()])
ncam_p = 2 + 6 * (NC - 1)

def fun(x):
    f, k1 = x[0], x[1]
    rt = x[2:ncam_p].reshape(-1, 6)
    P3 = x[ncam_p:].reshape(-1, 3)
    res = np.empty((n_obs, 2))
    for ci in range(NC):
        m = obs_cam == ci
        if ci == 0:
            R, t = poses[0]
        else:
            R = cv2.Rodrigues(rt[ci - 1, :3])[0]; t = rt[ci - 1, 3:]
        res[m] = project(P3[obs_pt[m]], R, t, f, k1) - obs_uv[m]
    return res.ravel()

cidx = obs_cam - 1
both = np.repeat(np.arange(n_obs) * 2, 2) + np.tile([0, 1], n_obs)
rr, cc = [], []
for col in (0, 1):
    rr.append(both); cc.append(np.full(2 * n_obs, col))
m = np.repeat(cidx >= 0, 2)
for k in range(6):
    rr.append(both[m]); cc.append(2 + 6 * np.repeat(cidx, 2)[m] + k)
for k in range(3):
    rr.append(both); cc.append(ncam_p + 3 * np.repeat(obs_pt, 2) + k)
A = coo_matrix((np.ones(sum(len(r) for r in rr), np.uint8),
                (np.concatenate(rr), np.concatenate(cc))),
               shape=(2 * n_obs, len(x0))).tolil()

r0 = fun(x0)
print("initial RMS %.2f px" % np.sqrt(np.mean(r0**2)))
for nfev in (6, 40, 200, 1000):
    t0 = time.time()
    sol = least_squares(fun, x0, jac_sparsity=A, loss="huber", f_scale=2.0,
                        x_scale="jac", tr_solver="lsmr", max_nfev=nfev)
    r = sol.fun
    print(f"max_nfev={nfev:5d}: RMS {np.sqrt(np.mean(r**2)):7.3f} px  "
          f"f={sol.x[0]:7.1f} k1={sol.x[1]:+.4f}  nfev={sol.nfev} njev={sol.njev} "
          f"status={sol.status} ({time.time()-t0:.1f} s)")
