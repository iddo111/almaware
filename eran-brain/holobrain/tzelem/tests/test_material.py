# -*- coding: utf-8 -*-
"""
> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

WHAT THE MATERIALS ORGAN IS NOT ALLOWED TO GET WRONG.

Eight sections, each one a sentence someone could otherwise just assert:

  1  a material written to disk and read back is the SAME BYTES
  2  every map wraps: the seam has no more energy than the interior
  3  on an axis-aligned face triplanar costs ONE sample, not three
  4  the texture repeats at exactly its PHYSICAL SIZE in millimetres
  5  the same world point gives the same texel from any camera (no view leak)
  6  the normal map actually perturbs the shading normal
  7  a material CANNOT MOVE AN EDGE -- ownership is bit-identical with and
     without it, which is `palette.py`'s law extended to stage 3
  8  the metres world and the 403.0376 mm/unit world land at the same real size
  9  a material that has collapsed below the brush SAYS SO (TZ-7)

WHY THIS FILE MOVED, 2026-09-06 (TZ-6)
--------------------------------------
It used to live in the tzelem ROOT as a hand-rolled `main()` with its own `check()`
and a `sys.exit`, and `count_tests.py` runs `pytest tests -q`. So `out-night/tests.json`
reported "tzelem: 21 passed, green: true" and `night_sheet.py` printed that as the
night's coverage, while the 21 checks of the newest and largest module in the organ
were outside the count entirely -- `pytest test_material.py --collect-only` collected
ZERO. Nothing was broken; it was simply unwatched, which is the same failure
`count_tests.py`'s own docstring was written against, one level up.

The checks are run ONCE at collection and then reported one pytest test per check, so
a single failure names itself instead of hiding inside one big green test.
"""
from __future__ import annotations

import ast
import os
import sys

import numpy as np
import pytest

TZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if TZ not in sys.path:
    sys.path.insert(0, TZ)

import material as M                                       # noqa: E402

MATS = os.path.join(TZ, "mats")
_CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _CHECKS.append((name, bool(ok), detail))


