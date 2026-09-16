# -*- coding: utf-8 -*-
"""TZELEM / צלם — THE MATERIALS: what a surface IS, at the size it really is.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

לזכרה של עלמה ז"ל.

Iddo, 2026-09-06 03:12: *"תבנה את שלב 3 - חומרים"*.

STAGE 3 OF THE IMAGE PIPELINE, AND WHY IT IS THE LEVER
-------------------------------------------------------
`room.py` gives every one of the workshop's 105 boxes ONE RGB triple. A stone wall
is not one grey; it is thousands of greys that catch the light differently, and
the difference between those two sentences is most of the distance between a
blocking-out and a picture. Measured, on the one ruler, in
`_deliverables/tzelem-sharpen/README-FINDINGS.md`: turning on the *procedural*
texture multiplier moved lit Laplacian variance 326 -> 372 -> 504 at strength
0 / 0.3 / 0.6, all at 100% coverage — more than the entire shadow + ambient
occlusion pass bought (10.1 -> 9.1 soft, 43.4 -> 41.8 hard). This file is the
organ that does the same job with REAL SURFACES instead of noise.

WHAT THIS FILE IS ALLOWED TO TOUCH
-----------------------------------
Nothing that already exists. `stage.Stage.shade` is the fidelity ruler and does
not move (`tzelem-sharpen/freeze.py` hashes its source). `canvas.render(soft=False)`
— pass-1 ownership, one stroke per pixel — is the sharp path found on 2026-09-06
and is not regressed: this organ is consulted at PLANTING time, to decide what
colour a stroke's anchor is, and colour is still read only AFTER ownership is
decided, exactly as `palette.py` requires. A material cannot move an edge.

TRIPLANAR, AND WHY IT IS NOT A COMPROMISE HERE
-----------------------------------------------
The workshop's 105 boxes have no UV coordinates. Neither do the photogrammetric
meshes in `_deliverables/room3d/objects/` — map-anything emits vertices and faces,
nothing else. Getting UVs means running a parameteriser, owning it forever, and
accepting its seams. Triplanar needs none: sample the texture three times using
the world XZ / XY / YZ coordinates and blend by the normal squared.

Three properties make it the right answer rather than the cheap one:

  1. **It is already in millimetres.** The lookup coordinate IS the world position,
     so a material whose texel is 0.1677 mm wide lands at 0.1677 mm wide on every
     surface in the room, with no per-object tuning. Iddo's scene is calibrated at
     403.0376 mm per model unit (`room3d/scale.json`, 0.489 mm residual) and the
     workshop is authored directly in metres, so both worlds are placed at true
     size by the same line of code.
  2. **On an axis-aligned box it is FREE and EXACT.** The blend weights are the
     squared components of the face normal, which on an axis-aligned face is
     (1,0,0) — one plane, weight 1, the other two weight 0. `triplanar()` skips any
     plane under `WEIGHT_EPS`, so 105 axis-aligned boxes cost ONE sample per
     anchor, not three. Only the photogrammetric meshes pay the full price.
  3. **No seams to hide.** A wrapped 2-D projection across a box corner does not
     tear, because the projection changes with the normal, not with an atlas.

Its one real cost is stretching on surfaces at 45 degrees to every axis, where two
planes blend. That is a known triplanar artefact, it is bounded, and on this scene
it applies to nothing.

THE FORMAT — .tzm, deliberately dumb, and 100% ours
----------------------------------------------------
Written in the idiom `gbuffer.py` set: no PNG, no EXR, no OpenCV. A material is
six arrays and one number.

    <name>.tzm    magic "TZMAT01\\0", uint32 size, uint32 flags, float32 mm_per_texel,
                  then, little-endian, in this order:
                      uint8 albedo    [S*S*3]   sRGB DETAIL, mean-normalised
                      uint8 normal    [S*S*3]   tangent space, 128 = zero slope
                      uint8 roughness [S*S]                        (flag bit 0)
                      uint8 metallic  [S*S]                        (flag bit 1)
                      uint8 ao        [S*S]                        (flag bit 2)
                      uint8 height    [S*S]                        (flag bit 3)
    <name>.json   the provenance: source frame, crop, licence, what was measured
                  and what was derived, physical size in mm.

**Why uint8 and not the float32 `gbuffer.py` uses.** A g-buffer holds depths and
world positions, where 8 bits would be a catastrophe. A material holds reflectance
and a slope, both of which every renderer on earth ships at 8 bits, and the choice
is what keeps a 512-texel six-channel set at 1.6 MB instead of 6.3 MB. The one
place 8 bits would have hurt — quantising a height field before differentiating it
into a normal — does not arise, because `harvest.py` computes the normal from the
float height and stores the RESULT.

Numpy only. No torch on the PC (D:\\CLAUDE\\CLAUDE.md). PIL is used by the
harvester to open Iddo's JPEGs and by nothing in this file.
"""
from __future__ import annotations

