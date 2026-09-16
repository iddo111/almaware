# -*- coding: utf-8 -*-
"""TZELEM - CONTACT SHADOW, AMBIENT OCCLUSION AND SURFACE TEXTURE.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

WHY THIS FILE EXISTS, and what it is forbidden to do
----------------------------------------------------
Iddo, 2026-09-06 01:07: "tetaken et ha-modelim shelanu she-lo yihyu BLURRED."
Measured on the one ruler (Laplacian variance, greyscale, <=2400 px long edge):
the workshop he rejected reads 126 where his own document pages read 1868-4038.
Two structural causes were named, and this file answers the second one:

    `stage.Stage.shade` is Lambert + ambient and there is NO SHADOW RAY anywhere
    in TZELEM. Nothing is ever dark because something else is in front of it.

Sharpness IS edges. A scene with no contact darkening has no hard edges to find,
so no amount of smaller brushstrokes will save it.

**`Stage.shade` IS THE RULER** - every fidelity number TZELEM has ever reported is
an MSE against it, and editing it would silently delete the meaning of all of them.
So nothing in this file touches it. Instead the occlusion is baked into the
**albedo channel of the g-buffer**, which is exactly where a game bakes it, and the
untouched `Stage.shade` then does what it always did.

That choice has one more property that matters: `anatomy.scatter` plants a stroke's
colour from `stage.shade(...)`, so the painter and the ruler receive the SAME
darkening from the SAME line of code. The gate stays a fair fight.

Numpy only. No torch on the PC.
"""
from __future__ import annotations

# TZ-5, 2026-09-06: NOTHING RENDERS WITH THIS. `occlusion.py`'s only importer in the
# whole folder is `freeze.py`, which uses it as a null-check (ShadedStage with every
# strength at zero must reproduce Stage bit for bit). Its measured +300% sharpness
# reaches no picture TZELEM actually makes. Declared here so the state is a fact the
# code asserts rather than a silence; `tests/test_wiring.py` checks it against the
# real import graph in both directions.
RENDER_PATH_WIRED = False

import numpy as np

from stage import Stage

EPS = 1e-4


# ------------------------------------------------------------------ ray casting

def _any_hit(lo: np.ndarray, hi: np.ndarray, o: np.ndarray, d: np.ndarray,
             tmax: np.ndarray | float, tmin_eps: float = 2e-3) -> np.ndarray:
    """Does ANY box block the segment o -> o + d*tmax? Per-ray origins.

    `Stage._hit_boxes` cannot answer this: it takes ONE origin for the whole batch
    and it wants the NEAREST hit. A shadow ray starts at its own surface point and
    only ever asks yes/no, so it can stop at the first blocker and never sort.

    lo, hi are (B,3); o, d are (M,3). Returns bool (M,).
    """
    with np.errstate(divide="ignore", invalid="ignore"):
        inv = np.divide(1.0, d, out=np.full_like(d, np.inf), where=d != 0)
    blocked = np.zeros(len(o), dtype=bool)
    tmax = np.asarray(tmax, dtype=np.float64)
    for i in range(len(lo)):
        live = ~blocked
        if not live.any():
            break
        t0 = (lo[i] - o[live]) * inv[live]
        t1 = (hi[i] - o[live]) * inv[live]
        near = np.maximum(np.minimum(t0, t1).max(axis=1), tmin_eps)
        far = np.maximum(t0, t1).min(axis=1)
        tm = tmax[live] if tmax.ndim else tmax
        blocked[live] = (far >= near) & (near < tm)
    return blocked


def _chunks(n: int, size: int):
    for a in range(0, n, size):
        yield a, min(a + size, n)


def _blocker_arrays(stage: Stage, blockers: np.ndarray | None):
    """The boxes a shadow ray is allowed to be stopped by.

    WHY THIS EXISTS AND IS NOT A CHEAT. In an interior the light is INSIDE the
    room: it comes through the window in the west wall, or out of the tubes bolted
    to the ceiling. Those fixtures, and the shell that holds them, are boxes like
    any other - so a shadow ray fired at the window hits the wall the window is cut
    into and the entire room goes black. Excluding the emitter and its shell is not
    softening the test; it is telling the ray caster where the light actually is.
    Everything else in the room still blocks, which is the whole point.
    """
    lo = np.array([b.lo for b in stage.boxes])
    hi = np.array([b.hi for b in stage.boxes])
    if blockers is not None:
        keep = np.asarray(blockers, dtype=bool)
        lo, hi = lo[keep], hi[keep]
    return lo, hi


