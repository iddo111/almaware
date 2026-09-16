"""timeline.py -- what actually happened at the microphone, from mtimes + wav headers."""
import glob
import os
import sys
import wave

import numpy as np

STAGED = r"D:\CLAUDE\eran-brain\booth\staged\t06"
DEEP = ["ah", "ba", "ma", "ima", "ih", "abba"]
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

rows = []
for p in sorted(glob.glob(os.path.join(STAGED, "*.wav"))):
    n = os.path.basename(p)[:-4].split("_")
    with wave.open(p, "rb") as w:
        dur = w.getnframes() / float(w.getframerate())
    rows.append({"unit": n[0], "take": int(n[2]), "dur": dur,
                 "mt": os.path.getmtime(p), "name": os.path.basename(p)})

deep = [r for r in rows if r["unit"] in DEEP]
deep.sort(key=lambda r: r["mt"])
t0 = deep[0]["mt"]
import datetime
print("first clip mtime : %s" % datetime.datetime.fromtimestamp(deep[0]["mt"]))
print("last  clip mtime : %s" % datetime.datetime.fromtimestamp(deep[-1]["mt"]))
print("order by mtime, first 8 :", [r["name"] for r in deep[:8]])
print("order by mtime, last  8 :", [r["name"] for r in deep[-8:]])

gaps = np.diff([r["mt"] for r in deep])
print()
print("gaps between consecutive clips in MTIME ORDER (n=%d):" % len(gaps))
for q in (10, 25, 50, 75, 90, 95, 99):
    print("   p%-2d %8.2f s" % (q, np.percentile(gaps, q)))
print("   max %8.2f s (%.1f min)" % (gaps.max(), gaps.max() / 60))
big = gaps[gaps > 60]
print("   gaps > 60 s : %d, totalling %.1f s (%.1f min)"
      % (len(big), big.sum(), big.sum() / 60))
active = gaps[gaps <= 60].sum()
print()
print("ACTIVE time at the mic (sum of gaps <= 60 s, + first clip) : %.1f s (%.1f min)"
      % (active, active / 60))
print("  -> %.2f s per take ACTIVE" % (active / 600.0))
print("TOTAL elapsed span : %.1f s (%.1f h)"
      % (deep[-1]["mt"] - t0, (deep[-1]["mt"] - t0) / 3600))

print()
print("per-unit: when each block of 100 was recorded")
for u in DEEP:
    rr = sorted([r for r in deep if r["unit"] == u], key=lambda r: r["take"])
    ts = np.array([r["mt"] for r in rr])
    dd = np.array([r["dur"] for r in rr])
    g = np.diff(ts)
    print("  %5s : start %s  span %6.1f s  take-gap median %.2f s  "
          "clip dur median %.3f s  (min %.3f max %.3f)"
          % (u, datetime.datetime.fromtimestamp(ts[0]).strftime("%H:%M:%S"),
             ts[-1] - ts[0], np.median(g), np.median(dd), dd.min(), dd.max()))
    mono = bool(np.all(np.diff(ts) >= 0))
    print("          take index monotonic in time: %s   gaps>60s within unit: %d"
          % (mono, int((g > 60).sum())))

print()
print("clip duration by unit (s):")
for u in DEEP:
    dd = np.array([r["dur"] for r in deep if r["unit"] == u])
    print("  %5s : median %.3f  mean %.3f  p10 %.3f  p90 %.3f"
          % (u, np.median(dd), dd.mean(), np.percentile(dd, 10),
             np.percentile(dd, 90)))
