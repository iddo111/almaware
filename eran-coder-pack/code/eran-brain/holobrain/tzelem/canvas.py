"""TZELEM / צלם — THE CANVAS: the same semantics as the weave, at ANY resolution.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

`anatomy.py` is the DEFINITION — an ALMA weave in which the beat is the depth and
the first spark to reach a patch of canvas wins it. This file is the BODY: the
same rule at 480p or 8K, in numpy, because a Python loom cannot run 33M knots a
frame and saying otherwise would be a lie.

The rule implemented here is *nearest wins*, decided per pixel, with no global
sort — exactly what "the first spark to arrive" means when you write it down in
array form. Strokes are visited in whatever order they come; the answer does not
depend on that order, which is the whole point.

GATE 2 — WHY THIS IS "RESOLUTION-FREE"
--------------------------------------
A stroke's radius is in WORLD units. The pixel radius is `radius * focal / depth`
and `focal` is proportional to the canvas height, so the SAME strokes at 8K are
the same painting seen closer — bigger strokes, not more of them. Nothing here
knows what resolution it is painting at; the only place a pixel count enters is
the focal length. That is why `tests/test_gate2.py` can block-average a 4K frame
down to 480p and demand it agree with the native 480p frame on WHICH STROKE OWNS
WHICH PIXEL.

TWO PASSES, AND WHY THE SECOND ONE CANNOT CHEAT
-----------------------------------------------
Painterly strokes need a soft edge, but a soft edge is alpha blending and alpha
blending is where every renderer smuggles a sort back in. So:

    pass 1  OWNERSHIP  — hard ellipse, nearest-wins per pixel. This, and only
                         this, decides what is visible. No colour is read.
    pass 2  COLOUR     — strokes that are CO-VISIBLE with the owner (their centre
                         depth is not behind the winning depth) lay down alpha and
                         are averaged. An occluded stroke contributes nothing.

So the soft edge blends neighbours on the same surface; it never lets a stroke
behind a wall bleed through, and it never reorders anything.

Numpy only. No torch on the PC.
"""
from __future__ import annotations

import numpy as np

BACKGROUND = (0.82, 0.87, 0.94)

# painterly defaults: length 2-4x width, a small deterministic angle jitter
ELONG_MIN, ELONG_MAX = 2.0, 4.0
JITTER_DEG = 14.0
GATE1_ELONG = 2.6          # the fixed shape gate 1 was measured with
COVISIBLE = 1.02           # a stroke may be this much farther and still blend
EDGE = 0.55                # alpha falloff exponent; <1 = fat core, thin rim


def _pixel_radius(cam, radius_world: np.ndarray, depth: np.ndarray) -> np.ndarray:
    focal = 0.5 * cam.height / np.tan(np.radians(cam.fov_deg) * 0.5)
    return np.maximum(radius_world * focal / np.maximum(depth, 1e-6), 0.75)


def _tangent_dir(cam, strokes, depth):
    """The 2D direction a stroke lies along: a surface tangent, seen from here.

    A stroke must lie IN the surface, so that when the camera turns, the stroke
    turns with the wall it is painted on. This is the second half of coherence —
    the first half is that the anchor is in the world.
    """
    tan = getattr(strokes, "tangent", None)
    if tan is None:
        # the ORIGINAL direction: a legal surface tangent, but an arbitrary one.
        view = strokes.point - cam.eye
        view = view / np.maximum(np.linalg.norm(view, axis=1, keepdims=True), 1e-9)
        tan = np.cross(strokes.normal, view)
    else:
        tan = np.asarray(tan, dtype=np.float64)
    n = np.linalg.norm(tan, axis=1, keepdims=True)
    tan = np.where(n > 1e-6, tan / np.maximum(n, 1e-9), np.array([1.0, 0.0, 0.0]))
    px0, py0, _ = cam.project(strokes.point)
    px1, py1, _ = cam.project(strokes.point + tan * (0.25 * depth)[:, None])
    dx, dy = px1 - px0, py1 - py0
    ln = np.hypot(dx, dy)
    ok = ln > 1e-6
    return np.where(ok, dx / np.where(ok, ln, 1.0), 1.0), \
        np.where(ok, dy / np.where(ok, ln, 1.0), 0.0)


