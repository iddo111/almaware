# -*- coding: utf-8 -*-
"""targets_v3.py -- Iddo's real voice, heard through EAR v3.

THE CACHE IS REUSED, NEVER RECOMPUTED HERE: ~/ear-v3/targets-cache/
ear3-t06.json was computed on eran2 from the 600 big-unit t06 clips
through the full Ear-v3 pipeline (scripts/precompute_t06.py + judge.
build_cache). ear3.judge.load_cache() REFUSES a cache whose spec_hash /
judge_spec mismatches the running code -- a stale judge lies.

wdist convention comes from ear3.judge verbatim (spread-weighted L2 with
per-block floors + block balance: legacy192 x12, growth law). This
module only re-exports it and writes the per-unit real-clip bar table
(calib/real-clip-bars.json) -- "the new 13.9": every report prints THESE
numbers; v1 numbers are never quoted beside them without the words
"different ear".
"""
from __future__ import annotations

import json
import os
import sys

EAR_DIR = os.path.expanduser("~/ear-v3")
if EAR_DIR not in sys.path:
    sys.path.insert(0, EAR_DIR)

from ear3 import judge as J                      # noqa: E402

_HERE = os.path.dirname(os.path.abspath(__file__))
BARS_PATH = os.path.join(_HERE, "calib", "real-clip-bars.json")

UNITS = J.UNITS                                   # ah ba ih ma abba ima
wdist = J.wdist
nearest_table = J.nearest_table


def load_all():
    """{unit: stats}. Refuses on spec mismatch (ear3.judge.load_cache)."""
    return J.load_cache()


def write_bars(stats=None, path=BARS_PATH):
    """The per-unit real-clip bar table, from ear3's own numbers."""
    stats = stats or load_all()
    from ear3 import features as F
    bars = {"ear": "ear3", "spec_hash": F.spec_hash(),
            "note": "wdist of Iddo's own takes to their unit centroid, "
                    "through Ear v3. DIFFERENT EAR from v1 -- never compare "
                    "raw numbers across ears.",
            "units": {}}
    for u in UNITS:
        s = stats[u]
        bars["units"][u] = {
            "n_clips": s["n_clips"],
            "real_wdist_mean": s["real_wdist_mean"],
            "real_wdist_min": s["real_wdist_min"],
            "real_wdist_max": s["real_wdist_max"],
            "win_bar_1p3x_mean": 1.3 * s["real_wdist_mean"],
        }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(bars, f, indent=1)
    return bars


if __name__ == "__main__":
    b = write_bars()
    print("real-clip bars (Ear v3, spec %s...):" % b["spec_hash"][:12])
    for u, r in b["units"].items():
        print("  %-5s n=%3d  mean %.3f  min %.3f  max %.3f  win<=%.3f"
              % (u, r["n_clips"], r["real_wdist_mean"], r["real_wdist_min"],
                 r["real_wdist_max"], r["win_bar_1p3x_mean"]))
