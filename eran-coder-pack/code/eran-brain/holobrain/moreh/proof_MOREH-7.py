"""PROOF MOREH-7 — the amounts fallback must read the LIVE rows, and no-lessons must raise.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

The defect: when an amount had fewer than 3 live lessons, fit() fell back to the median over ALL rows —
including the rows where that amount is not live and the loader had filled it with 0.0. It would emit a
physically wrong number, silently, with nothing on the spec to say it was guessed. Measured on the real
corpus: c_area median over all rows 2.000 ("mouth wide open") vs 0.167 over the live rows; velum 0.000
("nose shut") vs 0.654.

The fix: the median is taken over the live rows, n_live == 0 raises instead of guessing, and ruler.py
writes n_live + amounts_guessed into every LOO JSON.

    python proof_MOREH-7.py          # live learn.py       -> must PASS
    python proof_MOREH-7.py --old    # .bak-rev-20260906   -> must FAIL
"""
import os
import sys

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

    # what the two medians actually are, on the real corpus
    for a in ("c_area", "velum", "gap_area", "d_pre"):
        i = A.AMOUNTS.index(a)
        live = [r["am"][i] for r in rows if r["live"][i]]
        allr = [r["am"][i] for r in rows]
        print("  %-9s median over LIVE rows %.3f   over ALL rows %.3f   (n_live %d/%d)"
              % (a, float(np.median(live)), float(np.median(allr)), len(live), len(allr)))

    i = A.AMOUNTS.index("c_area")
    live = sorted((r for r in rows if r["live"][i]), key=lambda r: r["am"][i])
    two = live[:2]                                           # 2 live rows -> the <3 fallback fires
    thin = two + [r for r in rows if not r["live"][i]]
    p = L.fit(thin)
    want_live = float(np.median([r["am"][i] for r in two]))
    want_all = float(np.median([r["am"][i] for r in thin]))
    print("fallback for c_area with 2 live rows: got %.4f   live-median %.4f   all-rows-median %.4f"
          % (p.a0[i], want_live, want_all))
    assert abs(p.a0[i] - want_live) < 1e-12, (
        "the fallback took the median over ALL rows (%.4f), i.e. the loader's 0.0 filler for the dead "
        "rows, not the live lessons (%.4f)" % (p.a0[i], want_live))
    assert abs(want_live - want_all) > 1e-6, "this corpus does not separate the two medians any more"

    dead_only = [r for r in rows if not r["live"][i]]
    try:
        L.fit(dead_only)
        raise AssertionError("fit() invented a number for c_area with n_live == 0 instead of raising")
    except ValueError as e:
        print("n_live == 0 raises: %s" % str(e)[:90])

    src = open(os.path.join(ORGAN, "ruler.py" + (".bak-rev-20260906" if OLD else "")), encoding="utf-8").read()
    assert "amounts_guessed" in src and "n_live" in src, \
        "the LOO JSON does not record which amounts were guessed"
    print("ruler.py records n_live and amounts_guessed in the LOO JSON: yes")
    print("PROOF MOREH-7 PASSED")


try:
    main()
except Exception as e:
    print("PROOF MOREH-7 FAILED: %s: %s" % (type(e).__name__, e))
    sys.exit(1)
