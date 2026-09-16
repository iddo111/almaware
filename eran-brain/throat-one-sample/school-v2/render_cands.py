#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""render_cands.py -- render CANDIDATE syllables for Iddo's ruling (the order of teaching: he trains the
teacher, the teacher trains ERAN). Files: candidates/CLAUDE-<syl>-cand-<X>.wav + .json (Label Law).

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

2026-09-03 15:27 Iddo: "קלוד NA אתה אומר MA". probe_na2.py: with a FAST tongue release (glide 0.05)
the closure at 0.84-0.90 gives F2 flat at ~1200-1290 Hz from +5 ms on (his own na: 1414 flat), while
the old na (0.93, glide 0.35) started at ~1050 like ma and the slow release at 0.84-0.90 shot to
~2500 Hz first (a palatal glide, nya). Three candidates go to him; he says which one is נַ.

Runs on eran2:  python3 render_cands.py
"""
import json, os, wave
import numpy as np
import ruler as R
import gesture as G
import locus

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "candidates"); os.makedirs(OUT, exist_ok=True)

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
    "A": dict(c_pos=0.86, glide=0.05, d_trans=0.005),
    "B": dict(c_pos=0.90, glide=0.05, d_trans=0.020),
    "C": dict(c_pos=0.84, glide=0.15, d_trans=0.005),
}
for X, upd in CANDS.items():
    spec = dict(base); spec.update(upd)
    ok, fails, brief, y = R.judge("na", spec)
    tl = G.timeline(spec)
    F2 = [F_at(y, tl["t_rel"] + d)[1] for d in (0.005, 0.010, 0.020, 0.040, 0.080)]
    wp = os.path.join(OUT, "CLAUDE-na-cand-%s.wav" % X)
    write_wav(wp, y)
    json.dump({"speaker": "CLAUDE", "syl": "na", "candidate": X, "spec": G.clean(spec), "ruler_ok": ok,
               "ruler_fails": fails, "F2_after_release_ms_5_10_20_40_80": F2, "brief": brief,
               "why": "Iddo 2026-09-03 15:27 rejected the 0.93/glide0.35 na as ma; candidates differ in place and release speed"},
              open(wp[:-4] + ".json", "w"), indent=1)
    print("cand %s  %s  ok=%s  F2 %s  %s" % (X, upd, ok, F2, fails))
print("wrote", OUT)
