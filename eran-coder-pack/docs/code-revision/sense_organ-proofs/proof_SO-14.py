# -*- coding: utf-8 -*-
"""PROOF SO-14 -- eval on a label the page hides: gates_v3.py:50 and 367-370 say a
review_flagged winner is NEVER auto-celebrated and Iddo's listen is the only promotion.
The page painted exactly such a winner GREEN with "below the human mean" and kept the flag
in a table column. On 2026-09-06 all 12 non-control arms are flagged.

    python3 proof_SO-14.py ~/eran-throat-listen.py.bak-rev-20260906   -> FAIL
    python3 proof_SO-14.py ~/eran-throat-listen.py                    -> PASS

Renders the REAL current champion (flagged, below the mean) -- the exact case that went out
green -- on a throwaway localhost port.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _proof_listen as L                                           # noqa: E402

PATH = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else "~/eran-throat-listen.py")
print("PROOF SO-14 against %s" % PATH)
mod = L.load(PATH)
checks = []

res = mod.champions()
rows = res[0] if isinstance(res, tuple) else res
ba = mod.best_of(rows, "ba") or mod.best_of(rows, "v5live-ba")
print("  (champion on disk: %s wdist %.4f flagged=%s)"
      % (ba["arm"], ba["wdist"], ba["flagged"]) if ba else "  (no ba champion)")

status, body = L.get(mod, "/")
html = body.decode("utf-8", "replace")
checks.append(("the page renders", status == 200, "HTTP %s, %d bytes" % (status, len(body))))

green = '<div class="big">' in html
checks.append(("a flagged champion is NOT painted green",
               (not ba or not ba["flagged"]) or not green,
               "flagged=%s, green headline present=%s" % (bool(ba and ba["flagged"]), green)))
checks.append(("the headline carries the warn class instead",
               'class="big warn"' in html, "warn headline present=%s" % ('class="big warn"' in html)))
checks.append(("the headline says it is waiting for HIS ear",
               "מסומן לביקורת" in html, "flag sentence in headline area=%s"
               % ("מסומן לביקורת" in html)))
head_cut = html.split('<h2>', 1)[0]
checks.append(("the flag is on the clip card, not only in the table",
               html.count("⚑") >= 2 and "⚑" in html.split('כל הזרועות', 1)[0],
               "⚑ occurrences=%d, before the table=%s"
               % (html.count("⚑"), "⚑" in html.split('כל הזרועות', 1)[0])))
checks.append(("(evidence) the headline block: %s" % head_cut[head_cut.find('<div class="big'):
                                                              head_cut.find('<div class="big') + 90]
               .replace("\n", " "), True, "shown for the record"))

L.report(checks)
