"""KAV-14 proof — no dead walker, and the common-answer floor stops building a design matrix it throws away

Run: python proofs/proof_KAV-14.py old   -> must FAIL (exit 1)
     python proofs/proof_KAV-14.py new   -> must PASS (exit 0)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness


def check(organ):

    import inspect
    import numpy as np
    import mesh, joiner, ruler
    assert not hasattr(joiner, "training_contrasts"), \
        "joiner.training_contrasts has no callers anywhere and is still here"
    assert not hasattr(joiner, "training_rows"), \
        "joiner.training_rows lost its last caller and is still here"
    assert len(inspect.signature(ruler._most_common).parameters) == 1, \
        "ruler._most_common still accepts a k it never uses"
    seen = {"described": 0, "bare": 0}
    real = joiner.step_of
    def counting(surface, k, near=joiner.NEAR, describe=True):
        seen["described" if describe else "bare"] += 1
        return real(surface, k, near, describe)
    joiner.step_of = counting
    corpus = [("clip", [t for t in mesh.our_corpus() if t[0] == "clip"][0][1])]
    got = joiner.most_common_answer(corpus)
    joiner.step_of = real
    print(f"    most_common_answer -> {got}; step_of called "
          f"{seen['described']}x WITH the 46 descriptions, {seen['bare']}x without")
    # the same walk, the same skip rule, counted independently
    from collections import Counter
    c = Counter()
    for _, tris in corpus:
        table, faces = mesh.table_and_faces(tris)
        for st, far in joiner.walk(table.astype(float), faces):
            if st is None or far not in st.cands:
                continue
            c.update([int(far)])
    assert got == c.most_common(1)[0][0], (got, c.most_common(3))
    assert seen["described"] == 0, (
        "most_common_answer still builds the full 46-column design matrix for every "
        "step of every training shape -- the 450/714/104-face STL parts included -- "
        "and throws every one of them away, to feed the weakest floor of the five")


_harness.run(check)
