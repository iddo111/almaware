"""TZELEM / צלם — A STAGE MADE OF TRIANGLES.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

`stage.py` casts rays at boxes because gate 1 had to be provable with no engine
installed. But ERAN's own modeller, KAV, does not speak boxes — it says TRIANGLES,
and Godot will hand over triangles too. So this is the same Stage contract
(`gbuffer`, `shade`, and the inherited exact `flow`) over an arbitrary triangle
soup, with Moller-Trumbore doing the intersection.

It is the piece that lets the two organs born tonight look at each other:

    KAV says a shape  ->  TZELEM paints it

and it is the same piece Godot geometry will arrive through. Nothing here is a
demo scaffold.

Numpy only. Brute force over all triangles per ray batch — correct first, and a
few thousand faces is well within what that affords.
"""
from __future__ import annotations

import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from stage import Stage      # noqa: E402  (for shade/flow, and to BE a Stage)

EPS = 1e-9


class MeshStage(Stage):
    """A world that is a bag of triangles."""

    def __init__(self, tris: np.ndarray, albedo=(0.72, 0.68, 0.60),
                 light_dir=(-0.4, -1.0, -0.35), ambient: float = 0.28,
                 two_sided: bool = True, face_albedo: np.ndarray | None = None) -> None:
        super().__init__(boxes=[], ground_albedo=albedo, light_dir=light_dir,
                         ambient=ambient)
        self.tris = np.asarray(tris, dtype=np.float64)
        if self.tris.ndim != 3 or self.tris.shape[1:] != (3, 3):
            raise ValueError(f"triangles must be (F,3,3), got {self.tris.shape}")
        self.albedo = np.asarray(albedo, dtype=np.float64)
        # One colour for the whole soup is right for a single KAV solid, but a real
        # subject is several objects on a ground. face_albedo gives each triangle its
        # own material without inventing a scene graph we do not need yet.
        self.face_albedo = (None if face_albedo is None
                            else np.asarray(face_albedo, dtype=np.float64))
        if self.face_albedo is not None and self.face_albedo.shape != self.tris.shape[:1] + (3,):
            raise ValueError("face_albedo must be (F,3)")
        # A generated mesh has no reason to be consistently wound, and a renderer
        # that culls back faces on one would show holes that are not in the shape.
        self.two_sided = bool(two_sided)
        self.v0 = self.tris[:, 0, :]
        self.e1 = self.tris[:, 1, :] - self.v0
        self.e2 = self.tris[:, 2, :] - self.v0
        n = np.cross(self.e1, self.e2)
        ln = np.linalg.norm(n, axis=1, keepdims=True)
        self.face_n = n / np.maximum(ln, EPS)
        self.area = ln[:, 0] * 0.5

    # -- Moller-Trumbore, every ray against every triangle -----------------

    def _cast(self, o: np.ndarray, d: np.ndarray):
        """d is (R,3). Returns (t, face_index) with inf/-1 where nothing was hit."""
        R = d.shape[0]
        best_t = np.full(R, np.inf)
        best_i = np.full(R, -1, dtype=np.int64)
        # chunk over faces so the (R,F) intermediates stay affordable
        step = max(1, int(4_000_000 / max(R, 1)))
        for a in range(0, len(self.v0), step):
            b = min(a + step, len(self.v0))
            e1, e2, v0 = self.e1[a:b], self.e2[a:b], self.v0[a:b]
            p = np.cross(d[:, None, :], e2[None, :, :])          # (R,F,3)
            det = np.einsum("fk,rfk->rf", e1, p)
            live = np.abs(det) > EPS if self.two_sided else det > EPS
            inv = np.where(live, 1.0 / np.where(live, det, 1.0), 0.0)
            tvec = o[None, None, :] - v0[None, :, :]
            u = np.einsum("rfk,rfk->rf", tvec, p) * inv
            q = np.cross(tvec, e1[None, :, :])
            v = np.einsum("rk,rfk->rf", d, q) * inv
            t = np.einsum("fk,rfk->rf", e2, q) * inv
            ok = live & (u >= -EPS) & (v >= -EPS) & (u + v <= 1.0 + EPS) & (t > 1e-6)
            t = np.where(ok, t, np.inf)
            j = np.argmin(t, axis=1)
            tm = t[np.arange(R), j]
            closer = tm < best_t
            best_t = np.where(closer, tm, best_t)
            best_i = np.where(closer, j + a, best_i)
        return best_t, best_i

    def gbuffer(self, cam) -> dict[str, np.ndarray]:
        d = cam.rays().reshape(-1, 3)
        t, i = self._cast(cam.eye, d)
        hit = np.isfinite(t)
        p = cam.eye + d * np.where(hit, t, 0.0)[:, None]
        n = np.where(hit[:, None], self.face_n[np.clip(i, 0, None)], 0.0)
        if self.two_sided:                       # face the camera, always
            n = np.where((np.einsum("rk,rk->r", n, d) > 0)[:, None], -n, n)
        if self.face_albedo is None:
            alb = np.tile(self.albedo, (len(d), 1))
        else:
            alb = np.where(hit[:, None], self.face_albedo[np.clip(i, 0, None)],
                           self.albedo)
        shp = (cam.height, cam.width)
        return {"depth": np.where(hit, t, np.inf).reshape(shp),
                "point": p.reshape(shp + (3,)),
                "normal": n.reshape(shp + (3,)),
                "albedo": alb.reshape(shp + (3,)),
                "mask": hit.reshape(shp)}


def frame(tris: np.ndarray, width: int = 480, height: int = 360,
          step_deg: float = 0.0, pad: float = 1.15, fov_deg: float = 50.0):
    """A camera that actually contains the shape, whatever size it came out.

    The distance is DERIVED, not guessed. For a bounding sphere of radius R and a
    vertical half-angle t, the sphere fits only when R/d <= sin(t), i.e. d >= R/sin(t).
    The first version used a flat 1.9*R, which is closer than the 2.37*R that a 50
    degree field actually needs, so an elongated object -- the Pongo clip, 15 x 40 x 70
    -- came out cropped at both ends. A framing constant that happens to work on cubes
    is not a framing rule.
    """
    from stage import Camera
    pts = tris.reshape(-1, 3)
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    centre = (lo + hi) * 0.5
    radius = float(np.linalg.norm(hi - lo)) * 0.5 + 1e-6
    half_v = np.radians(fov_deg) * 0.5
    half_h = np.arctan(np.tan(half_v) * (width / height))
    dist = radius / min(np.sin(half_v), np.sin(half_h)) * pad
    ang = np.radians(-38.0 + step_deg)
    eye = centre + np.array([np.sin(ang), 0.45, np.cos(ang)]) * dist
    return Camera(eye=eye, target=centre, width=width, height=height,
                  fov_deg=fov_deg)
