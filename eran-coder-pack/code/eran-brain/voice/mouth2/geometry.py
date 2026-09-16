# -*- coding: utf-8 -*-
"""geometry.py -- the child vocal tract geometry authority for MOUTH v2.

Single canonical source for "what shape is ERAN's tract". Retires the
7-section / 34-section / age-parameter schism: every other module asks
this one.

PROVENANCE -- real published numbers, not invented ones
=======================================================
Story, B. H., Vorperian, H. K., Bunton, K., and Durtschi, R. B. (2018).
"An age-dependent vocal tract model for males and females based on
anatomic measurements," J. Acoust. Soc. Am. 143(5), 3079-3102.
Open access: PMC5966313 (fetched 2026-08-26, tables transcribed verbatim
from the HTML full text -- these are the paper's numbers, NOT fits of ours).

The model (paper Eq. 1):

    A(i) = (pi/4) * [ Omega(i) + q1*phi1(i) + q2*phi2(i) ]^2

where Omega(i) is the neutral DIAMETER function (cm), phi1/phi2 are the
two principal modes (cm), q1/q2 dimensionless vowel coefficients, over
Nx = 44 elements, element 1 just above the glottis, element 44 the lips.

Transcribed here:
  * Table III -- Omega, phi1, phi2 for the MALE model at ages
    0, 4, 8, 12 yr and adult (asterisk = the original Story 2008 adult),
    plus the per-age uniform element length L(i) and total VTL.
  * Table I   -- male VTL(age) for ages 0..12 yr (used as a cross-check).
  * Table II  -- vowel mode coefficients (q1, q2), derived on the adult
    male and by the paper's design applicable at every age (the modes
    are scaled along with Omega).

WHAT IS APPROXIMATED (honest list)
==================================
1. Ages between the published columns (0/4/8/12 yr): the paper generates
   any age via double-logistic growth curves whose fitted coefficients
   are NOT published numerically (only Fig. 4 plots). Instead:
   - tract LENGTH comes straight from Table I, which publishes VTL at
     every integer age 0..12 yr (linear inside each 1-yr span) -- so
     length error at integer ages is zero by construction;
   - the diameter COMPONENTS (Omega, phi1, phi2) are linearly
     interpolated element-wise between the published 0/4/8/12-yr
     columns. Measured in the first __main__ check before this anchor
     was added: pure component interpolation put VTL off by up to 7%
     at ages 1-3 yr (fast nonlinear growth), <0.3% at ages >= 4 yr --
     that is the size of the residual SHAPE approximation at 1-3 yr.
     At our target age (60 months) the residual is ~0.1%.
2. Ages above 144 months blend linearly toward the adult column placed
   at 252 months (21 yr) -- OUR placement, not the paper's; anything
   above 144 months is a convenience extrapolation, clamped at adult.
3. The paper's kappa(i) warping (Eqs. 3-4) is NOT re-implemented -- the
   per-age Table III columns already contain its result. Nothing is
   lost for the published ages; intermediate ages inherit approximation 1.
4. nasal_geometry() is NOT from Story & Bunton (their model has no nasal
   tract). Length ratio and junction position follow Pink Trombone's
   proportions (noseLength/n = 28/44, noseStart/n = 17/44); the area
   profile is PT's hump shape scaled to a child maximum of 1.2 cm^2.
   Documented guess, to be validated against VTL/Dresden later.

House rules: numpy + scipy.interpolate.PchipInterpolator only. No torch.
No synthesis here -- this module only makes area functions.
"""
from __future__ import annotations

import numpy as np
from scipy.interpolate import PchipInterpolator

C_SOUND = 35000.0  # cm/s, same constant as tract_analytic.py

N_ELEMENTS = 44    # paper's Nx; element 1 just above glottis, 44 = lips

# ----------------------------------------------------------------------
# Table III (male): Omega(i), phi1(i), phi2(i) in cm, elements 1..44.
# Transcribed verbatim from PMC5966313 Table III (2026-08-26).
# ----------------------------------------------------------------------

