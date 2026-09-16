# -*- coding: utf-8 -*-
"""analytic2.py -- branched-tube transfer function for MOUTH v2.

Frequency-domain transmission-matrix (ABCD) computation of the
volume-velocity transfer function U_out/U_source of a chain of
cylindrical sections, with an OPTIONAL side branch (the nasal tract)
shunted at a junction. No audio, no LPC, no peak-picking of spectra
estimated from synthesis -- the transfer function is computed exactly
from the geometry (lossless sections + resistive terminations).

TWO ENGINES, ONE FINDING (2026-08-26, measured, not assumed)
============================================================
While building the required "reduce to tract_analytic" self-test, the
old ladder's overtone structure was probed directly:

    uniform 24-section tube, tract_analytic calibration (L = 12 cm):
        ladder resonances:  728, 1455, 2182, 2910 Hz  (EQUALLY spaced)
        physical closed-open tube: 729, 2188, 3646 Hz  (ODD multiples of c/4L)

    The step-up polynomial with the terminations appended as two extra
    reflection coefficients factors (uniform case, k_interior = 0) as
        A(z) = (1 + 0.9 z^-1) - 0.85 z^-(n+1) (1 + 0.9 z)
    whose roots are equally spaced around the circle -- the mode
    structure of a SAME-SIGN-terminated (closed-closed-like) resonator,
    not of the closed-open tube the constants intend. F1 lands on c/4L
    because the 2026-08-23 "factor of two" calibration pinned it there;
    F2 of a uniform tube then sits at 2*(c/4L), where a real closed-open
    tube (and a real schwa: ~500/1500/2500 Hz at 17.5 cm) has 3*(c/4L).

So:
  * `transfer_function()` / `resonances_physical()` -- the PHYSICAL
    model. Uniform closed-open tube gives odd multiples of c/4L
    (self-test 1). This is the engine MOUTH v2 builds on; the Dresden
    measured transfer functions are its ground truth (dresden_check.py).
  * `ladder_compat_resonances()` -- a genuine transfer-matrix chain in
    the ladder's own travelling-wave variables (half-sample section
    delays, terminations as reflection coefficients), which reproduces
    tract_analytic.resonances (self-test 2, <1% on random shapes).
    Kept as the bridge to every number the project printed before.

Conventions shared with the house: C_SOUND = 35000 cm/s,
glottal_reflect = 0.9, lip_reflect = -0.85 (pressure-wave reflectances;
Z = Zc (1+r)/(1-r), so the glottis is nearly rigid, the lips nearly
open). Sections are lossless; all damping comes from the resistive
terminations -- same regime as the old ladder, honest about it.
numpy only (scipy unused here).
"""
from __future__ import annotations

import numpy as np

C_SOUND = 35000.0        # cm/s
RHO = 1.14e-3            # g/cm^3, air; only enters via Zc = rho*c/A ratios
GLOTTAL_REFLECT = 0.9
LIP_REFLECT = -0.85


def _z_from_reflect(r, zc):
    """Termination impedance from a pressure reflectance: Z = Zc(1+r)/(1-r)."""
    return zc * (1.0 + r) / (1.0 - r)


def _chain_abcd(areas, sec_len_cm, w):
    """Cumulative ABCD (pressure/volume-velocity) matrices of a section
    chain at angular frequencies w. Returns (A, B, C, D) arrays over w
    for the WHOLE chain, glottis side to lip side."""
    A = np.ones_like(w, dtype=complex)
    B = np.zeros_like(w, dtype=complex)
    C = np.zeros_like(w, dtype=complex)
    D = np.ones_like(w, dtype=complex)
    k = w / C_SOUND
    for a_cm2, l_cm in zip(areas, sec_len_cm):
        zc = RHO * C_SOUND / a_cm2
        kl = k * l_cm
        ca, sa = np.cos(kl), np.sin(kl)
        A2 = A * ca + B * (1j * sa / zc)
        B2 = A * (1j * zc * sa) + B * ca
        C2 = C * ca + D * (1j * sa / zc)
        D2 = C * (1j * zc * sa) + D * ca
        A, B, C, D = A2, B2, C2, D2
    return A, B, C, D


