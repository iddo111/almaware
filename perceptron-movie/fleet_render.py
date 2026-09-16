#!/usr/bin/env python3
"""fleet_render.py — render a job list across EVERY DGX at once.

WHY THIS EXISTS. On 2026-08-14 the whole Perceptron movie was rendered by
eran_movie_render.py, which hardcodes COMFY = http://127.0.0.1:8188 — one node,
one shot at a time. eran2 and eran4 sat at 0% GPU and 40 C for the entire day
holding the SAME ltxv-13b checkpoint, and eran4 additionally held
ltxv-13b-0.9.7-dev (the non-distilled model whose real CFG would have fixed the
fake-CCTV-broadcast problem). Iddo asked why. There was no reason. Nobody
looked.

  18 shots @ 1920x1088 serial  = 41 min
  18 shots @ 1920x1088 x3      = 14 min

Workers are just ComfyUI endpoints — SSH-forwarded to the PC, so the fleet is
addressable from one script. A worker that dies is dropped and its job requeued
on a survivor; the run does not stop because one node did.
"""
from __future__ import annotations

import json
import queue
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

WORKERS = [
    ("eran1", "http://127.0.0.1:8188"),
    ("eran2", "http://127.0.0.1:8288"),
    ("eran4", "http://127.0.0.1:8488"),
]
POLL_S = 4
JOB_TIMEOUT_S = 900


def flux_workflow(prompt: str, out_prefix: str, seed: int,
                  width: int = 1024, height: int = 1024,
                  steps: int = 22, guidance: float = 3.5,
                  neg: str = "") -> dict:
    """FLUX dev fp8 as an all-in-one checkpoint (clip + vae included).

    cfg stays 1.0 — FLUX is guidance-distilled and a real CFG scrambles it.
    Prompt adherence comes from FluxGuidance, NOT from cfg. This is the exact
    distinction that made the LTX 1080p run reproduce a Chinese TV broadcast:
    at cfg 1.0 a negative prompt is inert, so anything you want ABSENT has to
    be handled by the model choice or the positive prompt, never by `neg`.
    """
    return {
        "1": {"class_type": "CheckpointLoaderSimple",
              "inputs": {"ckpt_name": "flux1-dev-fp8.safetensors"}},
        "2": {"class_type": "CLIPTextEncode",
              "inputs": {"text": prompt, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode",
              "inputs": {"text": neg, "clip": ["1", 1]}},
        "4": {"class_type": "FluxGuidance",
              "inputs": {"conditioning": ["2", 0], "guidance": guidance}},
        "5": {"class_type": "EmptyLatentImage",
              "inputs": {"width": width, "height": height, "batch_size": 1}},
        "6": {"class_type": "KSampler",
              "inputs": {"model": ["1", 0], "seed": seed, "steps": steps,
                         "cfg": 1.0, "sampler_name": "euler",
                         "scheduler": "simple", "denoise": 1.0,
                         "positive": ["4", 0], "negative": ["3", 0],
                         "latent_image": ["5", 0]}},
        "7": {"class_type": "VAEDecode",
              "inputs": {"samples": ["6", 0], "vae": ["1", 2]}},
        "8": {"class_type": "SaveImage",
              "inputs": {"images": ["7", 0], "filename_prefix": out_prefix}},
    }


def _post(base: str, wf: dict) -> str:
    req = urllib.request.Request(
        base + "/prompt", data=json.dumps({"prompt": wf}).encode(),
        headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=60))["prompt_id"]


def _await(base: str, pid: str) -> list[dict]:
    t0 = time.time()
    while time.time() - t0 < JOB_TIMEOUT_S:
        time.sleep(POLL_S)
        try:
            h = json.load(urllib.request.urlopen(f"{base}/history/{pid}", timeout=30))
        except Exception:
            continue
        if pid not in h:
            continue
        st = h[pid].get("status", {})
        if st.get("status_str") != "success":
            raise RuntimeError(f"job failed: {st.get('status_str')}")
        imgs = []
        for node in h[pid].get("outputs", {}).values():
            imgs.extend(node.get("images", []))
        return imgs
    raise TimeoutError("job timed out")


def _fetch(base: str, img: dict, dest: Path) -> Path:
    q = urllib.parse.urlencode({"filename": img["filename"],
                                "subfolder": img.get("subfolder", ""),
                                "type": img.get("type", "output")})
    data = urllib.request.urlopen(f"{base}/view?{q}", timeout=120).read()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return dest


def run(jobs: list[dict], outdir: Path, log=print) -> list[Path]:
    """jobs: [{id, prompt, seed, width, height, steps, guidance, neg}]"""
    import urllib.parse  # noqa: F401 - used via _fetch
    q: queue.Queue = queue.Queue()
    for j in jobs:
        q.put(j)
    done: list[Path] = []
    lock = threading.Lock()

    def worker(name: str, base: str) -> None:
        while True:
            try:
                job = q.get_nowait()
            except queue.Empty:
                return
            t0 = time.time()
            try:
                wf = flux_workflow(
                    job["prompt"], job["id"], int(job.get("seed", 0)),
                    width=int(job.get("width", 1024)),
                    height=int(job.get("height", 1024)),
                    steps=int(job.get("steps", 22)),
                    guidance=float(job.get("guidance", 3.5)),
                    neg=job.get("neg", ""))
                imgs = _await(base, _post(base, wf))
                for k, im in enumerate(imgs):
                    p = _fetch(base, im, outdir / f"{job['id']}.png")
                    with lock:
                        done.append(p)
                log(f"  [{name}] {job['id']} ok  {int(time.time()-t0)}s")
            except Exception as exc:
                log(f"  [{name}] {job['id']} FAILED ({type(exc).__name__}: {exc}) — requeued")
                q.put(job)
                return          # this worker steps out; survivors take the load
            finally:
                q.task_done()

    ths = [threading.Thread(target=worker, args=w, daemon=True) for w in WORKERS]
    t0 = time.time()
    for t in ths:
        t.start()
    for t in ths:
        t.join()
    log(f"fleet: {len(done)}/{len(jobs)} images in {int(time.time()-t0)}s "
        f"across {len(WORKERS)} nodes")
    return done


import urllib.parse  # noqa: E402