_OMEGA_ADULT = np.array([
    0.80, 0.74, 0.71, 0.72, 0.85, 1.10, 1.35, 1.47,
    1.44, 1.39, 1.38, 1.42, 1.46, 1.49, 1.49, 1.49,
    1.50, 1.53, 1.57, 1.59, 1.58, 1.57, 1.56, 1.56,
    1.53, 1.50, 1.46, 1.46, 1.52, 1.60, 1.68, 1.76,
    1.86, 1.97, 2.06, 2.13, 2.17, 2.13, 2.01, 1.84,
    1.69, 1.55, 1.43, 1.31])
_PHI1_ADULT = np.array([
    0.004, -0.014, -0.029, -0.042, -0.054, -0.066, -0.078, -0.091,
    -0.105, -0.120, -0.137, -0.153, -0.170, -0.184, -0.195, -0.203,
    -0.205, -0.201, -0.191, -0.174, -0.149, -0.118, -0.082, -0.040,
    0.005, 0.051, 0.097, 0.141, 0.180, 0.213, 0.238, 0.255,
    0.261, 0.257, 0.244, 0.221, 0.192, 0.158, 0.122, 0.089,
    0.061, 0.043, 0.038, 0.047])
_PHI2_ADULT = np.array([
    0.003, -0.020, -0.052, -0.084, -0.109, -0.124, -0.131, -0.129,
    -0.121, -0.108, -0.092, -0.073, -0.053, -0.032, -0.009, 0.015,
    0.040, 0.067, 0.095, 0.123, 0.150, 0.176, 0.198, 0.214,
    0.224, 0.224, 0.214, 0.193, 0.160, 0.117, 0.066, 0.009,
    -0.048, -0.100, -0.140, -0.163, -0.160, -0.129, -0.065, 0.028,
    0.141, 0.256, 0.344, 0.356])

_OMEGA_12YR = np.array([
    0.58, 0.53, 0.52, 0.55, 0.71, 0.94, 1.08, 1.09,
    1.05, 1.05, 1.08, 1.12, 1.15, 1.15, 1.16, 1.18,
    1.21, 1.24, 1.26, 1.25, 1.25, 1.26, 1.26, 1.24,
    1.21, 1.21, 1.24, 1.32, 1.40, 1.48, 1.56, 1.66,
    1.76, 1.84, 1.91, 1.95, 1.94, 1.86, 1.74, 1.63,
    1.53, 1.44, 1.35, 1.26])
_PHI1_12YR = np.array([
    0.003, -0.011, -0.024, -0.035, -0.044, -0.054, -0.065, -0.077,
    -0.090, -0.104, -0.118, -0.132, -0.144, -0.153, -0.158, -0.159,
    -0.155, -0.144, -0.128, -0.106, -0.079, -0.047, -0.012, 0.026,
    0.064, 0.101, 0.136, 0.167, 0.193, 0.212, 0.224, 0.229,
    0.226, 0.215, 0.198, 0.175, 0.148, 0.120, 0.092, 0.067,
    0.049, 0.038, 0.036, 0.045])
_PHI2_12YR = np.array([
    0.002, -0.017, -0.044, -0.069, -0.087, -0.096, -0.097, -0.092,
    -0.083, -0.070, -0.055, -0.038, -0.021, -0.002, 0.018, 0.039,
    0.062, 0.085, 0.108, 0.131, 0.151, 0.168, 0.180, 0.184,
    0.182, 0.170, 0.149, 0.120, 0.082, 0.039, -0.008, -0.054,
    -0.095, -0.128, -0.146, -0.145, -0.123, -0.077, -0.008, 0.080,
    0.178, 0.271, 0.331, 0.342])

_OMEGA_8YR = np.array([
    0.50, 0.46, 0.45, 0.49, 0.65, 0.85, 0.95, 0.93,
    0.91, 0.92, 0.95, 0.99, 1.00, 1.00, 1.02, 1.04,
    1.07, 1.09, 1.10, 1.10, 1.10, 1.11, 1.10, 1.08,
    1.07, 1.09, 1.15, 1.23, 1.30, 1.38, 1.46, 1.56,
    1.65, 1.72, 1.78, 1.81, 1.79, 1.70, 1.59, 1.50,
    1.42, 1.35, 1.28, 1.21])
