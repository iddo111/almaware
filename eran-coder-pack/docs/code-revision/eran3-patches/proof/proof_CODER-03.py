# -*- coding: utf-8 -*-
"""CODER-03 (watchdog half) -- a finished run is not a broken one.

max-steps is 1600. At step 1600 train.py writes status 'finished' and exits 0;
systemd (Restart=on-failure) correctly leaves the unit inactive; the watchdog
then saw `not alive` + ENABLED and restarted it. train.py would reload the 47 GB
checkpoint (~8 minutes), run `for step in range(1600, 1600)` -- zero iterations --
write 'finished', exit 0, and be restarted again, through the 60/120/240/480 s
backoff until the 4/hour cap escalated the completed run to BROKEN.

WHAT COMES AFTER STEP 1600 IS NOT FIXED HERE. A second cosine cycle over the same
756 M tokens, a new corpus, or a stop with the model exported are three different
answers and they are Iddo's to give -- see NEEDS-IDDO-coder.md. This proof only
covers the half that is unambiguous: do not restart-loop a completed run.

Run:  python proof_CODER-03.py ../orig/watchdog.py   -> FAIL
      python proof_CODER-03.py ../new/watchdog.py    -> PASS
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _proofkit import Proof, load_module, target_from_argv  # noqa: E402

target = target_from_argv("new/watchdog.py")
p = Proof("CODER-03", target)
w = load_module(target)

FINISHED = {"status": "finished", "step": 1600, "max_steps": 1600, "loss": 0.9}
MIDRUN = {"status": "running", "step": 53, "max_steps": 1600, "loss": 1.06829}
STOPPED = {"status": "stopped", "step": 40, "max_steps": 1600}

if not hasattr(w, "run_completed"):
    p.fail("run_completed() exists",
           "nothing distinguishes 'the 1600-step pass is done' from 'the process "
           "died'; both are just `not alive`")
else:
    rc = w.run_completed
    p.check(rc(FINISHED) is True, "step 1600/1600 + 'finished' is a completed run")
    p.check(rc(MIDRUN) is False, "a running job is not 'completed'")
    p.check(rc(STOPPED) is False, "a human stop is not 'completed'")
    p.check(rc(None) is False, "no status.json is not 'completed'")
    p.check(rc({"status": "finished", "step": 40, "max_steps": 1600}) is False,
            "'finished' below max_steps is not accepted as complete")

# The decision must actually be wired: a completed run must not book a restart,
# and must not read as BROKEN.
src = pathlib.Path(target).read_text(encoding="utf-8")
after_gate = src.split("needs_restart = (not alive) or hung")[-1]
p.check("run_completed(" in after_gate,
        "run_completed() gates the restart decision",
        "defining it is not enough -- `needs_restart = not alive` still fires")
p.check('verdict = "VERIFIED"' in after_gate.split("run_completed(status_data) and not alive")[-1][:400]
        if "run_completed(status_data) and not alive" in after_gate else False,
        "a completed run reports VERIFIED, not BROKEN",
        "430 h of GB10 time ending in a red verdict trains humans to ignore the verdict")

# Simulate the two passes that used to loop.
booked = 0
for _ in range(2):
    alive = False
    needs_restart = not alive
    if needs_restart and hasattr(w, "run_completed") and w.run_completed(FINISHED):
        needs_restart = False
    booked += int(needs_restart)
p.check(booked == 0,
        "a completed run books zero restarts",
        "booked=%d -- each one costs an 8-minute 47 GB reload to run "
        "`range(1600, 1600)`" % booked)

p.done()
