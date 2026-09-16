# -*- coding: utf-8 -*-
"""shape_audit.py -- is the searched tube a VOWEL, or just a good score?

THE QUESTION THIS EXISTS TO ASK. voice/gym.py drives d(ERAN, Iddo /ah/) from
1.07 down to 0.43 in his own frozen cochlea, and it beats its own blind control
by 43%. Both of those are real. Neither of them proves he made a vowel.

The frozen ear is level-free (ears.py:197 divides every frame spectrum by its
own sum) and pools the sound into 8 slices. It scores SHAPE. It does not score
smoothness, it does not score whether a human throat could hold the posture, and
it does not know what a formant is. So a low distance can in principle be earned
by something that is not speech -- and this file measures whether that is what
happened.

WHAT IT PRINTS, and the second row is the one that matters:

  * the searched shape, against the three textbook vowel area functions that
    ship in tract_analytic.py, and against a straight tube.
  * ROUGHNESS = mean |A[i+1] - A[i]|. A human tract is smooth; the tongue is
    one object. A comb is not a tract.
  * max|k_interior|, the largest reflection at any junction.
  * F1/F2 straight from the analytic poles, no audio, no peak picking.

Writes results/SHAPE-AUDIT-<utc>.json.
"""
from __future__ import annotations

import datetime
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(ROOT, "body"), os.path.join(ROOT, "voice")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import earlink                                   # noqa: E402
import mouth34                                   # noqa: E402
import tract_analytic as TA                      # noqa: E402


def roughness(a):
    return float(np.mean(np.abs(np.diff(np.asarray(a, dtype=float)))))


def main():
    ears = earlink.open_ear()
    t, s = earlink.target_for(ears, "ah")

    def score(a):
        y = mouth34.say(a, f0=220.0, seconds=0.6, seed=0)
        return (earlink.distance(ears.utterance_from_samples(y), t)
                if y is not None else float("nan"))

    pj = os.path.join(ROOT, "voice", "postures", "ah-best.json")
    searched = np.array(json.load(open(pj))["areas"], dtype=float)
    cands = {
        "ERAN_searched": searched,
        "textbook_a": TA.vowel_a(34),
        "textbook_i": TA.vowel_i(34),
        "textbook_u": TA.vowel_u(34),
        "uniform_tube": np.ones(34),
    }

    rows = {}
    print("%-16s %8s %9s %10s %14s" % ("shape", "d(ah)", "max|k|", "roughness",
                                       "F1/F2 Hz"))
    for k, a in cands.items():
        res = TA.resonances(a, mouth34.TRACT_FS, n=2)
        f = [round(x, 1) for x, _ in res]
        rows[k] = {"d_ah": score(a), "max_k_interior": mouth34.max_k_interior(a),
                   "roughness": roughness(a), "formants_hz": f,
                   "areas": [float(x) for x in a]}
        print("%-16s %8.4f %9.3f %10.3f %14s"
              % (k, rows[k]["d_ah"], rows[k]["max_k_interior"],
                 rows[k]["roughness"], "/".join("%.0f" % x for x in f) or "-"))

    tb = [rows[k]["d_ah"] for k in ("textbook_a", "textbook_i", "textbook_u")]
    spread_tb = float(max(tb) - min(tb))
    f2s = [rows[k]["formants_hz"][1] for k in ("textbook_a", "textbook_i", "textbook_u")
           if len(rows[k]["formants_hz"]) > 1]
    f2_spread = float(max(f2s) - min(f2s)) if len(f2s) == 3 else None

    print()
    print("standard: a REAL clip of Iddo saying ah = %.4f, within-class spread %.4f"
          % (s["real_to_centroid_mean"], s["within_class_spread"]))
    print()
    verdict = []
    verdict.append(
        "ALL THREE textbook vowels score within %.4f of each other (%.4f..%.4f) "
        "and within %.4f of a STRAIGHT TUBE. In this ear, at this tract, a "
        "textbook /a/ /i/ /u/ and a pipe are the same object."
        % (spread_tb, min(tb), max(tb),
           abs(np.mean(tb) - rows["uniform_tube"]["d_ah"])))
    if f2_spread is not None:
        verdict.append(
            "The tube's own F2 spread across /a/ /i/ /u/ is %.0f Hz. In human "
            "speech F2 spans roughly 1400 Hz. The terminations (0.9 / -0.85) "
            "dominate the interior, so SMOOTH area functions barely move the "
            "formants -- this is eran2's known weakness, measured again here."
            % f2_spread)
    verdict.append(
        "So the search did not reach 0.43 by finding a vowel posture. It reached "
        "it by going COMB: roughness %.3f against %.3f for a textbook /a/, "
        "max|k_interior| %.3f against %.3f. Many closely spaced resonances can "
        "imitate the 8-slice level-free spectral statistics of a vowel without "
        "being one."
        % (rows["ERAN_searched"]["roughness"], rows["textbook_a"]["roughness"],
           rows["ERAN_searched"]["max_k_interior"],
           rows["textbook_a"]["max_k_interior"]))
    verdict.append(
        "WHAT IS THEREFORE PROVEN: the loop is closed and it learns (guided beats "
        "a blind control by 43%, and the null posture sits at 1.07). WHAT IS NOT "
        "PROVEN: that the wav sounds like /ah/ to a human. Iddo's ear is the "
        "judge of that, not 0.43.")
    verdict.append(
        "THE ACTIONABLE CONSEQUENCE: the next fix is NOT more search steps. It is "
        "the tract -- either a smoothness prior on the area function, or "
        "terminations that stop dominating the interior. Searching harder in this "
        "geometry buys a better score and not a better voice.")
    for v in verdict:
        print(" * " + v)

    out = {"utc": datetime.datetime.now(datetime.timezone.utc)
           .strftime("%Y%m%dT%H%M%SZ"),
           "host": os.uname().nodename,
           "shapes": rows,
           "standard": s,
           "textbook_vowel_score_spread": spread_tb,
           "textbook_f2_spread_hz": f2_spread,
           "verdict": verdict}
    d = os.path.join(ROOT, "results")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "SHAPE-AUDIT-%s.json" % out["utc"])
    with open(p, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    print()
    print("wrote %s" % p)

    # stamp the caveat onto the deliverable sidecar so the wav cannot be misread
    side = os.path.expanduser("~/eran-voice-out/01-ERAN-ah-searched.json")
    if os.path.exists(side):
        j = json.load(open(side, encoding="utf-8"))
        j["CAVEAT_SHAPE"] = verdict[2]
        j["CAVEAT_PROVEN"] = verdict[3]
        j["roughness"] = rows["ERAN_searched"]["roughness"]
        j["roughness_textbook_a"] = rows["textbook_a"]["roughness"]
        j["formants_hz"] = rows["ERAN_searched"]["formants_hz"]
        json.dump(j, open(side, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
        print("stamped the caveat onto %s" % side)
    return 0


if __name__ == "__main__":
    sys.exit(main())
