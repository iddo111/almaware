"""KAV-03 proof — gate 1b can be asked from the start gate 2 actually climbs from

Run: python proofs/proof_KAV-03.py old   -> must FAIL (exit 1)
     python proofs/proof_KAV-03.py new   -> must PASS (exit 0)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness


def check(organ):

    import inspect
    import mesh, joiner
    sig = inspect.signature(joiner.score)
    assert "seed_fraction" in sig.parameters, \
        "joiner.score cannot be asked from gate 2's start, so gate 1b's number can " \
        "never predict gate 2's and the ladder between them is unsound"
    tris = mesh.box([0, 0, 0], [1, 2, 3])
    corpus = [("slab", tris)]
    a = joiner.score({"m": joiner.MirrorFloor()}, corpus)
    b = joiner.score({"m": joiner.MirrorFloor()}, corpus, seed_fraction=joiner.SEED_FRACTION)
    print(f"    from one face: {a['frames']} questions ({a['started_from']})")
    print(f"    from gate 2's seed: {b['frames']} questions ({b['started_from']})")
    assert a["frames"] != b["frames"] or a["accuracy"]["m"] != b["accuracy"]["m"], \
        "the two starts ask the same questions — then there was nothing to fix"


_harness.run(check)
