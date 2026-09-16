import os, sys, numpy as np, trimesh
from shapely.geometry import Polygon
import fast_simplification as fs
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

QUICK = '--quick' in sys.argv
FPS = 18
OUT = '/c/Users/iddo1/AppData/Local/Temp/claude/D--CLAUDE/b9e6ece8-3c5f-4239-92b0-867cda33eac1/scratchpad/frames'
os.makedirs(OUT, exist_ok=True)
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
mold=load('silicone-fold-mold.stl'); moldhalf=trimesh.load('silicone-fold-mold.stl').slice_plane(plane_origin=[0,2.5,2.5],plane_normal=[-1,0,0],cap=True); moldhalf.apply_translation(-moldhalf.bounding_box.centroid)
collar=load('buzz-collar.stl'); plenum=load('plenum-cap.stl'); mouth=load('mouth-ah.stl'); tee=load('bleed-tee.stl'); tract=load('tract-ah.stl',1500)

def shade(ax, mesh, color, alpha=1.0, wire=False):
    if mesh is None: return
    n=mesh.face_normals; L=np.array([0.3,0.55,0.9]); L/=np.linalg.norm(L)
    inten=0.4+0.6*np.clip(n@L,0,1); cols=np.clip(np.array(color)[None,:]*inten[:,None],0,1)
    pc=Poly3DCollection(mesh.triangles, facecolors=cols, edgecolor=('#8fb0ff' if wire else 'none'), lw=(0.3 if wire else 0), alpha=alpha)
    ax.add_collection3d(pc)

def frame(idx, meshes, azim, elev, title, sub, lim=60, extra=None):
    fig=plt.figure(figsize=(12.8,7.2), dpi=100, facecolor=BG)
    ax=fig.add_subplot(111, projection='3d', facecolor=BG)
    for m,c,a,w in meshes: shade(ax,m,c,a,w)
    ax.set_xlim(-lim,lim); ax.set_ylim(-lim,lim); ax.set_zlim(-lim,lim)
    ax.set_box_aspect((1,1,1)); ax.view_init(elev=elev, azim=azim); ax.set_axis_off()
    fig.text(0.5,0.93,title,ha='center',fontsize=26,weight='bold',color=INK)
    fig.text(0.5,0.87,sub,ha='center',fontsize=15,color='#9fb3d0')
    fig.text(0.04,0.05,'ER"N voice box  -  real printed parts',fontsize=11,color='#5f7599')
    fig.text(0.96,0.05,'ALMA',ha='right',fontsize=13,weight='bold',color=ACC)
    if extra: extra(fig)
    fig.savefig(f'{OUT}/f{idx:04d}.png', facecolor=BG); plt.close(fig)

idx=0
def hold(meshes,azim,elev,title,sub,secs,lim=60,spin=0.0,extra=None):
    global idx
    N=max(1,int(secs*FPS));
    if QUICK: N=max(1,N//6)
    for k in range(N):
        frame(idx,meshes,azim+spin*k,elev,title,sub,lim,extra); idx+=1

# tiny palettes
G=[0.45,0.8,0.45]; R=[0.95,0.45,0.45]; GR=[0.6,0.66,0.75]; B=[0.5,0.7,1.0]; Y=[1.0,0.8,0.35]

# S1 title
hold([],45,20,'ER"N  -  building a VOICE','from a printed mold to a talking throat  (slow, step by step)',2.2,60)
# S2 mold
hold([(mold,G,1,False)],45,18,'1) PRINT THE MOLD','a little block with a fold-shaped trough inside',2.5,22,spin=2.0)
# S3 pour: mold cutaway + rising red
def make_fill(h):
    if h<=0.1: return None
    f=trimesh.creation.box(extents=[15,8,h]); f.apply_translation([0,0,-6.5+h/2]); return f
for k in range(int((2.5 if not QUICK else 0.5)*FPS)):
    t=k/((2.5)*FPS); fh=13*min(1,t*1.1)
    hold_meshes=[(moldhalf,G,1,False)]
    fillm=make_fill(fh)
    if fillm is not None: hold_meshes.append((fillm,R,0.9,False))
    frame(idx,hold_meshes,60,16,'2) POUR SILICONE','soft Shore-10A fills the fold trough',22); idx+=1
    if QUICK: break
# S4 peel two folds
f2=fold.copy(); f2.apply_translation([14,0,0]); f1=fold.copy(); f1.apply_translation([-14,0,0])
hold([(f1,R,1,False),(f2,R,1,False)],40,16,'3) PEEL THE FOLDS','cast TWICE  ->  a matched pair of vocal folds',2.5,26,spin=2.0)
# S5 assemble voice box: plenum bottom, collar, tract, mouth top
plen=plenum.copy(); plen.apply_translation([0,0,-40])
col=collar.copy(); col.apply_translation([0,0,-8])
trc=tract.copy(); trc.apply_translation([0,0,60])
mth=mouth.copy(); mth.apply_translation([0,0,120])
teec=tee.copy(); teec.apply_translation([28,0,-40])
hold([(plen,GR,1,False),(col,GR,1,False),(teec,Y,1,False)],35,14,'4) THE VOICE BOX','folds sit in the buzz-collar; plenum + air line below',3.0,90,spin=1.6)
hold([(plen,GR,1,False),(col,GR,1,False),(teec,Y,1,False),(trc,B,1,False),(mth,B,1,False)],35,12,'5) TRACT + MOUTH','the tube + horn shape the buzz into vowels',3.0,110,spin=1.6)
# S6 full-head concept (honest: not built)
def label_next(fig):
    fig.text(0.5,0.16,'NEXT (not built yet): teeth . tongue . lips . cheeks . skull',ha='center',fontsize=15,color=ACC,weight='bold')
skull=trimesh.creation.icosphere(subdivisions=2, radius=55); skull.apply_translation([0,0,60])
hold([(plen,GR,1,False),(col,GR,1,False),(trc,B,1,False),(mth,B,1,False),(skull,[0.4,0.5,0.7],0.12,True)],30,10,'6) THE TALKING HEAD','real voice box inside  -  the rest is the plan',3.0,120,spin=1.4,extra=label_next)
# outro
hold([(mth,B,1,False)],40,12,'air in -> folds buzz -> mouth shapes','"Aaaah."   real parts, printed on the K2 Plus',2.2,30,spin=2.0)
print('FRAMES', idx)
