# -*- coding: utf-8 -*-
"""
> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

THE ACT THAT NEVER RETURNS -- caught as a test instead of as a surprise (TZ-5).

`material.py` (27.7 KB, the newest and largest module in the organ, built on Iddo's
03:12 order "tibne et shalav 3 - chomarim") and `occlusion.py` (15.0 KB) both carry a
MEASURED improvement -- +78% Laplacian variance and +300% sharpness -- and NEITHER is
imported by anything that renders. `night.py`, `godot_gate.py`, `gate2.py` and
`oneroom/paint.py` import neither. A copy of a file dropped into the render folder had
started to look like a connection.

The remedy is not to delete them (the materials deliverable renders with `material.py`
every time it runs) and not to wire them in silence (turning materials on is an art
decision with a measured fidelity cost, and it is Iddo's call). The remedy is that the
state must be DECLARED in the code and CHECKED, in both directions:

  * a module that declares itself wired must actually be imported by a render path;
  * a module that is imported by a render path must not still declare itself unwired.

So the day somebody wires it, this test fails until the declaration is corrected --
and the day somebody unwires it, the same. A silence cannot come back.
"""
from __future__ import annotations

import ast
import os
import sys

import pytest

TZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if TZ not in sys.path:
    sys.path.insert(0, TZ)

# Everything that turns strokes into a picture anyone looks at.
RENDER_ENTRY_POINTS = [
    os.path.join(TZ, "night.py"),
    os.path.join(TZ, "godot_gate.py"),
    os.path.join(TZ, "gate2.py"),
    os.path.join(TZ, "ruler.py"),
    os.path.join(TZ, "canvas.py"),
    os.path.join(TZ, "anatomy.py"),
    os.path.join(TZ, "hero8k.py"),
    os.path.join(TZ, "meshstage.py"),
    os.path.join(TZ, "stage.py"),
    os.path.join(TZ, "palette.py"),
    os.path.join(r"D:\CLAUDE\oneroom", "paint.py"),
    os.path.join(r"D:\CLAUDE\oneroom", "gate.py"),
]

DECLARED = ["material", "occlusion"]


def _imported_by_render_paths(module: str) -> list[str]:
    """Which render entry points really import `module`. Read from the AST."""
    hits = []
    for path in RENDER_ENTRY_POINTS:
        if not os.path.isfile(path):
            continue
        try:
            tree = ast.parse(open(path, encoding="utf-8").read())
        except SyntaxError:                                # pragma: no cover
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                if any(a.name.split(".")[0] == module for a in node.names):
                    hits.append(os.path.basename(path))
                    break
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.module.split(".")[0] == module:
                    hits.append(os.path.basename(path))
                    break
    return hits


@pytest.mark.parametrize("module", DECLARED)
def test_declaration_matches_the_real_import_graph(module: str) -> None:
    mod = __import__(module)
    declared = getattr(mod, "RENDER_PATH_WIRED", None)
    assert declared is not None, (
        f"{module}.py sits in the render folder and says nothing about whether any "
        f"render path uses it. Declare RENDER_PATH_WIRED.")
    actual = _imported_by_render_paths(module)
    if declared:
        assert actual, (
            f"{module}.RENDER_PATH_WIRED is True but no render entry point imports "
            f"it. A declaration is not a wire.")
    else:
        assert not actual, (
            f"{module}.RENDER_PATH_WIRED is False but {actual} import it. It IS in "
            f"the render path now — flip the declaration and re-measure the gate, "
            f"because turning materials on already cost fidelity headroom once "
            f"(gate-mat.log: BLANK ratio x2.24 -> x1.58 -> x1.44).")


def test_material_stage_refuses_a_stage_that_has_no_boxes() -> None:
    """TZ-5: MaterialStage keys on BOX ids and MeshStage is a triangle soup.

    Mixed into MeshStage the old code silently gave every pixel the GROUND material
    instead of the subject's. `night.py` renders a MeshStage, so this was the exact
    shape a careless "wiring" would have taken.
    """
    import numpy as np

    import material as M
    import meshstage
    from stage import orbit

    class MatMesh(M.MaterialStage, meshstage.MeshStage):
        pass

    tris = np.array([[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]])
    mset = M.MaterialSet(materials={}, assignment={})
    st = MatMesh(tris, mset=mset, mat_of_box=[])
    with pytest.raises(TypeError, match="no boxes"):
        st.gbuffer(orbit(0.0, 32, 24))
