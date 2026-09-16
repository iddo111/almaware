#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Clean protocol, no leakage:
   SELECT the ruler on the STATION rows only, then TEST it once on the BLIND
   SITTING rows only (different day, different rating scale, clips he had never
   rated before).  Also: how much power does the within-arm control actually have?
"""
import json, os, collections
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
D = json.load(open(os.path.join(HERE, 'feats.json'), encoding='utf-8'))
from auc import FEATS  # noqa

SEED = 20260901


def pack(rows, key, fname):
    S = collections.defaultdict(list)
    for d in rows:
        S[key(d)].append(d)
    out = []
    for k, v in S.items():
        if len(v) < 3 or len(set(x['y'] for x in v)) < 2:
            continue
        y = np.array([x['y'] for x in v])
        f = np.array([(x.get(fname) if x.get(fname) is not None else np.nan) for x in v], float)
        ok = np.isfinite(f)
        a = np.nan_to_num(f, nan=0.0)
        C = ((a[:, None] > a[None, :]).astype(float) + 0.5 * (a[:, None] == a[None, :]))
        V = (ok[:, None] & ok[None, :]).astype(float)
        out.append((k, y, C * V, V))
    return out


def score(packs, perm=None, rng=None):
    num = den = 0.0
    for k, y, CV, V in packs:
        yy = rng.permutation(y) if perm else y
        P = (yy[:, None] > yy[None, :]).astype(float)
        n = (V * P).sum()
        if n:
            num += (CV * P).sum()
            den += n
    return (num / den if den else np.nan), den


def auc_p(packs, nperm=20000, seed=SEED):
    rng = np.random.default_rng(seed)
    a, n = score(packs)
    if not np.isfinite(a):
        return a, np.nan, n, np.nan
    null = np.array([score(packs, True, rng)[0] for _ in range(nperm)])
    return a, float((np.abs(null - 0.5) >= abs(a - 0.5) - 1e-12).mean()), n, float(np.nanstd(null))


def main():
    stn = [d for d in D if d['source'] == 'station']
    sit = [d for d in D if d['source'] != 'station']
    K = lambda d: (d['source'], d['unit'])

    print('=== A. SELECT on STATION only (113 clips, 4 syllables) ===')
    tab = []
    for f in FEATS:
        a, n = score(pack(stn, K, f))
        if np.isfinite(a):
            tab.append((abs(a - 0.5), a, int(n), f))
    tab.sort(reverse=True)
    for dv, a, n, f in tab[:8]:
        print('   %-20s station AUC %.3f (%d pairs)' % (f, a, n))
    winner = tab[0][3]
    print('   -> SELECTED: %s' % winner)

    print('\n=== B. TEST that one choice ONCE on the BLIND SITTING (24 clips, never rated before) ===')
    for name, rows in [('sitting all', sit), ('sitting ERAN-only', [d for d in sit if d['truth'] == 'ERAN'])]:
        a, p, n, sd = auc_p(pack(rows, K, winner))
        print('   %-20s AUC %.3f  perm p %.4f  pairs %d  null_sd %.3f' % (name, a, p, n, sd))

    print('\n=== C. and the reverse: rank ALL features on the SITTING alone ===')
    tab2 = []
    for f in FEATS:
        a, n = score(pack(sit, K, f))
        if np.isfinite(a) and n:
            tab2.append((abs(a - 0.5), a, int(n), f))
    tab2.sort(reverse=True)
    for dv, a, n, f in tab2[:8]:
        print('   %-20s sitting AUC %.3f (%d pairs)' % (f, a, n))

    print('\n=== D. POWER of the within-arm control (source,unit,arm) ===')
    K2 = lambda d: (d['source'], d['unit'], d['arm'])
    pk = pack([d for d in D], K2, 'f1_traj_hz')
    a, p, n, sd = auc_p(pk, nperm=20000)
    print('   observed AUC %.3f  p %.4f  pairs %d  null_sd %.3f' % (a, p, n, sd))
    print('   -> smallest AUC this control could have detected at p<0.05: %.3f' % (0.5 + 1.96 * sd))
    print('   (the pooled effect is 0.782; within-arm the test cannot resolve anything below %.2f)' % (0.5 + 1.96 * sd))
    grp = collections.Counter((d['source'], d['unit'], d['arm']) for d in D)
    usable = [k for k, v in grp.items() if v >= 3]
    print('   arms with >=3 clips: %d of %d' % (len(usable), len(grp)))

    print('\n=== E. within-arm, all features (which if any survives the strictest control) ===')
    tab3 = []
    for f in FEATS:
        a, n = score(pack(D, K2, f))
        if np.isfinite(a) and n:
            tab3.append((abs(a - 0.5), a, int(n), f))
    tab3.sort(reverse=True)
    for dv, a, n, f in tab3[:8]:
        aa, pp, nn, ss = auc_p(pack(D, K2, f), nperm=5000)
        print('   %-20s within-arm AUC %.3f  p %.4f  (%d pairs)' % (f, aa, pp, nn))

    print('\n=== F. the incumbent rulers, stated plainly ===')
    for f in ['wdist', 'p_judge']:
        a, p, n, sd = auc_p(pack(stn if f == 'wdist' else D, K, f), nperm=20000)
        print('   %-10s AUC %.3f  p %.4f  pairs %d' % (f, a, p, n))
    # wdist convention: LOWER is better in the search, so agreement with Iddo
    # would show as AUC < 0.5.  Report the search-convention number too.
    a, p, n, sd = auc_p(pack(stn, K, 'wdist'), nperm=20000)
    print('   wdist in SEARCH convention (lower=better): agreement AUC = %.3f' % (1 - a))


if __name__ == '__main__':
    main()
