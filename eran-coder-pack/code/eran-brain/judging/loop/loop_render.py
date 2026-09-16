#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""loop_render.py -- runs ON eran2 (~/throat-one-sample/loop_render.py).

The render leg of the judging loop (D:\CLAUDE\eran-brain\judging\loop.py).
Reads ONE JSON job on stdin, renders wavs with the SAME render() the search
used (train_one.render for /ah/, train_syl2.render for ma/na/la/ya), writes
them into out_dir and prints a manifest JSON on the last line of stdout.

Job:
  {"unit": "ah", "out_dir": "~/throat-one-sample/loop/r03",
   "items":  [{"name": "ERAN-ah-r03-x.wav", "genome": [...]}, ...],   # explicit
   "mutate": {"parent": [...], "sigma": 0.55, "n": 3, "seed": 3,
              "prefix": "ERAN-ah-r03"}}                              # optional
Either or both. No metric is computed here on purpose: Iddo is the metric.
"""
import importlib
import json
import os
import sys
import wave

import numpy as np

sys.path.insert(0, os.path.expanduser("~/throat-one-sample"))
sys.path.insert(0, os.path.expanduser("~/mouth-v2"))

SR = 16000


def write_wav(path, y):
    w = wave.open(path, "wb")
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((np.clip(y, -1, 1) * 32767).astype(np.int16).tobytes())
    w.close()


def load_unit(unit):
    """Return (render, lo, hi, span_scaled) for the unit, importing the very
    module that trained it so the sound is the sound the search made."""
    if unit == "ah":
        sys.argv = ["loop_render", "8"]
        import train_one as T
        return T.render, np.array([T.LO]), np.array([T.HI]), False
    sys.argv = ["loop_render", unit]
    import train_syl2 as S
    S = importlib.reload(S)          # module-level UNIT/LO/HI depend on argv
    return S.render, S.LO, S.HI, True


def main():
    job = json.load(sys.stdin)
    unit = job["unit"]
    out = os.path.expanduser(job["out_dir"])
    os.makedirs(out, exist_ok=True)
    render, lo, hi, scaled = load_unit(unit)
    items = list(job.get("items", []))
    m = job.get("mutate")
    if m:
        rng = np.random.default_rng(int(m.get("seed", 0)))
        parent = np.asarray(m["parent"], float)
        step = float(m["sigma"]) * ((hi - lo) if scaled else 1.0)
        for i in range(int(m.get("n", 3))):
            g = np.clip(parent + step * rng.standard_normal(len(parent)), lo, hi)
            items.append({"name": "%s-c%d.wav" % (m["prefix"], i + 1),
                          "genome": [float(v) for v in g], "kind": "mutant"})
    done = []
    for it in items:
        y = render(np.asarray(it["genome"], float))
        ok = y is not None and np.isfinite(y).all() and np.abs(y).max() > 1e-4
        if ok:
            write_wav(os.path.join(out, it["name"]), y)
        done.append({"name": it["name"], "genome": it["genome"],
                     "kind": it.get("kind", "explicit"),
                     "ok": bool(ok), "peak": float(np.abs(y).max()) if ok else 0.0,
                     "samples": int(len(y)) if ok else 0})
    print("MANIFEST " + json.dumps({"unit": unit, "out_dir": out, "items": done}))


if __name__ == "__main__":
    main()
