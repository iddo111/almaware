#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""back.py -- the BACK family of ERAN's mouth: ga, ka, kha, qa.
claude-cli-PEH-BACK, 2026-09-02. Runs on eran2 (stdlib + numpy + scipy + mouth2).

For each syllable: build the gesture from gesture-table.json ranges, render with
mouth2.say_gesture (C backend, burst dials), MEASURE the acoustic signature with
numpy, and iterate up to 6 times deciding each change from the measurement.
Writes school/ERAN-<syl>.wav (best attempt) + <syl>.json (final gesture + every
attempt's numbers). No audio is played anywhere.
"""
import json, os, sys, time, wave
import numpy as np
sys.path.insert(0, os.path.expanduser("~/mouth-v2"))
import mouth2
from scipy.signal import welch

SR = 16000
BK = "c"
AH = [-0.6013, -0.0092, -0.6310, -1.4002, 1.6041, -1.8558, 1.8504, 1.9330]
F0 = 105.0
OUT = os.path.expanduser("~/throat-one-sample/school")
os.makedirs(OUT, exist_ok=True)
KF = mouth2.keyframe

# ------------------------------------------------------------ measurement
def wav(path, y):
    w = wave.open(path, "wb"); w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((np.clip(y, -1, 1) * 32767).astype(np.int16).tobytes()); w.close()

def psd(y, nper=1024):
    y = np.asarray(y, float); nper = min(nper, len(y))
    return welch(y, fs=SR, nperseg=nper, noverlap=nper // 2)

def centroid(y, fmin=200):
    f, p = psd(y); m = f >= fmin
    return float(np.sum(f[m] * p[m]) / (np.sum(p[m]) + 1e-30))

def band_frac(y, lo, hi):
    f, p = psd(y); tot = np.sum(p) + 1e-30
    return float(np.sum(p[(f >= lo) & (f < hi)]) / tot)

def rms(y):
    y = np.asarray(y, float)
    return float(np.sqrt(np.mean(y ** 2))) if len(y) else 0.0

def db(a, b): return float(20 * np.log10(max(a, 1e-12) / max(b, 1e-12)))

def formants(y, n=3):
    """LPC formants (the train_one.py recipe that matched Iddo F1/F2)."""
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
    y = np.asarray(y, float); y = y - y.mean()
    if rms(y) < 1e-5: return -99.0
    ac = np.correlate(y, y, "full")[len(y) - 1:]; ac = ac / ac[0]
    lo, hi = int(SR / 400), int(SR / 70)
    r = float(np.max(ac[lo:hi])); r = min(max(r, 1e-6), 0.999999)
    return float(10 * np.log10(r / (1 - r)))

def env(y, w):
    n = int(w * SR)
    return np.array([rms(y[i:i + n]) for i in range(0, len(y) - n + 1, n)])

def S(t): return int(round(t * SR))

def traj(y, t0, n=10, step=0.010, win=0.025):
    """F1/F2/F3 every 10 ms from t0, 25 ms windows."""
    out = []
    for k in range(n):
        a = S(t0 + k * step); seg = y[a:a + S(win)]
        if len(seg) < S(win): break
        out.append([int(k * step * 1000)] + formants(seg))
    return out

def render(g):
    gg = dict(g); gg["keyframes"] = [np.asarray(k, float) for k in g["keyframes"]]
    return mouth2.say_gesture(gg, seed=0, backend=BK)

# ------------------------------------------------------------ gestures
def kf_json(kf):
    kf = [round(float(v), 4) for v in kf]
    return {"knots8": kf[:8], "c_pos": kf[8], "c_area": kf[9], "velum": kf[10],
            "tenseness": kf[11], "voicing": kf[12]}

def build(syl, P):
    """P: dict of dials -> gesture dict + timeline."""
    V = KF(AH)
    f0k = [F0, F0, F0 * 0.93]; tenk = [0.6, 0.6, 0.55]
    if syl in ("ga",):
        kc = KF(AH, c_pos=P["c_pos"], c_area=0.0, velum=0.0, voicing=1.0)
        g = {"keyframes": [kc, kc, V], "durations": [P["d_close"], P["d_trans"], P["d_vowel"]],
             "f0_knots": f0k, "tenseness_knots": tenk, "glide": P.get("glide", 0.35),
             "burst": {"gain": P["burst_gain"], "tau_s": P.get("tau_s", 0.003)}}
        tl = {"t_rel": P["d_close"] + P["d_trans"], "t_voice": P["d_close"] + P["d_trans"]}
    elif syl in ("ka", "qa"):
        kc = KF(AH, c_pos=P["c_pos"], c_area=0.0, velum=0.0, voicing=1.0)
        kgap = KF(AH, c_pos=P.get("gap_c_pos", 0.65), c_area=P.get("gap_c_area", 2.0),
                  tenseness=P.get("gap_tenseness", 0.6), voicing=P.get("gap_voicing", 0.0))
        g = {"keyframes": [kc, kc, kgap, V],
             "durations": [P["d_close"], P["d_trans"], P["d_gap"], P["d_vowel"]],
             "f0_knots": f0k, "tenseness_knots": tenk, "glide": P.get("glide", 0.35),
             "burst": {"gain": P["burst_gain"], "tau_s": P.get("tau_s", 0.003)}}
        tl = {"t_rel": P["d_close"] + P["d_trans"], "t_voice": P["d_close"] + P["d_trans"] + P["d_gap"]}
    elif syl == "kha":
        kf = KF(AH, c_pos=P["c_pos"], c_area=P["c_area"], velum=0.0, tenseness=0.6, voicing=P.get("voicing", 0.0))
        g = {"keyframes": [kf, kf, V], "durations": [P["d_noise"], P["d_trans"], P["d_vowel"]],
             "f0_knots": f0k, "tenseness_knots": tenk, "glide": P.get("glide", 0.35)}
        tl = {"t_rel": P["d_noise"] + P["d_trans"], "t_voice": P["d_noise"] + P["d_trans"]}
    else:
        raise ValueError(syl)
    return g, tl

def measure(syl, y, tl, P):
    """The signature numbers. All dB re the steady vowel."""
    t_rel, t_voice = tl["t_rel"], tl["t_voice"]
    e5 = env(y, 0.005); e20 = env(y, 0.020)
    vow = y[-S(0.18):-S(0.03)]
    vow_rms = rms(vow); vow_e5 = e5[-36:-6].mean()
    m = {"vowel": {"F": formants(vow), "f0": round(f0_ac(vow), 1), "hnr": round(hnr(vow), 1),
                   "rms": round(vow_rms, 4)},
         "env20_db": [round(db(v, vow_e5), 1) for v in e20]}
    # consonant portion
    c0, c1 = S(0.015), S(t_rel - 0.005)
    cons = y[c0:c1]
    m["cons"] = {"ms": int((t_rel - 0.020) * 1000), "level_db": round(db(rms(cons), vow_rms), 1),
                 "centroid": round(centroid(cons, 200)), "hnr": round(hnr(cons), 1),
                 "f0": round(f0_ac(cons), 1),
                 "frac_lt500": round(band_frac(cons, 0, 500), 3),
                 "frac_1k3k": round(band_frac(cons, 1000, 3000), 3),
                 "frac_gt2k": round(band_frac(cons, 2000, 8000), 3),
                 "frac_gt4k": round(band_frac(cons, 4000, 8000), 3)}
    # burst: 5 ms envelope in [t_rel-15, t_rel+60] ms; jump = max rise within 20 ms
    i_rel = int(t_rel / 0.005)
    win = e5[max(0, i_rel - 3):i_rel + 12]
    edb = 20 * np.log10(np.maximum(win, 1e-9) / max(vow_e5, 1e-9))
    jump = 0.0; jump_at = -1
    for i in range(len(edb)):
        for k in range(1, 5):
            if i + k < len(edb) and edb[i + k] - edb[i] > jump:
                jump, jump_at = edb[i + k] - edb[i], i + k
    ipk = int(np.argmax(win))
    seg_b = y[S(t_rel):S(t_rel) + S(0.020)]
    m["burst"] = {"peak_db_re_vowel": round(float(edb[ipk]), 1),
                  "peak_at_ms_after_release": int((ipk - 3) * 5),
                  "jump_db_within_20ms": round(float(jump), 1),
                  "jump_at_ms_after_release": int((jump_at - 3) * 5) if jump_at >= 0 else None,
                  "centroid_20ms": round(centroid(seg_b, 300)),
                  "pre_release_db": round(float(edb[:3].mean()), 1)}
    # gap (VOT) for voiceless stops
    if "d_gap" in P:
        gseg = y[S(t_rel + 0.015):S(t_voice - 0.002)]
        m["gap"] = {"ms": int(P["d_gap"] * 1000), "level_db": round(db(rms(gseg), vow_rms), 1),
                    "hnr": round(hnr(gseg), 1), "centroid": round(centroid(gseg, 200))}
    # formant transition into the vowel
    m["_c_pos"] = float(P["c_pos"])
    m["F_onset_15_60ms"] = formants(y[S(t_rel + 0.015):S(t_rel + 0.060)])
    m["F_voiced_onset_15_60ms"] = formants(y[S(t_voice + 0.015):S(t_voice + 0.060)])
    m["traj_from_release"] = traj(y, t_rel, n=14)
    return m

def check(syl, m):
    """Signature per gesture-table.json. Returns (ok, list of failures)."""
    fails = []
    c, b, v = m["cons"], m["burst"], m["vowel"]
    F_on = m["F_onset_15_60ms"]
    if syl in ("ga", "ka", "qa"):
        if c["level_db"] > -20: fails.append("closure %.1f dB > -20" % c["level_db"])
        if b["jump_db_within_20ms"] < 15: fails.append("burst jump %.1f dB < 15" % b["jump_db_within_20ms"])
        if not (0 <= b["peak_at_ms_after_release"] <= 15): fails.append("burst peak at %d ms (want 0-15)" % b["peak_at_ms_after_release"])
        lo, hi = (850, 1050) if syl == "ga" else (800, 1000)
        if not (lo <= b["centroid_20ms"] <= hi): fails.append("burst centroid %d (want %d-%d)" % (b["centroid_20ms"], lo, hi))
        # velar pinch: the highest F2 in the first 45 ms after release (the transition is 14 ms of glide in a
        # voiceless stop, ~100 ms in a voiced one), falling into the vowel
        tr = m["traj_from_release"][:4]
        f2max = max(t[2] for t in tr) if tr else 0
        if f2max < 1400: fails.append("F2 after release max %d < 1400 (velar pinch)" % f2max)
        if f2max - v["F"][1] < 120: fails.append("F2 fall %d < 120" % (f2max - v["F"][1]))
        F1v = m["F_voiced_onset_15_60ms"][0]
        if F1v >= v["F"][0]: fails.append("F1 voiced onset %d not below vowel %d" % (F1v, v["F"][0]))
        if syl == "qa" and m.get("_c_pos", 0.485) > 0.49: fails.append("qa must sit behind ka (c_pos <= 0.49)")
        if syl == "ga":
            if c["hnr"] < -3: fails.append("closure voicing HNR %.1f (voice bar missing)" % c["hnr"])
            if not (85 <= c["f0"] <= 125): fails.append("closure f0 %.0f not ~105" % c["f0"])
        else:
            g = m["gap"]
            if not (30 <= g["ms"] <= 50): fails.append("gap %d ms" % g["ms"])
            if not (-9 <= g["level_db"] <= -2): fails.append("gap level %.1f (want -2..-9)" % g["level_db"])
            if g["hnr"] > 2: fails.append("gap HNR %.1f > 2 (voiced gap)" % g["hnr"])
    elif syl == "kha":
        if c["ms"] < 80: fails.append("noise %d ms < 80" % c["ms"])
        if not (1900 <= c["centroid"] <= 2500): fails.append("centroid %d (want 1900-2500)" % c["centroid"])
        if c["frac_1k3k"] < 0.85: fails.append("1-3k frac %.2f < 0.85" % c["frac_1k3k"])
        if c["hnr"] > 1: fails.append("HNR %.1f > 1 (voiced)" % c["hnr"])
        if not (-10 <= c["level_db"] <= -3): fails.append("level %.1f (want -4..-8)" % c["level_db"])
        if b["jump_db_within_20ms"] > 15: fails.append("a burst (%.1f dB) in a fricative" % b["jump_db_within_20ms"])
    return (not fails), fails

# ------------------------------------------------------------ iteration
START = {
    "ga":  dict(c_pos=0.50, d_close=0.09, d_trans=0.015, d_vowel=0.35, burst_gain=6.0),
    "ka":  dict(c_pos=0.51, d_close=0.09, d_trans=0.015, d_gap=0.040, d_vowel=0.35, burst_gain=6.0),
    "qa":  dict(c_pos=0.485, d_close=0.10, d_trans=0.015, d_gap=0.040, d_vowel=0.35, burst_gain=6.0),
    "kha": dict(c_pos=0.51, c_area=0.15, d_noise=0.12, d_trans=0.015, d_vowel=0.35),
}

def adjust(syl, P, fails, m):
    """Decide the next dials FROM the measurement (not a blind search)."""
    P = dict(P); why = []
    c, b = m["cons"], m["burst"]
    if syl in ("ga", "ka", "qa"):
        if any("closure" in f and "dB >" in f for f in fails):
            # seal leaks: move onto the 0.49-0.50 seal floor
            P["c_pos"] = 0.50 if syl != "qa" else max(0.48, P["c_pos"] + 0.005); why.append("seal leaks -> c_pos %.3f" % P["c_pos"])
        if any("burst jump" in f for f in fails):
            P["burst_gain"] = min(12.0, P["burst_gain"] * 1.5); why.append("weak burst -> gain %.1f" % P["burst_gain"])
        if any("burst peak at" in f for f in fails):
            P["tau_s"] = 0.002; P["d_trans"] = 0.010; why.append("late burst -> faster vent, shorter trans")
        if any("burst centroid" in f for f in fails):
            if b["centroid_20ms"] < 800:
                if P.get("tau_s", 0.003) > 0.0015: P["tau_s"] = 0.0015; why.append("burst is a thump -> faster vent tau 1.5 ms")
                elif P["c_pos"] <= 0.485 or syl == "qa":
                    # the seal window ends at 0.48 (0.475 leaks -16.8 dB): the place cannot go further back.
                    # measured: the thump is the low-frequency pressure dump, so less gain = brighter centroid
                    P["burst_gain"] = max(2.2, round(P["burst_gain"] - 2.0, 1)); why.append("burst dark at the seal back wall -> gain %.1f" % P["burst_gain"])
                else: P["c_pos"] = round(P["c_pos"] - 0.01, 3); why.append("burst still dark -> back c_pos %.2f" % P["c_pos"])
            else: P["c_pos"] = round(P["c_pos"] + 0.01, 3); why.append("burst too bright -> forward c_pos %.2f" % P["c_pos"])
        if any("F1 voiced onset" in f for f in fails) and "d_gap" in P and P.get("gap_voicing", 0.0) < 0.1:
            P["gap_voicing"], P["gap_tenseness"] = 0.15, 0.25; why.append("hard voice onset -> breathy aspirated gap (voicing 0.15, ten 0.25)")
        if (any("F2 after release" in f for f in fails) or any("F2 fall" in f for f in fails)) and "d_gap" in P:
            # transition is invisible when the gap noise is constriction-sourced: make the aspiration glottal
            # (breathy low voicing) and keep the tongue near the palate through the gap (no-noise area >= 0.49)
            P["gap_voicing"] = min(0.3, P.get("gap_voicing", 0.0) + 0.15); P["gap_tenseness"] = 0.25
            P["gap_c_pos"], P["gap_c_area"] = P["c_pos"], 0.8
            why.append("F2 pinch invisible -> glottal aspiration voicing %.2f, tongue held at %.2f/0.8" % (P["gap_voicing"], P["c_pos"]))
        if any("gap level" in f for f in fails):
            g = m["gap"]
            if g["level_db"] > -2: P["burst_gain"] = max(2.2, P["burst_gain"] / 1.5); why.append("gap too loud (vented pressure) -> gain %.1f" % P["burst_gain"])
            else: P["gap_voicing"] = min(0.3, P.get("gap_voicing", 0.0) + 0.1); P["gap_tenseness"] = 0.25; why.append("gap too quiet -> breathier gap")
        if any("gap HNR" in f for f in fails):
            P["gap_voicing"] = max(0.0, P.get("gap_voicing", 0.0) - 0.05); why.append("gap voiced -> gap voicing %.2f" % P["gap_voicing"])
        if any("voice bar" in f for f in fails) or any("closure f0" in f for f in fails):
            P["d_close"] = min(0.15, P["d_close"] + 0.03); why.append("voice bar weak -> longer closure %.2f" % P["d_close"])
    elif syl == "kha":
        if any("centroid" in f for f in fails):
            if c["centroid"] > 2500: P["c_pos"] = round(P["c_pos"] - 0.01, 3); why.append("too bright -> back c_pos %.2f" % P["c_pos"])
            else: P["c_pos"] = round(P["c_pos"] + 0.01, 3); why.append("too dark -> forward c_pos %.2f" % P["c_pos"])
        if any("1-3k" in f for f in fails):
            P["c_area"] = round(max(0.10, P["c_area"] - 0.02), 3); why.append("band spread -> narrower %.2f" % P["c_area"])
        if any("level" in f for f in fails):
            if c["level_db"] < -10: P["c_area"] = round(min(0.25, P["c_area"] + 0.03), 3); why.append("too quiet -> wider %.2f" % P["c_area"])
            else: P["c_area"] = round(max(0.10, P["c_area"] - 0.03), 3); why.append("too loud -> narrower %.2f" % P["c_area"])
        if any("HNR" in f for f in fails):
            P["voicing"] = 0.0; why.append("voiced -> voicing 0")
        if any("noise" in f and "ms" in f for f in fails):
            P["d_noise"] = 0.14; why.append("short -> 140 ms")
    return P, why

def run(syl, overrides=None, max_tries=6):
    P = dict(START[syl]); P.update(overrides or {})
    attempts = []; best = None
    for t in range(1, max_tries + 1):
        g, tl = build(syl, P)
        y = render(g)
        m = measure(syl, y, tl, P)
        ok, fails = check(syl, m)
        rec = {"try": t, "dials": dict(P), "ok": ok, "fails": fails, "measured": m}
        attempts.append(rec)
        print("[%s] try %d ok=%s dials=%s" % (syl, t, ok, json.dumps(P)))
        print("      cons", m["cons"]); print("      burst", m["burst"])
        if "gap" in m: print("      gap", m["gap"])
        print("      F_onset", m["F_onset_15_60ms"], "vowel", m["vowel"]["F"], "traj", m["traj_from_release"][:8])
        if fails: print("      FAILS:", fails)
        score = len(fails)
        if best is None or score < best[0]: best = (score, t, y, g, m, P)
        if ok: break
        P, why = adjust(syl, P, fails, m)
        print("      ->", why)
        if not why: print("      no rule fires; stopping"); break
    score, t, y, g, m, Pb = best
    wav(os.path.join(OUT, "ERAN-%s.wav" % syl), y)
    gj = {"syllable": syl, "speaker": "ERAN", "backend": BK, "seed": 0, "sr": SR,
          "keyframes": [kf_json(k) for k in g["keyframes"]], "durations": g["durations"],
          "f0_knots": g["f0_knots"], "tenseness_knots": g["tenseness_knots"], "glide": g.get("glide", 0.35),
          "burst": g.get("burst"), "dials": Pb, "signature_ok": bool(score == 0), "chosen_try": t,
          "measured": m, "attempts": [{k: a[k] for k in ("try", "dials", "ok", "fails")} for a in attempts],
          "attempt_measurements": [a["measured"] for a in attempts]}
    with open(os.path.join(OUT, "%s.json" % syl), "w", encoding="utf-8") as f:
        json.dump(gj, f, indent=1, ensure_ascii=False)
    print("[%s] SAVED try %d signature_ok=%s" % (syl, t, score == 0))
    return gj

if __name__ == "__main__":
    syls = sys.argv[1:] or ["ga", "ka", "kha", "qa"]
    ov = {}
    if os.environ.get("BACK_OVERRIDES"): ov = json.loads(os.environ["BACK_OVERRIDES"])
    t0 = time.time()
    for s in syls:
        run(s, ov.get(s))
    print("done in %.1f s" % (time.time() - t0))
