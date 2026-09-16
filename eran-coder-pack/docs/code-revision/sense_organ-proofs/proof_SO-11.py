# -*- coding: utf-8 -*-
"""PROOF SO-11 -- stale-config: ROOT was hardcoded to ~/throat-search-v3, so the v4 tree
(16 arms, including every v5live arm and the newest writes on the box, 2026-09-02 07:38)
never appeared on Iddo's page. And wdist is only comparable inside ONE ear, so rows from a
tree judged by a different ear3 spec must be named, not silently ladder-mixed.

    python3 proof_SO-11.py ~/eran-throat-listen.py.bak-rev-20260906   -> FAIL
    python3 proof_SO-11.py ~/eran-throat-listen.py                    -> PASS

Serves one page on 127.0.0.1:<ephemeral>. :8845 and pid 3252 are untouched.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _proof_listen as L                                           # noqa: E402

PATH = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else "~/eran-throat-listen.py")
print("PROOF SO-11 against %s" % PATH)
mod = L.load(PATH)
checks = []

res = mod.champions()
rows = res[0] if isinstance(res, tuple) else res
excluded = res[1] if isinstance(res, tuple) else []
arms = [r["arm"] for r in rows]
checks.append(("the leaderboard reaches every throat-search-v* tree",
               any(a.startswith("v5live-") for a in arms),
               "%d rows, v5live rows=%d" % (len(rows),
                                            sum(1 for a in arms if a.startswith("v5live-")))))
checks.append(("every row says which tree it came from",
               bool(rows) and all(r.get("ver") for r in rows),
               "ver of first row = %r" % (rows[0].get("ver") if rows else None)))
checks.append(("rows judged by a different ear are excluded, not mixed in",
               isinstance(res, tuple) and len(excluded) > 0,
               "excluded=%s" % [("%s/%s" % (r["ver"], r["arm"])) for r in excluded[:6]]))
specs = {r.get("spec") for r in rows}
checks.append(("every row on the ladder shares one ear3 spec_hash",
               len(specs) == 1 and None not in specs,
               "specs=%s" % [str(s)[:12] for s in specs]))

status, body = L.get(mod, "/")
html = body.decode("utf-8", "replace")
checks.append(("the page still renders", status == 200, "HTTP %s, %d bytes" % (status, len(body))))
checks.append(("the page shows a v5live arm",
               "v5live-" in html, "v5live in page: %s" % ("v5live-" in html)))

L.report(checks)
