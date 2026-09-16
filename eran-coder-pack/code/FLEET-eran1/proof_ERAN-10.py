#!/usr/bin/env python3
"""proof_ERAN-10.py -- checkpoints nobody loads must not grow without bound.

Defect: snap-<beat>.json.gz is written every SNAP_EVERY beats (23 s of wall
clock) and NO script in this tree ever reads one -- eran-save.sh already keeps
200 verified snapshots elsewhere. They had reached 59,470 files (~2.4 GB), and
the real cost is the directory, not the disk: state/'s inode had grown to
2.8 MB, so every listdir/glob of state/ -- the window's journal lookup on each
GET, every backup, every ls -- walks 59k entries.

Life._rotate_snaps is lifted out of eran_life.py by source segment and run on a
throwaway directory of 100 fake snapshots. Nothing on eran1 is touched.

    python3 proof_ERAN-10.py           # eran_life.py as it is now
    python3 proof_ERAN-10.py --bak     # eran_life.py.bak-rev-20260906
"""
import ast
import io
import os
import shutil
import sys
import tempfile
import textwrap

HERE = os.path.dirname(os.path.abspath(__file__))


def _node(path, dotted):
    src = io.open(path, encoding="utf-8").read()
    tree = ast.parse(src)

    def find(body, want):
        for n in body:
            if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == want:
                return n
            if isinstance(n, ast.Assign):
                for t in n.targets:
                    if isinstance(t, ast.Name) and t.id == want:
                        return n
        return None

    node, body = None, tree.body
    for part in dotted.split("."):
        node = find(body, part)
        if node is None:
            return None, src
        body = getattr(node, "body", [])
    return textwrap.dedent(ast.get_source_segment(src, node) or ""), src


class Obj(object):
    def __init__(self, **kw):
        self.__dict__.update(kw)


def main():
    bak = "--bak" in sys.argv
    path = os.path.join(HERE, "eran_life.py") + (".bak-rev-20260906" if bak else "")
    print("proof ERAN-10 -- bound state/: snapshots nobody loads are rotated")
    print("  eran_life : %s" % path)
    if not os.path.exists(path):
        print("FAIL: missing %s" % path)
        return 1

    seg, src = _node(path, "Life._rotate_snaps")
    if seg is None:
        print("  Life._rotate_snaps: NOT FOUND -- snapshots accumulate forever")
        print("RESULT: FAIL")
        return 1
    keep_seg, _ = _node(path, "Life.SNAP_KEEP")
    max_seg, _ = _node(path, "Life.SNAP_PRUNE_MAX")
    if keep_seg is None or max_seg is None:
        print("  SNAP_KEEP / SNAP_PRUNE_MAX: NOT FOUND")
        print("RESULT: FAIL")
        return 1

    tmp = tempfile.mkdtemp(prefix="proof-eran10-")
    try:
        for i in range(1, 101):
            io.open(os.path.join(tmp, "snap-%d.json.gz" % (i * 5000)), "w").close()
        io.open(os.path.join(tmp, "brain.json.gz"), "w").close()
        io.open(os.path.join(tmp, "journal-2026-09-06.md"), "w").close()
        before = len(os.listdir(tmp))

        g = {"os": os, "genome": Obj(STATE_DIR=tmp)}
        exec(compile(seg, "Life._rotate_snaps", "exec"), g)
        cls = {}
        exec(compile(keep_seg + "\n" + max_seg, "attrs", "exec"), cls)
        life = Obj(SNAP_KEEP=cls["SNAP_KEEP"], SNAP_PRUNE_MAX=cls["SNAP_PRUNE_MAX"])
        g["_rotate_snaps"](life)

        snaps = [n for n in os.listdir(tmp) if n.startswith("snap-")]
        others = [n for n in os.listdir(tmp) if not n.startswith("snap-")]
        newest = "snap-500000.json.gz" in snaps
        oldest_gone = "snap-5000.json.gz" not in snaps
        ok = (len(snaps) == life.SNAP_KEEP and newest and oldest_gone
              and len(others) == 2)
        print("  100 snaps + 2 other files -> %d snaps kept (SNAP_KEEP=%d), "
              "newest kept=%s oldest pruned=%s, other files untouched=%s"
              % (len(snaps), life.SNAP_KEEP, newest, oldest_gone,
                 len(others) == 2))
        print("  dir went %d -> %d entries" % (before, len(os.listdir(tmp))))

        # and the write site must actually call it
        called = "_rotate_snaps()" in src.split("def one_beat", 1)[-1]
        print("  one_beat calls _rotate_snaps after writing a snap: %s" % called)
        ok = ok and called
        print("RESULT: %s" % ("PASS" if ok else "FAIL"))
        return 0 if ok else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
