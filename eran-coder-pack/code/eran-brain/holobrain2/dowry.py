# -*- coding: utf-8 -*-
"""THE DOWRY - the twelve syllables the sibling is born already holding.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

THE HONESTY REQUIREMENT, and it is not optional. Iddo listened to the best of
these on the morning of 2026-09-01 and his verdict was, verbatim:

    "כולם לא שווים כלום"        - they are all worth nothing

So this module carries what the dowry ACTUALLY is:

    "what the old ruler considered best"   -- NOT "verified speech".

That distinction is the whole reason this file exists rather than a folder of
wavs. Every syllable here carries its own provenance and its own standing
verdict, and `verdict()` refuses to describe the dowry as a solved mouth. If a
downstream report says the sibling "can say twelve syllables", that report is
wrong and this module is the evidence.

WHAT IS ACTUALLY INHERITED. Not the audio - the GESTURE. Each best.json holds a
motor program: articulator keyframes, segment durations, an f0 contour, a glide
and a burst. That is what "born knowing the syllable" means here: the newborn
holds the movement, not a recording of it.

MEASURED FACTS ABOUT THIS DOWRY (read off the files, printed by `--table`):
  * 12/12 carry a gesture.
  * Only 4 of 12 (pa, ma, na, ta) beat their own win-bar. The other 8 are ABOVE
    the bar the sweep set for them - by the old ruler's own arithmetic they did
    not win.
  * `aa` fails the acoustic gate outright (gate_pass = false).
  * 11 of 12 match the numbers Iddo dictated at 12:27 to 4 decimal places. `na`
    improved from 4.414 to 4.3831 because the sweep is still running. Both
    numbers are kept below; neither is quietly overwritten.
"""
from __future__ import annotations

import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
DOWRY_DIR = os.path.join(_HERE, "dowry")

# Exactly what Iddo dictated at 2026-09-01 12:27, kept verbatim so that any later
# drift in the live sweep is visible as drift and never silently absorbed.
IDDO_1227 = {
    "pa": (3.279, 5.139), "ma": (4.284, 5.076), "na": (4.414, 5.005),
    "ta": (4.725, 5.172), "ga": (5.197, 5.123), "da": (5.234, 5.136),
    "la": (5.252, 5.129), "ka": (6.342, 5.053), "aa": (7.145, 5.163),
    "ih": (9.707, 4.936), "ah": (13.694, 5.149), "ra": (30.922, 5.191),
}

IDDO_VERDICT = {
    "when": "2026-09-01, morning",
    "said": "כולם לא שווים כלום",
    "means": "all of them are worth nothing",
    "standing": True,
    "so": ("The dowry is what the OLD RULER scored best. It is not verified "
           "speech. Iddo's ear rejected it and that verdict stands until he "
           "himself lifts it."),
}


def load(unit: str) -> dict:
    """One syllable of the dowry, with its provenance attached."""
    p = os.path.join(DOWRY_DIR, unit + ".json")
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    dictated = IDDO_1227.get(unit)
    return {
        "unit": d["unit"],
        "wdist": d["wdist"],
        "win_bar": d["win_bar_1p3x_mean"],
        "beat_own_bar": d["wdist"] < d["win_bar_1p3x_mean"],
        "gate_pass": d["gate_pass"],
        "review_flagged": d.get("review_flagged", False),
        "gesture": d["gesture"],                  # the real inheritance
        "x": d.get("x"),
        "nearest": {n["unit"]: n["wdist"] for n in d["nearest"]},
        "provenance": {
            "arm": d.get("arm"), "seed": d.get("seed"), "utc": d.get("utc"),
            "evals": d.get("evals"), "organs": d.get("organs"),
            "source": "eran2:~/syllable-sweep/run/sweep-%s-20" % d.get("arm"),
            "dictated_by_iddo_1227": dictated[0] if dictated else None,
            "drift_since_dictated": (round(d["wdist"] - dictated[0], 4)
                                     if dictated else None),
        },
        "verdict": IDDO_VERDICT,
        "wav": os.path.join(DOWRY_DIR, unit + ".wav"),
    }


def load_all() -> dict:
    return {u: load(u) for u in IDDO_1227}


def verdict(all_units: dict | None = None) -> dict:
    """The one paragraph any report about this sibling must carry.

    Deliberately worded so it cannot be quoted as good news."""
    d = all_units or load_all()
    beat = sorted(u for u, v in d.items() if v["beat_own_bar"])
    gated = sorted(u for u, v in d.items() if not v["gate_pass"])
    return {
        "n_units": len(d),
        "n_with_gesture": sum(1 for v in d.values() if v.get("gesture")),
        "beat_own_win_bar": beat,
        "n_beat_own_win_bar": len(beat),
        "failed_acoustic_gate": gated,
        "iddo_verdict": IDDO_VERDICT["said"],
        "iddo_verdict_en": IDDO_VERDICT["means"],
        "what_this_is": ("what the old ruler considered best - NOT verified "
                         "speech. %d of %d did not even beat their own win-bar."
                         % (len(d) - len(beat), len(d))),
        "do_not_say": "the sibling can say twelve syllables",
    }


if __name__ == "__main__":
    a = load_all()
    print("%-5s %10s %9s %9s %6s %8s %8s  %s"
          % ("unit", "wdist", "win_bar", "dictated", "gate", "beat_bar", "gesture", "arm"))
    for u, v in sorted(a.items(), key=lambda kv: kv[1]["wdist"]):
        p = v["provenance"]
        print("%-5s %10.4f %9.3f %9.3f %6s %8s %8s  %s"
              % (u, v["wdist"], v["win_bar"], p["dictated_by_iddo_1227"],
                 v["gate_pass"], v["beat_own_bar"], bool(v["gesture"]), p["arm"]))
    print()
    print(json.dumps(verdict(a), indent=2, ensure_ascii=False))
