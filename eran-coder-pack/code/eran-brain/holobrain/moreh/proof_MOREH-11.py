"""PROOF MOREH-11 — the ceiling must be recomputed from the ledger, not read from a stale snapshot.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

The defect: gate1.json is a 2026-09-03 09:43 snapshot (994 attempts -> 333 verified, "33.5%"), and
ruler.py read it as `ceiling_teacher_variants` in every sitting. The ledger it summarises has since
grown 360 rows (the 15:30-18:01 probe runs), so the teacher's real measured pass rate is lower and four
syllables' per-syllable rates have drifted. STATUS.md published the stale figure as "the reachable bar".

The fix: ceiling_from_ledger() recomputes from ledger.jsonl at the start of every sitting; the gate1
snapshot is kept beside it, clearly labelled, and STATUS.md carries the measured number.

    python proof_MOREH-11.py          # live ruler.py       -> must PASS
    python proof_MOREH-11.py --old    # .bak-rev-20260906   -> must FAIL
"""
import json
import os
import sys

ORGAN = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ORGAN)
from _proofkit import load          # noqa: E402
import _proofstubs                  # noqa: E402

OLD = "--old" in sys.argv
LESSONS = os.path.abspath(os.path.join(ORGAN, "..", "..", "throat-one-sample", "school-v2", "lessons"))


def main():
    _proofstubs.install()
    R = load(ORGAN, "ruler.py", "moreh_ruler_under_test", OLD)
    print("ruler under test: %s" % R.__proof_source__)

    if not hasattr(R, "ceiling_from_ledger"):
        raise AssertionError("ruler.py has no ceiling_from_ledger(): the sitting still publishes the "
                             "gate1.json snapshot as 'the reachable bar'")
    per, tot = R.ceiling_from_ledger(os.path.join(LESSONS, "ledger.jsonl"))
    snap = json.load(open(os.path.join(LESSONS, "gate1.json"), encoding="utf-8"))["per_syllable"]
    snap_att = sum(v["attempts"] for v in snap.values())
    snap_ok = sum(v["verified"] for v in snap.values())
    print("gate1.json snapshot : %d attempts -> %d passed = %.1f%%"
          % (snap_att, snap_ok, 100.0 * snap_ok / snap_att))
    print("ledger.jsonl now    : %d attempts -> %d passed = %.1f%%"
          % (tot["attempts"], tot["passed"], 100.0 * tot["pass_rate"]))
    assert tot["attempts"] > snap_att, "the ledger has not grown past the snapshot on this machine"
    drift = {s: (snap[s]["pass_rate"], per[s]["pass_rate"]) for s in sorted(per)
             if s in snap and abs(snap[s]["pass_rate"] - per[s]["pass_rate"]) > 0.0006}
    print("per-syllable rates that drifted: %s" % drift)
    assert len(drift) >= 1 and len(per) == 24, (len(drift), len(per))

    # the sitting must use the ledger, and say which source it used
    src = open(os.path.join(ORGAN, "ruler.py" + (".bak-rev-20260906" if OLD else "")), encoding="utf-8").read()
    assert "ceiling_source" in src, "loo-results.json does not say where its ceiling came from"
    assert "ceiling_gate1_snapshot" in src, "the stale snapshot is not kept beside the live number"

    # and STATUS.md must no longer publish 33.5% as the rate
    st = open(os.path.join(ORGAN, "STATUS.md"), encoding="utf-8").read()
    bar = u"| **תקרה — המורה עצמו**, דגימה אקראית בתוך החלונות | **26.7%** לניסיון | |"
    assert bar in st, "STATUS.md still publishes the stale ceiling in its gate-2 table"
    print("STATUS.md gate-2 table carries the measured 26.7%: yes")
    print("PROOF MOREH-11 PASSED")


try:
    main()
except Exception as e:
    print("PROOF MOREH-11 FAILED: %s: %s" % (type(e).__name__, e))
    sys.exit(1)
