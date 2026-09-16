# -*- coding: utf-8 -*-
"""proof_K6-14 -- a log file with no ceiling.

    python proof_K6-14.py <path-to-keshev6_server.py> [path-to-keshev6-stt.service]

FAILS on the old file, PASSES on the fixed one.

Measured: state/keshev6.log reached 916,335 B in 17.5 h (~1.3 MB/day) as
systemd's `StandardOutput=append:` with no logrotate entry for it anywhere on
the box -- nothing in the system could ever trim it. This proof writes real
records through the real handler until the real 8 MB threshold is crossed, so
it measures the ceiling rather than asserting a constant.

Cases:
  A  the file is bounded: after >8 MB of records the live file is under the cap
  B  the history is kept, and bounded too (a .1 backup, never more than 6 files)
  C  an EMPTY setting installs nothing -- so a unit that still appends is
     unchanged and no line is ever written twice
  D  the unit itself no longer appends into an unrotated file (only when the
     unit path is given)
"""
from __future__ import annotations

import importlib.util
import logging
import shutil
import sys
import tempfile
from pathlib import Path

TARGET = Path(sys.argv[1]).resolve()
UNIT = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else None
FAILS: list[str] = []


def check(name: str, ok: bool, detail="") -> None:
    print("  %-58s %s%s" % (name, "PASS" if ok else "FAIL",
                            ("  <- " + str(detail)) if detail else ""))
    if not ok:
        FAILS.append(name)


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="k6proof14-"))
    shutil.copy2(TARGET, tmp / "keshev6_server.py")
    lex = TARGET.parent / "lexicon.py"
    if lex.exists():
        shutil.copy2(lex, tmp / "lexicon.py")
    spec = importlib.util.spec_from_file_location("k6_under_test14",
                                                  tmp / "keshev6_server.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["k6_under_test14"] = m
    spec.loader.exec_module(m)
    print("proof_K6-14 against %s" % TARGET)

    has = hasattr(m, "install_rotating_log")
    check("the server can bound its own log file at all", has,
          "" if has else "no install_rotating_log()")
    if not has:
        print("\nproof_K6-14: FAIL (%d) -> %s" % (len(FAILS), FAILS))
        return 1

    check("C an empty KESHEV6_LOG_FILE installs nothing",
          m.install_rotating_log("") is None)

    logfile = tmp / "state" / "keshev6.log"
    root = logging.getLogger()
    before = list(root.handlers)
    fh = m.install_rotating_log(str(logfile))
    check("the handler is installed on the root logger",
          fh is not None and fh in logging.getLogger().handlers)

    cap = getattr(m, "LOG_MAX_BYTES", 0)
    backups = getattr(m, "LOG_BACKUPS", 0)
    log = logging.getLogger("keshev6")
    log.setLevel(logging.INFO)
    pad = "x" * 260
    written = 0
    while written < int(cap * 1.15):
        log.info("evt=PROOF pad=%s", pad)
        written += 300
    fh.flush()

    files = sorted(p.name for p in logfile.parent.glob("keshev6.log*"))
    live = logfile.stat().st_size
    check("A the live file is bounded by the cap after %d MB written"
          % (written // (1024 * 1024)), live <= cap,
          "live=%d cap=%d" % (live, cap))
    check("B a rotated backup exists", (logfile.parent / "keshev6.log.1").exists(),
          files)
    check("B the history is bounded too", len(files) <= backups + 1,
          "%d files, backupCount=%d" % (len(files), backups))

    for h in list(logging.getLogger().handlers):
        if h not in before:
            logging.getLogger().removeHandler(h)
            h.close()

    if UNIT is not None:
        txt = UNIT.read_text(encoding="utf-8")
        appends = [ln for ln in txt.splitlines()
                   if ln.strip().startswith(("StandardOutput=append:",
                                             "StandardError=append:"))]
        hands_over = "KESHEV6_LOG_FILE" in txt
        check("D the unit no longer appends into an unrotated file",
              not appends, "; ".join(appends))
        check("D the unit hands the rotated file to the server", hands_over,
              UNIT.name)

    print("\nproof_K6-14: %s" % ("PASS" if not FAILS else
                                 "FAIL (%d) -> %s" % (len(FAILS), FAILS)))
    return 0 if not FAILS else 1


if __name__ == "__main__":
    raise SystemExit(main())