# --------------------------------------------------------------- stroke shape

def footprint(cam, strokes, style: str = "painterly", seed: int = 17,
              elongation: float | None = None):
    """Where every stroke lands on THIS canvas, and what shape it is there.

    Returns a dict of per-stroke arrays. The jitter is drawn from a seed and the
    stroke's own index, so it is identical at 480p and at 8K — a stroke does not
    change shape when you look closer.
    """
    px, py, z = cam.project(strokes.point)
    depth = np.linalg.norm(strokes.point - cam.eye, axis=-1)
    live = (z > 0) & np.isfinite(depth) & np.isfinite(px) & np.isfinite(py)
    r = _pixel_radius(cam, strokes.radius, depth)
    ux, uy = _tangent_dir(cam, strokes, depth)

    n = len(strokes)
    if style == "gate1":
        el = np.full(n, GATE1_ELONG if elongation is None else elongation)
    elif style == "round":
        el = np.ones(n)
    elif style == "painterly":
        rng = np.random.default_rng(seed)
        el = rng.uniform(ELONG_MIN, ELONG_MAX, n)
        ang = np.radians(rng.uniform(-JITTER_DEG, JITTER_DEG, n))
        c, s = np.cos(ang), np.sin(ang)
        ux, uy = ux * c - uy * s, ux * s + uy * c
    else:
        raise ValueError("unknown stroke style: " + repr(style))

    # A planter may override the SHAPE per stroke (never the style's rng draws, so
    # the angle jitter of `painterly` is bit-identical with and without this).
    per = getattr(strokes, "elong", None)
    if per is not None:
        el = np.asarray(per, dtype=np.float64)

    ra = r * el                                   # half-length, along the tangent
    # the AABB of the ROTATED ellipse, not of its bounding circle: at 8K a stroke
    # is ~240 px long and the difference is a 2-3x saving on every splat.
    hw = np.sqrt((ra * ux) ** 2 + (r * uy) ** 2) + 1.0
    hh = np.sqrt((ra * uy) ** 2 + (r * ux) ** 2) + 1.0
    return {"px": px, "py": py, "depth": depth, "live": live,
            "r": r, "ra": ra, "ux": ux, "uy": uy, "hw": hw, "hh": hh}


def _boxes(fp, w, h):
    """Integer bounding boxes, clipped to the canvas."""
    x0 = np.maximum(np.floor(fp["px"] - fp["hw"]), 0).astype(np.int64)
    x1 = np.minimum(np.ceil(fp["px"] + fp["hw"]), w - 1).astype(np.int64)
    y0 = np.maximum(np.floor(fp["py"] - fp["hh"]), 0).astype(np.int64)
    y1 = np.minimum(np.ceil(fp["py"] + fp["hh"]), h - 1).astype(np.int64)
    return x0, x1, y0, y1


def _quad(fp, i, x0, x1, y0, y1):
    """(a/ra)^2 + (b/r)^2 for every pixel of a stroke's box. 1.0 is the rim."""
    dx = (np.arange(x0, x1 + 1, dtype=np.float32) - np.float32(fp["px"][i]))[None, :]
    dy = (np.arange(y0, y1 + 1, dtype=np.float32) - np.float32(fp["py"][i]))[:, None]
    ux, uy = np.float32(fp["ux"][i]), np.float32(fp["uy"][i])
    a = dx * ux + dy * uy
    b = dy * ux - dx * uy
    return (a / np.float32(fp["ra"][i])) ** 2 + (b / np.float32(fp["r"][i])) ** 2


# ------------------------------------------------------------- pass 1: who wins

