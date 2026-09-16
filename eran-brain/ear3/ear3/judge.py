# -*- coding: utf-8 -*-
"""judge.py -- Ear v3 targets cache + wdist. Same convention as legacy
targets.py (the throat-search judge): per unit a centroid over Iddo's real
takes and a per-dim spread, wdist = spread-weighted L2.

SPREAD FLOOR (documented choice): legacy used a single absolute floor 1e-3.
Ear-v3 blocks live on wildly different scales (L2-normalized 192 dims vs
log-loudness vs Hz), so the floor is PER BLOCK:

    floor_block = max(1e-3, 0.05 * median(std of dims in that block))

i.e. no dim may be trusted more than 20x the typical dim of its own block.
This keeps one nearly-constant dim from dominating wdist (the v1 cheat
mechanism) while still letting genuinely tight dims count.

BLOCK BALANCE (measured choice, 2026-08-26). Plain concatenation let the
804 new dims DROWN the frozen 192: six-way LOO fell to 0.583 vs 0.643 for
the 192 alone (the growth law violated in the metric). Each block's
contribution is therefore normalized by its dimensionality (w scaled by
sqrt(d_b)) and given a fixed gain: legacy192 x12, the four new blocks x1
each -- the identity block carries 75% of the metric, the new layers 25%.
Measured on the 600-clip t06 LOO: 0.695 six / 0.830 binary, vs 0.642/0.825
for the legacy-200 judge under the SAME protocol. Sensitivity: gains 4-16
on the legacy block all land 0.683-0.697, so the dial is coarse, not
tuned. Honesty note: chosen on the same 600 clips (no second corpus
exists); the gates + real-clip bar + Iddo's listen stay the anti-overfit
protection.

CACHE: targets-cache/ear3-t06.json carries spec_hash = sha256 of
features.FEATURE_SPEC (block names/dims/params + carfac SHA + patch id + the
frozen SPL gain) AND judge_spec (floors, block gains). load_cache REFUSES a
cache whose spec mismatches the running code -- a stale judge lies.
"""
from __future__ import annotations

import json
import os
import tempfile

import numpy as np

from ear3 import features as F

UNITS = ["ah", "ba", "ih", "ma", "abba", "ima"]
W_FLOOR_ABS = 1e-3
W_FLOOR_REL = 0.05
BLOCK_GAINS = {"legacy192": 12.0, "level": 1.0, "cochleagram": 1.0,
               "pitch": 1.0, "modulation": 1.0}
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "targets-cache")
CACHE = os.path.join(CACHE_DIR, "ear3-t06.json")


def judge_spec():
    return {"w_floor_abs": W_FLOOR_ABS, "w_floor_rel": W_FLOOR_REL,
            "block_norm": "sqrt(d_b)", "block_gains": BLOCK_GAINS}


def spread_floor(std):
    """Per-block floor + block-balance scaling of a raw per-dim std vector.

    The returned w goes STRAIGHT into wdist's denominator, so the block
    balance lives here: w = max(std, floor_b) * sqrt(d_b) / sqrt(gain_b).
    """
    std = np.asarray(std, dtype=np.float64)
    w = std.copy()
    for name, lo, hi in F.block_ranges():
        med = float(np.median(std[lo:hi]))
        floor = max(W_FLOOR_ABS, W_FLOOR_REL * med)
        scale = np.sqrt(hi - lo) / np.sqrt(BLOCK_GAINS[name])
        w[lo:hi] = np.maximum(std[lo:hi], floor) * scale
    return w


def unit_stats(P):
    """P (n_takes, 996) -> stats dict for one unit."""
    t = P.mean(axis=0)
    w = spread_floor(P.std(axis=0))
    wd = np.sqrt(np.sum(((P - t[None, :]) / w[None, :]) ** 2, axis=1))
    return {"n_clips": int(len(P)),
            "target": t.tolist(), "w": w.tolist(),
            "real_wdist_mean": float(wd.mean()),
            "real_wdist_min": float(wd.min()),
            "real_wdist_max": float(wd.max())}


def wdist(vec, stats):
    t = np.asarray(stats["target"], dtype=np.float64)
    w = np.asarray(stats["w"], dtype=np.float64)
    v = np.asarray(vec, dtype=np.float64)
    return float(np.sqrt(np.sum(((v - t) / w) ** 2)))


def nearest_table(vec, all_stats):
    rows = sorted(((u, wdist(vec, s)) for u, s in all_stats.items()
                   if u in UNITS), key=lambda r: r[1])
    return [{"unit": u, "wdist": round(d, 4)} for u, d in rows]


def build_cache(vectors_by_unit, cache=CACHE):
    """{unit: (n,996) array} -> write the cache with the current spec_hash."""
    d = {"spec_hash": F.spec_hash(), "judge_spec": judge_spec(),
         "dim": F.DIM, "units": {}}
    for u in UNITS:
        d["units"][u] = unit_stats(np.asarray(vectors_by_unit[u]))
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(cache), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(d, f)
    os.replace(tmp, cache)
    return d


def load_cache(cache=CACHE):
    """Load and VERIFY. A spec_hash mismatch is a refusal, never a warning."""
    with open(cache, encoding="utf-8") as f:
        d = json.load(f)
    want = F.spec_hash()
    got = d.get("spec_hash")
    if got != want:
        raise RuntimeError(
            f"targets cache {cache} was built for spec {got} but the running "
            f"code is spec {want} -- rebuild the cache (scripts/"
            f"precompute_t06.py then judge.build_cache); a stale judge lies.")
    if d.get("dim") != F.DIM:
        raise RuntimeError(f"cache dim {d.get('dim')} != {F.DIM}")
    if d.get("judge_spec") != judge_spec():
        raise RuntimeError(
            f"targets cache judge_spec {d.get('judge_spec')} != running "
            f"{judge_spec()} -- rebuild the cache")
    return d["units"]
