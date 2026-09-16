# -*- coding: utf-8 -*-
"""CODER-10 -- restarts_last_hour was not filtered by the hour.

watchdog-status.json at 12:03:41 reported `restarts_last_hour: 4`. The four
timestamps in watchdog-state.json decode to 04:23:56, 04:28:57, 05:11:56 and
05:16:57 -- seven hours earlier. The number was
`len(state.get("restart_history", []))`, unfiltered; the hour window lives only
inside restart_allowed(), which is reached only when a restart is NEEDED. So a
healthy run reports a frightening count forever, and a human reading the status
file cannot tell a run that is crash-looping now from one that had trouble
overnight.

Filter where the number is REPORTED, not only where it is enforced.

Run:  python proof_CODER-10.py ../orig/watchdog.py   -> FAIL
      python proof_CODER-10.py ../new/watchdog.py    -> PASS
"""
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _proofkit import Proof, load_module, target_from_argv  # noqa: E402

target = target_from_argv("new/watchdog.py")
p = Proof("CODER-10", target)
w = load_module(target)

now = time.time()
# the exact state on the box today: 4 restarts, all ~7 h old
OLD_STATE = {"restart_history": [now - 7 * 3600 - 60, now - 7 * 3600,
                                 now - 6.8 * 3600, now - 6.7 * 3600]}
MIXED = {"restart_history": [now - 7 * 3600, now - 1800, now - 600]}

if not hasattr(w, "restarts_last_hour"):
    p.fail("restarts_last_hour() exists",
           "the reported count is len(restart_history) with no time window at all")
else:
    p.check(w.restarts_last_hour(OLD_STATE, now) == 0,
            "four 7-hour-old restarts report as 0 in the last hour",
            "got %d" % w.restarts_last_hour(OLD_STATE, now))
    p.check(w.restarts_last_hour(MIXED, now) == 2,
            "only the entries inside the hour are counted",
            "got %d of 3" % w.restarts_last_hour(MIXED, now))
    p.check(w.restarts_last_hour({}, now) == 0, "an empty state is 0, not a crash")

src = pathlib.Path(target).read_text(encoding="utf-8")
p.check('"restarts_last_hour": len(state.get("restart_history", []))' not in src,
        "the status file no longer reports the unfiltered length",
        "the helper existing does not help if the report still bypasses it")
p.check('"restarts_last_hour": restarts_last_hour(' in src,
        "the status file reports the filtered count")

p.done()
