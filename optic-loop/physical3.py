"""physical3.py -- corrected. The bug in v2 was that settle times (160-200 ms)
were SHORTER than the measured round-trip latency (~175 ms), so every reading
carried the previous frame. Here every capture flushes the pipeline for a
wall-clock interval well beyond the latency before a single frame is kept."""
import sys, time, json, datetime
import cv2, numpy as np
from pathlib import Path
import calibration as calib

OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
SIZE, RECT, WAIT = 800, 256, 0.55
X, Y = 2560-SIZE-20, 1440-SIZE-80
win = "OPTIC-LOOP"; m = SIZE//10
cv2.namedWindow(win, cv2.WINDOW_NORMAL); cv2.resizeWindow(win, SIZE, SIZE)
cv2.moveWindow(win, X, Y); cv2.setWindowProperty(win, cv2.WND_PROP_TOPMOST, 1)

def panel(inner):
    f = np.zeros((SIZE, SIZE, 3), np.uint8)
    big = cv2.resize(np.asarray(inner, np.uint8), (SIZE-2*m, SIZE-2*m), interpolation=cv2.INTER_NEAREST)
    f[m:-m, m:-m] = big[..., None]; return f

cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
cap.set(cv2.CAP_PROP_FRAME_WIDTH,1280); cap.set(cv2.CAP_PROP_FRAME_HEIGHT,720)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
cv2.imshow(win, panel(np.full((8,8),200))); cv2.waitKey(30); time.sleep(1.2)
cap.set(cv2.CAP_PROP_AUTOFOCUS,1); time.sleep(1.8)
for _ in range(25): cap.read()
cap.set(cv2.CAP_PROP_AUTOFOCUS,0); cap.set(cv2.CAP_PROP_AUTO_WB,0)
cap.set(cv2.CAP_PROP_AUTO_EXPOSURE,0.25); cap.set(cv2.CAP_PROP_EXPOSURE,-4)
time.sleep(1.0)
for _ in range(10): cap.read()

def display_then_read(inner, n=5, wait=WAIT):
    """show, then BURN wall-clock longer than the round trip, then keep n frames"""
    cv2.imshow(win, panel(inner)); cv2.waitKey(1)
    t0 = time.perf_counter()
    while time.perf_counter()-t0 < wait:
        cap.read(); cv2.waitKey(5)
    fr=[]
    for _ in range(n):
        ok,f = cap.read()
        if not ok: raise SystemExit("camera read failed")
        fr.append(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(np.float32)); cv2.waitKey(5)
    return fr

# geometry
f = display_then_read(np.full((8,8),255), 4)[-1]
quad = calib.find_display_quad(f.astype(np.uint8))
if quad is None: print("CALIB_FAIL"); sys.exit(4)
M = calib.compute_rectify_matrix(quad, RECT)
rectify = lambda fr: np.mean([calib.rectify(x.astype(np.uint8),M,RECT).astype(np.float32) for x in fr],axis=0)

# flat field
BLACK = rectify(display_then_read(np.zeros((8,8)), 8, 0.8))
WHITE = rectify(display_then_read(np.full((8,8),255), 8, 0.8))
GAIN  = np.clip(WHITE-BLACK, 1.0, None)
print(f"flat field: black={BLACK.mean():.1f} white={WHITE.mean():.1f} gain {GAIN.min():.0f}..{GAIN.max():.0f} (mean {GAIN.mean():.0f})")
if GAIN.mean() < 8: print("!! flat field still collapsed -- results below are not trustworthy")
norm = lambda img: np.clip((img-BLACK)/GAIN, -0.3, 1.4)
core = (slice(30,RECT-30), slice(30,RECT-30))
R = {"utc": datetime.datetime.now().isoformat(timespec="seconds"), "wait_s": WAIT,
     "flat_field": {"black":float(BLACK.mean()),"white":float(WHITE.mean()),"gain_mean":float(GAIN.mean())}}

# A. transfer curve
curve=[]
for L in list(range(0,256,16))+[255]:
    fr = display_then_read(np.full((8,8),L), 6)
    reps=[norm(calib.rectify(x.astype(np.uint8),M,RECT).astype(np.float32))[core].mean() for x in fr]
    curve.append({"level":L,"resp":float(np.mean(reps)),"std":float(np.std(reps))})
    print(f"  L={L:3d} -> {np.mean(reps):+.4f} +-{np.std(reps):.5f}")
R["transfer_curve"]=curve
resp=np.array([c["resp"] for c in curve]); noise=float(np.mean([c["std"] for c in curve]))
R["swing"]=float(resp[-1]-resp[0]); R["noise"]=noise
R["effective_bits"]=float(np.log2(abs(R["swing"])/max(noise,1e-9)))
R["monotonic"]=bool(np.all(np.diff(resp)>-0.01))
xx=np.array([c["level"] for c in curve],float)/255.; ok=(xx>0.02)&(resp>0.02)
R["gamma"]=float(np.polyfit(np.log(xx[ok]),np.log(resp[ok]),1)[0]) if ok.sum()>3 else None

