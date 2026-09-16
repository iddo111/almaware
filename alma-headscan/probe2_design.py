# probe2_design.py - corrected probes: portrait frames, real face filter, motion baselines,
# head-vs-bg rigidity on well-conditioned pairs, skin-seeded grabCut.
import glob, os, json
import numpy as np
import cv2

SCRATCH = r"C:\Users\<user>\AppData\Local\Temp\claude\D--CLAUDE\19ebf17c-40e0-4c38-9292-d19f3347d92e\scratchpad"
FRAMES = sorted(glob.glob(os.path.join(SCRATCH, "frames", "k*.jpg")))
OUT = {}

img0 = cv2.imread(FRAMES[0])
H, W = img0.shape[:2]
OUT["frame_shape_HxW"] = [H, W]

face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")

def detect_big_face(gray):
    faces = face_cascade.detectMultiScale(gray, 1.1, 6, minSize=(300, 300))
    if len(faces) == 0:
        return None
    return max(faces, key=lambda f: f[2] * f[3])

big_faces = {}
for i, fp in enumerate(FRAMES):
    g = cv2.cvtColor(cv2.imread(fp), cv2.COLOR_BGR2GRAY)
    f = detect_big_face(g)
    if f is not None:
        big_faces[i] = tuple(int(v) for v in f)
OUT["n_big_face_frames"] = len(big_faces)
OUT["big_face_frames"] = sorted(big_faces.keys())
OUT["face_widths_px"] = sorted(int(v[2]) for v in big_faces.values())

# ---------- median flow between consecutive keyframes (baseline check) ----------
sift = cv2.SIFT_create(nfeatures=4000)
bf = cv2.BFMatcher()
def sift_pts(i):
    g = cv2.cvtColor(cv2.imread(FRAMES[i]), cv2.COLOR_BGR2GRAY)
    return sift.detectAndCompute(g, None)

def matched_pts(ia, ib, cache={}):
    for k in (ia, ib):
        if k not in cache:
            cache[k] = sift_pts(k)
    kA, dA = cache[ia]; kB, dB = cache[ib]
    m = bf.knnMatch(dA, dB, k=2)
    good = [x for x, y in m if x.distance < 0.75 * y.distance]
    ptsA = np.float32([kA[g.queryIdx].pt for g in good])
    ptsB = np.float32([kB[g.trainIdx].pt for g in good])
    return ptsA, ptsB

flows = []
for ia, ib in zip(range(0, 20), range(1, 21)):
    ptsA, ptsB = matched_pts(ia, ib)
    if len(ptsA) < 20:
        flows.append((ia, ib, None)); continue
    med = float(np.median(np.linalg.norm(ptsB - ptsA, axis=1)))
    flows.append((ia, ib, round(med, 1)))
OUT["median_flow_first20_pairs"] = flows

# pick pairs with real motion (median flow 40..250 px) and a big face in first frame
good_pairs = [(a, b, fl) for a, b, fl in flows if fl and 40 < fl < 250 and a in big_faces]
OUT["well_conditioned_pairs"] = good_pairs[:4]

def head_box(f):
    x, y, w, h = f
    x0 = max(0, int(x - 0.30 * w)); x1 = min(W, int(x + 1.30 * w))
    y0 = max(0, int(y - 0.70 * h)); y1 = min(H, int(y + 1.60 * h))
    return x0, y0, x1, y1

def rot_deg(R):
    return float(np.degrees(np.arccos(np.clip((np.trace(R) - 1) / 2, -1, 1))))

# ---------- focal sweep with CORRECT principal point on best pair ----------
if good_pairs:
    ia, ib, _ = good_pairs[0]
    ptsA, ptsB = matched_pts(ia, ib)
    sweep = {}
    for f in [900, 1100, 1300, 1500, 1700, 2000, 2400]:
        K = np.array([[f, 0, W / 2], [0, f, H / 2], [0, 0, 1.0]])
        E, mask = cv2.findEssentialMat(ptsA, ptsB, K, cv2.RANSAC, 0.999, 1.0)
        if E is None:
            sweep[f] = None; continue
        _, R, t, m2 = cv2.recoverPose(E, ptsA, ptsB, K, mask=mask.copy())
        sweep[f] = {"E_inl": int(mask.sum()), "rot_deg": round(rot_deg(R), 2)}
    OUT["focal_sweep"] = {"pair": (ia, ib), "n_matches": len(ptsA), "sweep": sweep}

