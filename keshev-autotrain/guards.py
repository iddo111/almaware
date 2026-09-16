# -*- coding: utf-8 -*-
"""KESHEV AUTOTRAIN / guards.py -- the guards every training run must pass.

> BROKEN WINDOWS LAW: test the REAL output, not a proxy.

WHY THIS FILE EXISTS: tonight's evidence
----------------------------------------
At 03:44 on 2026-09-12 the existing nightly LoRA was killed by the Linux OOM
killer on eran4:

    Active: failed (Result: oom-kill) since Sat 2026-09-12 03:44:42 IDT

It had 7.7 GB of available RAM and asked for a whisper-large-v3-turbo training
step. On a GB10 the 121 GB is UNIFIED memory -- host RAM and GPU memory are the
same pool -- so "free RAM" is the whole budget, and eran4's was already spent
(ollama alone holds a 52 GB model resident).

The run did not check. It never checks. So it trains until the kernel kills it,
which on a box that also runs dmidi-life and alma-stt is a risk to things that
were minding their own business.

THE FLOOR IS THE FIX: refuse to start, and pause mid-run, below a memory floor.
A training job that declines to start is a healthy outcome, not a failure.

THE LAWS THIS ENCODES (D:\\CLAUDE\\CLAUDE.md)
--------------------------------------------
  * No AI training on the PC, ever. `require_fleet()` refuses to run on Windows.
  * BELOW_NORMAL / nice 19 so nothing starves KESHEV (the 09-03 scar).
  * Never endanger a live brain: `require_headroom()` reads the REAL number.
"""
from __future__ import annotations
import json, os, platform, subprocess, sys, time

DEFAULT_FLOOR_GB = 12.0          # a whisper-large LoRA step needs ~10-16 GB on GB10
CHECK_EVERY_S = 30


def _avail_gb_local():
    """Available memory in GB on this (Linux) box. 'available', not 'free' --
    'free' excludes reclaimable cache and would refuse runs that would fit."""
    try:
        with open("/proc/meminfo", encoding="utf-8") as fh:
            for ln in fh:
                if ln.startswith("MemAvailable:"):
                    return int(ln.split()[1]) / (1024.0 * 1024.0)
    except OSError:
        pass
    return -1.0


def avail_gb(host=None):
    if host:
        r = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host,
                            "awk '/MemAvailable/{print $2}' /proc/meminfo"],
                           capture_output=True, text=True)
        try:
            return int(r.stdout.strip()) / (1024.0 * 1024.0)
        except Exception:
            return -1.0
    return _avail_gb_local()


def require_fleet():
    """Project law: training runs on the fleet, never on the PC."""
    if platform.system() == "Windows":
        sys.exit("[guard] REFUSED: training on the PC is forbidden by project law.\n"
                 "        Run this on a fleet box (eran2 / eran4).")


def require_headroom(floor_gb=DEFAULT_FLOOR_GB, host=None):
    """Refuse to START below the floor. Returns the measured number."""
    got = avail_gb(host)
    where = host or platform.node()
    if got < 0:
        sys.exit("[guard] REFUSED: could not measure available memory on %s.\n"
                 "        Refusing to train blind." % where)
    if got < floor_gb:
        sys.exit("[guard] REFUSED: %s has %.1f GB available, floor is %.1f GB.\n"
                 "        Nothing was started. This is the guard working, not a failure.\n"
                 "        (2026-09-12: the old nightly skipped this check and was OOM-killed.)"
                 % (where, got, floor_gb))
    print("[guard] memory OK on %s: %.1f GB available (floor %.1f)" % (where, got, floor_gb))
    return got


def pause_if_low(floor_gb=DEFAULT_FLOOR_GB, max_wait_s=1800):
    """Mid-run: block while memory is under the floor; give up rather than push.
    Returns True if it is safe to continue, False if the caller should stop and
    checkpoint."""
    t0 = time.time()
    warned = False
    while True:
        got = _avail_gb_local()
        if got < 0 or got >= floor_gb:
            if warned:
                print("[guard] memory recovered: %.1f GB -- resuming" % got, flush=True)
            return True
        if not warned:
            print("[guard] PAUSING: %.1f GB available, under the %.1f GB floor"
                  % (got, floor_gb), flush=True)
            warned = True
        if time.time() - t0 > max_wait_s:
            print("[guard] memory did not recover in %ds -- stopping cleanly so the "
                  "checkpoint survives." % max_wait_s, flush=True)
            return False
        time.sleep(CHECK_EVERY_S)


def be_nice(n=19):
    """nice 19 -- KESHEV must never be starved by a training run (09-03 scar)."""
    try:
        os.nice(n)
        print("[guard] nice %d" % n)
    except (AttributeError, OSError) as exc:
        print("[guard] could not renice: %s" % exc)


def log_run(path, **fields):
    """One line per run, with the number. Append-only."""
    fields.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%S"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(fields, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    host = sys.argv[1] if len(sys.argv) > 1 else None
    print("available: %.1f GB on %s" % (avail_gb(host), host or platform.node()))
