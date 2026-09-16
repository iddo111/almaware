"""
segmentation.py — head+neck silhouette masks for the ALMA head-scan pipeline (stage S6 input).

Cuts the HEAD (plus neck, nothing below) out of each of the 60 sharpness-selected keyframes.
Output: masks/mask_k###.png (head=255), a QA report JSON, and contact sheets for eyeball review.

WHY THIS DESIGN — what was probed and rejected before this file existed:
  * Rect-seeded grabCut from a raw Haar box grabbed the window PLANTS as foreground and missed
    the head (probe_grabcut_overlay.jpg). Everything outside a skull-shaped ROI is therefore
    labelled DEFINITE background here, so distant textured clutter is never in play.
  * Mask-seeded grabCut from frame 27's Haar box segmented a BOOKSHELF, because that box was a
    phantom face. Every Haar hit here must pass validation: plausible size (measured eye
    separation is 216-223 px, so a real face box is ~350-700 px), plausible position, and an
    eye-cascade hit inside the upper half of the box — or temporal corroboration by an
    overlapping validated box on a neighbouring keyframe.
  * A CrCb skin model built from his own face matched 92.4% of the ENTIRE frame (wood shelves,
    leather sofa, warm light). Skin colour is not used anywhere in this file.
  * The subject is bald with stubble; the skull ellipse is grown UP from the face box by ~0.75
    face-heights to cover the crown, and a narrow trapezoid below the chin admits the neck while
    hard-excluding shoulders/chair — the carve stage's stated corruption mode.
Frames with no validated detection get their skull ROI PROPAGATED from the nearest validated
keyframe via SIFT + RANSAC homography (>=30 inliers, source keypoints restricted to the source
head region). Cluster-transition pairs are known to collapse to ~10 inliers, so crown/profile
frames that cannot be reached are reported as FAILED rather than guessed — a dropped frame is a
correct output for the downstream QA-gated carve; a shoulder-bearing mask is not.
grabCut runs at half resolution (quality is boundary-level, cost drops 4x); the binary result is
clipped to the ROI, opened/closed, largest-component'd and hole-filled at full resolution.
"""

import json
import os
import sys

import cv2
import numpy as np
from scipy.ndimage import binary_fill_holes

FRAMES_DIR = (r"C:\Users\<user>\AppData\Local\Temp\claude\D--CLAUDE"
              r"\19ebf17c-40e0-4c38-9292-d19f3347d92e\scratchpad\frames")
OUT_DIR = r"D:\CLAUDE\alma-headscan"
MASKS_DIR = os.path.join(OUT_DIR, "masks")
DEBUG_DIR = os.path.join(OUT_DIR, "seg_debug")

N_FRAMES = 60
GC_ITERS = 5
GC_SCALE = 0.5
MIN_PROP_INLIERS = 30
# Measured eye sep is 216-223 px on ordinary frontal frames -> face box ~430-520 px, but the
# grimace-zone frames (k039-43) are shot much closer (eye sep ~370 px seen on k041), so the
# ceiling must admit ~900 px boxes.
FACE_W_RANGE = (300, 900)
QA_AREA_FRAC = (0.030, 0.420)      # close-up (k039-44) heads legitimately reach ~35-40%
QA_MIN_SOLIDITY = 0.80
QA_MIN_BASE_FILL = 0.50            # run 1: real heads fill 0.58-0.69, garbage 0.44


# Written after eyeballing the round-4 contact sheets and full-res overlays — keep honest.
VERDICT_NOTES = [
    "Masks err PERMISSIVE (background included), never the destructive direction: on every "
    "passing mask the full head+neck is INSIDE the mask, so a silhouette carve cannot cut "
    "into the reconstructed head.",
    "Residual defect A: ~10 passing masks keep a bookshelf band/strip above or beside the "
    "crown (3-8% of mask area, up to ~150 px outward) — warm book spines are colorimetrically "
    "skin-like; a permissive sector simply fails to carve, it does not corrupt.",
    "Residual defect B: k033/k045 (tilted head) include a small shoulder-top wedge where the "
    "axis-aligned neck trapezoid meets the shoulder; small area, same permissive direction.",
    "Honest failures, no mask shipped: crown cluster k017-k021 (head dome abuts bare "
    "shoulders, no face anchor to validate a mask against), desk zone k026-k029 (no head in "
    "frame), left profiles k036-k037 (backlit, unreachable across the measured ~10-inlier "
    "SIFT transition), plus QA-rejected leaky masks (k030-k032, k034, k038, k040-k044, "
    "k049, k022).",
    "Boundary precision on clean sectors ~5-15 px at 1080x1920; grabCut ran at half "
    "resolution.",
]


