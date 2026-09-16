#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gesture.py -- the SPEC of a syllable: discrete DECISIONS first, then AMOUNTS; spec -> mouth2 gesture.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

claude-cli-MOREH, 2026-09-03, Iddo's order 09:19 ("סוכן שלך ... שילמד איך מפעילים את הפה ועושים
הברות והוא יאמן את ערן"). This is the representation the 09-02 diagnosis asked for: a regressor
averaged c_area 0 and 0.15 into a mouth that neither seals nor hisses. Here a syllable is
   DECISIONS  knots | constr | nasal | voice | release | burst | pre        (classes)
   AMOUNTS    c_pos c_area velum ten voi d_pre d_cons d_trans d_gap gap_pos gap_area
              gap_voi gap_ten d_bridge d_vowel glide gain f0                 (numbers, given the classes)
and only the AMOUNTS that the DECISIONS make meaningful are read by to_gesture().
Same file on PC (eran-brain/throat-one-sample/school-v2) and eran2 (~/throat-one-sample/school-v2).
"""
import os, sys
import numpy as np

sys.path.insert(0, os.path.expanduser("~/mouth-v2"))
try:
    import mouth2
    KF = mouth2.keyframe
    KI = [float(v) for v in mouth2.vowel_knots("i")]
    KU = [float(v) for v in mouth2.vowel_knots("u")]
except Exception:            # the PC has no mouth; the spec grammar still works there
    mouth2 = None
    def KF(knots8, c_pos=0.65, c_area=2.0, velum=0.0, tenseness=0.6, voicing=1.0):
        return np.concatenate([np.asarray(knots8, float), [c_pos, c_area, velum, tenseness, voicing]])
    KI = KU = None

AH = [-0.6013, -0.0092, -0.6310, -1.4002, 1.6041, -1.8558, 1.8504, 1.9330]
AH4 = list(AH); AH4[3] = -0.9
SR = 16000
BK = "c"

DECISIONS = {
    "knots":   ("AH", "I", "AH4", "U"),
    "constr":  ("seal", "narrow", "wide", "none"),   # c_area: 0 | 0.10-0.25 | 0.3-0.6 | 2.0
    "nasal":   (0, 1),                                # velum 0 | >= 0.5
    "voice":   ("on", "part", "off"),                 # consonant voicing 1 | 0.1-0.5 | 0
    "release": ("plain", "gap", "fric", "none"),      # what follows the hold
    "burst":   (0, 1),                                # C-backend burst dial
    "pre":     (0, 1),                                # a vowel BEFORE the consonant (tap, aya)
}
AMOUNTS = ["c_pos", "c_area", "velum", "ten", "voi", "d_pre", "d_cons", "d_trans", "d_gap", "gap_pos",
           "gap_area", "gap_voi", "gap_ten", "d_bridge", "d_vowel", "glide", "gain", "f0", "trans_voi"]

# which amounts a decision makes meaningful (everything else is ignored by to_gesture)
def live_amounts(spec):
    a = {"d_vowel", "glide", "f0"}
    if spec["constr"] != "none" or spec["voice"] != "on" or spec["knots"] != "AH":
        a |= {"c_pos", "c_area", "ten", "voi", "d_cons", "d_trans", "trans_voi"}
    if spec["constr"] == "seal":  a.discard("c_area")
    if spec["nasal"]:             a.add("velum")
    if spec["release"] == "gap":  a |= {"d_gap", "gap_pos", "gap_area", "gap_voi", "gap_ten", "d_bridge"}
    if spec["release"] == "fric": a |= {"d_gap", "gap_pos", "gap_area", "gap_voi", "gap_ten"}
    if spec["burst"]:             a.add("gain")
    if spec["pre"]:               a.add("d_pre")
    return a

def knots_of(name):
    return {"AH": AH, "I": KI, "AH4": AH4, "U": KU}[name]

def c_area_of(spec):
    return 0.0 if spec["constr"] == "seal" else (2.0 if spec["constr"] == "none" else float(spec["c_area"]))

def voi_of(spec):
    return {"on": 1.0, "off": 0.0}.get(spec["voice"], float(spec["voi"]))

def vowel_kf(): return KF(AH)

def to_gesture(spec):
    """spec -> mouth2 gesture dict. Only the amounts the decisions make live are read."""
    s = spec
    V = vowel_kf()
    f0 = float(s.get("f0", 105.0))
    g = {"f0_knots": [f0, f0, f0 * 0.93], "tenseness_knots": [0.6, 0.6, 0.55], "glide": float(s["glide"])}
    kfs, durs = [], []
    bare_vowel = (s["constr"] == "none" and s["voice"] == "on" and s["knots"] == "AH" and not s["pre"]
                  and s["release"] == "none")
    if s["pre"]:
        kfs.append(V); durs.append(float(s["d_pre"]))
    if not bare_vowel:
        C = KF(knots_of(s["knots"]), float(s["c_pos"]), c_area_of(s), float(s["velum"]) if s["nasal"] else 0.0,
               float(s["ten"]), voi_of(s))
        kfs.append(C); durs.append(float(s["d_cons"]))
        if float(s.get("d_trans", 0)) > 0:
            C2 = np.array(C, float)
            if s.get("trans_voi") is not None: C2[12] = float(s["trans_voi"])   # devoicing before the release
            kfs.append(C2); durs.append(float(s["d_trans"]))
    if s["release"] in ("gap", "fric"):
        G = KF(AH, float(s["gap_pos"]), float(s["gap_area"]), 0.0, float(s["gap_ten"]), float(s["gap_voi"]))
        kfs.append(G); durs.append(float(s["d_gap"]))
        if s["release"] == "gap" and float(s.get("d_bridge", 0)) > 0:
            kfs.append(V); durs.append(float(s["d_bridge"]))
    kfs.append(V); durs.append(float(s["d_vowel"]))
    g["keyframes"] = [np.asarray(k, float) for k in kfs]; g["durations"] = durs
    if s["burst"]:
        g["burst"] = {"gain": float(s["gain"]), "tau_s": 0.003}
    return g

def timeline(spec):
    """the moments the rulers need (seconds): t_c0 hold start, t_rel release, t_on voicing onset, total."""
    s = spec
    t = float(s["d_pre"]) if s["pre"] else 0.0
    t_c0 = t
    if not (s["constr"] == "none" and s["voice"] == "on" and s["knots"] == "AH" and not s["pre"] and s["release"] == "none"):
        t += float(s["d_cons"]) + (float(s["d_trans"]) if float(s.get("d_trans", 0)) > 0 else 0.0)
    t_rel = t
    if s["release"] in ("gap", "fric"):
        t += float(s["d_gap"])
    t_on = t
    total = t + (float(s["d_bridge"]) if s["release"] == "gap" and float(s.get("d_bridge", 0)) > 0 else 0.0) + float(s["d_vowel"])
    return {"t_c0": t_c0, "t_rel": t_rel, "t_on": t_on, "total": total}

def render(spec, seed=0, ports=False):
    g = to_gesture(spec)
    return mouth2.say_gesture(g, seed=seed, backend=BK, return_ports=ports)

def readable(spec):
    g = to_gesture(spec)
    return {"keyframes": [[round(float(v), 4) for v in k] for k in g["keyframes"]],
            "keyframe_dims": "k1..k8 log2-area, c_pos, c_area, velum, tenseness, voicing",
            "durations": [round(d, 4) for d in g["durations"]], "f0_knots": g["f0_knots"],
            "tenseness_knots": g["tenseness_knots"], "glide": g["glide"], "burst": g.get("burst"),
            "backend": BK, "seed": 0}

def clean(spec, report=False):
    """clip a (predicted) spec into the mouth's legal space.

    MOREH-8 (code revision 2026-09-06): the rewrites are RECORDED. An out-of-vocabulary decision used to
    become the first class ("AH", "seal", "plain") silently, so a malformed prediction turned into a
    plausible sealed AH syllable that the judge then scored as the model's real answer. With report=True
    this returns (spec, coercions) and the caller writes them into the lesson / LOO JSON."""
    s = dict(spec); coercions = []
    for k, v in DECISIONS.items():
        if s.get(k) not in v:
            coercions.append({"key": k, "from": s.get(k), "to": v[0], "why": "not in DECISIONS[%r]" % k})
            s[k] = v[0]
    lo_hi = {"c_pos": (0.30, 1.0), "c_area": (0.0, 2.0), "velum": (0.0, 0.8), "ten": (0.25, 0.95), "voi": (0.0, 1.0),
             "d_pre": (0.0, 0.5), "d_cons": (0.02, 0.4), "d_trans": (0.0, 0.05), "d_gap": (0.01, 0.15),
             "gap_pos": (0.30, 1.0), "gap_area": (0.0, 2.0), "gap_voi": (0.0, 1.0), "gap_ten": (0.25, 0.95),
             "d_bridge": (0.0, 0.08), "d_vowel": (0.2, 0.7), "glide": (0.02, 0.7), "gain": (2.0, 16.0), "f0": (90.0, 140.0)}
    for k, (lo, hi) in lo_hi.items():
        s[k] = float(np.clip(float(s.get(k, lo)), lo, hi))
    if s["constr"] == "narrow": s["c_area"] = float(np.clip(s["c_area"], 0.10, 0.25))
    if s["constr"] == "wide":   s["c_area"] = float(np.clip(s["c_area"], 0.30, 0.60))
    if s["nasal"]:              s["velum"] = float(np.clip(s["velum"], 0.5, 0.8))
    if s["voice"] == "part":    s["voi"] = float(np.clip(s["voi"], 0.1, 0.5))
    if s["d_trans"] < 0.005:    s["d_trans"] = 0.0
    if s.get("trans_voi") is not None: s["trans_voi"] = float(np.clip(float(s["trans_voi"]), 0.0, 1.0))
    if s["d_bridge"] < 0.008:   s["d_bridge"] = 0.0
    if s["knots"] in ("I", "U") and KI is None:
        # MOREH-8: a box with no mouth must not pretend to render. This used to silently become "AH",
        # so on the PC `ya` -- the one syllable whose true knots is I -- was judged as a different
        # sound with no record anywhere.
        raise RuntimeError("knots=%r needs mouth2's vowel knots and this box has none (mouth2 is not "
                           "importable here). Run where the mouth lives; refusing to substitute AH."
                           % s["knots"])
    return (s, coercions) if report else s
