#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""render_cands2.py -- round 2 of na candidates for Iddo: the TONGUE BODY moves (probe_na3.py).

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

Round 1 (A/B/C: place + fast release, F2 flat ~1250) -- Iddo 17:58: "כל השלושה" sound like ma.
Round 2: the closure keyframe fronts the tongue body (knots = AH->I blend in log2-areas) with the tip
sealed at 0.86, then the body relaxes into /a/ -- F2 starts ~1600-1800 and FALLS to the vowel, the
alveolar pattern (mem rises from ~1070). Measured on eran2:
  AI70 0.86 glide0.15: F2 1778 -> 1546 -> 1393 -> 1235     (D)
  AI50 0.86 glide0.15: F2 1588 -> 1431 -> 1382 -> 1235     (E)  (ruler's antiformant window objects; his ear rules)
  D + a small tongue-tip tick at the release (burst gain 3) (F)
Files: candidates/CLAUDE-na-cand-{D,E,F}.wav+json. Runs on eran2.
"""
import json, os, wave
import numpy as np
import ruler as R
import gesture as G
import locus

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "candidates"); os.makedirs(OUT, exist_ok=True)

AH = np.array(G.AH, float); KI = np.array(G.KI, float)
BLENDS = {"AI50": (0.5 * AH + 0.5 * KI).tolist(), "AI70": (0.3 * AH + 0.7 * KI).tolist()}
_orig = G.knots_of
G.knots_of = lambda n: BLENDS[n] if n in BLENDS else _orig(n)
G.DECISIONS["knots"] = tuple(G.DECISIONS["knots"]) + tuple(BLENDS)

def F_at(y, t):
    n = int(0.025 * G.SR); s = int(max(0.0, t - 0.0125) * G.SR)
    fs = [int(round(f)) for f, b in locus.formants(y[s:s + n], G.SR)][:3]
    return fs + [None] * (3 - len(fs))

def write_wav(path, y):
    y = np.asarray(y, float); pk = np.abs(y).max() or 1.0
    y = y / pk * 0.7 if pk > 0.7 else y
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(G.SR)
        w.writeframes((np.clip(y, -1, 1) * 32767).astype("<i2").tobytes())

base = dict(R.BASE_0902["na"])
CANDS = {
    "D": dict(knots="AI70", c_pos=0.86, glide=0.15, d_trans=0.0),
    "E": dict(knots="AI50", c_pos=0.86, glide=0.15, d_trans=0.0),
    "F": dict(knots="AI70", c_pos=0.86, glide=0.15, d_trans=0.0, burst=1, gain=3.0),
}
for X, upd in CANDS.items():
    spec = dict(base); spec.update(upd)
    ok, fails, brief, y = R.judge("na", spec)
    tl = G.timeline(spec)
    F2 = [F_at(y, tl["t_rel"] + d)[1] for d in (0.010, 0.020, 0.040, 0.080)]
    wp = os.path.join(OUT, "CLAUDE-na-cand-%s.wav" % X)
    write_wav(wp, y)
    spec_out = G.clean(spec); spec_out["knots_vector_log2_area"] = BLENDS[spec["knots"]]
    json.dump({"speaker": "CLAUDE", "syl": "na", "candidate": X, "round": 2, "spec": spec_out, "ruler_ok": ok,
               "ruler_fails": fails, "F2_after_release_ms_10_20_40_80": F2, "brief": brief,
               "why": "round 1 (A/B/C) rejected by Iddo 17:58 as ma; round 2 fronts the tongue body during the tip closure"},
              open(wp[:-4] + ".json", "w"), indent=1)
    print("cand %s  %s  ok=%s  F2 %s  %s" % (X, upd, ok, F2, fails))
print("wrote", OUT)
