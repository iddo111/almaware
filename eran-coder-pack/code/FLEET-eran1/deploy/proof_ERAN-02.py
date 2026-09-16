#!/usr/bin/env python3
"""proof_ERAN-02.py -- the nanny must NAME what is wrong, never restart the child.

Defect: deploy/nanny.sh answered every metrics problem with
`systemctl --user restart eranb-life.service` -- the one remedy that is poison
for a starving or slow-booting organism, applied to a state it could not name,
on a hand-picked 900 s threshold unrelated to the 4.6 ms beat. And it never
looked at the one signature that means FAMINE: metrics lines with no "surprise"
key (the 2026-09-06 near-death).

Two fixtures, run against the script under test:
  (a) metrics an hour stale, every line fed  -> old RESTARTS eranb-life
                                                new writes ALARM-stalled only
  (b) metrics fresh, NO line carries surprise -> old says "ok", no alarm
                                                new writes ALARM-famine

SAFETY: `systemctl` and `curl` are shadowed by shims on PATH, so the OLD
script's restart is recorded in a log file and never reaches real systemd.
Nothing on eran1 is restarted by this proof. HOME is a throwaway fixture, so
the real ~/eran-brain/state is never written.

    python3 proof_ERAN-02.py             # deploy/nanny.sh as it is now
    python3 proof_ERAN-02.py --bak       # deploy/nanny.sh.bak-rev-20260906
"""
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))

SYSTEMCTL = """#!/bin/bash
echo "$@" >> "$FAKE_LOG"
case "$*" in
  *ActiveEnterTimestampMonotonic*) echo "1000000" ;;
esac
exit 0
"""

CURL = """#!/bin/bash
echo "curl $@" >> "$FAKE_LOG"
exit 0
"""


def _sh(path, body):
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(body)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP)


def fixture(root, fed, age_s):
    state = os.path.join(root, "eran-brain", "state")
    os.makedirs(state)
    p = os.path.join(state, "metrics.jsonl")
    now = time.time() - age_s
    with io.open(p, "w", encoding="utf-8", newline="\n") as f:
        for i in range(400):
            line = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S",
                                        time.localtime(now - (400 - i) * 0.005)),
                    "beat": 1000 + i, "protos": 60, "unit": "la"}
            if fed:
                line["surprise"] = 0.066
            f.write(json.dumps(line) + "\n")
    os.utime(p, (now, now))
    return state


def run_case(script, label, fed, age_s, results):
    root = tempfile.mkdtemp(prefix="proof-eran02-")
    try:
        state = fixture(root, fed, age_s)
        binz = os.path.join(root, "bin")
        os.makedirs(binz)
        log = os.path.join(root, "fake.log")
        _sh(os.path.join(binz, "systemctl"), SYSTEMCTL)
        _sh(os.path.join(binz, "curl"), CURL)
        env = dict(os.environ)
        env["HOME"] = root
        env["FAKE_LOG"] = log
        env["PATH"] = binz + os.pathsep + env.get("PATH", "")
        subprocess.run(["bash", script], env=env, cwd=root,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       timeout=120)
        calls = io.open(log, encoding="utf-8").read() if os.path.exists(log) else ""
        restarted_life = "restart eranb-life.service" in calls
        famine = os.path.exists(os.path.join(state, "ALARM-famine"))
        stalled = os.path.exists(os.path.join(state, "ALARM-stalled"))
        nanny = os.path.join(state, "nanny.log")
        logline = (io.open(nanny, encoding="utf-8").read().strip().splitlines()[-1]
                   if os.path.exists(nanny) else "(no nanny.log)")
        want_famine = not fed
        want_stalled = fed and age_s > 3600 - 1
        ok = (not restarted_life) and famine == want_famine and stalled == want_stalled
        print("  %-28s restart-life=%-5s ALARM-famine=%-5s ALARM-stalled=%-5s  %s"
              % (label, restarted_life, famine, stalled, "OK" if ok else "BAD"))
        print("      %s" % logline[:170])
        results.append(ok)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main():
    bak = "--bak" in sys.argv
    script = os.path.join(HERE, "nanny.sh") + (".bak-rev-20260906" if bak else "")
    print("proof ERAN-02 -- the nanny names, it does not restart the living thing")
    print("  script    : %s" % script)
    if not os.path.exists(script):
        print("FAIL: missing %s" % script)
        return 1
    results = []
    run_case(script, "(a) stale 1h, all fed", True, 3600, results)
    run_case(script, "(b) fresh, NO surprise", False, 5, results)
    ok = all(results) and len(results) == 2
    print("RESULT: %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
