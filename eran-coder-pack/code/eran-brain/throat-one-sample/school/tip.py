#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tip.py -- the tongue-tip school: da ta na la sa za tza sha ra  (claude-cli-PEH-TIP, 2026-09-02)

Iddo's order: "תפעיל אתה את הפה ותוציא איתו הברות את כולן". I operate the mouth
from MOUTH-MANUAL.md / gesture-table.json, render on eran2 (C backend), MEASURE the
acoustic signature with numpy, and only a render that meets its own row is saved as
ERAN-<syl>.wav.  Nothing is played anywhere.

usage:  python3 tip.py <syl> [json-overrides] [--save]
        python3 tip.py da '{"c_pos":0.95,"gain":6}' --save
Self-contained: stdlib + numpy + mouth2.
"""
import json, os, sys, wave
import numpy as np
sys.path.insert(0, os.path.expanduser("~/mouth-v2"))
import mouth2

SR = 16000
BK = "c"
F0 = 105.0
AH = [-0.6013, -0.0092, -0.6310, -1.4002, 1.6041, -1.8558, 1.8504, 1.9330]
HERE = os.path.dirname(os.path.abspath(__file__))
KF = mouth2.keyframe
V = KF(AH)                                  # THE vowel keyframe (manual §1.1)

# ------------------------------------------------------------------ gestures
# Every parameter here is a decision from the manual's ranges; iterations edit these.
DEFAULT = {
    "da":  dict(kind="stop_v", c_pos=0.95, c_area=0.0, d_close=0.08, d_tr=0.015, d_vow=0.35, gain=6.0, tau=0.003),
    # ta: the tip stays narrow (0.8 cm2) through the VOT gap so the aspiration carries the F3-high
    # transition (2851 Hz); a 30 ms bridge segment makes voicing start 10 ms after the gap, not 60.
    "ta":  dict(kind="stop_u", c_pos=0.95, c_area=0.0, d_close=0.08, d_tr=0.015, d_gap=0.04, gap_c_pos=0.95, gap_c_area=0.8,
                d_bridge=0.03, d_vow=0.35, gain=6.0, tau=0.003),
    "na":  dict(kind="nasal",  c_pos=0.93, c_area=0.0, velum=0.75, d_close=0.15, d_tr=0.02, d_vow=0.35),
    "la":  dict(kind="approx", c_pos=0.88, c_area=0.40, velum=0.0, d_close=0.09, d_tr=0.02, d_vow=0.35),
    "sa":  dict(kind="fric",   c_pos=0.92, c_area=0.12, voicing=0.0, tenseness=0.6, d_close=0.12, d_tr=0.015, d_vow=0.35),
    "za":  dict(kind="fric",   c_pos=0.92, c_area=0.12, voicing=0.3, tenseness=0.25, d_close=0.12, d_tr=0.015, d_vow=0.35),
    "sha": dict(kind="fric",   c_pos=0.80, c_area=0.18, voicing=0.0, tenseness=0.6, d_close=0.12, d_tr=0.015, d_vow=0.35),
    "tza": dict(kind="affr",   c_pos=0.95, c_area=0.0, c_pos2=0.90, c_area2=0.12, d_close=0.06, d_tr=0.01, d_fric=0.08, d_vow=0.30, gain=6.0, tau=0.003),
    "ra":  dict(kind="tap",    c_pos=0.94, c_area=0.0, d_pre=0.08, d_tap=0.03, d_vow=0.35, glide=0.5),
}


def build(syl, P):
    """gesture dict + the measurement windows (seconds) it implies."""
    f0k = [F0, F0, F0 * 0.93]
    tenk = [0.6, 0.6, 0.55]
    k = P["kind"]
    if k in ("stop_v", "nasal", "approx", "fric"):
        kf_c = KF(AH, P["c_pos"], P["c_area"], P.get("velum", 0.0), P.get("tenseness", 0.6), P.get("voicing", 1.0))
        kfs, durs = [kf_c, kf_c, V], [P["d_close"], P["d_tr"], P["d_vow"]]
        if P.get("d_bridge"):          # fast release: the glide of a short V segment
            kfs, durs = [kf_c, kf_c, V, V], [P["d_close"], P["d_tr"], P["d_bridge"], P["d_vow"]]
        win = dict(cons=(0.01, P["d_close"] - 0.005), t_rel=P["d_close"] + P["d_tr"])
    elif k == "stop_u":
        kf_c = KF(AH, P["c_pos"], P["c_area"], 0.0, 0.6, 1.0)
        kf_gap = KF(AH, P.get("gap_c_pos", 0.65), P.get("gap_c_area", 2.0), 0.0, 0.6, 0.0)
        kfs, durs = [kf_c, kf_c, kf_gap, V], [P["d_close"], P["d_tr"], P["d_gap"], P["d_vow"]]
        if P.get("d_bridge"):          # fast voicing onset after the gap
            kfs, durs = [kf_c, kf_c, kf_gap, V, V], [P["d_close"], P["d_tr"], P["d_gap"], P["d_bridge"], P["d_vow"]]
        t_rel = P["d_close"] + P["d_tr"]
        win = dict(cons=(0.01, P["d_close"] - 0.005), t_rel=t_rel, gap=(t_rel + 0.015, t_rel + P["d_gap"]),
                   t_onset=t_rel + P["d_gap"])
    elif k == "affr":
        kf_t = KF(AH, P["c_pos"], P["c_area"], 0.0, 0.6, 1.0)
        kf_s = KF(AH, P["c_pos2"], P["c_area2"], 0.0, 0.6, 0.0)
        kfs, durs = [kf_t, kf_t, kf_s, V], [P["d_close"], P["d_tr"], P["d_fric"], P["d_vow"]]
        t_f = P["d_close"] + P["d_tr"]
        win = dict(cons=(0.01, P["d_close"] - 0.005), t_rel=t_f, fric=(t_f + 0.35 * P["d_fric"], t_f + P["d_fric"]),
                   t_vow=t_f + P["d_fric"])
    elif k == "tap":
        kf_r = KF(AH, P["c_pos"], P["c_area"], 0.0, 0.6, 1.0)
        kfs, durs = [V, kf_r, V], [P["d_pre"], P["d_tap"], P["d_vow"]]
        win = dict(pre=(0.02, P["d_pre"] - 0.005), cons=(P["d_pre"], P["d_pre"] + P["d_tap"]), t_rel=P["d_pre"] + P["d_tap"])
    else:
        raise ValueError(k)
    g = {"keyframes": kfs, "durations": durs, "f0_knots": f0k, "tenseness_knots": tenk, "glide": P.get("glide", 0.35)}
    if "gain" in P:
        g["burst"] = {"gain": float(P["gain"]), "tau_s": float(P.get("tau", 0.003))}
    T = sum(durs)
    win["vowel"] = (T - 0.15, T - 0.02)
    return g, win


# --------------------------------------------------------------- measurement
def seg(y, a, b):
    return np.asarray(y[int(a * SR):int(b * SR)], float)

def rms(y):
    return float(np.sqrt(np.mean(np.asarray(y, float) ** 2))) if len(y) else 0.0

def db(a, b):
    return float(20 * np.log10(max(a, 1e-12) / max(b, 1e-12)))

def psd(y, nper=1024):
    """Welch PSD, numpy only (Hann, 50 % overlap)."""
    y = np.asarray(y, float); y = y - y.mean()
    nper = min(nper, len(y)); hop = nper // 2
    w = np.hanning(nper); acc = np.zeros(nper // 2 + 1); n = 0
    for i in range(0, len(y) - nper + 1, max(1, hop)):
        acc += np.abs(np.fft.rfft(y[i:i + nper] * w)) ** 2; n += 1
    if n == 0:
        acc = np.abs(np.fft.rfft(np.pad(y, (0, nper - len(y))) * w)) ** 2; n = 1
    return np.fft.rfftfreq(nper, 1.0 / SR), acc / n

def centroid(y, fmin=200):
    f, p = psd(y); m = f >= fmin
    return float(np.sum(f[m] * p[m]) / (np.sum(p[m]) + 1e-30))

def band_frac(y, lo, hi):
    f, p = psd(y); return float(np.sum(p[(f >= lo) & (f < hi)]) / (np.sum(p) + 1e-30))

def f0_ac(y):
    y = np.asarray(y, float); y = y - y.mean()
    if rms(y) < 1e-5: return 0.0
    ac = np.correlate(y, y, "full")[len(y) - 1:]
    lo, hi = int(SR / 400), int(SR / 70)
    return float(SR / (lo + np.argmax(ac[lo:hi])))

def hnr(y):
    y = np.asarray(y, float); y = y - y.mean()
    if rms(y) < 1e-5: return -99.0
    ac = np.correlate(y, y, "full")[len(y) - 1:]; ac = ac / ac[0]
    lo, hi = int(SR / 400), int(SR / 70)
    r = float(np.max(ac[lo:hi])); r = min(max(r, 1e-6), 0.999999)
    return float(10 * np.log10(r / (1 - r)))

def env(y, w):
    n = int(w * SR)
    return np.array([rms(y[i:i + n]) for i in range(0, len(y) - n + 1, n)])

def formants(y, n=3):
    """LPC formants -- same recipe as train_one.py / probe_manual.py."""
    x = np.asarray(y, float); x = x - x.mean()
    if x.std() < 1e-9 or len(x) < 64: return [0.0] * n
    x = x * np.hamming(len(x)); x = np.append(x[0], x[1:] - 0.97 * x[:-1])
    p = int(2 + SR / 1000)
    r = np.correlate(x, x, "full")[len(x) - 1:len(x) + p]
    if r[0] <= 0: return [0.0] * n
    a = np.zeros(p + 1); a[0], e = 1.0, r[0]
    for i in range(1, p + 1):
        k = -r[1] / e if i == 1 else -(r[i] + np.dot(a[1:i], r[i - 1:0:-1])) / e
        na = a.copy()
        for j in range(1, i): na[j] = a[j] + k * a[i - j]
        na[i] = k; a = na; e *= (1 - k * k)
        if e <= 0: break
    rts = [z for z in np.roots(a) if np.imag(z) > 0]
    fs = sorted(np.arctan2(np.imag(z), np.real(z)) * SR / (2 * np.pi) for z in rts)
    fs = [int(round(f)) for f in fs if 90 < f < 5000]
    return (fs + [0] * n)[:n]

def antiformant(y, lo=1400, hi=3200):
    """deepest notch of the smoothed PSD between lo and hi (nasal zero)."""
    f, p = psd(y, 512); d = 10 * np.log10(p + 1e-30)
    d = np.convolve(d, np.ones(3) / 3, mode="same"); m = (f >= lo) & (f <= hi)
    return float(f[m][np.argmin(d[m])])

def measure(y, lip, nose, win, P):
    vow = seg(y, *win["vowel"]); v_rms = rms(vow)
    M = {"vowel_F": formants(vow[:800]), "vowel_f0": round(f0_ac(vow), 1), "vowel_hnr": round(hnr(vow), 1)}
    c = seg(y, *win["cons"])
    M["cons_ms"] = int(1000 * (win["cons"][1] - win["cons"][0]))
    M["cons_level_db"] = round(db(rms(c), v_rms), 1)
    M["cons_centroid"] = int(centroid(c)) if rms(c) > 1e-6 else 0
    M["cons_hnr"] = round(hnr(c), 1); M["cons_f0"] = round(f0_ac(c), 1)
    M["cons_lt500"] = round(band_frac(c, 0, 500), 3)
    M["cons_gt2k"] = round(band_frac(c, 2000, 8000), 3)
    M["cons_2k4k"] = round(band_frac(c, 2000, 4000), 3)
    M["cons_gt4k"] = round(band_frac(c, 4000, 8000), 3)
    M["cons_F"] = formants(c[:800]) if rms(c) > 1e-4 else [0, 0, 0]
    # 20 ms energy envelope over the whole utterance (dB re vowel)
    e20 = env(y, 0.020); M["env20_db"] = [round(db(v, v_rms)) for v in e20]
    # burst: 5 ms envelope, biggest jump within 20 ms around the release
    e5 = env(y, 0.005); e5db = 20 * np.log10(e5 / max(v_rms, 1e-12) + 1e-12)
    i0 = max(4, int((win["t_rel"] - 0.03) / 0.005)); i1 = min(len(e5db), int((win["t_rel"] + 0.15) / 0.005))
    jumps = [(float(e5db[i] - e5db[i - 4:i].min()), i) for i in range(i0, i1)]
    jmax, ji = max(jumps) if jumps else (0.0, 0)
    M["burst_jump_db"] = round(jmax, 1); M["burst_t_ms"] = int(ji * 5)
    M["burst_peak_re_vowel_db"] = round(float(e5db[i0:i1].max()) if i1 > i0 else -99, 1)
    ib = ji; bseg = y[max(0, ib * 80 - 80):ib * 80 + 240]
    M["burst_centroid"] = int(centroid(bseg)) if rms(bseg) > 1e-6 else 0
    # min level (closure/dip) around the consonant in 5 ms frames
    ic0, ic1 = int(win["cons"][0] / 0.005), max(int(win["cons"][0] / 0.005) + 1, int(win["cons"][1] / 0.005))
    M["cons_min5ms_db"] = round(float(e5db[ic0:ic1].min()), 1)
    M["cons_ms_below_m10"] = int(5 * np.sum(e5db[ic0:ic1] < -10))
    # formant trajectory after release: 25 ms LPC windows every 10 ms
    tr = []
    for k in range(0, 11):
        t = win["t_rel"] + 0.01 * k
        s = seg(y, t, t + 0.025)
        tr.append([int(t * 1000)] + (formants(s) if rms(s) > 1e-4 else [0, 0, 0]))
    M["F_traj"] = tr
    if "gap" in win:
        gp = seg(y, *win["gap"]); M["gap_level_db"] = round(db(rms(gp), v_rms), 1); M["gap_hnr"] = round(hnr(gp), 1)
        # voiced onset after the gap: first 25 ms window (stepping 10 ms) with hnr > 3, up to +120 ms
        for k in range(0, 12):
            t = win["t_onset"] + 0.01 * k; s_ = seg(y, t, t + 0.025)
            if hnr(s_) > 1:
                M["onset_F"] = formants(s_); M["onset_t_ms"] = int(t * 1000); M["onset_hnr"] = round(hnr(s_), 1); break
        else:
            M["onset_F"] = [0, 0, 0]; M["onset_t_ms"] = -1
    if "fric" in win:
        fr = seg(y, *win["fric"]); M["fric_level_db"] = round(db(rms(fr), v_rms), 1)
        M["fric_centroid"] = int(centroid(fr)); M["fric_gt4k"] = round(band_frac(fr, 4000, 8000), 3)
        M["fric_hnr"] = round(hnr(fr), 1); M["fric_ms"] = int(1000 * (win["fric"][1] - win["fric"][0]))
    if "pre" in win:
        pr = seg(y, *win["pre"]); M["pre_level_db"] = round(db(rms(pr), v_rms), 1); M["pre_hnr"] = round(hnr(pr), 1)
    if lip is not None:
        ln = seg(lip, *win["cons"]); nn = seg(nose, *win["cons"])
        M["nose_re_lip_db"] = round(db(rms(nn), rms(ln)), 1)
        M["antiformant"] = int(antiformant(c))
    return M


# ------------------------------------------------------------------ verdicts
def verdict(syl, M, P):
    ok, why = True, []
    def need(cond, txt):
        nonlocal ok
        if not cond: ok = False; why.append("FAIL " + txt)
        else: why.append("ok   " + txt)
    k = P["kind"]
    on = M["F_traj"][2][1:]            # window at release+20 ms (manual: onset = 15-60 ms after release)
    if "onset_F" in M: on = M["onset_F"]
    if syl == "da":
        need(M["cons_level_db"] <= -16, "closure %.1f dB <= -16" % M["cons_level_db"])
        need(M["burst_jump_db"] > 15, "burst jump %.1f dB > 15 within 20 ms" % M["burst_jump_db"])
        need(M["cons_f0"] > 70 and M["cons_hnr"] > 0, "voiced closure f0 %.0f hnr %.1f" % (M["cons_f0"], M["cons_hnr"]))
        need(on[2] >= 2780, "F3 onset %d high (>=2780) -> %d" % (on[2], M["vowel_F"][2]))
        need(on[0] < M["vowel_F"][0], "F1 onset %d rising -> %d" % (on[0], M["vowel_F"][0]))
    elif syl == "ta":
        need(M["cons_level_db"] <= -16, "closure %.1f dB <= -16" % M["cons_level_db"])
        need(M["burst_jump_db"] > 15, "burst jump %.1f dB > 15" % M["burst_jump_db"])
        need(M["burst_peak_re_vowel_db"] >= 5, "burst peak %.1f dB re vowel >= +5" % M["burst_peak_re_vowel_db"])
        need(-8 <= M["gap_level_db"] <= 0 and M["gap_hnr"] < 3, "VOT gap %d ms at %.1f dB (-8..0) hnr %.1f < 3" % (int(1000 * P["d_gap"]), M["gap_level_db"], M["gap_hnr"]))
        f3max = max(r[3] for r in M["F_traj"][1:5])     # aspirated transition, +10..+40 ms after release
        need(f3max >= 2780, "F3 high (%d >= 2780) in the aspirated transition +10..+40 ms; F3 at voicing onset %d (t %d ms)" % (f3max, on[2], M.get("onset_t_ms", -1)))
        need(0 <= M.get("onset_t_ms", -1) - int(1000 * (P["d_close"] + P["d_tr"] + P["d_gap"])) <= 40, "voicing starts within 40 ms after the gap (at %d ms)" % M.get("onset_t_ms", -1))
    elif syl == "na":
        need(M["cons_lt500"] >= 0.95, "murmur <500 Hz %.3f >= 0.95" % M["cons_lt500"])
        need(M["nose_re_lip_db"] >= 20, "nose/lip %.1f dB >= +20" % M["nose_re_lip_db"])
        need(1900 <= M["antiformant"] <= 2600, "antiformant %d in 1.9-2.6 kHz" % M["antiformant"])
        need(M["burst_jump_db"] < 15, "no burst (jump %.1f < 15)" % M["burst_jump_db"])
        need(M["cons_hnr"] > 3 and M["cons_f0"] > 70, "murmur voiced hnr %.1f f0 %.0f" % (M["cons_hnr"], M["cons_f0"]))
        need(-8 <= M["cons_level_db"] <= 2, "murmur level %.1f dB (-8..+2)" % M["cons_level_db"])
    elif syl == "la":
        need(abs(M["cons_level_db"]) <= 2.5, "level %.1f within 2.5 dB of vowel" % M["cons_level_db"])
        need(0 < M["cons_F"][0] <= 470, "F1 %d <= 470 during l (vowel %d)" % (M["cons_F"][0], M["vowel_F"][0]))
        need(M["burst_jump_db"] < 15, "no burst (jump %.1f)" % M["burst_jump_db"])
        need(M["cons_min5ms_db"] > -6, "no closure (min %.1f dB > -6)" % M["cons_min5ms_db"])
        need(M["cons_hnr"] > 3, "voiced hnr %.1f > 3" % M["cons_hnr"])
    elif syl == "sa":
        need(M["cons_ms"] >= 80, "noise %d ms >= 80" % M["cons_ms"])
        need(M["cons_centroid"] >= 4300, "centroid %d >= 4300" % M["cons_centroid"])
        need(M["cons_gt4k"] >= 0.5, ">4k frac %.2f >= 0.5" % M["cons_gt4k"])
        need(M["cons_hnr"] < 0, "hnr %.1f < 0" % M["cons_hnr"])
        need(-18 <= M["cons_level_db"] <= -10, "level %.1f (-18..-10)" % M["cons_level_db"])
        need(M["burst_jump_db"] < 15, "no burst (jump %.1f)" % M["burst_jump_db"])
    elif syl == "sha":
        need(M["cons_ms"] >= 80, "noise %d ms >= 80" % M["cons_ms"])
        need(3300 <= M["cons_centroid"] <= 3900, "centroid %d in 3300-3900" % M["cons_centroid"])
        need(M["cons_2k4k"] >= 0.65, "2-4k frac %.2f >= 0.65" % M["cons_2k4k"])
        need(M["cons_gt4k"] <= 0.3, ">4k frac %.2f <= 0.3" % M["cons_gt4k"])
        need(M["cons_hnr"] < 0, "hnr %.1f < 0" % M["cons_hnr"])
        need(-12 <= M["cons_level_db"] <= -4, "level %.1f (-12..-4)" % M["cons_level_db"])
    elif syl == "za":
        need(85 <= M["cons_f0"] <= 130 and 1.5 <= M["cons_hnr"] <= 7, "voiced f0 %.0f hnr %.1f (1.5-7)" % (M["cons_f0"], M["cons_hnr"]))
        need(M["cons_gt2k"] >= 0.15, ">2k frac %.2f >= 0.15" % M["cons_gt2k"])
        need(2300 <= M["cons_centroid"] <= 4000, "centroid %d ~3 kHz" % M["cons_centroid"])
        need(-12 <= M["cons_level_db"] <= -4, "level %.1f (-12..-4)" % M["cons_level_db"])
        need(M["burst_jump_db"] < 15, "no burst (jump %.1f)" % M["burst_jump_db"])
    elif syl == "tza":
        need(M["cons_level_db"] <= -18, "closure %.1f <= -18 for %d ms" % (M["cons_level_db"], M["cons_ms"]))
        need(60 <= M["fric_ms"] + int(1000 * 0.35 * P["d_fric"]) <= 90, "fricative %d ms (60-90)" % (M["fric_ms"] + int(1000 * 0.35 * P["d_fric"])))
        need(-11 <= M["fric_level_db"] <= -3, "fric level %.1f (-11..-3)" % M["fric_level_db"])
        need(M["fric_centroid"] >= 3500, "fric centroid %d >= 3500" % M["fric_centroid"])
        need(M["fric_gt4k"] >= 0.4, "fric >4k %.2f >= 0.4" % M["fric_gt4k"])
        need(M["fric_hnr"] < 0, "fric hnr %.1f < 0" % M["fric_hnr"])
    elif syl == "ra":
        need(M["cons_min5ms_db"] <= -10, "tap dip %.1f dB <= -10" % M["cons_min5ms_db"])
        need(M["cons_ms_below_m10"] <= 35, "dip lasts %d ms (<= 35)" % M["cons_ms_below_m10"])
        need(M["pre_hnr"] > 3 and M["vowel_hnr"] > 3, "voicing continuous around (hnr %.1f / %.1f)" % (M["pre_hnr"], M["vowel_hnr"]))
        need(M["burst_peak_re_vowel_db"] <= 4, "no burst pop (release peak %.1f dB re vowel <= +4; jump %.1f)" % (M["burst_peak_re_vowel_db"], M["burst_jump_db"]))
        need(M["cons_gt2k"] < 0.3, "no noise band >2k (%.2f)" % M["cons_gt2k"])
    return ok, why


def write_wav(path, y):
    w = wave.open(path, "wb"); w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((np.clip(y, -1, 1) * 32767).astype(np.int16).tobytes()); w.close()


def main():
    syl = sys.argv[1]
    P = dict(DEFAULT[syl])
    save = "--save" in sys.argv
    for a in sys.argv[2:]:
        if a.startswith("{"): P.update(json.loads(a))
    g, win = build(syl, P)
    y = mouth2.say_gesture(g, seed=0, backend=BK)
    lip, nose = mouth2.say_gesture(g, seed=0, backend=BK, return_ports=True)
    M = measure(y, lip, nose, win, P)
    ok, why = verdict(syl, M, P)
    out = {"syl": syl, "params": P, "ok": ok, "why": why, "measured": M}
    print(json.dumps(out, default=float))
    log = os.path.join(HERE, syl + ".attempts.jsonl")
    with open(log, "a") as f: f.write(json.dumps(out, default=float) + "\n")
    if save:
        write_wav(os.path.join(HERE, "ERAN-%s.wav" % syl), y)
        gj = {"syl": syl, "speaker": "ERAN", "backend": BK, "seed": 0, "sr": SR, "params": P,
              "gesture": {"keyframes": [[round(float(v), 4) for v in k] for k in g["keyframes"]],
                          "durations": g["durations"], "f0_knots": g["f0_knots"],
                          "tenseness_knots": g["tenseness_knots"], "glide": g["glide"], "burst": g.get("burst")},
              "keyframe_dims": "k1..k8 log2-area, c_pos, c_area, velum, tenseness, voicing",
              "signature_ok": ok, "verdict": why, "measured": M}
        with open(os.path.join(HERE, syl + ".json"), "w") as f: json.dump(gj, f, indent=1, default=float)
        print("SAVED ERAN-%s.wav (%d samples, peak %.3f)" % (syl, len(y), float(np.abs(y).max())))


if __name__ == "__main__":
    main()
