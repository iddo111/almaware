#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""glottal.py -- the GLOTTAL family of ERAN's mouth: a, ha, ya, cha, aya.
claude-cli-PEH-GLOTTAL, 2026-09-02, on Iddo's order (operate the mouth yourself).

Self-contained: stdlib + numpy + mouth2 (eran2:~/mouth-v2). No audio is played.
Each syllable is built from gesture-table.json ranges, rendered with
mouth2.say_gesture (C backend), MEASURED with numpy, and iterated up to 6 times
from the measurement until its acoustic signature matches the table's row.
Outputs: ~/throat-one-sample/school/ERAN-<syl>.wav + <syl>.json.
"""
import json, os, sys, wave, copy
import numpy as np
sys.path.insert(0, os.path.expanduser("~/mouth-v2"))
import mouth2

SR = 16000
BK = "c"
AH = [-0.6013, -0.0092, -0.6310, -1.4002, 1.6041, -1.8558, 1.8504, 1.9330]
AH4 = list(AH); AH4[3] = -0.9          # digitally silent at voicing 0 (manual 1.1)
F0 = 105.0
OUT = os.path.expanduser("~/throat-one-sample/school")
os.makedirs(OUT, exist_ok=True)
KF = mouth2.keyframe
V = KF(AH)                              # THE vowel keyframe (gesture space 580/1226/2550)

# ------------------------------------------------------------------ measurement
def wav_write(path, y):
    w = wave.open(path, "wb"); w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((np.clip(y, -1, 1) * 32767).astype(np.int16).tobytes()); w.close()

def rms(y):
    y = np.asarray(y, float)
    return float(np.sqrt(np.mean(y ** 2))) if y.size else 0.0

def db(a, b): return float(20 * np.log10(max(a, 1e-12) / max(b, 1e-12)))

def psd(y, nper=1024):
    """Welch PSD in numpy (Hann, 50% overlap)."""
    y = np.asarray(y, float); nper = min(nper, len(y))
    if nper < 32: return np.array([0.0]), np.array([0.0])
    win = np.hanning(nper); hop = nper // 2
    acc = np.zeros(nper // 2 + 1); n = 0
    for i in range(0, len(y) - nper + 1, hop):
        seg_ = (y[i:i + nper] - y[i:i + nper].mean()) * win
        acc += np.abs(np.fft.rfft(seg_)) ** 2; n += 1
    f = np.fft.rfftfreq(nper, 1.0 / SR)
    return f, acc / max(n, 1)

def centroid(y, fmin=200):
    f, p = psd(y); m = f >= fmin
    return float(np.sum(f[m] * p[m]) / (np.sum(p[m]) + 1e-30))

def band_frac(y, lo, hi):
    f, p = psd(y); tot = np.sum(p) + 1e-30
    return float(np.sum(p[(f >= lo) & (f < hi)]) / tot)

def formants(y, n=3):
    """LPC formants, same recipe as train_one.py / probe_manual.py."""
    x = np.asarray(y, float); x = x - x.mean()
    if x.std() < 1e-9 or len(x) < 64: return [0] * n
    x = x * np.hamming(len(x)); x = np.append(x[0], x[1:] - 0.97 * x[:-1])
    p = int(2 + SR / 1000)
    r = np.correlate(x, x, "full")[len(x) - 1:len(x) + p]
    if r[0] <= 0: return [0] * n
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

def f0_ac(y):
    y = np.asarray(y, float); y = y - y.mean()
    if rms(y) < 1e-5: return 0.0
    ac = np.correlate(y, y, "full")[len(y) - 1:]
    lo, hi = int(SR / 400), int(SR / 70)
    return float(SR / (lo + np.argmax(ac[lo:hi])))

def hnr(y):
    y = np.asarray(y, float); y = y - y.mean()
    if rms(y) < 1e-5: return -99.0
    N = len(y); ac = np.correlate(y, y, "full")[N - 1:]
    lo, hi = int(SR / 400), int(SR / 70)
    # normalised cross-correlation at each lag (ac[lag]/ac[0] is biased low by (N-lag)/N on short windows)
    e = np.cumsum(y ** 2); lags = np.arange(lo, hi)
    head = e[N - lags - 1]; tail = e[N - 1] - e[lags - 1]
    r = float(np.max(ac[lo:hi] / np.sqrt(head * tail + 1e-30))); r = min(max(r, 1e-6), 0.999999)
    return float(10 * np.log10(r / (1 - r)))

def hnr_frames(y, w=0.040):
    """median HNR over 40 ms frames (a falling f0 + vibrato smears one long autocorrelation)."""
    n = int(w * SR); vals = [hnr(y[i:i + n]) for i in range(0, len(y) - n + 1, n // 2)]
    return float(np.median(vals)) if vals else -99.0

def onset_overshoot(y, t_on, t_vowel0, t_vowel1):
    """peak 5 ms rms within 40 ms after the onset, dB re the steady vowel. A burst is > +3 dB;
    a plain (glottal) voicing onset from silence is <= 0 -- the 'jump' metric cannot tell them apart."""
    e = env(seg(y, t_on, t_on + 0.040), 0.005)
    return round(db(e.max() if e.size else 0.0, rms(seg(y, t_vowel0, t_vowel1))), 1)

def env(y, w=0.005):
    n = int(w * SR)
    return np.array([rms(y[i:i + n]) for i in range(0, len(y) - n + 1, n)])

def seg(y, t0, t1):
    return y[int(t0 * SR):int(t1 * SR)]

def burst_check(y):
    """energy jump > 15 dB within 20 ms (5 ms env, vs the min of the previous 4 frames)."""
    e = env(y, 0.005); best = (-99.0, 0.0)
    for i in range(4, len(e)):
        prev = max(e[i - 4:i].min(), 1e-6)
        j = db(e[i], prev)
        if j > best[0]: best = (j, i * 5.0)
    return {"max_jump_db": round(best[0], 1), "at_ms": best[1], "burst": bool(best[0] > 15)}

def traj(y, t0, t1, win=0.030, hop=0.010):
    """F1/F2/F3 every 10 ms from t0 to t1 (30 ms LPC windows)."""
    out = []
    t = t0
    while t + win <= t1 + 1e-9:
        out.append([int(round(t * 1000))] + formants(seg(y, t, t + win)))
        t += hop
    return out

def env20(y):
    return [round(db(v, 1.0), 1) for v in env(y, 0.020)]

def rise_time_ms(y, t_from, t_to):
    """10->90% rise of the 5 ms rms envelope between t_from and t_to."""
    e = env(seg(y, t_from, t_to), 0.005)
    if e.size < 3: return 0.0
    top = e.max(); lo = int(np.argmax(e >= 0.1 * top)); hi = int(np.argmax(e >= 0.9 * top))
    return float((hi - lo) * 5)

def render(g, seed=0):
    gg = dict(g); gg["keyframes"] = [np.asarray(k, float) for k in g["keyframes"]]
    return mouth2.say_gesture(gg, seed=seed, backend=BK)

def g_json(g):
    return {"keyframes": [[round(float(v), 4) for v in k] for k in g["keyframes"]],
            "keyframe_dims": "k1..k8 log2-area, c_pos, c_area, velum, tenseness, voicing",
            "durations": g["durations"], "f0_knots": g["f0_knots"],
            "tenseness_knots": g["tenseness_knots"], "glide": g.get("glide", 0.35),
            "burst": g.get("burst"), "backend": BK, "seed": 0}

# ------------------------------------------------------------------ syllables
def std(kfs, durs, glide=0.35):
    return {"keyframes": kfs, "durations": durs, "f0_knots": [F0, F0, F0 * 0.93],
            "tenseness_knots": [0.6, 0.6, 0.55], "glide": glide}

# ---- a : the vowel alone ---------------------------------------------------
def build_a(p):
    g = std([KF(AH, tenseness=p["ten"])], [p["dur"]])
    g["f0_knots"] = [F0, F0, F0 * 0.95]          # slight fall, Iddo's 105 at the centre
    return g

def check_a(y, p, g):
    d = p["dur"]; st = seg(y, 0.15, 0.45)         # the steady middle (the tail is the f0 fall)
    F = formants(st); m = {"F1": F[0], "F2": F[1], "F3": F[2], "f0": round(f0_ac(st), 1),
                           "hnr_db": round(hnr_frames(st), 1), "hnr_whole_db": round(hnr(st), 1),
                           "frac_gt2k": round(band_frac(st, 2000, 8000), 3),
                           "burst": burst_check(y), "onset_overshoot_db": onset_overshoot(y, 0.0, 0.15, 0.45),
                           "dur_s": d, "env20_db": env20(y)}
    m["exp"] = "F1 580+-60 F2 1226+-80 F3 2550+-150, f0 105+-5, HNR >= 7 (40 ms frames), onset overshoot <= +3 dB (no burst)"
    ok = (abs(F[0] - 580) <= 60 and abs(F[1] - 1226) <= 80 and abs(F[2] - 2550) <= 150
          and abs(m["f0"] - 105) <= 5 and m["hnr_db"] >= 7 and m["onset_overshoot_db"] <= 3)
    return ok, m

def adjust_a(p, m):
    q = dict(p)
    if m["hnr_db"] < 7: q["ten"] = max(0.4, p["ten"] - 0.1)
    if m["F1"] > 640: q["ten"] = max(0.4, p["ten"] - 0.1)
    return q

# ---- ha : aspiration, pharynx noise (0.32-0.40, 0.15-0.25), voicing 0-0.2 -----
def build_ha(p):
    kf_h = KF(AH, c_pos=p["c_pos"], c_area=p["c_area"], tenseness=p["ten"], voicing=p["voi"])
    return std([kf_h, kf_h, V], [p["d1"], p["d2"], 0.35])

def check_ha(y, p, g):
    dc = p["d1"] + p["d2"]; nz = seg(y, 0.010, dc); vow = seg(y, dc + 0.15, dc + 0.33)
    m = {"noise_ms": round(dc * 1000), "centroid_hz": round(centroid(nz, 200)), "hnr_db": round(hnr(nz), 1),
         "level_db_re_vowel": round(db(rms(nz), rms(vow)), 1), "frac_lt500": round(band_frac(nz, 0, 500), 3),
         "burst": burst_check(y), "vowel_F": formants(vow),
         "traj_F1F2F3": traj(y, dc - 0.02, dc + 0.14), "env20_db": env20(y)}
    m["exp"] = "noise 50-90 ms, HNR < 0, centroid 3700-5100, level -8..-13 dB, no burst, <500 Hz frac < 0.3, then vowel 580/1226"
    ok = (50 <= m["noise_ms"] <= 90 and m["hnr_db"] < 0 and 3700 <= m["centroid_hz"] <= 5100
          and -13 <= m["level_db_re_vowel"] <= -8 and not m["burst"]["burst"] and m["frac_lt500"] < 0.3
          and abs(m["vowel_F"][0] - 580) <= 60 and abs(m["vowel_F"][1] - 1226) <= 100)
    return ok, m

def adjust_ha(p, m):
    q = dict(p)
    if m["hnr_db"] >= 0: q["voi"] = max(0.0, p["voi"] - 0.1)            # too voiced -> less voicing
    if m["level_db_re_vowel"] < -13: q["c_area"] = min(0.25, p["c_area"] + 0.05)   # too weak -> wider channel
    if m["level_db_re_vowel"] > -8: q["c_area"] = max(0.10, p["c_area"] - 0.03)     # too loud -> narrower
    if m["centroid_hz"] < 3700: q["c_pos"] = max(0.30, p["c_pos"] - 0.03)          # too dark -> deeper
    if m["centroid_hz"] > 5100: q["c_pos"] = min(0.40, p["c_pos"] + 0.03)
    if m["noise_ms"] < 50: q["d1"] = p["d1"] + 0.02
    if m["noise_ms"] > 90: q["d1"] = p["d1"] - 0.02
    return q

# ---- ya : glide from the /i/ tube (0.70-0.78, 0.4-0.6) into /a/ ------------
def build_ya(p):
    kf_y = KF(mouth2.vowel_knots("i"), c_pos=p["c_pos"], c_area=p["c_area"], voicing=1.0)
    return std([kf_y, kf_y, V], [p["d1"], p["d2"], p["d3"]], glide=p["glide"])

def check_ya(y, p, g):
    dc = p["d1"] + p["d2"]; on = seg(y, 0.015, 0.055); vow = seg(y, dc + p["glide"] * p["d3"] + 0.05, dc + p["d3"] - 0.02)
    cons = seg(y, 0.010, dc)
    tr = traj(y, dc - 0.02, dc + 0.20)
    m = {"onset_F": formants(on), "vowel_F": formants(vow), "hnr_cons_db": round(hnr(cons), 1),
         "f0_cons": round(f0_ac(cons), 1), "frac_gt2k_cons": round(band_frac(cons, 2000, 8000), 3),
         "burst": burst_check(y), "traj_F1F2F3": tr, "glide_ms": round(p["glide"] * p["d3"] * 1000),
         "level_cons_db_re_vowel": round(db(rms(cons), rms(vow)), 1), "env20_db": env20(y)}
    # time for F2 to fall from onset to within 100 Hz of the vowel's F2
    t_arr = None
    for row in tr:
        if row[2] and abs(row[2] - m["vowel_F"][1]) <= 100: t_arr = row[0]; break
    m["F2_arrives_ms_after_release"] = None if t_arr is None else t_arr - round(dc * 1000)
    m["exp"] = "onset F1<=300 F2>=1900; F2 slides to ~1205 over 100-150 ms (arrive 60-180 ms); HNR>=4 continuous; no burst; vowel 580/1226"
    ok = (m["onset_F"][0] <= 300 and m["onset_F"][1] >= 1900 and m["hnr_cons_db"] >= 4 and not m["burst"]["burst"]
          and t_arr is not None and 60 <= m["F2_arrives_ms_after_release"] <= 180
          and abs(m["vowel_F"][0] - 580) <= 60 and abs(m["vowel_F"][1] - 1226) <= 100
          and m["level_cons_db_re_vowel"] > -12)
    return ok, m

def adjust_ya(p, m):
    q = dict(p)
    if m["onset_F"][0] > 300: q["c_area"] = max(0.3, p["c_area"] - 0.1)          # F1 too high -> narrower palate
    if m["onset_F"][1] < 1900: q["c_pos"] = min(0.78, p["c_pos"] + 0.03)           # F2 too low -> more forward
    a = m["F2_arrives_ms_after_release"]
    if a is None or a > 180: q["glide"] = max(0.3, p["glide"] - 0.1)
    elif a < 60: q["glide"] = min(0.7, p["glide"] + 0.1)
    if m["hnr_cons_db"] < 4: q["c_area"] = min(0.6, p["c_area"] + 0.1)             # noisy -> out of the turbulence window
    return q

# ---- cha : voiceless uvular fricative (0.50-0.53, 0.12-0.20) ---------------
def build_cha(p):
    kf_f = KF(AH, c_pos=p["c_pos"], c_area=p["c_area"], voicing=0.0)
    return std([kf_f, kf_f, V], [p["d1"], p["d2"], 0.35])

def check_cha(y, p, g):
    dc = p["d1"] + p["d2"]; nz = seg(y, 0.010, dc); vow = seg(y, dc + 0.15, dc + 0.33)
    m = {"noise_ms": round(dc * 1000), "centroid_hz": round(centroid(nz, 200)), "hnr_db": round(hnr(nz), 1),
         "frac_1_3k": round(band_frac(nz, 1000, 3000), 3), "frac_gt4k": round(band_frac(nz, 4000, 8000), 3),
         "level_db_re_vowel": round(db(rms(nz), rms(vow)), 1), "frac_lt500": round(band_frac(nz, 0, 500), 3),
         "burst": burst_check(y), "vowel_F": formants(vow),
         "traj_F1F2F3": traj(y, dc - 0.02, dc + 0.14), "env20_db": env20(y)}
    m["exp"] = "noise >= 80 ms, centroid 1900-2500, 1-3 kHz frac >= 0.85, HNR <= 1, level -4..-8 dB, no burst, vowel 580/1226"
    ok = (m["noise_ms"] >= 80 and 1900 <= m["centroid_hz"] <= 2500 and m["frac_1_3k"] >= 0.85 and m["hnr_db"] <= 1
          and -8 <= m["level_db_re_vowel"] <= -4 and not m["burst"]["burst"]
          and abs(m["vowel_F"][0] - 580) <= 60 and abs(m["vowel_F"][1] - 1226) <= 100)
    return ok, m

def adjust_cha(p, m):
    q = dict(p)
    if m["centroid_hz"] > 2500 or m["frac_1_3k"] < 0.85: q["c_pos"] = max(0.50, p["c_pos"] - 0.01)
    if m["centroid_hz"] < 1900: q["c_pos"] = min(0.53, p["c_pos"] + 0.01)
    if m["level_db_re_vowel"] < -8: q["c_area"] = min(0.25, p["c_area"] + 0.03)
    if m["level_db_re_vowel"] > -4: q["c_area"] = max(0.10, p["c_area"] - 0.03)
    if m["noise_ms"] < 80: q["d1"] = p["d1"] + 0.02
    return q

# ---- aya : vowel, glottal stop (voicing gap), vowel ------------------------
def build_aya(p):
    gap = KF(p["gap_knots"], c_pos=p["gap_cpos"], c_area=p["gap_carea"], voicing=0.0)
    g = std([V, gap, V], [p["d1"], p["d2"], p["d3"]], glide=p["glide"])
    g["f0_knots"] = [F0, F0 * 0.97, F0 * 0.93]
    return g

def check_aya(y, p, g):
    d1, d2, d3 = p["d1"], p["d2"], p["d3"]
    v1 = seg(y, d1 - 0.15, d1 - 0.02); gap = seg(y, d1 + 0.015, d1 + d2 - 0.005); v2 = seg(y, d1 + d2 + 0.12, d1 + d2 + d3 - 0.02)
    e5 = env(y, 0.005); ivow = rms(v1)
    # how long the envelope stays <= -20 dB re the first vowel
    below = [i * 5 for i, v in enumerate(e5) if db(v, ivow) <= -20 and d1 * 1000 - 20 <= i * 5 <= (d1 + d2) * 1000 + 60]
    m = {"gap_db_re_vowel": round(db(rms(gap), ivow), 1), "gap_ms_at_le_-20dB": (below[-1] - below[0] + 5) if below else 0,
         "rise_10_90_ms": rise_time_ms(y, d1 + d2 - 0.01, d1 + d2 + 0.16),
         "vowel1_F": formants(v1), "vowel2_F": formants(v2), "f0_v2": round(f0_ac(v2), 1), "hnr_v2_db": round(hnr_frames(v2), 1),
         "burst": burst_check(y), "onset_overshoot_db": onset_overshoot(y, d1 + d2, d1 + d2 + 0.12, d1 + d2 + d3 - 0.02),
         "gap_centroid_hz": round(centroid(gap, 200)),
         "traj_F1F2F3": traj(y, d1 + d2 - 0.02, d1 + d2 + 0.12), "env20_db": env20(y)}
    m["exp"] = ("gap <= -20 dB for >= 50 ms, voicing rise 10-90% <= 70 ms, no burst = onset overshoot <= +3 dB re vowel "
                "(the jump metric fires on ANY onset from silence), both vowels 580/1226, f0 ~105")
    ok = (m["gap_db_re_vowel"] <= -20 and m["gap_ms_at_le_-20dB"] >= 50 and m["rise_10_90_ms"] <= 70
          and m["onset_overshoot_db"] <= 3
          and abs(m["vowel1_F"][0] - 580) <= 60 and abs(m["vowel2_F"][0] - 580) <= 60
          and abs(m["vowel1_F"][1] - 1226) <= 100 and abs(m["vowel2_F"][1] - 1226) <= 100)
    return ok, m

def adjust_aya(p, m):
    q = dict(p)
    if m["gap_db_re_vowel"] > -20:
        # the tract still hisses at voicing 0 -> first try the AH4 knots, then a lip seal in the gap
        if p["gap_knots"] == AH: q["gap_knots"] = AH4
        else: q["gap_cpos"], q["gap_carea"] = 0.97, 0.0
    if m["gap_ms_at_le_-20dB"] < 50: q["d2"] = p["d2"] + 0.02
    if m["rise_10_90_ms"] > 70: q["glide"] = max(0.02, p["glide"] / 2)
    if m["onset_overshoot_db"] > 3: q["gap_cpos"], q["gap_carea"] = 0.65, 2.0; q["gap_knots"] = AH4
    return q

FAMILY = {
    "a":   ("alef/ayin (vowel)", build_a,   check_a,   adjust_a,   {"dur": 0.60, "ten": 0.6}),
    "ha":  ("he",        build_ha,  check_ha,  adjust_ha,  {"c_pos": 0.35, "c_area": 0.15, "ten": 0.25, "voi": 0.2, "d1": 0.06, "d2": 0.02}),
    "ya":  ("yod",       build_ya,  check_ya,  adjust_ya,  {"c_pos": 0.75, "c_area": 0.5, "d1": 0.06, "d2": 0.02, "d3": 0.32, "glide": 0.5}),
    "cha": ("chet",      build_cha, check_cha, adjust_cha, {"c_pos": 0.51, "c_area": 0.15, "d1": 0.10, "d2": 0.015}),
    "aya": ("alef/ayin glottal onset (a-?-a)", build_aya, check_aya, adjust_aya,
            {"d1": 0.25, "d2": 0.07, "d3": 0.32, "glide": 0.02, "gap_knots": AH, "gap_cpos": 0.65, "gap_carea": 2.0}),
}

def run(which):
    results = {}
    for syl in which:
        letter, build, check, adjust, p = FAMILY[syl]
        log = []; best = None
        for attempt in range(1, 7):
            g = build(p); y = render(g)
            ok, m = check(y, p, g)
            slim = {k: v for k, v in m.items() if k not in ("traj_F1F2F3", "env20_db")}
            log.append({"attempt": attempt, "params": copy.deepcopy(p), "ok": ok, "measured": slim})
            print("[%s] attempt %d ok=%s %s" % (syl, attempt, ok, json.dumps(slim)), flush=True)
            if best is None or ok: best = (p, g, y, m, ok)
            if ok: break
            p2 = adjust(p, m)
            if p2 == p:
                print("[%s] no adjustment left; stopping" % syl); break
            p = p2
        p, g, y, m, ok = best
        wav_write(os.path.join(OUT, "ERAN-%s.wav" % syl), y)
        rec = {"syl": syl, "letter": letter, "signature_ok": ok, "attempts": len(log),
               "gesture": g_json(g), "params": p, "measured": m, "log": log,
               "speaker": "ERAN", "mouth": "eran2:~/mouth-v2/mouth2.py adult 17.60 cm, backend c",
               "author": "claude-cli-PEH-GLOTTAL 2026-09-02"}
        with open(os.path.join(OUT, "%s.json" % syl), "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, indent=1)
        results[syl] = ok
    print("RESULT", json.dumps(results))

if __name__ == "__main__":
    run(sys.argv[1:] or list(FAMILY))
