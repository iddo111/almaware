"""KAV-11 proof — the phase gate counts QUESTIONS, not answer-rival rows

Run: python proofs/proof_KAV-11.py old   -> must FAIL (exit 1)
     python proofs/proof_KAV-11.py new   -> must PASS (exit 0)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness


def check(organ):

    import inspect
    import numpy as np
    import joiner
    src = inspect.getsource(joiner.fit_line)
    assert "R[m].sum()" in src, (
        "fit_line still gates a phase on int(m.sum()) -- the number of (answer, rival) "
        "ROWS, the exact quantity its own docstring ten lines above explains is why "
        "the STL parts supplied 97.8%% of them. One question with 60 legal candidates "
        "unlocks a phase's private line by itself; thirty two-candidate questions "
        "do not.")
    assert hasattr(joiner, "MIN_QUESTIONS")
    import mesh
    clean = joiner.intact_only(mesh.our_corpus())[:8]
    X, P_, R, _, _ = joiner.training_pairs(clean)
    for ph in range(joiner.BINS):
        m = P_ == ph
        rows_, qs = int(m.sum()), float(R[m].sum())
        if rows_:
            print(f"    phase {ph}: {rows_:6d} rows = {qs:7.2f} questions "
                  f"({'row-gate' if rows_ >= joiner.MIN_QUESTIONS else 'no'} / "
                  f"{'question-gate' if qs >= joiner.MIN_QUESTIONS else 'no'})")
    disagree = [ph for ph in range(joiner.BINS)
                if (int((P_ == ph).sum()) >= joiner.MIN_QUESTIONS)
                != (float(R[P_ == ph].sum()) >= joiner.MIN_QUESTIONS)]
    print(f"    phases where the two rules disagree on this corpus: {disagree}")


_harness.run(check)