_PHI1_8YR = np.array([
    0.003, -0.010, -0.021, -0.031, -0.040, -0.049, -0.058, -0.069,
    -0.081, -0.094, -0.107, -0.119, -0.129, -0.136, -0.139, -0.137,
    -0.131, -0.119, -0.102, -0.079, -0.053, -0.023, 0.010, 0.044,
    0.077, 0.109, 0.139, 0.164, 0.185, 0.199, 0.207, 0.208,
    0.202, 0.191, 0.173, 0.152, 0.128, 0.103, 0.079, 0.058,
    0.043, 0.036, 0.035, 0.044])
_PHI2_8YR = np.array([
    0.002, -0.016, -0.040, -0.062, -0.077, -0.084, -0.084, -0.078,
    -0.069, -0.056, -0.043, -0.027, -0.011, 0.006, 0.024, 0.044,
    0.064, 0.085, 0.106, 0.125, 0.142, 0.155, 0.161, 0.163,
    0.156, 0.141, 0.119, 0.088, 0.052, 0.012, -0.030, -0.070,
    -0.103, -0.128, -0.134, -0.130, -0.102, -0.053, 0.014, 0.097,
    0.185, 0.269, 0.317, 0.328])

_OMEGA_4YR = np.array([
    0.43, 0.40, 0.39, 0.43, 0.58, 0.75, 0.82, 0.80,
    0.79, 0.80, 0.84, 0.86, 0.87, 0.87, 0.88, 0.91,
    0.93, 0.94, 0.94, 0.95, 0.96, 0.96, 0.95, 0.93,
    0.95, 0.99, 1.06, 1.13, 1.21, 1.28, 1.37, 1.46,
    1.54, 1.60, 1.65, 1.66, 1.63, 1.55, 1.46, 1.38,
    1.31, 1.25, 1.19, 1.13])
_PHI1_4YR = np.array([
    0.002, -0.009, -0.019, -0.027, -0.035, -0.043, -0.052, -0.062,
    -0.073, -0.084, -0.096, -0.106, -0.114, -0.119, -0.120, -0.117,
    -0.108, -0.095, -0.078, -0.056, -0.031, -0.003, 0.026, 0.056,
    0.085, 0.112, 0.137, 0.157, 0.174, 0.184, 0.189, 0.188,
    0.181, 0.169, 0.153, 0.133, 0.111, 0.089, 0.069, 0.051,
    0.038, 0.033, 0.033, 0.041])
_PHI2_4YR = np.array([
    0.002, -0.014, -0.036, -0.055, -0.068, -0.073, -0.072, -0.066,
    -0.057, -0.046, -0.033, -0.020, -0.005, 0.011, 0.028, 0.046,
    0.064, 0.082, 0.100, 0.116, 0.130, 0.139, 0.141, 0.139,
    0.130, 0.114, 0.090, 0.061, 0.028, -0.009, -0.045, -0.078,
    -0.105, -0.122, -0.123, -0.113, -0.083, -0.036, 0.028, 0.103,
    0.183, 0.257, 0.297, 0.307])

_OMEGA_0YR = np.array([
    0.34, 0.31, 0.31, 0.32, 0.41, 0.55, 0.63, 0.63,
    0.61, 0.61, 0.63, 0.65, 0.67, 0.67, 0.67, 0.68,
    0.70, 0.72, 0.72, 0.72, 0.72, 0.72, 0.72, 0.70,
    0.69, 0.69, 0.71, 0.74, 0.78, 0.82, 0.87, 0.92,
    0.98, 1.03, 1.07, 1.08, 1.07, 1.03, 0.99, 0.98,
    0.97, 0.96, 0.95, 0.92])
_PHI1_0YR = np.array([
    0.002, -0.007, -0.014, -0.020, -0.026, -0.032, -0.038, -0.044,
    -0.052, -0.060, -0.068, -0.076, -0.083, -0.089, -0.092, -0.092,
    -0.089, -0.083, -0.073, -0.060, -0.044, -0.025, -0.004, 0.018,
    0.040, 0.062, 0.081, 0.097, 0.110, 0.118, 0.122, 0.121,
    0.116, 0.108, 0.097, 0.084, 0.070, 0.056, 0.043, 0.034,
    0.027, 0.025, 0.026, 0.033])
