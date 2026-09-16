"""Rebuild silicone-fold-mold as a CLEAN watertight boolean mesh (manifold3d).
Keeps the published M5 medial profile from make_silicone_fold_mold.py, but
builds real solids and subtracts them, so the fold cavity is guaranteed present
and the mesh is watertight/printable. The old marching-cubes STL had lost the
cavity (96.5% solid, non-watertight)."""
import numpy as np, trimesh
from shapely.geometry import Polygon

# M5 medial profile (a = medial-lateral, b = inferior-superior), mm
M5 = [(6.08,0.00),(4.89,1.00),(3.70,2.00),(2.50,3.00),(1.31,4.00),(0.12,5.00),
      (0.00,6.40),(0.289,7.098),(0.987,7.387),(9.00,8.40),(9.00,0.00)]
FOLD_LEN = 17.0

# 1) mould block: X:-13..13 (26), Y:-6.5..11.5 (18), Z:-4..9 (13)
block = trimesh.creation.box(extents=[26,18,13])
block.apply_translation([0, 2.5, 2.5])

# 2) fold prism: extrude M5 (in a,b) along +Z by 17, then remap (x,y,z)->(z,y,x)
poly = Polygon(M5)
fold = trimesh.creation.extrude_polygon(poly, height=FOLD_LEN)   # cross-sec in XY=(a,b), length +Z
T = np.array([[0,0,1,0],[0,1,0,0],[1,0,0,0],[0,0,0,1]], float)   # (x,y,z)->(z,y,x): a->Z, b->Y, len->X
fold.apply_transform(T)
fold.apply_translation([-FOLD_LEN/2.0, 0, 0])                    # X:-8.5..8.5
fold.fix_normals()

# 3) peel notch box: center (12.5,2.5,4.0), extents (4,6,12)
notch = trimesh.creation.box(extents=[4,6,12]); notch.apply_translation([12.5,2.5,4.0])

# 4) finger scoop cylinder along X: center (0,12.0,-2.0), r=2, len=12
scoop = trimesh.creation.cylinder(radius=2.0, height=12.0, sections=48)
Rx = trimesh.transformations.rotation_matrix(np.pi/2, [0,1,0])   # z-axis -> x-axis
scoop.apply_transform(Rx); scoop.apply_translation([0,12.0,-2.0])

mould = block.difference(fold).difference(notch).difference(scoop)

print('watertight:', mould.is_watertight)
print('bounds min', np.round(mould.bounds[0],2), 'max', np.round(mould.bounds[1],2))
ext = mould.extents; print('size mm: %.2f x %.2f x %.2f' % tuple(ext))
print('mould vol mm3: %.1f' % mould.volume)
print('block vol mm3: %.1f' % block.volume)
print('total cavity mm3: %.1f (fold+notch+scoop)' % (block.volume - mould.volume))
# how open is the top? area of holes on the top face plane z=9
sec = mould.section(plane_origin=[0,0,8.5], plane_normal=[0,0,1])
if sec is not None:
    p2,_ = sec.to_2D(); print('cross-section near top: %d loops' % len(p2.entities))
mould.export('silicone-fold-mold.stl')
print('EXPORTED silicone-fold-mold.stl')
