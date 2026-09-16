# -*- coding: utf-8 -*-
"""
> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

DO NOT STARVE THE MICROPHONE. Import this FIRST, before numpy.

THE SCAR THIS ANSWERS (TZ-8, written 2026-09-06)
------------------------------------------------
On 2026-09-03 a normal-priority render on the PC starved KESHEV into 78% empty
decodes, and every TZELEM entry point on the PC has opened with
`BELOW_NORMAL_PRIORITY_CLASS` ever since -- night.py:78, gate2.py:44,
godot_gate.py:81, hero8k.py:42, and both oneroom logs.

The materials track did not. `gate_mat.py`, `ab.py`, `calibrate.py` and `harvest.py`
contained no `nice`, no priority class and no thread cap anywhere -- and they were
run ON ERAN1, the box that serves ERAN's live microphone (keshev-stt :8737,
keshev6-stt :8739), for roughly half an hour of full-rate numpy: `gate-mat.log`
records 24 pose-pairs at 41-58 s each, 1920x1080, 30,000 strokes, and its last line
writes to `/home/eran1/materials-run/lab/gate-out/`. The same scar, moved from the PC
to the one box that must never be busy.

WHAT THIS DOES
--------------
  * caps every BLAS/OpenMP thread pool at 2 -- which is why it must be imported
    BEFORE numpy, since those pools size themselves once, at numpy import time;
  * drops the process priority: BELOW_NORMAL on Windows, `nice 19` on POSIX;
  * says out loud where it is running, so a run on a microphone box is visible in
    the log instead of being discovered afterwards.

THE REAL FIX IS NOT THIS FILE. TZELEM render work belongs on eran3 -- idle apart
from voice-ant-farm and chef, 76% disk, 840 GB free, and NO microphone. This is the
net for the run that goes to the wrong box anyway.

Nothing here restarts, stops or signals anything. It only changes THIS process.
"""
from __future__ import annotations

import os
import socket
import sys

THREADS = os.environ.get("TZELEM_THREADS", "2")
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_v, THREADS)

# Boxes that serve a live microphone and must never carry a render.
MIC_HOSTS = ("eran1", "eran4")

_where = socket.gethostname().split(".")[0].lower()
_how = "unchanged"
try:
    if os.name == "nt":
        import psutil
        psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        _how = "BELOW_NORMAL"
    else:
        os.nice(19 - os.nice(0))          # end at nice 19 whatever we started from
        _how = f"nice {os.nice(0)}"
except Exception as e:                                        # noqa: BLE001
    _how = f"could not lower priority: {e}"

print(f"courtesy: host={_where} priority={_how} threads={THREADS}", flush=True)
if any(h in _where for h in MIC_HOSTS):
    print(f"courtesy: WARNING — {_where} serves a LIVE MICROPHONE. TZELEM render work "
          f"belongs on eran3. Running anyway, niced and thread-capped; watch the "
          f"empty-decode rate.", file=sys.stderr, flush=True)