def _run_all() -> None:
    names = sorted(f[:-4] for f in os.listdir(MATS) if f.endswith(".tzm"))

    # ---- 1. round trip ----------------------------------------------------
    for n in names:
        a = M.load_tzm(os.path.join(MATS, n))
        tmp = os.path.join(TZ, "out", "_rt_" + n)
        os.makedirs(os.path.dirname(tmp), exist_ok=True)
        M.write_tzm(tmp, a)
        b = M.load_tzm(tmp)
        same = all(np.array_equal(getattr(a, k), getattr(b, k))
                   for k in ("albedo", "normal", "roughness", "metallic",
                             "ao", "height"))
        same = same and a.mm_per_texel == b.mm_per_texel
        check(f"1 round-trip {n}", same)
        os.remove(tmp + ".tzm")
        os.remove(tmp + ".json")

    m = M.load_tzm(os.path.join(MATS, "wood_polished"))

    # ---- 2. the maps wrap -------------------------------------------------
    for k in ("albedo", "normal", "roughness", "ao", "height"):
        a = getattr(m, k).astype(np.float64)
        seam = np.abs(a[:, 0] - a[:, -1]).mean() + np.abs(a[0] - a[-1]).mean()
        inner = (np.abs(np.diff(a, axis=1)).mean() + np.abs(np.diff(a, axis=0)).mean())
        check(f"2 {k} wraps", seam <= inner * 3.0,
              f"seam {seam:6.2f}  interior {inner:6.2f}  "
              f"ratio {seam / max(inner, 1e-9):5.2f}")

    # ---- 3. an axis-aligned face uses one plane ---------------------------
    p = np.array([[100.0, 200.0, 300.0]])
    for ax in range(3):
        n = np.zeros((1, 3))
        n[0, ax] = 1.0
        w = M.triplanar(m, p, n)["weights"][0]
        check(f"3 axis {ax} uses one plane", w[ax] > 0.999 and w.sum() > 0.999,
              f"weights {np.round(w, 6)}")

    # ---- 4. the texture repeats at its PHYSICAL SIZE ----------------------
    per = m.physical_size_mm
    rng = np.random.default_rng(3)
    pts = rng.uniform(-500, 500, (400, 3))
    nrm = np.tile(np.array([0.0, 1.0, 0.0]), (400, 1))
    a0 = M.triplanar(m, pts, nrm)["albedo"]
    a1 = M.triplanar(m, pts + np.array([per, 0.0, per]), nrm)["albedo"]
    check("4 repeats at physical_size_mm", np.allclose(a0, a1, atol=1e-9),
          f"period {per:.3f} mm, max|diff| {np.abs(a0 - a1).max():.2e}")
    a2 = M.triplanar(m, pts + np.array([per * 0.37, 0.0, 0.0]), nrm)["albedo"]
    check("4b a NON-period offset really does change it",
          np.abs(a0 - a2).mean() > 1e-3, f"mean|diff| {np.abs(a0 - a2).mean():.4f}")

    # ---- 5. no view leak: the sampler never sees a camera ------------------
    src = open(os.path.join(TZ, "material.py"), encoding="utf-8").read()
    fn = next(f for f in ast.walk(ast.parse(src))
              if isinstance(f, ast.FunctionDef) and f.name == "triplanar")
    # Every NAME the function actually uses. This reads the AST rather than the
    # source text because the text version failed on the WORD "camera" inside a
    # comment explaining why there is no camera — a test that fails on its own
    # documentation is a broken test, not a caught bug.
    used = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)}
    used |= {a.arg for a in fn.args.args}
    used |= {n.attr for n in ast.walk(fn) if isinstance(n, ast.Attribute)}
    bad = used & {"cam", "camera", "eye", "view", "project", "rays"}
    check("5 triplanar cannot see a camera", not bad, f"used: {sorted(bad)}")

    # ---- 6. the normal map perturbs the shading normal --------------------
    n_geo = np.tile(np.array([0.0, 1.0, 0.0]), (400, 1))
    tn = M.triplanar(m, pts, n_geo)["normal"]
    ang = np.degrees(np.arccos(np.clip(np.einsum("ij,ij->i", tn, n_geo), -1, 1)))
    check("6 normal map bends the normal", ang.mean() > 0.5,
          f"mean {ang.mean():.2f} deg, p95 {np.percentile(ang, 95):.2f} deg, "
          f"max {ang.max():.2f} deg")

    # ---- 7. a material cannot move an edge --------------------------------
    #   This is `palette.py`'s law, extended: the material changes a stroke's
    #   COLOUR, and `canvas.ownership` reads no colour at all, so ownership must
    #   be bit-identical. Proved against the real canvas, not by inspection.
    try:
        import canvas                                     # noqa: E402
        from anatomy import Strokes                       # noqa: E402
        from stage import Camera                          # noqa: E402
        rng = np.random.default_rng(11)
        n = 4000
        pt = rng.uniform(-2, 2, (n, 3))
        nr = np.tile(np.array([0.0, 1.0, 0.0]), (n, 1))
        rad = np.full(n, 0.02)
        cam = Camera(eye=np.array([0.0, 1.5, 5.0]), target=np.zeros(3),
                     width=320, height=240)
        s_flat = Strokes(point=pt, normal=nr, rgb=np.full((n, 3), 0.5), radius=rad)
        s_mat = Strokes(point=pt, normal=nr, rgb=rng.random((n, 3)), radius=rad)
        o1, _, _ = canvas.ownership(cam, s_flat)
        o2, _, _ = canvas.ownership(cam, s_mat)
        check("7 a material cannot move an edge", np.array_equal(o1, o2),
              f"{int((o1 != o2).sum())} pixels differ out of {o1.size}")
    except Exception as e:                                 # noqa: BLE001
        check("7 a material cannot move an edge", False, f"could not run: {e!r}")

    # ---- 8. the two worlds land at the same physical size -----------------
    #   The workshop is authored in METRES (1 unit = 1000 mm). Iddo's
    #   photogrammetric room is in map-anything units calibrated at 403.0376 mm
    #   per unit (room3d/scale.json, 0.489 mm residual). The SAME material has to
    #   come out the SAME PHYSICAL SIZE in both, or "true scale" is a slogan.
    ms = M.MaterialSet(materials={"wood_polished": m},
                       assignment={"s": "wood_polished"})
    per_mm = m.physical_size_mm
    base = np.zeros((64, 3))
    base[:, 0] = np.linspace(-1.0, 1.0, 64)
    nrm2 = np.tile(np.array([0.0, 1.0, 0.0]), (64, 1))
    ids2 = np.zeros(64, dtype=np.int64)
    MM_PER_UNIT = 403.03764473                 # room3d/scale.json
    a_room = ms.surfaces(base, nrm2, ids2, ["s"], world_scale_mm=1000.0)["detail"]
    b_room = ms.surfaces(base + np.array([per_mm / 1000.0, 0, 0]), nrm2, ids2,
                         ["s"], world_scale_mm=1000.0)["detail"]
    a_pg = ms.surfaces(base, nrm2, ids2, ["s"],
                       world_scale_mm=MM_PER_UNIT)["detail"]
    b_pg = ms.surfaces(base + np.array([per_mm / MM_PER_UNIT, 0, 0]), nrm2, ids2,
                       ["s"], world_scale_mm=MM_PER_UNIT)["detail"]
    check("8 metres world repeats at the material's real size",
          np.allclose(a_room, b_room, atol=1e-9))
    check("8b the 403.0376 mm/unit world repeats at the same real size",
          np.allclose(a_pg, b_pg, atol=1e-9))

    # ---- 9. THE COLLAPSE IS NAMED, NOT SILENT (TZ-7, 2026-09-06) ----------
    #   At the gate's own 42 mm brush most of these materials clip to the top of
    #   the mip pyramid and become a CONSTANT, while `covered` stays True and the
    #   pipeline goes on calling them active at 100% coverage.
    fine = M.load_tzm(os.path.join(MATS, "steel_brushed"))
    check("9 a material finer than the brush collapses to ~1 texel",
          M.effective_map_px(fine, 42.0) < M.FLAT_TEXELS,
          f"steel_brushed at 42 mm -> {M.effective_map_px(fine, 42.0)} texels")
    coarse = M.load_tzm(os.path.join(MATS, "floor_vinyl"))
    check("9b a material harvested inside the band survives the brush",
          M.effective_map_px(coarse, 42.0) >= M.FLAT_TEXELS,
          f"floor_vinyl at 42 mm -> {M.effective_map_px(coarse, 42.0)} texels")
    ms2 = M.MaterialSet(materials={"steel_brushed": fine},
                        assignment={"s": "steel_brushed"})
    got = ms2.surfaces(base, nrm2, ids2, ["s"], world_scale_mm=1000.0,
                       footprint_mm=42.0)
    check("9c surfaces() reports flat_frac, not just covered",
          got.get("flat_frac") == 1.0 and got["covered"].all(),
          f"flat_frac {got.get('flat_frac')}  covered_frac {got.get('covered_frac')}")
    got0 = ms2.surfaces(base, nrm2, ids2, ["s"], world_scale_mm=1000.0)
    check("9d with no footprint given there is no LOD and nothing is called flat",
          got0["flat_frac"] == 0.0, f"flat_frac {got0['flat_frac']}")


_run_all()


@pytest.mark.parametrize("name,ok,detail", _CHECKS, ids=[c[0] for c in _CHECKS])
def test_material_check(name: str, ok: bool, detail: str) -> None:
    assert ok, f"{name}   {detail}"
