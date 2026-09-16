# probe_design.py - cheap probes to ground pipeline design decisions with real output.
# Runs on the 60 pre-extracted sharp frames. No torch, stdlib + cv2/numpy/scipy/skimage only.
import glob, os, sys, json
import numpy as np
import cv2

SCRATCH = r"C:\Users\<user>\AppData\Local\Temp\claude\D--CLAUDE\19ebf17c-40e0-4c38-9292-d19f3347d92e\scratchpad"
FRAMES = sorted(glob.glob(os.path.join(SCRATCH, "frames", "k*.jpg")))
OUT = {}

# ---------- 0. module availability ----------
OUT["cv2_version"] = cv2.__version__
OUT["has_ximgproc"] = hasattr(cv2, "ximgproc")
OUT["has_SGBM"] = hasattr(cv2, "StereoSGBM_create")
OUT["has_SIFT"] = hasattr(cv2, "SIFT_create")
try:
    import scipy
    from scipy.optimize import least_squares
    from scipy.sparse import lil_matrix
    OUT["scipy"] = scipy.__version__
except Exception as e:
    OUT["scipy"] = "FAIL " + str(e)
try:
    import skimage
    from skimage.measure import marching_cubes
    OUT["skimage"] = skimage.__version__
except Exception as e:
    OUT["skimage"] = "FAIL " + str(e)

OUT["n_frames"] = len(FRAMES)

face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
eye_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_eye.xml")

def detect_face(gray):
    faces = face_cascade.detectMultiScale(gray, 1.1, 5, minSize=(120, 120))
    if len(faces) == 0:
        return None
    # largest
    return max(faces, key=lambda f: f[2] * f[3])

def head_box_from_face(f, W, H):
    x, y, w, h = f
    # expand: bald scalp above, chin/neck below, ears sideways
    x0 = max(0, int(x - 0.35 * w)); x1 = min(W, int(x + 1.35 * w))
    y0 = max(0, int(y - 0.75 * h)); y1 = min(H, int(y + 1.45 * h))
    return x0, y0, x1, y1

# ---------- 1. find frames with faces, pick a consecutive pair ----------
face_idx = []
face_boxes = {}
for i, fp in enumerate(FRAMES):
    g = cv2.cvtColor(cv2.imread(fp), cv2.COLOR_BGR2GRAY)
    f = detect_face(g)
    if f is not None:
        face_idx.append(i)
        face_boxes[i] = tuple(int(v) for v in f)
OUT["n_face_frames"] = len(face_idx)
OUT["face_frame_indices"] = face_idx

# pick up to 3 consecutive-in-list pairs with faces in both
pairs = []
for a, b in zip(face_idx, face_idx[1:]):
    if b - a <= 2:
        pairs.append((a, b))
    if len(pairs) >= 3:
        break
OUT["probe_pairs"] = pairs

sift = cv2.SIFT_create(nfeatures=6000)

def match_pair(ia, ib):
    A = cv2.imread(FRAMES[ia]); B = cv2.imread(FRAMES[ib])
    gA = cv2.cvtColor(A, cv2.COLOR_BGR2GRAY); gB = cv2.cvtColor(B, cv2.COLOR_BGR2GRAY)
    kA, dA = sift.detectAndCompute(gA, None)
    kB, dB = sift.detectAndCompute(gB, None)
    bf = cv2.BFMatcher()
    m = bf.knnMatch(dA, dB, k=2)
    good = [x for x, y in m if x.distance < 0.75 * y.distance]
    ptsA = np.float32([kA[g.queryIdx].pt for g in good])
    ptsB = np.float32([kB[g.trainIdx].pt for g in good])
    return A, ptsA, ptsB

# ---------- 2. focal sweep on first probe pair (all matches) ----------
H_img, W_img = 1080, 1920
if pairs:
    ia, ib = pairs[0]
    A, ptsA, ptsB = match_pair(ia, ib)
    sweep = {}
    for f in [800, 1000, 1200, 1400, 1600, 2000, 2400, 2800]:
        K = np.array([[f, 0, W_img / 2], [0, f, H_img / 2], [0, 0, 1]])
        E, mask = cv2.findEssentialMat(ptsA, ptsB, K, cv2.RANSAC, 0.999, 1.0)
        if E is None:
            sweep[f] = None; continue
        n_in = int(mask.sum())
        _, R, t, mask2 = cv2.recoverPose(E, ptsA, ptsB, K, mask=mask.copy())
        n_chei = int(mask2.astype(bool).sum())
        ang = float(np.degrees(np.arccos(np.clip((np.trace(R) - 1) / 2, -1, 1))))
        sweep[f] = {"E_inliers": n_in, "cheirality_pass": n_chei, "rot_deg": round(ang, 2)}
    OUT["focal_sweep_pair0"] = {"pair": (ia, ib), "n_matches": len(ptsA), "sweep": sweep}

# ---------- 3. head vs background motion consistency (2 pairs) ----------
def rot_angle_between(R1, R2):
    R = R1 @ R2.T
    return float(np.degrees(np.arccos(np.clip((np.trace(R) - 1) / 2, -1, 1))))

