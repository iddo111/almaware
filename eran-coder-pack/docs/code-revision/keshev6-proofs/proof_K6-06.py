# -*- coding: utf-8 -*-
"""proof_K6-06 -- Windows code running on a DGX, warning about it every boot.

    python proof_K6-06.py <path-to-keshev6_server.py>

RUN THIS ON eran1 (or any Linux box) -- the defect only exists off Windows, and
a proof that cannot see the platform is not a proof. On eran1 use the venv the
service uses, under nice:

    nice -n 19 ~/keshev-spike/venv/bin/python proof_K6-06.py <file>

FAILS on the old file, PASSES on the fixed one. Nothing is loaded but the
module: no model, no CUDA, no port.

Measured: 5 of 5 boots logged `evt=PRIORITY_FAIL err=ModuleNotFoundError`
because psutil is not in keshev-spike/venv and the constants it wanted
(HIGH_PRIORITY_CLASS and friends) are Windows-only. Priority on this box is set
by the unit (Nice=5, CPUWeight=30). A warning that fires every single boot and
means nothing is worse than no warning: it teaches whoever reads the log to
skip warnings, and the next one will matter.

Cases:
  A  _set_priority does not raise
  B  _set_priority does not log PRIORITY_FAIL, and says who really owns it
  C  _add_cuda_dlls does not prepend a Windows-shaped path onto PATH
"""
from __future__ import annotations

import importlib.util
import logging
import os
import shutil
import sys
import tempfile
from pathlib import Path

TARGET = Path(sys.argv[1]).resolve()
FAILS: list[str] = []


def check(name: str, ok: bool, detail="") -> None:
    print("  %-58s %s%s" % (name, "PASS" if ok else "FAIL",
                            ("  <- " + str(detail)) if detail else ""))
    if not ok:
        FAILS.append(name)


def main() -> int:
    if os.name == "nt":
        print("proof_K6-06 must run on Linux (this defect is 'Windows code on "
              "the DGX'); os.name=nt here.")
        return 2

    tmp = Path(tempfile.mkdtemp(prefix="k6proof06-"))
    shutil.copy2(TARGET, tmp / "keshev6_server.py")
    lex = TARGET.parent / "lexicon.py"
    if lex.exists():
        shutil.copy2(lex, tmp / "lexicon.py")
    spec = importlib.util.spec_from_file_location("k6_under_test06",
                                                  tmp / "keshev6_server.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["k6_under_test06"] = m
    spec.loader.exec_module(m)
    print("proof_K6-06 against %s   (os.name=%s)" % (TARGET, os.name))

    records = []

    class Cap(logging.Handler):
        def emit(self, rec):
            records.append(rec.getMessage())

    logging.getLogger("keshev6").addHandler(Cap())
    logging.getLogger("keshev6").setLevel(logging.INFO)

    # ---- A + B --------------------------------------------------------------
    raised = None
    try:
        m._set_priority("high")
    except Exception as e:
        raised = "%s: %s" % (type(e).__name__, e)
    check("A _set_priority does not raise", raised is None, raised)
    fails = [r for r in records if "PRIORITY_FAIL" in r]
    check("B no PRIORITY_FAIL on a box where systemd owns priority",
          not fails, fails[0] if fails else "")
    check("B it says who owns priority instead",
          any(r.startswith("evt=PRIORITY") and "owner=systemd" in r
              for r in records),
          records[-1] if records else "(nothing logged)")

    # ---- C: a Windows-shaped nvidia tree must be ignored, not walked --------
    fake_root = tmp / "fakevenv" / "bin" / "python"
    fake_root.parent.mkdir(parents=True, exist_ok=True)
    fake_root.write_text("#!/bin/false\n")
    dll_dir = tmp / "fakevenv" / "bin" / "Lib" / "site-packages" / "nvidia" \
        / "cublas" / "bin"
    dll_dir.mkdir(parents=True, exist_ok=True)
    real_exe, m.sys.executable = m.sys.executable, str(fake_root)
    path_before = os.environ.get("PATH", "")
    try:
        m._add_cuda_dlls()
    except Exception as e:
        check("C _add_cuda_dlls does not raise", False, repr(e))
    finally:
        m.sys.executable = real_exe
    path_after = os.environ.get("PATH", "")
    os.environ["PATH"] = path_before
    check("C a Windows site-packages layout is NOT prepended to PATH",
          path_after == path_before,
          "PATH gained %r" % path_after[:len(path_after) - len(path_before)])

    print("\nproof_K6-06: %s" % ("PASS" if not FAILS else
                                 "FAIL (%d) -> %s" % (len(FAILS), FAILS)))
    return 0 if not FAILS else 1


if __name__ == "__main__":
    raise SystemExit(main())