_PHI2_0YR = np.array([
    0.001, -0.010, -0.026, -0.040, -0.051, -0.056, -0.057, -0.054,
    -0.048, -0.041, -0.032, -0.022, -0.012, -0.001, 0.011, 0.023,
    0.036, 0.049, 0.063, 0.076, 0.088, 0.097, 0.103, 0.105,
    0.102, 0.094, 0.079, 0.059, 0.034, 0.007, -0.020, -0.045,
    -0.066, -0.078, -0.079, -0.070, -0.047, -0.010, 0.038, 0.094,
    0.153, 0.210, 0.238, 0.248])

# Age knots in months. 252 mo (21 yr) for "adult" is OUR placement
# (approximation 2 in the header) -- the paper anchors only 0..144.
_AGE_KNOTS_MONTHS = np.array([0.0, 48.0, 96.0, 144.0, 252.0])
_OMEGA_BY_AGE = np.stack([_OMEGA_0YR, _OMEGA_4YR, _OMEGA_8YR, _OMEGA_12YR, _OMEGA_ADULT])
_PHI1_BY_AGE = np.stack([_PHI1_0YR, _PHI1_4YR, _PHI1_8YR, _PHI1_12YR, _PHI1_ADULT])
_PHI2_BY_AGE = np.stack([_PHI2_0YR, _PHI2_4YR, _PHI2_8YR, _PHI2_12YR, _PHI2_ADULT])
# Per-age uniform element length L(i) and VTL, from the bottom of Table III.
_ELEM_LEN_BY_AGE = np.array([0.192, 0.264, 0.296, 0.330, 0.400])
_VTL_BY_AGE = np.array([8.45, 11.62, 13.02, 14.52, 17.60])

# Table I (male): VTL in cm at integer ages 0..12 yr. This is the
# length authority for ages 0-144 months (see approximation note 1).
TABLE_I_MALE_VTL = np.array([
    8.47, 9.95, 10.75, 11.24, 11.63, 11.98, 12.32,
    12.67, 13.02, 13.38, 13.75, 14.13, 14.51])
_VTL_KNOTS_MONTHS = np.concatenate([np.arange(13) * 12.0, [252.0]])
_VTL_KNOTS_CM = np.concatenate([TABLE_I_MALE_VTL, [17.6]])

# Table II: vowel mode coefficients (q1, q2). Keys are IPA-ish ASCII.
VOWEL_MODES = {
    "i":  (-5.10,  0.88),
    "I":  (-2.57,  0.93),   # /ɪ/
    "E":  (-1.07,  1.22),   # /ɛ/
    "ae": ( 0.66,  2.22),   # /æ/
    "V":  ( 2.55,  0.10),   # /ʌ/
    "a":  ( 3.86,  1.35),   # /ɑ/  -- the /a/ preset
    "O":  ( 3.47, -0.45),   # /ɔ/
    "o":  ( 0.00, -2.69),
    "U":  ( 1.68, -1.87),   # /ʊ/
    "u":  (-3.48, -1.70),
}

_D_MIN_CM = 0.01  # diameter floor: keeps areas positive (paper clips at 0 too)


def _components_at_age(age_months):
    """Omega, phi1, phi2, element_length at an age, by linear interpolation
    between the published columns (approximations 1-2 in the header)."""
    a = float(np.clip(age_months, _AGE_KNOTS_MONTHS[0], _AGE_KNOTS_MONTHS[-1]))
    omega = np.array([np.interp(a, _AGE_KNOTS_MONTHS, _OMEGA_BY_AGE[:, i])
                      for i in range(N_ELEMENTS)])
    phi1 = np.array([np.interp(a, _AGE_KNOTS_MONTHS, _PHI1_BY_AGE[:, i])
                     for i in range(N_ELEMENTS)])
    phi2 = np.array([np.interp(a, _AGE_KNOTS_MONTHS, _PHI2_BY_AGE[:, i])
                     for i in range(N_ELEMENTS)])
    # Length is anchored to Table I (published at every integer age),
    # not to the sparser Table III columns -- approximation note 1.
    elem_len = float(np.interp(a, _VTL_KNOTS_MONTHS, _VTL_KNOTS_CM)) / N_ELEMENTS
    return omega, phi1, phi2, elem_len


