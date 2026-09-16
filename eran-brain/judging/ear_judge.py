#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ear_judge.py -- learn Iddo's EAR from his own verdicts.

Born 2026-08-27 06:35 JDT out of one measurement: the search's own objective,
wdist, barely tracks the only judge that matters. Across his 105 verdicts the
mean wdist of a thumbs-up (4.883) and a thumbs-down (5.167) differ by 0.28, and
the lowest-wdist candidate ever produced (ma, 4.155) was rejected outright.
All 292 queued candidates pass all gates, so the gates separate nothing either.

So: features from the WAV -- what his ear actually meets -- not from the organ
parameter vector (whose dimension differs per arm and is unhearable anyway).

HONESTY, non-negotiable (scar: project_eran_session_leak_scar):
  the station re-flags the SAME arm's improving best every 10 minutes, so two
  rows from one arm are near-duplicates. A random split leaks them across
  train/test and reports a fantasy. Scoring here is LEAVE-ONE-ARM-OUT, and every
  model is printed next to the wdist-only baseline on the identical folds. If it
  does not beat the baseline, this file says so.

usage:  python ear_judge.py            # train, score honestly, save model
        python ear_judge.py <wav>...   # score new candidates with saved model
"""
import json
import os
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import lfilter, get_window

HERE = Path(__file__).resolve().parent
QUEUE = HERE / "queue"
VERDICTS = HERE / "iddo-verdicts.jsonl"
MODEL = HERE / "ear_judge_model.json"
SR = 16000


# ---------------------------------------------------------------- features
def _frames(x, n=400, hop=160):
    if len(x) < n:
        x = np.pad(x, (0, n - len(x)))
    idx = np.arange(0, len(x) - n + 1, hop)
    return np.stack([x[i:i + n] for i in idx]) * get_window("hann", n)


def _f0_track(fr, sr=SR, lo=60, hi=500):
    """Autocorrelation f0 per frame; 0 where unvoiced."""
    out = []
    lo_lag, hi_lag = int(sr / hi), int(sr / lo)
    for f in fr:
        f = f - f.mean()
        e = np.dot(f, f)
        if e < 1e-9:
            out.append(0.0)
            continue
        ac = np.correlate(f, f, "full")[len(f) - 1:]
        seg = ac[lo_lag:hi_lag]
        if not len(seg):
            out.append(0.0)
            continue
        k = int(np.argmax(seg))
        peak = seg[k] / (ac[0] + 1e-12)
        out.append(sr / (lo_lag + k) if peak > 0.35 else 0.0)
    return np.array(out)


def _lpc_formants(x, sr=SR, order=12, n=2):
    """First n formants via LPC roots. Cheap, adequate for vowel identity."""
    x = x - x.mean()
    if np.dot(x, x) < 1e-9:
        return [0.0] * n
    x = lfilter([1, -0.97], 1, x) * get_window("hann", len(x))
    r = np.correlate(x, x, "full")[len(x) - 1:][:order + 1]
    if r[0] <= 0:
        return [0.0] * n
    # Levinson-Durbin
    a = np.zeros(order + 1)
    a[0], err = 1.0, r[0]
    for i in range(1, order + 1):
        acc = r[i] + np.dot(a[1:i], r[i - 1:0:-1]) if i > 1 else r[i]
        k = -acc / err
        a[1:i + 1] = a[1:i + 1] + k * a[i - 1::-1][:i] if i > 1 else np.array([k])
        err *= (1 - k * k)
        if err <= 0:
            break
    rt = np.roots(a)
    rt = rt[np.imag(rt) > 0.01]
    f = np.sort(np.angle(rt) * sr / (2 * np.pi))
    f = [v for v in f if 90 < v < sr / 2 - 200]
    return (f + [0.0] * n)[:n]


def features(wav):
    x, sr = sf.read(str(wav))
    if x.ndim > 1:
        x = x.mean(1)
    x = x.astype(np.float64)
    if sr != SR:                      # every candidate is 16k; guard anyway
        k = int(round(len(x) * SR / sr))
        x = np.interp(np.linspace(0, len(x) - 1, k), np.arange(len(x)), x)
    peak = np.abs(x).max()
    if peak > 0:
        x = x / peak
    fr = _frames(x)
    rms = np.sqrt((fr ** 2).mean(1)) + 1e-12
    db = 20 * np.log10(rms)
    live = db > (db.max() - 30)       # the sound, minus its silence
    if live.sum() < 2:
        live = np.ones_like(live, bool)

    S = np.abs(np.fft.rfft(fr, axis=1)) + 1e-12
    fx = np.fft.rfftfreq(fr.shape[1], 1 / SR)
    P = S / S.sum(1, keepdims=True)
    cen = (P * fx).sum(1)
    flat = np.exp(np.log(S).mean(1)) / S.mean(1)      # 1.0 == pure noise
    hi = S[:, fx > 4000].sum(1) / S.sum(1)            # hiss / breath share

    f0 = _f0_track(fr)
    vo = f0[live] > 0

    # --- the /b/ questions: is there a closure, then a burst?
    a = rms[live]
    ai = int(np.argmax(a))
    rise = a[:ai + 1]
    onset = float(np.argmax(rise > 0.5 * a[ai]) * 160 / SR) if ai else 0.0
    lead = a[:max(ai, 1)]
    closure_db = float(20 * np.log10(lead.min() / (a[ai] + 1e-12))) if len(lead) else 0.0
    burst = float(np.max(np.diff(db[live])) if live.sum() > 1 else 0.0)

    core = x[np.repeat(live, 160)[:len(x)]] if live.sum() else x
    F1, F2 = _lpc_formants(core[:2048] if len(core) > 2048 else core)

    return {
        "dur_s": len(x) / SR,
        "voiced_frac": float(vo.mean()) if live.sum() else 0.0,
        "f0_mean": float(f0[f0 > 0].mean()) if (f0 > 0).any() else 0.0,
        "f0_std": float(f0[f0 > 0].std()) if (f0 > 0).sum() > 1 else 0.0,
        "centroid": float(cen[live].mean()),
        "flatness": float(flat[live].mean()),
        "hf_share": float(hi[live].mean()),
        "onset_s": onset,
        "closure_db": closure_db,
        "burst_db": burst,
        "dyn_db": float(db[live].max() - db[live].min()),
        "F1": float(F1),
        "F2": float(F2),
    }


FEATS = ["dur_s", "voiced_frac", "f0_mean", "f0_std", "centroid", "flatness",
         "hf_share", "onset_s", "closure_db", "burst_db", "dyn_db", "F1", "F2"]


# ---------------------------------------------------------------- dataset
def dataset():
    rows = []
    for line in open(VERDICTS, encoding="utf-8"):
        if not line.strip():
            continue
        v = json.loads(line)
        wav = QUEUE / v["file"]
        cj = QUEUE / (os.path.splitext(v["file"])[0] + ".json")
        if not wav.exists() or not cj.exists():
            continue
        f = features(wav)
        f["wdist"] = v.get("wdist") or 0.0
        rows.append({"x": f, "y": 1 if v["verdict"] == 1 else 0,
                     "arm": v["arm"], "unit": v.get("unit", "?"),
                     "file": v["file"]})
    return rows
