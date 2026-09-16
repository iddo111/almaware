#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Try to BREAK f1_traj_hz.  Confounds, estimator robustness, held-out replication."""
import json, os, wave, collections, sys
import numpy as np
import scipy.signal as sig
from scipy.linalg import toeplitz

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from feats import load, frames, db, autocorr_f0, FS  # noqa

D = json.load(open(os.path.join(HERE, 'feats.json'), encoding='utf-8'))
BIG = [('station', 'ma'), ('station', 'ba'), ('station', 'ah'), ('sitting-20260901', 'ba')]
SEED = 20260901


def strat_auc(rows, key, fname=None, fvals=None, nperm=20000, seed=SEED):
    """pooled within-stratum concordance AUC + permutation p"""
    S = collections.defaultdict(list)
    for i, d in enumerate(rows):
        S[key(d)].append(i)
    S = {k: v for k, v in S.items() if len(v) >= 3 and len(set(rows[i]['y'] for i in v)) >= 2}
    if not S:
        return np.nan, np.nan, 0, {}
    rng = np.random.default_rng(seed)
    num = den = 0.0
    perstrat = {}
    packs = []
    for k, idx in S.items():
        y = np.array([rows[i]['y'] for i in idx])
        f = np.array([(fvals[i] if fvals is not None else
                       (rows[i].get(fname) if rows[i].get(fname) is not None else np.nan)) for i in idx], float)
        ok = np.isfinite(f)
        C = (f[:, None] > f[None, :]).astype(float) + 0.5 * (f[:, None] == f[None, :])
        V = (ok[:, None] & ok[None, :]).astype(float)
        P = (y[:, None] > y[None, :]).astype(float)
        n_ = (V * P).sum()
        if n_ == 0:
            continue
        a_ = (C * V * P).sum() / n_
        perstrat[k] = (a_, int(n_), len(idx))
        num += a_ * n_
        den += n_
        packs.append((y, C * V, V))
    obs = num / den
    null = np.empty(nperm)
    for t in range(nperm):
        n2 = d2 = 0.0
        for y, CV, V in packs:
            yp = rng.permutation(y)
            P = (yp[:, None] > yp[None, :]).astype(float)
            nn = (V * P).sum()
            if nn:
                n2 += (CV * P).sum()
                d2 += nn
        null[t] = n2 / d2 if d2 else np.nan
    p = float((np.abs(null - 0.5) >= abs(obs - 0.5) - 1e-12).mean())
    return obs, p, int(den), perstrat


# ---------------------------------------------------------------- alternates
def lpc_f1(x, order):
    if len(x) < order * 3:
        return np.nan
    x = x * np.hanning(len(x))
    x = sig.lfilter([1, -0.97], [1], x)
    r = np.correlate(x, x, 'full')[len(x) - 1:len(x) - 1 + order + 1]
    if r[0] <= 0:
        return np.nan
    r = r.copy()
    r[0] *= 1.0001
    try:
        a = np.linalg.solve(toeplitz(r[:order]), r[1:order + 1])
    except Exception:
        return np.nan
    rts = np.roots(np.concatenate([[1.0], -a]))
    rts = rts[np.imag(rts) > 0.01]
    if not len(rts):
        return np.nan
    f = np.sort(np.angle(rts) * FS / (2 * np.pi))
    f = f[(f > 150) & (f < 5000)]
    return float(f[0]) if len(f) else np.nan


def active_seg(x):
    fr, _ = frames(x)
    e = np.sqrt((fr ** 2).mean(axis=1))
    edb = db(e)
    act = edb > edb.max() - 35
    ai = np.where(act)[0]
    if len(ai) < 6:
        return None
    return x[ai[0] * 160: min(ai[-1] * 160 + 400, len(x))]


