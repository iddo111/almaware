#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_melody_wav.py -- plain sine/saw rendering of DARWISH's own channel-0
melody, mono @ 32kHz, for MusicGen-melody conditioning (Part B, Iddo
2026-09-03 21:04). Reuses psy_render.load_ch0_notes (v1) -- the same note
extraction already proven for psy_render_v2.py -- no new MIDI parsing.
Capped to musicgen's practical ~30s generation window so the condition
audio covers the same span as what gets generated.
"""
import glob
import os
import sys
import wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import psy_render as v1  # noqa: E402

SR = 32000
MAX_S = 30.0


def render_melody(path_in, path_out, sr=SR, max_s=MAX_S):
    ch0, orig_bpm, orig_len = v1.load_ch0_notes(path_in)
    # take only the notes that fall inside the first max_s seconds of the
    # ORIGINAL performance (not time-stretched) -- keeps melody-conditioning
    # audio a faithful, undistorted excerpt of Darwish's own line.
    ch0 = [(t, p, vv) for (t, p, vv) in ch0 if t < max_s]
    n = int(max_s * sr)
    buf = np.zeros(n)
    for i, (t0, pitch, vel) in enumerate(ch0):
        t1 = ch0[i + 1][0] if i + 1 < len(ch0) else min(t0 + 0.4, max_s)
        dur = max(0.06, min(t1 - t0, 0.5))
        s = int(t0 * sr)
        ns = int(dur * sr)
        e = min(s + ns, n)
        if e <= s:
            continue
        tt = np.arange(e - s) / sr
        f = 440.0 * 2 ** ((pitch - 69) / 12.0)
        saw = 2 * ((tt * f) % 1.0) - 1.0
        sine = np.sin(2 * np.pi * f * tt)
        sig = 0.5 * sine + 0.5 * saw
        a = max(1, int(0.01 * sr))
        r = max(1, int(0.03 * sr))
        env = np.ones(e - s)
        env[:min(a, len(env))] = np.linspace(0, 1, min(a, len(env)))
        if len(env) > r:
            env[-r:] = np.linspace(1, 0, r)
        buf[s:e] += sig * env * min(vel / 110.0, 1.0) * 0.7
    peak = np.max(np.abs(buf)) or 1.0
    buf = buf / peak * 0.9
    with wave.open(path_out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((buf * 32767.0).astype(np.int16).tobytes())
    return len(ch0), orig_bpm


if __name__ == "__main__":
    raw_dir = os.path.join(HERE, "raw")
    mids = sorted(glob.glob(os.path.join(raw_dir, "*.mid")))
    for i, m in enumerate(mids, start=1):
        out = os.path.join(HERE, f"DARWISH-melody-{i}.wav")
        n_notes, bpm = render_melody(m, out)
        print(out, n_notes, "notes, bpm", bpm)
