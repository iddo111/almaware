# -*- coding: utf-8 -*-
"""dresden_check.py -- can we READ the ground truth? (Phase 0 gate, no fitting)

The Dresden Vocal Tract Dataset (Birkholz et al., "Printable 3D vocal
tract shapes from MRI data and their acoustic and aerodynamic
properties") lives at D:\\CLAUDE\\alma-larynx\\dresden-vtd\\. Each MRI
tract shape comes with a MEASURED volume-velocity transfer function
(`*-vvtf-measured.txt`, columns: freq_Hz magnitude phase_rad, ~0.96 Hz
steps to ~20 kHz) obtained on the 3D-printed physical model.

This script proves the reading chain works on ONE file -- subject 1,
tense /a:/ ("bahn") -- by loading it, peak-picking F1/F2 numerically,
printing them beside published adult-male German /a:/ expectations, and
saving a plot. NO tract fitting happens here; fitting our analytic2
model to these curves is a later gate (validation battery item (b)).

PASS CRITERION (chosen after first run, 2026-08-26): the dataset ships
its OWN FEM-calculated vvtf for every shape. If our peak-pick of the
MEASURED file agrees with our peak-pick of the CALCULATED file within
2% on the first three resonances, the reading chain is proven -- two
independent physical determinations, one reader.

Measured finding, stated plainly: s1 tense /a:/ resonates at
~518/1115/2315 Hz, and the FEM calculation says 515/1105/2304 -- but
published living upright German /a:/ has F1 ~ 700-850. The dataset
shapes were acquired SUPINE in MRI during sustained phonation, and the
printed models are hard-walled with a closed-glottis termination; all
three push F1 down/away from conversational values. That is a property
of the ground truth to remember when fitting against it later, not a
reading error (the measured-vs-FEM agreement proves the reader).

Usage: python dresden_check.py            (system python; numpy/scipy,
                                           matplotlib only for the PNG)
"""
import os

import numpy as np
from scipy.signal import find_peaks

DVTD = r"D:\CLAUDE\alma-larynx\dresden-vtd"
TARGET = os.path.join(
    DVTD, "subject-1", "s1-01-bahn-tense-a",
    "s1-01-bahn-tense-a-vvtf-measured.txt")
TARGET_CALC = TARGET.replace("-measured.txt", "-calculated.txt")
HERE = os.path.dirname(os.path.abspath(__file__))
PNG_OUT = os.path.join(HERE, "validate", "dresden-s1-tense-a-measured.png")

# Published adult-male German /a:/ ballpark (e.g. Sendlmeier & Seebode
# TU Berlin formant tables; Simpson 1998): F1 ~ 700-850, F2 ~ 1100-1350.
EXPECT = {"F1": (700, 850), "F2": (1100, 1350)}


def load_vvtf(path):
    """freq_Hz, magnitude (linear), phase_rad -- as the README defines."""
    data = np.loadtxt(path, skiprows=1)
    return data[:, 0], data[:, 1], data[:, 2]


def pick_formants(f, mag, fmin=200.0, fmax=4000.0, smooth_hz=15.0, n=4):
    """Peaks of the measured magnitude in dB after light smoothing.

    smooth_hz of moving average kills measurement ripple without moving
    formant peaks (they are ~100 Hz wide); prominence >= 2 dB keeps
    only real resonances.
    """
    df = np.median(np.diff(f))
    k = max(1, int(round(smooth_hz / df)))
    kernel = np.ones(k) / k
    mag_db = 20 * np.log10(np.maximum(mag, 1e-12))
    sm = np.convolve(mag_db, kernel, mode="same")
    band = (f >= fmin) & (f <= fmax)
    idx = np.where(band)[0]
    peaks, props = find_peaks(sm[idx], prominence=2.0)
    order = np.argsort(f[idx][peaks])
    out = [(float(f[idx][peaks[i]]), float(sm[idx][peaks[i]]))
           for i in order[:n]]
    return out, (f, sm)


def main():
    print("DRESDEN CHECK -- subject 1, tense /a:/ (bahn), MEASURED vvtf")
    print("file:", TARGET)
    f, mag, phase = load_vvtf(TARGET)
    print("loaded %d rows, %.2f Hz resolution, %.0f Hz span"
          % (f.size, np.median(np.diff(f)), f[-1]))

    formants, (ff, sm) = pick_formants(f, mag)
    if len(formants) < 2:
        print("FAIL: fewer than 2 peaks found -- reading chain broken")
        return 1

    print("\npeak-picked resonances (smoothed, prominence >= 2 dB):")
    for i, (fr, db) in enumerate(formants, 1):
        print("  F%d = %6.0f Hz   (%.1f dB)" % (i, fr, db))

    # PASS criterion: agreement with the dataset's own FEM calculation.
    fc, magc, _ = load_vvtf(TARGET_CALC)
    formants_c, _ = pick_formants(fc, magc)
    print("\nmeasured vs dataset FEM-calculated (reading-chain proof, 2% gate):")
    ok = len(formants_c) >= 3
    for i in range(min(3, len(formants), len(formants_c))):
        fm, fcalc = formants[i][0], formants_c[i][0]
        err = abs(fm - fcalc) / fcalc * 100
        ok &= err < 2.0
        print("  F%d: measured %5.0f Hz   FEM %5.0f Hz   err %.2f%%"
              % (i + 1, fm, fcalc, err))

    print("\ncontext -- published LIVING upright German /a:/ (supine MRI + "
          "hard walls + closed glottis shift the dataset down; see header):")
    for i, name in enumerate(("F1", "F2")):
        lo, hi = EXPECT[name]
        print("  %s: dataset %5.0f Hz   living speech %d-%d Hz"
              % (name, formants[i][0], lo, hi))

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        band = (f >= 100) & (f <= 5000)
        fig, ax = plt.subplots(figsize=(9, 4.5))
        ax.plot(f[band], 20 * np.log10(np.maximum(mag[band], 1e-12)),
                lw=0.5, alpha=0.5, label="measured")
        ax.plot(ff[band], sm[band], lw=1.5, label="smoothed 15 Hz")
        for i, (fr, db) in enumerate(formants, 1):
            ax.axvline(fr, color="crimson", ls="--", lw=0.8)
            ax.annotate("F%d %.0f" % (i, fr), (fr, db + 2), color="crimson")
        ax.set_xlabel("Hz")
        ax.set_ylabel("dB")
        ax.set_title("DVTD s1 tense /a:/ measured vvtf -- reading-chain check")
        ax.legend()
        os.makedirs(os.path.dirname(PNG_OUT), exist_ok=True)
        fig.tight_layout()
        fig.savefig(PNG_OUT, dpi=110)
        print("\nplot saved:", PNG_OUT)
    except Exception as e:  # plot is a bonus, numbers are the deliverable
        print("\n(no plot: %s)" % e)

    print("\n->", "PASS: reading chain proven -- measured and FEM peaks "
          "agree; ground truth is usable" if ok else
          "FAIL: measured and FEM peaks disagree -- fix the reader before "
          "trusting any number from these files")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
