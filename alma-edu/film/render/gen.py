#!/usr/bin/env python3
"""ALMIDO film generator — LTX-13B-distilled clips across the DGX fleet.

Posts one ComfyUI graph per shot; frames are saved as PNG *on the DGX* so the
Real-ESRGAN x4 stage can run there without dragging 4K frames over the wire.
"""
from __future__ import annotations

import argparse
import json
import queue
import threading
import time
import urllib.request
from pathlib import Path

import shots as S

CKPT = "ltxv-13b-0.9.8-distilled.safetensors"
T5 = "t5xxl_fp16.safetensors"
FPS = 24.0
STEPS = 8
WIDTH = 1216
HEIGHT = 704


def workflow(prompt: str, neg: str, out_prefix: str, seed: int,
             width: int, height: int, length: int) -> dict:
    return {
        "1": {"class_type": "CheckpointLoaderSimple",
              "inputs": {"ckpt_name": CKPT}},
        "0": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": T5, "type": "ltxv"}},
        "2": {"class_type": "CLIPTextEncode",
              "inputs": {"text": prompt, "clip": ["0", 0]}},
        "3": {"class_type": "CLIPTextEncode",
              "inputs": {"text": neg, "clip": ["0", 0]}},
        "4": {"class_type": "LTXVConditioning",
              "inputs": {"positive": ["2", 0], "negative": ["3", 0],
                         "frame_rate": FPS}},
        "5": {"class_type": "EmptyLTXVLatentVideo",
              "inputs": {"width": width, "height": height,
                         "length": length, "batch_size": 1}},
        "6": {"class_type": "ModelSamplingLTXV",
              "inputs": {"model": ["1", 0], "max_shift": 2.05,
                         "base_shift": 0.95}},
        "7": {"class_type": "LTXVScheduler",
              "inputs": {"steps": STEPS, "max_shift": 2.05, "base_shift": 0.95,
                         "stretch": True, "terminal": 0.1}},
        "8": {"class_type": "KSamplerSelect",
              "inputs": {"sampler_name": "euler"}},
        "9": {"class_type": "SamplerCustom",
              "inputs": {"model": ["6", 0], "add_noise": True,
                         "noise_seed": seed, "cfg": 1.0,
                         "positive": ["4", 0], "negative": ["4", 1],
                         "sampler": ["8", 0], "sigmas": ["7", 0],
                         "latent_image": ["5", 0]}},
        "10": {"class_type": "VAEDecode",
               "inputs": {"samples": ["9", 0], "vae": ["1", 2]}},
        "11": {"class_type": "SaveImage",
               "inputs": {"images": ["10", 0],
                          "filename_prefix": f"almido/{out_prefix}/f"}},
    }


def post(base: str, wf: dict) -> str:
    req = urllib.request.Request(
        base + "/prompt", data=json.dumps({"prompt": wf}).encode(),
        headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=90))["prompt_id"]


def await_job(base: str, pid: str, timeout_s: int = 3600) -> list[dict]:
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        time.sleep(5)
        try:
            h = json.load(urllib.request.urlopen(f"{base}/history/{pid}", timeout=60))
        except Exception:
            continue
        if pid not in h:
            continue
        st = h[pid].get("status", {})
        if st.get("status_str") != "success":
            raise RuntimeError(f"job failed: {json.dumps(st)[:600]}")
        imgs = []
        for node in h[pid].get("outputs", {}).values():
            imgs.extend(node.get("images", []))
        return imgs
    raise TimeoutError("job timed out")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", default="eran1=http://127.0.0.1:18188")
    ap.add_argument("--only", default="")
    ap.add_argument("--width", type=int, default=WIDTH)
    ap.add_argument("--height", type=int, default=HEIGHT)
    ap.add_argument("--out", default=str(Path(__file__).with_name("gen_log.json")))
    a = ap.parse_args()

    workers = []
    for w in a.workers.split(","):
        n, u = w.split("=", 1)
        workers.append((n, u))

    todo = [s for s in S.T2V if not a.only or s["id"] in a.only.split(",")]
    q: queue.Queue = queue.Queue()
    for s in todo:
        q.put(s)
    results: list[dict] = []
    lock = threading.Lock()

    def run(name: str, base: str) -> None:
        while True:
            try:
                job = q.get_nowait()
            except queue.Empty:
                return
            t0 = time.time()
            try:
                wf = workflow(job["prompt"], S.NEG, job["id"], job["seed"],
                              a.width, a.height, S.LEN)
                imgs = await_job(base, post(base, wf))
                dt = time.time() - t0
                with lock:
                    results.append(dict(id=job["id"], node=name, frames=len(imgs),
                                        seconds=round(dt, 1), seed=job["seed"],
                                        width=a.width, height=a.height,
                                        length=S.LEN,
                                        subfolder=imgs[0]["subfolder"] if imgs else ""))
                print(f"  [{name}] {job['id']}  {len(imgs)} frames  {dt:.0f}s", flush=True)
            except Exception as exc:
                print(f"  [{name}] {job['id']} FAILED {type(exc).__name__}: {exc}", flush=True)
                with lock:
                    results.append(dict(id=job["id"], node=name, error=str(exc)[:400]))
            finally:
                q.task_done()

    ths = [threading.Thread(target=run, args=w, daemon=True) for w in workers]
    t0 = time.time()
    for t in ths:
        t.start()
    for t in ths:
        t.join()
    print(f"fleet: {len([r for r in results if 'error' not in r])}/{len(todo)} shots "
          f"in {int(time.time()-t0)}s")
    Path(a.out).write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
