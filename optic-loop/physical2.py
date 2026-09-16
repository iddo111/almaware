"""physical2.py -- the real channel, with auto-exposure KILLED and a flat-field
correction that removes the LCD viewing-angle gradient. Real photons only."""
import sys, time, json, datetime
import cv2, numpy as np
from pathlib import Path
import calibration as calib

OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
SIZE, RECT = 800, 256
X, Y = 2560-SIZE-20, 1440-SIZE-80
win = "OPTIC-LOOP"
cv2.namedWindow(win, cv2.WINDOW_NORMAL); cv2.resizeWindow(win, SIZE, SIZE)
cv2.moveWindow(win, X, Y); cv2.setWindowProperty(win, cv2.WND_PROP_TOPMOST, 1)
m = SIZE//10
def panel(inner_u8):
    f = np.zeros((SIZE, SIZE, 3), np.uint8)
    big = cv2.resize(inner_u8, (SIZE-2*m, SIZE-2*m), interpolation=cv2.INTER_NEAREST)
    f[m:-m, m:-m] = big[..., None] if big.ndim == 2 else big
    return f
def show(img, k=3):
    cv2.imshow(win, img)
    for _ in range(k): cv2.waitKey(15)

cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
cap.set(cv2.CAP_PROP_FRAME_WIDTH,1280); cap.set(cv2.CAP_PROP_FRAME_HEIGHT,720)
show(panel(np.full((8,8),200,np.uint8))); time.sleep(1.2)
cap.set(cv2.CAP_PROP_AUTOFOCUS,1); time.sleep(1.6)
for _ in range(20): cap.read()
cap.set(cv2.CAP_PROP_AUTOFOCUS,0); cap.set(cv2.CAP_PROP_AUTO_WB,0)
cap.set(cv2.CAP_PROP_AUTO_EXPOSURE,0.25)          # MANUAL. this is the whole fix.
EXPO = -4
cap.set(cv2.CAP_PROP_EXPOSURE, EXPO); time.sleep(0.8)
for _ in range(8): cap.read()

def grab(n=1):
    out=[]
    for _ in range(n):
        ok,f = cap.read()
        if not ok: raise SystemExit("camera read failed")
        out.append(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(np.float32)); cv2.waitKey(4)
    return out

# ---- geometry ----
show(panel(np.full((8,8),255,np.uint8))); time.sleep(0.7); grab(4)
quad = calib.find_display_quad(grab(3)[-1].astype(np.uint8))
if quad is None: print("CALIB_FAIL"); sys.exit(4)
M = calib.compute_rectify_matrix(quad, RECT)
def rect(n=3):
    return np.mean([calib.rectify(f.astype(np.uint8), M, RECT).astype(np.float32) for f in grab(n)],axis=0)

# ---- FLAT FIELD: per-pixel black and white reference ----
show(panel(np.zeros((8,8),np.uint8)));   time.sleep(0.7); grab(3); BLACK = rect(8)
show(panel(np.full((8,8),255,np.uint8)));time.sleep(0.7); grab(3); WHITE = rect(8)
GAIN = np.clip(WHITE-BLACK, 3.0, None)
def norm(img): return np.clip((img-BLACK)/GAIN, -0.3, 1.4)
cv2.imwrite(str(OUT/"flat_black.png"), BLACK.astype(np.uint8))
cv2.imwrite(str(OUT/"flat_white.png"), WHITE.astype(np.uint8))
R={"utc":datetime.datetime.now().isoformat(timespec="seconds"),"exposure":EXPO,
   "flat_field":{"black_mean":float(BLACK.mean()),"white_mean":float(WHITE.mean()),
                 "gain_mean":float(GAIN.mean()),"gain_min":float(GAIN.min()),"gain_max":float(GAIN.max())}}
core=(slice(30,RECT-30),slice(30,RECT-30))

# ---- transfer curve ----
curve=[]
for L in list(range(0,256,16))+[255]:
    show(panel(np.full((8,8),L,np.uint8))); time.sleep(0.20); grab(2)
    reps=[norm(calib.rectify(f.astype(np.uint8),M,RECT).astype(np.float32))[core].mean() for f in grab(6)]
    curve.append({"level":L,"resp":float(np.mean(reps)),"std":float(np.std(reps))})
    print(f"  L={L:3d} -> {np.mean(reps):+.4f} +-{np.std(reps):.5f}")
R["transfer_curve"]=curve
lo,hi=curve[0]["resp"],curve[-1]["resp"]; noise=float(np.mean([c['std'] for c in curve]))
R["swing"]=hi-lo; R["noise"]=noise; R["effective_bits"]=float(np.log2(abs(hi-lo)/max(noise,1e-9)))
R["monotonic"]=bool(np.all(np.diff([c['resp'] for c in curve])>-0.01))
xx=np.array([c['level'] for c in curve],float)/255.; yy=np.array([c['resp'] for c in curve],float)
ok=(xx>0.02)&(yy>0.02); R["gamma"]=float(np.polyfit(np.log(xx[ok]),np.log(yy[ok]),1)[0])

