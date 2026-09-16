#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""probe_na2.py -- place x release-speed for the tongue-tip nasal. F2 read at +5/+10/+20/+40 ms after
the release, so the shape of the transition (flat like Iddo's na, rising like ma, falling like ya) is
visible, not one number.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

probe_na.py showed a cliff: closure at 0.92-0.95 -> F2 onset ~1080 (= ma); closure at 0.78-0.90 ->
F2 onset ~2500 falling to the vowel in 30-40 ms (= a palatal glide). Iddo's own na: F2 1414 flat.
Hypothesis: the release in this mouth passes through a NARROW phase (front-cavity resonance ~2.5 kHz)
for as long as d_trans + glide let it; a real tongue-tip release is ~5-10 ms. Faster release => the
narrow phase is too short to hear => F2 starts near the vowel = na, not nya.

Runs on eran2:  python3 probe_na2.py
"""
import json, sys
import numpy as np
import ruler as R
import gesture as G
import locus

def F_at(y, t):
    n = int(0.025 * G.SR); s = int(max(0.0, t - 0.0125) * G.SR)
    fs = [int(round(f)) for f, b in locus.formants(y[s:s + n], G.SR)][:3]
    return fs + [None] * (3 - len(fs))

def row(syl, spec, label):
    ok, fails, brief, y = R.judge(syl, spec)
    if y is None:
        print("  %-34s RENDER FAIL %s" % (label, fails)); return None
    tl = G.timeline(spec); tr = tl["t_rel"]
    Fs = [F_at(y, tr + d) for d in (0.005, 0.010, 0.020, 0.040, 0.080)]
    f2 = [f[1] for f in Fs]
    print("  %-34s ok=%-5s F2 @+5 %5s @+10 %5s @+20 %5s @+40 %5s @+80 %5s | F3 @+10 %5s  %s" % (
        label, ok, f2[0], f2[1], f2[2], f2[3], f2[4], Fs[1][2], "" if ok else fails[:2]))
    return dict(label=label, spec=spec, ok=ok, fails=fails, F2=f2, y=y)

base = dict(R.BASE_0902["na"])
out = []
print("reference:")
out.append(row("ma", dict(R.BASE_0902["ma"]), "ma 0.97 glide0.35 dtr0.02"))
out.append(row("na", dict(base), "na 0.93 glide0.35 dtr0.02 (REJECTED)"))
print("place x release speed:")
for cp in (0.84, 0.86, 0.88, 0.90):
    for glide in (0.35, 0.15, 0.05):
        for dtr in (0.02, 0.005):
            s = dict(base); s.update(c_pos=cp, glide=glide, d_trans=dtr)
            r = row("na", s, "na %.2f glide%.2f dtr%.3f" % (cp, glide, dtr))
            if r: out.append(r)
json.dump([{k: v for k, v in r.items() if k != "y"} for r in out if r], open("probe_na2.json", "w"), indent=1)
print("wrote probe_na2.json")
