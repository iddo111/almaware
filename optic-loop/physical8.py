"""physical8.py -- the split test found the real bug. The screen mask was
thresholded at 30% of peak delta, but the panel's contrast falls smoothly from
83% at the bottom to 32% at the top (off-axis viewing angle), so the threshold
CUT THE TOP OFF. Everything below the cut was then stretched over the whole
warped frame, which is exactly why left/right worked (1.41) and top/bottom did
not (0.003). Fix: threshold on an absolute delta, not a fraction of the peak.

Then, Iddo's idea: measure the channel the way vision science measures an eye --
with gratings and Gabor patches. The modulation transfer function tells us how
much contrast survives at each spatial frequency, which IS the answer to "how
many independent numbers can this optical path carry".
"""
import sys, time, json, datetime
import cv2, numpy as np
from pathlib import Path

OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
SIZE, RECT, WAIT = 800, 256, 0.32
X, Y = 2560 - SIZE - 20, 1440 - SIZE - 80
win = "OPTIC-LOOP"; m = SIZE // 10
INNER = SIZE - 2 * m
cv2.namedWindow(win, cv2.WINDOW_NORMAL); cv2.resizeWindow(win, SIZE, SIZE)
cv2.moveWindow(win, X, Y); cv2.setWindowProperty(win, cv2.WND_PROP_TOPMOST, 1)


def panel(inner):
    f = np.zeros((SIZE, SIZE, 3), np.uint8)
    b = cv2.resize(np.asarray(inner, np.uint8), (INNER, INNER), interpolation=cv2.INTER_NEAREST)
    f[m:-m, m:-m] = b[..., None]
    return f


cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280); cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
chk = ((np.indices((16, 16)).sum(0) % 2) * 255).astype(np.uint8)
cv2.imshow(win, panel(chk)); cv2.waitKey(30); time.sleep(1.0)
cap.set(cv2.CAP_PROP_AUTOFOCUS, 1); time.sleep(3.0)
for _ in range(40): cap.read()
_ok, _f = cap.read()
print("focus sharpness = %.1f" % cv2.Laplacian(cv2.cvtColor(_f, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var())
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
B = shot(np.zeros((16, 16)), 10, 0.8)
W = shot(np.full((16, 16), 255), 10, 0.8)
D = W - B
# THE FIX: absolute threshold. The dimmest part of the panel still swings tens
# of counts; a fraction-of-peak threshold amputates it.
THR = 10.0
mask = (D > THR).astype(np.uint8)
mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))
cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
c = max(cnts, key=cv2.contourArea); peri = cv2.arcLength(c, True); quad = None
for e in (0.02, 0.03, 0.04, 0.05, 0.06, 0.08, 0.10):
    ap = cv2.approxPolyDP(c, e * peri, True)
    if len(ap) == 4:
        quad = ap.reshape(4, 2).astype(np.float32); break
if quad is None:
    quad = cv2.boxPoints(cv2.minAreaRect(c)).astype(np.float32)
ss = quad.sum(1); sd = np.diff(quad, axis=1).ravel()
src = np.array([quad[np.argmin(ss)], quad[np.argmin(sd)], quad[np.argmax(ss)], quad[np.argmax(sd)]], np.float32)
dst = np.array([[0, 0], [RECT - 1, 0], [RECT - 1, RECT - 1], [0, RECT - 1]], np.float32)
M = cv2.getPerspectiveTransform(src, dst)
warp = lambda i: cv2.warpPerspective(i, M, (RECT, RECT), flags=cv2.INTER_AREA)
Bw, Ww = warp(B), warp(W); GAIN = np.clip(Ww - Bw, 2.0, None)
resp = lambda i: (warp(i) - Bw) / GAIN
prof = [int(100 * (Ww - Bw)[r:r + 32, 20:-20].mean() / max((Ww - Bw)[20:-20, 20:-20].max(), 1))
        for r in range(0, RECT - 31, 32)]
