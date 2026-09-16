"""physical6.py -- v5 got a perfect monotonic transfer curve and a 0.99 optical
sum, but per-cell readback was r2=0.001. A global mean that is perfect while
per-cell is zero is the signature of a REGISTRATION error, not a physics one.
So: stop assuming. Light up single known cells and find out where they actually
land in the warped image, then measure the vector channel with the mapping
that the light itself reports.
"""
import sys, time, json, datetime
import cv2, numpy as np
from pathlib import Path

OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
SIZE, RECT, WAIT = 800, 256, 0.32
X, Y = 2560 - SIZE - 20, 1440 - SIZE - 80
win = "OPTIC-LOOP"; m = SIZE // 10
cv2.namedWindow(win, cv2.WINDOW_NORMAL); cv2.resizeWindow(win, SIZE, SIZE)
cv2.moveWindow(win, X, Y); cv2.setWindowProperty(win, cv2.WND_PROP_TOPMOST, 1)


def panel(inner):
    f = np.zeros((SIZE, SIZE, 3), np.uint8)
    b = cv2.resize(np.asarray(inner, np.uint8), (SIZE - 2 * m, SIZE - 2 * m),
                   interpolation=cv2.INTER_NEAREST)
    f[m:-m, m:-m] = b[..., None]
    return f


cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280); cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
# autofocus MUST have something to focus ON: a flat grey field gives the lens
# no gradient, so it locks at an arbitrary distance and every later measurement
# is a blur. Focus on a high-contrast checker instead, then lock.
_chk = ((np.indices((16, 16)).sum(0) % 2) * 255).astype(np.uint8)
cv2.imshow(win, panel(_chk)); cv2.waitKey(30); time.sleep(1.0)
cap.set(cv2.CAP_PROP_AUTOFOCUS, 1); time.sleep(3.0)
for _ in range(40): cap.read()
_ok, _f = cap.read()
_sharp = cv2.Laplacian(cv2.cvtColor(_f, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()
print("focus lock: sharpness (var of Laplacian) = %.1f  [<50 = blurred, >300 = sharp]" % _sharp)
cap.set(cv2.CAP_PROP_AUTOFOCUS, 0); cap.set(cv2.CAP_PROP_AUTO_WB, 0)
cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25); cap.set(cv2.CAP_PROP_EXPOSURE, -4)
time.sleep(1.0)
for _ in range(10): cap.read()


def shot(inner, n=5, wait=WAIT):
    cv2.imshow(win, panel(inner)); cv2.waitKey(1)
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < wait:
        cap.read(); cv2.waitKey(4)
    fr = []
    for _ in range(n):
        ok, f = cap.read()
        if not ok: raise SystemExit("camera read failed")
        fr.append(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(np.float32)); cv2.waitKey(4)
    return np.mean(fr, axis=0)


R = {"utc": datetime.datetime.now().isoformat(timespec="seconds")}
B = shot(np.zeros((8, 8)), 8, 0.8)
W = shot(np.full((8, 8), 255), 8, 0.8)
D = W - B
mask = (D > max(6.0, 0.30 * float(D.max()))).astype(np.uint8)
mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((11, 11), np.uint8))
mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((9, 9), np.uint8))
cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
c = max(cnts, key=cv2.contourArea); peri = cv2.arcLength(c, True); quad = None
for e in (0.02, 0.03, 0.04, 0.05, 0.06, 0.08, 0.10):
    ap = cv2.approxPolyDP(c, e * peri, True)
    if len(ap) == 4:
        quad = ap.reshape(4, 2).astype(np.float32); break
if quad is None:
    quad = cv2.boxPoints(cv2.minAreaRect(c)).astype(np.float32)
ssum = quad.sum(1); sdif = np.diff(quad, axis=1).ravel()
src = np.array([quad[np.argmin(ssum)], quad[np.argmin(sdif)],
                quad[np.argmax(ssum)], quad[np.argmax(sdif)]], np.float32)
dst = np.array([[0, 0], [RECT - 1, 0], [RECT - 1, RECT - 1], [0, RECT - 1]], np.float32)
M = cv2.getPerspectiveTransform(src, dst)
warp = lambda img: cv2.warpPerspective(img, M, (RECT, RECT), flags=cv2.INTER_AREA)
Bw, Ww = warp(B), warp(W)
GAIN = np.clip(Ww - Bw, 1.0, None)
resp = lambda img: (warp(img) - Bw) / GAIN
print("geometry ok: quad fill %.3f, warped gain median %.1f"
      % (cv2.contourArea(c) / max(cv2.contourArea(src), 1), np.median(GAIN[20:-20, 20:-20])))