# ---- latency ----
lats=[]
for i in range(8):
    a,b=(0,255) if i%2==0 else (255,0)
    show(panel(np.full((8,8),a,np.uint8))); time.sleep(0.3); grab(3)
    base=norm(rect(1))[core].mean()
    t0=time.perf_counter(); cv2.imshow(win,panel(np.full((8,8),b,np.uint8))); cv2.waitKey(1)
    for _ in range(40):
        v=norm(calib.rectify(grab(1)[0].astype(np.uint8),M,RECT).astype(np.float32))[core].mean()
        if abs(v-base)>0.3: lats.append((time.perf_counter()-t0)*1000); break
R["latency_ms"]={"n":len(lats),"median":float(np.median(lats)),"min":float(np.min(lats))}

# ---- VECTOR channel: write 64 numbers with light, read them back ----
G=8; rc=RECT//G; rng=np.random.default_rng(1); sent=[];got=[]
for t in range(14):
    vals=rng.integers(0,256,size=(G,G)).astype(np.uint8)
    show(panel(vals)); time.sleep(0.16); grab(2)
    r=norm(rect(4))
    meas=np.array([[r[i*rc+rc//3:(i+1)*rc-rc//3, j*rc+rc//3:(j+1)*rc-rc//3].mean()
                    for j in range(G)] for i in range(G)])
    sent.append(vals.ravel().astype(float)); got.append(meas.ravel())
    if t==0:
        cv2.imwrite(str(OUT/"vec_sent.png"), cv2.resize(vals,(256,256),interpolation=cv2.INTER_NEAREST))
        cv2.imwrite(str(OUT/"vec_got.png"), np.clip(r*255,0,255).astype(np.uint8))
s=np.concatenate(sent); q=np.concatenate(got)
r_=float(np.corrcoef(s,q)[0,1]); a_,b_=np.polyfit(s,q,1); res=q-(a_*s+b_)
R["vector_channel"]={"cells":G*G,"trials":len(sent),"r2":r_*r_,
   "rms_err_frac":float(np.sqrt(np.mean(res**2))),
   "bits_per_cell":float(np.log2(np.ptp(q)/max(np.sqrt(np.mean(res**2)),1e-9)))}

# ---- OPTICAL SUM: let the sensor do the addition ----
d=[]
for t in range(12):
    vals=rng.integers(0,256,size=(G,G)).astype(np.uint8)
    show(panel(vals)); time.sleep(0.16); grab(2)
    d.append((float(vals.mean()), float(norm(rect(4))[core].mean())))
d=np.array(d); rs=float(np.corrcoef(d[:,0],d[:,1])[0,1])
R["optical_sum"]={"n":len(d),"r2":rs*rs,
  "residual_pct":float(100*np.std(d[:,1]-np.polyval(np.polyfit(d[:,0],d[:,1],1),d[:,0]))/np.ptp(d[:,1]))}

# ---- CLOSE THE LOOP: 40 iterations through real air ----
state=(rng.random((16,16))>0.5).astype(np.float32)
diffs=[]
for it in range(40):
    show(panel((state*255).astype(np.uint8))); time.sleep(0.12); grab(2)
    seen=cv2.resize(norm(rect(2)),(16,16),interpolation=cv2.INTER_AREA)
    seen=cv2.GaussianBlur(seen,(3,3),0.8)
    new=np.clip(1/(1+np.exp(-10*(seen*1.15-0.5))),0,1).astype(np.float32)
    diffs.append(float(np.abs(new-state).mean())); state=new
R["closed_loop"]={"iters":40,"diff_first5":diffs[:5],"diff_last5":diffs[-5:],
                  "final_diff":diffs[-1],"converged":bool(diffs[-1]<0.02)}
cv2.imwrite(str(OUT/"loop_attractor.png"), cv2.resize((state*255).astype(np.uint8),(256,256),interpolation=cv2.INTER_NEAREST))

cap.release(); cv2.destroyAllWindows()
(OUT/"PHYSICAL-OPTIC-v2.json").write_text(json.dumps(R,indent=2),encoding="utf-8")
print("\n===== PHYSICAL RESULT (real photons) =====")
print(f"flat field    black={BLACK.mean():.1f} white={WHITE.mean():.1f} gain {GAIN.min():.0f}..{GAIN.max():.0f} counts")
print(f"transfer      gamma={R['gamma']:.2f} monotonic={R['monotonic']} swing={R['swing']:.3f} noise={noise:.5f}")
print(f"              -> {R['effective_bits']:.1f} effective bits per pixel")
print(f"latency       median {R['latency_ms']['median']:.0f} ms   min {R['latency_ms']['min']:.0f} ms")
print(f"vector 8x8    r2={R['vector_channel']['r2']:.4f}  {R['vector_channel']['bits_per_cell']:.1f} bits/cell")
print(f"optical SUM   r2={R['optical_sum']['r2']:.4f}  residual {R['optical_sum']['residual_pct']:.1f}%")
print(f"closed loop   first={diffs[0]:.4f} last={diffs[-1]:.4f} converged={R['closed_loop']['converged']}")