def shadow(stage: Stage, point: np.ndarray, normal: np.ndarray,
           light_dir: np.ndarray | None = None, reach: float = 40.0,
           chunk: int = 120_000, blockers: np.ndarray | None = None) -> np.ndarray:
    """1.0 where the light reaches the point, 0.0 where a box stands in the way.

    The one ray every renderer has and TZELEM did not.
    """
    ld = stage.light_dir if light_dir is None else np.asarray(light_dir, float)
    ld = ld / np.linalg.norm(ld)
    to_light = -ld                                   # light_dir points FROM the light
    n = len(point)
    lit = np.ones(n)
    lo, hi = _blocker_arrays(stage, blockers)
    facing = (normal @ to_light) > 1e-6              # a back face is already dark
    for a, b in _chunks(n, chunk):
        m = facing[a:b]
        if not m.any():
            continue
        o = point[a:b][m] + normal[a:b][m] * EPS
        d = np.repeat(to_light[None, :], int(m.sum()), axis=0)
        hit = _any_hit(lo, hi, o, d, reach)
        sub = lit[a:b]
        sub[m] = np.where(hit, 0.0, 1.0)
        lit[a:b] = sub
    return lit


def shadow_point(stage: Stage, point: np.ndarray, normal: np.ndarray,
                 light_pos: np.ndarray, chunk: int = 120_000,
                 blockers: np.ndarray | None = None,
                 softness: float = 0.0, samples: int = 1,
                 seed: int = 5) -> np.ndarray:
    """Shadow from a light AT A PLACE IN THE ROOM, not at infinity.

    Indoors this is the honest model and it is also the better picture: the window
    is 1.5 m of wall at night and the tubes are two metres of ceiling, so shadows
    fan out from them instead of running parallel, and a thing standing near the
    window throws a long one. `softness` (metres) jitters the light position over
    `samples` rays and returns a fraction in 0..1, which is a penumbra.
    """
    n = len(point)
    lo, hi = _blocker_arrays(stage, blockers)
    lp = np.asarray(light_pos, dtype=np.float64)
    rng = np.random.default_rng(seed)
    offs = np.zeros((samples, 3))
    if samples > 1 and softness > 0:
        offs = rng.normal(0.0, softness, (samples, 3))
        offs[0] = 0.0
    acc = np.zeros(n)
    for a, b in _chunks(n, chunk):
        o = point[a:b] + normal[a:b] * EPS
        got = np.zeros(b - a)
        for s in range(samples):
            v = (lp + offs[s]) - o
            dist = np.linalg.norm(v, axis=1)
            d = v / np.maximum(dist, 1e-9)[:, None]
            facing = np.einsum("ij,ij->i", normal[a:b], d) > 1e-6
            blocked = np.ones(b - a, dtype=bool)
            if facing.any():
                blocked[facing] = _any_hit(lo, hi, o[facing], d[facing],
                                           dist[facing] - 2e-3)
            got += ~blocked
        acc[a:b] = got / samples
    return acc


def _hemisphere(n_rays: int, seed: int = 11) -> np.ndarray:
    """Cosine-weighted directions around +z, deterministic (Fibonacci spiral)."""
    i = np.arange(n_rays) + 0.5
    phi = np.arccos(np.sqrt(1.0 - i / n_rays))
    gold = np.pi * (1.0 + 5.0 ** 0.5)
    th = gold * i + seed
    return np.stack([np.cos(th) * np.sin(phi), np.sin(th) * np.sin(phi),
                     np.cos(phi)], axis=1)


