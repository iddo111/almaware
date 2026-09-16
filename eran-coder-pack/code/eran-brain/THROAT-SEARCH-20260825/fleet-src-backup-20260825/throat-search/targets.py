# -*- coding: utf-8 -*-
"""targets.py -- Iddo's real voice, heard through the EXTENDED search judge.

Follows voice/earlink.py's conventions on eran1 exactly, with the one addition
this search exists for: percepts are 200-d (frozen 192 + 8-energy contour).

THE JUDGE IS ERAN'S OWN EAR ONLY. The corpus is Iddo's 657 real recordings of
six units (t06). Never TTS, never a synthetic clip: the synthetic corpus was
measured on 2026-08-23 to transfer to a real mouth AT CHANCE (6.1% vs 4.5%).

TWO DISTANCES, both written down, because they answer different questions:
  * weighted  -- babble.py's convention: each dim scaled by 1/its spread over
    Iddo's own takes of that unit. This is the SEARCH objective; it is what
    lets 8 energy numbers that swing by whole log-units live in the same
    metric as 192 spectral dims that move by hundredths.
  * plain192  -- earlink.distance on the L2-normalised frozen-192 part alone,
    against the L2-normalised frozen centroid: the exact number gym.py
    printed (ah-best = 0.4312...), kept so every old result stays comparable.
"""
from __future__ import annotations

import json
import os
import tempfile

import numpy as np

CORPUS = os.path.expanduser(os.environ.get(
    "ERAN_HUMAN_CORPUS", os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                      "data", "t06")))
UNITS = ["ah", "ba", "ih", "ma", "abba", "ima"]
W_FLOOR = 1e-3
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "targets-cache.json")


def clips(unit, corpus=None, limit=None):
    d = corpus or CORPUS
    if not os.path.isdir(d):
        raise FileNotFoundError("no human corpus at %s" % d)
    names = sorted(n for n in os.listdir(d)
                   if n.endswith(".wav") and n.split("_")[0] == unit)
    if not names:
        raise FileNotFoundError("no clips for unit %r in %s" % (unit, d))
    if limit:
        names = names[:limit]
    return [os.path.join(d, n) for n in names]


def percepts(ext, paths):
    return np.stack([ext.utterance(p) for p in paths])


def _stats_for(ext, unit, corpus=None):
    P = percepts(ext, clips(unit, corpus))
    n192 = ext.frozen.dim
    t = P.mean(axis=0)                            # 200-d, NOT re-normalised
    w = np.maximum(P.std(axis=0), W_FLOOR)        # per-dim honest spread
    # earlink-identical frozen-192 target for the legacy metric
    t192 = P[:, :n192].mean(axis=0)
    nn = float(np.linalg.norm(t192))
    t192 = t192 / nn if nn > 0 else t192
    wd = np.sqrt(np.sum(((P - t[None, :]) / w[None, :]) ** 2, axis=1))
    p192 = np.linalg.norm(P[:, :n192] - t192[None, :], axis=1)
    return {"unit": unit, "n_clips": int(len(P)),
            "target": t.tolist(), "w": w.tolist(), "t192": t192.tolist(),
            "real_wdist_mean": float(wd.mean()),
            "real_wdist_min": float(wd.min()),
            "real_wdist_max": float(wd.max()),
            "real_plain192_mean": float(p192.mean()),
            "real_plain192_min": float(p192.min())}


def load_all(ext, corpus=None, cache=CACHE, verbose=False):
    """{unit: stats} for all six units, cached on disk (atomic write; a lost
    race just rewrites identical content)."""
    if cache and os.path.exists(cache):
        try:
            with open(cache, "r", encoding="utf-8") as f:
                d = json.load(f)
            if sorted(d) == sorted(UNITS) and d["ah"].get("dim") == ext.dim:
                return d
        except (ValueError, OSError, KeyError):
            pass
    d = {}
    for u in UNITS:
        if verbose:
            print("  hearing all of Iddo's /%s/ takes..." % u, flush=True)
        d[u] = _stats_for(ext, u, corpus)
        d[u]["dim"] = ext.dim
    if cache:
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(cache), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(d, f)
        os.replace(tmp, cache)
    return d


def wdist(vec, stats):
    """The search objective: spread-weighted distance to one unit's centre."""
    t = np.asarray(stats["target"], dtype=float)
    w = np.asarray(stats["w"], dtype=float)
    return float(np.sqrt(np.sum(((np.asarray(vec, dtype=float) - t) / w) ** 2)))


def plain192(vec, stats, n192=192):
    """gym.py/earlink's exact legacy number, for continuity with every old run."""
    v = np.asarray(vec, dtype=float)[:n192]
    nn = float(np.linalg.norm(v))
    v = v / nn if nn > 0 else v
    return float(np.linalg.norm(v - np.asarray(stats["t192"], dtype=float)))


def nearest_table(vec, all_stats):
    """babble.py's embarrassment control: which unit's cloud is this nearest?"""
    rows = sorted(((u, wdist(vec, s)) for u, s in all_stats.items()),
                  key=lambda r: r[1])
    return [{"unit": u, "wdist": round(d, 4)} for u, d in rows]
