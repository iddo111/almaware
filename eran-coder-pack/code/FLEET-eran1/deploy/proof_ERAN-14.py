#!/usr/bin/env python3
"""proof_ERAN-14.py -- the installer must not re-arm a retired tournament.

Defect: deploy/install.sh ran `systemctl --user enable --now
eranb-tournament.timer` unconditionally. genome.EAR_FROZEN is True -- the
crowned ear is frozen by law, so a tournament cannot change anything, and the
timer is correctly DISABLED on the box (last result 2026-08-24). Any future
install would have re-armed it, and results/tournament-*.json going quiet is
exactly the shape of "a job nobody noticed had died".

install.sh is run for real, but inside a throwaway HOME and with `systemctl`
and `loginctl` shadowed by shims on PATH: every unit command is written to a
log file and NOTHING reaches real systemd. No unit is enabled, started,
stopped, or restarted by this proof.

    python3 proof_ERAN-14.py           # deploy/install.sh as it is now
    python3 proof_ERAN-14.py --bak     # deploy/install.sh.bak-rev-20260906
"""
import io
import os
import shutil
import stat
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TREE = os.path.dirname(HERE)
UNITS = ["eranb-life.service", "eranb-serve.service", "eranb-nanny.service",
         "eranb-nanny.timer", "eranb-tournament.service",
         "eranb-tournament.timer"]

SYSTEMCTL = """#!/bin/bash
echo "systemctl $@" >> "$FAKE_LOG"
exit 0
"""
LOGINCTL = """#!/bin/bash
echo "Linger=yes"
exit 0
"""


def _sh(path, body):
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(body)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)


def main():
    bak = "--bak" in sys.argv
    script = os.path.join(HERE, "install.sh") + (".bak-rev-20260906" if bak else "")
    print("proof ERAN-14 -- install.sh must not re-arm the frozen-ear tournament")
    print("  install   : %s" % script)
    if not os.path.exists(script):
        print("FAIL: missing %s" % script)
        return 1

    root = tempfile.mkdtemp(prefix="proof-eran14-")
    try:
        base = os.path.join(root, "eran-brain")
        os.makedirs(os.path.join(base, "deploy"))
        os.makedirs(os.path.join(base, "body"))
        shutil.copy2(os.path.join(TREE, "body", "genome.py"),
                     os.path.join(base, "body", "genome.py"))
        shutil.copy2(script, os.path.join(base, "deploy", "install.sh"))
        for u in UNITS:
            src = os.path.join(HERE, u)
            dst = os.path.join(base, "deploy", u)
            if os.path.exists(src):
                shutil.copy2(src, dst)
            else:
                io.open(dst, "w").close()
        io.open(os.path.join(base, "deploy", "nanny.sh"), "w").close()

        binz = os.path.join(root, "bin")
        os.makedirs(binz)
        log = os.path.join(root, "fake.log")
        _sh(os.path.join(binz, "systemctl"), SYSTEMCTL)
        _sh(os.path.join(binz, "loginctl"), LOGINCTL)
        env = dict(os.environ)
        env["HOME"] = root
        env["FAKE_LOG"] = log
        env["PATH"] = binz + os.pathsep + env.get("PATH", "")
        r = subprocess.run(["bash", os.path.join(base, "deploy", "install.sh")],
                           env=env, cwd=root, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=120)
        out = r.stdout.decode("utf-8", "replace")
        calls = io.open(log, encoding="utf-8").read() if os.path.exists(log) else ""

        armed = "enable --now eranb-tournament.timer" in calls
        life_ok = "enable --now eranb-life.service" in calls
        said = "EAR_FROZEN" in out or "tournament: NOT enabled" in out
        ok = (not armed) and life_ok and said
        print("  systemctl calls the installer made:")
        for line in calls.strip().splitlines():
            print("      %s" % line)
        print("  tournament re-armed=%-5s  life still installed=%-5s  says why=%s"
              % (armed, life_ok, said))
        print("RESULT: %s" % ("PASS" if ok else "FAIL"))
        return 0 if ok else 1
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
