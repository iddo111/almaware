# -*- coding: utf-8 -*-
"""v_c_child_vowels.py -- gate (c): the child says child vowels.

/a i u/ presets from the geometry vowel modes (Story & Bunton Table II
q1,q2 on the 60-month tract), rendered through the identical path
(white-noise probe, Welch peak-pick, NO LPC). Gates:

1. F1/F2 within 20% of validate/child_targets.json (the /a/ row was
   revised to literature values 2026-08-26 -- the file's meta and
   STATUS.md carry the full evidence chain; the VTL number contradicted
   both the measured-children literature and the geometry authority).
2. STRICT vowel-triangle ordering:
   F1(a) > F1(u), F1(a) > F1(i), F2(i) > F2(a) > F2(u).

Also prints the same-termination analytic twin per vowel, so a render
error is separable from a geometry-vs-target disagreement.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

import analytic2
import geometry
import measure as M
import mouth2

SECONDS = 6.0
NPERSEG = 8192
SMOOTH_HZ = 30.0
HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    with open(os.path.join(HERE, "child_targets.json"), encoding="utf-8") as f:
        targets = json.load(f)

    N = mouth2.N_MAIN
    got = {}
    ok_all = True
    print("GATE (c) -- child vowels /a i u/ at %d months (N=%d)"
          % (mouth2.AGE_MONTHS, N))
    for v in ("a", "i", "u"):
        _, a44 = geometry.child_area(mouth2.AGE_MONTHS, vowel=v)
        aN = geometry.resample_areas(a44, N)
        freqs = np.arange(150.0, 6000.0, 1.0)
        twin = analytic2.peak_pick(
            freqs, np.abs(M.twin_transfer(aN, freqs)["H_lip"]), n=2)
        track, velum = M.track_for(aN, SECONDS)
        lip16, _ = M.noise_probe(track, velum, seconds=SECONDS)
        pk = M.spectral_peaks(lip16, n=2, fmin=250.0, nperseg=NPERSEG,
                              smooth_hz=SMOOTH_HZ)
        got[v] = pk
        t = targets[v]
        e1 = abs(pk[0] - t["F1"]) / t["F1"] * 100 if len(pk) > 0 else 999
        e2 = abs(pk[1] - t["F2"]) / t["F2"] * 100 if len(pk) > 1 else 999
        ok = e1 <= 20.0 and e2 <= 20.0
        ok_all &= ok
        print("  /%s/ target %4.0f/%4.0f  twin %s  rendered %s  "
              "err %4.1f%%/%4.1f%%  %s"
              % (v, t["F1"], t["F2"],
                 "/".join("%.0f" % x for x in twin),
                 "/".join("%.0f" % x for x in pk),
                 e1, e2, "PASS" if ok else "FAIL"))

    tri = (got["a"][0] > got["u"][0] and got["a"][0] > got["i"][0]
           and got["i"][1] > got["a"][1] > got["u"][1])
    print("  vowel triangle: F1(a)>F1(u), F1(a)>F1(i), F2(i)>F2(a)>F2(u) "
          "-> %s" % ("PASS" if tri else "FAIL"))
    ok_all &= tri
    print("  -> %s" % ("PASS" if ok_all else "FAIL"))
    return {"gate": "c", "pass": bool(ok_all), "rendered": got,
            "triangle": bool(tri)}


if __name__ == "__main__":
    r = main()
    sys.exit(0 if r["pass"] else 1)
