# -*- coding: utf-8 -*-
"""PROOF TZ-8 — the materials track cannot starve a microphone

Run it against the code on disk:      python proof_TZ-8.py
Run it against the pre-fix backup:    python proof_TZ-8.py <dir-with-the-old-modules>
It must FAIL on the old code and PASS on the new. That is the whole point of it.
"""
import os
import sys
import warnings

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import ast

FILES = ("gate_mat.py", "ab.py", "calibrate.py", "harvest.py")


def main():
    for f in FILES:
        p = os.path.join(ROOT, f)
        assert os.path.isfile(p), p
        tree = ast.parse(open(p, encoding="utf-8").read())
        order = []
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                for a in n.names:
                    order.append((n.lineno, a.name.split(".")[0]))
        order.sort()
        names = [m for _, m in order]
        assert "courtesy" in names, (
            f"{f} has no priority class, no nice and no thread cap anywhere, while "
            f"night.py, gate2.py, godot_gate.py, hero8k.py and both oneroom logs all "
            f"set BELOW_NORMAL as their first act. This track was run ON ERAN1, the "
            f"box that serves ERAN's live microphone.")
        if "numpy" in names:
            assert names.index("courtesy") < names.index("numpy"), (
                f"{f} imports numpy before courtesy, so the BLAS thread pools are "
                f"already sized and the cap does nothing")
    src = open(os.path.join(ROOT, "courtesy.py"), encoding="utf-8").read()
    for needed in ("OMP_NUM_THREADS", "BELOW_NORMAL", "os.nice", "MIC_HOSTS"):
        assert needed in src, needed
    print(f"PASS  {ROOT}")
    print(f"      {', '.join(FILES)} all import courtesy BEFORE numpy")
    print("      courtesy caps threads, nices the process, and warns on a mic box")


if __name__ == "__main__":
    try:
        main()
    except BaseException as e:                                    # noqa: BLE001
        print(f"FAIL  {ROOT}\n      {type(e).__name__}: {e}")
        sys.exit(1)
    sys.exit(0)