def child_area(age_months=60, vowel=None):
    """Area function for a male child of `age_months` (paper Eq. 1).

    vowel: None for the neutral tract, or a key of VOWEL_MODES
    ("a", "i", "u", ...), or a (q1, q2) tuple.

    Returns (length_cm, areas_cm2): total tract length and 44 areas,
    element 1 just above the glottis, element 44 at the lips.
    """
    omega, phi1, phi2, elem_len = _components_at_age(age_months)
    if vowel is None:
        q1 = q2 = 0.0
    elif isinstance(vowel, str):
        q1, q2 = VOWEL_MODES[vowel]
    else:
        q1, q2 = float(vowel[0]), float(vowel[1])
    diam = omega + q1 * phi1 + q2 * phi2
    diam = np.maximum(diam, _D_MIN_CM)
    areas = (np.pi / 4.0) * diam ** 2
    return elem_len * N_ELEMENTS, areas


def resample_areas(areas, n_sections):
    """Resample an area function to n_sections by linear interpolation at
    section centers. Length is unchanged (it belongs to the caller)."""
    a = np.asarray(areas, dtype=float)
    src = (np.arange(a.size) + 0.5) / a.size
    dst = (np.arange(n_sections) + 0.5) / n_sections
    return np.interp(dst, src, a)


def spline_knots_to_areas(knots8, n_sections):
    """8 control stations, glottis->lips, PCHIP-interpolated on LOG area.

    knots8: 8 areas in cm^2 at stations equally spaced from glottis (0)
    to lips (1). PCHIP on log-area is shape-preserving: no negative-area
    overshoot, no spurious constrictions between knots.
    Returns n_sections areas at section centers.
    """
    k = np.asarray(knots8, dtype=float)
    if k.shape != (8,):
        raise ValueError("knots8 must have exactly 8 values, got %r" % (k.shape,))
    k = np.maximum(k, 1e-3)  # log needs positive; 0.001 cm^2 = sealed for our use
    stations = np.linspace(0.0, 1.0, 8)
    f = PchipInterpolator(stations, np.log(k))
    centers = (np.arange(n_sections) + 0.5) / n_sections
    return np.exp(f(centers))


def spline_knots_to_areas_batch(knots_mat, n_sections):
    """Batched spline_knots_to_areas: (B, 8) -> (B, n_sections).

    BIT-IDENTICAL to calling spline_knots_to_areas row by row -- PCHIP's
    derivative formulas and the evaluation are elementwise along the
    batch axis, so PchipInterpolator(..., axis=0) on stacked columns
    computes exactly the per-row numbers. VERIFIED 2026-08-26 on 2000
    random rows, np.array_equal True, on BOTH the PC and eran2 (their
    scipy versions differ). Exists because say_gesture's per-1-ms-block
    loop made 500 PchipInterpolator constructions per render (~109 ms of
    a 113 ms C-backend render, measured pinned on eran2)."""
    k = np.asarray(knots_mat, dtype=float)
    if k.ndim != 2 or k.shape[1] != 8:
        raise ValueError("knots_mat must be (B, 8), got %r" % (k.shape,))
    k = np.maximum(k, 1e-3)
    stations = np.linspace(0.0, 1.0, 8)
    f = PchipInterpolator(stations, np.log(k).T, axis=0)
    centers = (np.arange(n_sections) + 0.5) / n_sections
    return np.exp(f(centers)).T


def constriction_batch(areas_mat, c_pos, c_area, width_cm=1.5,
                       length_cm=12.0):
    """Batched constriction: (B, n) areas + (B,) c_pos/c_area -> (B, n).

    BIT-IDENTICAL to calling constriction row by row (same elementwise
    expressions, broadcast over the batch axis; verified 2026-08-26 on
    2000 random rows on both PC and eran2)."""
    a = np.asarray(areas_mat, dtype=float)
    cp = np.asarray(c_pos, dtype=float)[:, None]
    ca = np.asarray(c_area, dtype=float)[:, None]
    x = (np.arange(a.shape[1]) + 0.5) / a.shape[1]
    sigma = (width_cm / 2.0) / length_cm
    w = np.exp(-0.5 * ((x[None, :] - cp) / max(sigma, 1e-6)) ** 2)
    log_a = np.log(np.maximum(a, 1e-6))
    log_c = np.log(np.maximum(ca, 1e-6))
    return np.exp((1.0 - w) * log_a + w * log_c)


