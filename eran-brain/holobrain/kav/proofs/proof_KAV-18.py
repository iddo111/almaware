"""KAV-18 proof — blinding the grove is tested, not only argued in a docstring

Run: python proofs/proof_KAV-18.py old   -> must FAIL (exit 1)
     python proofs/proof_KAV-18.py new   -> must PASS (exit 0)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness


def check(organ):

    import ast, io
    src = io.open(os.path.join(organ, "tests", "test_joiner.py"), encoding="utf-8").read()
    hits = [n.name for n in ast.parse(src).body
            if isinstance(n, ast.FunctionDef) and "fit_grove_without" in ast.dump(n)]
    assert hits, (
        "the ablation the fold ruling actually rests on is GROVE_NOFOLD, produced by "
        "ruler.fit_grove_without, whose exactness is asserted in a DOCSTRING ('a "
        "constant-zero column can never be split on') and never tested. The only "
        "blinding test covers fit_line_without, the ridge.")
    print(f"    grove-blinding tests: {hits}")
    # and the property itself, measured here
    import numpy as np
    import mesh, joiner, ruler
    train = ruler.clean_solids()[:6]
    sc = ruler.fit_grove_without(train, ruler.FOLD_COLUMNS)
    used = set()
    for tree in sc.grove.trees:
        stack = [tree]
        while stack:
            nd = stack.pop()
            if isinstance(nd, tuple) and len(nd) == 4:
                used.add(int(nd[0]))
                stack.extend([nd[2], nd[3]])
    print(f"    a grove blinded on {ruler.FOLD_COLUMNS} split on {len(used)} columns, "
          f"none of them blinded: {sorted(used & set(ruler.FOLD_COLUMNS)) == []}")
    assert not (used & set(ruler.FOLD_COLUMNS))


_harness.run(check)
