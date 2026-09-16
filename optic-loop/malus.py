"""malus.py -- THE physics test, as opposed to everything measured so far.

Bits, MTF and latency are specifications of a webcam and a monitor. Iddo said
so plainly: "is it physics, it's just resolutions". He was right.

This is not that. An LCD emits LINEARLY POLARISED light -- there is a polariser
glued to the front of the panel, it is how the display works at all. Put a
second polariser (a real pair of polarised sunglasses) in the path and rotate
it, and the transmitted intensity must follow

        I(theta) = I0 * cos^2(theta)          -- Malus's law, 1809

That cos^2 is a MULTIPLICATION, performed by the material itself, with no
circuit, no clock and no energy. If the brightness traces it, the glass did
arithmetic. If the glasses are merely dark and not polarising, rotating them
changes nothing and the trace is flat -- which is the control, built in.

Run it, then rotate the sunglasses slowly and steadily through half a turn in
front of the camera while the screen shows white.

Usage:  malus.py <seconds> <outdir>
"""
import sys, time, json
import cv2, numpy as np
from pathlib import Path

DUR = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0
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
# exposure MUST be manual or the camera will undo the very effect we measure
cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25); cap.set(cv2.CAP_PROP_EXPOSURE, -4)
time.sleep(1.0)
for _ in range(12): cap.read()

# dark reference: what the camera reads with the screen black (room light + sensor floor)
cv2.imshow(win, black); cv2.waitKey(1); time.sleep(0.8)
for _ in range(6): cap.read()
dk = []
for _ in range(8):
    ok, f = cap.read(); dk.append(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(np.float32)); cv2.waitKey(4)
DARK = float(np.mean(dk))
cv2.imshow(win, white); cv2.waitKey(1); time.sleep(0.8)
for _ in range(6): cap.read()
print("dark reference (screen off) = %.1f counts" % DARK)
print("ROTATE THE SUNGLASSES SLOWLY, half a turn, for %.0f seconds. Starting now." % DUR)

ts, vals = [], []
t0 = time.perf_counter()
while time.perf_counter() - t0 < DUR:
    ok, f = cap.read()
    if not ok: break
    g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(np.float32)
    h, w = g.shape
    ts.append(time.perf_counter() - t0)
    vals.append(float(g[h // 4:3 * h // 4, w // 4:3 * w // 4].mean()))
    cv2.waitKey(1)
cap.release(); cv2.destroyAllWindows()

t = np.array(ts); v = np.array(vals)
sig = v - DARK
sig = np.clip(sig, 0.01, None)
k = max(3, int(len(sig) / 60))
sm = np.convolve(sig, np.ones(k) / k, mode="same")
lo, hi = float(np.percentile(sm, 2)), float(np.percentile(sm, 98))
mod = (hi - lo) / max(hi + lo, 1e-9)
res = {"seconds": DUR, "frames": len(v), "fps": round(len(v) / max(t[-1], 1e-9), 1),
       "dark_reference": round(DARK, 1),
       "min_counts": round(lo, 2), "max_counts": round(hi, 2),
       "modulation_depth": round(mod, 4),
       "extinction_ratio": round(hi / max(lo, 1e-6), 2)}

# how well does a cos^2 in time describe it? (valid if the rotation was steady)
best = None
for cyc in np.linspace(0.25, 3.0, 120):          # cos^2 cycles over the recording
    ph = 2 * np.pi * cyc * t / max(t[-1], 1e-9)
    Xd = np.c_[np.ones_like(t), np.cos(2 * ph), np.sin(2 * ph)]
    coef, *_ = np.linalg.lstsq(Xd, sm, rcond=None)
    pred = Xd @ coef
    ss = 1 - np.sum((sm - pred) ** 2) / max(np.sum((sm - sm.mean()) ** 2), 1e-9)
    if best is None or ss > best[0]: best = (ss, cyc, pred)
res["cos2_fit_r2"] = round(float(best[0]), 4)
res["cos2_cycles_in_recording"] = round(float(best[1]), 2)

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(9, 4), dpi=130)
    ax.plot(t, sig, lw=0.7, alpha=0.45, label="camera, screen-light only")
    ax.plot(t, sm, lw=2.0, label="smoothed")
    ax.plot(t, best[2], lw=1.6, ls="--", label="cos$^2$ fit  (r$^2$=%.3f)" % best[0])
    ax.set_xlabel("seconds"); ax.set_ylabel("intensity (counts above dark)")
    ax.set_title("Malus: rotating a polariser in front of an LCD   "
                 "modulation %.1f%%   extinction %.1f:1" % (100 * mod, res["extinction_ratio"]))
    ax.legend(fontsize=8); fig.tight_layout()
    fig.savefig(str(OUT / "malus.png")); res["plot"] = str(OUT / "malus.png")
except Exception as e:
    res["plot_error"] = str(e)

(OUT / "MALUS.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
print("\n===== MALUS =====")
print("frames %d at %.1f fps" % (res["frames"], res["fps"]))
print("intensity  min %.1f  max %.1f  counts above dark" % (lo, hi))
print("MODULATION DEPTH   %.1f%%   (polarised source + polariser -> large; plain dark glass -> ~0)" % (100 * mod))
print("EXTINCTION RATIO   %.1f : 1" % res["extinction_ratio"])
print("cos^2 fit r2       %.3f  over %.2f cycles" % (best[0], best[1]))
if mod > 0.5 and best[0] > 0.7:
    print("VERDICT: the glass performed cos^2 -- a multiplication done by the material.")
elif mod > 0.25:
    print("VERDICT: real polarisation modulation, partial. Rotate further / more steadily.")
else:
    print("VERDICT: no modulation. Either the glasses are not polarised, or they never")
    print("         got between the screen and the lens.")
