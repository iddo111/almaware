"""KAV-02 proof — the two halves are composed at least once (gate 3)

Run: python proofs/proof_KAV-02.py old   -> must FAIL (exit 1)
     python proofs/proof_KAV-02.py new   -> must PASS (exit 0)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness


def check(organ):

    import numpy as np
    import mesh, joiner, ruler
    import anatomy
    assert hasattr(ruler, "measure_gate3"), "there is no gate 3: the coordinate half " \
        "and the joining half have never been asked to speak together"
    assert hasattr(ruler, "say_shape"), "nothing composes the halves"
    calls = {"n": 0}
    real = anatomy.continue_shape
    def counting(*a, **k):
        calls["n"] += 1
        return real(*a, **k)
    anatomy.continue_shape = counting
    ruler.continue_shape = counting
    tris = mesh.box([0, 0, 0], [1, 1, 1])
    train = [("cube2", mesh.box([0, 0, 0], [1, 1.5, 1])),
             ("slab2", mesh.box([0, 0, 0], [2, 1, 1]))]
    posture = ruler.fit(train, 18)
    scorer = joiner.fit(train)
    r = ruler.say_shape("cube", tris, posture, scorer, whole=True)
    print(f"    continue_shape called {calls['n']}x; said {r['said_vertices']} vertices "
          f"of {r['true_vertices']}, {r['said_faces']}/{r['true_faces']} faces, "
          f"volume x{r['volume_ratio']:.3f}, right={r['right']}")
    assert calls["n"] >= 1, "gate 3 did not actually call the coordinate half"
    truth_table = mesh.table_and_faces(tris)[0]
    assert r["vertices"] is not None
    said = r["vertices"]["table"]
    assert not (said.shape == truth_table.shape and np.array_equal(said, truth_table)), \
        "gate 3 used the TRUTH's vertex table — that is gate 2 with a new name"


_harness.run(check)
