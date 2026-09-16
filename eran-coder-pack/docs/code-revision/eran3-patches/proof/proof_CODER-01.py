# -*- coding: utf-8 -*-
"""CODER-01 -- 'deactivating' is not death, and a queued restart is not a failure.

The bug: watchdog.py:307 mapped 'deactivating' and 'activating' to False = dead,
and restart_via_systemd() waited on `systemctl restart` with run_cmd's 15 s
default while a graceful stop here takes 7-8 minutes (47 GB checkpoint). So one
real restart was booked TWICE -- once as "restart FAILED ... timed out after
15 seconds" (9 such lines in watchdog.log, 0 saying "restart OK") and again five
minutes later, when the unit was still writing that checkpoint, as "dead".
Two real events in an hour burned all four crash-loop slots and escalated a
healthy run to BROKEN.

Run:  python proof_CODER-01.py ../orig/watchdog.py   -> FAIL
      python proof_CODER-01.py ../new/watchdog.py    -> PASS
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _proofkit import Proof, load_module, target_from_argv  # noqa: E402

target = target_from_argv("new/watchdog.py")
p = Proof("CODER-01", target)
w = load_module(target)

# ---- 1. the mapping itself -------------------------------------------------
if not hasattr(w, "map_systemd_state"):
    p.fail("map_systemd_state() exists",
           "no pure mapping of `systemctl is-active` output -- the busy states "
           "cannot be named, let alone spared")
else:
    m = w.map_systemd_state
    p.check(m("deactivating") == "busy", "'deactivating' maps to busy", repr(m("deactivating")))
    p.check(m("activating") == "busy", "'activating' maps to busy", repr(m("activating")))
    p.check(m("active") == "active", "'active' maps to active")
    p.check(m("inactive") == "inactive", "'inactive' maps to inactive")
    p.check(m("failed") == "inactive", "'failed' maps to inactive")
    p.check(m("") == "unknown", "empty answer maps to unknown, NOT dead")

# ---- 2. tri->four state on the real entry point ----------------------------
calls = []


def fake_run_cmd(args, timeout=15):
    calls.append(list(args))
    if "list-unit-files" in args:
        return 0, "coder-train.service enabled enabled\n", ""
    if "is-active" in args:
        return 3, fake_run_cmd.state + "\n", ""
    return 0, "", ""


fake_run_cmd.state = "deactivating"
w.run_cmd = fake_run_cmd
w.find_train_pid = lambda: None

try:
    res = w.determine_liveness()
except Exception as e:
    res = None
    p.fail("determine_liveness() survives a busy unit", "%s: %s" % (type(e).__name__, e))

if res is not None:
    if len(res) != 4:
        p.fail("determine_liveness() reports unit_busy",
               "returned %d values %r -- there is no channel to say 'in motion', so "
               "the caller can only read this as dead" % (len(res), res))
    else:
        alive, pid, via, busy = res
        p.check(busy is True, "unit_busy True while deactivating", repr(res))
        p.check(alive is False, "not reported alive while deactivating")

# ---- 3. the restart is QUEUED, not waited on -------------------------------
calls[:] = []
ok, detail = w.restart_via_systemd()
restart_call = [c for c in calls if "restart" in c]
p.check(bool(restart_call), "restart_via_systemd calls systemctl restart")
if restart_call:
    p.check("--no-block" in restart_call[0],
            "restart is issued with --no-block",
            "argv=%r -- without it systemctl blocks for the whole 7-8 minute stop "
            "and run_cmd's 15 s timeout turns every SUCCESS into a reported FAILURE"
            % (restart_call[0],))
p.check(ok is True, "a queued restart reports success", repr(detail))

# ---- 4. two passes, one real event: only ONE restart is booked -------------
# Pass A: unit deactivating (our own 8-minute stop). Pass B: 5 minutes later,
# still deactivating.
booked = 0
state = {}
now = 1000.0
for pass_no in (1, 2):
    try:
        alive, pid, via, busy = w.determine_liveness()
    except ValueError:
        # old code: 3-tuple. It has no idea the unit is busy, so it books.
        alive, pid, via = w.determine_liveness()
        busy = False
    needs_restart = not alive
    if needs_restart and (busy or (hasattr(w, "pending_restart_active")
                                   and w.pending_restart_active(state, now))):
        needs_restart = False
    if needs_restart:
        booked += 1
        state["restart_pending_ts"] = now
    now += 300.0

p.check(booked <= 1,
        "one real restart event books at most one restart",
        "booked=%d (cap is %s/hour, so %d events per hour escalate a healthy run "
        "to BROKEN)" % (booked, getattr(w, "MAX_RESTARTS_PER_HOUR", "?"),
                        max(1, getattr(w, "MAX_RESTARTS_PER_HOUR", 4) // max(booked, 1))))

p.done()