def _branch_input_admittance(areas, sec_len_cm, w, term_reflect=LIP_REFLECT):
    """Input admittance of a terminated side branch (e.g. the nasal tract
    seen from the velum port), plus the chain matrices for later use."""
    A, B, C, D = _chain_abcd(areas, sec_len_cm, w)
    zc_end = RHO * C_SOUND / areas[-1]
    z_term = _z_from_reflect(term_reflect, zc_end)
    z_in = (A * z_term + B) / (C * z_term + D)
    return 1.0 / z_in, (A, B, C, D, z_term)


def transfer_function(areas, length_cm, freqs,
                      glottal_reflect=GLOTTAL_REFLECT,
                      lip_reflect=LIP_REFLECT,
                      nasal_areas=None, nasal_length_cm=None,
                      velum_area_cm2=0.0, junction_frac=17.0 / 44.0,
                      nostril_reflect=LIP_REFLECT):
    """Volume-velocity transfer function(s) of the (optionally branched) tract.

    areas: main-tract areas cm^2, glottis->lips, uniform section length
    length_cm / len(areas). freqs: Hz array.

    Nasal branch: if velum_area_cm2 > 0 and nasal_areas is given, a side
    branch is shunted at junction_frac of the main length; its first
    section (the velopharyngeal port) area is REPLACED by velum_area_cm2.
    velum_area_cm2 = 0 reduces EXACTLY to the unbranched chain
    (asserted in the self-test).

    Returns dict:
      f        -- the frequency grid
      H_lip    -- complex U_lip / U_source
      H_nose   -- complex U_nostril / U_source (zeros if no branch)
    """
    a = np.asarray(areas, dtype=float)
    n = a.size
    w = 2 * np.pi * np.asarray(freqs, dtype=float)
    sec = np.full(n, length_cm / n)

    zc_g = RHO * C_SOUND / a[0]
    zc_l = RHO * C_SOUND / a[-1]
    z_g = _z_from_reflect(glottal_reflect, zc_g)
    z_l = _z_from_reflect(lip_reflect, zc_l)

    branched = (velum_area_cm2 > 0.0 and nasal_areas is not None)
    if not branched:
        A, B, C, D = _chain_abcd(a, sec, w)
        denom = z_g * (C * z_l + D) + (A * z_l + B)
        H_lip = z_g / denom
        return {"f": np.asarray(freqs, float), "H_lip": H_lip,
                "H_nose": np.zeros_like(H_lip)}

    j = int(round(junction_frac * n))
    j = min(max(j, 1), n - 1)
    A1, B1, C1, D1 = _chain_abcd(a[:j], sec[:j], w)          # glottis -> junction
    A2, B2, C2, D2 = _chain_abcd(a[j:], sec[j:], w)          # junction -> lips

    na = np.asarray(nasal_areas, dtype=float).copy()
    na[0] = velum_area_cm2
    nsec = np.full(na.size, float(nasal_length_cm) / na.size)
    Y_n, (An, Bn, Cn, Dn, z_nostril) = _branch_input_admittance(
        na, nsec, w, term_reflect=nostril_reflect)

    # Downstream of the junction: P_j = (A2 z_l + B2) U_lip ; U_after = (C2 z_l + D2) U_lip
    P_j_per_Ulip = A2 * z_l + B2
    U_after_per_Ulip = C2 * z_l + D2
    U_nasal_per_Ulip = P_j_per_Ulip * Y_n
    U_before_per_Ulip = U_after_per_Ulip + U_nasal_per_Ulip
    # Upstream chain maps junction state to the glottis port:
    P_g_per_Ulip = A1 * P_j_per_Ulip + B1 * U_before_per_Ulip
    U_g_per_Ulip = C1 * P_j_per_Ulip + D1 * U_before_per_Ulip
    # Norton source U_src with internal impedance z_g at the glottis port:
    U_src_per_Ulip = U_g_per_Ulip + P_g_per_Ulip / z_g
    H_lip = 1.0 / U_src_per_Ulip
    # Within the branch: U_nostril = U_nasal_in / (Cn z_nostril + Dn)
    H_nose = (U_nasal_per_Ulip / (Cn * z_nostril + Dn)) * H_lip
    return {"f": np.asarray(freqs, float), "H_lip": H_lip, "H_nose": H_nose}


