#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SIGN CONSISTENCY across the four adequately-powered syllable cells.
Statistic per feature: min over the 4 cells of AUC (or of 1-AUC, whichever
direction is better) -- i.e. "the worst cell, after allowing the feature to
pick one global direction".
Null: shuffle Iddo's labels inside each cell; take the MAX of that statistic
over all 35 candidates.  That corrects for having searched the whole panel."""
import json, os
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
D = json.load(open(os.path.join(HERE, 'feats.json'), encoding='utf-8'))
from auc import FEATS  # noqa

CELLS = [('station', 'ma'), ('station', 'ba'), ('station', 'ah'), ('sitting-20260901', 'ba')]
NPERM = 20000
rng = np.random.default_rng(20260901)

packs = []
for k in CELLS:
    rows = [d for d in D if (d['source'], d['unit']) == k]
    y = np.array([d['y'] for d in rows])
    Cs, Vs = [], []
    for f in FEATS:
        v = np.array([(d.get(f) if d.get(f) is not None else np.nan) for d in rows], float)
        ok = np.isfinite(v)
        a = np.nan_to_num(v, nan=0.0)
        C = (a[:, None] > a[None, :]).astype(np.float32) + 0.5 * (a[:, None] == a[None, :])
        V = (ok[:, None] & ok[None, :]).astype(np.float32)
        Cs.append(C * V)
        Vs.append(V)
    packs.append((k, y, np.stack(Cs), np.stack(Vs)))


def cellaucs(perm=False):
    out = np.empty((len(CELLS), len(FEATS)))
    for ci, (k, y, C, V) in enumerate(packs):
        yy = rng.permutation(y) if perm else y
        P = (yy[:, None] > yy[None, :]).astype(np.float32)
        num = np.einsum('fij,ij->f', C, P)
        den = np.einsum('fij,ij->f', V, P)
        with np.errstate(invalid='ignore', divide='ignore'):
            out[ci] = num / den
    return out


def stat(A):
    """best of the two directions, then the worst cell"""
    return np.maximum(np.nanmin(A, 0), np.nanmin(1 - A, 0))


obs = cellaucs()
so = stat(obs)
null = np.empty((NPERM, len(FEATS)))
for t in range(NPERM):
    null[t] = stat(cellaucs(True))
mx = np.nanmax(null, axis=1)

print('WORST-CELL AUC (feature allowed one global direction) over the 4 powered cells')
print('%-20s %8s   %s' % ('feature', 'worst', '  '.join('%s/%s' % (c[0][:3], c[1]) for c in CELLS)))
order = np.argsort(-so)
for i in order[:12]:
    p_f = float((mx >= so[i] - 1e-12).mean())
    print('%-20s %8.3f   %s   p_fwer=%.4f' %
          (FEATS[i], so[i], '  '.join('%7.2f' % obs[c, i] for c in range(len(CELLS)))
           .replace('nan', ' -- '), p_f))
print('\nnull: max worst-cell statistic over all %d candidates, %d shuffles' % (len(FEATS), NPERM))
print('  null median %.3f   95th pct %.3f   99th pct %.3f' %
      (np.median(mx), np.percentile(mx, 95), np.percentile(mx, 99)))
n_pos = (obs > 0.5).sum(0)
print('\nfeatures with all 4 cells on the same side of 0.5: %s' %
      [FEATS[i] for i in range(len(FEATS)) if n_pos[i] in (0, 4)])
