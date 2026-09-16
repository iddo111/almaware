#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
loop_seed_syl.py -- seed rounds for the syl3 fits of /na/ /la/ /ya/ (2026-09-03).

Same shape as loop_seed.seed_ma, but these units have only ONE finished fit
each (out/best-<unit>.wav + out/result-<unit>.json, finished 22:00-22:48 on
2026-09-02 after the velum fix), so a round is: the syl3 fit, the no-learning
control (train_syl2's P0 for that unit), and TWO mutants around the fit at the
unit's sigma0 -- four clips, blind letters, Iddo picks.

    python loop_seed_syl.py na la ya
"""
import io
import os
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import loopgen                      # noqa: E402
import loop_seed as LS              # noqa: E402  (load_state/save_state/pull/rjson/POOL/R)

# train_syl2 P0 per unit: [mean(pos), mean(area range), 0.60, 0.10, 0.05, 0.30]
# pos: na (0.55,0.80) la (0.55,0.80) ya (0.30,0.60); area: sealed 0..0.30, open 0.15..1.20
CONTROL = {
    "na": [0.675, 0.15,  0.60, 0.10, 0.05, 0.30],
    "la": [0.675, 0.675, 0.60, 0.10, 0.05, 0.30],
    "ya": [0.45,  0.675, 0.60, 0.10, 0.05, 0.30],
}


def seed_syl(st, unit):
    rn = st["next_round"]
    tag = "r%02d-%s" % (rn, unit)
    d = os.path.join(LS.POOL, tag)
    clips = []
    g3 = LS.rjson("%s/result-%s.json" % (LS.R, unit))
    name = "ERAN-%s-r%02d-syl3.wav" % (unit, rn)
    clips.append({"name": name, "path": LS.pull("%s/best-%s.wav" % (LS.R, unit), os.path.join(d, name)),
                  "genome": g3["params"], "kind": "fit-syl3", "ok": True,
                  "note": "loss %.4f (start %.4f) params %s" % (g3["loss"], g3["start_loss"],
                                                                [round(x, 3) for x in g3["params"]])})
    sigma = loopgen.sigma_for(unit, 0)
    man = loopgen.remote_render(
        unit, tag,
        items=[{"name": "ERAN-%s-r%02d-control.wav" % (unit, rn), "genome": CONTROL[unit],
                "kind": "control-no-learning"}],
        mutate={"parent": g3["params"], "sigma": sigma, "n": 2, "seed": rn * 7919 + 3,
                "prefix": "ERAN-%s-r%02d" % (unit, rn)})
    for c in man["items"]:
        assert c["ok"], c
        note = ("train_syl2 P0 for /%s/ on the frozen /ah/ vowel, no search" % unit
                if c["kind"] == "control-no-learning" else "mutant of the syl3 fit, sigma %.2f" % sigma)
        clips.append({"name": c["name"], "path": c["path"], "genome": c["genome"],
                      "kind": c["kind"], "ok": True, "note": note})
    st["rounds"].append({"round": rn, "unit": unit, "sigma": None, "generation": 0,
                         "made": time.strftime("%Y-%m-%d %H:%M:%S"), "timing": man["timing"],
                         "clips": clips, "chosen": None, "seed": True})
    st["gen"].setdefault(unit, 0)
    st["next_round"] = rn + 1
    return rn, [c["name"] for c in clips]


if __name__ == "__main__":
    units = [u for u in sys.argv[1:] if u in CONTROL]
    if not units:
        print(__doc__); sys.exit(2)
    st = LS.load_state()
    for u in units:
        t = time.time()
        rn, names = seed_syl(st, u)
        LS.save_state(st)
        print("seeded round %d /%s/ in %.1f s: %s" % (rn, u, time.time() - t, names))
    print("next_round =", st["next_round"])