def load_cascades():
    d = cv2.data.haarcascades
    return {
        "front": [cv2.CascadeClassifier(d + "haarcascade_frontalface_alt2.xml"),
                  cv2.CascadeClassifier(d + "haarcascade_frontalface_default.xml")],
        "profile": cv2.CascadeClassifier(d + "haarcascade_profileface.xml"),
        "eye": cv2.CascadeClassifier(d + "haarcascade_eye.xml"),
    }


def detect_face(gray, cas):
    """Return (box, kind) with kind in {'front','front-noeye','profile',None}.
    'front-noeye' boxes are kept only if later corroborated temporally.
    Cascades run at half resolution (4x faster on the thermally-capped PC; a >=300 px face
    is still >=150 px there); the eye check runs on the full-resolution crop."""
    H, W = gray.shape
    small = cv2.resize(gray, (W // 2, H // 2), interpolation=cv2.INTER_AREA)
    lo, hi = FACE_W_RANGE[0] // 2, FACE_W_RANGE[1] // 2
    hits = []
    for c in cas["front"]:
        for (x, y, w, h) in c.detectMultiScale(small, 1.08, 5,
                                               minSize=(lo, lo), maxSize=(hi, hi)):
            hits.append((2 * x, 2 * y, 2 * w, 2 * h, "front"))
    clahe = cv2.createCLAHE(2.0, (8, 8)).apply(small)
    for g, flip in ((clahe, False), (cv2.flip(clahe, 1), True)):
        for (x, y, w, h) in cas["profile"].detectMultiScale(g, 1.08, 6,
                                                            minSize=(lo, lo),
                                                            maxSize=(hi, hi)):
            if flip:
                x = small.shape[1] - x - w
            hits.append((2 * x, 2 * y, 2 * w, 2 * h, "profile"))
    best = None
    for (x, y, w, h, kind) in hits:
        cx = x + w / 2
        if not (0.12 * W < cx < 0.88 * W):
            continue
        if y + h > 0.92 * H:               # face cannot sit on the bottom edge at this range
            continue
        score = -w                         # tie-break: tighter box (Haar inflates close-ups)
        if kind == "front":
            roi = gray[y:y + int(0.60 * h), x:x + w]
            eyes = cas["eye"].detectMultiScale(roi, 1.1, 3,
                                               minSize=(w // 12, w // 12),
                                               maxSize=(w // 3, w // 3))
            kind = "front" if len(eyes) >= 1 else "front-noeye"
            if kind == "front":
                score += 10000             # eye-validated beats everything
        if best is None or score > best[1]:
            best = ((x, y, w, h), score, kind)
    return (best[0], best[2]) if best else (None, None)


def build_regions(box, shape):
    """Skull ellipse + neck trapezoid from a face box. Returns dict of uint8 masks:
    core (definite FG), base (probable FG), roi (hard outer limit)."""
    H, W = shape[:2]
    x, y, w, h = box
    cx = x + w / 2.0
    base = np.zeros((H, W), np.uint8)
    # b=0.92h (round 2 used 1.05h): the crown of a bald head tops out ~0.6 face-heights above
    # the Haar box, and the taller ellipse dragged a band of bookshelf into every mask
    cv2.ellipse(base, (int(cx), int(y + 0.28 * h)), (int(0.72 * w), int(0.88 * h)),
                0, 0, 360, 255, -1)
    # Neck stops at 1.5 face-heights: he is shirtless and the bare chest starts right below
    # the neck — a deeper trapezoid drags a chest strip into the mask (seen on k000/k041).
    neck = np.array([[cx - 0.30 * w, y + 0.95 * h], [cx + 0.30 * w, y + 0.95 * h],
                     [cx + 0.34 * w, y + 1.50 * h], [cx - 0.34 * w, y + 1.50 * h]], np.int32)
    cv2.fillConvexPoly(base, neck, 255)
    core = np.zeros((H, W), np.uint8)
    cv2.ellipse(core, (int(cx), int(y + 0.42 * h)), (int(0.26 * w), int(0.38 * h)),
                0, 0, 360, 255, -1)
    cv2.ellipse(core, (int(cx), int(y - 0.05 * h)), (int(0.22 * w), int(0.22 * h)),
                0, 0, 360, 255, -1)        # bald forehead/crown skin — definitely head
    # ROI ring width 0.06*w: run 1 used 0.12*w and 57% of every mask's area leaked into that
    # ring (chest/chair skin-toned bleed) — measured base_fill 0.63 at area_frac 0.32 on k000.
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (int(0.12 * w) | 1,) * 2)
    roi = cv2.dilate(base, k)
    # Ceiling at y-0.60h: the crown tops out ~0.5h above the Haar box on every inspected
    # frame (k000, k009, k041); round 3's 0.72h ceiling left a bookshelf band above the
    # crown inside ~10 passing masks.
    roi[:max(0, int(y - 0.60 * h)), :] = 0
    roi[:, :4] = 0
    roi[:, -4:] = 0                        # never let the ROI touch the frame sides
    core &= base
    return {"core": core, "base": base, "roi": roi, "box": [int(v) for v in box]}


def grabcut_head(img, reg):
    small = cv2.resize(img, None, fx=GC_SCALE, fy=GC_SCALE, interpolation=cv2.INTER_AREA)
    def rs(m):
        return cv2.resize(m, (small.shape[1], small.shape[0]), interpolation=cv2.INTER_NEAREST)
    core, base, roi = rs(reg["core"]), rs(reg["base"]), rs(reg["roi"])
    gc = np.full(small.shape[:2], cv2.GC_BGD, np.uint8)
    gc[roi > 0] = cv2.GC_PR_BGD
    gc[base > 0] = cv2.GC_PR_FGD
    # The second frontal cluster (k038-59) is backlit: the wall blows out to near-white and
    # becomes colorimetrically identical to overexposed skin, flooding the mask (measured
    # area_frac 0.43-0.55 there in round 2). Blown ACHROMATIC pixels are wall, not skin —
    # skin keeps chroma at the boundary — so force them to definite BG outside the core.
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    blown = (hsv[:, :, 1] < 25) & (hsv[:, :, 2] > 235) & (core == 0)
    gc[blown] = cv2.GC_BGD
    gc[core > 0] = cv2.GC_FGD
    if not ((gc == cv2.GC_FGD).any() and (gc == cv2.GC_BGD).any()):
        return None
    bgd = np.zeros((1, 65), np.float64)
    fgd = np.zeros((1, 65), np.float64)
    cv2.grabCut(small, gc, None, bgd, fgd, GC_ITERS, cv2.GC_INIT_WITH_MASK)
    binm = np.where((gc == cv2.GC_FGD) | (gc == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
    binm = cv2.resize(binm, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST)
    binm &= reg["roi"]
    # 19 px opening: guitar-headstock / book-spine spikes 15-30 px wide survived a 9 px
    # kernel in rounds 2-3; the thinnest true head feature (ear rim) is ~80 px here
    binm = cv2.morphologyEx(binm, cv2.MORPH_OPEN,
                            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (19, 19)))
    binm = cv2.morphologyEx(binm, cv2.MORPH_CLOSE,
                            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (17, 17)))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(binm)
    if n < 2:
        return None
    binm = np.where(lab == 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA]), 255, 0).astype(np.uint8)
    return (binary_fill_holes(binm > 0).astype(np.uint8)) * 255


def qa_mask(mask, reg, shape):
    H, W = shape[:2]
    reasons = []
    area = int(np.count_nonzero(mask))
    frac = area / (H * W)
    if not (QA_AREA_FRAC[0] <= frac <= QA_AREA_FRAC[1]):
        reasons.append(f"area_frac={frac:.3f}")
    # scale-aware bleed gate: the skull+neck prior IS the expected mask, so mask pixels
    # outside it are leak; run 1 measured 57% leak on masks that "looked" solid
    out_frac = (np.count_nonzero(mask & ~reg["base"]) / area) if area else 1.0
    if out_frac > 0.30:
        reasons.append(f"outside_base={out_frac:.2f}")
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if cnts:
        c = max(cnts, key=cv2.contourArea)
        hull_a = cv2.contourArea(cv2.convexHull(c))
        sol = cv2.contourArea(c) / hull_a if hull_a > 0 else 0
        if sol < QA_MIN_SOLIDITY:
            reasons.append(f"solidity={sol:.2f}")
    else:
        sol = 0.0
        reasons.append("empty")
    base_a = np.count_nonzero(reg["base"])
    fill = np.count_nonzero(mask & reg["base"]) / base_a if base_a else 0
    if fill < QA_MIN_BASE_FILL:
        reasons.append(f"base_fill={fill:.2f}")
    x, y, w, h = reg["box"]
    if mask[min(H - 1, int(y + 0.42 * h)), min(W - 1, int(x + w / 2))] == 0:
        reasons.append("core_center_empty")
    ys, xs = np.nonzero(mask)
    if len(ys):
        bot = ys.max()
        bw = np.count_nonzero(mask[max(0, bot - 4):bot + 1, :].any(axis=0))
        if bw > 1.15 * w:                  # wider than a face at the bottom cut = shoulders
            reasons.append(f"bottom_width={bw}px>1.15*face_w")
        if xs.min() < 6 or xs.max() > W - 7:
            reasons.append("touches_side_border")
    return {"ok": not reasons, "reasons": reasons, "area_frac": round(frac, 4),
            "solidity": round(sol, 3), "base_fill": round(fill, 3)}


def propagate_regions(sift, feats, src_idx, dst_idx, src_reg, shape):
    kps_s, des_s = feats[src_idx]
    kps_d, des_d = feats[dst_idx]
    if des_s is None or des_d is None:
        return None, 0
    pts_s = np.array([kp.pt for kp in kps_s])
    inside = src_reg["base"][pts_s[:, 1].astype(int).clip(0, shape[0] - 1),
                             pts_s[:, 0].astype(int).clip(0, shape[1] - 1)] > 0
    if inside.sum() < 50:
        return None, 0
    idx_map = np.nonzero(inside)[0]
    bf = cv2.BFMatcher()
    matches = bf.knnMatch(des_s[idx_map], des_d, k=2)
    good = [m for m, n2 in matches if m.distance < 0.75 * n2.distance]
    if len(good) < MIN_PROP_INLIERS:
        return None, len(good)
    src_pts = np.float32([kps_s[idx_map[m.queryIdx]].pt for m in good]).reshape(-1, 1, 2)
    dst_pts = np.float32([kps_d[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    Hmat, inl = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 3.0)
    n_inl = int(inl.sum()) if inl is not None else 0
    if Hmat is None or n_inl < MIN_PROP_INLIERS:
        return None, n_inl
    x, y, w, h = src_reg["box"]
    corners = np.float32([[x, y], [x + w, y], [x + w, y + h], [x, y + h]]).reshape(-1, 1, 2)
    wc = cv2.perspectiveTransform(corners, Hmat).reshape(-1, 2)
    nx, ny = wc[:, 0].min(), wc[:, 1].min()
    nw, nh = wc[:, 0].max() - nx, wc[:, 1].max() - ny
    s = np.sqrt(max(nw * nh, 1.0) / (w * h))
    if not (0.5 < s < 2.0):               # a sane propagation cannot halve/double the head
        return None, n_inl
    # absolute gates: run 1 let chained propagations balloon (k034 got a box covering 79%
    # of the frame); a real face box in this footage is 300-950 px and mostly in-frame
    if not (280 <= nw <= 950):
        return None, n_inl
    ivis = (max(0.0, min(nx + nw, shape[1]) - max(nx, 0.0)) *
            max(0.0, min(ny + nh, shape[0]) - max(ny, 0.0))) / (nw * nh)
    if ivis < 0.55:
        return None, n_inl
    return build_regions((nx, ny, nw, nh), shape), n_inl


def contact_sheets(frames, records, masks, prefix):
    tiles = []
    for i, img in enumerate(frames):
        r = records[i]
        vis = img.copy()
        if masks[i] is not None:
            cnts, _ = cv2.findContours(masks[i], cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(vis, cnts, -1, (0, 255, 0), 6)
            dark = cv2.addWeighted(vis, 0.35, np.zeros_like(vis), 0.65, 0)
            vis = np.where(masks[i][:, :, None] > 0, vis, dark)
        if r.get("box"):
            x, y, w, h = r["box"]
            cv2.rectangle(vis, (x, y), (x + w, y + h), (0, 255, 255), 4)
        t = cv2.resize(vis, (270, 480), interpolation=cv2.INTER_AREA)
        ok = r["qa"]["ok"] if r.get("qa") else False
        col = (0, 200, 0) if ok else (0, 0, 255)
        tag = f"k{i:03d} {r['source']}" + ("" if ok else " FAIL")
        cv2.rectangle(t, (0, 0), (269, 26), (0, 0, 0), -1)
        cv2.putText(t, tag, (4, 19), cv2.FONT_HERSHEY_SIMPLEX, 0.55, col, 2)
        tiles.append(t)
    paths = []
    for s in range(2):
        chunk = tiles[s * 30:(s + 1) * 30]
        while len(chunk) < 30:
            chunk.append(np.zeros((480, 270, 3), np.uint8))
        rows = [np.hstack(chunk[r * 6:(r + 1) * 6]) for r in range(5)]
        sheet = np.vstack(rows)
        p = os.path.join(OUT_DIR, f"{prefix}_{s + 1}.png")
        cv2.imwrite(p, sheet)
        paths.append(p)
    return paths


def main():
    os.makedirs(MASKS_DIR, exist_ok=True)
    os.makedirs(DEBUG_DIR, exist_ok=True)
    cas = load_cascades()
    frames, grays = [], []
    for i in range(N_FRAMES):
        img = cv2.imread(os.path.join(FRAMES_DIR, f"k{i:03d}.jpg"))
        assert img is not None and img.shape[:2] == (1920, 1080), f"k{i:03d} bad"
        frames.append(img)
        grays.append(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
    shape = frames[0].shape

    records = [{"frame": f"k{i:03d}", "source": "none", "box": None, "qa": None}
               for i in range(N_FRAMES)]
    regions = [None] * N_FRAMES

    for i in range(N_FRAMES):
        box, kind = detect_face(grays[i], cas)
        if box is not None:
            records[i]["box"] = [int(v) for v in box]
            records[i]["source"] = kind

    # temporal corroboration: keep 'front-noeye' only if a neighbour's validated box overlaps
    def iou(a, b):
        ax, ay, aw, ah = a; bx, by, bw, bh = b
        ix = max(0, min(ax + aw, bx + bw) - max(ax, bx))
        iy = max(0, min(ay + ah, by + bh) - max(ay, by))
        inter = ix * iy
        return inter / (aw * ah + bw * bh - inter) if inter else 0.0
    for i in range(N_FRAMES):
        if records[i]["source"] == "front-noeye":
            ok = any(records[j]["source"] in ("front", "profile") and records[j]["box"]
                     and iou(records[i]["box"], records[j]["box"]) > 0.35
                     for j in range(max(0, i - 2), min(N_FRAMES, i + 3)) if j != i)
            if not ok:
                records[i]["source"] = "none"
                records[i]["box"] = None

    for i in range(N_FRAMES):
        if records[i]["box"] is not None:
            regions[i] = build_regions(records[i]["box"], shape)

    sift = cv2.SIFT_create(nfeatures=3000)
    feat_cache = {}

    def feats_get(i):                  # lazy: only frames that propagation actually touches
        if i not in feat_cache:
            feat_cache[i] = sift.detectAndCompute(grays[i], None)
        return feat_cache[i]

    class _Lazy:
        def __getitem__(self, i):
            return feats_get(i)
    feats = _Lazy()
    for _pass in range(3):
        placed = False
        for i in range(N_FRAMES):
            if regions[i] is not None:
                continue
            srcs = sorted((j for j in range(N_FRAMES) if regions[j] is not None
                           and records[j]["source"] != "propagated-far"),
                          key=lambda j: abs(j - i))[:5]
            for j in srcs:
                reg, n_inl = propagate_regions(sift, feats, j, i, regions[j], shape)
                if reg is not None:
                    regions[i] = reg
                    records[i]["box"] = reg["box"]
                    records[i]["source"] = (f"propagated<-k{j:03d}({n_inl}inl)"
                                            if abs(j - i) <= 4 else "propagated-far")
                    if records[i]["source"] == "propagated-far":
                        records[i]["source"] = f"propagated-far<-k{j:03d}({n_inl}inl)"
                    placed = True
                    break
        if not placed:
            break

    masks = [None] * N_FRAMES
    n_ok = 0
    for i in range(N_FRAMES):
        if regions[i] is None:
            records[i]["qa"] = {"ok": False, "reasons": ["no_head_region"]}
            continue
        m = grabcut_head(frames[i], regions[i])
        if m is None:
            records[i]["qa"] = {"ok": False, "reasons": ["grabcut_empty"]}
            continue
        records[i]["qa"] = qa_mask(m, regions[i], shape)
        masks[i] = m
        if records[i]["qa"]["ok"]:
            cv2.imwrite(os.path.join(MASKS_DIR, f"mask_k{i:03d}.png"), m)
            n_ok += 1
        print(records[i]["frame"], records[i]["source"], records[i]["qa"], flush=True)

    sheets = contact_sheets(frames, records, masks, "contact_masks")
    report = {"frames": N_FRAMES, "masks_passed_qa": n_ok,
              "verdict_notes": VERDICT_NOTES, "per_frame": records, "sheets": sheets}
    rp = os.path.join(OUT_DIR, "segmentation_report.json")
    with open(rp, "w") as f:
        json.dump(report, f, indent=1)
    print(f"\n{n_ok}/{N_FRAMES} masks passed QA -> {MASKS_DIR}")
    print("sheets:", *sheets)


if __name__ == "__main__":
    main()
