# -*- coding: utf-8 -*-
"""_rev20260906.py — shared loader for the 2026-09-06 code-revision proofs.

Every proof_DW-*.py beside this file runs against the SAME organism tree twice:

    python3 proof_DW-01.py --mode old    -> must FAIL  (the code that ran 16 days)
    python3 proof_DW-01.py               -> must PASS  (the fixed code)

`--mode old` works by copying the tree's *.py into a scratch directory and then
overwriting every file that has a `.bak-rev-20260906` sibling with that backup.
So "old" is not a story about the old code, it is the old code.

Pure stdlib, no numpy, no torch, no network, no disk outside a tempdir — safe to
run on eran4 under `nice -n 19` while dmidi-life is alive. It never touches
state/, food/, songs/ or feedback/, and it never signals a process.
"""
import os
import shutil
import sys
import tempfile

REV = ".bak-rev-20260906"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUBDIRS = ("", "body", "voice")


def build_tree(old):
    """Scratch copy of the organism's python tree; old=True swaps in the backups."""
    dst = tempfile.mkdtemp(prefix="dw-rev-%s-" % ("old" if old else "new"))
    swapped = []
    for sub in SUBDIRS:
        src_d = os.path.join(ROOT, sub)
        dst_d = os.path.join(dst, sub)
        if not os.path.isdir(src_d):
            continue
        os.makedirs(dst_d, exist_ok=True)
        for name in sorted(os.listdir(src_d)):
            src = os.path.join(src_d, name)
            if not os.path.isfile(src):
                continue
            if name.endswith(".py"):
                shutil.copy2(src, os.path.join(dst_d, name))
            elif old and name.endswith(REV):
                target = name[:-len(REV)]
                shutil.copy2(src, os.path.join(dst_d, target))
                swapped.append(os.path.join(sub, target))
    if old and not swapped:
        raise SystemExit("proof: --mode old needs the *%s backups; none found "
                         "under %s" % (REV, ROOT))
    return dst, swapped


def enter(mode):
    """Build the tree for `mode` and put it on sys.path. Returns (tree, swapped)."""
    tree, swapped = build_tree(mode == "old")
    for p in (os.path.join(tree, "voice"), os.path.join(tree, "body"), tree):
        sys.path.insert(0, p)
    return tree, swapped


def mode_from_argv(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if "--mode" in argv:
        return argv[argv.index("--mode") + 1]
    return "new"


class Checks:
    """The tiniest possible check harness: prints, remembers, sets the exit code."""

    def __init__(self, title, mode):
        self.failed = []
        self.mode = mode
        print("%s  [mode=%s]" % (title, mode))

    def check(self, name, ok, detail=""):
        print("  [%s] %s  %s" % ("PASS" if ok else "FAIL", name, detail))
        if not ok:
            self.failed.append(name)
        return ok

    def done(self):
        if self.failed:
            print("\nFAILURES: %s" % self.failed)
            print("EXPECTED for --mode old: this proof must fail against the "
                  "pre-revision code." if self.mode == "old" else "")
            sys.exit(1)
        print("\nALL PASS")
        sys.exit(0)
