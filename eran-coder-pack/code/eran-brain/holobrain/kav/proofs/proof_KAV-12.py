"""KAV-12 proof — a corpus and a split that lose a shape refuse instead of shrinking in silence

Run: python proofs/proof_KAV-12.py old   -> must FAIL (exit 1)
     python proofs/proof_KAV-12.py new   -> must PASS (exit 0)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness


def check(organ):

    import io, os as _os, inspect
    import mesh, learn
    corpus = [("plate", None), ("stack", None), ("drum8", None)]
    try:
        learn.split(corpus, ("plate", "stack", "drum8", "THIS-SHAPE-DOES-NOT-EXIST"))
    except ValueError as e:
        print(f"    split refused: {e}")
    else:
        raise AssertionError(
            "learn.split accepted a held-out name that is not in the corpus and sealed "
            "a smaller set with no complaint — gate 1's sealed set can drop from 2,097 "
            "frames to 120 and every number moves wholesale with nothing said")
    real = _os.path.exists
    try:
        _os.path.exists = lambda p: real(p) and not str(p).endswith("PINCH-RAIL.stl")
        try:
            got = mesh.our_corpus()
        except FileNotFoundError as e:
            print(f"    our_corpus refused: {str(e)[:110]}...")
        else:
            raise AssertionError(
                "mesh.our_corpus() silently returned %d shapes with PINCH-RAIL.stl "
                "missing — the corpus shrinks and nothing says so" % len(got))
    finally:
        _os.path.exists = real
    src = inspect.getsource(learn.fit)
    body = src.split("if not rows[ph]:", 1)[1][:200]
    assert "raise" in body, ("learn.fit still leaves a phase with no rows at zero "
                             "weights and zero bias, predicting 0 for ever, with no "
                             "raise and no log")
    print("    learn.fit raises on an empty phase")


_harness.run(check)
