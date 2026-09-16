"""snapshot.py -- stage A of the physical test: put a known pattern in the
bottom-right corner of the screen, photograph it with the webcam, save BOTH
so a human (and Claude) can look at them. No loop, no learning. Just: does
an optical path from screen to camera exist at all?"""
import sys, time, cv2, numpy as np
from pathlib import Path

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
SIZE = 800                      # window size, logical px
SCREEN_W, SCREEN_H = 2560, 1440 # logical desktop (DPI-scaled)
X, Y = SCREEN_W - SIZE - 20, SCREEN_H - SIZE - 80

# --- the pattern: 8x8 checker + white border, unmistakable in a photo ---
pat = np.zeros((SIZE, SIZE, 3), np.uint8)
cell = SIZE // 10
for i in range(10):
    for j in range(10):
        if (i + j) % 2 == 0:
            pat[i*cell:(i+1)*cell, j*cell:(j+1)*cell] = 255
cv2.rectangle(pat, (0, 0), (SIZE-1, SIZE-1), (0, 0, 255), 12)   # red frame
cv2.circle(pat, (SIZE//2, SIZE//2), SIZE//6, (0, 255, 0), -1)   # green centre

win = "OPTIC-LOOP"
cv2.namedWindow(win, cv2.WINDOW_NORMAL)
cv2.resizeWindow(win, SIZE, SIZE)
cv2.moveWindow(win, X, Y)
cv2.setWindowProperty(win, cv2.WND_PROP_TOPMOST, 1)
cv2.imshow(win, pat)
for _ in range(30):
    cv2.waitKey(20)

# --- camera: VIDEO ONLY. No audio pin is ever opened. ---
cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
if not cap.isOpened():
    print("CAMERA_FAIL: could not open device 0"); cv2.destroyAllWindows(); sys.exit(2)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
cap.set(cv2.CAP_PROP_AUTOFOCUS, 0)
time.sleep(1.2)
ok = False
for _ in range(15):
    ok, frame = cap.read()
    cv2.waitKey(30)
if not ok:
    print("CAMERA_FAIL: opened but no frame"); cap.release(); cv2.destroyAllWindows(); sys.exit(3)

p = OUT / "camera-sees.png"
cv2.imwrite(str(p), frame)
g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
print(f"OK frame={frame.shape} saved={p}")
print(f"gray mean={g.mean():.1f} min={g.min()} max={g.max()} std={g.std():.1f}")
print(f"saturated(>=250)={100*(g>=250).mean():.2f}%  dark(<=5)={100*(g<=5).mean():.2f}%")
print(f"window placed at x={X} y={Y} size={SIZE}")
cap.release(); cv2.destroyAllWindows()