# B. latency (unchanged method -- this one was already honest)
lats=[]
for i in range(8):
    a,b=(0,255) if i%2==0 else (255,0)
    base=norm(rectify(display_then_read(np.full((8,8),a),2)))[core].mean()
    t0=time.perf_counter(); cv2.imshow(win,panel(np.full((8,8),b))); cv2.waitKey(1)
    for _ in range(50):
        ok,fr=cap.read(); cv2.waitKey(3)
        v=norm(calib.rectify(cv2.cvtColor(fr,cv2.COLOR_BGR2GRAY),M,RECT).astype(np.float32))[core].mean()
        if abs(v-base)>0.3: lats.append((time.perf_counter()-t0)*1000); break
R["latency_ms"]={"n":len(lats),"median":float(np.median(lats)),"min":float(np.min(lats))}

# C. vector channel -- 64 numbers written with light, read back
G=8; rc=RECT//G; rng=np.random.default_rng(7); sent=[]; got=[]
for t in range(10):
    vals=rng.integers(0,256,size=(G,G))
    r=norm(rectify(display_then_read(vals,4)))
    meas=np.array([[r[i*rc+rc//3:(i+1)*rc-rc//3, j*rc+rc//3:(j+1)*rc-rc//3].mean() for j in range(G)] for i in range(G)])
    sent.append(vals.ravel().astype(float)); got.append(meas.ravel())
    if t==0:
        cv2.imwrite(str(OUT/"v3_sent.png"), cv2.resize(vals.astype(np.uint8),(256,256),interpolation=cv2.INTER_NEAREST))
        cv2.imwrite(str(OUT/"v3_got.png"), np.clip(r*255,0,255).astype(np.uint8))
s=np.concatenate(sent); q=np.concatenate(got)
rr=float(np.corrcoef(s,q)[0,1]); a_,b_=np.polyfit(s,q,1); res=q-(a_*s+b_)
rms=float(np.sqrt(np.mean(res**2)))
R["vector_channel"]={"cells":64,"trials":len(sent),"r2":rr*rr,"rms_err":rms,
                     "bits_per_cell":float(np.log2(np.ptp(q)/max(rms,1e-9)))}

# D. optical sum -- the sensor does the addition
d=[]
for t in range(8):
    vals=rng.integers(0,256,size=(G,G))
    d.append((float(vals.mean()), float(norm(rectify(display_then_read(vals,4)))[core].mean())))
d=np.array(d); rs=float(np.corrcoef(d[:,0],d[:,1])[0,1])
R["optical_sum"]={"n":len(d),"r2":rs*rs,
  "residual_pct":float(100*np.std(d[:,1]-np.polyval(np.polyfit(d[:,0],d[:,1],1),d[:,0]))/np.ptp(d[:,1]))}

# E. close the loop through real air
state=(rng.random((16,16))>0.5).astype(np.float32); diffs=[]
for it in range(30):
    seen=cv2.resize(norm(rectify(display_then_read((state*255).astype(np.uint8),2,0.35))),(16,16),interpolation=cv2.INTER_AREA)
    seen=cv2.GaussianBlur(seen,(3,3),0.8)
    new=(1/(1+np.exp(-10*(seen*1.15-0.5)))).astype(np.float32)
    diffs.append(float(np.abs(new-state).mean())); state=new
R["closed_loop"]={"iters":30,"first":diffs[0],"last":diffs[-1],"converged":bool(diffs[-1]<0.02),
                  "tail":[round(x,4) for x in diffs[-6:]]}
cv2.imwrite(str(OUT/"v3_attractor.png"), cv2.resize((state*255).astype(np.uint8),(256,256),interpolation=cv2.INTER_NEAREST))

cap.release(); cv2.destroyAllWindows()
(OUT/"PHYSICAL-OPTIC-v3.json").write_text(json.dumps(R,indent=2),encoding="utf-8")
print("\n===== PHYSICAL, CORRECTED (real photons) =====")
print(f"transfer     gamma={R['gamma']:.2f}  monotonic={R['monotonic']}  swing={R['swing']:.3f}  noise={noise:.5f}")
print(f"             -> {R['effective_bits']:.1f} effective bits per region")
print(f"latency      median {R['latency_ms']['median']:.0f} ms  min {R['latency_ms']['min']:.0f} ms  -> {1000/R['latency_ms']['median']:.1f} Hz")
print(f"vector 8x8   r2={R['vector_channel']['r2']:.4f}  {R['vector_channel']['bits_per_cell']:.1f} bits/cell")
print(f"optical SUM  r2={R['optical_sum']['r2']:.4f}  residual {R['optical_sum']['residual_pct']:.1f}%")
print(f"closed loop  first={diffs[0]:.4f} last={diffs[-1]:.4f} converged={R['closed_loop']['converged']}")
