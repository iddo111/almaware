# -*- coding: utf-8 -*-
"""PROOF SO-06 -- error-as-data: a wrong-sized target produced err=NaN, json.dumps wrote
it to the wire as a bare `NaN` (not JSON for any strict client), and the loop DISTANCE was
returned under the same key "error" that a failure uses -- so babble.py:79
(`if "error" in res: raise`) would have raised on a perfectly good learning signal.

    python3 proof_SO-06.py ~/eran-organs/sense_organ.py.bak-rev-20260906   -> FAIL
    python3 proof_SO-06.py ~/eran-organs/sense_organ.py                    -> PASS
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _proof_harness as H                                          # noqa: E402

PATH = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else "~/eran-organs/sense_organ.py")
print("PROOF SO-06 against %s" % PATH)
mod = H.load(PATH, env={"ERAN_ORGAN_HOST": "127.0.0.1"})
np = mod.np
checks = []
areas = list(np.full(34, 1.0))

# 1. wrong-sized target: named fault, and nothing non-finite on the wire
c, t, err = H.pair(mod)
H.send(c, {"op": "loop", "areas": areas, "target": [0.5] * 27, "seconds": 0.05})
res, raw, _ = H.recv(c)
checks.append(("wrong-sized target is a named string fault",
               isinstance(res.get("error"), str) and "27" in res["error"] and "28" in res["error"],
               "error=%r" % (res.get("error"),)))
try:
    H.strict(raw)
    strict_ok, why = True, "strict json.loads accepted the frame"
except ValueError as exc:
    strict_ok, why = False, str(exc)
checks.append(("the reply is JSON a strict client can parse", strict_ok, why))
checks.append(("no bare NaN/Infinity token in the bytes",
               b"NaN" not in raw and b"Infinity" not in raw,
               "raw=%s" % raw[:120]))
c.close()

# 2. a GOOD loop: the distance must not live in the fault key
c, t, err = H.pair(mod)
H.send(c, {"op": "say", "areas": areas, "seconds": 0.2, "seed": 3})
res, _, _ = H.recv(c)
target = res["gist"]
c.close()

c, t, err = H.pair(mod)
H.send(c, {"op": "loop", "areas": areas, "target": target, "seconds": 0.2, "seed": 3})
res, raw, audio = H.recv(c)
checks.append(("a successful loop carries the distance in loop_error",
               isinstance(res.get("loop_error"), float),
               "loop_error=%r" % (res.get("loop_error"),)))
checks.append(('a successful loop has NO "error" key (that key means FAULT)',
               "error" not in res,
               "keys=%s" % sorted(res.keys())))
checks.append(("the loop still measures itself (distance ~0 against its own gist)",
               isinstance(res.get("loop_error"), float) and res["loop_error"] < 1e-6,
               "loop_error=%r audio=%d bytes" % (res.get("loop_error"), len(audio))))
c.close()

H.report(checks)
