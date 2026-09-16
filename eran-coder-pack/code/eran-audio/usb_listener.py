"""usb_listener.py — Eran's eye via a plugged-in USB camera.

Run this FIRST, then plug the camera in: it polls for a DirectShow camera, and
once it appears, grabs 1 frame every INTERVAL seconds into seen_usb/ (auto-pruned
to KEEP newest). Light + local + private (frames stay on this machine). Ctrl-C to stop.
"""
import os, time, datetime
import cv2

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seen_usb")
os.makedirs(OUT, exist_ok=True)
INTERVAL = 10      # seconds between frames
KEEP = 300         # auto-clear: keep newest N


def find_cam(max_idx=5):
    for i in range(max_idx):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
        if cap.isOpened():
            ok, _ = cap.read()
            if ok:
                return cap, i
            cap.release()
    return None, None


def prune():
    files = sorted(f for f in os.listdir(OUT) if f.endswith(".jpg"))
    for f in files[:-KEEP]:
        try:
            os.remove(os.path.join(OUT, f))
        except OSError:
            pass


print("USB listener: waiting for a camera — plug it in now...", flush=True)
cap, idx = None, None
while cap is None:
    cap, idx = find_cam()
    if cap is None:
        time.sleep(2)
print(f"camera found at index {idx} — capturing 1 frame / {INTERVAL}s into {OUT}", flush=True)

n = 0
while True:
    ok, frame = cap.read()
    if ok:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        cv2.imwrite(os.path.join(OUT, f"usb_{ts}.jpg"), frame)
        n += 1
        if n % 6 == 0:
            prune()
            print(f"[{ts}] {n} frames captured", flush=True)
    else:
        # camera unplugged? re-acquire
        cap.release()
        cap, idx = None, None
        print("camera lost — waiting for re-plug...", flush=True)
        while cap is None:
            cap, idx = find_cam()
            if cap is None:
                time.sleep(2)
    time.sleep(INTERVAL)
