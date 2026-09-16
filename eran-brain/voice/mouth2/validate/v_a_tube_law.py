# -*- coding: utf-8 -*-
"""v_a_tube_law.py -- gate (a): the rendered tube must be a PHYSICAL tube.

Uniform child tube, velum closed. Three checks:

1. TWIN AGREEMENT (the 3% gate): the rendered audio's resonances
   (white-noise probe through the identical render path, Welch
   peak-pick, NO LPC) within 3% of the analytic transfer function of
   the SAME discrete geometry with the SAME terminations
   (measure.twin_transfer -- the HF-filtered ends the ladder really
   has). First run of this gate exposed a real ~7% end correction from
   those filters; that measurement now lives in
   tract_core.END_CORRECTION_SECTIONS and the anatomy compensates.
2. ODD-MULTIPLE LAW: F2/F1 ~ 3, F3/F1 ~ 5 -- the closed-open law the
   old tract_analytic ladder FAILED (it gave 1:2:3; analytic2 header
   records that measurement). Equal spacing here = inherited bug.
3. ANATOMY HONESTY (report + loose gate): the effective acoustic
   length (from rendered F1 via c/4L) must be within 5% of the
   11.98 cm child target -- i.e. the end-correction compensation in
   n_sections_for actually lands the child at child length.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

import analytic2
import measure as M
import mouth2
import tract_core as T

AREA = 1.5          # cm^2, uniform
SECONDS = 6.0       # 3 s left ~2% Welch variance on F1 (measured); 6 s
                    # with nperseg 8192 / 30 Hz smoothing converges
NPERSEG = 8192
SMOOTH_HZ = 30.0


def main():
    N = mouth2.N_MAIN
    L = N * T.SECTION_CM
    L_child = mouth2._L_CHILD
    areas = np.full(N, AREA)

    ideal = analytic2.resonances_physical(areas, L, n=3)
    freqs = np.arange(200.0, 5000.0, 1.0)
    tf = M.twin_transfer(areas, freqs)
    twin = analytic2.peak_pick(freqs, np.abs(tf["H_lip"]), n=3)

    track, velum = M.track_for(areas, SECONDS)
    lip16, nose16 = M.noise_probe(track, velum, seconds=SECONDS)
    got = M.spectral_peaks(lip16, n=3, fmin=300.0, nperseg=NPERSEG,
                           smooth_hz=SMOOTH_HZ)

    print("GATE (a) -- tube law, uniform child tube (N=%d, ladder %.2f cm, "
          "effective %.2f cm, child target %.2f cm)"
          % (N, L, T.effective_length_cm(N), L_child))
    print("  ideal-termination analytic peaks:    %s"
          % ["%.0f" % x for x in ideal])
    print("  SAME-termination twin (HF-filtered): %s"
          % ["%.0f" % x for x in twin])
    print("  rendered (noise probe, Welch):       %s"
          % ["%.0f" % x for x in got])

    ok = len(got) >= 3 and len(twin) >= 3
    errs = []
    if ok:
        errs = [abs(g - w) / w * 100 for g, w in zip(got, twin)]
        print("  render-vs-twin err%%: %s (gate: all within 3%%)"
              % ["%.2f" % e for e in errs])
        ok &= all(e <= 3.0 for e in errs)
        r2, r3 = got[1] / got[0], got[2] / got[0]
        print("  overtone ratios: F2/F1 = %.3f (odd law 3, old-ladder bug 2), "
              "F3/F1 = %.3f (odd law 5, bug 3)" % (r2, r3))
        ok &= abs(r2 - 3.0) < 0.25 and abs(r3 - 5.0) < 0.40
        L_eff = analytic2.C_SOUND / (4.0 * got[0])
        len_err = abs(L_eff - L_child) / L_child * 100
        print("  effective length from rendered F1: %.2f cm (child %.2f, "
              "err %.1f%%, gate 5%%)" % (L_eff, L_child, len_err))
        ok &= len_err <= 5.0

    print("  -> %s" % ("PASS" if ok else "FAIL"))
    return {"gate": "a", "pass": bool(ok), "N": N, "L_cm": L,
            "ideal": ideal, "twin": twin, "rendered": got, "err_pct": errs}


if __name__ == "__main__":
    r = main()
    sys.exit(0 if r["pass"] else 1)
