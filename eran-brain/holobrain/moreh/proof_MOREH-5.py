"""PROOF MOREH-5 — the lesson source must be a parameter, so the second corpus can be read at all.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

The defect: learn.LESSONS was a module constant pointing only at school-v2. A second, independently
gated corpus — school-v3, 134 renders passed by a Hebrew wav2vec2 phoneme judge instead of the
self-confirming acoustic ruler — has been on disk since 2026-09-03 19:29 and was read by nothing.

The fix: load_lessons(school="v3") (and root=...) with a schema adapter, so the whole sitting can be
re-run on the judge's corpus. It covers 12 of the 24 syllables — a 12-syllable LOO, and ruler.py says so.

    python proof_MOREH-5.py          # live learn.py       -> must PASS
    python proof_MOREH-5.py --old    # .bak-rev-20260906   -> must FAIL
"""
import os
import sys

ORGAN = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ORGAN)
from _proofkit import load          # noqa: E402

OLD = "--old" in sys.argv


def main():
    L = load(ORGAN, "learn.py", "learn_under_test", OLD)
    print("learn under test: %s" % L.__proof_source__)

    v3root = os.path.abspath(os.path.join(ORGAN, "..", "..", "throat-one-sample", "school-v3", "lessons"))
    n_json = len([f for f in os.listdir(v3root) if f.endswith(".json")])
    print("school-v3 on disk: %d lesson JSONs at %s" % (n_json, v3root))
    assert n_json == 134, n_json

    rows = L.load_lessons(school="v3")
    by = L.by_syllable(rows)
    print("loaded school-v3: %d rows over %d syllables: %s" % (len(rows), len(by), " ".join(sorted(by))))
    assert len(rows) == 134, len(rows)
    assert len(by) == 12, sorted(by)

    # the facts must be identical to school-v2's for the same syllable -- never a second typed table
    v2 = L.by_syllable(L.load_lessons(school="v2"))
    for s in by:
        assert list(by[s][0]["x"]) == list(v2[s][0]["x"]), ("facts differ for %s" % s)
    print("facts for all 12 syllables come from the v2 corpus unchanged: yes")

    # and it must actually fit
    p = L.fit(rows)
    print("fit on school-v3 ok; smallest n_live = %d" % int(p.n_live.min()))

    src = open(os.path.join(ORGAN, "ruler.py" + (".bak-rev-20260906" if OLD else "")), encoding="utf-8").read()
    assert "--school" in src, "ruler.py cannot be pointed at another corpus"
    print("ruler.py accepts --school: yes")
    print("PROOF MOREH-5 PASSED")


try:
    main()
except Exception as e:
    print("PROOF MOREH-5 FAILED: %s: %s" % (type(e).__name__, e))
    sys.exit(1)
