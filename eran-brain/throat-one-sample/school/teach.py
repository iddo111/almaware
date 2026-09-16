#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""teach.py -- ERAN learns LETTER -> MOUTH MOVEMENT from the 21 verified hand-made syllables.

claude-cli-MORE, 2026-09-03, on Iddo's order 'תפעיל אתה את הפה ... ותאמן את ערן על זה'.
Runs on eran2 only (the mouth lives here). numpy + mouth2 + the four family scripts' own
measurement code (lips.py tip.py back.py glottal.py) -- the SAME checkers that verified the
hand-made syllables now judge ERAN's predictions. Nothing is played anywhere.

  1. school/dataset.json      letter + class facts  ->  16-dim gesture vector (order below)
  2. leave-one-syllable-out   hold one out, fit on the other 20, predict, RENDER, MEASURE
  3. school/eran-mouth-v0.npz the MLP fitted on all 21 (+ the NN table)
  4. school/loo/              ERAN-<syl>-loo-mlp.wav / -loo-nn.wav + loo-results.json

FEATURE ORDER of the target vector (16 dims, all in the renderer's own units):
   0 c_pos       constriction position 0..1 (0 glottis, 1 lips) of the consonant keyframe
   1 c_area      constriction area cm^2 (0 = sealed, 2.0 = no constriction)
   2 velum       nasal port area (0 shut, 0.75 open)
   3 tenseness   glottal tenseness of the consonant keyframe
   4 voicing     0..1 of the consonant keyframe
   5 d_pre       seconds of vowel BEFORE the consonant (ra, aya; else 0)
   6 d_cons      seconds of the consonant hold
   7 d_trans     seconds of the second (identical) consonant keyframe = release timing
   8 d_gap       seconds of voiceless gap after release (VOT; 0 = none)
   9 gap_area    c_area during the gap (2.0 = fully open)
  10 d_bridge    seconds of a short vowel keyframe before the vowel (fast voicing onset; 0 = none)
  11 d_vowel     seconds of the final vowel
  12 glide       fraction of each segment spent gliding from the previous keyframe
  13 burst_gain  C-backend burst gain (0 = no burst dial)
  14 knots_i     1 = consonant keyframe uses the /i/ tube knots (ya), else the /ah/ FIT
  15 knots_ah4   1 = consonant keyframe uses the AH4 knots (aya's silent gap), else the /ah/ FIT
The vowel knots are always the shared /ah/ FIT; f0 knots [105,105,97.65]; tenseness knots [.6,.6,.55].
"""
import json, os, sys, time, wave, hashlib, traceback
import numpy as np

sys.path.insert(0, os.path.expanduser("~/mouth-v2"))
SCHOOL = os.path.expanduser("~/throat-one-sample/school")
sys.path.insert(0, SCHOOL)
import mouth2, tract_core as T
import lips, tip, back, glottal          # the family schools: their measure/check functions are reused

SR = 16000
BK = "c"
AH = [-0.6013, -0.0092, -0.6310, -1.4002, 1.6041, -1.8558, 1.8504, 1.9330]
AH4 = list(AH); AH4[3] = -0.9
KI = [float(v) for v in mouth2.vowel_knots("i")]
F0 = 105.0
KF = mouth2.keyframe
V13 = KF(AH)
LOO = os.path.join(SCHOOL, "loo"); os.makedirs(LOO, exist_ok=True)

FEATURES = ["c_pos", "c_area", "velum", "tenseness", "voicing", "d_pre", "d_cons", "d_trans", "d_gap",
            "gap_area", "d_bridge", "d_vowel", "glide", "burst_gain", "knots_i", "knots_ah4"]
ND = len(FEATURES)

# ------------------------------------------------------------------ the 21 verified syllables
# letter, hebrew, place, manner, nasal, voiced  -- the four facts a child's ear would hear
VERIFIED = {
    "ba":  ("bet",    "ב", "lips",    "stop",        0, 1, "lips"),
    "va":  ("vet",    "ב", "lips",    "fricative",   0, 1, "lips"),
    "ma":  ("mem",    "מ", "lips",    "nasal",       1, 1, "lips"),
    "pa":  ("pe",     "פ", "lips",    "stop",        0, 0, "lips"),
    "fa":  ("fe",     "פ", "lips",    "fricative",   0, 0, "lips"),
    "wa":  ("vav",    "ו", "lips",    "approximant", 0, 1, "lips"),
    "da":  ("dalet",  "ד", "tip",     "stop",        0, 1, "tip"),
    "ta":  ("tav",    "ת", "tip",     "stop",        0, 0, "tip"),
    "na":  ("nun",    "נ", "tip",     "nasal",       1, 1, "tip"),
    "la":  ("lamed",  "ל", "tip",     "approximant", 0, 1, "tip"),
    "sa":  ("samekh", "ס", "tip",     "fricative",   0, 0, "tip"),
    "za":  ("zayin",  "ז", "tip",     "fricative",   0, 1, "tip"),
    "sha": ("shin",   "ש", "palate",  "fricative",   0, 0, "tip"),
    "ra":  ("resh",   "ר", "tip",     "tap",         0, 1, "tip"),
    "ga":  ("gimel",  "ג", "back",    "stop",        0, 1, "back"),
    "kha": ("khaf",   "כ", "back",    "fricative",   0, 0, "back"),
    "a":   ("alef",   "א", "glottal", "vowel",       0, 1, "glottal"),
    "ha":  ("he",     "ה", "glottal", "fricative",   0, 0, "glottal"),
    "ya":  ("yod",    "י", "palate",  "approximant", 0, 1, "glottal"),
    "cha": ("chet",   "ח", "back",    "fricative",   0, 0, "glottal"),
    "aya": ("ayin",   "ע", "glottal", "stop",        0, 0, "glottal"),
}
SYLS = list(VERIFIED)
PLACES = ["lips", "tip", "palate", "back", "glottal"]
MANNERS = ["vowel", "stop", "fricative", "nasal", "approximant", "tap"]

# ------------------------------------------------------------------ gesture JSON -> vector
def flat13(kf):
    if isinstance(kf, dict):
        return [float(v) for v in kf["knots8"]] + [float(kf[k]) for k in ("c_pos", "c_area", "velum", "tenseness", "voicing")]
    return [float(v) for v in kf]

def load_gesture(syl):
    d = json.load(open(os.path.join(SCHOOL, syl + ".json"), encoding="utf-8"))
    g = d.get("gesture", d)
    kfs = [flat13(k) for k in g["keyframes"]]
    return kfs, [float(x) for x in g["durations"]], float(g.get("glide", 0.35)), g.get("burst")

def is_vowel(kf): return np.allclose(kf, V13, atol=2e-3)

def to_vector(kfs, durs, glide, burst):
    v = np.zeros(ND)
    n = len(kfs)
    if n == 1:                                   # 'a': the vowel alone
        v[0:5] = V13[8:13]; v[11] = durs[0]; v[12] = glide; return v
    ic = next(i for i in range(n) if not is_vowel(kfs[i]))
    C = kfs[ic]
    v[0:5] = C[8:13]; v[5] = sum(durs[:ic]); v[6] = durs[ic]
    if np.allclose(C[:8], AH, atol=2e-3): pass
    elif np.allclose(C[:8], AH4, atol=2e-3): v[15] = 1
    elif np.allclose(C[:8], KI, atol=2e-3): v[14] = 1
    else: raise ValueError("unknown consonant knots %s" % C[:8])
    j = ic + 1
    if j < n and np.allclose(kfs[j], C, atol=2e-3): v[7] = durs[j]; j += 1
    v[9] = 2.0
    if j < n and (not is_vowel(kfs[j])) and kfs[j][12] < 0.5 and not np.allclose(kfs[j], C, atol=2e-3):
        v[8] = durs[j]; v[9] = kfs[j][9]; j += 1
    rest = durs[j:]
    if not all(is_vowel(k) for k in kfs[j:]): raise ValueError("tail is not vowel")
    if len(rest) == 2: v[10], v[11] = rest
    elif len(rest) == 1: v[11] = rest[0]
    else: raise ValueError("bad tail %s" % rest)
    v[12] = glide; v[13] = burst["gain"] if burst else 0.0
    return v

# ------------------------------------------------------------------ vector -> gesture (the template)
def clean(v):
    """clip a predicted vector into the renderer's legal space; tiny durations become 0."""
    v = np.array(v, float)
    v[0] = np.clip(v[0], 0.0, 1.0); v[1] = np.clip(v[1], 0.0, 2.0); v[2] = np.clip(v[2], 0.0, 0.8)
    v[3] = np.clip(v[3], 0.25, 0.95); v[4] = np.clip(v[4], 0.0, 1.0)
    for i in (5, 6, 7, 8, 10):
        v[i] = 0.0 if v[i] < 0.008 else float(v[i])
    v[9] = np.clip(v[9], 0.0, 2.0); v[11] = max(0.2, float(v[11])); v[12] = np.clip(v[12], 0.02, 0.7)
    v[13] = 0.0 if v[13] < 3.0 else float(v[13])
    v[14] = 1.0 if v[14] > 0.5 else 0.0; v[15] = 1.0 if v[15] > 0.5 else 0.0
    if v[14] and v[15]: v[15] = 0.0
    return v

def to_gesture(v):
    knots = KI if v[14] else (AH4 if v[15] else AH)
    C = KF(knots, v[0], v[1], v[2], v[3], v[4])
    kfs, durs = [], []
    if v[5] > 0: kfs.append(V13); durs.append(v[5])
    if v[6] > 0: kfs.append(C); durs.append(v[6])
    if v[7] > 0: kfs.append(C); durs.append(v[7])
    if v[8] > 0:
        gap = KF(AH, v[0] if v[9] < 2.0 else 0.65, v[9], 0.0, 0.6, 0.0)
        kfs.append(gap); durs.append(v[8])
    if v[10] > 0: kfs.append(V13); durs.append(v[10])
    kfs.append(V13); durs.append(v[11])
    g = {"keyframes": [np.asarray(k, float) for k in kfs], "durations": [float(d) for d in durs],
         "f0_knots": [F0, F0, F0 * 0.93], "tenseness_knots": [0.6, 0.6, 0.55], "glide": float(v[12])}
    if v[13] > 0: g["burst"] = {"gain": float(v[13]), "tau_s": 0.003}
    return g

def render(g, ports=False):
    return mouth2.say_gesture(g, seed=0, backend=BK, return_ports=ports)

def wav_write(path, y):
    w = wave.open(path, "wb"); w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((np.clip(np.asarray(y, float), -1, 1) * 32767).astype(np.int16).tobytes()); w.close()

# ------------------------------------------------------------------ the family checkers, adapted
def judge(syl, v, g, y, lipnose):
    """(signature_ok, fails, measured-brief) using the SAME checker that verified the hand-made syllable."""
    fam = VERIFIED[syl][6]
    d_pre, d_cons, d_trans, d_gap, d_bridge, d_vow, glide = v[5], v[6], v[7], v[8], v[10], v[11], v[12]
    t_rel = d_pre + d_cons + d_trans
    Ttot = sum(g["durations"])
    if fam == "lips":
        M = lips.measure(y, g, syl, ports=lipnose if syl == "ma" else None)
        ok, fails = lips.check(syl, M)
        brief = lips.brief(syl, M)
        return ok, fails, brief
    if fam == "tip":
        kind = {"stop": "stop_u" if d_gap > 0 else "stop_v", "nasal": "nasal", "approximant": "approx",
                "fricative": "fric", "tap": "tap"}[VERIFIED[syl][3]]
        P = {"kind": kind, "c_pos": v[0], "d_close": d_cons, "d_tr": d_trans, "d_gap": d_gap, "d_pre": d_pre}
        if kind == "tap":
            win = dict(pre=(0.02, max(0.03, d_pre - 0.005)), cons=(d_pre, d_pre + d_cons), t_rel=t_rel)
        else:
            win = dict(cons=(0.01, max(0.02, d_pre + d_cons - 0.005)), t_rel=t_rel)
        if d_gap > 0:
            win["gap"] = (t_rel + 0.015, t_rel + d_gap); win["t_onset"] = t_rel + d_gap
        win["vowel"] = (Ttot - 0.15, Ttot - 0.02)
        lip, nose = lipnose if lipnose else (None, None)
        M = tip.measure(y, lip, nose, win, P)
        ok, why = tip.verdict(syl, M, P)
        fails = [w for w in why if w.startswith("FAIL")]
        brief = "; ".join(why)
        return ok, fails, brief
    if fam == "back":
        P = {"c_pos": v[0]}
        if d_gap > 0: P["d_gap"] = d_gap
        tl = {"t_rel": t_rel, "t_voice": t_rel + d_gap}
        M = back.measure(syl, y, tl, P)
        ok, fails = back.check(syl, M)
        c, b = M["cons"], M["burst"]
        brief = "cons %d ms lvl %.1f cen %d hnr %.1f | burst %.1f dB jump %.1f cen %d | vowel %s" % (
            c["ms"], c["level_db"], c["centroid"], c["hnr"], b["peak_db_re_vowel"], b["jump_db_within_20ms"], b["centroid_20ms"], M["vowel"]["F"])
        return ok, fails, brief
    # glottal
    if syl == "a":
        p = {"dur": d_vow, "ten": v[3]}
        if d_cons > 0 or d_pre > 0:                # the vowel alone must be a vowel alone
            return False, ["FAIL predicted a consonant for the bare vowel"], "d_pre %.3f d_cons %.3f" % (d_pre, d_cons)
        ok, m = glottal.check_a(y, p, g)
    elif syl == "ha":
        ok, m = glottal.check_ha(y, {"d1": d_pre + d_cons, "d2": d_trans}, g)
    elif syl == "ya":
        ok, m = glottal.check_ya(y, {"d1": d_pre + d_cons, "d2": d_trans, "d3": d_bridge + d_vow, "glide": glide}, g)
    elif syl == "cha":
        ok, m = glottal.check_cha(y, {"d1": d_pre + d_cons, "d2": d_trans}, g)
    elif syl == "aya":
        if d_pre < 0.12:
            return False, ["FAIL no vowel before the glottal stop (d_pre %.3f)" % d_pre], "d_pre %.3f" % d_pre
        ok, m = glottal.check_aya(y, {"d1": d_pre, "d2": d_cons + d_trans + d_gap, "d3": d_bridge + d_vow, "glide": glide}, g)
    slim = {k: m[k] for k in m if k not in ("env20_db", "traj_F1F2F3", "exp")}
    return bool(ok), ([] if ok else ["FAIL " + m.get("exp", "")]), json.dumps(slim, default=float)

def render_and_judge(syl, v):
    v = clean(v); g = to_gesture(v)
    y = render(g)
    if y is None: return None, False, ["render returned None"], ""
    lipnose = render(g, ports=True) if VERIFIED[syl][4] else None
    try:
        ok, fails, brief = judge(syl, v, g, y, lipnose)
    except Exception as e:
        ok, fails, brief = False, ["measure error: %s: %s" % (type(e).__name__, e)], traceback.format_exc()[-400:]
    return y, ok, fails, brief

# ------------------------------------------------------------------ inputs
def x_of(syl, letter_known=True):
    _, _, place, manner, nasal, voiced, _ = VERIFIED[syl]
    x = np.zeros(len(SYLS) + len(PLACES) + len(MANNERS) + 2)
    if letter_known: x[SYLS.index(syl)] = 1
    o = len(SYLS); x[o + PLACES.index(place)] = 1
    o += len(PLACES); x[o + MANNERS.index(manner)] = 1
    o += len(MANNERS); x[o] = nasal; x[o + 1] = voiced
    return x

def xc_of(syl):
    """class facts only: place + manner + nasal + voiced (13 dims), no letter."""
    return x_of(syl, letter_known=False)[len(SYLS):]

def ridge_fit(train, Y, lam=0.1):
    X = np.stack([np.append(xc_of(s), 1.0) for s in train]); Yt = np.stack([Y[s] for s in train])
    W = np.linalg.solve(X.T @ X + lam * np.eye(X.shape[1]), X.T @ Yt)
    return {"W": W}

def ridge_predict(model, syl):
    return np.append(xc_of(syl), 1.0) @ model["W"]

def class_dist(a, b):
    A, B = VERIFIED[a], VERIFIED[b]
    return 2 * (A[2] != B[2]) + 2 * (A[3] != B[3]) + 1 * (A[4] != B[4]) + 1 * (A[5] != B[5])

def nn_predict(syl, train, Y):
    d = {s: class_dist(syl, s) for s in train}
    m = min(d.values()); near = [s for s in train if d[s] == m]
    return np.mean([Y[s] for s in near], axis=0), near, m

# ------------------------------------------------------------------ the small MLP (numpy)
class MLP:
    def __init__(self, nin, nh, nout, seed):
        r = np.random.RandomState(seed)
        self.W1 = r.randn(nin, nh) * 0.3 / np.sqrt(nin); self.b1 = np.zeros(nh)
        self.W2 = r.randn(nh, nout) * 0.3 / np.sqrt(nh); self.b2 = np.zeros(nout)
    def fwd(self, X):
        self.H = np.tanh(X @ self.W1 + self.b1); return self.H @ self.W2 + self.b2
    def fit(self, X, Z, epochs=3000, lr=0.01, wd=1e-3):
        ps = [self.W1, self.b1, self.W2, self.b2]; m = [np.zeros_like(p) for p in ps]; s = [np.zeros_like(p) for p in ps]
        for t in range(1, epochs + 1):
            out = self.fwd(X); err = out - Z
            gW2 = self.H.T @ err / len(X) + wd * self.W2; gb2 = err.mean(0)
            dH = (err @ self.W2.T) * (1 - self.H ** 2)
            gW1 = X.T @ dH / len(X) + wd * self.W1; gb1 = dH.mean(0)
            for i, gp in enumerate((gW1, gb1, gW2, gb2)):
                m[i] = 0.9 * m[i] + 0.1 * gp; s[i] = 0.999 * s[i] + 0.001 * gp * gp
                ps[i] -= lr * (m[i] / (1 - 0.9 ** t)) / (np.sqrt(s[i] / (1 - 0.999 ** t)) + 1e-8)
        return float(np.mean((self.fwd(X) - Z) ** 2))

def fit_ensemble(train, Y, seeds=(0, 1, 2, 3, 4), class_only=False):
    X = np.stack([xc_of(s) if class_only else x_of(s) for s in train]); Yt = np.stack([Y[s] for s in train])
    mu, sd = Yt.mean(0), Yt.std(0); sd = np.where(sd < 1e-6, 1.0, sd)
    Z = (Yt - mu) / sd
    nets = []
    for sd_ in seeds:
        net = MLP(X.shape[1], 24, ND, sd_); net.fit(X, Z); nets.append(net)
    return {"nets": nets, "mu": mu, "sd": sd, "class_only": class_only}

def mlp_predict(model, syl, letter_known=False):
    x = (xc_of(syl) if model["class_only"] else x_of(syl, letter_known))[None, :]
    z = np.mean([n.fwd(x)[0] for n in model["nets"]], axis=0)
    return z * model["sd"] + model["mu"]

def md5(path):
    return hashlib.md5(open(path, "rb").read()).hexdigest()

# ------------------------------------------------------------------ main
def main():
    t00 = time.time()
    print("teach.py: mouth2 adult %.2f cm, N=%d, BLOCK_S=%s, backend %s" % (mouth2._L_CHILD, mouth2.N_MAIN, T.BLOCK_S, BK), flush=True)
    # 1. dataset
    Y = {}; rows = []
    for s in SYLS:
        kfs, durs, glide, burst = load_gesture(s)
        v = to_vector(kfs, durs, glide, burst); Y[s] = v
        letter, heb, place, manner, nasal, voiced, fam = VERIFIED[s]
        rows.append({"syl": s, "letter": letter, "hebrew": heb, "family_script": fam,
                     "input": {"place": place, "manner": manner, "nasal": nasal, "voiced": voiced},
                     "target": [round(float(x), 4) for x in v],
                     "source_wav_md5": md5(os.path.join(SCHOOL, "ERAN-%s.wav" % s))})
    ds = {"what": "ERAN mouth school dataset: LETTER (+ place/manner/nasal/voiced) -> gesture vector for mouth2.say_gesture",
          "feature_order": FEATURES, "feature_doc": __doc__.split("FEATURE ORDER")[1],
          "input_encoding": "one-hot letter (%d) + one-hot place %s + one-hot manner %s + nasal + voiced" % (len(SYLS), PLACES, MANNERS),
          "vowel_knots_shared": AH, "f0_knots": [F0, F0, F0 * 0.93], "tenseness_knots": [0.6, 0.6, 0.55],
          "mouth": "eran2:~/mouth-v2/mouth2.py adult 17.60 cm backend c seed 0", "n": len(rows), "rows": rows,
          "written_by": "claude-cli-MORE teach.py 2026-09-03"}
    json.dump(ds, open(os.path.join(SCHOOL, "dataset.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("dataset.json: %d rows x %d dims" % (len(rows), ND), flush=True)

    # 2. template fidelity: does vector -> gesture -> render reproduce the verified wav and pass its own checker?
    selfcheck = {}
    for s in SYLS:
        y, ok, fails, brief = render_and_judge(s, Y[s])
        ref = np.frombuffer(open(os.path.join(SCHOOL, "ERAN-%s.wav" % s), "rb").read()[44:], np.int16).astype(float) / 32767
        n = min(len(ref), len(y)); diff = float(np.max(np.abs(ref[:n] - y[:n]))) if n else 9.0
        selfcheck[s] = {"signature_ok": ok, "fails": fails, "len_ref": len(ref), "len_new": len(y), "max_abs_diff": round(diff, 4)}
        print("  self %-4s ok=%-5s diff=%.4f len %d/%d %s" % (s, ok, diff, len(ref), len(y), fails), flush=True)
    json.dump(selfcheck, open(os.path.join(LOO, "selfcheck.json"), "w"), indent=1, default=float)

    # 3. leave-one-syllable-out, four predictors
    MODELS = ["mlp", "mlpc", "ridge", "nn"]
    results = {}
    for s in SYLS:
        train = [t for t in SYLS if t != s]
        t0 = time.time()
        preds = {}
        preds["mlp"] = mlp_predict(fit_ensemble(train, Y), s, letter_known=False)
        preds["mlpc"] = mlp_predict(fit_ensemble(train, Y, class_only=True), s)
        preds["ridge"] = ridge_predict(ridge_fit(train, Y), s)
        v_nn, near, dmin = nn_predict(s, train, Y); preds["nn"] = v_nn
        r = {"syl": s, "letter": VERIFIED[s][0], "train_s": round(time.time() - t0, 1), "nn_neighbours": near, "nn_dist": dmin}
        for tag in MODELS:
            v = preds[tag]
            y, ok, fails, brief = render_and_judge(s, v)
            path = os.path.join(LOO, "ERAN-%s-loo-%s.wav" % (s, tag))
            if y is not None: wav_write(path, y)
            r[tag] = {"vector": [round(float(x), 4) for x in clean(v)], "signature_ok": bool(ok), "fails": fails,
                      "brief": brief[:600], "wav": path if y is not None else None,
                      "vec_err_l2": round(float(np.linalg.norm(clean(v) - Y[s])), 4)}
        results[s] = r
        print("LOO %-4s " % s + " ".join("%s=%-5s" % (t, r[t]["signature_ok"]) for t in MODELS) + " (nn<-%s d=%d) ridge_fails=%s" % (near, dmin, r["ridge"]["fails"][:3]), flush=True)
    passes = {t: sum(results[s][t]["signature_ok"] for s in SYLS) for t in MODELS}
    n_mlp, n_nn = passes["mlp"], passes["nn"]
    summary = {"n": len(SYLS), "loo_pass": passes, "loo_mlp_pass": n_mlp, "loo_nn_pass": n_nn,
               "selfcheck_pass": sum(selfcheck[s]["signature_ok"] for s in SYLS),
               "models": {"mlp": "numpy MLP 34->24(tanh)->16 on one-hot letter + class facts; Adam 3000 epochs, wd 1e-3, 5-seed ensemble; the held-out letter's one-hot is ZERO at test",
                          "mlpc": "same MLP on the 13 class facts only (place/manner/nasal/voiced), no letter",
                          "ridge": "additive linear model (ridge lam 0.1) on the 13 class facts: gesture = place effect + manner effect + nasal + voiced + bias",
                          "nn": "nearest neighbour in class space (place 2, manner 2, nasal 1, voiced 1); ties averaged"},
               "per_syllable": results, "selfcheck": selfcheck, "seconds": round(time.time() - t00, 1)}
    json.dump(summary, open(os.path.join(LOO, "loo-results.json"), "w", encoding="utf-8"), indent=1, default=float, ensure_ascii=False)
    print("LEAVE-ONE-OUT: " + "  ".join("%s %d/%d" % (t, passes[t], len(SYLS)) for t in MODELS) + "  selfcheck %d/%d" % (summary["selfcheck_pass"], len(SYLS)), flush=True)

    # 4. the models on all 21
    model = fit_ensemble(SYLS, Y); modelc = fit_ensemble(SYLS, Y, class_only=True); ridge = ridge_fit(SYLS, Y)
    np.savez(os.path.join(SCHOOL, "eran-mouth-v0.npz"),
             feature_order=np.array(FEATURES), syllables=np.array(SYLS), places=np.array(PLACES), manners=np.array(MANNERS),
             input_doc=np.array(ds["input_encoding"]), mu=model["mu"], sd=model["sd"],
             mlp_W1=np.stack([n.W1 for n in model["nets"]]), mlp_b1=np.stack([n.b1 for n in model["nets"]]),
             mlp_W2=np.stack([n.W2 for n in model["nets"]]), mlp_b2=np.stack([n.b2 for n in model["nets"]]),
             mlpc_W1=np.stack([n.W1 for n in modelc["nets"]]), mlpc_b1=np.stack([n.b1 for n in modelc["nets"]]),
             mlpc_W2=np.stack([n.W2 for n in modelc["nets"]]), mlpc_b2=np.stack([n.b2 for n in modelc["nets"]]),
             ridge_W=ridge["W"], nn_table=np.stack([Y[s] for s in SYLS]),
             loo_pass=np.array([passes[t] for t in MODELS]), loo_models=np.array(MODELS))
    # sanity: the full model reproduces its own training letters?
    full = {}
    for s in SYLS:
        y, ok, fails, brief = render_and_judge(s, mlp_predict(model, s, letter_known=True))
        full[s] = bool(ok)
    summary["full_model_train_pass"] = sum(full.values()); summary["full_model_per_syl"] = full
    json.dump(summary, open(os.path.join(LOO, "loo-results.json"), "w", encoding="utf-8"), indent=1, default=float, ensure_ascii=False)
    print("full model (letter known) reproduces %d/%d of its own lessons" % (sum(full.values()), len(SYLS)))
    print("done in %.1f s" % (time.time() - t00))

if __name__ == "__main__":
    main()
