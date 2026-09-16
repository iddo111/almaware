"""EINAYIM -> TZELEM: let the painter look at what the eyes captured.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

The captured mesh goes onto TZELEM's MeshStage and is painted with TZELEM's own
strokes (anatomy.scatter + canvas.render, gate-2 code, untouched). Nothing here
belongs to EINAYIM except the choice of subject: a shape that came from
PHOTOGRAPHS, not from a modeller. First time the painter looks at the world.
"""
import os, sys
import numpy as np
_H = os.path.dirname(os.path.abspath(__file__))
for p in (os.path.join(os.path.dirname(_H), "tzelem"), _H):
    if p not in sys.path: sys.path.insert(0, p)
from meshstage import MeshStage, frame
import anatomy, canvas
from truthviews import read_stl
from PIL import Image

# PC courtesy (2026-09-03 scar: renders starved the KESHEV mic): run below normal priority.
try:
    import psutil as _ps
    _ps.Process().nice(_ps.BELOW_NORMAL_PRIORITY_CLASS)
except Exception:
    pass


stl, out, n, W, H = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])
tris = read_stl(stl)
st = MeshStage(tris, albedo=(0.78, 0.66, 0.52))
cam = frame(tris, width=W, height=H, step_deg=18.0)
strokes = anatomy.scatter(st, cam, n=n, seed=11, size=0.028)
img = canvas.render(st, cam, strokes)
Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).save(out)
truth = (np.clip(st.shade(st.gbuffer(cam)), 0, 1) * 255).astype(np.uint8)
Image.fromarray(truth).save(out.replace(".png", "-flat.png"))
print(f"{len(tris)} tris, {n} strokes -> {out}")
