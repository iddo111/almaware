"""TZELEM / צלם — THE STAGE: a world we own completely, so the ruler cannot lie.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

לזכרה של עלמה ז"ל.

GATE 0 — DATA PROVENANCE, settled here and provable by reading this file:
every pixel, every depth, every normal and every optical-flow vector in TZELEM is
BORN FROM THIS GEOMETRY. Nothing is scraped, nothing is downloaded, nothing is
estimated. That matters for one reason only: the organ's ruler is temporal
coherence measured against optical flow, and optical flow is the single number
the whole computer-vision field cannot obtain exactly. We can — because we own
the scene. `flow()` below is not an estimator. It is the truth.

The stage is deliberately poor: axis-aligned boxes and a ground plane, one
directional light, Lambert. A rich scene would hide a weak organ.

Numpy only. No torch on the PC (D:\\CLAUDE\\CLAUDE.md).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

# --------------------------------------------------------------- geometry

@dataclass
class Box:
    """An axis-aligned box. lo/hi are world-space corners."""
    lo: np.ndarray
    hi: np.ndarray
    albedo: np.ndarray            # rgb in 0..1

    def __post_init__(self) -> None:
        self.lo = np.asarray(self.lo, dtype=np.float64)
        self.hi = np.asarray(self.hi, dtype=np.float64)
        self.albedo = np.asarray(self.albedo, dtype=np.float64)


@dataclass
class Camera:
    """A pinhole camera. `eye` looks at `target`, `up` is the world up hint."""
    eye: np.ndarray
    target: np.ndarray
    up: np.ndarray = field(default_factory=lambda: np.array([0.0, 1.0, 0.0]))
    fov_deg: float = 50.0
    width: int = 160
    height: int = 120

    def __post_init__(self) -> None:
        self.eye = np.asarray(self.eye, dtype=np.float64)
        self.target = np.asarray(self.target, dtype=np.float64)
        self.up = np.asarray(self.up, dtype=np.float64)

    # -- the camera basis: forward / right / true-up
    def basis(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        f = self.target - self.eye
        f = f / np.linalg.norm(f)
        r = np.cross(f, self.up)
        r = r / np.linalg.norm(r)
        u = np.cross(r, f)
        return f, r, u

    def rays(self) -> np.ndarray:
        """Unit direction for every pixel. Shape (H, W, 3), pixel centres."""
        f, r, u = self.basis()
        aspect = self.width / self.height
        half = np.tan(np.radians(self.fov_deg) * 0.5)
        xs = (np.arange(self.width) + 0.5) / self.width * 2.0 - 1.0
        ys = 1.0 - (np.arange(self.height) + 0.5) / self.height * 2.0
        gx, gy = np.meshgrid(xs, ys)
        d = (f[None, None, :]
             + (gx * half * aspect)[..., None] * r[None, None, :]
             + (gy * half)[..., None] * u[None, None, :])
        return d / np.linalg.norm(d, axis=2, keepdims=True)

    def project(self, p: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """World points -> (x_pixel, y_pixel, depth_along_forward).

        p is (..., 3). Points behind the camera come back with depth <= 0 and
        their pixel coordinates are meaningless — callers must mask on depth.
        """
        f, r, u = self.basis()
        v = np.asarray(p, dtype=np.float64) - self.eye
        z = v @ f
        with np.errstate(divide="ignore", invalid="ignore"):
            xc = (v @ r) / z
            yc = (v @ u) / z
        aspect = self.width / self.height
        half = np.tan(np.radians(self.fov_deg) * 0.5)
        px = ((xc / (half * aspect)) * 0.5 + 0.5) * self.width - 0.5
        py = (0.5 - (yc / half) * 0.5) * self.height - 0.5
        return px, py, z


# --------------------------------------------------------------- the scene

class Stage:
    """A room: a ground plane and a handful of boxes, plus one light."""

    def __init__(self, boxes: list[Box] | None = None,
                 ground_albedo=(0.62, 0.60, 0.55),
                 light_dir=(-0.4, -1.0, -0.35),
                 ambient: float = 0.28) -> None:
        self.boxes = boxes if boxes is not None else default_boxes()
        self.ground_albedo = np.asarray(ground_albedo, dtype=np.float64)
        d = np.asarray(light_dir, dtype=np.float64)
        self.light_dir = d / np.linalg.norm(d)
        self.ambient = float(ambient)

    # -- ray casting ------------------------------------------------------

    def _hit_boxes(self, o: np.ndarray, d: np.ndarray):
        """Slab test against every box. Returns (t, idx) with t=inf where missed."""
        shape = d.shape[:-1]
        best_t = np.full(shape, np.inf)
        best_i = np.full(shape, -1, dtype=np.int64)
        inv = np.divide(1.0, d, out=np.full_like(d, np.inf), where=d != 0)
        for i, b in enumerate(self.boxes):
            t0 = (b.lo - o) * inv
            t1 = (b.hi - o) * inv
            tmin = np.maximum(np.minimum(t0, t1).max(axis=-1), 0.0)
            tmax = np.minimum(np.maximum(t0, t1), np.inf).min(axis=-1)
            hit = (tmax >= tmin) & (tmax > 0.0)
            closer = hit & (tmin < best_t)
            best_t = np.where(closer, tmin, best_t)
            best_i = np.where(closer, i, best_i)
        return best_t, best_i

    def _box_normal(self, p: np.ndarray, idx: np.ndarray) -> np.ndarray:
        """Face normal from which slab the point sits on. idx < 0 -> zeros."""
        n = np.zeros(p.shape, dtype=np.float64)
        for i, b in enumerate(self.boxes):
            m = idx == i
            if not m.any():
                continue
            q = p[m]
            centre = (b.lo + b.hi) * 0.5
            half = (b.hi - b.lo) * 0.5
            rel = (q - centre) / np.maximum(half, 1e-12)
            axis = np.argmax(np.abs(rel), axis=-1)
            nn = np.zeros_like(q)
            nn[np.arange(q.shape[0]), axis] = np.sign(
                rel[np.arange(q.shape[0]), axis])
            n[m] = nn
        return n

    def gbuffer(self, cam: Camera) -> dict[str, np.ndarray]:
        """The whole truth of one view: depth, world point, normal, albedo, mask.

        This is exactly what Godot's G-buffer will hand us later — built here in
        numpy first, so gate 1 can be proven with no engine installed.
        """
        d = cam.rays()
        o = cam.eye
        flat_d = d.reshape(-1, 3)
        t_box, i_box = self._hit_boxes(o, flat_d)

        # ground plane y = 0, hit only when looking down at it
        with np.errstate(divide="ignore", invalid="ignore"):
            t_gnd = np.where(flat_d[:, 1] < -1e-9, -o[1] / flat_d[:, 1], np.inf)
        t_gnd = np.where(t_gnd > 0, t_gnd, np.inf)

        use_gnd = t_gnd < t_box
        t = np.where(use_gnd, t_gnd, t_box)
        hit = np.isfinite(t)

        p = o + flat_d * np.where(hit, t, 0.0)[:, None]
        n = self._box_normal(p, np.where(use_gnd, -1, i_box))
        n[use_gnd] = np.array([0.0, 1.0, 0.0])

        alb = np.zeros_like(p)
        alb[use_gnd] = self.ground_albedo
        for i, b in enumerate(self.boxes):
            m = (~use_gnd) & (i_box == i)
            alb[m] = b.albedo

        # a checker on the ground so a flat-colour cheat cannot score
        if use_gnd.any():
            q = p[use_gnd]
            chk = ((np.floor(q[:, 0]) + np.floor(q[:, 2])) % 2 == 0)
            alb[use_gnd] = np.where(chk[:, None], self.ground_albedo * 1.25,
                                    self.ground_albedo * 0.72)

        shp = (cam.height, cam.width)
        return {
            "depth": np.where(hit, t, np.inf).reshape(shp),
            "point": p.reshape(shp + (3,)),
            "normal": n.reshape(shp + (3,)),
            "albedo": np.clip(alb, 0.0, 1.0).reshape(shp + (3,)),
            "mask": hit.reshape(shp),
        }

    def shade(self, g: dict[str, np.ndarray]) -> np.ndarray:
        """Lambert + ambient. The image TZELEM is judged against for fidelity."""
        lam = np.clip(-(g["normal"] @ self.light_dir), 0.0, 1.0)
        lit = g["albedo"] * (self.ambient + (1.0 - self.ambient) * lam[..., None])
        sky = np.array([0.82, 0.87, 0.94])
        return np.where(g["mask"][..., None], lit, sky)

    # -- the exact ruler input -------------------------------------------

    def flow(self, a: Camera, b: Camera) -> dict[str, np.ndarray]:
        """EXACT optical flow from view a to view b, plus a validity mask.

        For every pixel of a we take its world point, project it into b, and ask
        b whether that point is still the nearest surface along that ray. If it
        is not, the pixel was occluded/disoccluded and is excluded — an honest
        ruler never scores a pixel whose answer does not exist.
        """
        ga = self.gbuffer(a)
        gb = self.gbuffer(b)
        px, py, z = b.project(ga["point"])

        inside = (px >= 0) & (px <= b.width - 1) & (py >= 0) & (py <= b.height - 1)
        valid = ga["mask"] & inside & (z > 0)

        # visibility: compare the point's depth in b against b's own depth buffer
        xi = np.clip(np.rint(px), 0, b.width - 1).astype(np.int64)
        yi = np.clip(np.rint(py), 0, b.height - 1).astype(np.int64)
        seen_t = np.linalg.norm(ga["point"] - b.eye, axis=-1)
        depth_b = gb["depth"][yi, xi]
        # A point may not be BEHIND what b sees along that ray. It may be slightly in
        # front: we sample b's depth at a ROUNDED pixel, and at a silhouette the
        # neighbouring ray can hit something nearer. A 0.1% window was far tighter than
        # the depth change across one pixel of grazing ground, and it discarded 94% of
        # the image — the ruler was measuring a sliver and calling it the picture.
        visible = seen_t <= depth_b * 1.02 + 1e-3

        return {"px": px, "py": py, "valid": valid & visible,
                "gbuffer_a": ga, "gbuffer_b": gb}


def default_boxes() -> list[Box]:
    """Three blocks and a slab — enough for real occlusion and disocclusion."""
    return [
        Box([-1.6, 0.0, -0.6], [-0.6, 1.5, 0.4], [0.78, 0.30, 0.24]),
        Box([0.35, 0.0, -1.4], [1.45, 0.95, -0.3], [0.26, 0.42, 0.72]),
        Box([-0.35, 0.0, 0.9], [0.55, 2.15, 1.7], [0.90, 0.78, 0.32]),
        Box([-2.6, 0.0, 1.9], [2.6, 0.22, 2.3], [0.35, 0.55, 0.36]),
    ]


def orbit(step: float = 0.0, width: int = 160, height: int = 120,
          radius: float = 5.2) -> Camera:
    """The camera move the ruler is measured over: a slow orbit, one target."""
    ang = np.radians(-38.0 + step)
    eye = np.array([np.sin(ang) * radius, 2.35, np.cos(ang) * radius])
    return Camera(eye=eye, target=np.array([0.0, 0.75, 0.0]),
                  width=width, height=height)
