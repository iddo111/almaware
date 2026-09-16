"""physical4.py -- v3 failed because the quad finder latched onto the wrong
region (part of the window is outside the camera's field of view). Here the
SCREEN DEFINES ITSELF: capture a black field and a white field, and the pixels
whose value actually changed ARE the screen. Everything else is discarded.
Level order is shuffled and every level measured twice, far apart in time, so
any residual auto-exposure drift shows up as a number instead of a fake curve."""
import sys, time, json, datetime
import cv2, numpy as np
from pathlib import Path

OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
SIZE, WAIT = 800, 0.32
X, Y = 2560-SIZE-20, 1440-SIZE-80
win="OPTIC-LOOP"; m=SIZE//10
cv2.namedWindow(win, cv2.WINDOW_NORMAL); cv2.resizeWindow(win,SIZE,SIZE)
cv2.moveWindow(win,X,Y); cv2.setWindowProperty(win, cv2.WND_PROP_TOPMOST,1)
def panel(inner):
    f=np.zeros((SIZE,SIZE,3),np.uint8)
    b=cv2.resize(np.asarray(inner,np.uint8),(SIZE-2*m,SIZE-2*m),interpolation=cv2.INTER_NEAREST)
    f[m:-m,m:-m]=b[...,None]; return f

cap=cv2.VideoCapture(0,cv2.CAP_DSHOW)
cap.set(cv2.CAP_PROP_FRAME_WIDTH,1280); cap.set(cv2.CAP_PROP_FRAME_HEIGHT,720)
cap.set(cv2.CAP_PROP_BUFFERSIZE,1)
cv2.imshow(win,panel(np.full((8,8),200))); cv2.waitKey(30); time.sleep(1.0)
cap.set(cv2.CAP_PROP_AUTOFOCUS,1); time.sleep(1.8)
for _ in range(25): cap.read()
cap.set(cv2.CAP_PROP_AUTOFOCUS,0); cap.set(cv2.CAP_PROP_AUTO_WB,0)
cap.set(cv2.CAP_PROP_AUTO_EXPOSURE,0.25); cap.set(cv2.CAP_PROP_EXPOSURE,-4); time.sleep(1.0)
for _ in range(10): cap.read()

def shot(inner,n=5,wait=WAIT):
    cv2.imshow(win,panel(inner)); cv2.waitKey(1)
    t0=time.perf_counter()
    while time.perf_counter()-t0<wait: cap.read(); cv2.waitKey(4)
    fr=[]
    for _ in range(n):
        ok,f=cap.read()
        if not ok: raise SystemExit("camera read failed")
        fr.append(cv2.cvtColor(f,cv2.COLOR_BGR2GRAY).astype(np.float32)); cv2.waitKey(4)
    return np.mean(fr,axis=0)

# ---- 1. THE SCREEN DEFINES ITSELF ----
B = shot(np.zeros((8,8)),8,0.8)
W = shot(np.full((8,8),255),8,0.8)
D = W-B
R={"utc":datetime.datetime.now().isoformat(timespec="seconds")}
mask = D > max(6.0, 0.30*float(D.max()))
mask = cv2.morphologyEx(mask.astype(np.uint8),cv2.MORPH_OPEN,np.ones((9,9),np.uint8))
n,lab,stats,_ = cv2.connectedComponentsWithStats(mask,8)
if n<2: print("NO_RESPONSIVE_REGION"); sys.exit(5)
k = 1+int(np.argmax(stats[1:,cv2.CC_STAT_AREA])); mask = (lab==k)
ys,xs = np.where(mask)
R["responsive"]={"frac_of_frame":float(mask.mean()),"pixels":int(mask.sum()),
                 "bbox":[int(xs.min()),int(ys.min()),int(xs.max()),int(ys.max())],
                 "delta_max":float(D.max()),"delta_mean_in_mask":float(D[mask].mean())}
print(f"responsive region: {mask.sum()} px ({100*mask.mean():.1f}% of frame), "
      f"bbox x{xs.min()}-{xs.max()} y{ys.min()}-{ys.max()}, mean delta {D[mask].mean():.1f} counts")
touch = (xs.min()<4) or (ys.min()<4) or (xs.max()>D.shape[1]-5) or (ys.max()>D.shape[0]-5)
R["responsive"]["clipped_by_frame_edge"]=bool(touch)
if touch: print("!! the screen region touches the frame edge -- part of the panel is OUT OF VIEW")
cv2.imwrite(str(OUT/"v4_mask.png"), (mask*255).astype(np.uint8))
cv2.imwrite(str(OUT/"v4_delta.png"), np.clip(D,0,255).astype(np.uint8))
GAIN = np.clip(D,1.0,None)
def level_of(img): 
    v=((img-B)/GAIN)[mask]
    return float(v.mean()), float(v.std())

# ---- 2. transfer curve, SHUFFLED, each level twice ----
levels=list(range(0,256,16))+[255]
order=levels*2
rng=np.random.default_rng(3); rng.shuffle(order)
obs={L:[] for L in levels}
for L in order:
    obs[L].append(level_of(shot(np.full((8,8),L),4))[0])
