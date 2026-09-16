"""KAV-13 proof — the wide table's hit counts stay integers, and `seeded` is the shape's

Run: python proofs/proof_KAV-13.py old   -> must FAIL (exit 1)
     python proofs/proof_KAV-13.py new   -> must PASS (exit 0)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness


def check(organ):

    import ast, io, inspect
    import mesh, joiner, ruler
    sc = joiner.score({"m": joiner.MirrorFloor()},
                      [("cube", mesh.box([0, 0, 0], [1, 1, 1]))])
    assert "hits" in sc, ("joiner.score computes the integer hit count and then divides "
                          "it away, so ruler.measure_join_wide has to reconstruct it "
                          "out of a float -- and the wide test compares the result to "
                          "four decimal places")
    assert all(isinstance(v, int) for v in sc["hits"].values()), sc["hits"]
    print(f"    joiner.score returns integer hits: {sc['hits']}")
    src = inspect.getsource(ruler.measure_join_wide)
    assert 'sc["accuracy"][n] * sc["frames"]' not in src, \
        "measure_join_wide still rebuilds integer hit counts out of floats"
    tree = ast.parse(inspect.getsource(ruler.measure_join_wide).lstrip())
    inner = None
    for node in ast.walk(tree):
        if isinstance(node, ast.For) and getattr(node.target, "id", "") == "n":
            inner = node
    assert inner is not None
    def writes_row_seeded(node):
        for t in node.targets:
            if (isinstance(t, ast.Subscript) and getattr(t.value, "id", "") == "row"
                    and isinstance(t.slice, ast.Constant) and t.slice.value == "seeded"):
                return True
        return False
    seeded_in_loop = any(writes_row_seeded(x)
                         for x in ast.walk(inner) if isinstance(x, ast.Assign))
    assert not seeded_in_loop, ("row['seeded'] is written inside the per-chooser loop, "
                                "so the row records only the LAST chooser's seed count; "
                                "it is a property of the shape")
    print("    hits come from joiner.score's integers; seeded is set once per shape")


_harness.run(check)
