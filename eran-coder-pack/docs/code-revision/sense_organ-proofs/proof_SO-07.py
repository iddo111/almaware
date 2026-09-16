# -*- coding: utf-8 -*-
"""PROOF SO-07 -- stale-config: say/loop never read req['seed'], so speak() always ran with
seed=0. The glottal jitter the docstring promises was fixed, every render of the same areas
was bit-identical, and a caller could not ask for variation over the wire.

    python3 proof_SO-07.py ~/eran-organs/sense_organ.py.bak-rev-20260906   -> FAIL
    python3 proof_SO-07.py ~/eran-organs/sense_organ.py                    -> PASS
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _proof_harness as H                                          # noqa: E402

PATH = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else "~/eran-organs/sense_organ.py")
print("PROOF SO-07 against %s" % PATH)
mod = H.load(PATH, env={"ERAN_ORGAN_HOST": "127.0.0.1"})
np = mod.np
checks = []
areas = list(np.full(34, 1.0))


def say(seed):
    c, t, err = H.pair(mod)
    H.send(c, {"op": "say", "areas": areas, "seconds": 0.25, "seed": seed})
    res, _, audio = H.recv(c)
    c.close()
    return res, audio


r0, a0 = say(0)
r7, a7 = say(7)
r7b, a7b = say(7)

checks.append(("seed reaches the tract: seed 0 and seed 7 render different audio",
               a0 != a7 and len(a0) == len(a7) > 0,
               "%d bytes each, equal=%s" % (len(a0), a0 == a7)))
checks.append(("the same seed still renders the same audio (reproducible)",
               a7 == a7b, "equal=%s" % (a7 == a7b)))
checks.append(("the reply echoes the seed it used",
               r7.get("seed") == 7, "seed=%r" % r7.get("seed")))

# in-process control: speak() itself always could take a seed -- only the wire ignored it
s0 = mod.speak(np.full(34, 1.0), seconds=0.1, seed=0)
s7 = mod.speak(np.full(34, 1.0), seconds=0.1, seed=7)
checks.append(("control: speak(seed=) was never the broken half",
               not np.array_equal(s0, s7), "speak differs by seed as it always did"))

H.report(checks)
