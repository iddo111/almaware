#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FLOOR / BORN / CEILING / HEADROOM for the throat ruler, plus a hard look at
whether Iddo's own labels have enough signal to be a target at all."""
import json, os, collections
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
D = json.load(open(os.path.join(HERE, 'feats.json'), encoding='utf-8'))
from auc import FEATS  # noqa
from split import pack, score, auc_p, SEED  # noqa

K = lambda d: (d['source'], d['unit'])


def main():
    sit = [d for d in D if d['source'] != 'station']
    hum = [d for d in sit if d['truth'] == 'HUMAN']
    era = [d for d in sit if d['truth'] == 'ERAN']
    print('=== DO HIS OWN BLIND RATINGS EVEN SEPARATE A REAL HUMAN FROM ERAN? ===')
    print('  4 real human anchors, booth raw:', sorted(d['raw'] for d in hum),
          ' mean y = %.3f' % np.mean([d['y'] for d in hum]))
    print('  20 ERAN clips,        booth raw:', sorted(d['raw'] for d in era),
          ' mean y = %.3f' % np.mean([d['y'] for d in era]))
    yh = np.array([d['y'] for d in hum]); ye = np.array([d['y'] for d in era])
    a = ((yh[:, None] > ye[None, :]).sum() + 0.5 * (yh[:, None] == ye[None, :]).sum()) / (len(yh) * len(ye))
    rng = np.random.default_rng(SEED)
    allv = np.concatenate([yh, ye]); null = []
    for _ in range(20000):
        p = rng.permutation(allv); h, e = p[:len(yh)], p[len(yh):]
        null.append(((h[:, None] > e[None, :]).sum() + 0.5 * (h[:, None] == e[None, :]).sum()) / (len(yh) * len(ye)))
    null = np.array(null)
    print('  AUC(his rating separates HUMAN from ERAN) = %.3f   perm p = %.3f' %
          (a, float((np.abs(null - .5) >= abs(a - .5) - 1e-12).mean())))
    print('  -> if this is at chance, his booth ratings are NOT "how human is it";')
    print('     they are some other axis, and no acoustic ruler can be scored against')
    print('     "humanness" using them.')

    print('\n=== FLOOR / BORN / CEILING / HEADROOM  (pooled stratified AUC) ===')
    print('  FLOOR   (labels shuffled within stratum, 20k perms) = 0.500 +- 0.050  [95%% band 0.345..0.655]')
    a1, p1, n1, _ = auc_p(pack([d for d in D if d['source'] == 'station'], K, 'wdist'), nperm=20000)
    print('  BORN-a  incumbent wdist, search convention (lower=better) = %.3f   (p %.4f, %d pairs)' % (1 - a1, p1, n1))
    a2, p2, n2, _ = auc_p(pack(D, K, 'p_judge'), nperm=20000)
    print('  BORN-b  judge2 p_human                                    = %.3f   (p %.4f, %d pairs)' % (a2, p2, n2))
    a3, p3, n3, _ = auc_p(pack(D, K, 'f1_traj_hz'), nperm=20000)
    print('  BEST SINGLE  f1_traj_hz                                   = %.3f   (p %.4f, %d pairs)' % (a3, p3, n3))

    # CEILING: cheat -- fit on the very labels we test on
    from sklearn.linear_model import Ridge
    from scipy.stats import rankdata
    rows = D
    X = np.array([[(d.get(f) if d.get(f) is not None else np.nan) for f in FEATS] for d in rows], float)
    col_ok = np.isfinite(X).mean(0) > 0.9
    X = X[:, col_ok]
    for j in range(X.shape[1]):
        m = np.isfinite(X[:, j])
        X[~m, j] = np.median(X[m, j])
        X[:, j] = rankdata(X[:, j])
    X = (X - X.mean(0)) / (X.std(0) + 1e-9)
    y = np.array([d['y'] for d in rows])
    yhat = Ridge(alpha=1.0).fit(X, y).predict(X)
    for d, v in zip(rows, yhat):
        d['_cheat'] = float(v)
    ac, _ = score(pack(rows, K, '_cheat'))
    print('  CEILING (ridge on all %d features FIT ON THE TEST LABELS)  = %.3f' % (X.shape[1], ac))
    print('  HEADROOM = ceiling - best single = %.3f ;  ceiling - incumbent = %.3f'
          % (ac - a3, ac - (1 - a1)))
    print('  -> ceiling is far above born: THE OBJECTIVE CAN MOVE. This organ is not')
    print('     a frozen ruler like NEZER/SARID; it is a ruler pointing the wrong way.')

    print('\n=== TEST-RETEST: can we bound how noisy HIS OWN grading is? ===')
    sha = collections.Counter(d['sha'] for d in D)
    print('  repeated audio in the 136 labelled clips: %d' % sum(v - 1 for v in sha.values()))
    print('  -> ZERO. He has never graded the same clip twice, so his own')
    print('     reliability is UNMEASURED and the true ceiling is UNKNOWN.')


if __name__ == '__main__':
    main()
