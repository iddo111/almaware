"""physical5.py -- v4 found the screen correctly but sliced cells from an
axis-aligned bounding box while the camera views the panel at a steep angle,
so per-cell readback was garbage. Here the responsive mask is fitted to a real
QUADRILATERAL and warped flat. Also: the v4 "optical sum" test was badly
designed (random 8x8 patterns all have mean ~127, so there was nothing to
correlate) -- here the pattern mean is swept across the usable drive range.
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
cv2.imshow(win, panel(np.full((8, 8), 200))); cv2.waitKey(30); time.sleep(1.0)
cap.set(cv2.CAP_PROP_AUTOFOCUS, 1); time.sleep(2.0)
for _ in range(25): cap.read()
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

# ---- 1. the screen defines itself, then is fitted to a QUAD ----
B = shot(np.zeros((8, 8)), 8, 0.8)
W = shot(np.full((8, 8), 255), 8, 0.8)
D = W - B
mask = (D > max(6.0, 0.30 * float(D.max()))).astype(np.uint8)
mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((11, 11), np.uint8))
mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((9, 9), np.uint8))
cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
if not cnts:
    print("NO_SCREEN"); sys.exit(5)
c = max(cnts, key=cv2.contourArea)
peri = cv2.arcLength(c, True)
quad = None
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

area = cv2.contourArea(c); rectarea = max(cv2.contourArea(src), 1.0)
R["geometry"] = {"mask_px": int(mask.sum()), "quad": src.tolist(),
                 "quad_fill": float(area / rectarea),
                 "delta_mean": float(D[mask > 0].mean())}
print("screen quad: %d px, fill %.3f, mean delta %.1f counts"
      % (int(mask.sum()), area / rectarea, D[mask > 0].mean()))

Bw, Ww = warp(B), warp(W)
GAIN = np.clip(Ww - Bw, 1.0, None)
inner = (slice(18, RECT - 18), slice(18, RECT - 18))
good = GAIN > 0.35 * np.median(GAIN[inner])
print("warped gain: median %.1f counts, %.1f%% responsive after warp"
      % (np.median(GAIN[inner]), 100 * good[inner].mean()))
R["geometry"]["warped_gain_median"] = float(np.median(GAIN[inner]))
R["geometry"]["responsive_frac_after_warp"] = float(good[inner].mean())
cv2.imwrite(str(OUT / "v5_warp_white.png"), np.clip(Ww, 0, 255).astype(np.uint8))
cv2.imwrite(str(OUT / "v5_gain.png"), np.clip(GAIN, 0, 255).astype(np.uint8))


def resp(img):
    r = (warp(img) - Bw) / GAIN
    return r, float(r[inner][good[inner]].mean())


# ---- 2. transfer curve, shuffled order, every level measured twice ----
levels = list(range(0, 256, 16)) + [255]
order = levels * 2
rng = np.random.default_rng(11); rng.shuffle(order)
obs = {L: [] for L in levels}
for L in order:
    obs[L].append(resp(shot(np.full((8, 8), L), 4))[1])
curve = [{"level": L, "resp": float(np.mean(obs[L])),
          "spread": float(abs(obs[L][0] - obs[L][1]))} for L in levels]
for cc in curve:
    print("  L=%3d -> %+.4f  (spread %.4f)" % (cc["level"], cc["resp"], cc["spread"]))
rp = np.array([cc["resp"] for cc in curve])
drift = float(np.mean([cc["spread"] for cc in curve]))
R["transfer_curve"] = curve; R["drift"] = drift
R["monotonic_full"] = bool(np.all(np.diff(rp) > -0.02))
hi = [i for i, L in enumerate(levels) if L >= 128]
R["monotonic_upper_half"] = bool(np.all(np.diff(rp[hi]) > -0.01))
R["swing_upper_half"] = float(rp[-1] - rp[hi[0]])
R["effective_bits_upper_half"] = float(np.log2(abs(R["swing_upper_half"]) / max(drift, 1e-9)))

# ---- 3. round-trip latency ----
lats = []
for i in range(8):
    a, b = (128, 255) if i % 2 == 0 else (255, 128)
    base = resp(shot(np.full((8, 8), a), 2))[1]
    t0 = time.perf_counter(); cv2.imshow(win, panel(np.full((8, 8), b))); cv2.waitKey(1)
    for _ in range(50):
        ok, f = cap.read(); cv2.waitKey(3)
        v = resp(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(np.float32))[1]
        if abs(v - base) > 0.25:
            lats.append((time.perf_counter() - t0) * 1000); break
R["latency_ms"] = {"n": len(lats), "median": float(np.median(lats)) if lats else None}

# ---- 4. VECTOR channel, driven only in the usable range 128..255 ----
Gn = 8; rc = RECT // Gn; sent = []; got = []
for t in range(10):
    vals = rng.integers(128, 256, size=(Gn, Gn))
    r, _ = resp(shot(vals, 4))
    meas = np.array([[r[i * rc + rc // 4:(i + 1) * rc - rc // 4,
                        j * rc + rc // 4:(j + 1) * rc - rc // 4].mean()
                      for j in range(Gn)] for i in range(Gn)])
    sent.append(vals.ravel().astype(float)); got.append(meas.ravel())
    if t == 0:
        cv2.imwrite(str(OUT / "v5_sent.png"),
                    cv2.resize(vals.astype(np.uint8), (256, 256), interpolation=cv2.INTER_NEAREST))
        cv2.imwrite(str(OUT / "v5_got.png"), np.clip(r * 255, 0, 255).astype(np.uint8))
sv = np.concatenate(sent); qv = np.concatenate(got)
rr = float(np.corrcoef(sv, qv)[0, 1])
a_, b_ = np.polyfit(sv, qv, 1)
resid = qv - (a_ * sv + b_)
rms = float(np.sqrt(np.mean(resid ** 2)))
R["vector_channel"] = {"cells": 64, "trials": len(sent), "r2": rr * rr, "rms": rms,
                       "bits_per_cell": float(np.log2(np.ptp(qv) / max(rms, 1e-9)))}

# ---- 5. optical SUM -- sweep the pattern mean deliberately ----
d = []
for mu in np.linspace(130, 252, 10):
    vals = np.clip(rng.normal(mu, 18, size=(Gn, Gn)), 128, 255).astype(int)
    d.append((float(vals.mean()), resp(shot(vals, 4))[1]))
d = np.array(d)
rsx = float(np.corrcoef(d[:, 0], d[:, 1])[0, 1])
R["optical_sum"] = {"n": len(d), "r2": rsx * rsx,
                    "mean_range": [float(d[:, 0].min()), float(d[:, 0].max())],
                    "residual_pct": float(100 * np.std(d[:, 1] - np.polyval(np.polyfit(d[:, 0], d[:, 1], 1), d[:, 0])) / np.ptp(d[:, 1]))}

cap.release(); cv2.destroyAllWindows()
(OUT / "PHYSICAL-OPTIC-v5.json").write_text(json.dumps(R, indent=2), encoding="utf-8")
print("\n===== PHYSICAL v5 =====")
print("geometry     quad fill %.3f, %.1f%% responsive after warp"
      % (R["geometry"]["quad_fill"], 100 * R["geometry"]["responsive_frac_after_warp"]))
print("transfer     monotonic(full)=%s  monotonic(L>=128)=%s"
      % (R["monotonic_full"], R["monotonic_upper_half"]))
print("             usable swing %.3f, drift %.4f -> %.1f effective bits"
      % (R["swing_upper_half"], drift, R["effective_bits_upper_half"]))
if R["latency_ms"]["median"]:
    print("latency      median %.0f ms -> %.1f Hz"
          % (R["latency_ms"]["median"], 1000 / R["latency_ms"]["median"]))
print("vector 8x8   r2=%.4f  %.1f bits/cell" % (R["vector_channel"]["r2"], R["vector_channel"]["bits_per_cell"]))
print("optical SUM  r2=%.4f  residual %.1f%%" % (R["optical_sum"]["r2"], R["optical_sum"]["residual_pct"]))
