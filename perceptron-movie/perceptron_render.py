#!/usr/bin/env python3
"""Perceptron-movie LTX render engine — runs ON a DGX node, one shot at a time.

Reads ~/perceptron/shots_<node>.json, renders each shot with LTX-Video 13B
distilled at 1216x704 / 121 frames (5.04 s @ 24 fps) into
~/comfy/output/perceptron/, and records finished ids so a restart resumes.

Heat guard + ComfyUI watchdog + per-shot retries, same discipline as
eran-movie/eran_movie_render.py which this is derived from.
"""
import json, os, socket, subprocess, time, urllib.request

COMFY = "http://127.0.0.1:8188"
BASE = os.path.expanduser("~/perceptron")
NODE = os.environ.get("NODE") or socket.gethostname()
SHOTLIST = os.path.join(BASE, "shots_%s.json" % NODE)
STATE = os.path.join(BASE, "done_%s.json" % NODE)
LOG = os.path.join(BASE, "render_%s.log" % NODE)

WIDTH, HEIGHT, LENGTH = 1216, 704, 121
HOT_C, COOL_C, COOLDOWN_SEC = 82, 66, 8

NEG = ("low quality, worst quality, blurry, deformed, distorted, disfigured, "
       "motion smear, bad anatomy, cartoon, anime, text, watermark, subtitles, "
       "logo, letterbox, black bars, oversaturated, jpeg artifacts")


def log(m):
    line = time.strftime("%H:%M:%S") + "  " + m
    print(line, flush=True)
    try:
        with open(LOG, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def gpu_temp():
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=temperature.gpu",
             "--format=csv,noheader,nounits"], text=True)
        return int(out.strip().split("\n")[0])
    except Exception:
        return -1


def heat_guard():
    t = gpu_temp()
    if t >= HOT_C:
        log("HEAT GUARD: %dC -- pausing" % t)
        while True:
            time.sleep(30)
            t = gpu_temp()
            if 0 <= t <= COOL_C:
                log("HEAT GUARD: cooled to %dC -- resuming" % t)
                return


def wait_comfy():
    while True:
        try:
            urllib.request.urlopen(COMFY + "/system_stats", timeout=8)
            return
        except Exception:
            log("WATCHDOG: ComfyUI down -- waiting 30s")
            time.sleep(30)


def workflow(prompt, seed, sid):
    return {
        "44": {"class_type": "CheckpointLoaderSimple",
               "inputs": {"ckpt_name": "ltxv-13b-0.9.8-distilled.safetensors"}},
        "38": {"class_type": "CLIPLoader",
               "inputs": {"clip_name": "t5xxl_fp16.safetensors", "type": "ltxv",
                          "device": "default"}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["38", 0]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": NEG, "clip": ["38", 0]}},
        "70": {"class_type": "EmptyLTXVLatentVideo",
               "inputs": {"width": WIDTH, "height": HEIGHT, "length": LENGTH, "batch_size": 1}},
        "69": {"class_type": "LTXVConditioning",
               "inputs": {"positive": ["6", 0], "negative": ["7", 0], "frame_rate": 24.0}},
        "73": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "71": {"class_type": "LTXVScheduler",
               "inputs": {"steps": 8, "max_shift": 2.05, "base_shift": 0.95,
                          "stretch": True, "terminal": 0.1, "latent": ["70", 0]}},
        "72": {"class_type": "SamplerCustom",
               "inputs": {"model": ["44", 0], "add_noise": True, "noise_seed": seed,
                          "cfg": 1.0, "positive": ["69", 0], "negative": ["69", 1],
                          "sampler": ["73", 0], "sigmas": ["71", 0],
                          "latent_image": ["70", 0]}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["72", 0], "vae": ["44", 2]}},
        "78": {"class_type": "CreateVideo", "inputs": {"images": ["8", 0], "fps": 24.0}},
        "79": {"class_type": "SaveVideo",
               "inputs": {"video": ["78", 0], "filename_prefix": "perceptron/%s" % sid,
                          "format": "auto", "codec": "auto"}},
    }


def render(shot):
    wait_comfy()
    heat_guard()
    wf = workflow(shot["prompt"], int(shot["seed"]), shot["id"])
    req = urllib.request.Request(
        COMFY + "/prompt", data=json.dumps({"prompt": wf}).encode(),
        headers={"Content-Type": "application/json"})
    try:
        pid = json.load(urllib.request.urlopen(req, timeout=60))["prompt_id"]
    except Exception as e:
        log("submit FAILED %s: %s" % (shot["id"], e))
        return False
    t0 = time.time()
    while time.time() - t0 < 900:
        time.sleep(5)
        try:
            h = json.load(urllib.request.urlopen("%s/history/%s" % (COMFY, pid), timeout=30))
        except Exception:
            continue
        if pid in h:
            st = h[pid].get("status", {}).get("status_str")
            if st == "success":
                log("%s DONE %ds (GPU %dC)" % (shot["id"], int(time.time() - t0), gpu_temp()))
                return True
            log("%s ERROR: %s" % (shot["id"], st))
            return False
    log("%s TIMEOUT" % shot["id"])
    return False


def main():
    os.makedirs(BASE, exist_ok=True)
    shots = json.load(open(SHOTLIST))
    done = set(json.load(open(STATE))) if os.path.exists(STATE) else set()
    log("=== %s: %d shots, %d already done ===" % (NODE, len(shots), len(done)))
    t_start = time.time()
    for i, shot in enumerate(shots, 1):
        if shot["id"] in done:
            continue
        for attempt in range(3):
            if render(shot):
                done.add(shot["id"])
                json.dump(sorted(done), open(STATE, "w"))
                break
            log("retry %d for %s" % (attempt + 1, shot["id"]))
            time.sleep(15)
        el = time.time() - t_start
        log("[%d/%d done]  elapsed %dm" % (len(done), len(shots), el / 60))
        time.sleep(COOLDOWN_SEC)
    log("=== %s COMPLETE: %d/%d ===" % (NODE, len(done), len(shots)))


if __name__ == "__main__":
    main()
