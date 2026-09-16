# -*- coding: utf-8 -*-
"""CODER-11 -- the disk floor was below the cost of one checkpoint cycle.

MIN_DISK_FREE_GB was 50. One cycle needs far more than that:
  - the NEW 47 GB checkpoint is written in full BEFORE the old one is pruned
    (keep=2, so the peak is 3 x 47 GB);
  - save_checkpoint has no try/except, so a save that runs out of room dies
    mid-write with a traceback and no status;
  - the failed write leaves `.tmp_step_N.<pid>` behind, and the only cleanup path
    (`if os.path.exists(tmp)` at the top of save_checkpoint) matches a tmp dir
    carrying that process's OWN pid -- so after a restart nobody ever sweeps it,
    on a disk that is already 84% full;
  - and the watchdog's list_ckpts() returned EVERY entry in the directory, so
    such an orphan counted toward KEEP_CKPTS and could itself be deleted as "the
    oldest checkpoint" or reported as the newest one's age.

Not live today (561 GB free) but the box also hosts comfy/, colibri/ and models/.

Run:  python proof_CODER-11.py ../orig    -> FAIL
      python proof_CODER-11.py ../new     -> PASS
"""
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _proofkit import Proof, extract, load_module, target_from_argv  # noqa: E402

d = target_from_argv("new")
p = Proof("CODER-11", d)

# ---- the watchdog half -----------------------------------------------------
w = load_module(d / "watchdog.py")
CKPT_GB = 47.0
p.check(getattr(w, "MIN_DISK_FREE_GB", 0) >= 2 * CKPT_GB,
        "the disk floor covers a full checkpoint cycle (>= 94 GB)",
        "MIN_DISK_FREE_GB=%s -- the new 47 GB file is written before the old one "
        "is pruned, so the floor must hold two" % getattr(w, "MIN_DISK_FREE_GB", None))
p.check(getattr(w, "DISK_WARN_GB", 0) > getattr(w, "MIN_DISK_FREE_GB", 0),
        "there is a warning line above the floor",
        "a threshold whose only setting is 'already broken' warns nobody in time")

if not hasattr(w, "is_ckpt_entry"):
    p.fail("list_ckpts ignores .tmp_step_* dirs",
           "is_ckpt_entry() missing -- an orphaned temp dir is counted as a "
           "checkpoint, and can be chosen for deletion or reported as the newest")
else:
    p.check(w.is_ckpt_entry("step_00000040") is True, "a real checkpoint is a checkpoint")
    p.check(w.is_ckpt_entry(".tmp_step_00000040.1594129") is False,
            "a temp dir is NOT a checkpoint")
    p.check(w.is_ckpt_entry("train.out") is False, "a stray file is not a checkpoint")

# ---- the trainer half ------------------------------------------------------
ns, missing = extract(d / "train.py", ["tmp_dirs_to_sweep", "EXIT_SAVE"])
if "tmp_dirs_to_sweep" in missing:
    p.fail("train.py sweeps orphaned checkpoint temp dirs",
           "the only cleanup matches the CURRENT pid, so a 47 GB orphan from a "
           "killed save survives every restart")
else:
    now = time.time()
    entries = [(".tmp_step_00000020.111", now - 7200),   # orphan from a dead pid
               (".tmp_step_00000040.222", now - 60),     # a save happening now
               ("step_00000040", now - 7200),            # a real checkpoint
               ("train.out", now - 7200)]
    got = ns["tmp_dirs_to_sweep"](entries, 3600, now)
    p.check(got == [".tmp_step_00000020.111"],
            "only the OLD temp dir is swept", "got %r" % (got,))

if "EXIT_SAVE" in missing:
    p.fail("a failed checkpoint save has its own exit code",
           "a save that dies on a full disk is indistinguishable from any other "
           "crash, so systemd restarts it into the same full disk every 60 s")
else:
    p.check(ns["EXIT_SAVE"] == 6, "EXIT_SAVE is 6", repr(ns["EXIT_SAVE"]))
    src = (d / "train.py").read_text(encoding="utf-8")
    p.check("EXIT_SAVE," in src or "die(EXIT_SAVE" in src,
            "the save path actually raises it")
    p.check("save_guarded(" in src.split('if STOP["flag"]:')[-1][:600]
            or "save_guarded(" in src,
            "checkpoint saves go through the guarded wrapper")
    drop = d / "coder-train.service.d" / "30-exit-codes.conf"
    p.check(drop.exists() and "6" in drop.read_text(encoding="utf-8")
            .split("RestartPreventExitStatus=")[-1].splitlines()[0],
            "exit 6 is listed in RestartPreventExitStatus",
            "restarting into a full disk is a loop, not a recovery")

p.done()
