# -*- coding: utf-8 -*-
"""Measure Iddo's OWN f1_traj distribution, per unit, on the t06 corpus.
Writes human-band.json. Reads wavs as bytes. Plays nothing."""
import glob, json, os, sys, wave
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from f1traj import f1_traj_hz

T06 = os.path.expanduser("~/eran-cortex/data/t06")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "human-band.json")
UNITS = ["ba", "ah", "ma", "ih", "abba", "ima"]


def load(p):
    with wave.open(p) as w:
        assert w.getframerate() == 16000 and w.getnchannels() == 1 and w.getsampwidth() == 2
        raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, "<i2").astype(np.float64) / 32768.0


out = {"corpus": T06, "note": "Iddo's own real takes; f1_traj_hz per clip"}
for u in UNITS:
    fs = sorted(glob.glob(os.path.join(T06, "%s_t06_*.wav" % u)))
    vals = []
    for p in fs:
        try:
            v = f1_traj_hz(load(p))
        except Exception:
            v = float("nan")
        vals.append(v)
    a = np.array(vals, dtype=float)
    ok = a[np.isfinite(a)]
    if len(ok) < 5:
        out[u] = {"n": len(fs), "n_ok": int(len(ok)), "usable": False}
        continue
    p10, p25, p50, p75, p90 = [float(np.percentile(ok, q)) for q in (10, 25, 50, 75, 90)]
    out[u] = {"n": len(fs), "n_ok": int(len(ok)), "usable": True,
              "min": float(ok.min()), "p10": p10, "p25": p25, "median": p50,
              "p75": p75, "p90": p90, "max": float(ok.max()),
              "mean": float(ok.mean()), "sd": float(ok.std()),
              "lo": p10, "hi": p90, "scale": max(p90 - p10, 1.0)}
    print("%-6s n=%3d ok=%3d  p10 %7.1f  med %7.1f  p90 %7.1f  (min %6.1f max %7.1f)"
          % (u, len(fs), len(ok), p10, p50, p90, ok.min(), ok.max()), flush=True)

with open(OUT, "w") as f:
    json.dump(out, f, indent=1)
print("wrote", OUT)
