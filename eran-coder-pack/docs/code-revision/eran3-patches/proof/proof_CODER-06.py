# -*- coding: utf-8 -*-
"""CODER-06 -- the watchdog's only learning signal could not see learning.

The loss trend was: earliest single-step sample in a 2 h window vs the latest
single-step sample, with a hand-picked 0.1% relative threshold
(LOSS_STALL_REL_EPS = 1e-3) against a per-step sd of 0.079-0.085. That is 85x
more noise than threshold, so the verdict was reading noise: watchdog.log shows
'loss increasing over the trend window' on 30+ passes between 07:26 and 12:03
this morning while loss_blocks.py's block means over the same span FELL
1.2139 -> 1.1611 -> 1.1431 -> 1.1469 -> 1.1212 -> 1.1068.

It never acted on that verdict, so nothing died of it -- but it is the only
learning signal the watchdog has, and it was noise. The history also appended the
same step 3-4 times (321 lines covering steps 49-52), because a pass runs every
5 minutes and a step takes 16.7.

This proof replays that exact shape through the REAL compute_loss_trend() of each
file, via a temporary history file.

Run:  python proof_CODER-06.py ../orig/watchdog.py   -> FAIL
      python proof_CODER-06.py ../new/watchdog.py    -> PASS
"""
import json
import pathlib
import sys
import tempfile
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _proofkit import Proof, load_module, target_from_argv  # noqa: E402

target = target_from_argv("new/watchdog.py")
p = Proof("CODER-06", target)
w = load_module(target)

# A falling run whose FIRST sample happens to be low and LAST sample high --
# exactly what per-step noise of 0.085 on a -0.002/step slope produces.
now = time.time()
rows = []
for step in range(1, 61):
    loss = 1.25 - 0.002 * step
    if step == 1:
        loss -= 0.10          # a lucky first step
    if step == 60:
        loss += 0.10          # an unlucky last step
    rows.append({"ts": now - (60 - step) * 60.0, "step": step, "loss": round(loss, 5)})

with tempfile.TemporaryDirectory() as t:
    hist = pathlib.Path(t) / "watchdog-loss-history.jsonl"
    hist.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    w.LOSS_HISTORY = hist
    verdict, detail = w.compute_loss_trend()
    print("  verdict=%r detail=%r" % (verdict, detail))
    p.check(verdict != "increasing",
            "a FALLING run is not reported as 'increasing'",
            "block means fall from ~1.24 to ~1.13 here; the old two-point rule "
            "compares 1.148 to 1.220 and calls it a rise")
    p.check(verdict == "decreasing",
            "a falling run is reported as decreasing", repr(detail))
    p.check("+/-" in (detail or "") or "SE" in (detail or ""),
            "the trend is reported WITH its uncertainty",
            "a direction without an error bar is not a measurement")

    # An honestly flat/short run must not be given a direction it cannot support.
    flat = [{"ts": now - (10 - s) * 60.0, "step": s,
             "loss": 1.10 + (0.09 if s % 2 else -0.09)} for s in range(1, 11)]
    hist.write_text("".join(json.dumps(r) + "\n" for r in flat), encoding="utf-8")
    v2, d2 = w.compute_loss_trend()
    print("  pure-noise verdict=%r detail=%r" % (v2, d2))
    p.check(v2 in ("stalled", "underpowered", "insufficient_data"),
            "pure noise is not given a direction", repr(v2))

# ---- the duplicate-per-pass problem ---------------------------------------
if not hasattr(w, "last_history_step"):
    p.fail("last_history_step() exists",
           "the history is appended on every pass, so one 16.7-minute step lands "
           "3-4 times and a two-point comparison can land on the same step twice")
else:
    with tempfile.TemporaryDirectory() as t:
        h = pathlib.Path(t) / "h.jsonl"
        h.write_text('{"ts":1,"step":52,"loss":1.1}\n{"ts":2,"step":53,"loss":1.0}\n',
                     encoding="utf-8")
        p.check(w.last_history_step(h) == 53, "the last recorded step is readable")
        p.check(w.last_history_step(pathlib.Path(t) / "missing.jsonl") is None,
                "a missing history is None, not a crash")
    src = pathlib.Path(target).read_text(encoding="utf-8")
    p.check("last_history_step()" in src.split("append_jsonl(LOSS_HISTORY")[0][-600:],
            "the append is guarded by a step-changed check",
            "defining the helper is not enough")

p.done()
