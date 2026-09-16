# -*- coding: utf-8 -*-
"""PROOF SO-05 -- silent-empty: hear() answered 28 zeros for no audio and for a clip
under 4 frames, with no error key and no frame count, and a target of those zeros made
loop report a relative error of ~1e10 -- a number, not a fault.

    python3 proof_SO-05.py ~/eran-organs/sense_organ.py.bak-rev-20260906   -> FAIL
    python3 proof_SO-05.py ~/eran-organs/sense_organ.py                    -> PASS

Touches nothing live: a socketpair, in this process, no port, no service.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _proof_harness as H                                          # noqa: E402

PATH = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else "~/eran-organs/sense_organ.py")
print("PROOF SO-05 against %s" % PATH)
mod = H.load(PATH, env={"ERAN_ORGAN_HOST": "127.0.0.1"})
np = mod.np
checks = []

# 1. no audio at all
c, t, err = H.pair(mod)
H.send(c, {"op": "hear"})
res, _, _ = H.recv(c)
checks.append(("hear(no audio) is a named fault",
               isinstance(res.get("error"), str) and "no audio" in res["error"],
               "res=%s" % {k: (v[:3] if isinstance(v, list) else v) for k, v in res.items()}))
checks.append(("hear(no audio) reports n_frames",
               res.get("n_frames") == 0, "n_frames=%r" % res.get("n_frames")))
c.close()

# 2. audio present but under 4 frames (800 samples = 50 ms)
c, t, err = H.pair(mod)
pcm = (np.zeros(800) + 0.2)
H.send(c, {"op": "hear"}, (pcm * 32767).astype("<i2").tobytes())
res, _, _ = H.recv(c)
checks.append(("hear(800 samples) is a named fault",
               isinstance(res.get("error"), str) and "too short" in res["error"],
               "res=%s" % {k: (v[:3] if isinstance(v, list) else v) for k, v in res.items()}))
checks.append(("hear(800 samples) reports n_frames < 4",
               isinstance(res.get("n_frames"), int) and res["n_frames"] < 4,
               "n_frames=%r" % res.get("n_frames")))
c.close()

# 3. a real 880-sample clip still works -- the fix must not make the ear deaf
c, t, err = H.pair(mod)
sr = 16000
tt = np.arange(880) / sr
pcm = 0.4 * np.sin(2 * np.pi * 220 * tt)
H.send(c, {"op": "hear"}, (pcm * 32767).astype("<i2").tobytes())
res, _, _ = H.recv(c)
checks.append(("hear(880 samples) still returns a gist",
               isinstance(res.get("gist"), list) and len(res["gist"]) == 28
               and any(abs(v) > 1e-9 for v in res["gist"]),
               "n_frames=%r gist[0:2]=%s" % (res.get("n_frames"),
                                             (res.get("gist") or [])[:2])))
c.close()

# 4. in-process: an all-zero target must be a fault, not err=1.06e10
areas = np.full(34, 1.0)
try:
    mod.try_and_hear(areas, np.zeros(28))
    got = "returned err=%.4g" % mod.try_and_hear(areas, np.zeros(28))[2]
    ok = False
except ValueError as exc:
    got, ok = "ValueError: %s" % exc, "zero target" in str(exc)
except Exception as exc:                                            # noqa: BLE001
    got, ok = "%s: %s" % (type(exc).__name__, exc), False
checks.append(("try_and_hear(zero target) raises a named fault", ok, got))

H.report(checks)
