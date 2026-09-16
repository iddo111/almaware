"""TZELEM / צלם — THE DOOR THE ENGINE COMES THROUGH.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

`stage.py` is a world we wrote in numpy so gate 1 could be proven with no engine
installed. This file is how a REAL engine hands its world over instead — and the
whole design rule is one line:

    what comes back from disk must be indistinguishable from stage.gbuffer().

Same dict, same keys, same shapes. `canvas.py`, `anatomy.py` and `ruler.py` then
work on a Godot frame without a single line changing. If a loader needs the rest of
the organ to know where the pixels came from, the loader is wrong.

THE FORMAT — deliberately dumb, and 100% ours
---------------------------------------------
No EXR, no OpenCV, no imageio. A G-buffer is four arrays and a camera; anything
fancier is a dependency we would have to keep alive forever. GDScript can write
raw bytes with FileAccess and numpy can read them with frombuffer, so:

    <name>.tzg    magic "TZGBUF1\\0", uint32 width, uint32 height, uint32 flags,
                  then, little-endian, in this order:
                      float32 depth  [H*W]      distance from the eye along the ray
                                                (0 or non-finite = the ray hit nothing)
                      float32 normal [H*W*3]    unit, world space   (flag bit 0)
                      float32 albedo [H*W*3]    what the EYE RECEIVES, 0..1, i.e. the
                                                lit colour — not the raw material
                                                colour. A painter paints what he sees;
                                                stage.scatter() already samples the
                                                shaded image and this must match it.
                                                (flag bit 1)
                      int32   ident  [H*W]      object id, -1 = miss   (flag bit 2)
    <name>.json   the camera: eye, target, up, fov_deg, width, height

Depth is distance from the eye, NOT z along the forward axis. That is what
`stage.gbuffer()` stores and what `stage.flow()` compares against, and mixing the
two conventions is the classic way to get a renderer that is subtly wrong
everywhere and obviously wrong nowhere.
"""
from __future__ import annotations

import json
import os
import struct

import numpy as np

MAGIC = b"TZGBUF1\0"
HAS_NORMAL, HAS_ALBEDO, HAS_IDENT = 1, 2, 4


# ------------------------------------------------------------------ writing

def write(path_stem: str, cam, depth: np.ndarray, normal: np.ndarray | None = None,
          albedo: np.ndarray | None = None, ident: np.ndarray | None = None) -> str:
    """Write one frame in the format the Godot exporter writes."""
    h, w = depth.shape
    flags = ((HAS_NORMAL if normal is not None else 0)
             | (HAS_ALBEDO if albedo is not None else 0)
             | (HAS_IDENT if ident is not None else 0))
    blob = bytearray(MAGIC + struct.pack("<III", w, h, flags))
    d = np.where(np.isfinite(depth), depth, 0.0)          # 0 is the miss marker
    blob += np.ascontiguousarray(d, dtype="<f4").tobytes()
    if normal is not None:
        blob += np.ascontiguousarray(normal, dtype="<f4").tobytes()
    if albedo is not None:
        blob += np.ascontiguousarray(albedo, dtype="<f4").tobytes()
    if ident is not None:
        blob += np.ascontiguousarray(ident, dtype="<i4").tobytes()

    os.makedirs(os.path.dirname(os.path.abspath(path_stem)) or ".", exist_ok=True)
    with open(path_stem + ".tzg", "wb") as f:
        f.write(blob)
    with open(path_stem + ".json", "w", encoding="utf-8") as f:
        json.dump({"eye": list(map(float, cam.eye)),
                   "target": list(map(float, cam.target)),
                   "up": list(map(float, cam.up)),
                   "fov_deg": float(cam.fov_deg),
                   "width": int(cam.width), "height": int(cam.height)},
                  f, indent=1)
    return path_stem + ".tzg"


def from_stage(stage, cam, path_stem: str) -> str:
    """Dump our own numpy world in the engine's format.

    This is not a convenience — it is how the format gets TESTED without an engine.
    Round-trip it and the loader must hand back exactly what stage.gbuffer() gives.
    """
    g = stage.gbuffer(cam)
    return write(path_stem, cam, g["depth"], g["normal"], stage.shade(g))