def ambient_occlusion(stage: Stage, point: np.ndarray, normal: np.ndarray,
                      n_rays: int = 12, reach: float = 0.55,
                      chunk: int = 120_000, seed: int = 11) -> np.ndarray:
    """How much of the sky this point can see: 1.0 open, 0.0 buried in a corner.

    Short rays on purpose (`reach` is about half a metre). This is CONTACT
    occlusion - the dark seam where the toolbox meets the floor and where the
    drawer meets the cabinet. Those seams are the hard edges the picture lacked.
    """
    n = len(point)
    lo = np.array([b.lo for b in stage.boxes])
    hi = np.array([b.hi for b in stage.boxes])
    dirs = _hemisphere(n_rays, seed)
    open_frac = np.zeros(n)

    # a stable tangent frame per point, so the hemisphere really sits on the surface
    up = np.where(np.abs(normal[:, 1:2]) < 0.9, np.array([0.0, 1.0, 0.0]),
                  np.array([1.0, 0.0, 0.0]))
    t = np.cross(normal, up)
    t = t / np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-9)
    bt = np.cross(normal, t)

    for a, b in _chunks(n, chunk):
        o = point[a:b] + normal[a:b] * EPS
        acc = np.zeros(b - a)
        for k in range(n_rays):
            dx, dy, dz = dirs[k]
            d = t[a:b] * dx + bt[a:b] * dy + normal[a:b] * dz
            acc += ~_any_hit(lo, hi, o, d, reach)
        open_frac[a:b] = acc / n_rays
    return open_frac


# --------------------------------------------------------------------- texture

def _hash3(ix: np.ndarray, iy: np.ndarray, iz: np.ndarray, salt: int) -> np.ndarray:
    """A deterministic 0..1 value per integer lattice cell. No tables, no rng."""
    h = (ix.astype(np.int64) * 73856093) ^ (iy.astype(np.int64) * 19349663) \
        ^ (iz.astype(np.int64) * 83492791) ^ np.int64(salt * 2654435761)
    h = (h ^ (h >> 13)) * np.int64(1274126177)
    h = h ^ (h >> 16)
    return (h & 0xFFFFFF).astype(np.float64) / float(0xFFFFFF)


def value_noise(p: np.ndarray, period: float, salt: int = 0) -> np.ndarray:
    """Trilinear value noise on a world-space lattice. p is (...,3) in metres."""
    q = np.asarray(p, dtype=np.float64) / period
    i = np.floor(q)
    f = q - i
    f = f * f * (3.0 - 2.0 * f)                       # smoothstep
    ix, iy, iz = i[..., 0], i[..., 1], i[..., 2]
    c = {}
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                c[(dx, dy, dz)] = _hash3(ix + dx, iy + dy, iz + dz, salt)
    fx, fy, fz = f[..., 0], f[..., 1], f[..., 2]

    def lerp(a, b, t):
        return a + (b - a) * t
    x00 = lerp(c[(0, 0, 0)], c[(1, 0, 0)], fx)
    x10 = lerp(c[(0, 1, 0)], c[(1, 1, 0)], fx)
    x01 = lerp(c[(0, 0, 1)], c[(1, 0, 1)], fx)
    x11 = lerp(c[(0, 1, 1)], c[(1, 1, 1)], fx)
    return lerp(lerp(x00, x10, fy), lerp(x01, x11, fy), fz)


def texture(point: np.ndarray, normal: np.ndarray, strength: float = 0.30,
            salt: int = 0) -> np.ndarray:
    """A multiplier around 1.0 that gives a flat plane something to paint.

    Three octaves of world-space value noise plus a directional GRAIN that runs
    along the surface's longest in-plane axis - a bench reads as wood, a cabinet
    door as brushed metal - and a sparse SCRATCH pass that puts a few hard dark
    lines where a Lambert plane had none.

    Coarse on purpose: the finest octave is 3.5 cm, because a brushstroke in this
    room is about 2 cm of paint and a texture finer than the brush is a texture the
    painter cannot carry. Detail the painter cannot hold is a lie about the
    picture, not sharpness.
    """
    p = np.asarray(point, dtype=np.float64)
    nrm = np.asarray(normal, dtype=np.float64)
    n = value_noise(p, 0.135, salt + 1) - 0.5
    n = n + 0.55 * (value_noise(p, 0.062, salt + 2) - 0.5)
    n = n + 0.30 * (value_noise(p, 0.035, salt + 3) - 0.5)
    n = n / 1.85

    # grain: squash the lattice hard along the two axes the surface runs in, and
    # leave it coarse along the normal, so the noise becomes stripes IN the plane.
    ax = np.argmin(np.abs(nrm), axis=-1)
    stretch = np.full(p.shape, 1.0)
    np.put_along_axis(stretch, ax[..., None], 14.0, axis=-1)
    grain = value_noise(p * stretch, 0.34, salt + 4) - 0.5

    # scratches: the top few percent of a very stretched noise, driven negative
    s = value_noise(p * stretch, 0.11, salt + 7)
    scratch = -np.clip((s - 0.90) / 0.10, 0.0, 1.0)

    v = 1.0 + strength * (n + 0.85 * grain) + 0.80 * strength * scratch
    return np.clip(v, 0.25, 1.75)


