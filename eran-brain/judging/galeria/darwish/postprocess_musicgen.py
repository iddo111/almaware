#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""postprocess_musicgen.py -- measure + spectrogram + mp3 for the MusicGen
outputs pulled back from eran2. Reuses psy_render_v2's LUFS/true-peak
estimators and psy_render's spectrogram/mp3/measure helpers (no new DSP
code duplicated)."""
import json
import os
import sys
import wave

import librosa
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import psy_render as v1  # noqa: E402
import psy_render_v2 as v2  # noqa: E402


def read_wav_mono_stereo(path):
    with wave.open(path, "rb") as w:
        sr = w.getframerate()
        nfr = w.getnframes()
        ch = w.getnchannels()
        raw = w.readframes(nfr)
    data = np.frombuffer(raw, dtype=np.int16).astype(np.float64) / 32768.0
    data = data.reshape(-1, ch)
    if ch == 1:
        L = R = data[:, 0]
    else:
        L, R = data[:, 0], data[:, 1]
    return L, R, sr


results = []
for i in (1, 2, 3):
    wav_path = os.path.join(HERE, f"DARWISH-musicgen-psy-20260821-{i}.wav")
    mp3_path = os.path.join(HERE, f"DARWISH-musicgen-psy-20260821-{i}.mp3")
    png_path = os.path.join(HERE, f"DARWISH-musicgen-psy-20260821-{i}.png")

    L, R, sr = read_wav_mono_stereo(wav_path)
    wav_stats = v1.measure_wav(wav_path)
    lufs = v2.integrated_lufs(L, R, sr)
    tp = v2.true_peak_dbfs(L, R, sr)

    y, _ = librosa.load(wav_path, sr=sr, mono=True)
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    tempo_val = float(np.atleast_1d(tempo)[0])

    v1.make_spectrogram_png(L, R, png_path, sr=sr)
    v1.to_mp3(wav_path, mp3_path)

    r = {
        "track": i,
        "wav": os.path.basename(wav_path),
        "duration_s": round(len(L) / sr, 2),
        "sr": sr,
        "wav_rms_dbfs": wav_stats["rms_dbfs"],
        "wav_peak_dbfs": wav_stats["peak_dbfs"],
        "lufs_integrated_estimate": round(lufs, 2),
        "true_peak_dbfs": round(tp, 2),
        "estimated_bpm": round(tempo_val, 1),
    }
    results.append(r)
    print(json.dumps(r, indent=2))

with open(os.path.join(HERE, "musicgen_postprocess.json"), "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2)
print("WROTE musicgen_postprocess.json")
