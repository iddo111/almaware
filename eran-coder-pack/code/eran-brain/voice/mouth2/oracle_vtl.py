# -*- coding: utf-8 -*-
"""oracle_vtl.py -- the German oracle: VocalTractLab child formant targets.

GPL BOUNDARY -- READ BEFORE TOUCHING
====================================
VocalTractLab (vocaltractlab-cython, GPL) runs ONLY here, on the PC, in
the private venv `.venv-vtl` next to this file. It is never deployed to
the fleet, never imported by any worker, never linked into MOUTH v2.
Only NUMBERS cross this boundary: validate/child_targets.json.

What was measured before this script took its final shape (2026-08-26,
API 2.4.2, JD3.speaker, all on this machine -- decisions below follow
these numbers, not hope):

  * Adult presets are textbook:  /a/ 668/1192/2425, /i/ 207/2148/3128,
    /u/ 253/794/2511 Hz (F1/F2/F3), min tract areas 0.25-0.33 cm^2.
  * get_shape() FAILS after set_anatomy_from_age() (vtlGetTractParams
    error), and save_speaker() then writes a speaker whose vocal-tract
    shape library is EMPTY -- the age API drops the shapes. Therefore
    shapes must be fetched BEFORE the anatomy change and pushed through
    the child anatomy as raw articulatory parameter vectors.
  * On the 60-month anatomy: /a/ stays healthy (756/1752/3246, min
    area 0.218). /i/ CLOSES COMPLETELY (min area 0.0001 cm^2 -- it is
    a stop, not a vowel; blending 50% toward schwa opens it to 0.229
    and yields 460/2344/3292, but that is no longer the /i/ preset).
    /u/ stays open (0.227) but F2 jumps 794 -> 1806 Hz, 2.27x the
    adult -- the rounding/back-cavity character is destroyed, while a
    real child /u/ F2 sits near 1300-1500 Hz.

Verdict encoded here: accept a VTL child vowel only if
  (1) min tract area >= MIN_AREA_CM2, and
  (2) every child/adult formant ratio (F1, F2) lies in RATIO_OK --
      a child tract is shorter, so formants scale UP, but modestly.
Otherwise fall back to published child values (Vorperian & Kent 2007)
for that vowel, and record the rejected VTL numbers in meta anyway.
Result with API 2.4.2: /a/ from VTL, /i/ and /u/ from literature.

Literature fallback: Vorperian, H. K., and Kent, R. D. (2007). "Vowel
acoustic space development in children: A synthesis of acoustic and
anatomic data," J. Speech Lang. Hear. Res. 50(6), 1510-1545.
Approximate ~age-5 values read from the developmental charts (they are
APPROXIMATE -- the paper gives ranges, not single numbers):
/a/ 1050/1650, /i/ 430/3100, /u/ 480/1400 Hz. F3 is left null for
literature-sourced vowels rather than faking precision.

Known wart: the compiled extension segfaults in its atexit teardown on
Windows (AFTER all work is done). The JSON is written and fsynced
before that, so a 139 exit with the file present is success.

Usage:  .venv-vtl\\Scripts\\python.exe oracle_vtl.py
"""
import json
import os
import sys

import numpy as np

AGE_MONTHS = 60
IS_MALE = True
N_FFT = 16384
VOWELS = ("a", "i", "u")
MIN_AREA_CM2 = 0.10
RATIO_OK = (1.0, 1.7)     # child/adult formant ratio window
LITERATURE = {  # Vorperian & Kent 2007, ~age 5, approximate chart reads
    "a": {"F1": 1050.0, "F2": 1650.0, "F3": None},
    "i": {"F1": 430.0, "F2": 3100.0, "F3": None},
    "u": {"F1": 480.0, "F2": 1400.0, "F3": None},
}
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_PATH = os.path.join(HERE, "validate", "child_targets.json")


def peak_pick(mag, sr, nfft, n=3, fmin=150.0, fmax=5500.0):
    """First n local maxima of the magnitude spectrum, parabolic refine."""
    df = sr / nfft
    out = []
    for i in range(1, len(mag) - 1):
        f = i * df
        if f < fmin or f > fmax:
            continue
        if mag[i] > mag[i - 1] and mag[i] >= mag[i + 1]:
            d = mag[i - 1] - 2 * mag[i] + mag[i + 1]
            off = 0.5 * (mag[i - 1] - mag[i + 1]) / d if d != 0 else 0.0
            out.append(float((i + off) * df))
            if len(out) >= n:
                break
    return out