def constriction(areas, c_pos, c_area, width_cm=1.5, length_cm=12.0):
    """Constrict an area function with a Gaussian multiplicative window.

    c_pos: constriction center, normalized 0 (glottis) .. 1 (lips).
    c_area: target area cm^2 AT the center (reached exactly).
    width_cm: Gaussian sigma*2 (window is ~width_cm wide); length_cm
    converts it to normalized units, so pass the real tract length.

    Multiplicative in log-area: A' = A * (c_area/A)^w with w the
    Gaussian; w=1 at the center, ->0 away, so the rest of the tract
    is untouched -- the Pink Trombone style of imposing a constriction.
    Only ever narrows (w clamped where c_area > local area? no --
    a "constriction" wider than the tract would be a dilation; we allow
    it, callers decide. Documented, not hidden.)
    """
    a = np.asarray(areas, dtype=float)
    x = (np.arange(a.size) + 0.5) / a.size
    sigma = (width_cm / 2.0) / length_cm  # normalized units
    w = np.exp(-0.5 * ((x - c_pos) / max(sigma, 1e-6)) ** 2)
    log_a = np.log(np.maximum(a, 1e-6))
    log_c = np.log(max(c_area, 1e-6))
    return np.exp((1.0 - w) * log_a + w * log_c)


def nasal_geometry(main_length_cm, n_sections=28):
    """Nasal tract for a child: NOT from Story & Bunton (approximation 4).

    Proportions follow Pink Trombone: nasal length = (28/44) x main
    (~0.64), velum junction at station 17/44 of the main tract from the
    glottis. Area profile is PT's rise/fall hump, rescaled so the child
    maximum is 1.2 cm^2 (adult nasal max ~= 2-3 cm^2; child smaller).

    Returns dict:
      length_cm       -- nasal tract length
      areas_cm2       -- n_sections areas, velum port (index 0) -> nostrils
      junction_frac   -- where on the MAIN tract the branch attaches,
                         as a fraction of its length from the glottis
    """
    frac = np.arange(n_sections) / n_sections  # 0 at velum port
    d = 2.0 * frac
    diam = np.where(d < 1.0, 0.4 + 1.6 * d, 0.5 + 1.5 * (2.0 - d))
    diam = np.minimum(diam, 1.9)               # PT's cap
    prof = diam ** 2                           # PT uses diameter^2 as "area"
    areas = prof / prof.max() * 1.2            # child max 1.2 cm^2
    areas = np.maximum(areas, 0.05)
    return {
        "length_cm": 0.64 * float(main_length_cm),   # 28/44 = 0.636..., rounded per plan
        "areas_cm2": areas,
        "junction_frac": 17.0 / 44.0,
    }


# ----------------------------------------------------------------------
# Ballpark formant estimates (closed-form, NO synthesis) for __main__.
# ----------------------------------------------------------------------

