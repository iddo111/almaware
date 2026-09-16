"""Find an exposure setting where the camera actually SEES the screen swing."""
import time, cv2, numpy as np
SIZE, X, Y = 800, 2560-820, 1440-880
win="OPTIC-LOOP"; cv2.namedWindow(win, cv2.WINDOW_NORMAL); cv2.resizeWindow(win,SIZE,SIZE)
cv2.moveWindow(win,X,Y); cv2.setWindowProperty(win, cv2.WND_PROP_TOPMOST,1)
def show(v):
    f=np.full((SIZE,SIZE,3), v, np.uint8); cv2.imshow(win,f)
    for _ in range(3): cv2.waitKey(15)
cap=cv2.VideoCapture(0, cv2.CAP_DSHOW)
cap.set(cv2.CAP_PROP_FRAME_WIDTH,1280); cap.set(cv2.CAP_PROP_FRAME_HEIGHT,720)
show(200); time.sleep(1.5)
cap.set(cv2.CAP_PROP_AUTOFOCUS,1); time.sleep(1.5)
for _ in range(20): cap.read()
cap.set(cv2.CAP_PROP_AUTOFOCUS,0); cap.set(cv2.CAP_PROP_AUTO_WB,0)
print("readback AUTO_EXPOSURE =", cap.get(cv2.CAP_PROP_AUTO_EXPOSURE),
      " EXPOSURE =", cap.get(cv2.CAP_PROP_EXPOSURE), " FOCUS =", cap.get(cv2.CAP_PROP_FOCUS))
def mean_now(v, settle=0.45):
    show(v); time.sleep(settle)
    for _ in range(4): cap.read()
    ok,f=cap.read(); g=cv2.cvtColor(f,cv2.COLOR_BGR2GRAY)
    c=g[120:600, 220:1060]
    return float(c.mean()), float((c>=254).mean()*100)
print("\n-- AUTO exposure (baseline) --")
cap.set(cv2.CAP_PROP_AUTO_EXPOSURE,0.75); time.sleep(0.8)
b,_=mean_now(0); w,s=mean_now(255); print(f"   black={b:6.2f} white={w:6.2f} swing={w-b:6.2f} sat={s:.1f}%")
print("\n-- MANUAL exposure sweep --")
best=None
cap.set(cv2.CAP_PROP_AUTO_EXPOSURE,0.25); time.sleep(0.5)
for e in [-4,-5,-6,-7,-8,-9,-10,-11]:
    cap.set(cv2.CAP_PROP_EXPOSURE, e); time.sleep(0.5)
    for _ in range(5): cap.read()
    b,_=mean_now(0); w,s=mean_now(255)
    got=cap.get(cv2.CAP_PROP_EXPOSURE)
    print(f"  exp={e:4d} (got {got:6.1f})  black={b:6.2f} white={w:6.2f} swing={w-b:7.2f} sat={s:5.1f}%")
    if s<0.5 and (best is None or w-b>best[1]): best=(e,w-b)
print("\nBEST:", best)
cap.release(); cv2.destroyAllWindows()
