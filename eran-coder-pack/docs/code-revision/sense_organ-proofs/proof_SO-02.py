# -*- coding: utf-8 -*-
"""PROOF SO-02 -- hand-threshold / unnameable state: Restart=always + RestartSec=3 with no
start limit and no backoff restarted this unit 50,523 times in 46 h against a port a
hand-started copy of the same file was holding, at 3.25 s a restart -- a cadence that never
trips systemd's default 5-in-10 s limit. The code wrote a bare traceback each time and
never said WHO held the port.

    python3 proof_SO-02.py <sense_organ.py> <eran-senses.service>

    ... .bak-rev-20260906 pair -> FAIL          ... live pair -> PASS

Binds one throwaway listener on 127.0.0.1:0 (an ephemeral port the kernel picks) to create
the collision. It never touches :8830 and never signals the running organ.
"""
import contextlib
import io
import os
import socket
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _proof_harness as H                                          # noqa: E402

PATH = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else "~/eran-organs/sense_organ.py")
UNIT = os.path.expanduser(sys.argv[2] if len(sys.argv) > 2
                          else "~/.config/systemd/user/eran-senses.service")
print("PROOF SO-02 against %s + %s" % (PATH, UNIT))
checks = []

# ---------------------------------------------------------------- the code half
dummy = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
dummy.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
dummy.bind(("127.0.0.1", 0))
dummy.listen(1)
busy = dummy.getsockname()[1]
print("  (a throwaway listener holds 127.0.0.1:%d for this test)" % busy)

mod = H.load(PATH, env={"ERAN_ORGAN_HOST": "127.0.0.1", "ERAN_ORGAN_PORT": str(busy)})
buf = io.StringIO()
code, raised = None, None
try:
    with contextlib.redirect_stdout(buf):
        mod.serve()
    raised = "serve() returned -- it should never return"
except SystemExit as exc:
    code = exc.code
except BaseException as exc:                                        # noqa: BLE001
    raised = "%s: %s" % (type(exc).__name__, exc)
out = buf.getvalue()
dummy.close()

checks.append(("a busy port exits with the distinct code 98, not a bare traceback",
               code == 98, "exit=%r raised=%r" % (code, raised)))
checks.append(("the failure names itself on the way out",
               "BIND FAILED" in out, "stdout=%r" % out[:200]))
checks.append(("the failure names WHO holds the port",
               "holder:" in out and str(busy) in out,
               "stdout=%r" % out.replace("\n", " | ")[:300]))

# ---------------------------------------------------------------- the unit half
txt = open(UNIT).read() if os.path.exists(UNIT) else ""
for key in ("StartLimitIntervalSec", "StartLimitBurst", "RestartSteps", "RestartMaxDelaySec"):
    line = [l.strip() for l in txt.splitlines() if l.strip().startswith(key)]
    checks.append(("the unit backs off: %s is set" % key, bool(line),
                   line[0] if line else "absent -- restarts forever at RestartSec"))

H.report(checks)
