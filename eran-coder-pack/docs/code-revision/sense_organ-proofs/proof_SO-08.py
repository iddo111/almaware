# -*- coding: utf-8 -*-
"""PROOF SO-08 -- unpruned: StandardOutput/StandardError=append:%h/eran-organs/organ.log,
with no rotation and no dedupe. Measured 2026-09-06: 12,833,771 bytes, 303,155 lines,
50,523 identical `OSError: [Errno 98] Address already in use` tracebacks and 4 lines that
say "listening". A log that is 99.98% one sentence is not a log.

    python3 proof_SO-08.py ~/.config/systemd/user/eran-senses.service.bak-rev-20260906 -> FAIL
    python3 proof_SO-08.py ~/.config/systemd/user/eran-senses.service                   -> PASS

Reads text. Changes nothing, signals nothing.
"""
import os
import sys

UNIT = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1
                          else "~/.config/systemd/user/eran-senses.service")
print("PROOF SO-08 against %s" % UNIT)
txt = open(UNIT).read() if os.path.exists(UNIT) else ""
lines = [l.strip() for l in txt.splitlines() if not l.strip().startswith("#")]

checks = []
appenders = [l for l in lines if l.startswith(("StandardOutput", "StandardError"))
             and "append:" in l]
checks.append(("no unrotated append: sink", not appenders,
               "; ".join(appenders) or "none -- nothing appends to a flat file"))
out = [l for l in lines if l.startswith("StandardOutput=")]
errl = [l for l in lines if l.startswith("StandardError=")]
checks.append(("stdout goes to journald (rate-limited, rotated)",
               out == ["StandardOutput=journal"], out or "unset"))
checks.append(("stderr goes to journald",
               errl == ["StandardError=journal"], errl or "unset"))
ident = [l for l in lines if l.startswith("SyslogIdentifier=")]
checks.append(("the journal entries are findable by name", bool(ident),
               ident[0] if ident else "no SyslogIdentifier"))

log = os.path.expanduser("~/eran-organs/organ.log")
if os.path.exists(log):
    print("  (the old flat log is still on disk at %s, %d bytes -- left for Iddo, "
          "nothing here deletes it)" % (log, os.path.getsize(log)))

ok = all(c[1] for c in checks)
for label, good, detail in checks:
    print("  [%s] %s -- %s" % ("PASS" if good else "FAIL", label, detail))
print("PROOF %s" % ("PASS" if ok else "FAIL"))
sys.exit(0 if ok else 1)