def peak_pick(f, mag, n=4, fmin=120.0, fmax=None):
    """Local maxima of a magnitude curve, lowest first, parabolic refine."""
    f = np.asarray(f, float)
    m = np.asarray(mag, float)
    if fmax is None:
        fmax = f[-1] - 1
    out = []
    for i in range(1, f.size - 1):
        if not (fmin <= f[i] <= fmax):
            continue
        if m[i] > m[i - 1] and m[i] >= m[i + 1]:
            d = (m[i - 1] - 2 * m[i] + m[i + 1])
            off = 0.5 * (m[i - 1] - m[i + 1]) / d if d != 0 else 0.0
            out.append(f[i] + off * (f[1] - f[0]))
            if len(out) >= n:
                break
    return out


def resonances_physical(areas, length_cm, n=4, fmax=5000.0, df=1.0):
    """F1..Fn of the unbranched physical tract, Hz."""
    freqs = np.arange(60.0, fmax, df)
    tf = transfer_function(areas, length_cm, freqs)
    return peak_pick(freqs, np.abs(tf["H_lip"]), n=n)


# ----------------------------------------------------------------------
# Ladder-compat engine: travelling-wave transfer matrices that reproduce
# the OLD tract_analytic ladder (its conventions, including the ones the
# header calls out as non-physical). One junction per area step, PLUS
# the two terminations as reflection coefficients, half-sample delays.
# ----------------------------------------------------------------------

def ladder_compat_response(areas, fs, freqs):
    """|U_out/U_in| of the old ladder, via a 2x2 wave-variable transfer-
    matrix product (independent code path from the step-up recursion).

    Wave pair (F, B) per port. Junction with reflection coefficient k:
        [F_i; B_i] = 1/(1+k) [[1, k], [k, 1]] [F_{i+1}; B_{i+1}]
    Half-sample propagation on each side of a junction:
        [F_left; B_left] = [[z^{+1/2}, 0], [0, z^{-1/2}]] [F_right; B_right]
    Terminations enter exactly as tract_analytic appends them: an extra
    junction k=glottal_reflect before the chain and k=lip_reflect after.
    """
    a = np.asarray(areas, dtype=float)
    k_int = (a[:-1] - a[1:]) / (a[:-1] + a[1:] + 1e-12)
    ks = np.concatenate([[GLOTTAL_REFLECT], k_int, [LIP_REFLECT]])
    w = 2 * np.pi * np.asarray(freqs, float) / fs
    zh = np.exp(0.5j * w)     # z^{+1/2}
    zhi = np.exp(-0.5j * w)   # z^{-1/2}
    # accumulate M = prod over (delay * junction) ... relating input port to output port
    M11 = np.ones_like(w, dtype=complex)
    M12 = np.zeros_like(w, dtype=complex)
    M21 = np.zeros_like(w, dtype=complex)
    M22 = np.ones_like(w, dtype=complex)
    for kk in ks:
        # delay half sample then junction
        J11 = J22 = 1.0 / (1.0 + kk)
        J12 = J21 = kk / (1.0 + kk)
        A11 = zh * J11
        A12 = zh * J12
        A21 = zhi * J21
        A22 = zhi * J22
        N11 = M11 * A11 + M12 * A21
        N12 = M11 * A12 + M12 * A22
        N21 = M21 * A11 + M22 * A21
        N22 = M21 * A12 + M22 * A22
        M11, M12, M21, M22 = N11, N12, N21, N22
    # Output side: forward wave only (B_out = 0). Input: F_in = source.
    #   F_src = M11 F_out  ->  |H| = 1/|M11|
    return 1.0 / np.abs(M11)


def ladder_compat_resonances(areas, fs, n=4, fmax=None, df=1.0):
    """Peak frequencies of the compat engine -- must match
    tract_analytic.resonances within 1% (self-test 2)."""
    if fmax is None:
        fmax = fs / 2 - 200
    freqs = np.arange(100.0, fmax, df)
    mag = ladder_compat_response(areas, fs, freqs)
    return peak_pick(freqs, mag, n=n)


# ----------------------------------------------------------------------
# Self-tests
# ----------------------------------------------------------------------

def _test_uniform_physical():
    """Physical engine: uniform closed-open tube -> odd multiples of c/4L."""
    print("[1] physical engine, uniform tube, odd-multiple law")
    ok = True
    for n_sec, L in ((24, 12.0), (34, 17.0)):
        got = resonances_physical(np.ones(n_sec), L, n=3)
        want = [C_SOUND / (4 * L) * m for m in (1, 3, 5)]
        errs = [abs(g - t) / t * 100 for g, t in zip(got, want)]
        print("    L=%4.1f cm  got %s  want %s  err%% %s"
              % (L, ["%.0f" % g for g in got], ["%.0f" % t for t in want],
                 ["%.2f" % e for e in errs]))
        ok &= all(e < 1.0 for e in errs)
    print("    ->", "PASS" if ok else "FAIL")
    return ok


