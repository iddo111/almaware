#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stratified concordance-AUC of every candidate ruler against Iddo's rulings,
with a within-stratum permutation null and a family-wise max-statistic correction.

Label y = iddo_human, already normalised so HIGHER = MORE HUMAN in both scales
(station 1/2/3 -> 1.0/0.5/0.0 ; booth 1..5 -> (raw-1)/4).  Verified in-script.
Strata = (source, unit): the two opposite-direction scales are NEVER compared
across, and syllable identity can never drive the score.
"""
import json, os, sys, collections
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
D = json.load(open(os.path.join(HERE, 'feats.json'), encoding='utf-8'))

FEATS = ['burst_rise_db', 'burst_rise_hf_db', 'head_hf_ratio_db', 'burst_time_s',
         'vot_ms', 'voice_onset_s',
         'f1_med', 'f2_med', 'f2_f1', 'f2_traj_hz', 'f1_traj_hz', 'spec_flux',
         'tilt_db_oct', 'centroid_hz', 'hf_lf_db',
         'f0_med', 'f0_range_st', 'f0_iqr_st', 'f0_slope_st_s', 'f0_jitter',
         'periodicity', 'hnr_db', 'voiced_frac',
         'dur_total', 'dur_active', 'attack_s', 'decay_s',
         'mod_ratio', 'noisefloor_rel_db', 'snr_db', 'crest_db', 'rms_db', 'peak_db',
         'wdist', 'p_judge']

SEED = 20260901
NPERM = 20000
BATCH = 250


def getf(x, f):
    v = x.get(f)
    return np.nan if v is None else float(v)


def build(rows):
    S = collections.defaultdict(list)
    for d in rows:
        S[(d['source'], d['unit'])].append(d)
    S = {k: v for k, v in S.items() if len(v) >= 4 and len(set(x['y'] for x in v)) >= 2}
    order = sorted(S, key=lambda k: -len(S[k]))
    st = {}
    for k in order:
        v = S[k]
        n = len(v)
        y = np.array([x['y'] for x in v])
        P0 = (y[:, None] > y[None, :]).astype(np.float32)
        M = np.zeros((len(FEATS), n, n), np.float32)
        V = np.zeros((len(FEATS), n, n), np.float32)
        for fi, f in enumerate(FEATS):
            fv = np.array([getf(x, f) for x in v])
            ok = np.isfinite(fv)
            vv = (ok[:, None] & ok[None, :]).astype(np.float32)
            a = np.nan_to_num(fv, nan=0.0)
            cmp_ = (a[:, None] > a[None, :]).astype(np.float32) + 0.5 * (a[:, None] == a[None, :])
            M[fi] = cmp_ * vv
            V[fi] = vv
        st[k] = dict(v=v, y=y, P0=P0, M=M, V=V, n=n)
    return order, st


def pooled(order, st, Ps):
    """Ps[k] = (B,n,n) permutation pair-masks -> (B, F) pooled AUC"""
    B = next(iter(Ps.values())).shape[0]
    num = np.zeros((B, len(FEATS)), np.float64)
    den = np.zeros((B, len(FEATS)), np.float64)
    for k in order:
        s = st[k]
        num += np.einsum('fij,bij->bf', s['M'], Ps[k], optimize=True)
        den += np.einsum('fij,bij->bf', s['V'], Ps[k], optimize=True)
    with np.errstate(invalid='ignore', divide='ignore'):
        return num / den, den


def main():
    stn = [d for d in D if d['source'] == 'station']
    sit = [d for d in D if d['source'] != 'station']
    chk = (all((d['raw'] == 3) == (d['y'] == 0.0) for d in stn) and
           all((d['raw'] == 1) == (d['y'] == 1.0) for d in stn) and
           all(abs(d['y'] - (d['raw'] - 1) / 4) < 1e-9 for d in sit))
    print('LABEL DIRECTION CHECK (higher y = more human on BOTH scales): %s' % ('PASS' if chk else 'FAIL'))
    if not chk:
        sys.exit('label normalisation wrong - refusing to score')

    order, st = build(D)
    print('\nSTRATA (source, unit)         n   pairs  mean_y')
    for k in order:
        print('  %-27s %3d %6d  %.3f' % (str(k), st[k]['n'], int(st[k]['P0'].sum()), st[k]['y'].mean()))
    print('  TOTAL %d clips, %d usable ordered pairs' %
          (sum(st[k]['n'] for k in order), int(sum(st[k]['P0'].sum() for k in order))))

    obs, obsden = pooled(order, st, {k: st[k]['P0'][None] for k in order})
    obs, obsden = obs[0], obsden[0]

    # per-stratum observed
    per = {}
    for k in order:
        s = st[k]
        a, d_ = pooled([k], {k: s}, {k: s['P0'][None]})
        per[k] = (a[0], d_[0])

    rng = np.random.default_rng(SEED)
    print('\n%d within-stratum permutations ...' % NPERM)
    null = np.empty((NPERM, len(FEATS)))
    done = 0
    while done < NPERM:
        b = min(BATCH, NPERM - done)
        Ps = {}
        for k in order:
            y = st[k]['y']
            yp = np.stack([rng.permutation(y) for _ in range(b)])
            Ps[k] = (yp[:, :, None] > yp[:, None, :]).astype(np.float32)
        a, _ = pooled(order, st, Ps)
        null[done:done + b] = a
        done += b
    dev = np.abs(null - 0.5)
    maxstat = np.nanmax(dev, axis=1)

    print('\n==== POOLED STRATIFIED AUC vs IDDO\'S RULINGS ====')
    print('AUC>0.5 = feature agrees with him; <0.5 = it disagrees (inverted).')
    print('%-20s %7s %6s %8s %9s %9s  %s' %
          ('feature', 'AUC', 'pairs', 'null_sd', 'p_raw', 'p_fwer', 'per-stratum AUC (n)'))
    rank = sorted(range(len(FEATS)), key=lambda i: -(abs(obs[i] - 0.5) if np.isfinite(obs[i]) else -1))
    out = {}
    for i in rank:
        f = FEATS[i]
        a = obs[i]
        if not np.isfinite(a):
            continue
        nd = null[:, i]
        nd = nd[np.isfinite(nd)]
        sd = nd.std()
        praw = float((np.abs(nd - 0.5) >= abs(a - 0.5) - 1e-12).mean())
        pf = float((maxstat >= abs(a - 0.5) - 1e-12).mean())
        ps = []
        for k in order:
            aa, dd = per[k]
            if dd[i] > 0:
                ps.append('%s/%s=%.2f(%d)' % (k[0][:3], k[1], aa[i], st[k]['n']))
        print('%-20s %7.3f %6d %8.3f %9.4f %9.4f  %s' %
              (f, a, int(obsden[i]), sd, praw, pf, ' '.join(ps)))
        out[f] = dict(auc=float(a), pairs=int(obsden[i]), null_sd=float(sd),
                      p_raw=praw, p_fwer=pf,
                      per={str(k): (float(per[k][0][i]), int(per[k][1][i])) for k in order if per[k][1][i] > 0})
    print('\np_fwer = permutation p corrected for having searched all %d candidates.' % len(FEATS))
    print('null AUC sd ~ %.3f; the 95%% two-sided null band on the pooled AUC is [%.3f, %.3f]'
          % (np.nanmean(null.std(axis=0)), 0.5 - np.percentile(maxstat, 95), 0.5 + np.percentile(maxstat, 95)))
    json.dump({'pooled': out, 'strata': {str(k): st[k]['n'] for k in order}, 'nperm': NPERM},
              open(os.path.join(HERE, 'auc.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