def _two_tube_ballpark(length_cm, areas):
    """Very coarse two-tube F1/F2 estimate. Split at the interior area
    minimum; classic recipes (Fant): back constriction (/a/-like) ->
    two quarter-wave tubes; front constriction (/i u/-like) -> Helmholtz
    F1 + back-cavity half-wave F2. Ballpark only -- the real answer
    comes from analytic2.py."""
    a = np.asarray(areas, dtype=float)
    n = a.size
    dx = length_cm / n
    lo, hi = int(0.15 * n), int(0.95 * n)
    c_idx = lo + int(np.argmin(a[lo:hi]))
    L_back = (c_idx + 0.5) * dx
    L_front = length_cm - L_back
    if c_idx < n // 2:  # back/pharyngeal constriction, /a/-like
        f_a = C_SOUND / (4.0 * max(L_back, 1e-3))
        f_b = C_SOUND / (4.0 * max(L_front, 1e-3))
        return min(f_a, f_b), max(f_a, f_b)
    # front constriction: Helmholtz resonator (back cavity + neck)
    neck = a[c_idx:min(c_idx + max(2, n // 10), n)]
    A_c = float(neck.mean())
    L_c = neck.size * dx
    V_b = float(a[:c_idx].sum() * dx)
    f1 = (C_SOUND / (2 * np.pi)) * np.sqrt(A_c / max(V_b * L_c, 1e-6))
    f2 = C_SOUND / (2.0 * max(L_back, 1e-3))
    return f1, f2


if __name__ == "__main__":
    print("GEOMETRY self-check -- Story & Bunton 2018 male model")
    print("=" * 64)

    # 1. Interpolated VTL vs the paper's own Table I, every integer age.
    print("\nVTL cross-check vs Table I (male), linear age interpolation:")
    worst = 0.0
    for yr in range(13):
        L, _ = child_area(age_months=12 * yr)
        want = TABLE_I_MALE_VTL[yr]
        err = abs(L - want) / want * 100
        worst = max(worst, err)
        flag = "" if err < 1.0 else "  <-- >1%"
        print("  age %2d yr: model %6.2f cm   Table I %6.2f cm   err %.2f%%%s"
              % (yr, L, want, err, flag))
    print("  worst error: %.2f%%  (%s)" % (worst, "OK <1%" if worst < 1.0 else "FAIL"))

    # 2. The 60-month child.
    L, neutral = child_area(60)
    print("\n60-month (5 yr) male child:")
    print("  tract length   %.2f cm  (Table I age-5: 11.98 cm)" % L)
    print("  neutral areas  min %.2f  max %.2f  mean %.2f cm^2"
          % (neutral.min(), neutral.max(), neutral.mean()))
    print("  quarter-wave neutral F1 = c/4L = %.0f Hz, 3c/4L = %.0f Hz"
          % (C_SOUND / (4 * L), 3 * C_SOUND / (4 * L)))

    # 3. Vowel presets + closed-form ballparks. Published child ~5 yr
    #    values for orientation (Vorperian & Kent 2007 review, approx):
    #    /a/ F1~1000 F2~1600; /i/ F1~450 F2~3000; /u/ F1~500 F2~1300.
    print("\nVowel presets (Eq. 1 with Table II q1,q2) + 2-tube ballpark:")
    print("  %-4s %8s %8s %10s %10s" % ("v", "Amin", "Amax", "~F1", "~F2"))
    for v in ("a", "i", "u"):
        Lv, av = child_area(60, vowel=v)
        f1, f2 = _two_tube_ballpark(Lv, av)
        print("  %-4s %8.2f %8.2f %10.0f %10.0f" % (v, av.min(), av.max(), f1, f2))
    print("  (ballpark closed-form only; trust analytic2.py, not this)")

    # 4. Utility round-trips.
    r34 = resample_areas(neutral, 34)
    assert r34.shape == (34,) and abs(r34.mean() - neutral.mean()) / neutral.mean() < 0.05
    knots = np.interp(np.linspace(0, 1, 8), (np.arange(44) + 0.5) / 44, neutral)
    spl = spline_knots_to_areas(knots, 44)
    spl_err = np.median(np.abs(np.log(spl) - np.log(neutral)))
    print("\nspline_knots_to_areas: median |log-area| error vs neutral "
          "when knots sampled FROM it: %.3f (coarse 8-knot summary, "
          "expected small but nonzero)" % spl_err)
    con = constriction(neutral, c_pos=0.85, c_area=0.05, length_cm=L)
    i_min = int(np.argmin(con))
    print("constriction(0.85, 0.05): min area %.3f cm^2 at station %.2f "
          "(asked 0.85)" % (con.min(), (i_min + 0.5) / 44))
    assert abs(con.min() - 0.05) < 0.005
    nas = nasal_geometry(L)
    print("nasal_geometry: length %.2f cm (0.64 x %.2f), max area %.2f cm^2, "
          "junction at %.3f of main tract"
          % (nas["length_cm"], L, nas["areas_cm2"].max(), nas["junction_frac"]))
    print("\nself-check done.")