consistency = []
for (ia, ib) in pairs[:2]:
    A, ptsA, ptsB = match_pair(ia, ib)
    fb = face_boxes[ia]
    x0, y0, x1, y1 = head_box_from_face(fb, W_img, H_img)
    in_head = (ptsA[:, 0] >= x0) & (ptsA[:, 0] <= x1) & (ptsA[:, 1] >= y0) & (ptsA[:, 1] <= y1)
    f = 1400.0
    K = np.array([[f, 0, W_img / 2], [0, f, H_img / 2], [0, 0, 1]])
    res = {"pair": (ia, ib), "n_head": int(in_head.sum()), "n_bg": int((~in_head).sum())}
    poses = {}
    for name, sel in [("head", in_head), ("bg", ~in_head)]:
        pa, pb = ptsA[sel], ptsB[sel]
        if len(pa) < 30:
            poses[name] = None; continue
        E, mask = cv2.findEssentialMat(pa, pb, K, cv2.RANSAC, 0.999, 1.0)
        if E is None:
            poses[name] = None; continue
        _, R, t, _ = cv2.recoverPose(E, pa, pb, K, mask=mask.copy())
        poses[name] = (R, t.ravel())
        res[name + "_inliers"] = int(mask.sum())
        res[name + "_rot_deg"] = round(float(np.degrees(np.arccos(np.clip((np.trace(R) - 1) / 2, -1, 1)))), 2)
    if poses.get("head") is not None and poses.get("bg") is not None:
        Rh, th = poses["head"]; Rb, tb = poses["bg"]
        res["rot_disagreement_deg"] = round(rot_angle_between(Rh, Rb), 2)
        cosang = abs(float(np.dot(th, tb) / (np.linalg.norm(th) * np.linalg.norm(tb) + 1e-12)))
        res["trans_dir_angle_deg"] = round(float(np.degrees(np.arccos(np.clip(cosang, -1, 1)))), 2)
    consistency.append(res)
OUT["head_vs_bg_motion"] = consistency

# ---------- 4. grabCut probe on one frontal frame ----------
if face_idx:
    i = face_idx[len(face_idx) // 2]
    img = cv2.imread(FRAMES[i])
    fb = face_boxes[i]
    x0, y0, x1, y1 = head_box_from_face(fb, W_img, H_img)
    mask = np.zeros(img.shape[:2], np.uint8)
    bgd = np.zeros((1, 65), np.float64); fgd = np.zeros((1, 65), np.float64)
    rect = (x0, y0, x1 - x0, y1 - y0)
    cv2.grabCut(img, mask, rect, bgd, fgd, 5, cv2.GC_INIT_WITH_RECT)
    fg = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 1, 0).astype(np.uint8)
    # largest connected component
    ncc, lab, stats, _ = cv2.connectedComponentsWithStats(fg)
    if ncc > 1:
        big = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        fg = (lab == big).astype(np.uint8)
    frac_of_rect = float(fg[y0:y1, x0:x1].mean())
    n_holes = 0
    inv = (1 - fg).astype(np.uint8)
    ncc2, lab2, stats2, _ = cv2.connectedComponentsWithStats(inv)
    # holes = inv components not touching border
    for c in range(1, ncc2):
        xs, ys, ws, hs, area = stats2[c]
        if xs > 0 and ys > 0 and xs + ws < W_img and ys + hs < H_img:
            n_holes += 1
    overlay = img.copy()
    overlay[fg == 1] = (0.5 * overlay[fg == 1] + np.array([0, 128, 0])).astype(np.uint8)
    cv2.rectangle(overlay, (x0, y0), (x1, y1), (0, 0, 255), 3)
    cv2.imwrite(os.path.join(SCRATCH, "probe_grabcut_overlay.jpg"), overlay)
    OUT["grabcut"] = {"frame": i, "rect": rect, "fg_frac_of_rect": round(frac_of_rect, 3),
                      "fg_pixels": int(fg.sum()), "n_holes_in_mask": n_holes,
                      "overlay": "probe_grabcut_overlay.jpg"}

# ---------- 5. eye detection for IPD scale anchor ----------
eye_hits = []
for i in face_idx[:12]:
    img = cv2.imread(FRAMES[i]); g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    x, y, w, h = face_boxes[i]
    roi = g[y:y + int(0.65 * h), x:x + w]
    eyes = eye_cascade.detectMultiScale(roi, 1.1, 6, minSize=(int(0.12 * w), int(0.12 * w)))
    if len(eyes) >= 2:
        # two largest, must be horizontally separated
        eyes = sorted(eyes, key=lambda e: -e[2] * e[3])[:2]
        cxs = sorted([x + e[0] + e[2] / 2 for e in eyes])
        sep = cxs[1] - cxs[0]
        if sep > 0.25 * w:
            eye_hits.append({"frame": i, "sep_px": round(float(sep), 1), "face_w": int(w)})
OUT["eye_pairs_found"] = eye_hits
OUT["n_eye_pair_frames"] = len(eye_hits)

print(json.dumps(OUT, indent=1, default=str))
