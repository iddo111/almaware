"""KAV code-revision 2026-09-06 — the proof harness.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

Every proof in this directory must FAIL against the code as it stood before the
revision and PASS against the code as it stands now. It is run twice:

    python proofs/proof_KAV-05.py old      -> must print FAIL and exit 1
    python proofs/proof_KAV-05.py new      -> must print PASS and exit 0

"old" is rebuilt from the `.bak-rev-20260906` backups into a sibling directory of
kav/ -- `holobrain/_kav_old_rev/` -- because that is the ONLY placement at which
mesh.our_corpus()'s `_ROOT = __file__/../../..` still resolves to D:\\CLAUDE and the
four real STL parts are found. Anything shallower or deeper silently loses them, and
a proof measured against a 19-shape corpus would be measuring the wrong organ.

The proofs test the CODE, not any running process. KAV has no server, no port, no
systemd unit and no checkpoint, so nothing here restarts, stops or signals anything.
"""
from __future__ import annotations

import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KAV = os.path.abspath(os.path.join(HERE, os.pardir))
HOLO = os.path.abspath(os.path.join(KAV, os.pardir))
OLD = os.path.join(HOLO, "_kav_old_rev")
SUFFIX = ".bak-rev-20260906"


def build_old() -> str:
    """The organ as it stood before this revision, at the same depth as kav/."""
    if os.path.isdir(OLD):
        shutil.rmtree(OLD)
    os.makedirs(os.path.join(OLD, "tests"))
    for sub in ("", "tests"):
        src = os.path.join(KAV, sub) if sub else KAV
        for fn in os.listdir(src):
            if fn.endswith(".py"):
                shutil.copy2(os.path.join(src, fn), os.path.join(OLD, sub, fn))
    # legacy/ is where the retired rulers were MOVED to; before the revision they
    # sat in the organ's own directory, so that is where "old" must have them.
    leg = os.path.join(KAV, "legacy")
    if os.path.isdir(leg):
        for fn in os.listdir(leg):
            if fn.endswith(".py"):
                shutil.copy2(os.path.join(leg, fn), os.path.join(OLD, fn))
        for fn in os.listdir(leg):                    # ...as they were before the move
            if fn.endswith(SUFFIX):
                shutil.copy2(os.path.join(leg, fn),
                             os.path.join(OLD, fn[:-len(SUFFIX)]))
    # and finally the backups win over everything
    for sub in ("", "tests"):
        src = os.path.join(KAV, sub) if sub else KAV
        for fn in os.listdir(src):
            if fn.endswith(SUFFIX):
                shutil.copy2(os.path.join(src, fn),
                             os.path.join(OLD, sub, fn[:-len(SUFFIX)]))
    for fn in os.listdir(KAV):
        if fn.endswith(".stl"):
            shutil.copy2(os.path.join(KAV, fn), os.path.join(OLD, fn))
    return OLD


def organ(variant: str) -> str:
    """Put the requested variant of the organ first on sys.path and return its dir."""
    d = build_old() if variant == "old" else KAV
    for p in (d, os.path.join(d, "tests")):
        if p in sys.path:
            sys.path.remove(p)
    sys.path.insert(0, d)
    return d


def run(check) -> None:
    """check(organ_dir) -> None. Raise AssertionError to fail; print freely."""
    variant = sys.argv[1] if len(sys.argv) > 1 else "new"
    assert variant in ("old", "new"), "usage: proof_KAV-xx.py old|new"
    d = organ(variant)
    print(f"--- {os.path.basename(sys.argv[0])} [{variant}] organ={d}")
    try:
        check(d)
    except AssertionError as e:
        print(f"FAIL [{variant}] {e}")
        raise SystemExit(1)
    except Exception as e:                       # a crash is a failure, not an error
        print(f"FAIL [{variant}] {type(e).__name__}: {e}")
        raise SystemExit(1)
    print(f"PASS [{variant}]")
    raise SystemExit(0)