import json
import os
import struct
from dataclasses import dataclass, field

import numpy as np

MAGIC = b"TZMAT01\0"
HAS_ROUGH, HAS_METAL, HAS_AO, HAS_HEIGHT = 1, 2, 4, 8
WEIGHT_EPS = 1e-3          # a triplanar plane under this weight is not sampled


# ------------------------------------------------------------------ the material

@dataclass
class Material:
    """Six maps and a physical size. The size is the half that usually goes missing."""
    name: str
    kind: str
    albedo: np.ndarray            # (S,S,3) uint8, sRGB, mean-normalised DETAIL
    normal: np.ndarray            # (S,S,3) uint8, tangent space
    roughness: np.ndarray         # (S,S)   uint8
    metallic: np.ndarray          # (S,S)   uint8
    ao: np.ndarray                # (S,S)   uint8
    height: np.ndarray            # (S,S)   uint8
    mm_per_texel: float
    meta: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        s = self.albedo.shape[0]
        if self.albedo.shape != (s, s, 3):
            raise ValueError(f"albedo must be square (S,S,3), got {self.albedo.shape}")
        for nm in ("normal",):
            if getattr(self, nm).shape != (s, s, 3):
                raise ValueError(f"{nm} must be (S,S,3), got {getattr(self, nm).shape}")
        for nm in ("roughness", "metallic", "ao", "height"):
            if getattr(self, nm).shape != (s, s):
                raise ValueError(f"{nm} must be (S,S), got {getattr(self, nm).shape}")

    @property
    def size(self) -> int:
        return int(self.albedo.shape[0])

    @property
    def physical_size_mm(self) -> float:
        return self.mm_per_texel * self.size


def write_tzm(path_stem: str, m: Material) -> str:
    """Write <stem>.tzm and <stem>.json. Returns the .tzm path."""
    flags = HAS_ROUGH | HAS_METAL | HAS_AO | HAS_HEIGHT
    blob = bytearray(MAGIC + struct.pack("<IIf", m.size, flags, m.mm_per_texel))
    for a in (m.albedo, m.normal, m.roughness, m.metallic, m.ao, m.height):
        blob += np.ascontiguousarray(a, dtype=np.uint8).tobytes()
    p = path_stem + ".tzm"
    with open(p, "wb") as fh:
        fh.write(blob)
    with open(path_stem + ".json", "w", encoding="utf-8") as fh:
        json.dump({"name": m.name, "kind": m.kind, "size": m.size,
                   "mm_per_texel": m.mm_per_texel,
                   "physical_size_mm": m.physical_size_mm, **m.meta},
                  fh, indent=1, ensure_ascii=False)
    return p


