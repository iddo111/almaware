"""subsessions.py -- the sitting was NOT one sitting.

mtimes show gaps of minutes-to-hours inside three of the six deep units. Cut
each unit's 100 takes at every gap > 60 s and you get real SUB-SESSIONS: he put
the microphone down, lived some of his day, and came back. That is the only
cross-time structure this data contains, and it is exactly what the session-leak
scar says must be respected. Map it first, measure it second.
"""
import datetime
import glob
import os
import sys

import numpy as np

STAGED = r"D:\CLAUDE\eran-brain\booth\staged\t06"
DEEP = ["ah", "ba", "ma", "ima", "ih", "abba"]
GAP = 60.0
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

info = {}
for p in sorted(glob.glob(os.path.join(STAGED, "*.wav"))):
    n = os.path.basename(p)[:-4].split("_")
    info.setdefault(n[0], []).append((int(n[2]), os.path.getmtime(p)))

print("SUB-SESSIONS (a gap > %.0f s starts a new one)" % GAP)
print("=" * 78)
sub = {}
for u in sorted(info):
    rr = sorted(info[u])
    ts = np.array([t for _, t in rr])
    cut = [0] + list(np.where(np.diff(ts) > GAP)[0] + 1) + [len(ts)]
    segs = [(cut[i], cut[i + 1]) for i in range(len(cut) - 1)]
    sub[u] = segs
    tag = "DEEP" if u in DEEP else "    "
    print("  %-5s %s %d take(s), %d sub-session(s):" % (u, tag, len(rr), len(segs)))
    for a, b in segs:
        print("        takes %3d-%-3d (n=%3d)  %s -> %s   (%.0f s)"
              % (rr[a][0], rr[b - 1][0], b - a,
                 datetime.datetime.fromtimestamp(ts[a]).strftime("%H:%M:%S"),
                 datetime.datetime.fromtimestamp(ts[b - 1]).strftime("%H:%M:%S"),
                 ts[b - 1] - ts[a]))

print()
print("UNITS WITH >= 2 SUB-SESSIONS (the only ones that can be tested across time):")
multi = [u for u in DEEP if len(sub[u]) >= 2]
print("  ", multi)
print()
print("SHALLOW units (3 takes) recorded at:")
for u in sorted(info):
    if u in DEEP:
        continue
    ts = sorted(t for _, t in info[u])
    print("  %-5s %s -> %s"
          % (u, datetime.datetime.fromtimestamp(ts[0]).strftime("%H:%M:%S"),
             datetime.datetime.fromtimestamp(ts[-1]).strftime("%H:%M:%S")))
