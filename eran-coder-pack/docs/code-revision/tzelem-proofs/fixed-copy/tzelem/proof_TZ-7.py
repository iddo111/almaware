# -*- coding: utf-8 -*-
"""PROOF TZ-7 — a material that cannot reach the picture says so

Run it against the code on disk:      python proof_TZ-7.py
Run it against the pre-fix backup:    python proof_TZ-7.py <dir-with-the-old-modules>
It must FAIL on the old code and PASS on the new. That is the whole point of it.
"""
import os
import sys
import warnings

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import numpy as np


def main():
    import material as M
    assert hasattr(M, "effective_map_px"), (
        "lod_for still clips to the top of the mip pyramid in silence: a material "
        "collapses to a 1x1 map — a constant — while the pipeline reports it as "
        "active at 100% coverage.")
    mats = os.path.join(ROOT, "mats")
    fine = M.load_tzm(os.path.join(mats, "steel_brushed"))
    coarse = M.load_tzm(os.path.join(mats, "floor_vinyl"))
    e_fine = M.effective_map_px(fine, 42.0)
    e_coarse = M.effective_map_px(coarse, 42.0)
    assert e_fine < M.FLAT_TEXELS <= e_coarse, (e_fine, e_coarse)

    ms = M.MaterialSet(materials={"steel_brushed": fine},
                       assignment={"s": "steel_brushed"})
    pt = np.zeros((32, 3))
    pt[:, 0] = np.linspace(-1, 1, 32)
    nr = np.tile(np.array([0.0, 1.0, 0.0]), (32, 1))
    ids = np.zeros(32, dtype=np.int64)
    got = ms.surfaces(pt, nr, ids, ["s"], world_scale_mm=1000.0, footprint_mm=42.0)
    assert "flat_frac" in got, (
        "MaterialSet.surfaces still reports only `covered`, so "
        "material_coverage_frac: 1.0 can be true and meaningless at once")
    assert got["flat_frac"] == 1.0 and got["covered"].all(), got["flat_frac"]
    none = ms.surfaces(pt, nr, ids, ["s"], world_scale_mm=1000.0)
    assert none["flat_frac"] == 0.0
    print(f"PASS  {ROOT}")
    print(f"      steel_brushed at a 42 mm brush -> {e_fine}x{e_fine} texels "
          f"(a constant);  floor_vinyl -> {e_coarse}x{e_coarse} (real structure)")
    print(f"      surfaces(): covered_frac={got['covered_frac']}  "
          f"flat_frac={got['flat_frac']}  bar={M.FLAT_FRAC_BAR}")


if __name__ == "__main__":
    try:
        main()
    except BaseException as e:                                    # noqa: BLE001
        print(f"FAIL  {ROOT}\n      {type(e).__name__}: {e}")
        sys.exit(1)
    sys.exit(0)
