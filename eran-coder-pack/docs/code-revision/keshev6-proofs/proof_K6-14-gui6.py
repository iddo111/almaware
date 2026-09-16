# -*- coding: utf-8 -*-
"""proof_K6-14-gui6 -- the PC half of the unrotated log. For a patch NOT applied.

    python proof_K6-14-gui6.py <path-to-keshev-next/app/gui6.py>

FAILS against gui6.py as it stands today, PASSES once
keshev6-proposed/gui6-trial-log-rotation.diff is applied. It does not import
gui6 (that would build a Tk window beside his live microphone) -- it lifts the
one function out of the source and runs it against real files in a temp dir.

Measured: D:\\CLAUDE\\keshev-next\\trial.log = 10,047,475 B in a single file,
appended to by every engine start since 2026-08-20, trimmed by nothing.

Cases:
  A  the function exists and is called before the engine's append handle opens
  B  a file over the ceiling really is rotated, and .1 keeps the old bytes
  C  a file under the ceiling is LEFT ALONE (the watchdog reads this tail)
  D  the backups are bounded
  E  it never raises on a file it cannot touch -- the 2026-08-25 scar was one
     unguarded open() on this exact path leaving Iddo with no microphone
"""
from __future__ import annotations

import ast
import os
import sys
import tempfile
import types
from pathlib import Path

TARGET = Path(sys.argv[1]).resolve()
FAILS: list[str] = []


def check(name: str, ok: bool, detail="") -> None:
    print("  %-62s %s%s" % (name, "PASS" if ok else "FAIL",
                            ("  <- " + str(detail)) if detail else ""))
    if not ok:
        FAILS.append(name)


def lift(src: str, fname: str):
    """Pull one top-level function out of a module's source, without importing
    the module. gui6 builds a Tk window on import; nothing here may do that."""
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == fname:
            mod = types.ModuleType("gui6_lifted")
            mod.__dict__["os"] = os
            for n in tree.body:      # carry the constants it reads
                if isinstance(n, ast.Assign):
                    try:
                        exec(compile(ast.Module([n], []), "<lift>", "exec"),
                             mod.__dict__)
                    except Exception:
                        pass
            exec(compile(ast.Module([node], []), "<lift>", "exec"), mod.__dict__)
            return mod.__dict__[fname], mod
    return None, None


def main() -> int:
    src = TARGET.read_text(encoding="utf-8", errors="replace")
    print("proof_K6-14-gui6 against %s" % TARGET)

    fn, mod = lift(src, "rotate_trial_log")
    check("A gui6 can rotate trial.log at all", fn is not None,
          "" if fn else "no rotate_trial_log() in the source")
    if fn is None:
        print("\nproof_K6-14-gui6: FAIL (%d) -> %s" % (len(FAILS), FAILS))
        return 1

    # A: it must run BEFORE the append handle is opened, or it just renames a
    # file someone already holds open and keeps writing into the old inode.
    call_at = src.find("rotate_trial_log()")
    open_at = src.find('open(TRIAL_LOG, "a"')
    check("A it is called before the engine's append handle is opened",
          0 < call_at < open_at, "call@%d open@%d" % (call_at, open_at))

    tmp = Path(tempfile.mkdtemp(prefix="k6proof14g-"))
    log = tmp / "trial.log"

    # ---- C: under the ceiling, leave it alone ------------------------------
    log.write_bytes(b"x" * 1000)
    rotated = fn(str(log), max_bytes=4096, backups=3)
    check("C a small log is left alone (the watchdog reads this tail)",
          rotated is False and log.stat().st_size == 1000,
          "rotated=%r size=%d" % (rotated, log.stat().st_size))

    # ---- B: over the ceiling, rotate and keep the bytes --------------------
    log.write_bytes(b"OLDBYTES" + b"y" * 9000)
    rotated = fn(str(log), max_bytes=4096, backups=3)
    b1 = tmp / "trial.log.1"
    check("B a log past the ceiling is rotated", rotated is True, rotated)
    check("B the old bytes survive in .1",
          b1.exists() and b1.read_bytes().startswith(b"OLDBYTES"),
          "exists=%s" % b1.exists())
    check("B the live path is now free for a fresh handle", not log.exists()
          or log.stat().st_size == 0, "exists=%s" % log.exists())

    # ---- D: bounded history ------------------------------------------------
    for _ in range(6):
        log.write_bytes(b"z" * 9000)
        fn(str(log), max_bytes=4096, backups=3)
    backups = sorted(p.name for p in tmp.glob("trial.log.*"))
    check("D the backups are bounded", len(backups) <= 3, backups)

    # ---- E: it must never raise -------------------------------------------
    raised = None
    try:
        fn(str(tmp / "nothing-here.log"), max_bytes=1, backups=3)
        fn(str(tmp), max_bytes=1, backups=3)          # a directory, not a file
    except Exception as e:
        raised = "%s: %s" % (type(e).__name__, e)
    check("E it never raises into the window that opens his microphone",
          raised is None, raised)

    print("\nproof_K6-14-gui6: %s" % ("PASS" if not FAILS else
                                      "FAIL (%d) -> %s" % (len(FAILS), FAILS)))
    return 0 if not FAILS else 1


if __name__ == "__main__":
    raise SystemExit(main())
