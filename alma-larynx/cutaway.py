import numpy as np, trimesh
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
m = trimesh.load('silicone-fold-mold.stl')
c = m.bounding_box.centroid
# cut in half across the length; keep the +X half so we see the fold cavity wall
half = m.slice_plane(plane_origin=c, plane_normal=[-1,0,0], cap=True)
fig = plt.figure(figsize=(13,6))
ax = fig.add_subplot(1,2,1, projection='3d')
ax.add_collection3d(Poly3DCollection(half.triangles, facecolor='#7ad17a', edgecolor='#2a7', lw=.2, alpha=1.0))
b=m.bounds
ax.set_xlim(b[0,0],b[1,0]); ax.set_ylim(b[0,1],b[1,1]); ax.set_zlim(b[0,2],b[1,2])
try: ax.set_box_aspect(m.extents)
except: pass
ax.view_init(elev=22, azim=-72); ax.set_title('CUTAWAY: hollow fold cavity + peel notch'); ax.set_xlabel('X'); ax.set_ylabel('Y'); ax.set_zlabel('Z')
# top-down: cavity opening visible as the hole in the top face
ax2 = fig.add_subplot(1,2,2)
sec = m.section(plane_origin=[0,0,8.7], plane_normal=[0,0,1])  # near the top
if sec is not None:
    p2,_ = sec.to_2D()
    for ent in p2.entities:
        pts=p2.vertices[ent.points]; ax2.fill(pts[:,0],pts[:,1], facecolor='none', edgecolor='#1a6', lw=2)
ax2.set_aspect('equal'); ax2.grid(True,alpha=.3); ax2.set_title('top face @ Z=8.7mm: outer wall + open cavity mouth')
plt.suptitle('silicone-fold-mold.stl REBUILT — you pour silicone into the cavity from the top', fontsize=12)
plt.tight_layout(); plt.savefig('mold_cutaway.png', dpi=100); print('saved mold_cutaway.png')
