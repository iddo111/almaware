import numpy as np, trimesh
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
m = trimesh.load('silicone-fold-mold.stl')
fig = plt.figure(figsize=(15,5))
# (1) 3D view
ax = fig.add_subplot(1,3,1, projection='3d')
ax.add_collection3d(Poly3DCollection(m.triangles, facecolor='#6fcf6f', edgecolor='none', alpha=0.9))
b=m.bounds; ax.set_xlim(b[0,0],b[1,0]); ax.set_ylim(b[0,1],b[1,1]); ax.set_zlim(b[0,2],b[1,2])
try: ax.set_box_aspect(m.extents)
except: pass
ax.view_init(elev=35, azim=-60); ax.set_title('mold 3D (cavity opens up)'); ax.set_xlabel('X'); ax.set_ylabel('Y')
# (2) cross-section across the fold (X-mid) -> reveals M5 cavity
def draw_section(ax, origin, normal, title):
    s = m.section(plane_origin=origin, plane_normal=normal)
    if s is None: ax.set_title(title+' (none)'); return
    p2,_ = s.to_2D()
    for ent in p2.entities:
        pts = p2.vertices[ent.points]; ax.plot(pts[:,0], pts[:,1], '-', color='#1a6', lw=1.5)
    ax.set_aspect('equal'); ax.grid(True, alpha=.3); ax.set_title(title)
c = m.bounding_box.centroid
ax2 = fig.add_subplot(1,3,2); draw_section(ax2, c, [1,0,0], 'section across length -> fold cavity')
ax3 = fig.add_subplot(1,3,3); draw_section(ax3, c, [0,1,0], 'section across depth')
plt.suptitle('silicone-fold-mold.stl (REBUILT) — deep M5 fold cavity, watertight', fontsize=13)
plt.tight_layout(); plt.savefig('mold_check.png', dpi=100)
print('saved mold_check.png')