# ------------------------------------------------------------------- the stages

class ShadedStage(Stage):
    """`Stage` with contact shadow, ambient occlusion and texture BAKED IN.

    Everything is folded into `gbuffer()["albedo"]`; `shade()` is inherited from
    `Stage` and is never overridden, never wrapped, never called differently. Read
    that as the design constraint it is: the ruler must not move while the picture
    is being sharpened, or the sharpening cannot be believed.
    """

    def __init__(self, *a, ao_rays: int = 12, ao_reach: float = 0.55,
                 ao_strength: float = 0.85, shadow_strength: float = 0.75,
                 texture_strength: float = 0.30, texture_salt: int = 0,
                 light_pos=None, blockers=None, softness: float = 0.0,
                 shadow_samples: int = 1, **kw) -> None:
        super().__init__(*a, **kw)
        self.ao_rays = int(ao_rays)
        self.ao_reach = float(ao_reach)
        self.ao_strength = float(ao_strength)
        self.shadow_strength = float(shadow_strength)
        self.texture_strength = float(texture_strength)
        self.texture_salt = int(texture_salt)
        self.light_pos = None if light_pos is None else np.asarray(light_pos, float)
        self.blockers = blockers
        self.softness = float(softness)
        self.shadow_samples = int(shadow_samples)

    def occlude(self, g: dict) -> np.ndarray:
        """The (H,W) multiplier this stage bakes into albedo. Exposed for tests."""
        m = g["mask"]
        pt = g["point"][m]
        nr = g["normal"][m]
        v = np.ones(pt.shape[0])
        if self.shadow_strength > 0:
            if self.light_pos is not None:
                lit = shadow_point(self, pt, nr, self.light_pos,
                                   blockers=self.blockers,
                                   softness=self.softness,
                                   samples=self.shadow_samples)
            else:
                lit = shadow(self, pt, nr, blockers=self.blockers)
            v = v * (1.0 - self.shadow_strength * (1.0 - lit))
        if self.ao_strength > 0 and self.ao_rays > 0:
            ao = ambient_occlusion(self, pt, nr, self.ao_rays, self.ao_reach)
            v = v * (1.0 - self.ao_strength * (1.0 - ao))
        if self.texture_strength > 0:
            v = v * texture(pt, nr, self.texture_strength, self.texture_salt)
        out = np.ones(m.shape)
        out[m] = v
        return out

    def gbuffer(self, cam):
        # CACHE. `godot_gate.one_pair` asks for the same two g-buffers five or six
        # times per pose pair (truth, flow a, flow b, both scatters), and at
        # 1920x1080 the occlusion pass is 2 million points x 13 rays x 105 boxes.
        # Without this the gate takes an hour to say what it says in four minutes,
        # and the answer is identical because the scene does not move.
        key = (tuple(np.round(cam.eye, 9)), tuple(np.round(cam.target, 9)),
               cam.width, cam.height, round(float(cam.fov_deg), 9))
        cache = self.__dict__.setdefault("_gcache", {})
        if key in cache:
            return cache[key]
        g = super().gbuffer(cam)
        g["albedo"] = np.clip(g["albedo"] * self.occlude(g)[..., None], 0.0, 1.0)
        if len(cache) >= 3:                       # one_pair only ever alternates two
            cache.pop(next(iter(cache)))
        cache[key] = g
        return g
