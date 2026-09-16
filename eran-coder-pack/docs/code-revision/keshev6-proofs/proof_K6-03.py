# -*- coding: utf-8 -*-
"""proof_K6-03 -- the canary that could not fail, and the /health that never said no.

Run it against a keshev6_server.py:

    python proof_K6-03.py <path-to-keshev6_server.py>

FAILS on eran1:~/keshev6/keshev6_server.py.bak-rev-20260906 (the old code).
PASSES on the fixed file. No model is loaded and no port is bound: the engine is
a stub, because the defect is in the SERVER'S JUDGEMENT of an engine's answer,
not in the engine.

Three cases, each a thing that really could happen and really was not caught:
  A  the engine answers rubbish (wrong type / missing contract keys / NaN).
     Old run_canary returned True because nothing raised.
  B  every canary has failed for an hour. Old health() answered 200 anyway --
     it read state=="READY" and printed canary_age_s beside it, gating nothing.
  C  three decodes in a row wedge past the wall. Old code abandoned each thread
     (still holding _decode_lock), freed the inflight slot, and kept saying READY.
"""
from __future__ import annotations

import importlib.util
import math
import shutil
import sys
import tempfile
from pathlib import Path

TARGET = Path(sys.argv[1]).resolve()
FAILS: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print("  %-58s %s%s" % (name, "PASS" if ok else "FAIL",
                            ("  <- " + str(detail)) if detail else ""))
    if not ok:
        FAILS.append(name)


