#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ruler.py -- THE verifier of mouth school v2. Not a friendlier ruler: the 09-02 family checkers
(lips.check, tip.verdict, back.check, glottal.check_*) PLUS the three objections the independent
verifiers raised that night, codified (a voiced VOT gap is not voiceless; an affricate must not start
with a voiced blip; qof sits behind kaf). Calibration: on the 24 hand-made 09-02 gestures this ruler
must say exactly what the verifiers said -- 21 pass, tza/ka/qa fail. `python3 ruler.py --calibrate`.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

claude-cli-MOREH 2026-09-03. Runs on eran2 only (the mouth lives there). Nothing is played.
"""
import json, os, sys, traceback
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SCHOOL = os.path.expanduser("~/throat-one-sample/school")
sys.path.insert(0, HERE); sys.path.insert(0, SCHOOL); sys.path.insert(0, os.path.expanduser("~/mouth-v2"))
import gesture as G
import lips, tip, back, glottal            # the 09-02 family rulers, untouched

# letter, hebrew, place, manner, nasal, voiced, family, twin-of
FACTS = {
    "a":   ("alef",   "א", "glottal", "vowel",       0, 1, "glottal", None),
    "aya": ("ayin",   "ע", "glottal", "stop",        0, 0, "glottal", None),
    "ba":  ("bet",    "ב", "lips",    "stop",        0, 1, "lips", None),
    "va":  ("vet",    "ב", "lips",    "fricative",   0, 1, "lips", None),
    "ga":  ("gimel",  "ג", "back",    "stop",        0, 1, "back", None),
    "da":  ("dalet",  "ד", "tip",     "stop",        0, 1, "tip", None),
    "ha":  ("he",     "ה", "glottal", "fricative",   0, 0, "glottal", None),
    "wa":  ("vav",    "ו", "lips",    "approximant", 0, 1, "lips", None),
    "za":  ("zayin",  "ז", "tip",     "fricative",   0, 1, "tip", None),
    "cha": ("chet",   "ח", "back",    "fricative",   0, 0, "glottal", None),
    "ta":  ("tet",    "ט", "tip",     "stop",        0, 0, "tip", None),
    "ya":  ("yod",    "י", "palate",  "approximant", 0, 1, "glottal", None),
    "ka":  ("kaf",    "כ", "back",    "stop",        0, 0, "back", None),
    "kha": ("khaf",   "כ", "back",    "fricative",   0, 0, "back", "cha"),
    "la":  ("lamed",  "ל", "tip",     "approximant", 0, 1, "tip", None),
    "ma":  ("mem",    "מ", "lips",    "nasal",       1, 1, "lips", None),
    "na":  ("nun",    "נ", "tip",     "nasal",       1, 1, "tip", None),
    "sa":  ("samekh", "ס", "tip",     "fricative",   0, 0, "tip", None),
    "pa":  ("pe",     "פ", "lips",    "stop",        0, 0, "lips", None),
    "fa":  ("fe",     "פ", "lips",    "fricative",   0, 0, "lips", None),
    "tza": ("tsadi",  "צ", "tip",     "affricate",   0, 0, "tip", None),
    "qa":  ("qof",    "ק", "back",    "stop",        0, 0, "back", "ka"),
    "ra":  ("resh",   "ר", "tip",     "tap",         0, 1, "tip", None),
    "sha": ("shin",   "ש", "palate",  "fricative",   0, 0, "tip", None),
}
SYLS = list(FACTS)

def _spec(**kw):
    s = {"knots": "AH", "constr": "seal", "nasal": 0, "voice": "on", "release": "plain", "burst": 0, "pre": 0,
         "c_pos": 0.65, "c_area": 2.0, "velum": 0.0, "ten": 0.6, "voi": 1.0, "d_pre": 0.0, "d_cons": 0.09,
         "d_trans": 0.015, "d_gap": 0.04, "gap_pos": 0.65, "gap_area": 2.0, "gap_voi": 0.0, "gap_ten": 0.6,
         "d_bridge": 0.0, "d_vowel": 0.35, "glide": 0.35, "gain": 6.0, "f0": 105.0, "trans_voi": None}
    s.update(kw); return s

# the 24 hand-made gestures of 09-02, as specs (from school/<syl>.json) -- the calibration set
BASE_0902 = {
    "a":   _spec(constr="none", release="none", d_vowel=0.60),
    "aya": _spec(pre=1, d_pre=0.25, constr="none", voice="off", knots="AH4", d_cons=0.09, d_trans=0.0, release="none", d_vowel=0.32, glide=0.02),
    "ba":  _spec(c_pos=0.97, burst=1, gain=9.6, d_cons=0.09),
    "pa":  _spec(c_pos=0.97, burst=1, gain=6.0, d_cons=0.09, release="gap", d_gap=0.04, gap_pos=0.65, gap_area=2.0, gap_voi=0.0, gap_ten=0.6),
    "ma":  _spec(c_pos=0.97, nasal=1, velum=0.75, d_cons=0.15, d_trans=0.02),
    "va":  _spec(constr="narrow", c_pos=0.96, c_area=0.10, voice="part", voi=0.13, ten=0.25, d_cons=0.12),
    "fa":  _spec(constr="narrow", c_pos=0.98, c_area=0.15, voice="off", d_cons=0.12),
    "wa":  _spec(constr="narrow", c_pos=1.00, c_area=0.15, voice="on", d_cons=0.08, d_trans=0.02, glide=0.5),
    "da":  _spec(c_pos=0.95, burst=1, gain=6.0, d_cons=0.08),
    "ta":  _spec(c_pos=0.95, burst=1, gain=6.0, d_cons=0.08, release="gap", d_gap=0.04, gap_pos=0.95, gap_area=0.8, gap_voi=0.0, gap_ten=0.6, d_bridge=0.03),
    "na":  _spec(c_pos=0.93, nasal=1, velum=0.75, d_cons=0.15, d_trans=0.02),
    "la":  _spec(constr="wide", c_pos=0.88, c_area=0.40, d_cons=0.09, d_trans=0.02),
    "sa":  _spec(constr="narrow", c_pos=0.92, c_area=0.12, voice="off", d_cons=0.12),
    "za":  _spec(constr="narrow", c_pos=0.92, c_area=0.12, voice="part", voi=0.30, ten=0.25, d_cons=0.12),
    "sha": _spec(constr="narrow", c_pos=0.80, c_area=0.18, voice="off", d_cons=0.12),
    "ra":  _spec(pre=1, d_pre=0.08, c_pos=0.94, d_cons=0.03, d_trans=0.0, glide=0.5),
    "ga":  _spec(c_pos=0.50, burst=1, gain=6.0, d_cons=0.09),
    "ka":  _spec(c_pos=0.49, burst=1, gain=6.0, d_cons=0.09, release="gap", d_gap=0.04, gap_pos=0.65, gap_area=2.0, gap_voi=0.15, gap_ten=0.25),
    "qa":  _spec(c_pos=0.485, burst=1, gain=4.0, d_cons=0.10, release="gap", d_gap=0.04, gap_pos=0.65, gap_area=2.0, gap_voi=0.15, gap_ten=0.25),
    "kha": _spec(constr="narrow", c_pos=0.51, c_area=0.15, voice="off", d_cons=0.12),
    "cha": _spec(constr="narrow", c_pos=0.51, c_area=0.15, voice="off", d_cons=0.10),
    "ha":  _spec(constr="narrow", c_pos=0.35, c_area=0.15, voice="part", voi=0.2, ten=0.25, d_cons=0.06, d_trans=0.02),
    "ya":  _spec(knots="I", constr="wide", c_pos=0.75, c_area=0.5, d_cons=0.06, d_trans=0.02, d_vowel=0.32, glide=0.5),
    "tza": _spec(c_pos=0.95, burst=1, gain=6.0, d_cons=0.06, d_trans=0.01, release="fric", d_gap=0.08, gap_pos=0.90, gap_area=0.12, gap_voi=0.0, gap_ten=0.6, d_vowel=0.30),
}

# ------------------------------------------------------------------ the rulers
def _basic(y):
    if y is None: return ["render None"]
    y = np.asarray(y, float); f = []
    if np.isnan(y).any(): f.append("NaN")
    if len(y) / G.SR < 0.3 or len(y) / G.SR > 1.5: f.append("duration %.2f s" % (len(y) / G.SR))
    if np.abs(y).max() < 0.006: f.append("silent")
    return f

def _family(syl, spec, g, y, lipnose):
    fam = FACTS[syl][6]; tl = G.timeline(spec); s = spec
    d_cons = float(s["d_cons"]) + (float(s["d_trans"]) if float(s["d_trans"]) > 0 else 0.0)
    if fam == "lips":
        M = lips.measure(y, g, syl, ports=lipnose if syl == "ma" else None)
        ok, fails = lips.check(syl, M)
        return ok, fails, lips.brief(syl, M)
    if fam == "tip":
        manner = FACTS[syl][3]
        kind = {"stop": "stop_u" if s["release"] == "gap" else "stop_v", "nasal": "nasal", "approximant": "approx",
                "fricative": "fric", "tap": "tap", "affricate": "affr"}[manner]
        P = {"kind": kind, "c_pos": s["c_pos"], "d_close": float(s["d_cons"]), "d_tr": float(s["d_trans"]),
             "d_gap": float(s["d_gap"]) if s["release"] == "gap" else 0.0, "d_pre": float(s["d_pre"]) if s["pre"] else 0.0,
             "d_fric": float(s["d_gap"]) if s["release"] == "fric" else 0.0}
        if kind == "tap":
            win = dict(pre=(0.02, max(0.03, P["d_pre"] - 0.005)), cons=(P["d_pre"], P["d_pre"] + float(s["d_cons"])), t_rel=tl["t_rel"])
        else:
            win = dict(cons=(0.01, max(0.02, P["d_pre"] + float(s["d_cons"]) - 0.005)), t_rel=tl["t_rel"])
        if kind == "stop_u":
            win["gap"] = (tl["t_rel"] + 0.015, tl["t_on"]); win["t_onset"] = tl["t_on"]
        if kind == "affr":
            win["fric"] = (tl["t_rel"] + 0.35 * P["d_fric"], tl["t_on"]); win["t_vow"] = tl["t_on"]
        win["vowel"] = (tl["total"] - 0.15, tl["total"] - 0.02)
        lip, nose = lipnose if lipnose else (None, None)
        M = tip.measure(y, lip, nose, win, P)
        ok, why = tip.verdict(syl, M, P)
        return ok, [w for w in why if w.startswith("FAIL")], "; ".join(why)
    if fam == "back":
        P = {"c_pos": s["c_pos"]}
        if s["release"] == "gap": P["d_gap"] = float(s["d_gap"])
        M = back.measure(syl, y, {"t_rel": tl["t_rel"], "t_voice": tl["t_on"]}, P)
        ok, fails = back.check(syl, M)
        c, b = M["cons"], M["burst"]
        brief = "cons %d ms lvl %.1f cen %d hnr %.1f | burst %.1f dB jump %.1f cen %d | gap %s | vowel %s" % (
            c["ms"], c["level_db"], c["centroid"], c["hnr"], b["peak_db_re_vowel"], b["jump_db_within_20ms"], b["centroid_20ms"],
            json.dumps(M.get("gap")), M["vowel"]["F"])
        return ok, fails, brief
    # glottal family
    if syl == "a":
        if s["constr"] != "none" or s["pre"] or s["release"] != "none":
            return False, ["FAIL a consonant was predicted for the bare vowel"], ""
        ok, m = glottal.check_a(y, {"dur": float(s["d_vowel"]), "ten": float(s["ten"])}, g)
    elif syl == "ha":
        ok, m = glottal.check_ha(y, {"d1": float(s["d_cons"]), "d2": float(s["d_trans"])}, g)
    elif syl == "ya":
        ok, m = glottal.check_ya(y, {"d1": float(s["d_cons"]), "d2": float(s["d_trans"]), "d3": float(s["d_vowel"]), "glide": float(s["glide"])}, g)
    elif syl == "cha":
        ok, m = glottal.check_cha(y, {"d1": float(s["d_cons"]), "d2": float(s["d_trans"])}, g)
    elif syl == "aya":
        if not s["pre"] or float(s["d_pre"]) < 0.12:
            return False, ["FAIL no vowel before the glottal stop"], ""
        ok, m = glottal.check_aya(y, {"d1": float(s["d_pre"]), "d2": d_cons + (float(s["d_gap"]) if s["release"] in ("gap", "fric") else 0.0),
                                      "d3": float(s["d_vowel"]), "glide": float(s["glide"])}, g)
    else:
        raise ValueError(syl)
    slim = {k: m[k] for k in m if k not in ("env20_db", "traj_F1F2F3", "exp")}
    return bool(ok), ([] if ok else ["FAIL " + m.get("exp", "")]), json.dumps(slim, default=float)

sys.path.insert(0, os.path.join(HERE, "verifiers"))
import verify_back as VB                     # VERIFIER-BACK's scratchpad ruler of 09-02, verbatim

def _gap_verifier_style(y, start=0.010):
    """VERIFIER-BACK's own procedure (verify_back.analyse, stop_voiceless branch): release from the 5 ms
    envelope, voice onset = first 30 ms frame after it with ACF r > 0.6, f0 80-200, level > -12 dB;
    gap = [release+10 ms, voice onset]; its ACF HNR. ka/qa failed at +1..+3 dB; pa (LIPS-VERIFIER) held at -5."""
    sr = 16000; y = np.asarray(y, float); N = len(y)
    t, e = VB.env(y, sr)
    vow = y[N - int(0.23 * sr): N - int(0.03 * sr)]; vref = VB.rms(vow)
    edb = np.array([VB.db(v, vref) for v in e])
    rel_i = None
    for i in range(2, len(edb) - 4):
        if edb[i] > -10 and edb[max(0, i - 3):i].max() < -15:
            rel_i = i; break
    if rel_i is None: return None, None, None
    rel_t = rel_i * 0.005
    hop = int(0.005 * sr); w20 = int(0.03 * sr); vo = None
    for s_ in range(0, N - w20, hop):
        tt = s_ / sr
        if tt < rel_t + 0.005: continue
        seg = y[s_:s_ + w20]; f0, r = VB.acf_peak(seg, sr); lv = VB.db(VB.rms(seg), vref)
        if r > 0.6 and 80 < f0 < 200 and lv > -12: vo = tt; break
    if vo is None: return rel_t, None, None
    g0 = int((rel_t + start) * sr); g1 = int(vo * sr); gap = y[g0:g1]
    if len(gap) <= int(0.01 * sr): return rel_t, vo, None
    f0g, hg = VB.hnr(gap, sr)
    return rel_t, vo, hg

def _strict(syl, spec, y):
    """The independent verifiers' objections of 09-02, as measurements (their own rulers)."""
    f = []; tl = G.timeline(spec); s = spec
    if s["release"] == "gap":
        rel_t, vo, hg = _gap_verifier_style(y, start=0.025 if FACTS[syl][6] == "lips" else 0.010)
        if hg is not None and hg >= 0:
            f.append("STRICT gap is voiced: VERIFIER-BACK procedure HNR %.1f >= 0 (ka/qa failed at +1..+3; pa held at -5)" % hg)
        if vo is not None and (vo - tl["t_on"]) > 0.08:
            f.append("STRICT voicing onset %d ms after the gap (want <= 80; pa measured 45-78)" % int(1000 * (vo - tl["t_on"])))
    if s["release"] == "fric":
        bl = tip.seg(y, tl["t_rel"] + 0.005, tl["t_rel"] + 0.045)
        h = tip.hnr(bl); lt = tip.band_frac(bl, 0, 500)
        if h >= 0 or lt >= 0.5:
            f.append("STRICT voiced blip after the closure: HNR %.1f, <500 Hz %.2f (VERIFIER-TIP on tza: d-uh-s-a)" % (h, lt))
    if syl == "qa" and float(s["c_pos"]) > 0.49:
        f.append("STRICT qof must sit behind kaf (c_pos %.3f > 0.49)" % s["c_pos"])
    return f

