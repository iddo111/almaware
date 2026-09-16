# from-einayim — shapes KAV did not say, KAV was SHOWN

> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

Every mesh in KAV's corpus so far was **generated** — a solid we wrote down. These
came from **pictures**. They are corpus *candidates*, dropped here by the EINAYIM
organ; **no file under `kav/` was modified to make them**, and nothing here is
wired into `learn.py` or `joiner.py` yet. That is a decision for whoever owns KAV.

## How they were made

1. `eran-brain/holobrain/einayim/truthviews.py` rendered 8 views of a scene we own
   (KAV's own `KAV-first-shape.stl` next to a decimated `alma-larynx/silicone-fold-mold.stl`,
   on a textured floor) — RGB at 640×480 plus **exact** depth and camera.
2. `recon.py` on **eran3** ran `facebook/VGGT-1B` on those PNGs. The model was given
   nothing but the pictures: no depth, no poses, no intrinsics.
3. `score.py` fused the model's depths into a TSDF volume and marched cubes
   (`fuse.py` — ours; open3d has no aarch64 wheel for the GB10).
4. `objectmesh.py` cut the floor away with a hand-given box and decimated to ≤2,000 faces.

## What is in each file

| file | views the model got | faces | measured against truth |
|---|---|---|---|
| `einayim-organs-8views.stl` | 8 | 1,996 | depth median abs-rel **0.38 %**, 98.4 % of pixels within 5 % |
| `einayim-organs-2views.stl` | 2 (21° apart) | 1,893 | depth median abs-rel **0.57 %**, 98.5 % within 5 % |
| `einayim-dropfolder-autocrop.stl` | 8, via the drop folder | 1,449 | same views, but isolated AUTOMATICALLY (RANSAC plane removal) instead of by hand — visibly worse, and kept here honestly as the comparison |

## What is wrong with them, plainly

* **Not watertight.** 225–314 boundary edges. Cameras saw one side of the scene;
  the back of every object is simply missing. KAV's `ruler.py` will say so.
* **Non-manifold in places** (280–322 edges): the decimator is vertex clustering
  on a grid, not quadric edge collapse. It welds things that should not weld.
* **Scale is real here only because the truth was ours.** A mesh from real photos
  comes out the right shape and an arbitrary size — see `einayim/EINAYIM-20260903.md`.

If KAV is going to eat these, the first honest question is whether an OPEN surface
belongs in a corpus whose grammar is about solids.
