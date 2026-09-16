"""physical.py -- STAGE B: characterise the real screen->air->camera channel.
Real photons. Numbers, not vibes. Nothing here is simulated."""
import sys, time, json, datetime
import cv2, numpy as np
from pathlib import Path
import calibration as calib

OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
SIZE, SCREEN_W, SCREEN_H = 800, 2560, 1440
X, Y = SCREEN_W - SIZE - 20, SCREEN_H - SIZE - 80
RECT = 256          # rectified resolution
win = "OPTIC-LOOP"

cv2.namedWindow(win, cv2.WINDOW_NORMAL); cv2.resizeWindow(win, SIZE, SIZE)
cv2.moveWindow(win, X, Y); cv2.setWindowProperty(win, cv2.WND_PROP_TOPMOST, 1)

def show(img_u8, settle=3):
    cv2.imshow(win, img_u8)
    for _ in range(settle): cv2.waitKey(15)

cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280); cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
cap.set(cv2.CAP_PROP_AUTOFOCUS, 1)
cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)   # DSHOW: 0.25 = manual
cap.set(cv2.CAP_PROP_AUTO_WB, 0)
show(np.full((SIZE, SIZE, 3), 128, np.uint8)); time.sleep(2.0)
for _ in range(20): cap.read()
cap.set(cv2.CAP_PROP_AUTOFOCUS, 0)          # lock focus after it settles

def grab(n=1):
    fs = []
    for _ in range(n):
        ok, f = cap.read()
        if not ok: raise SystemExit("camera read failed")
        fs.append(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(np.float32))
        cv2.waitKey(5)
    return fs

R = {"utc": datetime.datetime.now().isoformat(timespec="seconds")}

# ---------- 0. geometry: white square -> homography ----------
m = SIZE // 10
frame = np.zeros((SIZE, SIZE, 3), np.uint8); frame[m:-m, m:-m] = 255
show(frame); time.sleep(0.6); grab(5)
g = grab(3)[-1].astype(np.uint8)
quad = calib.find_display_quad(g)
if quad is None: print("CALIB_FAIL"); sys.exit(4)
M = calib.compute_rectify_matrix(quad, RECT)
R["quad"] = quad.tolist()
def read_rect(n=3):
    return np.mean([calib.rectify(f.astype(np.uint8), M, RECT).astype(np.float32) for f in grab(n)], axis=0)
core = (slice(40, RECT-40), slice(40, RECT-40))

# ---------- A/B. transfer function + noise ----------
levels = list(range(0, 256, 16)) + [255]
curve = []
for L in levels:
    f = np.zeros((SIZE, SIZE, 3), np.uint8); f[m:-m, m:-m] = L
    show(f); time.sleep(0.18); grab(2)
    reps = [calib.rectify(x.astype(np.uint8), M, RECT).astype(np.float32)[core].mean() for x in grab(5)]
    curve.append({"level": L, "cam_mean": float(np.mean(reps)), "cam_temporal_std": float(np.std(reps))})
    print(f"  L={L:3d} -> cam {np.mean(reps):6.2f}  +-{np.std(reps):.3f}")
R["transfer_curve"] = curve
lo, hi = curve[0]["cam_mean"], curve[-1]["cam_mean"]
noise = float(np.mean([c["cam_temporal_std"] for c in curve]))
R["dynamic_range_counts"] = hi - lo
R["mean_temporal_noise"] = noise
R["effective_bits"] = float(np.log2(max(hi - lo, 1e-6) / max(noise, 1e-6)))
# gamma fit on normalised curve
x = np.array([c["level"] for c in curve], float) / 255.0
y = (np.array([c["cam_mean"] for c in curve], float) - lo) / max(hi - lo, 1e-6)
ok = (x > 0.02) & (y > 0.02)
R["gamma"] = float(np.polyfit(np.log(x[ok]), np.log(np.clip(y[ok], 1e-6, None)), 1)[0])
R["monotonic"] = bool(np.all(np.diff([c["cam_mean"] for c in curve]) > -0.5))

