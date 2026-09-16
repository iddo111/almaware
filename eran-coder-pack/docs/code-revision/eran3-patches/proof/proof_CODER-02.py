# -*- coding: utf-8 -*-
"""CODER-02 -- the exit-code contract must survive contact with the watchdog.

train.py documents: exit 1 = config error, exit 3 = non-finite loss/grad ("do not
restart blindly"), exit 5 = hold-out leak ("never restart"). The unit voided all
of it (Restart=on-failure, RestartPreventExitStatus empty) and the watchdog
compounded it: its whole status classifier sits inside `if alive:`, so when the
process was DEAD, status.json saying 'crash_nonfinite_loss' was never read and
`needs_restart = (not alive)` fired anyway -- the exact opposite of its own
docstring ("bad loss ... reported only, never fixed by a restart").

The data order is a pure function of (seed, step), so the same NaN returns on
every resume: an endless loop of ~9-minute 47 GB reloads.

Run:  python proof_CODER-02.py ../orig/watchdog.py   -> FAIL
      python proof_CODER-02.py ../new/watchdog.py    -> PASS
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _proofkit import Proof, load_module, target_from_argv  # noqa: E402

target = target_from_argv("new/watchdog.py")
p = Proof("CODER-02", target)
w = load_module(target)

if not hasattr(w, "refuse_restart_reason"):
    p.fail("refuse_restart_reason() exists",
           "the watchdog has no way to say 'this dead run must NOT be restarted'; "
           "needs_restart = (not alive) is the whole decision")
else:
    r = w.refuse_restart_reason
    p.check(bool(r("crash_nonfinite_loss", 0)),
            "crash_nonfinite_loss refuses a restart", repr(r("crash_nonfinite_loss", 0)))
    p.check(bool(r("crash_nonfinite_grad", 0)),
            "crash_nonfinite_grad refuses a restart")
    p.check(bool(r(None, 3)), "exit 3 (non-finite) refuses a restart")
    p.check(bool(r(None, 5)), "exit 5 (hold-out leak) refuses a restart")
    p.check(bool(r(None, 1)), "exit 1 (config error) refuses a restart")
    p.check(r(None, 4) is None,
            "exit 4 (CUDA OOM) is STILL restartable",
            "an OOM can clear when the other job on this GPU finishes -- refusing "
            "it too would be over-correcting")
    p.check(r("running", 0) is None, "a healthy run is not blocked")
    p.check(r("crash_oom", 4) is None, "crash_oom is not blocked")
    p.check(r(None, None) is None, "an unreadable exit code does not block by itself")

# The classifier must be reachable when the process is DEAD -- that is the whole
# point. In the old file the CRASH_STATES branch lives inside `if alive:`.
src = pathlib.Path(target).read_text(encoding="utf-8")
p.check("refuse_restart_reason((status_data or {}).get(\"status\")" in src
        or "refuse_restart_reason(" in src.split("needs_restart = (not alive) or hung")[-1],
        "the refusal is consulted on the not-alive path",
        "a refusal that only runs while the process is alive cannot stop a restart loop")

p.done()