def judge(syl, spec, seed=0):
    """render + family ruler + strict extras. Returns (ok, fails, brief, y).

    MOREH-6 (code revision 2026-09-06): ok is True / False / **None**. None means the render or the
    measurement CRASHED — a broken box, not a bad sound. It used to come back as False, so three of the
    copy floor's 24 "failures" in the 09-03 sitting were KeyError/ValueError, and the published floor
    "copy 2/24" was part crash rate. None is falsy, so `if ok:` callers are unchanged; a caller that
    wants to tell the two apart tests `ok is None`."""
    spec = G.clean(spec)
    try:
        g = G.to_gesture(spec)
        y = G.render(spec, seed=seed)
    except Exception as e:
        return None, ["render error %s: %s" % (type(e).__name__, e)], "", None
    fails = _basic(y)
    if fails: return False, fails, "", y
    lipnose = G.render(spec, seed=seed, ports=True) if FACTS[syl][4] else None
    try:
        ok, ff, brief = _family(syl, spec, g, y, lipnose)
    except Exception as e:
        return None, ["measure error %s: %s" % (type(e).__name__, e)], traceback.format_exc()[-300:], y
    fails = list(ff) + _strict(syl, spec, y)
    return (len(fails) == 0), fails, brief, y

def calibrate(verbose=True):
    """the 09-02 hand-made gestures under THIS ruler. Expected: 21 pass; tza, ka, qa fail."""
    res = {}
    for syl in SYLS:
        ok, fails, brief, y = judge(syl, BASE_0902[syl])
        res[syl] = {"ok": ok, "fails": fails}
        if verbose: print("%-4s %s %s" % (syl, "PASS" if ok else "FAIL", "; ".join(fails)[:200]), flush=True)
    npass = sum(bool(r["ok"]) for r in res.values())          # MOREH-6: ok may be None (an error)
    exp_fail = {"tza", "ka", "qa"}; got_fail = {s for s, r in res.items() if not r["ok"]}
    same = (got_fail == exp_fail)
    if verbose: print("calibration: %d/24 pass; failing %s; SAME AS THE 09-02 VERIFIERS: %s" % (npass, sorted(got_fail), same), flush=True)
    return res, same

if __name__ == "__main__":
    if "--calibrate" in sys.argv:
        calibrate()
