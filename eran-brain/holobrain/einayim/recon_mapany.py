"""EINAYIM — run facebook/map-anything-apache and write recon.py's exact schema.

Apache-2.0 model + Apache-2.0 code. Replaces VGGT-1B (cc-by-nc-4.0).
Runs on eran2 (GB10, aarch64). Emits an npz that score.py reads unmodified.
"""
import argparse, glob, json, os, time
import numpy as np
import torch

os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

ap = argparse.ArgumentParser()
ap.add_argument("image_dir")
ap.add_argument("-o", "--out", required=True)
ap.add_argument("--views", default="0,1")
ap.add_argument("--model", default="facebook/map-anything-apache")
ap.add_argument("--ply", default=None)
a = ap.parse_args()

from mapanything.models import MapAnything
from mapanything.utils.image import load_images

dev = "cuda"
torch.cuda.reset_peak_memory_stats()
t0 = time.time()
model = MapAnything.from_pretrained(a.model).to(dev).eval()
t_load = time.time() - t0
vram_load = torch.cuda.max_memory_allocated() / 2**30

paths = sorted(glob.glob(os.path.join(a.image_dir, "*.png")))
print("images:", [os.path.basename(p) for p in paths])
views = load_images(a.image_dir)
print("n views:", len(views), "img shape:", tuple(views[0]["img"].shape))

torch.cuda.synchronize()
torch.cuda.reset_peak_memory_stats()
t0 = time.time()
with torch.no_grad():
    outputs = model.infer(views, memory_efficient_inference=True, minibatch_size=1,
                          use_amp=True, amp_dtype="bf16", apply_mask=True, mask_edges=True)
torch.cuda.synchronize()
t_infer = time.time() - t0
vram_peak = torch.cuda.max_memory_allocated() / 2**30

print("pred keys:", sorted(outputs[0].keys()))

D, C, E, K, IMG, MSK, PW = [], [], [], [], [], [], []
for pred in outputs:
    d = pred["depth_z"][0].squeeze(-1).float().cpu().numpy()          # (H,W)
    k = pred["intrinsics"][0].float().cpu().numpy()                   # (3,3)
    p = pred["camera_poses"][0].float().cpu().numpy()                 # (4,4) cam->world
    e = np.linalg.inv(p)[:3, :4]                                      # world->cam
    m = pred["mask"][0].squeeze(-1).cpu().numpy().astype(np.float32)
    conf = pred.get("conf", None)
    c = conf[0].squeeze(-1).float().cpu().numpy() if conf is not None else m
    img = pred["img_no_norm"][0].float().cpu().numpy()
    H, W = d.shape
    u, v = np.meshgrid(np.arange(W), np.arange(H))
    x = (u - k[0, 2]) / k[0, 0] * d
    y = (v - k[1, 2]) / k[1, 1] * d
    Xc = np.stack([x, y, d], -1)
    pw = Xc @ p[:3, :3].T + p[:3, 3]
    D.append(d); C.append(c); E.append(e); K.append(k); IMG.append(img); MSK.append(m); PW.append(pw)

D = np.stack(D); C = np.stack(C); E = np.stack(E); K = np.stack(K)
IMG = np.stack(IMG); MSK = np.stack(MSK); PW = np.stack(PW)
idx = np.array([int(x) for x in a.views.split(",")])

meta = {"t_load_s": t_load, "t_infer_s": t_infer, "vram_load_gib": vram_load,
        "vram_peak_gib": vram_peak, "model": a.model,
        "files": [os.path.basename(p) for p in paths],
        "transform": [{"src_w": 640, "src_h": 480, "out_w": int(D.shape[2]),
                       "out_h": int(D.shape[1])}]}
np.savez_compressed(a.out, depth=D, depth_conf=C, extrinsic=E, intrinsic=K,
                    world_points=PW, world_points_conf=C, images=IMG, valid_mask=MSK,
                    view_index=idx, meta=np.array(str(meta), dtype=object))

if a.ply:
    sel = MSK.reshape(-1) > 0.5
    pts = PW.reshape(-1, 3)[sel]
    col = (IMG.reshape(-1, 3)[sel] * 255).clip(0, 255).astype(np.uint8)
    with open(a.ply, "w") as f:
        f.write("ply\nformat ascii 1.0\nelement vertex %d\n" % len(pts))
        f.write("property float x\nproperty float y\nproperty float z\n")
        f.write("property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n")
        for P, Q in zip(pts, col):
            f.write("%.5f %.5f %.5f %d %d %d\n" % (P[0], P[1], P[2], Q[0], Q[1], Q[2]))
    print("ply points:", len(pts), "->", a.ply)

print(json.dumps({"t_load_s": round(t_load, 2), "t_infer_s": round(t_infer, 3),
                  "vram_peak_gib": round(vram_peak, 3), "depth_hw": list(D.shape),
                  "valid_px": int(MSK.sum()),
                  "depth_median_units": float(np.median(D[MSK > 0.5]))}, indent=1))
