"""KAV-04 proof — not_solids() can refuse, and SOLID_HELD is derived from it

Run: python proofs/proof_KAV-04.py old   -> must FAIL (exit 1)
     python proofs/proof_KAV-04.py new   -> must PASS (exit 0)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness


def check(organ):

    import mesh, ruler
    corpus = mesh.our_corpus()
    ns = ruler.not_solids(corpus)
    names = sorted(x["name"] for x in ns)
    print(f"    not_solids -> {names}")
    for x in ns:
        print(f"      {x['name']}: dropped {x['dropped_by_grid']} of {x['faces_in']} faces")
    assert names == ["clip", "pinch-bar", "pinch-lever", "pinch-rail"], (
        "not_solids() returns %r — the check that is supposed to name the parts the "
        "grid breaks has never refused, and the 'NOT A SOLID ON THIS GRID' line it "
        "exists to print has never printed" % (names,))
    assert hasattr(ruler, "solid_held"), "SOLID_HELD is still hand-written, not derived"
    assert ruler.solid_held(corpus) == ruler.SOLID_HELD, (
        ruler.solid_held(corpus), ruler.SOLID_HELD)
    print(f"    solid_held(corpus) = {ruler.solid_held(corpus)} == SOLID_HELD")


_harness.run(check)