def main():
    import vocaltractlab_cython as v

    version = v.get_version()
    sr = v.get_constants()["sr_audio"]
    print("VTL", version, "| speaker:", os.path.basename(v.active_speaker()))

    def formants(ts):
        tf = v.tract_state_to_transfer_function(ts, n_spectrum_samples=N_FFT)
        return peak_pick(np.asarray(tf["magnitude_spectrum"]), sr, N_FFT, n=3)

    def min_area(ts):
        return float(np.asarray(v.tract_state_to_tube_state(ts)["tube_area"]).min())

    # 1. Adult shapes BEFORE the anatomy change (see header).
    shapes = {vw: np.asarray(v.get_shape(vw, "tract")) for vw in VOWELS}
    adult = {vw: formants(shapes[vw]) for vw in VOWELS}
    for vw in VOWELS:
        print("  adult /%s/  %s" % (vw, ["%.0f" % f for f in adult[vw]]))

    # 2. Child anatomy, same articulatory vectors.
    v.set_anatomy_from_age(AGE_MONTHS, IS_MALE)
    print("anatomy set: %d months, male=%s" % (AGE_MONTHS, IS_MALE))

    targets = {}
    vtl_raw = {}
    for vw in VOWELS:
        F = formants(shapes[vw])
        ma = min_area(shapes[vw])
        vtl_raw[vw] = {"F1": round(F[0], 1) if F else None,
                       "F2": round(F[1], 1) if len(F) > 1 else None,
                       "F3": round(F[2], 1) if len(F) > 2 else None,
                       "min_area_cm2": round(ma, 4)}
        ratios = [F[k] / adult[vw][k] for k in (0, 1)] if len(F) >= 2 else []
        plausible = (ma >= MIN_AREA_CM2 and len(ratios) == 2
                     and all(RATIO_OK[0] <= r <= RATIO_OK[1] for r in ratios))
        if plausible:
            targets[vw] = {"F1": round(F[0], 1), "F2": round(F[1], 1),
                           "F3": round(F[2], 1) if len(F) > 2 else None,
                           "source": "vtl"}
            print("  child /%s/  %s  min_area %.3f  ratios %s  -> VTL ACCEPTED"
                  % (vw, ["%.0f" % f for f in F], ma,
                     ["%.2f" % r for r in ratios]))
        else:
            targets[vw] = dict(LITERATURE[vw],
                               source="literature: Vorperian & Kent 2007, "
                                      "~age 5, approximate chart values")
            why = ("tract closes (min area %.4f cm^2)" % ma
                   if ma < MIN_AREA_CM2 else
                   "child/adult formant ratios %s outside %s"
                   % (["%.2f" % r for r in ratios], list(RATIO_OK)))
            print("  child /%s/  %s  min_area %.3f  -> VTL REJECTED (%s), "
                  "literature fallback" % (vw, ["%.0f" % f for f in F], ma, why))

    payload = {vw: targets[vw] for vw in VOWELS}
    payload["meta"] = {
        "vtl_version": version,
        "age_months": AGE_MONTHS,
        "is_male": IS_MALE,
        "method": ("JD3.speaker adult preset shapes fetched BEFORE "
                   "vtlSetAnatomyFromAge(%d, male) (the age API drops the "
                   "shape library), then vtlGetTransferFunction (%d-pt, "
                   "sr=%d, df=%.2f Hz), F1-F3 peak-picked in 150-5500 Hz; "
                   "per-vowel plausibility gate: min area >= %.2f cm^2 and "
                   "child/adult F1,F2 ratios in %s, else Vorperian & Kent "
                   "2007 literature fallback"
                   % (AGE_MONTHS, N_FFT, sr, sr / N_FFT, MIN_AREA_CM2,
                      list(RATIO_OK))),
        "gpl_boundary": ("VTL runs only on the PC in .venv-vtl; only these "
                         "numbers ship."),
        "vtl_adult_formants": {vw: [round(f, 1) for f in adult[vw]]
                               for vw in VOWELS},
        "vtl_child_raw": vtl_raw,
        "literature_reference": ("Vorperian & Kent 2007, JSLHR 50(6):"
                                 "1510-1545; approximate ~age-5 chart values"),
        "generated": "oracle_vtl.py, 2026-08-26",
    }
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    print("wrote", OUT_PATH)
    sys.stdout.flush()


if __name__ == "__main__":
    main()
