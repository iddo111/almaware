# -*- coding: utf-8 -*-
"""CODER-09 -- train.pid names a process that has not existed since 2026-09-04.

  $ cat train.pid            -> 3905469
  $ ps -p 3905469            -> no such process
  $ cat status.json | pid    -> 1594129        (the real trainer)
  $ stat train.pid           -> Sep  4 19:36   (the very first launch)

start_direct() wrote it once; every launch since has gone through systemd, which
never touches it. This watchdog survives the lie (the pidfile check fails and the
/proc scan finds the truth) but WATCHDOG.md still lists train.pid as a liveness
source, so any other tool or human reading it sees a dead job. A stale liveness
file is exactly the "usefulness check that died quietly" shape.

Run:  python proof_CODER-09.py ../orig/watchdog.py   -> FAIL
      python proof_CODER-09.py ../new/watchdog.py    -> PASS
"""
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _proofkit import Proof, load_module, target_from_argv  # noqa: E402

target = target_from_argv("new/watchdog.py")
p = Proof("CODER-09", target)
w = load_module(target)

if not hasattr(w, "sync_pidfile"):
    p.fail("sync_pidfile() exists",
           "nothing ever corrects train.pid; it holds whatever the first direct "
           "launch wrote, forever")
    p.done()

with tempfile.TemporaryDirectory() as t:
    pf = pathlib.Path(t) / "train.pid"

    # the real situation on the box at 12:03 today
    pf.write_text("3905469")
    msg = w.sync_pidfile({"pid": 1594129}, 1594129, path=pf)
    p.check(pf.read_text().strip() == "1594129",
            "a stale pid is corrected from status.json",
            "train.pid=%r msg=%r" % (pf.read_text().strip(), msg))

    # already correct -> no churn
    msg2 = w.sync_pidfile({"pid": 1594129}, 1594129, path=pf)
    p.check(msg2 is None, "an already-correct pidfile is left alone", repr(msg2))

    # nothing running -> the file must not keep claiming a pid
    w.sync_pidfile(None, None, path=pf)
    p.check(not pf.exists(),
            "with no trainer at all, train.pid is removed rather than left lying",
            "a pidfile naming a dead process is worse than no pidfile")

    # status.json missing but /proc found one -> use that
    pf2 = pathlib.Path(t) / "p2.pid"
    w.sync_pidfile(None, 4242, path=pf2)
    p.check(pf2.exists() and pf2.read_text().strip() == "4242",
            "the /proc-scan pid is used when status.json has none")

# and it must run on every pass, not only when something is wrong
src = pathlib.Path(target).read_text(encoding="utf-8")
p.check("sync_pidfile(status_data, pid)" in src,
        "sync_pidfile is called from the main check pass",
        "a correction that only runs on the failure path never runs on a healthy run")

p.done()