def load_tzm(path_stem: str) -> Material:
    """Read a material back. Byte-for-byte the inverse of `write_tzm`."""
    stem = path_stem[:-4] if path_stem.endswith(".tzm") else path_stem
    with open(stem + ".tzm", "rb") as fh:
        raw = fh.read()
    if raw[:8] != MAGIC:
        raise ValueError(f"{stem}.tzm is not a TZELEM material (magic {raw[:8]!r})")
    size, flags, mm = struct.unpack("<IIf", raw[8:20])
    off = 20

    def take(shape):
        nonlocal off
        n = int(np.prod(shape))
        a = np.frombuffer(raw, dtype=np.uint8, count=n, offset=off).reshape(shape)
        off += n
        return a.copy()

    alb = take((size, size, 3))
    nrm = take((size, size, 3))
    rough = take((size, size)) if flags & HAS_ROUGH else np.full((size, size), 128, np.uint8)
    metal = take((size, size)) if flags & HAS_METAL else np.zeros((size, size), np.uint8)
    ao = take((size, size)) if flags & HAS_AO else np.full((size, size), 255, np.uint8)
    hgt = take((size, size)) if flags & HAS_HEIGHT else np.full((size, size), 128, np.uint8)
    meta = {}
    if os.path.exists(stem + ".json"):
        with open(stem + ".json", encoding="utf-8") as fh:
            meta = json.load(fh)
    return Material(name=meta.get("name", os.path.basename(stem)),
                    kind=meta.get("kind", "?"), albedo=alb, normal=nrm,
                    roughness=rough, metallic=metal, ao=ao, height=hgt,
                    mm_per_texel=float(mm), meta=meta)


# ------------------------------------------------------------- triplanar sampling

