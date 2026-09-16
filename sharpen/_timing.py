import os, sys, time
for v in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS"):
    os.environ[v] = "4"
sys.path[:0] = [r"D:\CLAUDE\eran-brain\holobrain\tzelem", r"D:\CLAUDE\oneroom", r"D:\CLAUDE\sharpen"]
sys.stdout.reconfigure(encoding="utf-8")
import psutil; psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
import numpy as np, room, canvas
from anatomy import Strokes
t0=time.time(); import paint; print("import", round(time.time()-t0,1))
t0=time.time(); s = paint.plant(verbose=False); print("plant", round(time.time()-t0,1), "s ->", len(s["point"]), "strokes")
np.savez_compressed(r"D:\CLAUDE\sharpen\_plant_v0165.npz", **{k:v for k,v in s.items() if k!="cameras"})
for n in (30_000, 100_000, 340_000):
    idx = np.linspace(0, len(s["point"])-1, min(n,len(s["point"]))).astype(int)
    st = Strokes(point=s["point"][idx], normal=s["normal"][idx], rgb=s["dark"][idx], radius=s["radius"][idx])
    cam = room.rail_camera(0.30, 1600, 900)
    t0=time.time(); img = canvas.render(None, cam, st, style="painterly", seed=17, background=room.STATES["dark"]["sky"])
    print(f"render {len(idx):>7,} strokes 1600x900: {time.time()-t0:6.1f}s")