def alt_thirds(x, order):
    s = active_seg(x)
    if s is None:
        return np.nan
    t = max(len(s) // 3, 200)
    a, b = lpc_f1(s[:t], order), lpc_f1(s[-t:], order)
    return abs(b - a) if (a == a and b == b) else np.nan


def alt_halves(x, order=14):
    s = active_seg(x)
    if s is None:
        return np.nan
    h = len(s) // 2
    a, b = lpc_f1(s[:h], order), lpc_f1(s[h:], order)
    return abs(b - a) if (a == a and b == b) else np.nan


def alt_track_range(x, order=14):
    """frame-by-frame F1 track -> p90-p10 spread (no start/end assumption)"""
    s = active_seg(x)
    if s is None:
        return np.nan
    w, hop = 400, 160
    vals = [lpc_f1(s[i:i + w], order) for i in range(0, max(len(s) - w + 1, 1), hop)]
    vals = np.array([v for v in vals if v == v])
    if len(vals) < 3:
        return np.nan
    return float(np.percentile(vals, 90) - np.percentile(vals, 10))


def alt_spec_centroid_lowband_range(x):
    """estimator-free stand-in for 'the low resonance moves':
    centroid of 150-1200 Hz energy, p90-p10 over frames.  No LPC at all."""
    s = active_seg(x)
    if s is None:
        return np.nan
    fr, _ = frames(s)
    F = np.abs(np.fft.rfft(fr * np.hanning(fr.shape[1]), axis=1))
    fq = np.fft.rfftfreq(fr.shape[1], 1 / FS)
    m = (fq >= 150) & (fq <= 1200)
    c = (fq[m] * F[:, m]).sum(1) / np.maximum(F[:, m].sum(1), 1e-12)
    if len(c) < 3:
        return np.nan
    return float(np.percentile(c, 90) - np.percentile(c, 10))


def main():
    rows = [d for d in D]
    wavs = {}
    for d in rows:
        pass
    # reload audio once
    import json as _j
    lab = {r['id']: r for r in [_j.loads(l) for l in open(r"D:\CLAUDE\eran-brain\judge2\iddo-labels.jsonl", encoding='utf-8')]}
    X = {}
    for d in rows:
        p = lab[d['id']]['path']
        X[d['id']], _ = load(p)

    print('=== 1. CONFOUND: does f1_traj survive stratifying by ARM as well? ===')
    for name, key in [('(source,unit)', lambda d: (d['source'], d['unit'])),
                      ('(source,unit,arm)', lambda d: (d['source'], d['unit'], d['arm'])),
                      ('(source,unit,date)', lambda d: (d['source'], d['unit'], d['date']))]:
        a, p, n, ps = strat_auc(rows, key, fname='f1_traj_hz', nperm=5000)
        print('  %-20s AUC %.3f  p %.4f  pairs %d  strata %d' % (name, a, p, n, len(ps)))

    print('\n=== 2. HELD-OUT: the blind sitting ALONE (other day, other scale) ===')
    sit = [d for d in rows if d['source'] != 'station']
    a, p, n, ps = strat_auc(sit, lambda d: (d['source'], d['unit']), fname='f1_traj_hz', nperm=20000)
    print('  all sitting          AUC %.3f  p %.4f  pairs %d' % (a, p, n))
    sit_e = [d for d in sit if d['truth'] == 'ERAN']
    a2, p2, n2, _ = strat_auc(sit_e, lambda d: (d['source'], d['unit']), fname='f1_traj_hz', nperm=20000)
    print('  sitting, ERAN only   AUC %.3f  p %.4f  pairs %d  (4 human anchors removed)' % (a2, p2, n2))
    stn = [d for d in rows if d['source'] == 'station']
    a3, p3, n3, _ = strat_auc(stn, lambda d: (d['source'], d['unit']), fname='f1_traj_hz', nperm=20000)
    print('  station only         AUC %.3f  p %.4f  pairs %d' % (a3, p3, n3))

    print('\n=== 3. LEAVE-ONE-STRATUM-OUT ===')
    for k in BIG:
        sub = [d for d in rows if (d['source'], d['unit']) != k]
        a, p, n, _ = strat_auc(sub, lambda d: (d['source'], d['unit']), fname='f1_traj_hz', nperm=5000)
        print('  drop %-24s AUC %.3f  p %.4f  pairs %d' % (str(k), a, p, n))

    print('\n=== 4. ESTIMATOR ROBUSTNESS (recompute the quantity a different way) ===')
    variants = {}
    for o in (10, 12, 16, 20):
        variants['thirds_lpc%d' % o] = {d['id']: alt_thirds(X[d['id']], o) for d in rows}
    variants['halves_lpc14'] = {d['id']: alt_halves(X[d['id']]) for d in rows}
    variants['track_p90p10_lpc14'] = {d['id']: alt_track_range(X[d['id']]) for d in rows}
    variants['NO-LPC lowband centroid range'] = {d['id']: alt_spec_centroid_lowband_range(X[d['id']]) for d in rows}
    for name, mp in variants.items():
        fv = [mp[d['id']] for d in rows]
        a, p, n, ps = strat_auc(rows, lambda d: (d['source'], d['unit']), fvals=fv, nperm=5000)
        cov = np.isfinite(np.array(fv, float)).mean()
        per = ' '.join('%s/%s=%.2f' % (k[0][:3], k[1], ps[k][0]) for k in BIG if k in ps)
        print('  %-32s AUC %.3f p %.4f cov %.0f%%  %s' % (name, a, p, cov * 100, per))

    print('\n=== 5. IS IT JUST duration / level / voicing in disguise? ===')
    for other in ['dur_active', 'rms_db', 'voiced_frac', 'periodicity', 'f2_traj_hz',
                  'burst_rise_hf_db', 'spec_flux', 'wdist', 'p_judge']:
        x = np.array([(d.get('f1_traj_hz') if d.get('f1_traj_hz') is not None else np.nan) for d in rows])
        z = np.array([(d.get(other) if d.get(other) is not None else np.nan) for d in rows])
        ok = np.isfinite(x) & np.isfinite(z)
        from scipy.stats import spearmanr
        r = spearmanr(x[ok], z[ok]).statistic
        print('  spearman(f1_traj, %-16s) = %+.3f   (n=%d)' % (other, r, ok.sum()))

    print('\n=== 6. RESIDUALISED: f1_traj with dur+rms+voiced_frac regressed out (rank space) ===')
    from scipy.stats import rankdata
    keep = [d for d in rows]
    x = np.array([d['f1_traj_hz'] for d in keep], float)
    Z = np.column_stack([[d['dur_active'] for d in keep], [d['rms_db'] for d in keep],
                         [d['voiced_frac'] for d in keep], [d['periodicity'] for d in keep]]).astype(float)
    ok = np.isfinite(x) & np.isfinite(Z).all(1)
    xr = rankdata(x[ok])
    Zr = np.column_stack([rankdata(Z[ok, j]) for j in range(Z.shape[1])])
    Zr = np.column_stack([np.ones(len(Zr)), Zr])
    beta, *_ = np.linalg.lstsq(Zr, xr, rcond=None)
    resid = xr - Zr @ beta
    fv = np.full(len(keep), np.nan)
    fv[np.where(ok)[0]] = resid
    a, p, n, ps = strat_auc(keep, lambda d: (d['source'], d['unit']), fvals=list(fv), nperm=20000)
    per = ' '.join('%s/%s=%.2f' % (k[0][:3], k[1], ps[k][0]) for k in BIG if k in ps)
    print('  residual f1_traj      AUC %.3f  p %.4f  pairs %d   %s' % (a, p, n, per))


if __name__ == '__main__':
    main()