# ---- THE REGISTRATION PROBE: light one cell, find where it lands ----
G = 8; rc = RECT // G
probes = [(0, 0), (0, G - 1), (G - 1, 0), (G - 1, G - 1), (3, 5)]
found = []
for (i, j) in probes:
    v = np.zeros((G, G), np.uint8); v[i, j] = 255
    r = resp(shot(v, 5))
    r = cv2.GaussianBlur(r, (9, 9), 3)
    yx = np.unravel_index(int(np.argmax(r)), r.shape)
    ci, cj = yx[0] / rc, yx[1] / rc
    found.append({"sent": [i, j], "peak_px": [int(yx[1]), int(yx[0])],
                  "landed_cell": [round(ci, 2), round(cj, 2)],
                  "peak_value": float(r[yx])})
    print("  sent cell (%d,%d) -> peak at cell (%.2f, %.2f)  value %.2f"
          % (i, j, ci, cj, r[yx]))
R["registration_probe"] = found
# how much of a single lit cell's light stays inside its own cell?
v = np.zeros((G, G), np.uint8); v[3, 5] = 255
r = np.clip(resp(shot(v, 6)), 0, None)
own = r[3 * rc:4 * rc, 5 * rc:6 * rc].sum()
R["crosstalk"] = {"energy_in_own_cell_pct": float(100 * own / max(r.sum(), 1e-9))}
print("  single-cell containment: %.1f%% of the light lands in its own cell"
      % R["crosstalk"]["energy_in_own_cell_pct"])
cv2.imwrite(str(OUT / "v7_single_cell.png"), np.clip(r * 255, 0, 255).astype(np.uint8))

# ---- vector channel, then every dihedral transform as a check ----
sent = []; got = []
rng = np.random.default_rng(23)
for t in range(10):
    vals = rng.integers(128, 256, size=(G, G))
    r = resp(shot(vals, 4))
    meas = np.array([[r[i * rc + rc // 4:(i + 1) * rc - rc // 4,
                        j * rc + rc // 4:(j + 1) * rc - rc // 4].mean()
                      for j in range(G)] for i in range(G)])
    sent.append(vals); got.append(meas)
    if t == 0:
        cv2.imwrite(str(OUT / "v7_sent.png"),
                    cv2.resize(vals.astype(np.uint8), (256, 256), interpolation=cv2.INTER_NEAREST))
        cv2.imwrite(str(OUT / "v7_got.png"), np.clip(r * 255, 0, 255).astype(np.uint8))

S = np.stack(sent).astype(float); Q = np.stack(got)


def r2_of(transform):
    q = np.stack([transform(x) for x in Q])
    a, b = S.ravel(), q.ravel()
    return float(np.corrcoef(a, b)[0, 1] ** 2)


TF = {"identity": lambda x: x, "rot90": lambda x: np.rot90(x, 1),
      "rot180": lambda x: np.rot90(x, 2), "rot270": lambda x: np.rot90(x, 3),
      "flipud": np.flipud, "fliplr": np.fliplr,
      "transpose": lambda x: x.T, "anti_transpose": lambda x: np.rot90(x, 2).T}
scores = {k: r2_of(f) for k, f in TF.items()}
best = max(scores, key=scores.get)
R["orientation_scan"] = scores
R["best_orientation"] = best
print("\n  orientation scan (r2 per dihedral transform):")
for k, v_ in sorted(scores.items(), key=lambda kv: -kv[1]):
    print("    %-14s r2=%.4f%s" % (k, v_, "   <== best" if k == best else ""))

q = np.stack([TF[best](x) for x in Q]).ravel()
s = S.ravel()
a_, b_ = np.polyfit(s, q, 1)
rms = float(np.sqrt(np.mean((q - (a_ * s + b_)) ** 2)))
R["vector_channel_best"] = {"orientation": best, "r2": scores[best], "rms": rms,
                            "bits_per_cell": float(np.log2(np.ptp(q) / max(rms, 1e-9)))}

# ---- and the same at a coarser grid: how many cells CAN it carry? ----
R["grid_scan"] = {}
for GG in (2, 4, 8, 16):
    rr = RECT // GG
    ss = []; qq = []
    for t in range(4):
        vals = rng.integers(128, 256, size=(GG, GG))
        r = resp(shot(vals, 3))
        meas = np.array([[r[i * rr + rr // 4:(i + 1) * rr - rr // 4,
                            j * rr + rr // 4:(j + 1) * rr - rr // 4].mean()
                          for j in range(GG)] for i in range(GG)])
        ss.append(TF[best](vals)); qq.append(meas)
    a = np.stack(ss).ravel().astype(float); b = np.stack(qq).ravel()
    val = float(np.corrcoef(a, b)[0, 1] ** 2)
    R["grid_scan"]["%dx%d" % (GG, GG)] = val
    print("  grid %2dx%-2d (%3d cells)  r2=%.4f" % (GG, GG, GG * GG, val))

cap.release(); cv2.destroyAllWindows()
(OUT / "PHYSICAL-OPTIC-v7.json").write_text(json.dumps(R, indent=2), encoding="utf-8")
print("\n===== v6 VERDICT =====")
print("best orientation : %s  (r2=%.4f, %.1f bits/cell)"
      % (best, scores[best], R["vector_channel_best"]["bits_per_cell"]))
print("single-cell containment: %.1f%%" % R["crosstalk"]["energy_in_own_cell_pct"])
print("grid scan        : " + "  ".join("%s=%.3f" % (k, v_) for k, v_ in R["grid_scan"].items()))