def ownership(cam, strokes, style: str = "painterly", seed: int = 17,
              elongation: float | None = None, need_owner: bool = True):
    """WHICH STROKE OWNS EACH PIXEL. No colour is read anywhere in this function.

    Returns (owner, zbuf, footprint). owner is int32, -1 where nothing arrived.
    This is the whole hidden-surface decision, and it is `nearest wins` — the
    array form of "the first spark to reach the patch keeps it".
    """
    h, w = cam.height, cam.width
    # MEMORY (2026-09-05): `owner` is (H,W) int32 = 203 MB at 8K and the SOFT
    # render path never reads a single element of it. It was being allocated and
    # fancy-index-written once per stroke for nothing. `need_owner=False` is the
    # same pass without that cost; the z-buffer, which is what the caller wanted,
    # is unaffected.
    owner = np.full((h, w), -1, dtype=np.int32) if need_owner else None
    zbuf = np.full((h, w), np.inf, dtype=np.float32)
    fp = footprint(cam, strokes, style=style, seed=seed, elongation=elongation)
    x0s, x1s, y0s, y1s = _boxes(fp, w, h)
    dep = fp["depth"].astype(np.float32)

    for i in np.nonzero(fp["live"])[0]:
        x0, x1, y0, y1 = x0s[i], x1s[i], y0s[i], y1s[i]
        if x1 < x0 or y1 < y0:
            continue
        q = _quad(fp, i, x0, x1, y0, y1)
        sub_z = zbuf[y0:y1 + 1, x0:x1 + 1]
        win = (q <= 1.0) & (dep[i] < sub_z)
        if not win.any():
            continue
        sub_z[win] = dep[i]
        if need_owner:
            owner[y0:y1 + 1, x0:x1 + 1][win] = i
    return owner, zbuf, fp


# --------------------------------------------------------- pass 2: what colour

def render(stage, cam, strokes, background=BACKGROUND, elongation=None,
           style: str = "painterly", seed: int = 17, soft: bool = True,
           pal=None, out_dtype=np.float64, return_zbuf: bool = False,
           edge: float | None = None, return_owner: bool = False):
    """Paint the world-anchored strokes as this camera sees them. (H,W,3) in 0..1.

    `stage` is accepted and unused: the painting is made of the strokes and the
    camera alone — the stage is only ever the thing it is JUDGED against.

    `edge` (2026-09-06) overrides the alpha exponent for ONE call. The default is
    `None`, which uses the module's `EDGE` and is therefore bit-identical to every
    render made before this parameter existed — `oneroom/gate.py` was re-run
    against `out/gate.json` to prove it. It exists because `EDGE` is the second
    blur source in the painter and nobody had ever varied it: alpha is
    `(1-q)**EDGE` across the WHOLE ellipse, so at 0.55 a stroke is a soft gradient
    from centre to rim and neighbouring strokes average into each other. A larger
    exponent narrows the core and hardens the boundary between one stroke and the
    next, which is the difference between a wash and a mark. Iddo asked for marks.
    """
    from palette import Palette
    if pal is None:
        pal = Palette.of(strokes)
    if elongation is not None and style == "painterly":
        style = "gate1"                       # an explicit shape means a fixed shape

    # REVISION 2026-09-06 (TZ-12): `return_owner` hands back the ownership map this
    # call already computes. gate2.resolution_free used to call canvas.ownership and
    # then canvas.render, which runs the whole splat loop over every stroke's bounding
    # box a SECOND time for one answer -- about 37% of each resolution's wall clock,
    # 5-6 s of every gate 2 run at 4K. Nothing about the numbers changes.
    owner, zbuf, fp = ownership(cam, strokes, style=style, seed=seed,
                                elongation=elongation,
                                need_owner=(not soft) or return_owner)
    if not soft:
        return pal.lookup(owner, background)
    if not return_owner:
        del owner
        owner = None

    h, w = cam.height, cam.width
    acc = np.zeros((h, w, 3), dtype=np.float32)
    wsum = np.zeros((h, w), dtype=np.float32)
    x0s, x1s, y0s, y1s = _boxes(fp, w, h)
    dep = fp["depth"].astype(np.float32)
    tab = pal.table.astype(np.float32)
    ex = np.float32(EDGE if edge is None else edge)

    for i in np.nonzero(fp["live"])[0]:
        x0, x1, y0, y1 = x0s[i], x1s[i], y0s[i], y1s[i]
        if x1 < x0 or y1 < y0:
            continue
        q = _quad(fp, i, x0, x1, y0, y1)
        sub_z = zbuf[y0:y1 + 1, x0:x1 + 1]
        # co-visible with whatever WON here; an occluded stroke lays down nothing
        m = (q < 1.0) & (dep[i] <= sub_z * np.float32(COVISIBLE) + np.float32(1e-3))
        if not m.any():
            continue
        alpha = np.where(m, np.maximum(1.0 - q, 0.0) ** ex, 0.0).astype(np.float32)
        wsum[y0:y1 + 1, x0:x1 + 1] += alpha
        acc[y0:y1 + 1, x0:x1 + 1] += alpha[..., None] * tab[i]

    # MEMORY (2026-09-05): the old tail spent 2.4 GB at 8K to hold ONE picture —
    # a tiled (H,W,3) float32 canvas, a fancy-indexed copy of every hit pixel and
    # its quotient, and then a whole float64 COPY on the way out. `acc` is already
    # the right shape and becomes the right numbers the moment it is divided, so
    # divide it in place and hand it back. The VALUES do not move: the division
    # was float32 arithmetic before this change too.
    hit = wsum > 1e-6
    np.divide(acc, wsum[..., None], out=acc, where=hit[..., None])
    acc[~hit] = np.asarray(background, dtype=np.float32)
    del wsum
    img = acc if out_dtype == np.float32 else acc.astype(out_dtype)
    if return_zbuf and return_owner:
        return img, zbuf, hit, owner
    if return_zbuf:
        # `hit` is the coverage answer the caller would otherwise have to
        # rediscover by comparing the whole image against a probe colour.
        return img, zbuf, hit
    if return_owner:
        return img, owner
    return img


