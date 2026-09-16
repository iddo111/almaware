"""spectral.py -- wavelength multiplexing, the physical half of Iddo's rainbow.

Three DIFFERENT patterns are displayed at the same instant in the same place,
one in each colour channel. One beam, three signals. Then a physical filter is
put in the path and we ask which of the three survive.

That is not a resolution measurement. A copper wire cannot carry three numbers
in one place at one instant; a beam of light can, and a piece of coloured glass
demultiplexes it with no power and no circuit.

Usage:  spectral.py <label> <outdir>      e.g.  spectral.py no_filter  C:/tmp/optic
"""
import sys, time, json
import cv2, numpy as np
from pathlib import Path

LABEL = sys.argv[1]
OUT = Path(sys.argv[2]); OUT.mkdir(parents=True, exist_ok=True)
SIZE, RECT, WAIT = 800, 256, 0.35
X, Y = 2560 - SIZE - 20, 1440 - SIZE - 80
win = "OPTIC-LOOP"; m = SIZE // 10; INNER = SIZE - 2 * m
cv2.namedWindow(win, cv2.WINDOW_NORMAL); cv2.resizeWindow(win, SIZE, SIZE)
cv2.moveWindow(win, X, Y); cv2.setWindowProperty(win, cv2.WND_PROP_TOPMOST, 1)


def panel_bgr(inner_bgr):
    f = np.zeros((SIZE, SIZE, 3), np.uint8)
    f[m:-m, m:-m] = cv2.resize(inner_bgr, (INNER, INNER), interpolation=cv2.INTER_NEAREST)
    return f


cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280); cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
chk = ((np.indices((16, 16)).sum(0) % 2) * 255).astype(np.uint8)
cv2.imshow(win, panel_bgr(np.dstack([chk] * 3))); cv2.waitKey(30); time.sleep(1.0)
cap.set(cv2.CAP_PROP_AUTOFOCUS, 1); time.sleep(3.0)
for _ in range(40): cap.read()
cap.set(cv2.CAP_PROP_AUTOFOCUS, 0); cap.set(cv2.CAP_PROP_AUTO_WB, 0)
cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25); cap.set(cv2.CAP_PROP_EXPOSURE, -4)
time.sleep(1.0)
for _ in range(10): cap.read()


def shot(inner_bgr, n=6, wait=WAIT):
    cv2.imshow(win, panel_bgr(inner_bgr)); cv2.waitKey(1)
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < wait:
        cap.read(); cv2.waitKey(4)
    fr = []
    for _ in range(n):
        ok, f = cap.read()
        if not ok: raise SystemExit("camera read failed")
        fr.append(f.astype(np.float32)); cv2.waitKey(4)
    return np.mean(fr, axis=0)          # BGR float


# geometry from a white field
gray = lambda bgr: cv2.cvtColor(bgr.astype(np.uint8), cv2.COLOR_BGR2GRAY).astype(np.float32)
Bf = shot(np.zeros((16, 16, 3), np.uint8), 8, 0.8)
Wf = shot(np.full((16, 16, 3), 255, np.uint8), 8, 0.8)
D = gray(Wf) - gray(Bf)
mask = (D > 10.0).astype(np.uint8)
mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))
cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
if not cnts:
    print(json.dumps({"label": LABEL, "error": "NO_SCREEN_VISIBLE"})); sys.exit(6)
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

res = {"label": LABEL, "mask_px": int(mask.sum()),
       "white_level_bgr": [round(float(v), 1) for v in Wf.reshape(-1, 3).mean(0)],
       "black_level_bgr": [round(float(v), 1) for v in Bf.reshape(-1, 3).mean(0)]}
print("[%s] screen visible: %d px   white BGR=%s" % (LABEL, mask.sum(), res["white_level_bgr"]))

# ---- three DIFFERENT patterns, one per colour channel, shown together ----
G = 4
rng = np.random.default_rng(101)
patterns = {}          # channel -> GxG values actually sent
img = np.zeros((G, G, 3), np.uint8)
for ci, cname in enumerate(("B", "G", "R")):
    v = rng.integers(40, 256, size=(G, G))
    patterns[cname] = v
    img[:, :, ci] = v
cap_img = shot(img, 8)
wb, ww = warp(Bf), warp(Wf)
gain = np.clip(ww - wb, 2.0, None)
r = (warp(cap_img) - wb) / gain
rc = RECT // G
readout = {}
for ci, cname in enumerate(("B", "G", "R")):
    meas = np.array([[r[i * rc + rc // 4:(i + 1) * rc - rc // 4,
                        j * rc + rc // 4:(j + 1) * rc - rc // 4, ci].mean()
                      for j in range(G)] for i in range(G)])
    readout[cname] = meas

# crosstalk matrix: how well does camera channel X report screen channel Y?
CM = {}
for scr in ("B", "G", "R"):
    s = patterns[scr].ravel().astype(float)
    row = {}
    for camc in ("B", "G", "R"):
        q = readout[camc].ravel()
        row[camc] = round(float(np.corrcoef(s, q)[0, 1] ** 2), 3)
    CM[scr] = row
res["crosstalk_r2"] = CM
res["diagonal"] = {k: CM[k][k] for k in CM}
res["channel_amplitude"] = {k: round(float(np.ptp(readout[k])), 3) for k in readout}

print("  r2 of screen-channel (row) read from camera-channel (col):")
print("           camB   camG   camR")
for scr in ("B", "G", "R"):
    print("   scr%s  %6.3f %6.3f %6.3f" % (scr, CM[scr]["B"], CM[scr]["G"], CM[scr]["R"]))
print("  diagonal (own channel recovered): B=%.3f G=%.3f R=%.3f"
      % (CM["B"]["B"], CM["G"]["G"], CM["R"]["R"]))
print("  channel amplitude through the path: %s" % res["channel_amplitude"])

# per-channel pure brightness, for a filter transmission estimate
for ci, cname in enumerate(("B", "G", "R")):
    pure = np.zeros((16, 16, 3), np.uint8); pure[:, :, ci] = 255
    f = shot(pure, 6)
    res.setdefault("pure_channel_response", {})[cname] = [round(float(v), 1) for v in f.reshape(-1, 3).mean(0)]
print("  pure-channel camera response (BGR): %s" % res["pure_channel_response"])

cv2.imwrite(str(OUT / ("spectral_%s.png" % LABEL)), np.clip(warp(cap_img), 0, 255).astype(np.uint8))
cap.release(); cv2.destroyAllWindows()
p = OUT / "SPECTRAL.json"
allres = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
allres[LABEL] = res
p.write_text(json.dumps(allres, indent=2), encoding="utf-8")
print("  saved -> %s  (labels so far: %s)" % (p, ", ".join(allres)))
