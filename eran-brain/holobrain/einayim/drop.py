"""EINAYIM / עֵינַיִם — THE DROP FOLDER. (PC orchestrator)

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

Iddo drops a phone video — or a folder of photos — into

    D:\\CLAUDE\\eran-brain\\holobrain\\einayim\\EINAYIM-drop\\

and gets back a mesh. Nothing else is asked of him: no calibration board, no
turntable, no app. That is the whole point of the organ.

What happens, in order:
  1. video -> frames, one every 0.5 s, with ffmpeg ON THE PC (ffmpeg is not ML).
  2. frames -> eran3 over scp. All inference is on eran3 (no ML on the PC).
  3. VGGT-1B -> per-view depth + camera.
  4. TSDF fusion + marching cubes -> a surface, decimated to <= 2000 faces.
  5. back to the PC -> STL, a turntable GIF and a .tzg rendered by TZELEM.

Run once over whatever is already there:      python drop.py --once
Watch the folder and process new arrivals:    python drop.py --watch

HONEST LIMITS, so nobody is surprised:
  * SCALE IS ARBITRARY. Photographs alone cannot know how big a thing is. Put a
    coin or a ruler in the shot and the size can be fixed afterwards by hand.
  * The mesh is the surface the CAMERA SAW. Nothing walks around the back of an
    object for you — walk around it yourself.
  * A textureless, shiny or transparent object will come out badly, and that is
    the model's honest failure, not a bug here.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time

# PC courtesy (2026-09-03 scar: renders starved the KESHEV mic): run below normal priority.
try:
    import psutil as _ps
    _ps.Process().nice(_ps.BELOW_NORMAL_PRIORITY_CLASS)
except Exception:
    pass


_HERE = os.path.dirname(os.path.abspath(__file__))
DROP = os.path.join(_HERE, "EINAYIM-drop")
DONE = os.path.join(DROP, "_done")
WORK = os.path.join(_HERE, "captures")
REMOTE = "eran3"
RDIR = "~/einayim"
PROXY = "http://<fabric-ip>:8899"

VIDEO = {".mp4", ".mov", ".m4v", ".avi", ".mkv"}
PHOTO = {".jpg", ".jpeg", ".png", ".heic", ".webp"}


def sh(cmd, **kw):
    p = subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True,
                       text=True, encoding="utf-8", errors="replace", **kw)
    if p.returncode:
        raise RuntimeError(f"{cmd}\n{p.stdout[-2000:]}\n{p.stderr[-2000:]}")
    return p.stdout


def frames_from_video(video, out_dir, fps=2.0, max_frames=48):
    os.makedirs(out_dir, exist_ok=True)
    sh(["ffmpeg", "-y", "-loglevel", "error", "-i", video,
        "-vf", f"fps={fps},scale=640:-2", "-q:v", "3",
        os.path.join(out_dir, "view_%02d.png")])
    got = sorted(f for f in os.listdir(out_dir) if f.startswith("view_"))
    if len(got) > max_frames:                     # keep an even spread, not the head
        keep = {got[int(round(i * (len(got) - 1) / (max_frames - 1)))]
                for i in range(max_frames)}
        for f in got:
            if f not in keep:
                os.remove(os.path.join(out_dir, f))
        for k, f in enumerate(sorted(os.listdir(out_dir))):
            os.rename(os.path.join(out_dir, f),
                      os.path.join(out_dir, f"tmp_{k:02d}.png"))
        for k, f in enumerate(sorted(os.listdir(out_dir))):
            os.rename(os.path.join(out_dir, f),
                      os.path.join(out_dir, f"view_{k:02d}.png"))
    return sorted(f for f in os.listdir(out_dir) if f.startswith("view_"))


def frames_from_folder(folder, out_dir, max_frames=48):
    from PIL import Image
    os.makedirs(out_dir, exist_ok=True)
    src = sorted(f for f in os.listdir(folder)
                 if os.path.splitext(f)[1].lower() in PHOTO)
    if len(src) > max_frames:
        src = [src[int(round(i * (len(src) - 1) / (max_frames - 1)))]
               for i in range(max_frames)]
    for k, f in enumerate(src):
        im = Image.open(os.path.join(folder, f)).convert("RGB")
        if im.width > 960:
            im = im.resize((960, round(im.height * 960 / im.width)),
                           Image.Resampling.LANCZOS)
        im.save(os.path.join(out_dir, f"view_{k:02d}.png"))
    return sorted(os.listdir(out_dir))


def process(item, faces=2000, gif_frames=16, fps=2.0, centre_frac=0.55):
    name = os.path.splitext(os.path.basename(item))[0]
    name = "".join(c if c.isalnum() or c in "-_" else "-" for c in name)[:40]
    work = os.path.join(WORK, name)
    frames = os.path.join(work, "frames")
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(frames, exist_ok=True)

    t0 = time.time()
    if os.path.isdir(item):
        got = frames_from_folder(item, frames)
        kind = "photos"
    else:
        got = frames_from_video(item, frames, fps=fps)
        kind = "video"
    if len(got) < 2:
        raise RuntimeError(f"{item}: {len(got)} usable frames — EINAYIM needs 2 or more")
    print(f"[{name}] {kind}: {len(got)} frames in {time.time()-t0:.1f}s")

    sh(f'ssh {REMOTE} "rm -rf {RDIR}/drops/{name} && mkdir -p {RDIR}/drops/{name}"')
    sh(f'scp -qr "{frames}" {REMOTE}:{RDIR}/drops/{name}/')
    rem = f"{RDIR}/drops/{name}"
    out = sh(f'ssh {REMOTE} "cd {RDIR} && export https_proxy={PROXY} HF_HUB_OFFLINE=1 && '
             f'./venv/bin/python recon.py {rem}/frames -o {rem}/pred.npz && '
             f'./venv/bin/python capture.py {rem}/pred.npz {rem}/mesh --faces {faces} '
             f'--centre-frac {centre_frac} --drop-plane"')
    print(out.strip()[-600:])

    os.makedirs(os.path.join(work, "out"), exist_ok=True)
    sh(f'scp -q {REMOTE}:{rem}/mesh.stl {REMOTE}:{rem}/mesh.json "{work}/out/"')
    meta = json.load(open(os.path.join(work, "out", "mesh.json")))

    from turntable import turntable
    stl = os.path.join(work, "out", "mesh.stl")
    stem = os.path.join(work, "out", f"einayim-{name}")
    shutil.copy(stl, stem + ".stl")
    turntable(stem + ".stl", stem, frames=gif_frames, width=288, height=216)

    meta.update({"source": item, "kind": kind, "frames": len(got),
                 "stl": stem + ".stl", "gif": stem + ".gif",
                 "tzg": stem + ".tzg", "seconds_total": round(time.time() - t0, 1)})
    json.dump(meta, open(os.path.join(work, "out", "einayim.json"), "w"), indent=1)
    print(f"[{name}] done in {meta['seconds_total']}s -> {stem}.stl / .gif")
    return meta


def pending():
    os.makedirs(DROP, exist_ok=True)
    os.makedirs(DONE, exist_ok=True)
    out = []
    for f in sorted(os.listdir(DROP)):
        p = os.path.join(DROP, f)
        if f.startswith("_") or f.startswith("."):
            continue
        if os.path.isdir(p):
            if any(os.path.splitext(x)[1].lower() in PHOTO for x in os.listdir(p)):
                out.append(p)
        elif os.path.splitext(f)[1].lower() in VIDEO:
            out.append(p)
    return out


def settled(path, wait=3.0):
    """Don't grab a file the phone is still copying."""
    a = os.path.getsize(path) if os.path.isfile(path) else -1
    time.sleep(wait)
    b = os.path.getsize(path) if os.path.isfile(path) else -1
    return a == b


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--watch", action="store_true")
    ap.add_argument("--faces", type=int, default=2000)
    ap.add_argument("--interval", type=float, default=10.0)
    ap.add_argument("--fps", type=float, default=2.0,
                    help="frames pulled per second of video (0.5 s apart by default)")
    ap.add_argument("--gif-frames", type=int, default=16, dest="gif_frames")
    ap.add_argument("--centre-frac", type=float, default=0.55, dest="centre_frac",
                    help="0 keeps the whole scene; 0.55 keeps what the middle of the first frame sees")
    a = ap.parse_args()
    os.makedirs(DROP, exist_ok=True); os.makedirs(DONE, exist_ok=True)
    os.makedirs(WORK, exist_ok=True)
    if not (a.once or a.watch):
        print(__doc__); return
    while True:
        for item in pending():
            if os.path.isfile(item) and not settled(item):
                continue
            try:
                process(item, faces=a.faces, fps=a.fps, gif_frames=a.gif_frames,
                        centre_frac=a.centre_frac)
                shutil.move(item, os.path.join(DONE, os.path.basename(item)))
            except Exception as e:                        # noqa: BLE001
                print(f"!! {item}: {type(e).__name__}: {e}", file=sys.stderr)
                shutil.move(item, os.path.join(DONE, "FAILED-" + os.path.basename(item)))
        if a.once:
            return
        time.sleep(a.interval)


if __name__ == "__main__":
    main()