# ---------- C. round-trip latency ----------
lats = []
for i in range(8):
    tgt = 255 if i % 2 == 0 else 0
    other = 0 if tgt == 255 else 255
    f0 = np.zeros((SIZE, SIZE, 3), np.uint8); f0[m:-m, m:-m] = other
    show(f0); time.sleep(0.25); grab(3)
    base = read_rect(1)[core].mean()
    f1 = np.zeros((SIZE, SIZE, 3), np.uint8); f1[m:-m, m:-m] = tgt
    t0 = time.perf_counter(); cv2.imshow(win, f1); cv2.waitKey(1)
    for _ in range(40):
        v = calib.rectify(grab(1)[0].astype(np.uint8), M, RECT).astype(np.float32)[core].mean()
        if abs(v - base) > 0.35 * abs(hi - lo):
            lats.append((time.perf_counter() - t0) * 1000); break
R["latency_ms"] = {"n": len(lats), "median": float(np.median(lats)) if lats else None,
                   "min": float(np.min(lats)) if lats else None, "max": float(np.max(lats)) if lats else None}

# ---------- D. can it carry a VECTOR? 8x8 cells, random values ----------
G = 8; cell = (SIZE - 2*m) // G
sent, got = [], []
rng = np.random.default_rng(0)
for trial in range(12):
    vals = rng.integers(0, 256, size=(G, G))
    f = np.zeros((SIZE, SIZE, 3), np.uint8)
    for i in range(G):
        for j in range(G):
            f[m+i*cell:m+(i+1)*cell, m+j*cell:m+(j+1)*cell] = int(vals[i, j])
    show(f); time.sleep(0.15); grab(2)
    rec = read_rect(3)
    rc = RECT // G
    meas = np.array([[rec[i*rc+rc//4:(i+1)*rc-rc//4, j*rc+rc//4:(j+1)*rc-rc//4].mean()
                      for j in range(G)] for i in range(G)])
    sent.append(vals.ravel()); got.append(meas.ravel())
    if trial == 0: cv2.imwrite(str(OUT/"vector_rectified.png"), rec.astype(np.uint8))
s = np.concatenate(sent).astype(float); q = np.concatenate(got).astype(float)
r = float(np.corrcoef(s, q)[0, 1])
R["vector_channel"] = {"cells": G*G, "trials": len(sent), "pearson_r": r, "r2": r*r}
# per-cell readback error after a global linear fit
a, b = np.polyfit(s, q, 1)
pred = a*s + b
R["vector_channel"]["rms_err_counts"] = float(np.sqrt(np.mean((q-pred)**2)))
R["vector_channel"]["bits_per_cell"] = float(np.log2(max(q.max()-q.min(),1e-6)/max(np.sqrt(np.mean((q-pred)**2)),1e-6)))

# ---------- E. does LIGHT do the addition? optical sum vs digital sum ----------
sums = []
for trial in range(10):
    vals = rng.integers(0, 256, size=(G, G))
    f = np.zeros((SIZE, SIZE, 3), np.uint8)
    for i in range(G):
        for j in range(G):
            f[m+i*cell:m+(i+1)*cell, m+j*cell:m+(j+1)*cell] = int(vals[i, j])
    show(f); time.sleep(0.15); grab(2)
    optical_total = read_rect(3)[core].mean()      # the sensor integrates the light itself
    sums.append((float(vals.mean()), float(optical_total)))
d = np.array(sums)
rs = float(np.corrcoef(d[:, 0], d[:, 1])[0, 1])
R["optical_sum"] = {"n": len(sums), "pearson_r": rs, "r2": rs*rs,
                    "residual_rms_pct": float(100*np.std(d[:,1]-np.polyval(np.polyfit(d[:,0],d[:,1],1),d[:,0]))/max(np.ptp(d[:,1]),1e-6))}

cap.release(); cv2.destroyAllWindows()
p = OUT/"PHYSICAL-OPTIC-2026-08-22.json"
p.write_text(json.dumps(R, indent=2), encoding="utf-8")
print("\n===== RESULT =====")
print(f"gamma            {R['gamma']:.2f}   monotonic={R['monotonic']}")
print(f"dynamic range    {R['dynamic_range_counts']:.1f} counts, noise {R['mean_temporal_noise']:.3f} -> {R['effective_bits']:.1f} effective bits")
print(f"latency          median {R['latency_ms']['median']} ms  (min {R['latency_ms']['min']})")
print(f"vector channel   r2={R['vector_channel']['r2']:.4f}  rms={R['vector_channel']['rms_err_counts']:.2f} counts  {R['vector_channel']['bits_per_cell']:.1f} bits/cell")
print(f"optical SUM      r2={R['optical_sum']['r2']:.4f}  residual {R['optical_sum']['residual_rms_pct']:.2f}% of range")
print(f"saved {p}")