def _test_ladder_compat():
    """Compat engine vs tract_analytic.resonances, 3 random area vectors."""
    import importlib.util
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location(
        "tract_analytic", os.path.join(here, "..", "tract_analytic.py"))
    ta = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ta)

    print("[2] ladder-compat engine vs tract_analytic.resonances (1% gate)")
    rng = np.random.default_rng(20260826)
    fs = ta.C_SOUND / (4 * 0.5)
    ok = True
    for trial in range(3):
        raw = np.exp(rng.uniform(-0.8, 0.8, 34))
        # smooth a little so shapes are tract-like, not white noise
        areas = np.convolve(raw, np.ones(5) / 5, mode="same") + 0.3
        want = [f for f, _ in ta.resonances(areas, fs, n=3)]
        got = ladder_compat_resonances(areas, fs, n=3)
        errs = [abs(g - t) / t * 100 for g, t in zip(got, want)]
        print("    trial %d  ladder %s  compat %s  err%% %s"
              % (trial, ["%.0f" % t for t in want], ["%.0f" % g for g in got],
                 ["%.3f" % e for e in errs]))
        ok &= len(got) >= 3 and len(want) >= 3 and all(e < 1.0 for e in errs)
    print("    ->", "PASS" if ok else "FAIL")
    return ok


def _test_velum_closed_reduction():
    """Branched code path with velum_area=0 must equal the plain chain."""
    print("[3] velum closed == unbranched chain (exact reduction)")
    import geometry
    L, areas = geometry.child_area(60)
    nas = geometry.nasal_geometry(L)
    freqs = np.arange(60.0, 5000.0, 5.0)
    plain = transfer_function(areas, L, freqs)
    closed = transfer_function(areas, L, freqs,
                               nasal_areas=nas["areas_cm2"],
                               nasal_length_cm=nas["length_cm"],
                               velum_area_cm2=0.0)
    d = np.max(np.abs(plain["H_lip"] - closed["H_lip"]))
    print("    max |dH| = %.2e" % d)
    ok = d == 0.0
    print("    ->", "PASS" if ok else "FAIL")
    return ok


def _test_nasal_antiformant():
    """Child /m/-like: lips sealed, velum open -> antiformant 500-2500 Hz
    in the nasal output."""
    print("[4] nasal antiformant, child /m/-like (lips sealed, velum open)")
    import geometry
    L, areas = geometry.child_area(60)
    areas = areas.copy()
    areas[-3:] = 0.01                      # lip seal
    nas = geometry.nasal_geometry(L)
    freqs = np.arange(60.0, 4000.0, 2.0)
    tf = transfer_function(areas, L, freqs,
                           nasal_areas=nas["areas_cm2"],
                           nasal_length_cm=nas["length_cm"],
                           velum_area_cm2=0.5,
                           junction_frac=nas["junction_frac"])
    mag_db = 20 * np.log10(np.abs(tf["H_nose"]) + 1e-30)
    band = (freqs >= 500) & (freqs <= 2500)
    i_min = np.where(band)[0][np.argmin(mag_db[band])]
    f_dip = freqs[i_min]
    # depth below the higher of the two flanking local maxima
    left_max = mag_db[:i_min].max()
    right_max = mag_db[i_min:].max()
    depth = min(left_max, right_max) - mag_db[i_min]
    # expected: quarter-wave zero of the sealed oral stub beyond the velum
    stub = L * (1 - nas["junction_frac"])
    print("    dip at %.0f Hz, depth %.1f dB below flanking peaks" % (f_dip, depth))
    print("    (oral-stub quarter-wave expectation: c/4*%.2f cm = %.0f Hz)"
          % (stub, C_SOUND / (4 * stub)))
    interior = 500.0 < f_dip < 2500.0
    ok = interior and depth >= 6.0
    print("    ->", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    print("ANALYTIC2 self-tests")
    print("=" * 64)
    results = [_test_uniform_physical(), _test_ladder_compat(),
               _test_velum_closed_reduction(), _test_nasal_antiformant()]
    print("=" * 64)
    print("ALL PASS" if all(results) else "SOME FAILED -- fix before use")
