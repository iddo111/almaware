import os, sys, numpy as np, trimesh
from shapely.geometry import Polygon
import fast_simplification as fs
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

QUICK = '--quick' in sys.argv
FPS = 15
OUT = r"C:/Users/<user>/AppData/Local/Temp/claude/D--CLAUDE/b9e6ece8-3c5f-4239-92b0-867cda33eac1/scratchpad/frames"
os.makedirs(OUT, exist_ok=True)
for old in os.listdir(OUT):
    if old.endswith('.png'):
        try: os.remove(os.path.join(OUT, old))
        except Exception: pass
BG='#0b1220'; INK='#eaf2ff'; ACC='#ff8a3d'

def load(fn, target=2600):
    m = trimesh.load(fn)
    if len(m.faces) > target:
        v,f = fs.simplify(m.vertices, m.faces, target_reduction=1-target/len(m.faces))
        m = trimesh.Trimesh(vertices=v, faces=f, process=False)
    m.apply_translation(-m.bounding_box.centroid)
    return m

M5=[(6.08,0),(4.89,1),(3.70,2),(2.50,3),(1.31,4),(0.12,5),(0,6.4),(0.289,7.098),(0.987,7.387),(9,8.4),(9,0)]
fold = trimesh.creation.extrude_polygon(Polygon(M5), height=17.0)
fold.apply_transform(np.array([[0,0,1,0],[0,1,0,0],[1,0,0,0],[0,0,0,1]],float)); fold.apply_translation([-8.5,0,0]); fold.fix_normals(); fold.apply_translation(-fold.bounding_box.centroid)
mold = load('silicone-fold-mold.stl')
moldhalf = trimesh.load('silicone-fold-mold.stl').slice_plane(plane_origin=[0,2.5,2.5],plane_normal=[-1,0,0],cap=True); moldhalf.apply_translation(-moldhalf.bounding_box.centroid)
collar=load('buzz-collar.stl'); plenum=load('plenum-cap.stl'); mouth=load('mouth-ah.stl'); tract=load('tract-ah.stl',1500)

def shade(ax, mesh, color, alpha=1.0):
    n=mesh.face_normals; L=np.array([0.3,0.55,0.9]); L=L/np.linalg.norm(L)
    inten=0.4+0.6*np.clip(n@L,0,1); cols=np.clip(np.array(color)[None,:]*inten[:,None],0,1)
    ax.add_collection3d(Poly3DCollection(mesh.triangles, facecolors=cols, edgecolor='none', alpha=alpha))

idx=0
def frame(meshes, azim, elev, title, sub, lim, extra=None):
    global idx
    fig=plt.figure(figsize=(12.8,7.2), dpi=100, facecolor=BG)
    ax=fig.add_subplot(111, projection='3d', facecolor=BG)
    for m,c,a in meshes: shade(ax,m,c,a)
    ax.set_xlim(-lim,lim); ax.set_ylim(-lim,lim); ax.set_zlim(-lim,lim)
    ax.set_box_aspect((1,1,1)); ax.view_init(elev=elev, azim=azim); ax.set_axis_off()
    fig.text(0.5,0.93,title,ha='center',fontsize=27,weight='bold',color=INK)
    fig.text(0.5,0.865,sub,ha='center',fontsize=15,color='#9fb3d0')
    fig.text(0.96,0.05,'ALMA · ER"N voice box',ha='right',fontsize=12,weight='bold',color=ACC)
    if extra: extra(fig)
    fig.savefig(os.path.join(OUT,f'f{idx:04d}.png'), facecolor=BG); plt.close(fig); idx+=1

def hold(meshes,azim,elev,title,sub,secs,lim,spin=0.0,extra=None):
    N=max(1,int(secs*FPS))
    if QUICK: N=max(1,N//8)
    for k in range(N): frame(meshes,azim+spin*k,elev,title,sub,lim,extra)

G=[0.45,0.8,0.45]; R=[0.95,0.45,0.45]; GR=[0.62,0.67,0.76]; B=[0.5,0.7,1.0]
hold([],45,20,'ER"N — building a VOICE','from a printed mold to a talking throat',2.0,60)
hold([(mold,G,1)],45,18,'STEP 1 — PRINT THE MOLD','a small block with a fold-shaped trough',2.6,22,spin=2.2)
# pour: rising red inside cutaway
def fillbox(h): 
    b=trimesh.creation.box(extents=[15,8,max(0.2,h)]); b.apply_translation([0,0,-6.5+max(0.2,h)/2]); return b
N=8 if QUICK else int(2.6*FPS)
for k in range(N):
    t=k/max(1,N-1); fh=13*min(1,t*1.05)
    frame([(moldhalf,G,1),(fillbox(fh),R,0.92)],58,16,'STEP 2 — POUR SILICONE','soft Shore-10A fills the fold trough',22)
f1=fold.copy(); f1.apply_translation([-13,0,0]); f2=fold.copy(); f2.apply_translation([13,0,0])
hold([(f1,R,1),(f2,R,1)],40,16,'STEP 3 — PEEL THE FOLDS','cast twice → a matched pair of vocal folds',2.8,26,spin=2.2)
plen=plenum.copy(); plen.apply_translation([0,0,-40]); col=collar.copy(); col.apply_translation([0,0,-8])
hold([(plen,GR,1),(col,GR,1)],35,14,'STEP 4 — THE VOICE BOX','the pair sits in the buzz-collar; air chamber below',3.0,80,spin=1.8)
trc=tract.copy(); trc.apply_translation([0,0,55]); mth=mouth.copy(); mth.apply_translation([0,0,115])
hold([(plen,GR,1),(col,GR,1),(trc,B,1),(mth,B,1)],35,12,'STEP 5 — TRACT + MOUTH','the tube + horn shape the buzz into vowels',3.0,110,spin=1.8)
hold([(mth,B,1)],40,12,'AIR IN → FOLDS BUZZ → MOUTH SHAPES','"Aaaah."  real parts, printed on the K2 Plus',2.4,30,spin=2.2)
print('FRAMES', idx)
