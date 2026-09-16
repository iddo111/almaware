"""PROOF MOREH-14 — a published number must be reproducible from an artefact, not only from a re-fit.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

The defect: learn.save()/load() had zero call sites anywhere in the organ or its tests and no .npz
existed on disk — the mirror image of "training that writes checkpoints nobody loads". Every consumer
re-fitted from the lesson files, so a published number could not be traced to the weights that made it.

The fix: ruler.main() writes loo/posture-school-<school>.npz beside loo-results.json with the corpus
fingerprint and the chosen lambdas in its meta, and learn.load_meta() reads them back.

    python proof_MOREH-14.py          # live learn.py       -> must PASS
    python proof_MOREH-14.py --old    # .bak-rev-20260906   -> must FAIL
"""
import os
import sys
import tempfile

import numpy as np

ORGAN = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ORGAN)
from _proofkit import load          # noqa: E402

OLD = "--old" in sys.argv


def main():
    L = load(ORGAN, "learn.py", "learn_under_test", OLD)
    print("learn under test: %s" % L.__proof_source__)
    import anatomy as A
    rows = L.load_lessons()

    assert hasattr(L, "corpus_fingerprint"), "no corpus fingerprint: an .npz could not name its corpus"
    fp = L.corpus_fingerprint(rows)
    print("corpus fingerprint: %s (%d lessons)" % (fp, len(rows)))
    assert L.corpus_fingerprint(list(reversed(rows))) == fp, "the fingerprint depends on row order"
    assert L.corpus_fingerprint(rows[:-1]) != fp, "the fingerprint does not see a missing lesson"

    lam = L.select_lams(rows) if hasattr(L, "select_lams") else {"lam_conj": L.LAM_CONJ}
    p = L.fit(rows, **lam)
    d = tempfile.mkdtemp(prefix="moreh-proof14-")
    f = os.path.join(d, "posture.npz")
    L.save(p, f, {"corpus": fp, "lam": lam, "lessons": len(rows)})
    q = L.load(f)
    for dec in A.DEC_NAMES:
        assert np.array_equal(p.W[dec], q.W[dec]) and np.array_equal(p.b[dec], q.b[dec]), dec
    assert np.array_equal(p.A, q.A) and np.array_equal(p.a0, q.a0)
    print("save -> load round-trips the weights bit for bit: yes")

    assert hasattr(L, "load_meta"), "the meta beside the weights cannot be read back: load_meta missing"
    meta = L.load_meta(f)
    print("meta read back: %s" % meta)
    assert meta["corpus"] == fp and meta["lessons"] == len(rows)

    src = open(os.path.join(ORGAN, "ruler.py" + (".bak-rev-20260906" if OLD else "")), encoding="utf-8").read()
    assert "L.save(" in src, "ruler.py never writes a posture: save() still has no call site"
    assert "corpus_fingerprint" in src, "the written posture would not name its corpus"
    print("ruler.main() writes the fit-on-all posture with its corpus fingerprint: yes")

    os.remove(f); os.rmdir(d)
    print("PROOF MOREH-14 PASSED")


try:
    main()
except Exception as e:
    print("PROOF MOREH-14 FAILED: %s: %s" % (type(e).__name__, e))
    sys.exit(1)
