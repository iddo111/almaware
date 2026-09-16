"""malus2.py -- the first attempt failed for a human reason: rotating the
glasses meant disturbing the rig, and the trace came out as blackouts and
spikes, not a cos^2. Modulation "99.9%" was a hand over the lens. Void.

So this version does not ask for a steady rotation. It records for a while and
then throws away every moment when anything was MOVING, keeping only the still
plateaus, and reports the brightness of each one. Fumble all you like; only the
seconds where the picture held still are measured.

Protocol: lay one lens flat on the screen over the white square. Let go. Then
turn it by roughly a quarter turn, let go again. Repeat a few times. The camera
is never touched.

A polarising lens gives plateaus at very different brightness levels.
A merely dark lens gives plateaus all at the same level. That is the whole test.

Usage:  malus2.py <seconds> <outdir>
"""
import sys, time, json
import cv2, numpy as np
from pathlib import Path

DUR = float(sys.argv[1]) if len(sys.argv) > 1 else 40.0
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "."); OUT.mkdir(parents=True, exist_ok=True)
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
cv2.imshow(win, white); cv2.waitKey(30); time.sleep(1.0)
cap.set(cv2.CAP_PROP_AUTOFOCUS, 0); cap.set(cv2.CAP_PROP_AUTO_WB, 0)
cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25); cap.set(cv2.CAP_PROP_EXPOSURE, -4)
time.sleep(1.0)
for _ in range(12): cap.read()

cv2.imshow(win, black); cv2.waitKey(1); time.sleep(0.8)
for _ in range(6): cap.read()
dk = [cv2.cvtColor(cap.read()[1], cv2.COLOR_BGR2GRAY).astype(np.float32) for _ in range(8)]
DARK = float(np.mean(dk))
cv2.imshow(win, white); cv2.waitKey(1); time.sleep(0.8)
for _ in range(6): cap.read()
print("dark reference = %.1f counts" % DARK)
print("Lay a lens flat on the white square, let go, then turn it a quarter and let go.")
print("Recording %.0f s -- only the STILL moments will be measured." % DUR)

ts, means, motion = [], [], []
prev = None
t0 = time.perf_counter()
while time.perf_counter() - t0 < DUR:
    ok, f = cap.read()
    if not ok: break
    g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(np.float32)
    h, w = g.shape
    roi = g[h // 5:4 * h // 5, w // 5:4 * w // 5]
    ts.append(time.perf_counter() - t0)
    means.append(float(roi.mean()))
    motion.append(0.0 if prev is None else float(np.abs(roi - prev).mean()))
    prev = roi
    cv2.waitKey(1)
cap.release(); cv2.destroyAllWindows()

t = np.array(ts); v = np.array(means) - DARK; mo = np.array(motion)
k = 5
mo_s = np.convolve(mo, np.ones(k) / k, mode="same")
thr = max(0.8, float(np.percentile(mo_s, 25)) * 2.0)
still = mo_s < thr
# group consecutive still frames into plateaus of at least 0.4 s
plateaus = []
i = 0
while i < len(still):
    if still[i]:
        j = i
        while j < len(still) and still[j]: j += 1
        if t[j - 1] - t[i] >= 0.4:
            seg = v[i:j]
            plateaus.append({"t_start": round(float(t[i]), 2), "t_end": round(float(t[j - 1]), 2),
                             "seconds": round(float(t[j - 1] - t[i]), 2),
                             "intensity": round(float(np.median(seg)), 2),
                             "stability": round(float(np.std(seg)), 3)})
        i = j
    else:
        i += 1

res = {"seconds": DUR, "frames": len(v), "fps": round(len(v) / max(t[-1], 1e-9), 1),
       "dark_reference": round(DARK, 1), "motion_threshold": round(thr, 3),
       "still_fraction": round(float(still.mean()), 3), "plateaus": plateaus}
if plateaus:
    lev = np.array([p["intensity"] for p in plateaus])
    lo, hi = float(lev.min()), float(lev.max())
    res["plateau_min"] = round(lo, 2); res["plateau_max"] = round(hi, 2)
    res["plateau_modulation"] = round((hi - lo) / max(hi + lo, 1e-9), 4)
    res["n_plateaus"] = len(plateaus)

print("\n===== STILL-ONLY MEASUREMENT =====")
print("%d frames, %.0f%% of the recording was still" % (len(v), 100 * still.mean()))
if not plateaus:
    print("no stable plateau found -- nothing was ever held still long enough.")
else:
    for p in plateaus:
        print("  %5.1f-%5.1f s (%4.1f s)  intensity %7.2f   +-%.2f"
              % (p["t_start"], p["t_end"], p["seconds"], p["intensity"], p["stability"]))
    print("\nplateau range %.2f .. %.2f counts   modulation %.1f%%"
          % (res["plateau_min"], res["plateau_max"], 100 * res["plateau_modulation"]))
    if res["plateau_modulation"] > 0.35 and len(plateaus) >= 3:
        print("READS AS: the lens changes transmission with its ANGLE -> polarising.")
    elif len(plateaus) < 3:
        print("READS AS: too few held positions to conclude. Hold 3-4 angles, a second each.")
    else:
        print("READS AS: transmission does NOT depend on angle -> a plain tinted lens,")
        print("          not a polariser. (This is a real answer, not a failure.)")

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(9, 5), dpi=130, sharex=True,
                                 gridspec_kw={"height_ratios": [3, 1]})
    a1.plot(t, v, lw=0.6, alpha=0.35, color="gray", label="all frames")
    for p in plateaus:
        sel = (t >= p["t_start"]) & (t <= p["t_end"])
        a1.plot(t[sel], v[sel], lw=2.5, color="tab:orange")
        a1.annotate("%.1f" % p["intensity"], (np.mean(t[sel]), p["intensity"]),
                    fontsize=7, ha="center", va="bottom")
    a1.set_ylabel("intensity above dark"); a1.legend(fontsize=8)
    a1.set_title("Malus, still-moments only -- %d plateaus, modulation %.0f%%"
                 % (len(plateaus), 100 * res.get("plateau_modulation", 0)))
    a2.plot(t, mo_s, lw=0.8, color="tab:blue"); a2.axhline(thr, ls="--", lw=0.8, color="r")
    a2.set_ylabel("motion"); a2.set_xlabel("seconds")
    fig.tight_layout(); fig.savefig(str(OUT / "malus2.png"))
    res["plot"] = str(OUT / "malus2.png")
except Exception as e:
    res["plot_error"] = str(e)

(OUT / "MALUS2.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