def source_hashes() -> dict:
    """THE PAINTER'S OWN FINGERPRINT (revision 2026-09-06, TZ-4).

    `freeze.py` pins the RULER -- `Stage.shade` and `Stage.gbuffer` -- and it does
    its job. Nothing pinned the PAINTER, so canvas.py moved +511/-240 lines
    underneath every stored gate number without a single alarm: re-running gate 1 at
    the exact configuration of `out/gate1-480.json` on 2026-09-06 moved every
    stroke-derived number (TZELEM fidelity 0.025025459 -> 0.022898981, -8.5%) while
    the two numbers that never pass through canvas.render -- BLANK and valid_px --
    reproduced to the last digit. A measurement must be able to name its painter.

    The constants are hashed alongside the source because EDGE and COVISIBLE change
    what every stroke lays down without changing a single line of any function.
    """
    import hashlib
    import inspect
    out = {}
    for name, fn in (("render", render), ("ownership", ownership),
                     ("footprint", footprint), ("warp", warp)):
        out[name] = hashlib.sha256(
            inspect.getsource(fn).encode("utf-8")).hexdigest()[:16]
    consts = repr((BACKGROUND, JITTER_DEG, GATE1_ELONG, COVISIBLE, EDGE))
    out["constants"] = hashlib.sha256(consts.encode("utf-8")).hexdigest()[:16]
    return out


def warp(img: np.ndarray, flow: dict) -> tuple[np.ndarray, np.ndarray]:
    """Carry an image from view a into view b along the EXACT flow.

    Returns (warped, valid). Nearest-neighbour on purpose: any interpolation would
    blur the picture and flatter every method that boils.
    """
    px, py = flow["px"], flow["py"]
    valid = flow["valid"]
    h, w = img.shape[:2]
    out = np.zeros_like(img)
    seen = np.zeros((h, w), dtype=bool)
    ys, xs = np.nonzero(valid)
    tx = np.clip(np.rint(px[ys, xs]), 0, w - 1).astype(np.int64)
    ty = np.clip(np.rint(py[ys, xs]), 0, h - 1).astype(np.int64)
    out[ty, tx] = img[ys, xs]
    seen[ty, tx] = True
    return out, seen
