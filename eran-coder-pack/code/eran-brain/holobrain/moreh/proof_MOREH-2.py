"""PROOF MOREH-2 — no hyperparameter may be chosen on the syllable it is scored on.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

The defect: learn.py's LAM_CONJ = 100.0 was picked by sweeping it against the leave-one-syllable-out
error that ruler.py then publishes. 100.0 is the argmin of its own metric, so the four syllables it
"gained" are selection bias, not learning.

The fix: select_lams() runs an inner LOO over the caller's TRAINING rows only, and ruler.loo() calls it
per fold, so the held-out syllable is never seen by the hyperparameter search either.

    python proof_MOREH-2.py          # against the live learn.py   -> must PASS
    python proof_MOREH-2.py --old    # against .bak-rev-20260906   -> must FAIL
"""
import os
import sys

ORGAN = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ORGAN)
from _proofkit import load          # noqa: E402

OLD = "--old" in sys.argv


def loo_wrong(L, A, rows, nested, lam=None):
    """decisions-only leave-one-SYLLABLE-out; returns the syllables whose decisions came out wrong"""
    by = L.by_syllable(rows)
    bad = []
    for syl in sorted(by):
        train = [r for r in rows if r["syl"] != syl]
        lm = L.select_lams(train) if nested else dict(lam or {})
        p = L.fit(train, **lm)
        truth = {d: max(set(r["dec"][d] for r in by[syl]), key=[r["dec"][d] for r in by[syl]].count)
                 for d in A.DEC_NAMES}
        if p.decide(by[syl][0]["x"]) != truth:
            bad.append(syl)
    return bad


def main():
    rp = os.path.join(ORGAN, "ruler.py" + (".bak-rev-20260906" if OLD else ""))
    L = load(ORGAN, "learn.py", "learn_under_test", OLD)
    print("learn under test: %s" % L.__proof_source__)
    import anatomy as A
    rows = L.load_lessons()
    print("corpus: %d lessons, %d syllables" % (len(rows), len(L.by_syllable(rows))))

    # 1. the chooser must exist and must take only the rows it is handed
    if not hasattr(L, "select_lams"):
        raise AssertionError("learn.py has no select_lams(): the lambdas are module constants, and "
                             "LAM_CONJ=100.0 was swept on the LOO that is published as the result")
    train = [r for r in rows if r["syl"] != "ba"]
    lam = L.select_lams(train)
    assert set(lam) == {"lam_dec", "lam_conj", "lam_amt"}, lam
    assert lam == L.select_lams(list(reversed(train))), "select_lams depends on row order"
    print("select_lams(train without ba) = %s" % lam)

    # 2. ruler.py must call it inside the fold, not fit with the constants
    src = open(rp, encoding="utf-8").read()
    assert "L.select_lams(train)" in src, "ruler.loo() does not choose lambda inside the fold"
    assert "L.fit(train)" not in src, "ruler.loo() still calls L.fit(train) with the tuned constants"
    print("ruler.py chooses lambda inside each fold: yes")

    # 3. the honest number, measured now
    tuned = loo_wrong(L, A, rows, nested=False, lam={"lam_conj": 100.0})
    nested = loo_wrong(L, A, rows, nested=True)
    print("LOO decisions wrong  with LAM_CONJ=100 (tuned on this metric): %d  %s" % (len(tuned), tuned))
    print("LOO decisions wrong  with lambda chosen inside each fold     : %d  %s" % (len(nested), nested))
    print("=> honest decisions correct: %d/24 (the published number was %d/24)"
          % (24 - len(nested), 24 - len(tuned)))
    assert len(nested) >= len(tuned), "a nested LOO cannot beat the constant that was tuned on it"
    assert len(nested) > len(tuned), ("the selection bias should be visible on this corpus "
                                      "(measured 09-06: 13 nested vs 9 tuned)")
    print("PROOF MOREH-2 PASSED")


try:
    main()
except Exception as e:
    print("PROOF MOREH-2 FAILED: %s: %s" % (type(e).__name__, e))
    sys.exit(1)
