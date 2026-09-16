# -*- coding: utf-8 -*-
"""Shared test plumbing: sys.path bootstrap + cached-corpus loading."""
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

CORPUS = os.path.expanduser("~/eran-cortex/data/t06")
NPZ = os.path.join(ROOT, "targets-cache", "t06-feats.npz")


def load_t06():
    from ear3 import features as F
    z = np.load(NPZ, allow_pickle=False)
    if str(z["spec_hash"]) != F.spec_hash():
        raise SystemExit("t06-feats.npz is stale (spec_hash mismatch); "
                         "rerun scripts/precompute_t06.py")
    return z


def by_unit(z):
    names = [str(n) for n in z["names"]]
    out = {}
    for i, nm in enumerate(names):
        out.setdefault(nm.split("_")[0], []).append(i)
    return names, out