# ---------- head vs bg rigidity, correct boxes, exclude selfie-arm zone ----------
consistency = []
for ia, ib, fl in good_pairs[:4]:
    ptsA, ptsB = matched_pts(ia, ib)
    x0, y0, x1, y1 = head_box(big_faces[ia])
    in_head = (ptsA[:, 0] >= x0) & (ptsA[:, 0] <= x1) & (ptsA[:, 1] >= y0) & (ptsA[:, 1] <= y1)
    arm_zone = ptsA[:, 1] > 0.72 * H  # bottom of frame: shoulders + selfie arm
    in_bg = (~in_head) & (~arm_zone)
    f = 1500.0
    K = np.array([[f, 0, W / 2], [0, f, H / 2], [0, 0, 1.0]])
    res = {"pair": (ia, ib), "flow": fl, "n_head": int(in_head.sum()), "n_bg": int(in_bg.sum())}
    poses = {}
    for name, sel in [("head", in_head), ("bg", in_bg)]:
        pa, pb = ptsA[sel], ptsB[sel]
        if len(pa) < 40:
            poses[name] = None; continue
        E, mask = cv2.findEssentialMat(pa, pb, K, cv2.RANSAC, 0.999, 1.0)
        if E is None:
            poses[name] = None; continue
        _, R, t, _ = cv2.recoverPose(E, pa, pb, K, mask=mask.copy())
        poses[name] = (R, t.ravel())
        res[name + "_inl"] = int(mask.sum()); res[name + "_rot"] = round(rot_deg(R), 2)
    if poses.get("head") is not None and poses.get("bg") is not None:
        Rh, th = poses["head"]; Rb, tb = poses["bg"]
        res["rot_disagree_deg"] = round(rot_deg(Rh @ Rb.T), 2)
        c = abs(float(np.dot(th, tb)))
        res["t_dir_angle_deg"] = round(float(np.degrees(np.arccos(np.clip(c, -1, 1)))), 2)
    consistency.append(res)
OUT["rigidity_check"] = consistency

# ---------- skin-seeded grabCut on a frame with a real face ----------
if big_faces:
    i = sorted(big_faces.keys())[len(big_faces) // 2]
    img = cv2.imread(FRAMES[i])
    x, y, w, h = big_faces[i]
    # skin model from face core (central 50% of face box)
    core = img[y + h // 4: y + 3 * h // 4, x + w // 4: x + 3 * w // 4]
    ycc = cv2.cvtColor(img, cv2.COLOR_BGR2YCrCb)
    core_ycc = cv2.cvtColor(core, cv2.COLOR_BGR2YCrCb).reshape(-1, 3).astype(np.float64)
    mu = core_ycc[:, 1:].mean(0); sd = core_ycc[:, 1:].std(0) + 1e-6
    d = np.abs((ycc[:, :, 1:].astype(np.float64) - mu) / sd).max(axis=2)
    skin = (d < 2.8).astype(np.uint8)
    OUT["skin_frac_whole_frame"] = round(float(skin.mean()), 3)

    # grabCut with mask init: FGD = face core + scalp band above face; BGD = top corners + known-far zones
    mask = np.full((H, W), cv2.GC_PR_BGD, np.uint8)
    hx0, hy0, hx1, hy1 = head_box((x, y, w, h))
    mask[hy0:hy1, hx0:hx1] = cv2.GC_PR_FGD
    mask[y + h // 4: y + 3 * h // 4, x + w // 4: x + 3 * w // 4] = cv2.GC_FGD
    scalp_y0 = max(0, y - int(0.45 * h))
    mask[scalp_y0: y, x + w // 3: x + 2 * w // 3] = cv2.GC_FGD  # bald scalp above brow
    mask[: max(1, hy0 - int(0.2 * h)), :] = cv2.GC_BGD           # well above head
    mask[:, : max(1, hx0 - int(0.25 * w))][: hy1] = cv2.GC_BGD if hx0 > 0.25 * w else mask[:, : max(1, hx0 - int(0.25 * w))][: hy1]
    bgd = np.zeros((1, 65), np.float64); fgd = np.zeros((1, 65), np.float64)
    cv2.grabCut(img, mask, None, bgd, fgd, 5, cv2.GC_INIT_WITH_MASK)
    fg = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 1, 0).astype(np.uint8)
    ncc, lab, stats, _ = cv2.connectedComponentsWithStats(fg)
    if ncc > 1:
        big = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        fg = (lab == big).astype(np.uint8)
    overlay = img.copy()
    overlay[fg == 1] = (0.55 * overlay[fg == 1] + np.array([0, 110, 0])).astype(np.uint8)
    cv2.rectangle(overlay, (x, y), (x + w, y + h), (0, 0, 255), 3)
    cv2.imwrite(os.path.join(SCRATCH, "probe2_grabcut_overlay.jpg"), overlay)
    OUT["grabcut2"] = {"frame": i, "face_box": [x, y, w, h], "fg_pixels": int(fg.sum()),
                       "fg_frac_of_headbox": round(float(fg[hy0:hy1, hx0:hx1].mean()), 3)}

print(json.dumps(OUT, indent=1, default=str))
