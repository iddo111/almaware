"""EINAYIM / עֵינַיִם — RUN THE PHOTO MODEL. (eran3, GPU)

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

Feed N ordinary RGB images to a feed-forward multi-view model and write down
everything it claims: per-view depth, per-view camera (K and world->cam [R|t]),
a world point map, and its own confidence. Nothing is scored here — scoring is
score.py, and it is deliberately a separate file so the model never sees the ruler.

VGGT-1B is the first model. NOTE ITS LICENCE: Meta "Research Materials" —
non-commercial research. That is fine for measuring what is possible; if EINAYIM
ships, MapAnything-apache is the licence-clean fallback.

Runs on eran3 only. No inference on the PC (D:\\CLAUDE\\CLAUDE.md).
"""
from __future__ import annotations

import argparse
import glob
import os
import time

import numpy as np
import torch
from PIL import Image

TARGET = 518
PATCH = 14


def load_images(paths):
    """VGGT's own 'crop' preprocessing, minus the torchvision dependency.

    width -> 518, height -> nearest multiple of 14 keeping the aspect, bicubic,
    then centre-crop the height if it came out over 518. Returned alongside the
    exact geometric transform so the ruler can follow the pixels.
    """
    imgs, tf = [], []
    for p in paths:
        im = Image.open(p).convert("RGB")
        w, h = im.size
        nw = TARGET
        nh = int(round(h * (nw / w) / PATCH) * PATCH)
        im = im.resize((nw, nh), Image.Resampling.BICUBIC)
        a = np.asarray(im, dtype=np.float32) / 255.0
        y0 = 0
        if nh > TARGET:
            y0 = (nh - TARGET) // 2
            a = a[y0:y0 + TARGET]
        imgs.append(torch.from_numpy(a).permute(2, 0, 1))
        tf.append({"src_w": w, "src_h": h, "scale": nw / w,
                   "crop_y0": y0, "out_w": a.shape[1], "out_h": a.shape[0]})
    return torch.stack(imgs), tf


def run_vggt(image_paths, device="cuda"):
    from vggt.models.vggt import VGGT
    from vggt.utils.pose_enc import pose_encoding_to_extri_intri

    dtype = torch.bfloat16 if torch.cuda.get_device_capability()[0] >= 8 else torch.float16
    t0 = time.time()
    model = VGGT.from_pretrained("facebook/VGGT-1B").to(device).eval()
    t_load = time.time() - t0

    images, tf = load_images(image_paths)
    images = images.to(device)
    torch.cuda.synchronize()
    t0 = time.time()
    with torch.no_grad():
        with torch.autocast(device_type="cuda", dtype=dtype):
            batch = images[None]
            tok, ps = model.aggregator(batch)
        pose_enc = model.camera_head(tok)[-1]
        extri, intri = pose_encoding_to_extri_intri(pose_enc, batch.shape[-2:])
        depth, depth_conf = model.depth_head(tok, images=batch, patch_start_idx=ps)
        wpts, wpts_conf = model.point_head(tok, images=batch, patch_start_idx=ps)
    torch.cuda.synchronize()
    t_infer = time.time() - t0

    f = lambda x: x[0].float().cpu().numpy()
    return {
        "extrinsic": f(extri),          # (S,3,4) world->cam, OpenCV
        "intrinsic": f(intri),          # (S,3,3) pixels of the 518-wide image
        "depth": f(depth)[..., 0],      # (S,H,W)
        "depth_conf": f(depth_conf),
        "world_points": f(wpts),
        "world_points_conf": f(wpts_conf),
        "transform": tf,
        "t_load_s": t_load, "t_infer_s": t_infer,
        "files": [os.path.basename(p) for p in image_paths],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("images", help="dir of view_*.png, or a glob")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("-n", "--nviews", type=int, default=0,
                    help="use a subset, spread evenly over the arc (0 = all)")
    ap.add_argument("--pick", default=None,
                    help="explicit view indices, e.g. 0,1 — the real two-camera case")
    ap.add_argument("--model", default="vggt")
    a = ap.parse_args()

    paths = (sorted(glob.glob(os.path.join(a.images, "view_*.png")))
             if os.path.isdir(a.images) else sorted(glob.glob(a.images)))
    if not paths:
        raise SystemExit(f"no images in {a.images}")
    idx = list(range(len(paths)))
    if a.pick:
        idx = [int(x) for x in a.pick.split(",")]
    elif a.nviews and a.nviews < len(paths):
        idx = [int(round(i * (len(paths) - 1) / (a.nviews - 1)))
               for i in range(a.nviews)] if a.nviews > 1 else [0]
        idx = sorted(set(idx))
    paths = [paths[i] for i in idx]
    print(f"{a.model}: {len(paths)} views -> {[os.path.basename(p) for p in paths]}")

    if a.model != "vggt":
        raise SystemExit(f"unknown model {a.model}")
    out = run_vggt(paths)
    out["view_index"] = np.asarray(idx)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
    np.savez_compressed(a.out, **{k: v for k, v in out.items()
                                  if isinstance(v, (np.ndarray, int, float))},
                        meta=np.array(str({k: v for k, v in out.items()
                                           if not isinstance(v, np.ndarray)}),
                                      dtype=object))
    print(f"load {out['t_load_s']:.1f}s  infer {out['t_infer_s']:.2f}s  "
          f"depth {out['depth'].shape}  -> {a.out}")


if __name__ == "__main__":
    main()
