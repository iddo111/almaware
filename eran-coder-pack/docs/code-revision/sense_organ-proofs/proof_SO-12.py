# -*- coding: utf-8 -*-
"""PROOF SO-12 -- hand-threshold: HUMAN_MEAN = 3.9115 was a constant in the page while
every best.json carries its own real_wdist_mean (ba 3.91147, ma 3.90444 -- per unit, per
calibration). A recalibration, or simply looking at ma, desynchronised the headline in
silence.

    python3 proof_SO-12.py ~/eran-throat-listen.py.bak-rev-20260906   -> FAIL
    python3 proof_SO-12.py ~/eran-throat-listen.py                    -> PASS
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _proof_listen as L                                           # noqa: E402

PATH = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else "~/eran-throat-listen.py")
print("PROOF SO-12 against %s" % PATH)
mod = L.load(PATH)
checks = []

res = mod.champions()
rows = res[0] if isinstance(res, tuple) else res
have = [r for r in rows if r.get("human_mean") is not None]
checks.append(("each arm carries its OWN human mean from its own best.json",
               len(have) == len(rows) and bool(rows),
               "%d/%d rows have human_mean; e.g. %s" % (
                   len(have), len(rows),
                   [(r["arm"], round(r["human_mean"], 4)) for r in have[:3]])))

means = sorted({round(r["human_mean"], 4) for r in have})
checks.append(("the page can tell two calibrations apart (ba 3.9115 vs ma 3.9044)",
               len(means) > 1, "distinct means on disk right now: %s" % means))

# a champion whose own calibration says 5.0 must be judged against 5.0, not against 3.9115
fake = {"arm": "ba-proof", "ver": "proof", "wdist": 4.0, "wav": "", "mtime": 0,
        "near": [("ba", 4.0), ("ma", 4.4)], "flagged": False, "unit": "ba",
        "human_mean": 5.0, "spec": "x", "calib": "SANITY-PROOF.json"}
try:
    head = mod.headline(fake)
    ok = ("5.0000" in head) and ("מתחת" in head)
    got = "headline says %s" % ("under its own 5.0000" if ok else head[:160])
except AttributeError:
    ok, got = False, ("no headline() -- the comparison is inlined against the constant "
                      "HUMAN_MEAN, so an arm calibrated at 5.0 would still be judged "
                      "against 3.9115 and read 'above by 0.0885'")
checks.append(("the headline is judged against the champion's own calibration", ok, got))

status, body = L.get(mod, "/")
html = body.decode("utf-8", "replace")
checks.append(("the page says WHERE the human mean came from",
               "best.json" in html or "גיבוי" in html,
               "footer/headline names the source: %s" % ("best.json" in html)))
checks.append(("the page still renders", status == 200,
               "HTTP %s, %d bytes" % (status, len(body))))

L.report(checks)
