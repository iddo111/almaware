import numpy as np, trimesh
from shapely.geometry import Polygon
import fast_simplification as fs
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

def load(fn, target=4000):
    m = trimesh.load(fn)
    if len(m.faces) > target:
        v,f = fs.simplify(m.vertices, m.faces, target_reduction=1-target/len(m.faces))
        m = trimesh.Trimesh(vertices=v, faces=f, process=False)
    return m

M5=[(6.08,0),(4.89,1),(3.70,2),(2.50,3),(1.31,4),(0.12,5),(0,6.4),(0.289,7.098),(0.987,7.387),(9,8.4),(9,0)]
fold = trimesh.creation.extrude_polygon(Polygon(M5), height=17.0)
fold.apply_transform(np.array([[0,0,1,0],[0,1,0,0],[1,0,0,0],[0,0,0,1]],float)); fold.apply_translation([-8.5,0,0]); fold.fix_normals()
mold  = load('silicone-fold-mold.stl'); moldhalf = trimesh.load('silicone-fold-mold.stl').slice_plane(plane_origin=[0,2.5,2.5],plane_normal=[-1,0,0],cap=True)
collar= load('buzz-collar.stl'); plenum= load('plenum-cap.stl'); mouth = load('mouth-ah.stl'); tee = load('bleed-tee.stl')

def shade(ax, mesh, color, elev=18, azim=-65, lw=0.0):
    n=mesh.face_normals; L=np.array([0.3,0.5,0.85]); L/=np.linalg.norm(L)
    inten=0.42+0.58*np.clip(n@L,0,1); cols=np.clip(np.array(color)[None,:]*inten[:,None],0,1)
    ax.add_collection3d(Poly3DCollection(mesh.triangles, facecolors=cols, edgecolor=('k' if lw else 'none'), lw=lw))
    b=mesh.bounds; ax.set_xlim(b[0,0],b[1,0]); ax.set_ylim(b[0,1],b[1,1]); ax.set_zlim(b[0,2],b[1,2])
    try: ax.set_box_aspect(mesh.extents)
    except: pass
    ax.view_init(elev=elev, azim=azim); ax.set_axis_off()

GREEN=[0.45,0.78,0.42]; RED=[0.93,0.42,0.42]; GREY=[0.62,0.66,0.72]; BLUE=[0.45,0.62,0.9]
steps=[
 ("1. PRINT THE MOLD", mold, GREEN, "Creality K2 Plus prints the little\nmold block (PLA). ~8 min, 3 g."),
 ("2. POUR SILICONE", moldhalf, GREEN, "Fill the fold-shaped trough with\nsoft Shore-10A silicone. Degas."),
 ("3. PEEL THE FOLD", fold, RED, "Cured silicone pops out = one soft\nvocal fold. Cast TWO for a pair."),
 ("4. LOAD THE FOLDS", collar, GREY, "The pair snaps into the buzz-collar\nfacing each other, a slit between."),
 ("5. CAP + AIR LINE", plenum, GREY, "Plenum cap + bleed-tee feed\npressurised air up to the folds."),
 ("6. ADD A MOUTH -> VOICE", mouth, BLUE, "Air makes the folds flap (buzz);\nthe mouth shapes it: 'Aaaah'."),
]
fig=plt.figure(figsize=(16,9), facecolor='#fbfbf7')
fig.suptitle("ALMA LARYNX  -  from 3D-printed MOLD to a talking THROAT", fontsize=20, weight='bold', color='#1c3c1c', y=0.975)
for i,(title,mesh,color,cap) in enumerate(steps):
    ax=fig.add_subplot(2,3,i+1, projection='3d', facecolor='#fbfbf7')
    shade(ax, mesh, color, lw=(0.15 if len(mesh.faces)<600 else 0.0))
    ax.set_title(title, fontsize=14, weight='bold', color='#233', pad=2)
    ax.text2D(0.5,-0.02, cap, transform=ax.transAxes, ha='center', va='top', fontsize=10.5, color='#333')
    ax.text2D(0.02,0.96, str(i+1), transform=ax.transAxes, fontsize=22, weight='bold', color='#fff',
              bbox=dict(boxstyle='circle,pad=0.28', fc='#e0662a', ec='none'))
# flow arrows
for (x0,x1,y) in [(0.345,0.375,0.60),(0.675,0.705,0.60),(0.345,0.375,0.135),(0.675,0.705,0.135)]:
    fig.add_artist(plt.matplotlib.patches.FancyArrowPatch((x0,y),(x1,y), transform=fig.transFigure, arrowstyle='-|>', mutation_scale=26, color='#e0662a', lw=3))
fig.text(0.5,0.5,'', ha='center')
fig.text(0.5,0.02,"Pour twice -> a matched pair of folds -> air in the bottom -> they buzz -> the mouth turns buzz into vowels.  This is ER\"N's voice box.",
         ha='center', fontsize=11.5, style='italic', color='#444')
plt.tight_layout(rect=[0,0.04,1,0.95])
plt.savefig('larynx_comic.png', dpi=110, facecolor=fig.get_facecolor())
plt.savefig('larynx_comic.pdf', facecolor=fig.get_facecolor())
print('saved larynx_comic.png + .pdf')
