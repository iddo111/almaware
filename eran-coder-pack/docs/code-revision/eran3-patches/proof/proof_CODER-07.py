# -*- coding: utf-8 -*-
"""CODER-07 -- a SIGTERM on a save step wrote the same 47 GB checkpoint twice.

Measured in train.out on 2026-09-06:
  [01:25:09] checkpoint step 20 -> ckpt2/step_00000020 (47.0 GB, 365.6s)
  [01:32:04] checkpoint step 20 -> ckpt2/step_00000020 (47.0 GB, 415.0s)
  [01:32:.. ] stopped on signal

Two writes of an identical file: once for `done % save_every == 0`, once more for
the STOP flag twelve lines below. 13 minutes of a 900 s TimeoutStopSec spent
producing a file that already existed -- and the closer that gets to the timeout,
the closer systemd comes to SIGKILLing a half-written 47 GB checkpoint.

Run:  python proof_CODER-07.py ../orig/train.py   -> FAIL
      python proof_CODER-07.py ../new/train.py    -> PASS
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _proofkit import Proof, extract, target_from_argv  # noqa: E402

target = target_from_argv("new/train.py")
p = Proof("CODER-07", target)

ns, missing = extract(target, ["should_save_periodic", "should_save_on_stop"])
if missing:
    p.fail("the save decision is a testable expression",
           "missing %r -- the periodic save and the stop save are two independent "
           "`if`s that know nothing about each other, so both fire on the same step"
           % (missing,))
    p.done()

sp, ss = ns["should_save_periodic"], ns["should_save_on_stop"]

# ---- simulate the exact 01:25/01:32 sequence -------------------------------
def run_loop(save_every, stop_at_step, n_steps=3, start_step=0):
    """Mirror of train.py's per-step tail: periodic save, then the STOP branch."""
    saves = []
    last_saved = start_step
    for step in range(start_step, start_step + n_steps):
        done = step + 1
        if sp(done, save_every, last_saved):
            saves.append(("save-every", done))
            last_saved = done
        if done == stop_at_step:
            if ss(done, last_saved):
                saves.append(("SIGTERM", done))
                last_saved = done
            break
    return saves

saves = run_loop(save_every=1, stop_at_step=1)
p.check(len(saves) == 1,
        "SIGTERM landing ON a save step writes ONE checkpoint",
        "writes=%r -- each is 47 GB and ~400 s against TimeoutStopSec=900" % (saves,))

saves2 = run_loop(save_every=20, stop_at_step=3, n_steps=3)
p.check(saves2 == [("SIGTERM", 3)],
        "SIGTERM between save steps still writes a checkpoint",
        "the fix must not lose work: %r" % (saves2,))

p.check(sp(20, 20, 20) is False,
        "a step already saved is not saved again by the periodic branch")
p.check(sp(20, 20, 0) is True, "a normal save-every step still saves")
p.check(sp(21, 20, 0) is False, "a non-multiple step does not save")
p.check(sp(20, 0, 0) is False, "save_every=0 disables saving")
p.check(ss(41, 40) is True, "a stop on an unsaved step saves")

# ---- and it must be wired into the real loop ------------------------------
src = pathlib.Path(target).read_text(encoding="utf-8")
stop_branch = src.split('if STOP["flag"]:')[-1][:700]
p.check("should_save_on_stop(" in stop_branch,
        "the STOP branch actually consults it",
        "defining the helper changes nothing if the branch still saves blindly")
p.check("last_saved_step" in src,
        "the loop tracks which step is already on disk")
resume = src.split("last_saved_step = start_step")[-1][:200] if "last_saved_step = start_step" in src else ""
p.check(bool(resume),
        "the resume point counts as already saved",
        "otherwise a SIGTERM immediately after a resume re-writes the checkpoint "
        "it just finished reading")

p.done()
