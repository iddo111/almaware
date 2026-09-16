"""split.py -- one decisive question. The channel reports the panel's TOTAL
brightness almost perfectly (r2=0.99) but carries no per-cell information
(r2~0.00). Two hypotheses explain that:
  (a) off-axis contrast collapse -- the far part of the panel has no contrast
  (b) veiling glare -- the lens is so close that light from the whole panel
      scatters over the whole sensor, so every pixel reads the global sum
Both predict the same thing at fine scale, but they differ at COARSE scale:
under (a) the near half still works; under (b) nothing local works at all.
So: show half the panel white and half black, and ask the camera which half.
"""
import sys, time, json
import cv2, numpy as np
from pathlib import Path

OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
SIZE, RECT, WAIT = 800, 256, 0.35
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
chk = ((np.indices((16, 16)).sum(0) % 2) * 255).astype(np.uint8)
cv2.imshow(win, panel(chk)); cv2.waitKey(30); time.sleep(1.0)
cap.set(cv2.CAP_PROP_AUTOFOCUS, 1); time.sleep(3.0)
for _ in range(40): cap.read()
cap.set(cv2.CAP_PROP_AUTOFOCUS, 0); cap.set(cv2.CAP_PROP_AUTO_WB, 0)
cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25); cap.set(cv2.CAP_PROP_EXPOSURE, -4)
time.sleep(1.0)
for _ in range(10): cap.read()


def shot(inner, n=5):
    cv2.imshow(win, panel(inner)); cv2.waitKey(1)
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < WAIT:
        cap.read(); cv2.waitKey(4)
    fr = []
    for _ in range(n):
        ok, f = cap.read()
        fr.append(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(np.float32)); cv2.waitKey(4)
    return np.mean(fr, axis=0)


B = shot(np.zeros((16, 16)), 8); W = shot(np.full((16, 16), 255), 8); D = W - B
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
ss = quad.sum(1); sd = np.diff(quad, axis=1).ravel()
src = np.array([quad[np.argmin(ss)], quad[np.argmin(sd)], quad[np.argmax(ss)], quad[np.argmax(sd)]], np.float32)
dst = np.array([[0, 0], [RECT - 1, 0], [RECT - 1, RECT - 1], [0, RECT - 1]], np.float32)
M = cv2.getPerspectiveTransform(src, dst)
warp = lambda i: cv2.warpPerspective(i, M, (RECT, RECT), flags=cv2.INTER_AREA)
Bw, Ww = warp(B), warp(W); GAIN = np.clip(Ww - Bw, 1.0, None)
resp = lambda i: (warp(i) - Bw) / GAIN

# raw (un-normalised) contrast profile: where on the panel does contrast survive?
prof_rows = [(int(100 * (Ww - Bw)[r0:r0 + 32, 20:-20].mean() / max((Ww - Bw)[20:-20, 20:-20].max(), 1)))
             for r0 in range(0, RECT - 31, 32)]
print("raw contrast by row band (top->bottom, %% of best): " + " ".join("%3d" % v for v in prof_rows))
prof_cols = [(int(100 * (Ww - Bw)[20:-20, c0:c0 + 32].mean() / max((Ww - Bw)[20:-20, 20:-20].max(), 1)))
             for c0 in range(0, RECT - 31, 32)]
print("raw contrast by col band (left->right, %% of best): " + " ".join("%3d" % v for v in prof_cols))

R = {"row_contrast_profile": prof_rows, "col_contrast_profile": prof_cols}
q = RECT // 4


def halves(inner, name):
    r = resp(shot(inner, 5))
    L = r[q:-q, 20:RECT // 2 - 10].mean(); Rr = r[q:-q, RECT // 2 + 10:-20].mean()
    T = r[20:RECT // 2 - 10, q:-q].mean(); Bo = r[RECT // 2 + 10:-20, q:-q].mean()
    print("  %-14s  left=%+.3f right=%+.3f  (L-R=%+.3f)   top=%+.3f bottom=%+.3f  (T-B=%+.3f)"
          % (name, L, Rr, L - Rr, T, Bo, T - Bo))
    return {"L": float(L), "R": float(Rr), "T": float(T), "B": float(Bo)}


v = np.zeros((16, 16), np.uint8); v[:, :8] = 255
R["left_white"] = halves(v, "LEFT white")
v = np.zeros((16, 16), np.uint8); v[:, 8:] = 255
R["right_white"] = halves(v, "RIGHT white")
v = np.zeros((16, 16), np.uint8); v[:8, :] = 255
R["top_white"] = halves(v, "TOP white")
v = np.zeros((16, 16), np.uint8); v[8:, :] = 255
R["bottom_white"] = halves(v, "BOTTOM white")

lr = (R["left_white"]["L"] - R["left_white"]["R"]) - (R["right_white"]["L"] - R["right_white"]["R"])
tb = (R["top_white"]["T"] - R["top_white"]["B"]) - (R["bottom_white"]["T"] - R["bottom_white"]["B"])
R["left_right_discrimination"] = float(lr)
R["top_bottom_discrimination"] = float(tb)
print("\n  LEFT/RIGHT discrimination : %+.3f   (1.0 = perfect, 0 = cannot tell)" % lr)
print("  TOP/BOTTOM discrimination : %+.3f" % tb)
R["verdict"] = ("coarse spatial information SURVIVES" if min(abs(lr), abs(tb)) > 0.5
                else "spatial information is LOST even at half-panel scale")
print("  VERDICT: " + R["verdict"])
cv2.imwrite(str(OUT / "split_gain.png"), np.clip(GAIN, 0, 255).astype(np.uint8))
cap.release(); cv2.destroyAllWindows()
(OUT / "SPLIT-TEST.json").write_text(json.dumps(R, indent=2), encoding="utf-8")