def _wrap_bilinear(tex: np.ndarray, u: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Bilinear sample of a WRAPPING texture. u,v in texels. tex is (S,S[,C])."""
    s = tex.shape[0]
    u0 = np.floor(u).astype(np.int64)
    v0 = np.floor(v).astype(np.int64)
    fu = (u - u0)[..., None] if tex.ndim == 3 else (u - u0)
    fv = (v - v0)[..., None] if tex.ndim == 3 else (v - v0)
    u0 %= s
    v0 %= s
    u1 = (u0 + 1) % s
    v1 = (v0 + 1) % s
    a = tex[v0, u0]
    b = tex[v0, u1]
    c = tex[v1, u0]
    d = tex[v1, u1]
    return (a * (1 - fu) * (1 - fv) + b * fu * (1 - fv)
            + c * (1 - fu) * fv + d * fu * fv)


# the three projection planes: (which world axes give (u, v), which axis is the normal)
_PLANES = ((1, 2, 0), (0, 2, 1), (0, 1, 2))          # YZ / XZ / XY


def _pyramid(tex: np.ndarray) -> list[np.ndarray]:
    """Box mip chain, level 0 = full size. Wrapping is exact: sizes are powers of 2."""
    a = tex.astype(np.float64)
    out = [a]
    while a.shape[0] > 1:
        a = 0.25 * (a[0::2, 0::2] + a[1::2, 0::2] + a[0::2, 1::2] + a[1::2, 1::2])
        out.append(a)
    return out


def mips(m: Material) -> dict[str, list[np.ndarray]]:
    """Cached mip chains for every map of a material. Built once, on first use."""
    got = m.__dict__.get("_mips")
    if got is not None:
        return got
    got = {
        "albedo": _pyramid(m.albedo.astype(np.float64) / 255.0),
        "normal": _pyramid(m.normal.astype(np.float64) / 127.5 - 1.0),
        "roughness": _pyramid(m.roughness.astype(np.float64) / 255.0),
        "metallic": _pyramid(m.metallic.astype(np.float64) / 255.0),
        "ao": _pyramid(m.ao.astype(np.float64) / 255.0),
        "height": _pyramid(m.height.astype(np.float64) / 255.0),
    }
    m.__dict__["_mips"] = got
    return got


# ---------------------------------------------------------------- TZ-5, 2026-09-06
# IS THIS ORGAN IN A PICTURE TZELEM ACTUALLY MAKES? No, and it must not be silent
# about that. `material.py` is the largest and newest module in the folder and its
# only importer anywhere is its own test; `night.py`, `godot_gate.py`, `gate2.py` and
# `oneroom/paint.py` -- everything that renders -- import neither it nor
# `occlusion.py`. The measured wins (+78% Laplacian variance here, +300% sharpness
# there) reach no picture. `tests/test_wiring.py` asserts this declaration against the
# real import graph, so it can never quietly drift from the truth in either direction.
#
# It is NOT dead code and must not be deleted: `_deliverables/tzelem-materials/`
# renders with it through `MaterialStage` every time the A/B or the materials gate is
# run, and that copy is byte-identical to this one.
RENDER_PATH_WIRED = False
RENDER_PATH_NOTE = (
    "MaterialStage is a MIXIN and it keys on BOX ids. It can dress room.RoomStage "
    "(proved by _deliverables/tzelem-materials/gate_mat.py) and it CANNOT dress "
    "meshstage.MeshStage, which is a triangle soup whose g-buffer has no 'box' key "
    "and whose boxes list is empty -- so night.py's subject cannot wear a material "
    "until a face->material map exists. Wiring the room path is an art decision with "
    "a measured cost (gate-mat.log: the BLANK fidelity headroom fell x2.24 -> x1.58 "
    "-> x1.44 as materials went on and up) and is Iddo's call, not this file's.")

FLAT_TEXELS = 8       # below this an 'active' material is a constant, not a texture
# TZ-7: how much collapse a run may carry and still be called MATERIALS ON.
FLAT_FRAC_BAR = 0.25


def effective_map_px(m: Material, footprint_mm: float) -> int:
    """HOW MANY TEXELS OF `m` SURVIVE AT THIS BRUSH SIZE. 1 means: none.

    TZ-7 (2026-09-06). `lod_for` clips to the top of the mip pyramid and says nothing,
    so at the gate's own 42 mm brush a material collapses to a 1x1 or 2x2 map -- a
    constant -- while the pipeline goes on reporting it as an active material at 100%
    coverage. Measured at 42 mm: steel_brushed -> 1x1, sampled detail std 0.001578
    about a mean of 0.9737 (a flat multiplier of ~1.0, i.e. literally nothing);
    plastic_black -> 1x1; wood_polished -> 2x2; only floor_vinyl (16x16, std 0.1021)
    carries structure. The number anyone actually needs is not "is a material
    assigned" but "does it reach the picture".
    """
    lod = lod_for(m, footprint_mm)
    return int(max(1, m.size // (2 ** int(np.floor(lod)))))


def lod_for(m: Material, footprint_mm: float) -> float:
    """WHICH LEVEL A BRUSH OF THIS SIZE CAN ACTUALLY CARRY.

    THE MEASUREMENT THAT PUT THIS FUNCTION HERE, 2026-09-06. The first A/B ran
    without it and reported lit Laplacian variance 329 -> 1524, a 4.6x win. I
    opened the picture. It was a mosaic of randomly coloured dabs — not wood, not
    a wall, NOISE. A brushstroke in the workshop is 42 mm across and
    `wood_polished` has a 0.168 mm texel, so every stroke was point-sampling ONE
    texel out of a patch 250 texels wide and neighbouring strokes were landing on
    unrelated grain. The ruler applauded because aliasing is high-frequency, and
    high frequency is all a Laplacian can see.

    `tzelem-sharpen/README-FINDINGS.md` had already written the rule down for the
    procedural texture — *"a texture finer than the brush is a texture the painter
    cannot carry"* — and the same rule binds a photograph. So the sample is taken
    from the mip level whose texel matches the stroke's footprint, which is
    ordinary texture filtering and is also the honest thing.

    The uncomfortable consequence, stated rather than hidden: a material harvested
    at 0.168 mm/texel and 85.8 mm across is, at a 42 mm brush, TWO TEXELS WIDE.
    It cannot help this render at this brush no matter how good the photograph is.
    A material has a SCALE BAND, and it has to be harvested inside the band the
    brush can carry.
    """
    n = int(np.log2(m.size))
    return float(np.clip(np.log2(max(footprint_mm, 1e-6) / m.mm_per_texel),
                         0.0, n))


def triplanar(m: Material, point_mm: np.ndarray, normal: np.ndarray,
              sharpness: float = 4.0,
              footprint_mm: float | None = None) -> dict[str, np.ndarray]:
    """Sample every map of `m` at world points, blended by the surface normal.

    `point_mm` is (N,3) in MILLIMETRES — the caller converts once, so this organ
    never has to guess whether a world unit is a metre, a model unit or an inch.
    `normal` is (N,3) unit.

    Returns float arrays: albedo (N,3) in 0..1 sRGB-decoded to linear-ish DETAIL
    around 1.0, normal (N,3) WORLD-space perturbed, roughness/metallic/ao/height
    (N,).
    """
    n = np.asarray(normal, dtype=np.float64)
    w = np.abs(n) ** sharpness
    w = w / np.maximum(w.sum(axis=1, keepdims=True), 1e-12)

    # THE MIP LEVEL. The footprint is a WORLD size (a stroke's diameter), and a
    # stroke's world size does not change with the camera, so the level is one
    # number for the whole call and not one per anchor.
    py = mips(m)
    if footprint_mm is None:
        lo = hi_lv = 0
        blend = 0.0
    else:
        lod = lod_for(m, footprint_mm)
        lo = int(np.floor(lod))
        hi_lv = min(lo + 1, len(py["albedo"]) - 1)
        blend = float(lod - lo)
    texel_mm = m.mm_per_texel * (2.0 ** lo)
    p = np.asarray(point_mm, dtype=np.float64) / texel_mm            # texels

    N = len(p)
    alb = np.zeros((N, 3))
    tn = np.zeros((N, 3))
    ro = np.zeros(N)
    me = np.zeros(N)
    ao = np.zeros(N)
    hi = np.zeros(N)

    def fetch(key, u, v):
        """Trilinear: the two bracketing mip levels, blended by the fraction."""
        a = _wrap_bilinear(py[key][lo], u, v)
        if blend <= 1e-9 or hi_lv == lo:
            return a
        b = _wrap_bilinear(py[key][hi_lv], u * 0.5, v * 0.5)
        return a * (1.0 - blend) + b * blend

    for k, (ua, va, na) in enumerate(_PLANES):
        wk = w[:, k]
        sel = wk > WEIGHT_EPS
        if not sel.any():
            continue
        u = p[sel, ua]
        v = p[sel, va]
        ww = wk[sel][:, None]
        alb[sel] += ww * fetch("albedo", u, v)
        tnk = fetch("normal", u, v)                    # tangent space (x, y, z)
        # unfold the tangent normal onto THIS plane's world axes, then blend
        wn = np.zeros((int(sel.sum()), 3))
        wn[:, ua] = tnk[:, 0]
        wn[:, va] = tnk[:, 1]
        wn[:, na] = tnk[:, 2] * np.sign(n[sel, na] + 1e-30)
        tn[sel] += ww * wn
        ww1 = wk[sel]
        ro[sel] += ww1 * fetch("roughness", u, v)
        me[sel] += ww1 * fetch("metallic", u, v)
        ao[sel] += ww1 * fetch("ao", u, v)
        hi[sel] += ww1 * fetch("height", u, v)

    ln = np.linalg.norm(tn, axis=1, keepdims=True)
    tn = np.where(ln > 1e-9, tn / np.maximum(ln, 1e-12), n)
    # albedo is stored with 1.0 at mid-grey (harvest.py divides by 2 before sRGB),
    # so undo that here and hand back a multiplier around 1.0.
    alb = _srgb_to_linear(alb) * 2.0
    return {"albedo": alb, "normal": tn, "roughness": ro, "metallic": me,
            "ao": ao, "height": hi, "weights": w}


def _srgb_to_linear(x: np.ndarray) -> np.ndarray:
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


# ------------------------------------------------------------------ the library

@dataclass
class MaterialSet:
    """Which material each named surface of a scene wears, and at what tint.

    The TINT is the scene's own authored colour (`room.MAT`). The material supplies
    STRUCTURE around a mean of 1.0, so `tint * detail` keeps the room's palette
    exactly where the art direction put it and only adds what a photograph knows.
    That is also what makes the A/B measurable: mean colour does not move, so the
    Laplacian variance cannot be applauding an exposure change.
    """
    materials: dict[str, Material]
    assignment: dict[str, str]                     # scene material name -> tzm name
    default: str = ""
    scale: dict[str, float] = field(default_factory=dict)
    """PLACEMENT SIZE, and it is the one honest lever in this file.

    `scale[name] = k` places that material's pattern k times LIFE SIZE. k = 1.0 is
    the measured truth and is the default. Anything else is a deliberate departure
    from real-world scale, and it exists because of a measurement, not a
    preference: at the workshop's 42 mm brushstroke, a 0.168 mm-texel material is
    a 4x4 map (see `lod_for`) and cannot reach the picture at all. Iddo filmed his
    desk from 300 mm; a room seen from 3 m needs features in the 10-500 mm band.
    Whoever sets k above 1 must SAY SO in the report — a texture at seven times
    life size is a decision about art, not a fact about the world.
    """

    @classmethod
    def from_dir(cls, folder: str, assignment: dict[str, str],
                 default: str = "", scale: dict[str, float] | None = None
                 ) -> "MaterialSet":
        mats = {}
        for f in sorted(os.listdir(folder)):
            if f.endswith(".tzm"):
                m = load_tzm(os.path.join(folder, f))
                mats[m.name] = m
        missing = {v for v in assignment.values()} - set(mats)
        if missing:
            raise KeyError(f"assignment names materials that are not in {folder}: "
                           f"{sorted(missing)}")
        return cls(materials=mats, assignment=assignment, default=default,
                   scale=dict(scale or {}))

    def for_surface(self, scene_mat: str) -> Material | None:
        nm = self.assignment.get(scene_mat, self.default)
        return self.materials.get(nm) if nm else None

    # -------------------------------------------------------------- the answer

    def surfaces(self, point_m: np.ndarray, normal: np.ndarray,
                 scene_mat: np.ndarray, mat_names: list[str],
                 world_scale_mm: float = 1000.0,
                 normal_strength: float = 1.0,
                 footprint_mm: float | None = None) -> dict[str, np.ndarray]:
        """Sample every material once per surface group. No lighting here.

        `scene_mat` is an int32 array indexing `mat_names`, not an array of
        strings: at 1.2 million anchors an object-dtype `np.unique` is minutes and
        an int one is milliseconds.
        """
        pt = np.asarray(point_m, dtype=np.float64)
        n_geo = np.asarray(normal, dtype=np.float64)
        ids = np.asarray(scene_mat, dtype=np.int64)

        detail = np.ones_like(pt)
        n_sh = n_geo.copy()
        rough = np.full(len(pt), 0.6)
        metal = np.zeros(len(pt))
        mao = np.ones(len(pt))
        covered = np.zeros(len(pt), dtype=bool)
        # TZ-7: an anchor whose material has collapsed to fewer than FLAT_TEXELS
        # texels at this brush is wearing a CONSTANT, not a texture. It still counts
        # as `covered`, which is why `material_coverage_frac: 1.0` was true and
        # meaningless at the same time.
        flat = np.zeros(len(pt), dtype=bool)

        for k in np.unique(ids):
            m = self.for_surface(mat_names[int(k)])
            if m is None:
                continue
            sel = ids == k
            mult = float(self.scale.get(m.name, 1.0))
            s = triplanar(m, pt[sel] * (world_scale_mm / mult), n_geo[sel],
                          footprint_mm=None if footprint_mm is None
                          else footprint_mm / mult)
            detail[sel] = s["albedo"]
            nn = n_geo[sel] + normal_strength * (s["normal"] - n_geo[sel])
            nn = nn / np.maximum(np.linalg.norm(nn, axis=1, keepdims=True), 1e-12)
            n_sh[sel] = nn
            rough[sel] = s["roughness"]
            metal[sel] = s["metallic"]
            mao[sel] = s["ao"]
            covered[sel] = True
            if footprint_mm is not None:
                eff = effective_map_px(m, footprint_mm / mult)
                if eff < FLAT_TEXELS:
                    flat[sel] = True
        n_pt = max(len(pt), 1)
        return {"detail": detail, "normal": n_sh, "roughness": rough,
                "metallic": metal, "ao": mao, "covered": covered,
                "flat": flat, "flat_frac": float(flat.sum()) / n_pt,
                "covered_frac": float(covered.sum()) / n_pt}

    def shade(self, point_m: np.ndarray, normal: np.ndarray, tint: np.ndarray,
              scene_mat: np.ndarray, mat_names: list[str],
              light_dir: np.ndarray, ambient: float,
              eye: np.ndarray | None = None, world_scale_mm: float = 1000.0,
              spec_strength: float = 0.35, normal_strength: float = 1.0,
              footprint_mm: float | None = None) -> dict[str, np.ndarray]:
        """THE ORGAN'S ONE QUESTION: what colour is this point, seen from there?

        point_m       (N,3) world position, in the scene's own units
        normal        (N,3) unit geometric normal
        tint          (N,3) the scene's authored albedo for that point
        scene_mat     (N,)  int index into `mat_names`
        world_scale_mm      how many millimetres ONE world unit is. 1000 for the
                            workshop (authored in metres); 403.0376 for the
                            photogrammetric room (`room3d/scale.json`).

        Returns the shaded colour and every intermediate, so a caller can measure
        which part did the work instead of taking the pretty picture on trust.
        """
        pt = np.asarray(point_m, dtype=np.float64)
        n_geo = np.asarray(normal, dtype=np.float64)
        ld = np.asarray(light_dir, dtype=np.float64)
        ld = ld / np.linalg.norm(ld)
        to_light = -ld

        surf = self.surfaces(pt, n_geo, scene_mat, mat_names,
                             world_scale_mm=world_scale_mm,
                             normal_strength=normal_strength,
                             footprint_mm=footprint_mm)
        detail, n_sh = surf["detail"], surf["normal"]
        rough, metal, mao = surf["roughness"], surf["metallic"], surf["ao"]

        alb = np.clip(np.asarray(tint, dtype=np.float64) * detail, 0.0, 1.0)
        lam = np.clip(n_sh @ to_light, 0.0, 1.0)
        diffuse = alb * (ambient + (1.0 - ambient) * lam[:, None]) * mao[:, None]

        spec = np.zeros_like(diffuse)
        if eye is not None and spec_strength > 0:
            v = np.asarray(eye, dtype=np.float64)[None, :] - pt
            v = v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-12)
            h = to_light[None, :] + v
            h = h / np.maximum(np.linalg.norm(h, axis=1, keepdims=True), 1e-12)
            ndh = np.clip(np.einsum("ij,ij->i", n_sh, h), 0.0, 1.0)
            # Blinn-Phong with the exponent read off roughness. Not GGX: GGX needs a
            # geometry and a Fresnel term to be worth its name, and half a GGX is
            # just a slower Blinn-Phong wearing a better word.
            expo = 2.0 / np.maximum(rough, 0.02) ** 2
            f0 = 0.04 + 0.9 * metal
            # NOT `s`: that name already held the surface sample, and reusing it
            # here made `s["covered"]` at the bottom index a float array.
            lobe = (f0 * ndh ** np.clip(expo, 2.0, 512.0)) * (lam > 0)
            colour = np.where(metal[:, None] > 0.5, alb, 1.0)
            spec = spec_strength * lobe[:, None] * colour

        return {"colour": np.clip(diffuse + spec, 0.0, 1.0),
                "diffuse": diffuse, "specular": spec, "albedo": alb,
                "detail": detail, "normal": n_sh, "roughness": rough,
                "metallic": metal, "ao": mao, "lambert": lam,
                "covered": surf["covered"]}


# ------------------------------------------------------------ the engine's door

class MaterialStage:
    """A `Stage` wearing materials, baked into the G-BUFFER — never into `shade`.

    This is the same discipline `occlusion.ShadedStage` follows and for the same
    reason: **`stage.Stage.shade` is the fidelity ruler**, every gate number
    TZELEM has ever reported is an MSE against it, and editing it would silently
    delete the meaning of all of them. So a material changes what the g-buffer
    SAYS the surface is (its albedo and its normal), and the untouched `shade`
    then does exactly what it always did.

    That also keeps the painter and the ruler honest against each other:
    `anatomy.scatter` samples `stage.shade(gbuffer)` for a stroke's colour, so
    both receive the material from the same line of code and the gate stays a
    fair fight.

    Use it by MIXING it into whatever stage class you already have:

        class MatRoom(MaterialStage, room.RoomStage): pass
        st = MatRoom(room.BOXES, mset=..., mat_of_box=[...])

    `footprint_mm` is what one brushstroke covers in the world. Passing it is not
    optional if you care whether the number you get back is real: see `lod_for`.
    """

    def __init__(self, *a, mset: "MaterialSet | None" = None,
                 mat_of_box: list[str] | None = None,
                 ground_mat: str = "__ground__",
                 footprint_mm: float | None = None,
                 world_scale_mm: float = 1000.0,
                 detail_strength: float = 1.0,
                 normal_strength: float = 1.0, **kw) -> None:
        super().__init__(*a, **kw)
        self.mset = mset
        self.mat_of_box = list(mat_of_box or [])
        self.ground_mat = ground_mat
        self.footprint_mm = footprint_mm
        self.world_scale_mm = float(world_scale_mm)
        self.detail_strength = float(detail_strength)
        self.normal_strength = float(normal_strength)

    def _box_ids(self, cam, g):
        """Which box each pixel hit. Uses the subclass's own `box` if it has one.

        TZ-5 (2026-09-06): mixed into a stage with no boxes and no `box` channel --
        `meshstage.MeshStage`, which is what night.py renders -- the fallback below
        returns -1 everywhere and the whole subject silently wears the GROUND
        material. A copy of this file sitting in the render folder was already being
        mistaken for a connection; a wrong picture with no complaint would have made
        that worse. So it refuses by name instead.
        """
        if "box" in g:
            return g["box"]
        if not len(getattr(self, "boxes", []) or []):
            raise TypeError(
                "MaterialStage was mixed into a stage that has no boxes and no 'box' "
                "channel in its g-buffer (e.g. MeshStage, a triangle soup). Every "
                "pixel would silently be given the ground material. Give the stage a "
                "face->material map first.")
        d = cam.rays().reshape(-1, 3)
        _t, i_box = self._hit_boxes(cam.eye, d)
        with np.errstate(divide="ignore", invalid="ignore"):
            t_gnd = np.where(d[:, 1] < -1e-9, -cam.eye[1] / d[:, 1], np.inf)
        return np.where(t_gnd < _t, -1, i_box).reshape(g["depth"].shape)

    def gbuffer(self, cam):
        key = (tuple(np.round(cam.eye, 9)), tuple(np.round(cam.target, 9)),
               cam.width, cam.height, round(float(cam.fov_deg), 9))
        cache = self.__dict__.setdefault("_mcache", {})
        if key in cache:
            return cache[key]
        g = super().gbuffer(cam)
        if self.mset is not None:
            bx = self._box_ids(cam, g)
            m = g["mask"]
            names = [self.ground_mat] + list(self.mat_of_box)
            ids = np.where(bx[m] < 0, 0, bx[m] + 1)
            s = self.mset.surfaces(g["point"][m], g["normal"][m], ids, names,
                                   world_scale_mm=self.world_scale_mm,
                                   normal_strength=self.normal_strength,
                                   footprint_mm=self.footprint_mm)
            alb = g["albedo"].copy()
            det = 1.0 + self.detail_strength * (s["detail"] - 1.0)
            alb[m] = np.clip(g["albedo"][m] * det * s["ao"][:, None], 0.0, 1.0)
            g = dict(g)
            g["albedo"] = alb
            if self.normal_strength > 0:
                nrm = g["normal"].copy()
                nrm[m] = s["normal"]
                g["normal"] = nrm
        if len(cache) >= 3:
            cache.pop(next(iter(cache)))
        cache[key] = g
        return g
