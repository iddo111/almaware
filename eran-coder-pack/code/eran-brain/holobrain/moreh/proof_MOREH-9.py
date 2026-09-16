"""PROOF MOREH-9 — a syllable filter that matches nothing must be an error, not "all 24".

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

The defect: ruler.main() had

    syls = [a for a in argv if a in by] or list(V2.SYLS)

so `python3 ruler.py xyz` produced an empty filter, fell through the `or` to all 24 syllables, and then
`if not argv:` was False, so the floors and the ceiling never ran. The result was a full-looking
loo-results.json with only "moreh" in its summary, no floor to compare against, and nothing anywhere
saying the filter had been ignored. A typo produced a complete but incomparable sitting.

The fix: unknown arguments are named and the run stops; the requested filter is written into
loo-results.json so a partial sitting can never be read as a full one.

    python proof_MOREH-9.py          # live ruler.py       -> must PASS
    python proof_MOREH-9.py --old    # .bak-rev-20260906   -> must FAIL
"""
import json
import os
import shutil
import sys
import tempfile

ORGAN = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ORGAN)
from _proofkit import load          # noqa: E402
import _proofstubs                  # noqa: E402

OLD = "--old" in sys.argv


def main():
    _proofstubs.install()
    R = load(ORGAN, "ruler.py", "moreh_ruler_under_test", OLD)
    print("ruler under test: %s" % R.__proof_source__)
    tmp = tempfile.mkdtemp(prefix="moreh-proof9-")
    R.OUT = tmp                                  # nothing of this proof touches the real loo/ folder

    # 1. a filter that matches nothing must stop the run and name the argument
    raised = None
    try:
        R.main(["xyz"])
    except SystemExit as e:
        raised = str(e)
    except Exception as e:                       # any other failure is not the guard we asked for
        raised = "%s: %s" % (type(e).__name__, e)
    print("ruler.main(['xyz']) -> %s" % (raised if raised else "RAN A FULL SITTING and returned"))
    if raised is None:
        wrote = os.path.join(tmp, "loo-results.json")
        d = json.load(open(wrote, encoding="utf-8")) if os.path.exists(wrote) else {}
        raise AssertionError(
            "a typo produced a whole sitting: %d syllables scored, summary keys %s, and nothing in the "
            "file records the ignored filter"
            % (d.get("lessons", 0) and len(d.get("results", {}).get("moreh", {})),
               sorted((d.get("summary") or {}))))
    assert "xyz" in raised, "the run stopped but did not name the unknown argument: %s" % raised

    # 2. a real, partial sitting must carry the filter that made it partial
    R.main(["ba"])
    d = json.load(open(os.path.join(tmp, "loo-results.json"), encoding="utf-8"))
    print("ruler.main(['ba']) -> requested_filter=%s  syllables_scored=%s"
          % (d.get("requested_filter"), d.get("syllables_scored")))
    assert d.get("requested_filter") == ["ba"], \
        "loo-results.json does not say which filter produced it: a partial sitting reads as a full one"
    shutil.rmtree(tmp, ignore_errors=True)
    print("PROOF MOREH-9 PASSED")


try:
    main()
except Exception as e:
    print("PROOF MOREH-9 FAILED: %s: %s" % (type(e).__name__, e))
    sys.exit(1)
