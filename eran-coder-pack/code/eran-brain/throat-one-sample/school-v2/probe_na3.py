#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""probe_na3.py -- the TONGUE BODY. Iddo (17:58): all three fast-release candidates still sound like ma.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

What the ear uses for nun vs mem before /a/ (and what the measurements say):
  mem:  F2 RISES from ~1000-1100 to the vowel (lips open, tongue body already in /a/).
  nun:  F2 starts HIGH (alveolar locus ~1600-1900 Hz for a man) and FALLS to the vowel: the tongue
        tip closes while the tongue BODY sits fronter than /a/, then the body relaxes into /a/.
  The murmurs differ too (mem zero ~600-800 Hz, nun higher) but this mouth's nasal murmur is a
  200 Hz hum with nothing above 1 kHz (measured on the PC), so the murmur cue is not available here.
Probe 1 (place) gave F2 ~1080 = ma; probe 2 (fast release) gave F2 flat ~1250 = still ma to his ear;
slow release gave 2500 = nya. Missing piece: the tongue body. So: closure keyframe with knots blended
AH -> I (log2-areas) by w, tip closure at c_pos, then the vowel; the body's return makes the fall.

Runs on eran2:  python3 probe_na3.py
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

# custom tongue-body postures: AH -> I blends in log2-area space
AH = np.array(G.AH, float); KI = np.array(G.KI, float)
BLENDS = {}
for w in (0.2, 0.35, 0.5, 0.7):
    BLENDS["AI%02d" % int(w * 100)] = ((1 - w) * AH + w * KI).tolist()
_orig_knots_of = G.knots_of
G.knots_of = lambda name: BLENDS[name] if name in BLENDS else _orig_knots_of(name)
G.DECISIONS["knots"] = tuple(G.DECISIONS["knots"]) + tuple(BLENDS)

def row(syl, spec, label):
    ok, fails, brief, y = R.judge(syl, spec)
    if y is None:
        print("  %-40s RENDER FAIL %s" % (label, fails)); return None
    tl = G.timeline(spec); tr = tl["t_rel"]
    Fs = [F_at(y, tr + d) for d in (0.010, 0.020, 0.040, 0.080)]
    f2 = [f[1] for f in Fs]
    print("  %-40s ok=%-5s F2 @+10 %5s @+20 %5s @+40 %5s @+80 %5s | F1 @+10 %4s F3 @+10 %5s  %s" % (
        label, ok, f2[0], f2[1], f2[2], f2[3], Fs[0][0], Fs[0][2], "" if ok else fails[:2]))
    return dict(label=label, spec=spec, ok=ok, fails=fails, F2=f2)

base = dict(R.BASE_0902["na"])
out = []
print("reference:")
out.append(row("ma", dict(R.BASE_0902["ma"]), "ma 0.97"))
out.append(row("na", dict(base, c_pos=0.86, glide=0.05, d_trans=0.005), "cand-A (rejected)"))
print("tongue body x place x release:")
for kn in ("AI20", "AI35", "AI50", "AI70"):
    for cp in (0.86, 0.90):
        for glide, dtr in ((0.15, 0.0), (0.35, 0.02), (0.5, 0.02)):
            s = dict(base); s.update(knots=kn, c_pos=cp, glide=glide, d_trans=dtr)
            r = row("na", s, "na %s %.2f glide%.2f dtr%.3f" % (kn, cp, glide, dtr))
            if r: out.append(r)
print("plus a small tongue-tip tick at the release (burst gain 3):")
for kn in ("AI35", "AI50"):
    s = dict(base); s.update(knots=kn, c_pos=0.88, glide=0.35, d_trans=0.02, burst=1, gain=3.0)
    r = row("na", s, "na %s 0.88 glide0.35 burst3" % kn)
    if r: out.append(r)
json.dump([r for r in out if r], open("probe_na3.json", "w"), indent=1)
print("wrote probe_na3.json")
