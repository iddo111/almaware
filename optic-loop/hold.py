"""hold.py -- one number per lens orientation, and nothing else.

Two failed attempts taught the same lesson: a human holding a lens is a source
of motion, and motion looks exactly like signal. So this asks for nothing to be
held. Put the lens down, take your hands away, and let the recording run. The
script finds the single most stable window in the recording and reports its
brightness and how stable it was.

Run it once per orientation:
    hold.py A_flat   10  <outdir>
    hold.py B_turned 10  <outdir>       (after turning the lens a quarter turn)
    hold.py C_none   10  <outdir>       (lens removed -- the reference)

If the two orientations differ far beyond their own stability, the lens is
polarising and the material performed cos^2. If they agree, it is just tinted
glass. Either answer is a result.
"""
import sys, time, json
import cv2, numpy as np
from pathlib import Path

LABEL = sys.argv[1]
DUR = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0
OUT = Path(sys.argv[3] if len(sys.argv) > 3 else "."); OUT.mkdir(parents=True, exist_ok=True)
SIZE = 800
X, Y = 2560 - SIZE - 20, 1440 - SIZE - 80
win = "OPTIC-LOOP"; m = SIZE // 10
cv2.namedWindow(win, cv2.WINDOW_NORMAL); cv2.resizeWindow(win, SIZE, SIZE)
cv2.moveWindow(win, X, Y); cv2.setWindowProperty(win, cv2.WND_PROP_TOPMOST, 1)
white = np.zeros((SIZE, SIZE, 3), np.uint8); white[m:-m, m:-m] = 255
black = np.zeros((SIZE, SIZE, 3), np.uint8)

cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280); cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
cv2.imshow(win, white); cv2.waitKey(30); time.sleep(0.8)
cap.set(cv2.CAP_PROP_AUTOFOCUS, 0); cap.set(cv2.CAP_PROP_AUTO_WB, 0)
cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25); cap.set(cv2.CAP_PROP_EXPOSURE, -4)
time.sleep(0.8)
for _ in range(12): cap.read()
cv2.imshow(win, black); cv2.waitKey(1); time.sleep(0.7)
for _ in range(6): cap.read()
DARK = float(np.mean([cv2.cvtColor(cap.read()[1], cv2.COLOR_BGR2GRAY).astype(np.float32).mean()
                      for _ in range(8)]))
cv2.imshow(win, white); cv2.waitKey(1); time.sleep(0.7)
for _ in range(6): cap.read()
print("[%s] hands off. recording %.0f s ..." % (LABEL, DUR))

ts, vals = [], []
t0 = time.perf_counter()
while time.perf_counter() - t0 < DUR:
    ok, f = cap.read()
    if not ok: break
    g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(np.float32)
    h, w = g.shape
    ts.append(time.perf_counter() - t0)
    vals.append(float(g[h // 5:4 * h // 5, w // 5:4 * w // 5].mean()))
    cv2.waitKey(1)
cap.release(); cv2.destroyAllWindows()

t = np.array(ts); v = np.array(vals) - DARK
fps = len(v) / max(t[-1], 1e-9)
wlen = max(8, int(2.0 * fps))            # a two-second window
best = None
for i in range(0, len(v) - wlen):
    seg = v[i:i + wlen]
    sd = float(np.std(seg))
    if best is None or sd < best[0]:
        best = (sd, float(np.median(seg)), float(t[i]), float(t[i + wlen - 1]))
sd, level, ta, tb = best
res = {"label": LABEL, "dark": round(DARK, 1), "fps": round(fps, 1), "frames": len(v),
       "window": [round(ta, 2), round(tb, 2)],
       "intensity": round(level, 2), "stability_sd": round(sd, 3),
       "whole_run_median": round(float(np.median(v)), 2),
       "whole_run_sd": round(float(np.std(v)), 2)}
print("  most stable 2 s : %.1f-%.1f s" % (ta, tb))
print("  INTENSITY       : %.2f counts above dark   (+-%.3f -- this is the error bar)" % (level, sd))
print("  whole run       : median %.2f, sd %.2f" % (res["whole_run_median"], res["whole_run_sd"]))
if sd > 1.5:
    print("  WARNING: nothing was still enough. Take your hands off and run it again.")

p = OUT / "HOLD.json"
allr = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
allr[LABEL] = res
p.write_text(json.dumps(allr, indent=2), encoding="utf-8")

labs = [k for k in allr if allr[k]["stability_sd"] <= 1.5]
if len(labs) >= 2:
    print("\n  --- comparison of stable runs ---")
    for k in labs:
        print("    %-12s %8.2f  +-%.3f" % (k, allr[k]["intensity"], allr[k]["stability_sd"]))
    lv = [allr[k]["intensity"] for k in labs]
    err = max(allr[k]["stability_sd"] for k in labs)
    spread = max(lv) - min(lv)
    print("    spread %.2f counts, largest error bar %.3f  -> %.0f sigma"
          % (spread, err, spread / max(err, 1e-9)))
print("  saved: %s  (runs so far: %s)" % (p, ", ".join(allr)))