def load(path: Path):
    """Load the target beside a real lexicon.py, in a scratch dir of its own."""
    tmp = Path(tempfile.mkdtemp(prefix="k6proof03-"))
    shutil.copy2(path, tmp / "keshev6_server.py")
    lex = path.parent / "lexicon.py"
    if lex.exists():
        shutil.copy2(lex, tmp / "lexicon.py")
    spec = importlib.util.spec_from_file_location("k6_under_test",
                                                  tmp / "keshev6_server.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["k6_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


CFG = {"bind": ["127.0.0.1"], "port": 0, "canary_interval_s": 300,
       "canary_lock_wait_s": 2.0, "decode_wall_s": 0.3, "inflight_cap": 2}


class GoodEngine:
    model_id = "stub"

    def decode(self, audio, language="he", initial_prompt=None):
        return {"text": "שלום", "avg_logprob": -0.3,
                "no_speech_prob": 0.1, "compression_ratio": 1.2}


class GarbageEngine(GoodEngine):
    """Returns a well-typed-looking answer that is NOT the contract."""

    def decode(self, audio, language="he", initial_prompt=None):
        return {"text": None, "avg_logprob": float("nan")}


def main() -> int:
    m = load(TARGET)
    print("proof_K6-03 against %s" % TARGET)

    # ---- A: a canary must refuse a malformed answer -------------------------
    srv = m.Keshev6Server(dict(CFG), token="t")
    srv.engine = GarbageEngine()
    try:
        ok = srv.run_canary()
    except Exception as e:                       # a crash is also not a pass
        ok = "raised:" + type(e).__name__
    check("A canary FAILS on a malformed decode result",
          ok is False, "run_canary returned %r" % (ok,))

    # sanity: the same canary must still PASS a good engine, or the gate is
    # just noise that will be turned off within a week.
    srv2 = m.Keshev6Server(dict(CFG), token="t")
    srv2.engine = GoodEngine()
    try:
        ok2 = srv2.run_canary()
    except Exception as e:
        ok2 = "raised:" + type(e).__name__
    check("A canary PASSES a well-formed decode result",
          ok2 is True, "run_canary returned %r" % (ok2,))

    # ---- B: /health must go 503 on a stale canary ---------------------------
    srv3 = m.Keshev6Server(dict(CFG), token="t")
    srv3.engine = GoodEngine()
    srv3.set_ready()
    srv3._canary_ts = None                       # never passed a canary at all
    try:
        code_never = srv3.health_code()
    except AttributeError:
        code_never = "no health_code(): /health code came from state alone"
    check("B /health is 503 when no canary has EVER passed",
          code_never == 503, "got %r" % (code_never,))

    import time as _t
    srv3._canary_ts = _t.monotonic() - 3600.0    # last pass an hour ago
    try:
        code_stale = srv3.health_code()
        stale_flag = srv3.canary_stale
    except AttributeError:
        code_stale, stale_flag = "no health_code()", "n/a"
    check("B /health is 503 when the canary is an hour stale",
          code_stale == 503, "state=%s canary_age=3600s code=%r stale=%r"
          % (srv3.state, code_stale, stale_flag))

    # and it must be 200 again once a canary passes -- a gate stuck at 503 is
    # as useless as one stuck at 200.
    srv3.run_canary()
    try:
        code_fresh = srv3.health_code()
    except AttributeError:
        code_fresh = "no health_code()"
    check("B /health is 200 again after a passing canary",
          code_fresh == 200, "got %r" % (code_fresh,))

    # ---- C: three wedged decodes must leave READY ---------------------------
    srv4 = m.Keshev6Server(dict(CFG), token="t")
    srv4.engine = GoodEngine()
    srv4.set_ready()
    srv4.run_canary()
    try:
        seen = [srv4.note_decode_timeout() for _ in range(3)]
        degraded = srv4.state != "READY"
        code = srv4.health_code()
    except AttributeError as e:
        seen, degraded, code = [], False, "no note_decode_timeout(): %s" % e
    check("C three consecutive decode timeouts leave READY",
          degraded, "state=%s after %r" % (srv4.state, seen))
    check("C /health is 503 while wedged", code == 503, "got %r" % (code,))

    # a passing canary is the ONLY thing allowed to clear it
    try:
        srv4._canary_ts = None
        srv4.run_canary()
        cleared = (srv4.state == "READY" and srv4._consec_timeouts == 0)
    except AttributeError:
        cleared = False
    check("C a passing canary clears DEGRADED", cleared,
          "state=%s" % srv4.state)

    # a single timeout must NOT: one hiccup is not a broken decoder
    srv5 = m.Keshev6Server(dict(CFG), token="t")
    srv5.engine = GoodEngine()
    srv5.set_ready()
    srv5.run_canary()
    try:
        srv5.note_decode_timeout()
        one_ok = (srv5.state == "READY" and srv5.health_code() == 200)
    except AttributeError:
        one_ok = False
    check("C one timeout does NOT degrade", one_ok, "state=%s" % srv5.state)

    # ---- D: the systemd watchdog must not kill a healthy boot -------------
    # This is the FIX'S OWN risk, so it gets its own case. WatchdogSec=180 with
    # a ping gated on health would SIGABRT a 1.6 GB model that takes longer than
    # that to load -- the 2026-08-12 scar exactly (:8737 petted every 300 s
    # against a 90 s watchdog, killed five times, unit given up on).
    srv6 = m.Keshev6Server(dict(CFG), token="t")
    srv6.engine = None                       # still loading, no canary yet
    try:
        booting = srv6.watchdog_should_ping()
    except AttributeError:
        booting = "no watchdog_should_ping()"
    check("D the watchdog pings while the model is still loading",
          booting is True, "got %r" % (booting,))

    # ...but the grace is BOUNDED: a load that hangs is still caught
    grace = getattr(srv6, "BOOT_GRACE_S", None)
    if grace is None:
        check("D a boot that hangs past the grace stops being pinged", False,
              "no BOOT_GRACE_S: the boot window is unbounded")
    else:
        srv6._t0 = _t.monotonic() - (grace + 1)
        check("D a boot that hangs past the grace stops being pinged",
              srv6.watchdog_should_ping() is False, "grace=%.0fs" % grace)

    # ...and once it HAS been ready, a stale canary stops the ping at once,
    # with no second grace to hide behind
    srv7 = m.Keshev6Server(dict(CFG), token="t")
    srv7.engine = GoodEngine()
    srv7.set_ready()
    srv7.run_canary()
    try:
        healthy_ping = srv7.watchdog_should_ping()
        srv7._canary_ts = _t.monotonic() - 3600.0
        srv7._t0 = _t.monotonic()        # fresh clock, but already READY once
        stale_ping = srv7.watchdog_should_ping()
    except AttributeError:
        healthy_ping, stale_ping = "no watchdog_should_ping()", "n/a"
    check("D a healthy server is pinged", healthy_ping is True, healthy_ping)
    check("D a stale canary stops the ping even on a fresh clock",
          stale_ping is False, "%r was_ready=%s" % (stale_ping, srv7._was_ready))

    print("\nproof_K6-03: %s" % ("PASS" if not FAILS else
                                 "FAIL (%d) -> %s" % (len(FAILS), FAILS)))
    return 0 if not FAILS else 1


if __name__ == "__main__":
    raise SystemExit(main())