curve=[{"level":L,"resp":float(np.mean(obs[L])),"repeat_spread":float(abs(obs[L][0]-obs[L][1]))} for L in levels]
for c in curve: print(f"  L={c['level']:3d} -> {c['resp']:+.4f}   (repeat spread {c['repeat_spread']:.4f})")
resp=np.array([c["resp"] for c in curve])
drift=float(np.mean([c["repeat_spread"] for c in curve]))
R["transfer_curve"]=curve; R["repeat_drift"]=drift
R["swing"]=float(resp[-1]-resp[0]); R["monotonic"]=bool(np.all(np.diff(resp)>-0.02))
R["effective_bits"]=float(np.log2(abs(R["swing"])/max(drift,1e-9)))
xx=np.array(levels,float)/255.; ok=(xx>0.02)&(resp>0.02)
R["gamma"]=float(np.polyfit(np.log(xx[ok]),np.log(resp[ok]),1)[0]) if ok.sum()>3 else None

# ---- 3. latency ----
lats=[]
for i in range(8):
    a,b=(0,255) if i%2==0 else (255,0)
    base,_=level_of(shot(np.full((8,8),a),2))
    t0=time.perf_counter(); cv2.imshow(win,panel(np.full((8,8),b))); cv2.waitKey(1)
    for _ in range(50):
        ok,f=cap.read(); cv2.waitKey(3)
        v=((cv2.cvtColor(f,cv2.COLOR_BGR2GRAY).astype(np.float32)-B)/GAIN)[mask].mean()
        if abs(v-base)>0.3: lats.append((time.perf_counter()-t0)*1000); break
R["latency_ms"]={"n":len(lats),"median":float(np.median(lats)),"min":float(np.min(lats))}

# ---- 4. VECTOR: 64 numbers written with light, read back through the mask ----
G=8; sent=[];got=[]
x0,y0,x1,y1 = xs.min(),ys.min(),xs.max(),ys.max()
for t in range(10):
    vals=rng.integers(0,256,size=(G,G))
    img=shot(vals,4); resp_img=(img-B)/GAIN
    meas=np.zeros((G,G)); okc=np.zeros((G,G),bool)
    for i in range(G):
        for j in range(G):
            sy=slice(int(y0+(y1-y0)*(i+0.28)/G), int(y0+(y1-y0)*(i+0.72)/G))
            sx=slice(int(x0+(x1-x0)*(j+0.28)/G), int(x0+(x1-x0)*(j+0.72)/G))
            sub=resp_img[sy,sx]; sm=mask[sy,sx]
            if sm.sum()>20: meas[i,j]=sub[sm].mean(); okc[i,j]=True
    sent.append(vals[okc].astype(float)); got.append(meas[okc])
    if t==0: cv2.imwrite(str(OUT/"v4_resp.png"), np.clip(resp_img*255,0,255).astype(np.uint8))
s=np.concatenate(sent); q=np.concatenate(got)
rr=float(np.corrcoef(s,q)[0,1]); a_,b_=np.polyfit(s,q,1); res=q-(a_*s+b_)
rms=float(np.sqrt(np.mean(res**2)))
R["vector_channel"]={"cells_used":int(len(s)/len(sent)),"trials":len(sent),"r2":rr*rr,
                     "rms_err":rms,"bits_per_cell":float(np.log2(np.ptp(q)/max(rms,1e-9)))}

# ---- 5. optical sum ----
d=[]
for t in range(8):
    vals=rng.integers(0,256,size=(G,G))
    d.append((float(vals.mean()), level_of(shot(vals,4))[0]))
d=np.array(d); rs=float(np.corrcoef(d[:,0],d[:,1])[0,1])
R["optical_sum"]={"n":len(d),"r2":rs*rs,
  "residual_pct":float(100*np.std(d[:,1]-np.polyval(np.polyfit(d[:,0],d[:,1],1),d[:,0]))/np.ptp(d[:,1]))}

cap.release(); cv2.destroyAllWindows()
(OUT/"PHYSICAL-OPTIC-v4.json").write_text(json.dumps(R,indent=2),encoding="utf-8")
print("\n===== PHYSICAL v4 =====")
print(f"screen found  {100*mask.mean():.1f}% of frame, clipped_by_edge={R['responsive']['clipped_by_frame_edge']}")
print(f"transfer      gamma={R['gamma']}  monotonic={R['monotonic']}  swing={R['swing']:.3f}")
print(f"drift         repeat spread {drift:.4f}  -> {R['effective_bits']:.1f} effective bits")
print(f"latency       median {R['latency_ms']['median']:.0f} ms -> {1000/R['latency_ms']['median']:.1f} Hz")
print(f"vector 8x8    r2={R['vector_channel']['r2']:.4f}  {R['vector_channel']['bits_per_cell']:.1f} bits/cell  ({R['vector_channel']['cells_used']} cells)")
print(f"optical SUM   r2={R['optical_sum']['r2']:.4f}  residual {R['optical_sum']['residual_pct']:.1f}%")
