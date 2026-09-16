#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Build psy3_measurements.json: every v2-vs-v3 number, side by side."""
import json
import math
import os

import numpy as np

try:
    import psutil
    psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
except Exception:
    pass

from scipy import signal as sps

import psy3_measure as M
import psy_render as v1
import psy_render_v2 as v2mod
import psy_render_v3 as v3

HERE = os.path.dirname(os.path.abspath(__file__))


def musicgen_reference():
    """Measured 1/3-octave average of the MusicGen psy renders in this folder.
    MusicGen was trained on real music, so this is empirical evidence of the
    genre's balance -- but its melody conditioning failed (see manifest) and it
    renders at 32 kHz with a weak sub, so it is a SECONDARY reference only,
    trustworthy above ~150 Hz and useless below it."""
    curves = []
    for i in (1, 2, 3):
        p = os.path.join(HERE, f"DARWISH-musicgen-psy-20260821-{i}.wav")
        if not os.path.exists(p):
            continue
        L, R, sr = M.load(p)
        curves.append(M.third_octave_db((L + R) / 2.0, sr))
    if not curves:
        return None
    keys = set(curves[0])
    for c in curves[1:]:
        keys &= set(c)
    return {c: round(float(np.mean([cc[c] for cc in curves])), 2)
            for c in sorted(keys)}


def kick_ab():
    """Engine-level kick A/B: v2's kick_v2() vs v3's kick_v3(), both as isolated
    one-shots, peak-normalised.  No limiter, no other instruments -- so unlike
    the mix-level numbers this one is not confounded by mastering."""
    rng = np.random.default_rng(3)
    out = {}
    for name, k in (("v2", v2mod.kick_v2(rng)), ("v3", v3.kick_v3(rng))):
        k = np.asarray(k, dtype=np.float64)
        k = k / (np.max(np.abs(k)) + 1e-12)
        sr = M.SR
        env = np.abs(sps.hilbert(k))
        pk = float(np.max(env))
        i10 = np.flatnonzero(env >= 0.1 * pk)
        i90 = np.flatnonzero(env >= 0.9 * pk)
        b, a = sps.butter(4, 1500.0 / (sr / 2), btype="high")
        hf = sps.lfilter(b, a, k)
        nc = int(0.006 * sr)
        f, ps = M.welch_psd(k, sr, 2048)
        out[name] = {
            "length_ms": round(len(k) / sr * 1000.0, 1),
            "crest_db": round(20 * math.log10(
                1.0 / (float(np.sqrt(np.mean(k ** 2))) + 1e-12)), 2),
            "attack_ms": round((i90[0] - i10[0]) / sr * 1000.0, 2)
            if len(i10) and len(i90) else None,
            "click_energy_first6ms_over_total_db": round(10 * math.log10(
                (float(np.sum(hf[:nc] ** 2)) + 1e-20) /
                (float(np.sum(k ** 2)) + 1e-20)), 2),
            # both one-shots are peak-normalised, so this is a fair ABSOLUTE
            # level for the click, not a ratio against a denominator that
            # differs wildly between the two kicks
            "click_level_first6ms_dbfs_at_unit_peak": round(10 * math.log10(
                (float(np.mean(hf[:nc] ** 2)) + 1e-20)), 2),
            "spectral_peak_hz": round(float(f[np.argmax(ps)]), 1),
            "energy_63hz_band_frac": round(float(
                M.band_energy(k, sr, 56.0, 71.0) /
                (M.band_energy(k, sr, 20.0, 20000.0) + 1e-20)), 4),
        }
    return out


def stem_bass_gap(base, onsets_from_stem=True):
    """True bass/kick gap from the v3 stems: how long the bass stem is silent
    immediately before each kick, and how much bass energy is inside the kick."""
    kp = os.path.join(HERE, "stems", f"{base}-kick.wav")
    bp = os.path.join(HERE, "stems", f"{base}-bass.wav")
    if not (os.path.exists(kp) and os.path.exists(bp)):
        return None
    kL, kR, sr = M.load(kp)
    bL, bR, _ = M.load(bp)
    km = M.kick_metrics((kL + kR) / 2.0, sr)
    onsets = km.pop("_onsets")
    bm = (bL + bR) / 2.0
    env = np.abs(sps.hilbert(bm))
    thr = 0.02 * float(np.max(env))
    gaps = []
    for s in onsets:
        i = s
        while i > 0 and env[i] < thr and (s - i) < int(0.4 * sr):
            i -= 1
        gaps.append((s - i) / sr * 1000.0)
    e = bm ** 2
    w = int(0.06 * sr)
    ins = [float(np.mean(e[s:s + w])) for s in onsets if s + w < len(e)]
    return {
        "kick_stem_crest_db": km["kick_crest_db"],
        "kick_stem_crest_db_fullband": km["kick_crest_db_fullband"],
        "kick_stem_peak_dbfs": km["kick_peak_dbfs"],
        "bass_silent_ms_before_each_kick_mean": round(float(np.mean(gaps)), 1) if gaps else None,
        "bass_silent_ms_before_each_kick_min": round(float(np.min(gaps)), 1) if gaps else None,
        "bass_stem_energy_in_kick_over_avg": round(
            float(np.mean(ins)) / (float(np.mean(e)) + 1e-20), 4) if ins else None,
    }


