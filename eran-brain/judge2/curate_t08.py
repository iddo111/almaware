#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""curate_t08.py - GROUND B. Measure every candidate human clip honestly.

No training. Pure measurement: duration, level, activity, voicing (pyin f0),
spectral flatness. Writes one JSON per directory to judge2/inventory/.
"""
import sys, os, json, glob, math
import numpy as np, soundfile as sf, librosa

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "inventory")
os.makedirs(OUT, exist_ok=True)

def measure(path):
    x, sr = sf.read(path, dtype="float32", always_2d=False)
    if x.ndim > 1: x = x.mean(axis=1)
    n = len(x)
    d = {"file": os.path.basename(path), "sr": int(sr), "secs": round(n/sr, 4)}
    if n < int(0.01*sr):
        d.update(verdict="TOO_SHORT"); return d
    peak = float(np.max(np.abs(x)))
    rms  = float(np.sqrt(np.mean(x*x)))
    d["peak_dbfs"] = round(20*math.log10(peak+1e-12), 2)
    d["rms_dbfs"]  = round(20*math.log10(rms +1e-12), 2)
    # frame energy -> active fraction relative to the clip's own peak frame
    hop = 128; fl = 512
    if n < fl: x = np.pad(x, (0, fl-n)); n = len(x)
    fe = librosa.feature.rms(y=x, frame_length=fl, hop_length=hop)[0]
    fdb = 20*np.log10(fe+1e-12)
    top = float(np.max(fdb))
    d["active_frac_40"] = round(float(np.mean(fdb > top-40)), 4)
    d["active_frac_20"] = round(float(np.mean(fdb > top-20)), 4)
    d["crest_db"] = round(d["peak_dbfs"] - d["rms_dbfs"], 2)
    # spectral flatness: 1.0 = white noise, low = tonal/voiced
    sfl = librosa.feature.spectral_flatness(y=x, n_fft=fl, hop_length=hop)[0]
    d["flatness_med"] = round(float(np.median(sfl)), 5)
    d["zcr_med"] = round(float(np.median(librosa.feature.zero_crossing_rate(x, frame_length=fl, hop_length=hop)[0])), 4)
    # voicing: pyin over a human speech f0 band
    try:
        f0, vflag, vprob = librosa.pyin(x, fmin=60, fmax=400, sr=sr,
                                        frame_length=fl*2, hop_length=hop)
        vf = float(np.mean(vflag)) if vflag is not None else 0.0
        d["voiced_frac"] = round(vf, 4)
        good = f0[vflag] if vflag is not None and np.any(vflag) else np.array([])
        d["f0_med"] = round(float(np.median(good)), 2) if good.size else None
        d["voiced_secs"] = round(vf * n/sr, 4)
    except Exception as e:
        d["voiced_frac"] = None; d["f0_med"] = None; d["voiced_secs"] = None
        d["pyin_err"] = str(e)[:120]
    return d

def keep_rule(d):
    """Honest keep rule for RESCUED/uncurated material. Reject: silence, room
    tone, too short to hold a syllable, no periodic voicing."""
    if d.get("verdict") == "TOO_SHORT": return False, "shorter than 10 ms"
    if d["secs"] < 0.12:               return False, "under 120 ms - cannot hold a syllable"
    if d["secs"] > 3.0:                return False, "over 3 s - not a syllable take"
    if d["peak_dbfs"] < -45:           return False, "peak under -45 dBFS - silence"
    vf = d.get("voiced_frac")
    if vf is None:                     return False, "pyin failed"
    if vf < 0.15:                      return False, "voiced fraction under 15%% (%.3f) - room/noise, not a voice" % vf
    if d.get("voiced_secs", 0) < 0.06: return False, "under 60 ms of voiced audio"
    if d["flatness_med"] > 0.30:       return False, "spectral flatness %.3f - noise-like" % d["flatness_med"]
    return True, "ok"

def run(tag, files):
    rows = []
    for i, p in enumerate(sorted(files)):
        try:
            d = measure(p)
        except Exception as e:
            d = {"file": os.path.basename(p), "error": str(e)[:160], "verdict": "ERROR"}
        if "error" not in d:
            k, why = keep_rule(d); d["keep"] = k; d["reason"] = why
        else:
            d["keep"] = False; d["reason"] = "unreadable"
        d["path"] = os.path.abspath(p)
        rows.append(d)
        if (i+1) % 25 == 0: print("  %s %d/%d" % (tag, i+1, len(files)), flush=True)
    kept = sum(1 for r in rows if r.get("keep"))
    print("%-10s n=%-4d keep=%-4d (%.1f%%)" % (tag, len(rows), kept, 100.0*kept/max(1,len(rows))))
    with open(os.path.join(OUT, "measure_%s.json" % tag), "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    return rows

if __name__ == "__main__":
    B = r"D:\CLAUDE\eran-brain\booth"
    jobs = [
        ("t08raw", glob.glob(os.path.join(B, "t08-raw", "*.wav"))),
        ("t07",    glob.glob(os.path.join(B, "staged", "t07", "*.wav"))),
        ("t07trash", glob.glob(os.path.join(B, "staged", "t07", "trash", "*.wav"))),
        ("t06",    glob.glob(os.path.join(B, "staged", "t06", "*.wav"))),
    ]
    only = sys.argv[1:] if len(sys.argv) > 1 else None
    for tag, fs in jobs:
        if only and tag not in only: continue
        run(tag, fs)
