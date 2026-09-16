#!/usr/bin/env python3
"""FLUX plate -> real Hebrew aleph composited in -> LTX image-to-video."""
from __future__ import annotations

import argparse
import io
import json
import mimetypes
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from PIL import Image

import letter
import shots as S

CKPT = "ltxv-13b-0.9.8-distilled.safetensors"
T5 = "t5xxl_fp16.safetensors"
FLUX = "flux1-dev-fp8.safetensors"
HERE = Path(__file__).parent


# --------------------------------------------------------------------- comfy io
def post(base: str, wf: dict) -> str:
    req = urllib.request.Request(
        base + "/prompt", data=json.dumps({"prompt": wf}).encode(),
        headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=90))["prompt_id"]


def await_job(base: str, pid: str, timeout_s: int = 3600) -> list[dict]:
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        time.sleep(4)
        try:
            h = json.load(urllib.request.urlopen(f"{base}/history/{pid}", timeout=60))
        except Exception:
            continue
        if pid not in h:
            continue
        st = h[pid].get("status", {})
        if st.get("status_str") != "success":
            raise RuntimeError(f"job failed: {json.dumps(st)[:700]}")
        imgs = []
        for node in h[pid].get("outputs", {}).values():
            imgs.extend(node.get("images", []))
        return imgs
    raise TimeoutError("job timed out")


def fetch(base: str, img: dict) -> bytes:
    q = urllib.parse.urlencode({"filename": img["filename"],
                                "subfolder": img.get("subfolder", ""),
                                "type": img.get("type", "output")})
    return urllib.request.urlopen(f"{base}/view?{q}", timeout=180).read()


def upload(base: str, path: Path) -> str:
    boundary = uuid.uuid4().hex
    body = io.BytesIO()

    def part(name: str, value: str) -> None:
        body.write(f"--{boundary}\r\nContent-Disposition: form-data; "
                   f'name="{name}"\r\n\r\n{value}\r\n'.encode())

    body.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; "
               f'filename="{path.name}"\r\n'
               f"Content-Type: {mimetypes.guess_type(path.name)[0]}\r\n\r\n".encode())
    body.write(path.read_bytes())
    body.write(b"\r\n")
    part("overwrite", "true")
    body.write(f"--{boundary}--\r\n".encode())
    req = urllib.request.Request(
        base + "/upload/image", data=body.getvalue(),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    return json.load(urllib.request.urlopen(req, timeout=180))["name"]


# ------------------------------------------------------------------- workflows
def flux_wf(prompt: str, seed: int, w: int, h: int, prefix: str) -> dict:
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": FLUX}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ["1", 1]}},
        "4": {"class_type": "FluxGuidance", "inputs": {"conditioning": ["2", 0], "guidance": 3.2}},
        "5": {"class_type": "EmptyLatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}},
        "6": {"class_type": "KSampler",
              "inputs": {"model": ["1", 0], "seed": seed, "steps": 24, "cfg": 1.0,
                         "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0,
                         "positive": ["4", 0], "negative": ["3", 0], "latent_image": ["5", 0]}},
        "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["1", 2]}},
        "8": {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": prefix}},
    }


def i2v_wf(prompt: str, neg: str, image_name: str, seed: int,
           w: int, h: int, length: int, prefix: str) -> dict:
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": CKPT}},
        "0": {"class_type": "CLIPLoader", "inputs": {"clip_name": T5, "type": "ltxv"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["0", 0]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": neg, "clip": ["0", 0]}},
        "4": {"class_type": "LTXVConditioning",
              "inputs": {"positive": ["2", 0], "negative": ["3", 0], "frame_rate": float(S.FPS)}},
        "12": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "13": {"class_type": "ImageScale",
               "inputs": {"image": ["12", 0], "upscale_method": "lanczos",
                          "width": w, "height": h, "crop": "center"}},
        "5": {"class_type": "LTXVImgToVideo",
              "inputs": {"positive": ["4", 0], "negative": ["4", 1], "vae": ["1", 2],
                         "image": ["13", 0], "width": w, "height": h,
                         "length": length, "batch_size": 1, "strength": 1.0}},
        "6": {"class_type": "ModelSamplingLTXV",
              "inputs": {"model": ["1", 0], "max_shift": 2.05, "base_shift": 0.95}},
        "7": {"class_type": "LTXVScheduler",
              "inputs": {"steps": 8, "max_shift": 2.05, "base_shift": 0.95,
                         "stretch": True, "terminal": 0.1}},
        "8": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "9": {"class_type": "SamplerCustom",
              "inputs": {"model": ["6", 0], "add_noise": True, "noise_seed": seed,
                         "cfg": 1.0, "positive": ["5", 0], "negative": ["5", 1],
                         "sampler": ["8", 0], "sigmas": ["7", 0], "latent_image": ["5", 2]}},
        "10": {"class_type": "VAEDecode", "inputs": {"samples": ["9", 0], "vae": ["1", 2]}},
        "11": {"class_type": "SaveImage",
               "inputs": {"images": ["10", 0], "filename_prefix": prefix}},
    }


# ------------------------------------------------------------------------ main
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:18188")
    ap.add_argument("--only", default="")
    ap.add_argument("--width", type=int, default=1536)
    ap.add_argument("--height", type=int, default=864)
    ap.add_argument("--stage", default="all", choices=["plate", "all"])
    a = ap.parse_args()

    plates = HERE / "plates"
    plates.mkdir(exist_ok=True)
    log = []

    todo = [s for s in S.I2V if not a.only or s["id"] in a.only.split(",")]
    for sh in todo:
        t0 = time.time()
        raw = plates / f"{sh['id']}_plate.png"
        if not raw.exists():
            imgs = await_job(a.base, post(a.base, flux_wf(
                sh["plate"], sh["seed"], a.width, a.height, f"almido_plate/{sh['id']}")))
            raw.write_bytes(fetch(a.base, imgs[0]))
            print(f"  plate {sh['id']} {int(time.time()-t0)}s", flush=True)

        comp = plates / f"{sh['id']}_aleph.png"
        img = Image.open(raw).convert("RGB")
        letter.apply(img, seed=sh["seed"], **sh["letter"]).save(comp)
        print(f"  composited {sh['id']} -> {comp.name}", flush=True)
        if a.stage == "plate":
            log.append(dict(id=sh["id"], plate=str(raw), composite=str(comp)))
            continue

        name = upload(a.base, comp)
        t1 = time.time()
        imgs = await_job(a.base, post(a.base, i2v_wf(
            sh["motion"], S.NEG, name, sh["seed"] + 1, a.width, a.height,
            sh.get("length", S.LEN), f"almido/{sh['id']}/f")))
        print(f"  [i2v] {sh['id']}  {len(imgs)} frames  {int(time.time()-t1)}s", flush=True)
        log.append(dict(id=sh["id"], frames=len(imgs), seconds=round(time.time() - t0, 1),
                        seed=sh["seed"], width=a.width, height=a.height, length=sh.get("length", S.LEN),
                        route="flux-plate + composited aleph + LTXVImgToVideo"))

    (HERE / "i2v_log.json").write_text(json.dumps(log, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