def main():
    raw = json.load(open(os.path.join(HERE, "_psy3_render_raw.json"),
                         encoding="utf-8"))
    tgt = M.normalized_target()
    mg = musicgen_reference()
    out = {
        "generated": "2026-09-03 night, claude-cli-FABLE-psy3",
        "engine_v3": ("PolyBLEP band-limited oscillators + pedalboard 0.9.24 "
                      "(Spotify/JUCE) LadderFilter, Compressor, Limiter, "
                      "Reverb, Delay, shelving EQ; 4x-oversampled saturation; "
                      "two-pass measured match-EQ; ITU BS.1770-4 loudness via "
                      "pyloudnorm 0.2.0"),
        "engine_A_surge_xt": ("NOT AVAILABLE: `pip install surgepy` -> 'No "
                              "matching distribution found' (surgepy is not "
                              "published on PyPI), and no VST3/VST2 plugin is "
                              "installed on this PC. Fell back to plan B."),
        "psy_target_curve_db": tgt,
        "psy_target_curve_provenance": ("HAND-SPECIFIED from the genre brief "
                                        "(strong 40-100 Hz, scooped 200-400 Hz, "
                                        "presence 2-5 kHz, air rolled above "
                                        "14 kHz). Not measured from commercial "
                                        "tracks -- none are on this machine."),
        "musicgen_reference_curve_db": mg,
        "musicgen_reference_provenance": ("MEASURED average of the three "
                                          "DARWISH-musicgen-psy renders. Model "
                                          "trained on real music -> useful "
                                          "evidence above ~150 Hz; its 32 kHz "
                                          "output has almost no sub, so its "
                                          "40-100 Hz values are NOT a target."),
        "oscillator_ab": raw["oscillator_ab"],
        "kick_ab": kick_ab(),
        "tracks": [],
    }

    for rep in raw["tracks"]:
        i = rep["wav"].split("-")[-1].split(".")[0]
        v2wav = os.path.join(HERE, f"DARWISH-psy2-20260821-{i}.wav")
        v3wav = os.path.join(HERE, rep["wav"])
        m2 = M.measure_file(v2wav) if os.path.exists(v2wav) else None
        m3 = M.measure_file(v3wav)
        d3t, r3t = M.spectrum_delta(m3["third_octave_db"], tgt)
        row = {
            "track": int(i),
            "source_mid": rep["source_mid"],
            "wav": rep["wav"],
            "mp3": rep["mp3"],
            "png": rep["png"],
            "bpm": rep["bpm"],
            "duration_s": rep["duration_s"],
            "melody": {
                "orig_ch0_notes": rep["orig_ch0_notes"],
                "lead_notes_placed": rep["lead_notes_placed"],
                "dropped_notes": rep["dropped_notes"],
                "pitch_class_match": v1.pitch_histogram_match(
                    rep["_orig_classes"], rep["_placed_classes"]),
            },
            "v3": m3,
            "v2": m2,
            "v3_delta_vs_psy_target_db": d3t,
            "v3_delta_vs_psy_target_rms_db": r3t,
            "v3_stems": stem_bass_gap(os.path.splitext(rep["wav"])[0]),
            "v3_scheduled_bass_gap_before_kick_ms":
                rep["scheduled_bass_gap_before_kick_ms"],
            "v3_bass_note_len_ms": rep["bass_note_len_ms"],
            "v3_match_eq_pass1_db": rep["match_eq_db"],
            "v3_match_eq_pass2_db": rep["match_eq_pass2_db"],
            "v3_limiter_threshold_db": rep["limiter_threshold_db"],
            "v3_bar_roots_from_his_phrase": rep["bar_roots_from_his_phrase"],
        }
        if m2:
            d2t, r2t = M.spectrum_delta(m2["third_octave_db"], tgt)
            row["v2_delta_vs_psy_target_db"] = d2t
            row["v2_delta_vs_psy_target_rms_db"] = r2t
        if mg:
            _, r3m = M.spectrum_delta(m3["third_octave_db"], mg)
            row["v3_delta_vs_musicgen_rms_db"] = r3m
            if m2:
                _, r2m = M.spectrum_delta(m2["third_octave_db"], mg)
                row["v2_delta_vs_musicgen_rms_db"] = r2m
        out["tracks"].append(row)

    with open(os.path.join(HERE, "psy3_measurements.json"), "w",
              encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    # ---- console table ---------------------------------------------------
    cols = [("LUFS", "lufs_integrated"), ("truePk", "true_peak_dbfs"),
            ("PLR", "plr_db"), ("crest", "crest_db_full"),
            ("kickCrest", "kick_crest_db"), ("kickClick", "kick_hf_transient_db"),
            ("pump", "pumping_depth_db"),
            ("flat>10k", "flatness_above_10k"), ("HF/mid", "alias_hf_ratio_db")]
    print(f"{'track':<9}{'ver':<5}" + "".join(f"{c[0]:>11}" for c in cols) +
          f"{'specRMS':>9}")
    for row in out["tracks"]:
        for ver in ("v2", "v3"):
            m = row[ver]
            if not m:
                continue
            rms = row.get(f"{ver}_delta_vs_psy_target_rms_db")
            print(f"{row['track']:<9}{ver:<5}" +
                  "".join(f"{str(m.get(c[1])):>11}" for c in cols) +
                  f"{str(rms):>9}")
    print("\noscillator A/B:", json.dumps(out["oscillator_ab"]))
    for row in out["tracks"]:
        print(f"track {row['track']} melody corr="
              f"{row['melody']['pitch_class_match']['correlation']} "
              f"dropped={row['melody']['dropped_notes']} "
              f"stems={row['v3_stems']}")


if __name__ == "__main__":
    main()
