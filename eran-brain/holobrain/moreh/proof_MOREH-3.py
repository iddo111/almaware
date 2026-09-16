"""PROOF MOREH-3 — the floor must run on the same features as the model.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

The defect: learn.Flat (the "09-02 regressor" the whole decisions-then-amounts thesis is argued against)
was fed the 14 bare facts while MOREH is fed ear(x) = 49 columns. Part of the published margin was a
feature-set difference, not the architecture.

The fix: Flat builds X from ear(x) and predicts from ear(x) — the same 49 columns.

    python proof_MOREH-3.py          # live learn.py               -> must PASS
    python proof_MOREH-3.py --old    # .bak-rev-20260906           -> must FAIL
"""
import os
import sys

ORGAN = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ORGAN)
from _proofkit import load          # noqa: E402

OLD = "--old" in sys.argv


def flat_loo_wrong(L, A, rows):
    by = L.by_syllable(rows)
    bad = []
    for syl in sorted(by):
        train = [r for r in rows if r["syl"] != syl]
        s = L.Flat(train).spec(by[syl][0]["x"])
        truth = {d: max(set(r["dec"][d] for r in by[syl]), key=[r["dec"][d] for r in by[syl]].count)
                 for d in A.DEC_NAMES}
        if any(s[d] != truth[d] for d in A.DEC_NAMES):
            bad.append(syl)
    return bad


def main():
    L = load(ORGAN, "learn.py", "learn_under_test", OLD)
    print("learn under test: %s" % L.__proof_source__)
    import anatomy as A
    rows = L.load_lessons()

    f = L.Flat(rows)
    n_cols = f.W.shape[0]
    print("flat floor feature columns: %d   (MOREH gets %d)" % (n_cols, A.NF + A.NC))
    bad = flat_loo_wrong(L, A, rows)
    print("flat LOO decisions wrong: %d/24  %s" % (len(bad), bad))
    assert n_cols == A.NF + A.NC == 49, (
        "the floor is fed %d columns while MOREH is fed %d: the comparison measures the feature set, "
        "not the architecture" % (n_cols, A.NF + A.NC))
    assert len(bad) <= 13, "with the same features the floor should reach 13 wrong (measured 09-06)"
    print("PROOF MOREH-3 PASSED")


try:
    main()
except Exception as e:
    print("PROOF MOREH-3 FAILED: %s: %s" % (type(e).__name__, e))
    sys.exit(1)
