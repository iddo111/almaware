# -*- coding: utf-8 -*-
"""PROOF TZ-5 — the orphan organs are declared, checked, and cannot lie in either direction

Run it against the code on disk:      python proof_TZ-5.py
Run it against the pre-fix backup:    python proof_TZ-5.py <dir-with-the-old-modules>
It must FAIL on the old code and PASS on the new. That is the whole point of it.
"""
import os
import sys
import warnings

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import ast

import numpy as np


def _imports(path, module):
    tree = ast.parse(open(path, encoding="utf-8").read())
    for n in ast.walk(tree):
        if isinstance(n, ast.Import) and any(
                a.name.split(".")[0] == module for a in n.names):
            return True
        if isinstance(n, ast.ImportFrom) and n.module and \
                n.module.split(".")[0] == module:
            return True
    return False


def main():
    import material
    import occlusion
    for mod in (material, occlusion):
        assert hasattr(mod, "RENDER_PATH_WIRED"), (
            f"{mod.__name__}.py sits in the render folder and says nothing about "
            f"whether anything renders with it. It is the biggest measured win of "
            f"the last 48 hours and it reaches no picture.")
    entries = [os.path.join(ROOT, f) for f in
               ("night.py", "godot_gate.py", "gate2.py", "ruler.py", "canvas.py")]
    for mod in (material, occlusion):
        actual = any(_imports(p, mod.__name__) for p in entries if os.path.isfile(p))
        assert bool(mod.RENDER_PATH_WIRED) == actual, (
            f"{mod.__name__}.RENDER_PATH_WIRED={mod.RENDER_PATH_WIRED} but the real "
            f"import graph says {actual}")

    # and the silent-wrong-picture path is now a named refusal
    import material as M
    import meshstage
    from stage import orbit

    class MatMesh(M.MaterialStage, meshstage.MeshStage):
        pass

    tris = np.array([[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]])
    st = MatMesh(tris, mset=M.MaterialSet(materials={}, assignment={}),
                 mat_of_box=[])
    try:
        st.gbuffer(orbit(0.0, 32, 24))
    except TypeError as e:
        assert "no boxes" in str(e), e
    else:
        raise AssertionError(
            "MaterialStage silently dressed a MeshStage — every pixel of night.py's "
            "subject would wear the GROUND material and nothing would complain")
    print(f"PASS  {ROOT}")
    print(f"      material.RENDER_PATH_WIRED={material.RENDER_PATH_WIRED}  "
          f"occlusion.RENDER_PATH_WIRED={occlusion.RENDER_PATH_WIRED}, "
          f"both matching the real import graph")
    print("      MaterialStage refuses a stage with no boxes, by name")


if __name__ == "__main__":
    try:
        main()
    except BaseException as e:                                    # noqa: BLE001
        print(f"FAIL  {ROOT}\n      {type(e).__name__}: {e}")
        sys.exit(1)
    sys.exit(0)
