#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Extract candidate ruler features from Iddo's 136 labelled clips.
NO AUDIO IS PLAYED. Files are read as bytes and measured numerically only.
"""
import json, os, re, wave, hashlib, sys
import numpy as np
import scipy.signal as sig
from scipy.linalg import toeplitz

FS = 16000
LAB = r"D:\CLAUDE\eran-brain\judge2\iddo-labels.jsonl"
PERCLIP = r"D:\CLAUDE\eran-brain\judge2\runs\acceptance-perclip.json"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "feats.json")

UNIT_PATS = [r'_(ba|ma|ah|ih|pa|ta|ga|na)[-_]',
             r'ERAN-best-(ba|ma|ah|ih|pa|ta|ga|na)-',
             r'ERAN-(ba|ma|ah|ih|pa|ta|ga|na)-',
             r'^(ba|ma|ah|ih|pa|ta|ga|na)[-_]']


def unit_of(r):
    if r.get('unit'):
        return r['unit']
    b = os.path.basename(r.get('path_original') or r.get('path_claimed') or '')
    for p in UNIT_PATS:
        m = re.search(p, b)
        if m:
            return m.group(1)
    return 'unk'


def load(p):
    with wave.open(p) as w:
        assert w.getframerate() == FS and w.getnchannels() == 1 and w.getsampwidth() == 2
        raw = w.readframes(w.getnframes())
    x = np.frombuffer(raw, '<i2').astype(np.float64) / 32768.0
    return x, hashlib.sha256(raw).hexdigest()[:16]


def frames(x, n=400, hop=160):
    if len(x) < n:
        x = np.pad(x, (0, n - len(x)))
    idx = np.arange(0, len(x) - n + 1, hop)
    return np.stack([x[i:i + n] for i in idx]), idx


def db(v, eps=1e-12):
    return 20 * np.log10(np.maximum(v, eps))


def autocorr_f0(fr, fs=FS, fmin=60, fmax=400):
    w = fr * np.hanning(fr.shape[1])
    w = w - w.mean(axis=1, keepdims=True)
    n = fr.shape[1]
    F = np.fft.rfft(w, 2 * n, axis=1)
    ac = np.fft.irfft(np.abs(F) ** 2, axis=1)[:, :n]
    ac0 = np.maximum(ac[:, :1], 1e-12)
    acn = ac / ac0
    lo, hi = int(fs / fmax), min(int(fs / fmin), n - 1)
    seg = acn[:, lo:hi + 1]
    k = np.argmax(seg, axis=1)
    per = seg[np.arange(len(k)), k]
    f0 = fs / (k + lo)
    return f0, per


def lpc_formants(x, order=14, fs=FS):
    if len(x) < order * 3:
        return np.nan, np.nan
    x = x * np.hanning(len(x))
    x = sig.lfilter([1, -0.97], [1], x)
    r = np.correlate(x, x, 'full')[len(x) - 1:len(x) - 1 + order + 1]
    if r[0] <= 0 or len(r) < order + 1:
        return np.nan, np.nan
    r = r.copy()
    r[0] *= 1.0001
    try:
        a = np.linalg.solve(toeplitz(r[:order]), r[1:order + 1])
    except Exception:
        return np.nan, np.nan
    A = np.concatenate([[1.0], -a])
    rts = np.roots(A)
    rts = rts[np.imag(rts) > 0.01]
    if len(rts) == 0:
        return np.nan, np.nan
    f = np.sort(np.angle(rts) * fs / (2 * np.pi))
    f = f[(f > 150) & (f < 5000)]
    f1 = float(f[0]) if len(f) > 0 else np.nan
    f2 = float(f[1]) if len(f) > 1 else np.nan
    return f1, f2


def rise(sub):
    s, _ = frames(sub, n=160, hop=40)
    ee = db(np.sqrt((s ** 2).mean(axis=1)))
    if len(ee) < 5:
        return 0.0, 0.0
    d = ee[2:] - ee[:-2]
    return float(d.max()), float(np.argmax(d) * 40 / FS)


def feats(x):
    f = {}
    fr, idx = frames(x)
    e = np.sqrt((fr ** 2).mean(axis=1))
    edb = db(e)
    peak = edb.max()
    f['dur_total'] = len(x) / FS
    act = edb > (peak - 35)
    f['dur_active'] = float(act.sum() * 160 / FS)
    f['rms_db'] = float(db(np.sqrt((x ** 2).mean())))
    f['peak_db'] = float(db(np.abs(x).max()))
    q10 = float(np.percentile(edb, 10))
    f['noisefloor_rel_db'] = float(peak - q10)
    f['snr_db'] = float(db(e[act].mean() if act.any() else 1e-9) - q10)
    f['crest_db'] = f['peak_db'] - f['rms_db']
    br, bt = rise(x)
    f['burst_rise_db'] = br
    f['burst_time_s'] = bt
    b, a = sig.butter(4, [2000 / (FS / 2), 7500 / (FS / 2)], 'bandpass')
    xh = sig.lfilter(b, a, x)
    brh, bth = rise(xh)
    f['burst_rise_hf_db'] = brh
    f['burst_hf_time_s'] = bth
    n60 = int(0.06 * FS)
    head, headh = x[:n60], xh[:n60]
    f['head_hf_ratio_db'] = float(db(np.sqrt((headh ** 2).mean())) - db(np.sqrt((head ** 2).mean())))
    f0, per = autocorr_f0(fr)
    v = (per > 0.45) & act
    f['voiced_frac'] = float(v.mean())
    if v.sum() >= 3:
        fv = f0[v]
        f['f0_med'] = float(np.median(fv))
        f['f0_range_st'] = float(12 * np.log2(np.percentile(fv, 90) / max(np.percentile(fv, 10), 1e-6)))
        f['f0_iqr_st'] = float(12 * np.log2(np.percentile(fv, 75) / max(np.percentile(fv, 25), 1e-6)))
        t = np.arange(len(fv))
        f['f0_slope_st_s'] = float(np.polyfit(t, 12 * np.log2(np.maximum(fv, 1e-6)), 1)[0] * (FS / 160))
        f['f0_jitter'] = float(np.mean(np.abs(np.diff(fv)) / np.maximum(fv[:-1], 1e-6))) if len(fv) > 1 else np.nan
    else:
        for k in ['f0_med', 'f0_range_st', 'f0_iqr_st', 'f0_slope_st_s', 'f0_jitter']:
            f[k] = np.nan
    pm = float(per[act].mean()) if act.any() else np.nan
    f['periodicity'] = pm
    f['hnr_db'] = float(db(max(pm, 1e-6)) - db(max(1 - pm, 1e-6))) if pm == pm else np.nan
    Fr = np.abs(np.fft.rfft(fr * np.hanning(fr.shape[1]), axis=1))
    fq = np.fft.rfftfreq(fr.shape[1], 1 / FS)
    S = Fr[act].mean(axis=0) if act.any() else Fr.mean(axis=0)
    m = fq > 80
    f['tilt_db_oct'] = float(np.polyfit(np.log2(fq[m]), db(S[m]), 1)[0])
    f['centroid_hz'] = float((fq * S).sum() / max(S.sum(), 1e-12))
    lo_e = S[(fq >= 100) & (fq < 1000)].sum()
    hi_e = S[(fq >= 2000) & (fq < 8000)].sum()
    f['hf_lf_db'] = float(db(hi_e) - db(lo_e))
    Sn = Fr / np.maximum(Fr.sum(axis=1, keepdims=True), 1e-12)
    f['spec_flux'] = float(np.abs(np.diff(Sn[act], axis=0)).sum(axis=1).mean()) if act.sum() > 2 else np.nan
    ai = np.where(act)[0]
    if len(ai) >= 6:
        s0, s1 = ai[0] * 160, min(ai[-1] * 160 + 400, len(x))
        seg = x[s0:s1]
        third = max(len(seg) // 3, 200)
        F1a, F2a = lpc_formants(seg[:third])
        F1b, F2b = lpc_formants(seg[-third:])
        F1m, F2m = lpc_formants(seg[third:2 * third] if len(seg) >= 2 * third else seg)
        f['f1_med'] = F1m
        f['f2_med'] = F2m
        f['f2_f1'] = (F2m - F1m) if (F2m == F2m and F1m == F1m) else np.nan
        f['f2_traj_hz'] = abs(F2b - F2a) if (F2a == F2a and F2b == F2b) else np.nan
        f['f1_traj_hz'] = abs(F1b - F1a) if (F1a == F1a and F1b == F1b) else np.nan
    else:
        for k in ['f1_med', 'f2_med', 'f2_f1', 'f2_traj_hz', 'f1_traj_hz']:
            f[k] = np.nan
    vi = np.where(v)[0]
    if len(vi):
        f['vot_ms'] = float((vi[0] * 160 / FS - bth) * 1000)
        f['voice_onset_s'] = float(vi[0] * 160 / FS)
    else:
        f['vot_ms'] = np.nan
        f['voice_onset_s'] = np.nan
    env = e - e.mean()
    if len(env) >= 8:
        E = np.abs(np.fft.rfft(env * np.hanning(len(env))))
        mf = np.fft.rfftfreq(len(env), 160 / FS)
        band = (mf >= 2) & (mf <= 16)
        f['mod_ratio'] = float(E[band].sum() / max(E[mf > 0].sum(), 1e-12))
    else:
        f['mod_ratio'] = np.nan
    if act.any():
        f['attack_s'] = float(np.argmax(edb > peak - 10) * 160 / FS)
        f['decay_s'] = float(f['dur_total'] - (len(edb) - 1 - int(np.argmax(edb[::-1] > peak - 10))) * 160 / FS)
    else:
        f['attack_s'] = np.nan
        f['decay_s'] = np.nan
    return f


def main():
    rows = [json.loads(l) for l in open(LAB, encoding='utf-8')]
    perclip = {d['id']: d for d in json.load(open(PERCLIP, encoding='utf-8'))}
    out = []
    for r in rows:
        p = r['path']
        if not p or not os.path.exists(p):
            print('SKIP missing', r['id'], file=sys.stderr)
            continue
        x, h = load(p)
        d = dict(id=r['id'], source=r['source'], unit=unit_of(r), date=r['date'],
                 y=r['iddo_human'], raw=r['iddo_raw'], truth=r['truth'],
                 wdist=r.get('wdist'), sha=h, arm=r.get('arm'),
                 orig=os.path.basename(r.get('path_original') or r.get('path_claimed') or ''),
                 note=r.get('note', ''))
        pc = perclip.get(r['id'])
        if pc:
            d['p_judge'] = pc.get('p_judge-v1')
            d['how_judge'] = pc.get('how_judge-v1')
            d['p_judge_iddoonly'] = pc.get('p_judge-v1-iddoonly')
        d.update(feats(x))
        out.append(d)

    def enc(o):
        if isinstance(o, float) and o != o:
            return None
        return float(o)
    json.dump(out, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1, default=enc)
    print('wrote', OUT, len(out))


if __name__ == '__main__':
    main()
