import numpy as np, trimesh
from shapely.geometry import Polygon
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

M5 = [(6.08,0.00),(4.89,1.00),(3.70,2.00),(2.50,3.00),(1.31,4.00),(0.12,5.00),
      (0.00,6.40),(0.289,7.098),(0.987,7.387),(9.00,8.40),(9.00,0.00)]
FOLD_LEN=17.0
# CAST POSITIVE = the silicone fold you pull out (== the cavity shape)
fold = trimesh.creation.extrude_polygon(Polygon(M5), height=FOLD_LEN)
T = np.array([[0,0,1,0],[0,1,0,0],[1,0,0,0],[0,0,0,1]],float)
fold.apply_transform(T); fold.apply_translation([-FOLD_LEN/2,0,0]); fold.fix_normals()
mold = trimesh.load('silicone-fold-mold.stl')

def shaded(ax, mesh, color, elev, azim, title):
    tris = mesh.triangles
    n = mesh.face_normals
    light = np.array([0.3,0.5,0.8]); light=light/np.linalg.norm(light)
    inten = 0.45 + 0.55*np.clip(n@light,0,1)
    base = np.array(color)
    cols = np.clip(base[None,:]*inten[:,None],0,1)
    pc = Poly3DCollection(tris, facecolors=cols, edgecolor='none')
    ax.add_collection3d(pc)
    b=mesh.bounds
    ax.set_xlim(b[0,0],b[1,0]); ax.set_ylim(b[0,1],b[1,1]); ax.set_zlim(b[0,2],b[1,2])
    try: ax.set_box_aspect(mesh.extents)
    except: pass
    ax.view_init(elev=elev, azim=azim); ax.set_title(title, fontsize=11)
    ax.set_xticks([]); ax.set_yticks([]); ax.set_zticks([])

fig = plt.figure(figsize=(15,5.5))
a1=fig.add_subplot(1,3,1,projection='3d')
shaded(a1, fold, [0.95,0.55,0.55], 18, -65, 'CAST SILICONE FOLD (the product)\n~17mm long, soft Shore-10A')
a2=fig.add_subplot(1,3,2,projection='3d')
half = mold.slice_plane(plane_origin=mold.bounding_box.centroid, plane_normal=[-1,0,0], cap=True)
shaded(a2, half, [0.55,0.8,0.55], 18, -65, 'THE MOLD, cut open (you 3D-print this)\nfold-shaped trough inside')
a3=fig.add_subplot(1,3,3)
xs=[p[0] for p in M5]+[M5[0][0]]; ys=[p[1] for p in M5]+[M5[0][1]]
a3.fill(xs,ys,color='#f0a0a0',ec='#c33',lw=2)
a3.set_aspect('equal'); a3.grid(True,alpha=.3)
a3.set_title('M5 vocal-fold profile (published science)\ncross-section of the fold', fontsize=11)
a3.set_xlabel('medial-lateral (mm)'); a3.set_ylabel('inferior-superior (mm)')
plt.suptitle('POUR silicone into the mold (middle) -> peel out the FOLD (left).  Cast TWO for a pair.', fontsize=12)
plt.tight_layout(); plt.savefig('mold_vs_cast.png', dpi=105); print('saved')
