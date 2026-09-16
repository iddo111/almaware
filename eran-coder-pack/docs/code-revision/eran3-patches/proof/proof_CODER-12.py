# -*- coding: utf-8 -*-
"""CODER-12 -- a resume checks the geometry and nothing else.

load_checkpoint() compares precision, seq_len and block_size against the
checkpoint and dies on a mismatch. It does NOT compare lr, warmup, max_steps,
min_lr_ratio, weight_decay, clip, seed -- or the CORPUS PATHS. Every one of those
is re-read from train.config.json on every start, and the watchdog restarts this
run with a fixed command line (`python3 train.py --resume auto`), so an edit to
that file between two restarts silently reshapes the cosine schedule, or swaps
the food, with only the boot-time config echo in train.out as a trace.

The config WAS edited mid-life once already (2026-09-05 14:36: grad-accum 8->128,
lr 1e-5->4e-5, max-steps 8000->1600). That edit was done correctly, with a fresh
ckpt-dir -- by discipline, not by any check in the code.

Also proved here: the --ckpt-dir default (the non-Iddo half of CODER-13). The old
default was `<out>/ckpt` -- the ABANDONED batch-8 run at step 1017, 95 GB of it.
`train.py --resume auto` with any config lacking a ckpt-dir key (and
train.config.json.bak-mb1ga8 is exactly that) would have silently resumed that
dead run at block 8 and reported it as normal. Deleting those 98 GB is Iddo's
call; refusing to GUESS a checkpoint directory is not.

Run:  python proof_CODER-12.py ../orig/train.py   -> FAIL
      python proof_CODER-12.py ../new/train.py    -> PASS
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _proofkit import Proof, extract, target_from_argv  # noqa: E402

target = target_from_argv("new/train.py")
p = Proof("CODER-12", target)
src = pathlib.Path(target).read_text(encoding="utf-8")

ns, missing = extract(target, ["config_drift", "CONFIG_DRIFT_KEYS"])
if missing:
    p.fail("config_drift() exists",
           "missing %r -- nothing compares the checkpoint's settings with this "
           "launch's, so a resume can continue one run under another run's "
           "hyperparameters" % (missing,))
else:
    cd = ns["config_drift"]

    class A(object):
        pass

    prev = {"lr": 1e-05, "warmup": 20, "max_steps": 8000, "weight_decay": 0.1,
            "clip": 1.0, "seed": 1337, "grad_accum": 8,
            "corpus": "~/coder-train/corpus/domain_jsonl"}

    same = A()
    for k, v in prev.items():
        setattr(same, k, v)
    p.check(cd(prev, same) == [], "an unchanged config reports no drift")

    # the real 2026-09-05 14:36 edit
    edited = A()
    for k, v in prev.items():
        setattr(edited, k, v)
    edited.lr = 4e-05
    edited.max_steps = 1600
    edited.grad_accum = 128
    got = cd(prev, edited)
    keys = sorted(k for k, _, _ in got)
    p.check(keys == ["grad_accum", "lr", "max_steps"],
            "the lr / max-steps / grad-accum edit is caught", "got %r" % (keys,))

    swapped = A()
    for k, v in prev.items():
        setattr(swapped, k, v)
    swapped.corpus = "~/coder-train/corpus/other_jsonl"
    p.check([k for k, _, _ in cd(prev, swapped)] == ["corpus"],
            "a CORPUS swap is caught",
            "changing what the model is fed, mid-run, must never be silent")

    p.check(cd(None, edited) == [],
            "a checkpoint with no recorded args does not fabricate drift")
    p.check("max_steps" in ns["CONFIG_DRIFT_KEYS"] and "corpus" in ns["CONFIG_DRIFT_KEYS"],
            "the watched set includes the schedule AND the food")

    # wiring: it must die, not just log
    p.check("config_drift(state.get(\"args\"), args)" in src,
            "load_checkpoint() calls it on every resume")
    tail = src.split("config_drift(state.get(\"args\"), args)")[-1][:900]
    p.check("die(EXIT_ERROR" in tail,
            "drift stops the resume instead of being logged and ignored")
    p.check("accept_config_change" in tail,
            "there is an explicit way to say 'I meant it'",
            "a check with no escape hatch gets deleted the first time it is "
            "inconvenient")
    p.check("--accept-config-change" in src, "the flag is declared in the parser")

# ---- CODER-13's non-Iddo half: no guessed checkpoint directory -------------
p.check('args.ckpt_dir or os.path.join(args.out, "ckpt")' not in src,
        "--ckpt-dir has no silent default",
        "the default pointed at ~/coder-train/ckpt -- the abandoned batch-8 run "
        "at step 1017 (95 GB). A resume must never guess which run it is joining.")
p.check("--ckpt-dir is required" in src,
        "a missing ckpt-dir is refused with a readable reason")

p.done()