print("mask area %d px (was ~124k before fix); row contrast top->bottom: %s"
      % (int(mask.sum()), " ".join(str(p) for p in prof)))
R["geometry"] = {"mask_px": int(mask.sum()), "row_contrast": prof,
                 "gain_median": float(np.median(GAIN[20:-20, 20:-20]))}

# ---- 1. sanity: does top/bottom work now? ----
def halves(inner):
    r = resp(shot(inner, 5)); q = RECT // 4
    return (float(r[20:RECT // 2 - 10, q:-q].mean()), float(r[RECT // 2 + 10:-20, q:-q].mean()))
v = np.zeros((16, 16), np.uint8); v[:8, :] = 255; tw = halves(v)
v = np.zeros((16, 16), np.uint8); v[8:, :] = 255; bw = halves(v)
tb = (tw[0] - tw[1]) - (bw[0] - bw[1])
R["top_bottom_discrimination"] = float(tb)
print("  TOP white  -> top=%+.3f bottom=%+.3f" % tw)
print("  BOTTOM white-> top=%+.3f bottom=%+.3f" % bw)
print("  TOP/BOTTOM discrimination = %+.3f  (was +0.003)" % tb)

# ---- 2. MTF with full-field gratings (Iddo's Gabor idea, un-windowed) ----
def grating(freq, theta_deg, size=INNER):
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32) / size
    th = np.deg2rad(theta_deg)
    ph = 2 * np.pi * freq * (xx * np.cos(th) + yy * np.sin(th))
    return (127.5 + 120.0 * np.sin(ph)).astype(np.uint8)


def demod(img01, freq, theta_deg):
    """amplitude of the displayed frequency in the captured image"""
    size = img01.shape[0]
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32) / size
    th = np.deg2rad(theta_deg)
    ph = 2 * np.pi * freq * (xx * np.cos(th) + yy * np.sin(th))
    w = np.hanning(size)[:, None] * np.hanning(size)[None, :]
    z = img01 - (img01 * w).sum() / w.sum()
    a = 2 * (z * np.cos(ph) * w).sum() / w.sum()
    b = 2 * (z * np.sin(ph) * w).sum() / w.sum()
    return float(np.hypot(a, b))


mtf = {}
freqs = [1, 2, 3, 4, 6, 8, 12, 16, 24, 32]
for th in (0, 90, 45):
    row = []
    for f in freqs:
        g = grating(f, th)
        r = resp(shot(g, 4))
        row.append(round(demod(r[16:-16, 16:-16], f, th), 4))
    mtf["%ddeg" % th] = dict(zip([str(f) for f in freqs], row))
    norm = [x / max(row[0], 1e-9) for x in row]
    print("  MTF %2ddeg: " % th + "  ".join("%d:%.2f" % (f, n) for f, n in zip(freqs, norm)))
R["mtf"] = mtf
# cutoff: highest frequency still above 20% of the lowest-frequency response
cut = {}
for th, row in mtf.items():
    vals = [row[str(f)] for f in freqs]
    base = max(vals[0], 1e-9)
    ok = [f for f, v_ in zip(freqs, vals) if v_ / base > 0.20]
    cut[th] = max(ok) if ok else 0
R["mtf_cutoff_cycles"] = cut
print("  cutoff (>20%% of DC-adjacent response): " + str(cut))

# ---- 3. localized GABOR patches: does position survive? ----
def gabor_patch(cx, cy, freq=6, theta=0, sigma=0.10, size=INNER):
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32) / size
    th = np.deg2rad(theta)
    env = np.exp(-(((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * sigma ** 2)))
    ph = 2 * np.pi * freq * ((xx - cx) * np.cos(th) + (yy - cy) * np.sin(th))
    return np.clip(127.5 + 120.0 * env * np.sin(ph), 0, 255).astype(np.uint8)


spots = [(0.25, 0.25), (0.75, 0.25), (0.25, 0.75), (0.75, 0.75), (0.5, 0.5)]
gab = []
for (cx, cy) in spots:
    r = resp(shot(gabor_patch(cx, cy), 5))
    e = cv2.GaussianBlur(np.abs(r - np.median(r)), (0, 0), 6)
    e[:12] = e[-12:] = e[:, :12] = e[:, -12:] = 0
    yx = np.unravel_index(int(np.argmax(e)), e.shape)
    fx, fy = yx[1] / RECT, yx[0] / RECT
    err = float(np.hypot(fx - cx, fy - cy))
    gab.append({"sent": [cx, cy], "found": [round(fx, 3), round(fy, 3)], "err": round(err, 3)})
    print("  gabor at (%.2f,%.2f) -> found (%.2f,%.2f)  err %.3f of panel width" % (cx, cy, fx, fy, err))
R["gabor_localisation"] = gab
R["gabor_median_err"] = float(np.median([g["err"] for g in gab]))

# ---- 4. the vector channel, redone with the fixed mask ----
G = 8; rc = RECT // G; rng = np.random.default_rng(31); S = []; Q = []
for t in range(10):
    vals = rng.integers(128, 256, size=(G, G))
    r = resp(shot(vals, 4))
    meas = np.array([[r[i * rc + rc // 4:(i + 1) * rc - rc // 4,
                        j * rc + rc // 4:(j + 1) * rc - rc // 4].mean()
                      for j in range(G)] for i in range(G)])
    S.append(vals.ravel().astype(float)); Q.append(meas.ravel())
    if t == 0:
        cv2.imwrite(str(OUT / "v8_sent.png"), cv2.resize(vals.astype(np.uint8), (256, 256), interpolation=cv2.INTER_NEAREST))
        cv2.imwrite(str(OUT / "v8_got.png"), np.clip(r * 255, 0, 255).astype(np.uint8))
s = np.concatenate(S); q = np.concatenate(Q)
rr = float(np.corrcoef(s, q)[0, 1]); a_, b_ = np.polyfit(s, q, 1)
rms = float(np.sqrt(np.mean((q - (a_ * s + b_)) ** 2)))
R["vector_channel"] = {"r2": rr * rr, "rms": rms, "bits_per_cell": float(np.log2(np.ptp(q) / max(rms, 1e-9)))}

R["grid_scan"] = {}
for GG in (2, 4, 8, 16):
    rr2 = RECT // GG; a = []; b = []
    for t in range(4):
        vals = rng.integers(128, 256, size=(GG, GG))
        r = resp(shot(vals, 3))
        meas = np.array([[r[i * rr2 + rr2 // 4:(i + 1) * rr2 - rr2 // 4,
                            j * rr2 + rr2 // 4:(j + 1) * rr2 - rr2 // 4].mean()
                          for j in range(GG)] for i in range(GG)])
        a.append(vals.ravel().astype(float)); b.append(meas.ravel())
    val = float(np.corrcoef(np.concatenate(a), np.concatenate(b))[0, 1] ** 2)
    R["grid_scan"]["%dx%d" % (GG, GG)] = val
    print("  grid %2dx%-2d (%3d cells) r2=%.4f" % (GG, GG, GG * GG, val))

cap.release(); cv2.destroyAllWindows()
(OUT / "PHYSICAL-OPTIC-v8.json").write_text(json.dumps(R, indent=2), encoding="utf-8")
print("\n===== v8 =====")
print("top/bottom discrimination : %+.3f" % R["top_bottom_discrimination"])
print("MTF cutoff (cycles/panel) : %s" % R["mtf_cutoff_cycles"])
print("gabor localisation error  : %.3f of panel width (median)" % R["gabor_median_err"])
print("vector 8x8  r2=%.4f  %.1f bits/cell" % (R["vector_channel"]["r2"], R["vector_channel"]["bits_per_cell"]))
print("grid scan   " + "  ".join("%s=%.3f" % (k, v_) for k, v_ in R["grid_scan"].items()))
