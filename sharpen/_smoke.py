import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, time, workshop as W
from sharpness import lapvar_array
from PIL import Image
try:
    import psutil; psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
except Exception: pass
t0 = time.time()
a = W.anchors(0.040, 200_000, verbose=False)
st = a.pop('stage'); print('anchors', len(a['point']), round(time.time()-t0,1), 's', flush=True)
occ = W.occlude_anchors(st, a['point'], a['normal'], ao_rays=8, shadow_samples=2)
for state in ('dark', 'lit'):
    for tag, o in (('plain', None), ('occ', occ)):
        rgb = W.colours(st, a['point'], a['normal'], a['box'], state, o)
        img, s, cov = W.paint(a['point'], a['normal'], rgb, 0.030, 800, 450, state)
        print(f'{state:5} {tag:5} lapvar {lapvar_array(img):7.1f} cov {cov*100:5.1f}% {s:.1f}s', flush=True)
        Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).save(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), f'_smoke-{state}-{tag}.png'))
print('total', round(time.time()-t0, 1), 's')
