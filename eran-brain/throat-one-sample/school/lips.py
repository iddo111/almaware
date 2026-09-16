#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""lips.py -- the LIPS family school for ERAN's mouth: ba va ma pa fa wa.

claude-cli-PEH-LIPS, 2026-09-02, on Iddo's order 'תפעיל אתה את הפה ותוציא איתו הברות'.
Self-contained: stdlib + numpy + mouth2 (eran2:~/mouth-v2). Renders on the C backend.
Nothing is played anywhere; every number is measured with numpy on the rendered float32.

For each syllable: build the gesture from gesture-table.json ranges (the /ah/ FIT knots as
the vowel), render, MEASURE the acoustic signature, compare with the table's expected
signature, and if it fails adjust the gesture by an explicit rule that follows from the
failed measurement (not a blind search), up to 6 attempts. Saves ERAN-<syl>.wav + <syl>.json
only for the best attempt; every attempt's wav goes to attempts/ (probes, not deliverables).
"""
import json, os, sys, time, wave, copy
import numpy as np
sys.path.insert(0, os.path.expanduser("~/mouth-v2"))
import mouth2, tract_core as T

SR = 16000
BK = "c"
AH = [-0.6013, -0.0092, -0.6310, -1.4002, 1.6041, -1.8558, 1.8504, 1.9330]
F0 = 105.0
OUT = os.path.expanduser("~/throat-one-sample/school")
ATT = os.path.join(OUT, "attempts")
os.makedirs(ATT, exist_ok=True)
KF = mouth2.keyframe
VOWEL = KF(AH)                      # the table's VOWEL_KF: measured 580/1226/2550 in gesture space
MAX_TRIES = 6
ONLY = sys.argv[1:]                 # optional subset

# ------------------------------------------------------------------ measurement
def wav_write(path, y):
    w = wave.open(path, "wb"); w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((np.clip(np.asarray(y, float), -1, 1) * 32767).astype(np.int16).tobytes()); w.close()

def rms(y):
    y = np.asarray(y, float)
    return float(np.sqrt(np.mean(y ** 2))) if len(y) else 0.0

def db(a, b):
    return float(20 * np.log10(max(a, 1e-12) / max(b, 1e-12)))

def psd(y, nper=512):
    """Welch PSD, numpy only (hann, 50 % overlap)."""
    y = np.asarray(y, float); y = y - y.mean()
    nper = int(min(nper, len(y)))
    if nper < 32:
        f = np.fft.rfftfreq(64, 1 / SR); return f, np.zeros_like(f)
    win = np.hanning(nper); hop = nper // 2
    acc = None; n = 0
    for i in range(0, len(y) - nper + 1, hop):
        seg = y[i:i + nper] * win
        p = np.abs(np.fft.rfft(seg)) ** 2
        acc = p if acc is None else acc + p; n += 1
    f = np.fft.rfftfreq(nper, 1 / SR)
    return f, (acc / max(n, 1))

def centroid(y, fmin=200):
    f, p = psd(y); m = f >= fmin
    return float(np.sum(f[m] * p[m]) / (np.sum(p[m]) + 1e-30))

def band_frac(y, lo, hi):
    f, p = psd(y); tot = np.sum(p) + 1e-30
    return float(np.sum(p[(f >= lo) & (f < hi)]) / tot)

def formants(y, n=3):
    """LPC formants (the train_one.py recipe that matched Iddo's F1/F2)."""
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
    fs = [round(f) for f in fs if 90 < f < 5000]
    return (fs + [0.0] * n)[:n]

def f0_ac(y):
    y = np.asarray(y, float); y = y - y.mean()
    if rms(y) < 1e-5: return 0.0
    ac = np.correlate(y, y, "full")[len(y) - 1:]
    lo, hi = int(SR / 400), int(SR / 70)
    return float(SR / (lo + np.argmax(ac[lo:hi])))

def hnr(y):
    """autocorrelation voicing strength (Boersma-style HNR, dB)."""
    y = np.asarray(y, float); y = y - y.mean()
    if rms(y) < 1e-5: return -99.0
    ac = np.correlate(y, y, "full")[len(y) - 1:]; ac = ac / ac[0]
    lo, hi = int(SR / 400), int(SR / 70)
    r = float(np.max(ac[lo:hi])); r = min(max(r, 1e-6), 0.999999)
    return float(10 * np.log10(r / (1 - r)))

def envelope(y, w_s, hop_s=None):
    n = int(w_s * SR); h = int((hop_s or w_s) * SR)
    return np.array([rms(y[i:i + n]) for i in range(0, max(1, len(y) - n), h)]), h

def antiformant(y, lo=1000, hi=3000):
    """deepest dip of the smoothed dB spectrum in [lo, hi] -- reported, not gated."""
    f, p = psd(y, 1024); d = 10 * np.log10(p + 1e-30)
    d = np.convolve(d, np.ones(7) / 7, mode="same")
    m = (f >= lo) & (f <= hi)
    return float(f[m][np.argmin(d[m])])

def seg_bounds(durs):
    """block-exact segment boundaries in seconds, same rounding as say_gesture."""
    total = sum(durs); n_blocks = int(round(total / T.BLOCK_S))
    b0 = 0; out = []
    for d in durs:
        nb = min(max(1, int(round(d / T.BLOCK_S))), n_blocks - b0)
        out.append((b0 * T.BLOCK_S, (b0 + nb) * T.BLOCK_S)); b0 += nb
    return out

def sl(y, t0, t1):
    return y[int(t0 * SR):int(t1 * SR)]

def render(g, ports=False):
    gg = dict(g); gg["keyframes"] = [np.asarray(k, float) for k in g["keyframes"]]
    return mouth2.say_gesture(gg, seed=0, backend=BK, return_ports=ports)

def measure(y, g, kind, ports=None):
    """the common signature dictionary. kind decides where the consonant and release are."""
    durs = g["durations"]; B = seg_bounds(durs)
    n_seg = len(durs)
    iv = n_seg - 1                                    # the vowel is the last segment
    t_vow0, t_vow1 = B[iv]
    steady = sl(y, t_vow0 + 0.15, t_vow1 - 0.03)
    v_rms = rms(steady)
    M = {"vowel": {"rms": v_rms, "formants": formants(steady), "f0": f0_ac(steady), "hnr": hnr(steady)}}
    # consonant portion = segment 0 (+ segment 1 which is the same keyframe)
    t_c0, t_c1 = B[0][0], B[1][1] if n_seg >= 3 else B[0][1]
    # steady part of the consonant: skip the first 20 ms
    cons = sl(y, t_c0 + 0.02, t_c1)
    M["cons"] = {"t": [t_c0, t_c1], "level_db": db(rms(cons), v_rms), "centroid": centroid(cons),
                 "hnr": hnr(cons), "f0": f0_ac(cons), "low500_frac": band_frac(cons, 0, 500),
                 "gt2k_frac": band_frac(cons, 2000, 8000), "gt4k_frac": band_frac(cons, 4000, 8000),
                 "formants": formants(cons), "antiformant_hz": antiformant(cons)}
    # 20 ms envelope in dB re vowel
    e20, h = envelope(y, 0.020, 0.010)
    M["env20_db"] = [round(db(v, v_rms), 1) for v in e20]
    M["env20_hop_s"] = h / SR
    # closure depth: min of the 20 ms envelope inside the consonant, and how long it stays <= -25 / -20
    cidx = [i for i in range(len(e20)) if t_c0 + 0.01 <= i * h / SR <= t_c1 - 0.02]
    if cidx:
        cd = [db(e20[i], v_rms) for i in cidx]
        M["closure_min_db"] = float(min(cd))
        M["closure_ms_le_-25"] = float(sum(1 for v in cd if v <= -25) * h / SR * 1000)
        M["closure_ms_le_-20"] = float(sum(1 for v in cd if v <= -20) * h / SR * 1000)
    # release = start of the segment after the consonant pair (gap or vowel)
    t_rel = B[2][0] if n_seg >= 3 else B[1][0]
    M["t_release"] = t_rel
    # burst: 5 ms rms envelope, peak in [t_rel-5ms, t_rel+40ms] re vowel; jump = max rise over 20 ms (hop 2.5 ms)
    e5, h5 = envelope(y, 0.005, 0.0025)
    i0 = max(0, int((t_rel - 0.005) / (h5 / SR))); i1 = min(len(e5), int((t_rel + 0.015) / (h5 / SR)))
    if i1 > i0:
        seg = e5[i0:i1]; k = int(np.argmax(seg))
        M["burst_peak_db"] = db(seg[k], v_rms)
        M["burst_t_after_release_ms"] = float((i0 + k) * h5 / SR * 1000 - t_rel * 1000)
        pre = e5[max(0, i0 + k - 8):i0 + k - 2]      # 20..5 ms before the peak
        M["burst_jump_db_20ms"] = db(seg[k], max(pre.max() if len(pre) else 1e-12, 1e-12))
        tp = (i0 + k) * h5 / SR
        M["burst_centroid"] = centroid(sl(y, tp - 0.002, tp + 0.010))
    # VOT gap (4-segment gestures): segment 2 level re vowel
    if n_seg >= 4:
        tg0, tg1 = B[2]
        gseg = sl(y, tg0 + 0.4 * (tg1 - tg0), tg1)
        ge, gh = envelope(gseg, 0.005, 0.0025)
        M["gap"] = {"t": [tg0, tg1], "ms": (tg1 - tg0) * 1000, "rms_level_db": db(rms(sl(y, tg0 + 0.008, tg1)), v_rms),
                    "level_db": float(np.median([db(v, v_rms) for v in ge])) if len(ge) else -99.0,
                    "hnr": hnr(gseg), "centroid": centroid(gseg)}
    # formant trajectory across the transition: 25 ms LPC windows after the vowel segment starts
    traj = []
    for off in (0.015, 0.040, 0.070, 0.110, 0.200):
        w = sl(y, t_vow0 + off, t_vow0 + off + 0.025)
        traj.append({"t_ms_after_vowel_start": off * 1000, "F": formants(w)})
    M["traj"] = traj
    if ports is not None:
        lip, nose = ports
        c_l, c_n = sl(lip, t_c0 + 0.02, t_c1), sl(nose, t_c0 + 0.02, t_c1)
        M["cons"]["nose_over_lip_db"] = db(rms(c_n), rms(c_l))
        v_l, v_n = sl(lip, t_vow0 + 0.15, t_vow1 - 0.03), sl(nose, t_vow0 + 0.15, t_vow1 - 0.03)
        M["vowel"]["nose_over_lip_db"] = db(rms(v_n), rms(v_l))
    return M

# ------------------------------------------------------------------ gestures
def kfl(k): return [float(v) for v in np.asarray(k, float)]

def build(syl, P):
    """P = the tunable parameters; returns the gesture (numpy keyframes) + a readable copy."""
    f0k = [F0, F0, 98.0]; tenk = [0.6, 0.6, 0.55]
    if syl == "ba":
        c = KF(AH, c_pos=P["c_pos"], c_area=0.0, velum=0.0, tenseness=0.6, voicing=1.0)
        g = {"keyframes": [c, c, VOWEL], "durations": [P["d_close"], 0.015, 0.35],
             "glide": P["glide"], "burst": {"gain": P["gain"], "tau_s": 0.003}}
    elif syl == "pa":
        c = KF(AH, c_pos=P["c_pos"], c_area=0.0, velum=0.0, tenseness=0.6, voicing=1.0)
        gap = KF(AH, c_pos=P["c_pos"], c_area=P["gap_area"], voicing=0.0) if P["gap_area"] < 2.0 else KF(AH, voicing=0.0)
        g = {"keyframes": [c, c, gap, VOWEL], "durations": [P["d_close"], 0.015, P["d_gap"], 0.35],
             "glide": P["glide"], "burst": {"gain": P["gain"], "tau_s": 0.003}}
    elif syl == "ma":
        c = KF(AH, c_pos=P["c_pos"], c_area=0.0, velum=P["velum"], tenseness=0.6, voicing=1.0)
        g = {"keyframes": [c, c, VOWEL], "durations": [P["d_murmur"], 0.02, 0.35], "glide": P["glide"]}
    elif syl == "va":
        c = KF(AH, c_pos=P["c_pos"], c_area=P["c_area"], velum=0.0, tenseness=P["ten"], voicing=P["voicing"])
        g = {"keyframes": [c, c, VOWEL], "durations": [P["d_noise"], 0.015, 0.35], "glide": P["glide"]}
    elif syl == "fa":
        c = KF(AH, c_pos=P["c_pos"], c_area=P["c_area"], velum=0.0, tenseness=0.6, voicing=0.0)
        g = {"keyframes": [c, c, VOWEL], "durations": [P["d_noise"], 0.015, 0.35], "glide": P["glide"]}
    elif syl == "wa":
        knots = mouth2.vowel_knots("u") if P["knots"] == "u" else AH
        c = KF(knots, c_pos=P["c_pos"], c_area=P["c_area"], velum=0.0, tenseness=0.6, voicing=1.0)
        g = {"keyframes": [c, c, VOWEL], "durations": [P["d_hold"], 0.02, 0.35], "glide": P["glide"]}
    else:
        raise ValueError(syl)
    g["f0_knots"] = f0k; g["tenseness_knots"] = tenk
    readable = {"keyframes": [kfl(k) for k in g["keyframes"]],
                "keyframe_fields": "knots8[0..7], c_pos, c_area, velum, tenseness, voicing",
                "durations": g["durations"], "f0_knots": f0k, "tenseness_knots": tenk,
                "glide": g.get("glide", 0.35), "burst": g.get("burst"), "backend": BK, "seed": 0,
                "params": dict(P), "vowel": "keyframe(AH_FIT) default c_pos 0.65 c_area 2.0"}
    return g, readable

START = {
    "ba": {"c_pos": 0.97, "d_close": 0.09, "gain": 6.0, "glide": 0.35},
    "pa": {"c_pos": 0.97, "d_close": 0.09, "d_gap": 0.04, "gain": 6.0, "glide": 0.35, "gap_area": 2.0},
    "ma": {"c_pos": 0.97, "velum": 0.75, "d_murmur": 0.15, "glide": 0.35},
    "va": {"c_pos": 0.96, "c_area": 0.10, "voicing": 0.13, "ten": 0.25, "d_noise": 0.12, "glide": 0.35},
    "fa": {"c_pos": 0.98, "c_area": 0.15, "d_noise": 0.12, "glide": 0.35},
    "wa": {"knots": "AH", "c_pos": 1.0, "c_area": 0.15, "d_hold": 0.08, "glide": 0.5},
}

EXPECTED = {
    "ba": "closure <= -25 dB re vowel for >= 40 ms; burst >= +3 dB (aim +8 at gain 6) within 10 ms of release, jump > 15 dB in 20 ms, centroid 400-800 Hz; F1 onset < steady F1 (rising), F2 within +-150 of steady",
    "pa": "closure <= -25 dB for >= 40 ms; burst >= +8 dB within 10 ms, jump > 15 dB; VOT gap 30-50 ms whose level after the burst tail is -2..-18 dB re vowel; F1 at voice onset not above steady+80 (the table says rising; measured: the lips open fully inside the voiceless gap, so the F1 transition is not voiced)",
    "ma": "murmur 80-200 ms with >= 95 % power < 500 Hz, nose/lip >= +30 dB, level -6..+2 dB re vowel, HNR >= 3; NO burst (peak < +3 dB, no 15 dB jump); F1 onset < steady",
    "va": "f0 95-120 Hz measurable in the consonant, HNR 1-8 dB; > 2 kHz fraction >= 0.10; level -10..-25 dB re vowel; no closure (no 20 ms frame more than 8 dB below the noise level); no burst (< +3 dB)",
    "fa": "level -18..-32 dB re vowel (table: -25); centroid 1.5-3.5 kHz (table ~2.2 k); HNR < 0 (no voicing); > 2 kHz fraction >= 0.10; no closure (no 20 ms frame more than 8 dB below the noise level), no burst",
    "wa": "continuous voicing (HNR >= 3, level >= -10 dB); onset F1 <= 420 and F2 <= 1050 Hz, F2 rising >= 150 Hz into the vowel over 40-120 ms; no burst (< +3 dB), no noise band (> 2 kHz fraction < 0.05)",
}

def check(syl, M):
    """returns (ok, fails[list of str]) against EXPECTED."""
    F = []
    c = M["cons"]; vF = M["vowel"]["formants"]
    on = M["traj"][0]["F"]
    bp = M.get("burst_peak_db", -99); bj = M.get("burst_jump_db_20ms", 0); bt = M.get("burst_t_after_release_ms", 99)
    if syl in ("ba", "pa"):
        if M.get("closure_min_db", 0) > -25: F.append("closure_shallow")
        if M.get("closure_ms_le_-25", 0) < 40: F.append("closure_short")
        need = 3.0 if syl == "ba" else 8.0
        if bp < need: F.append("burst_weak")
        if bj < 15: F.append("burst_no_jump")
        if not (-5 <= bt <= 10): F.append("burst_late")
        if not (400 <= M.get("burst_centroid", 0) <= 800): F.append("burst_centroid")
        if syl == "ba":
            if not (on[0] and on[0] < vF[0] - 20): F.append("F1_not_rising")
            if abs(on[1] - vF[1]) > 150: F.append("F2_not_flat")
        if syl == "pa":
            if not (on[0] and on[0] <= vF[0] + 80): F.append("F1_onset_high")
            gp = M["gap"]
            if not (30 <= gp["ms"] <= 50): F.append("gap_length")
            if not (-18 <= gp["level_db"] <= -2): F.append("gap_level")
    elif syl == "ma":
        if c["low500_frac"] < 0.95: F.append("murmur_not_low")
        if c.get("nose_over_lip_db", -99) < 30: F.append("nose_weak")
        if not (-6 <= c["level_db"] <= 2): F.append("murmur_level")
        if c["hnr"] < 3: F.append("murmur_unvoiced")
        if bp >= 3 or bj >= 15: F.append("has_burst")
        if not (on[0] and on[0] < vF[0] - 20): F.append("F1_not_rising")
    elif syl == "va":
        if not (95 <= c["f0"] <= 120): F.append("f0_lost")
        if not (1 <= c["hnr"] <= 8): F.append("hnr_out" + ("_low" if c["hnr"] < 1 else "_high"))
        if c["gt2k_frac"] < 0.10: F.append("noise_weak")
        if not (-25 <= c["level_db"] <= -10): F.append("level" + ("_loud" if c["level_db"] > -10 else "_quiet"))
        if M.get("closure_min_db", 0) <= c["level_db"] - 8: F.append("has_closure")
        if bp >= 3: F.append("has_burst")
    elif syl == "fa":
        if not (-32 <= c["level_db"] <= -18): F.append("level" + ("_loud" if c["level_db"] > -18 else "_quiet"))
        if not (1500 <= c["centroid"] <= 3500): F.append("centroid" + ("_high" if c["centroid"] > 3500 else "_low"))
        if c["hnr"] >= 0: F.append("voiced")
        if c["gt2k_frac"] < 0.10: F.append("noise_not_broad")
        if M.get("closure_min_db", 0) <= c["level_db"] - 8: F.append("has_closure")
        if bp >= 3: F.append("has_burst")
    elif syl == "wa":
        if c["hnr"] < 3: F.append("unvoiced")
        if c["level_db"] < -10: F.append("too_quiet")
        cF = c["formants"]
        if not (cF[0] and cF[0] <= 420): F.append("F1_high")
        if not (cF[1] and cF[1] <= 1050): F.append("F2_high")
        if vF[1] - cF[1] < 150: F.append("F2_not_rising")
        if bp >= 3: F.append("has_burst")
        if c["gt2k_frac"] >= 0.05: F.append("noisy")
    return (len(F) == 0), F

def adjust(syl, P, fails, M, attempt):
    """the decision from the measurement. Returns a NEW P, or None if nothing left to try."""
    P = dict(P); f = set(fails); c = M["cons"]
    if syl == "ba":
        if "closure_shallow" in f or "closure_short" in f:
            P["c_pos"] = 0.98; P["d_close"] = min(0.15, P["d_close"] + 0.03); return P
        if "burst_weak" in f or "burst_no_jump" in f or "burst_late" in f:
            # burst too small: more gain; too slow: a faster release (smaller glide)
            if P["gain"] < 12: P["gain"] = min(12.0, P["gain"] * 1.6)
            else: P["glide"] = max(0.10, P["glide"] - 0.10)
            return P
        if "F1_not_rising" in f or "F2_not_flat" in f:
            P["glide"] = max(0.10, P["glide"] - 0.10); return P
        if "burst_centroid" in f:
            P["c_pos"] = 0.96 if P["c_pos"] >= 0.97 else 0.99; return P
    elif syl == "pa":
        if "closure_shallow" in f or "closure_short" in f:
            P["c_pos"] = 0.98; P["d_close"] = min(0.15, P["d_close"] + 0.03); return P
        if "burst_weak" in f or "burst_no_jump" in f:
            if P["gain"] < 12: P["gain"] = min(12.0, P["gain"] * 1.6)
            else: P["glide"] = max(0.10, P["glide"] - 0.10)
            return P
        if "gap_level" in f:
            gl = M["gap"]["level_db"]
            # too loud after the burst tail -> longer gap; too quiet -> aspiration through a lip narrowing
            if gl > -2: P["d_gap"] = 0.05
            else: P["gap_area"] = 0.30
            return P
        if "gap_length" in f:
            P["d_gap"] = 0.04; return P
        if "F1_onset_high" in f:
            # keep the lips narrowed through the gap so the vowel still has an opening transition
            P["gap_area"] = 0.30 if P["gap_area"] >= 2.0 else max(0.15, P["gap_area"] - 0.10); return P
        if "burst_centroid" in f:
            P["c_pos"] = 0.96 if P["c_pos"] >= 0.97 else 0.99; return P
    elif syl == "ma":
        if "murmur_not_low" in f or "nose_weak" in f or "has_burst" in f:
            P["velum"] = 0.8; P["c_pos"] = 0.98 if P["c_pos"] < 0.98 else 0.96; return P
        if "murmur_level" in f or "murmur_unvoiced" in f:
            P["d_murmur"] = 0.18; return P
        if "F1_not_rising" in f:
            P["glide"] = max(0.15, P["glide"] - 0.10); return P
    elif syl == "va":
        if "noise_weak" in f or "hnr_out_high" in f or "level_loud" in f:
            # the voice is drowning the lips' weak noise (measured map: the window is voicing 0.10-0.15 at 0.96/0.10)
            P["voicing"] = max(0.08, round(P["voicing"] - 0.01, 2)); return P
        if "f0_lost" in f or "hnr_out_low" in f:
            P["voicing"] = min(0.6, round(P["voicing"] + 0.01, 2)); return P
        if "level_quiet" in f:
            P["c_area"] = 0.18; P["voicing"] = min(0.6, round(P["voicing"] + 0.05, 2)); return P
        if "has_closure" in f:
            P["c_area"] = 0.18; return P
    elif syl == "fa":
        if "level_quiet" in f:
            P["c_area"] = 0.20 if P["c_area"] < 0.20 else 0.25; P["c_pos"] = 0.97; return P
        if "level_loud" in f:
            P["c_pos"] = 1.0; P["c_area"] = 0.12; return P
        if "centroid_low" in f:
            P["c_pos"] = max(0.95, P["c_pos"] - 0.01); return P
        if "centroid_high" in f:
            P["c_pos"] = min(1.0, P["c_pos"] + 0.01); return P
        if "noise_not_broad" in f:
            P["c_pos"] = max(0.95, P["c_pos"] - 0.01); return P
    elif syl == "wa":
        if "noisy" in f or "unvoiced" in f:
            P["c_area"] = min(0.8, P["c_area"] + 0.05); return P
        if "F2_high" in f or "F1_high" in f:
            # measured map: the u preset never gets F2 below 1220; the AH tube + a 0.15 lip narrowing gives ~1000
            if P["knots"] != "AH": P["knots"] = "AH"; return P
            P["c_area"] = max(0.10, round(P["c_area"] - 0.03, 2)); return P
        if "F2_not_rising" in f:
            P["glide"] = max(0.3, P["glide"] - 0.1); return P
        if "too_quiet" in f:
            P["c_area"] = min(0.8, P["c_area"] + 0.1); return P
    return None

def score(syl, fails):
    return len(fails)

# ------------------------------------------------------------------ the school
def run(syl):
    P = dict(START[syl]); log = []; best = None
    for attempt in range(1, MAX_TRIES + 1):
        g, readable = build(syl, P)
        t0 = time.time()
        if syl == "ma":
            lip, nose = render(g, ports=True)
            y = mouth2._finish(lip, nose) if hasattr(mouth2, "_finish") else render(g)
            if y is None or not isinstance(y, np.ndarray): y = render(g)
            M = measure(y, g, syl, ports=(lip, nose))
        else:
            y = render(g); M = measure(y, g, syl)
        dt = time.time() - t0
        ok, fails = check(syl, M)
        apath = os.path.join(ATT, "%s-try%d.wav" % (syl, attempt)); wav_write(apath, y)
        entry = {"attempt": attempt, "params": dict(P), "ok": ok, "fails": fails, "render_s": round(dt, 2),
                 "measured": {k: v for k, v in M.items() if k != "env20_db"}, "env20_db": M["env20_db"]}
        log.append(entry)
        print("[%s] try %d ok=%s fails=%s  %s" % (syl, attempt, ok, fails, brief(syl, M)), flush=True)
        if best is None or score(syl, fails) < score(syl, best[2]):
            best = (y, readable, fails, M, attempt)
        if ok: break
        P2 = adjust(syl, P, fails, M, attempt)
        if P2 is None or P2 == P:
            print("[%s] no rule left for %s -- stopping" % (syl, fails), flush=True); break
        P = P2
    y, readable, fails, M, attempt = best
    wav_write(os.path.join(OUT, "ERAN-%s.wav" % syl), y)
    result = {"syl": syl, "speaker": "ERAN", "signature_ok": len(fails) == 0, "best_attempt": attempt,
              "fails": fails, "expected": EXPECTED[syl], "gesture": readable,
              "measured": {k: v for k, v in M.items() if k != "env20_db"}, "env20_db": M["env20_db"],
              "attempts": log, "written_by": "claude-cli-PEH-LIPS lips.py 2026-09-02",
              "wav": "ERAN-%s.wav" % syl}
    with open(os.path.join(OUT, "%s.json" % syl), "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=1, default=float)
    return result

def brief(syl, M):
    c = M["cons"]; v = M["vowel"]
    s = "cons lvl %.1f dB cen %.0f hnr %.1f f0 %.0f low500 %.2f >2k %.2f F %s | close min %.1f (<=-25: %.0f ms) | burst %.1f dB @%.1f ms jump %.1f cen %.0f | on %s -> vowel %s" % (
        c["level_db"], c["centroid"], c["hnr"], c["f0"], c["low500_frac"], c["gt2k_frac"], c["formants"],
        M.get("closure_min_db", 0), M.get("closure_ms_le_-25", 0), M.get("burst_peak_db", -99),
        M.get("burst_t_after_release_ms", 0), M.get("burst_jump_db_20ms", 0), M.get("burst_centroid", 0),
        M["traj"][0]["F"], v["formants"])
    if "nose_over_lip_db" in c: s += " | nose/lip %.1f dB" % c["nose_over_lip_db"]
    if "gap" in M: s += " | gap %.0f ms %.1f dB" % (M["gap"]["ms"], M["gap"]["level_db"])
    return s

if __name__ == "__main__":
    print("lips school: BLOCK_S=%s adult %.2f cm N=%d" % (T.BLOCK_S, mouth2._L_CHILD, mouth2.N_MAIN), flush=True)
    fam = ONLY or ["ba", "va", "ma", "pa", "fa", "wa"]
    summary = {}
    for s in fam:
        r = run(s)
        summary[s] = {"signature_ok": r["signature_ok"], "attempt": r["best_attempt"], "fails": r["fails"]}
    with open(os.path.join(OUT, "lips-summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=1)
    print(json.dumps(summary, indent=1))
