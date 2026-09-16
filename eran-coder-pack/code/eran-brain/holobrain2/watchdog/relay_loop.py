#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""relay_loop.py -- run watch_relay.py forever, because one pass is not a watch.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL
> output, not a proxy.

2026-09-05. `watch_relay.py` was written on 2026-09-01 and is a good piece of
work: it pulls the eran3 learning-watchdog's alarms into RAMCHAT, keeps NEW
apart from STILL, and its own docstring states the doctrine -- *"an instrument
nobody checks is an instrument that has already failed quietly."*

It was never scheduled. Its cursor file recorded `last_run 2026-09-01 13:51:33`
and did not move again. Meanwhile the watchdog on eran3 kept firing every three
minutes and wrote **105 alarm lines nobody read**, saying (still true today)
that both sibling services are dead, that no round has run for 2.9 days, and
that `birth.correct` has been 3.000000 in every round on record -- which the
watchdog itself names *"a dead wire, not a stable number."*

That is the same failure as `receipts.py`, written 2026-09-04 as the fix for the
mic's blindness, which exists and which **zero launchers call**. The workspace
does not lack instruments. It lacks anything that runs them.

So this file is deliberately almost empty. It adds no logic, no cleverness and
no new judgement -- the judging is `sibling_watch.py`'s job on eran3 and the
carrying is `watch_relay.py`'s job here. All it does is make the existing thing
happen again, and record honestly when it could not.

Reads only, like everything in this directory. It never touches the sibling,
the watchdog, or any service.

    python relay_loop.py                 every 5 minutes, forever
    python relay_loop.py --every 900     a different period
    python relay_loop.py --once          one pass (same as watch_relay.py)
"""
from __future__ import annotations

import argparse
import io
import os
import subprocess
import sys
import time
from datetime import datetime

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
RELAY = os.path.join(HERE, "watch_relay.py")
LOG = os.path.join(HERE, "relay-loop.log")
HEARTBEAT_S = 3600.0   # write a line at least this often, even when unchanged


def one_pass():
    """Run the relay once. Returns (ok, first line of what it said)."""
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    try:
        p = subprocess.run([sys.executable, RELAY], capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           timeout=180, env=env, cwd=HERE)
    except subprocess.TimeoutExpired:
        return False, "relay timed out after 180 s (eran3 unreachable?)"
    out = (p.stdout or "").strip()
    err = (p.stderr or "").strip()
    if p.returncode != 0:
        return False, ("rc=%d %s" % (p.returncode, (err or out).splitlines()[0][:160]
                                     if (err or out) else "no output"))
    # Read the relay's OWN count, not a guess from its text. The first version
    # of this line counted lines containing "ALARM" -- and the relay's summary
    # line reads `relay: verdict=ALARM posted=0`, so it reported "posted 1"
    # when the true answer was zero. That is the exact fault this whole
    # directory exists to catch: a proxy that moves when the product does not.
    posted = None
    verdict = "?"
    for ln in out.splitlines():
        for tok in ln.split():
            if tok.startswith("posted="):
                try:
                    posted = int(tok[7:])
                except ValueError:
                    pass
            elif tok.startswith("verdict="):
                verdict = tok[8:]
    if posted is None:
        return False, "relay printed no posted= count; output was: %s" % (out[:160] or "(empty)")
    return True, ("verdict=%s, posted %d new alarm(s)" % (verdict, posted)
                  if posted else "verdict=%s, nothing new" % verdict)


def log(line):
    stamp = datetime.now().astimezone().isoformat(timespec="seconds")
    with io.open(LOG, "a", encoding="utf-8") as fh:
        fh.write("%s  %s\n" % (stamp, line))
    print("%s  %s" % (stamp, line), flush=True)


def _below_normal():
    """Drop this process to BELOW_NORMAL on Windows, and VERIFY it took.

    2026-09-05: these two now start from the Startup folder at logon, so they
    can no longer rely on whoever launched them setting the priority. That
    matters more than it sounds -- normal-priority work on this PC starved
    Iddo's live microphone and 78% of his decodes came back empty. Nothing here
    may ever outrank his mic.

    The argtypes are NOT decoration. gui6.py records the same trap, measured:
    without restype/argtypes the (HANDLE)-1 pseudo-handle is truncated on 64-bit,
    SetPriorityClass fails SILENTLY and the process stays at Normal. Another tool
    on this fleet hit the identical bug tonight. So read the class back.
    """
    if os.name != "nt":
        return None
    try:
        import ctypes
        BELOW_NORMAL = 0x00004000
        k32 = ctypes.windll.kernel32
        k32.GetCurrentProcess.restype = ctypes.c_void_p
        k32.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        k32.GetPriorityClass.argtypes = [ctypes.c_void_p]
        k32.GetPriorityClass.restype = ctypes.c_uint32
        h = k32.GetCurrentProcess()
        k32.SetPriorityClass(h, BELOW_NORMAL)
        return k32.GetPriorityClass(h) == BELOW_NORMAL   # verified, not assumed
    except Exception:
        return None


def main():
    prio_ok = _below_normal()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--every", type=float, default=300.0, help="seconds between passes")
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args()

    if a.once:
        ok, what = one_pass()
        log(("OK   " if ok else "FAIL ") + what)
        return 0 if ok else 1

    log("relay loop started, every %.0f s" % a.every)
    last = None
    last_beat = 0.0
    while True:
        try:
            ok, what = one_pass()
        except Exception as e:                       # the loop must outlive a pass
            ok, what = False, "loop caught: %s" % e
        # Log every failure, and log success on CHANGE -- an unchanging "nothing
        # new" every 5 minutes is how a log becomes wallpaper, and wallpaper is
        # how the last four days were missed.
        #
        # BUT: a log that goes silent when healthy is indistinguishable from a
        # log that went silent because the process died -- which is the exact
        # failure this whole directory exists to catch, and the first version of
        # this loop had it. So a heartbeat line is written at least hourly even
        # when nothing changed. Silence now means DEAD, never means FINE.
        now = time.time()
        beat_due = (now - last_beat) >= HEARTBEAT_S
        key = (ok, what)
        if (not ok) or key != last or beat_due:
            log(("OK   " if ok else "FAIL ") + what
                + ("   [hourly heartbeat]" if beat_due and ok and key == last else ""))
            last = key
            last_beat = now
        time.sleep(a.every)


if __name__ == "__main__":
    sys.exit(main())