# ------------------------------------------------------------------ reading

def load(path_stem: str):
    """Read one frame back. Returns (gbuffer_dict, camera) — the stage's own shapes."""
    from stage import Camera

    stem = path_stem[:-4] if path_stem.endswith(".tzg") else path_stem
    with open(stem + ".tzg", "rb") as f:
        raw = f.read()
    if raw[:8] != MAGIC:
        raise ValueError(f"{stem}.tzg is not a TZELEM g-buffer (magic {raw[:8]!r})")
    w, h, flags = struct.unpack("<III", raw[8:20])
    n = w * h
    off = 20

    def take(count, dtype):
        nonlocal off
        size = count * np.dtype(dtype).itemsize
        a = np.frombuffer(raw, dtype=dtype, count=count, offset=off)
        off += size
        return a

    depth = take(n, "<f4").astype(np.float64).reshape(h, w)
    normal = (take(n * 3, "<f4").astype(np.float64).reshape(h, w, 3)
              if flags & HAS_NORMAL else np.zeros((h, w, 3)))
    albedo = (take(n * 3, "<f4").astype(np.float64).reshape(h, w, 3)
              if flags & HAS_ALBEDO else np.zeros((h, w, 3)))
    ident = (take(n, "<i4").reshape(h, w) if flags & HAS_IDENT
             else np.full((h, w), -1, dtype=np.int64))

    meta = json.load(open(stem + ".json", encoding="utf-8"))
    cam = Camera(eye=np.array(meta["eye"]), target=np.array(meta["target"]),
                 up=np.array(meta.get("up", [0.0, 1.0, 0.0])),
                 fov_deg=meta["fov_deg"], width=meta["width"], height=meta["height"])
    if (cam.height, cam.width) != (h, w):
        raise ValueError(f"{stem}: camera says {cam.width}x{cam.height}, "
                         f"buffer says {w}x{h}")

    mask = depth > 0
    point = cam.eye + cam.rays() * np.where(mask, depth, 0.0)[..., None]
    return ({"depth": np.where(mask, depth, np.inf), "point": point,
             "normal": normal, "albedo": albedo, "mask": mask,
             "ident": ident}, cam)


class LoadedStage:
    """A Stage whose world came from an engine instead of from ray casting.

    It answers the two questions the organ actually asks of a stage — `gbuffer(cam)`
    and `shade(g)` — by looking the frame up by camera identity. Everything else in
    TZELEM keeps working untouched, which is the entire point of this file.

    `flow()` is inherited unchanged: it only ever uses gbuffer + camera projection,
    so exact optical flow between two ENGINE frames costs nothing extra. That is the
    quiet win here — the ruler stays exact when the pixels stop being ours.
    """

    def __init__(self, frames: dict) -> None:
        self.frames = frames                     # id(camera) -> (gbuffer, camera)

    @classmethod
    def from_dir(cls, folder: str) -> "LoadedStage":
        stems = sorted(os.path.splitext(f)[0] for f in os.listdir(folder)
                       if f.endswith(".tzg"))
        if not stems:
            raise FileNotFoundError(f"no .tzg frames in {folder}")
        out, cams = {}, []
        for s in stems:
            g, cam = load(os.path.join(folder, s))
            out[id(cam)] = (g, cam)
            cams.append(cam)
        st = cls(out)
        st.cameras = cams
        return st

    def gbuffer(self, cam):
        rec = self.frames.get(id(cam))
        if rec is None:
            raise KeyError("TZELEM was handed a camera that has no exported frame. "
                           "An engine-backed stage cannot invent a view it was never "
                           "given — export that pose and try again.")
        return rec[0]

    def shade(self, g):
        """The engine already shaded it; 'albedo' here IS what the eye received."""
        sky = np.array([0.82, 0.87, 0.94])
        return np.where(g["mask"][..., None], g["albedo"], sky)

    # the exact ruler, unchanged
    flow = None      # bound below


def _flow(self, a, b):
    from stage import Stage
    return Stage.flow(self, a, b)


LoadedStage.flow = _flow
