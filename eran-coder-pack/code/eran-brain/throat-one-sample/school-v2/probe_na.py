#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""probe_na.py -- where must the tongue-tip closure sit so that nun is not mem?

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

Iddo, 2026-09-03 15:27, on hear_claude :8859: "קלוד NA אתה אומר MA". Measured on the PC (locus.py):
the teacher's na has F2 at release 1055-1131 Hz, its ma 1004-1081 Hz -- the same cue; Iddo's own
na 1414 Hz vs his ma 1160 Hz. The ruler never looked at F2 at the release, and the na closure sat at
c_pos 0.93, a hair behind the lips (ma 0.97). This probe slides the closure back along the tract and
reads, for each place: the ruler's verdict (nasal checks) + F2 at release (the place cue).

Runs on eran2 (the mouth lives there):  python3 probe_na.py [syl] [--fine]
"""
import json, sys
import numpy as np
import ruler as R
import gesture as G
import locus

syl = [a for a in sys.argv[1:] if not a.startswith("--")]
syl = syl[0] if syl else "na"
fine = "--fine" in sys.argv
base = dict(R.BASE_0902[syl])
places = [0.70, 0.74, 0.78, 0.80, 0.82, 0.84, 0.86, 0.88, 0.90, 0.92, 0.93, 0.95] if not fine else \
         [round(x, 3) for x in np.arange(0.78, 0.905, 0.01)]
velums = [0.75, 0.60] if base.get("nasal") else [0.0]

print("syl %s | base c_pos %.3f | ma reference first" % (syl, base["c_pos"]))
rows = []
ref = dict(R.BASE_0902["ma"])
ok, fails, brief, y = R.judge("ma", ref)
tl = G.timeline(ref)
r = locus.onset_formants(y, G.SR, t_rel=tl["t_rel"] + 0.01)
print("  ma  c_pos 0.970 velum 0.75  ok=%s  F_on %-18s F+10 %-18s F+40 %-18s vowel %s  %s" % (
    ok, r["F_on"], r["F_10"], r["F_40"], r["F_vow"], "" if ok else fails))
for v in velums:
    for cp in places:
        spec = dict(base); spec["c_pos"] = cp
        if base.get("nasal"): spec["velum"] = v
        ok, fails, brief, y = R.judge(syl, spec)
        if y is None:
            print("  %s c_pos %.3f velum %.2f  RENDER FAIL %s" % (syl, cp, v, fails)); continue
        tl = G.timeline(spec)
        r = locus.onset_formants(y, G.SR, t_rel=tl["t_rel"] + 0.01)
        f2 = r["F_on"][1] or 0
        rows.append(dict(c_pos=cp, velum=v, ok=ok, fails=fails, F_on=r["F_on"], F_10=r["F_10"], F_40=r["F_40"], brief=brief))
        print("  %s c_pos %.3f velum %.2f  ok=%-5s F_on %-18s F+10 %-18s F+40 %-18s vowel %s  %s" % (
            syl, cp, v, ok, r["F_on"], r["F_10"], r["F_40"], r["F_vow"], "" if ok else fails))
json.dump(rows, open("probe_%s.json" % syl, "w"), indent=1)
print("wrote probe_%s.json (%d rows)" % (syl, len(rows)))
