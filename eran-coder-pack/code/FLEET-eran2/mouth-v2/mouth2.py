# -*- coding: utf-8 -*-
"""mouth2.py -- the public face of MOUTH v2. ERAN's growing mouth.

Three doors, one tract:

  say(areas, f0, seconds, seed)      -- mouth34.say contract, unchanged:
                                        34 areas fenced [0.15, 4.0],
                                        flat f0, velum closed, float32
                                        @16 kHz peak-normalized to 0.7,
                                        None if the render diverges.
  say_sequence(keyframes, glide, seed) -- mouth34.say_sequence contract:
                                        [(areas34, secs), ...], linear
                                        glide over the first 35% of each
                                        segment then hold, state carried
                                        across blocks (never spliced).
  say_gesture(g, seed)               -- the NEW 13-dims-per-keyframe
                                        gesture space (the plan's control
                                        space): spline tract + explicit
                                        constriction + velum + tenseness
                                        + voicing, f0/tenseness contours.

GROWTH LAW COMPLIANCE: the Kelly-Lochbaum core and the say()/
say_sequence() lineage are KEPT (tract_core is a KL ladder; the
contracts above are mouth34's). What grew: a nasal branch (velum), a
maturing larynx (per-period LF source instead of the Rosenberg pulse),
child-length anatomy from geometry.py. Maturation, not transplant.

GESTURE SPACE (13 dims per keyframe, plan Phase 2 "Control space"):
    g = {
      "keyframes":  [[k1..k8, c_pos, c_area, velum, tenseness, voicing],
                     ...],
      "durations":  [seconds per keyframe segment],
      "f0_knots":   [3 knots, Hz, clipped by the renderer to [F0_MIN, F0_MAX]
                     = [90, 350]. The old note here said [200, 500] "genome child
                     band" -- that was the SEARCH's bound, never the tube's, and
                     it is wrong for an adult voice. Corrected 2026-09-02.],
      "tenseness_knots": [3 knots, clipped to [0.25, 0.95]],
      "glide":      optional, default 0.35 (mouth34 convention),
    }
    k1..k8    log2-AREA at 8 stations glottis->lips (PCHIP on log area
              via geometry.spline_knots_to_areas); resulting areas are
              fenced to [0.15, 4.0] BEFORE the constriction is imposed.
    c_pos     constriction center, clipped [0.30, 1.00] of tract length
    c_area    constriction area cm^2, clipped [0, 2]; < 0.01 = SEALED
    velum     velopharyngeal port area cm^2, clipped [0, 0.8]
    tenseness per-keyframe multiplier on the utterance contour:
              effective(t) = clip(contour(t) * kf(t)/0.6, 0.25, 0.95)
              (0.6 = the house reference tenseness, so keyframes that
              say 0.6 leave the contour untouched -- documented choice)
    voicing   0..1 -> the glottal intensity envelope, smoothed with a
              10 ms one-pole so onsets are physical, not clicks

All outputs: pure function of the arguments, float32 @ 16 kHz,
peak-normalized to 0.7 (mouth34 _finish convention), no file I/O, no
wall clock. Determinism: everything random flows through the seeded
streams documented in glottis.py.
"""
from __future__ import annotations

import numpy as np

import geometry
import glottis as G
import tract_core as T

SR = T.SR_OUT
AREA_MIN, AREA_MAX = 0.15, 4.0      # mouth34's search fence
F0_MIN, F0_MAX = 90.0, 350.0        # fence follows the campaign (lowered 2026-08-26); physics unchanged
TEN_MIN, TEN_MAX = 0.25, 0.95
TEN_REF = 0.6                       # house reference tenseness
AGE_MONTHS = 300                    # ADULT, FIXED. Iddo 2026-09-02 14:44.
# The throat becomes an adult and never changes shape -- not in the simulation and
# not in the silicone. The old value 60 was the campaign's five-year-old: an 11.98 cm
# tract resonating F1 1323 / F2 2006 / F3 3994 on /a/. Iddo's own recorded /ah/
# measures F1 504 / F2 1421 / F3 2379 at f0 105 Hz, so the child tube sat roughly
# 800 Hz above him on F1 and 1600 Hz above on F3 and could never have reached the
# target at any setting of any search. geometry.child_area() blends toward the
# paper's adult column above 144 months and clamps there, so 300 is simply "adult".
# NO MATURATION. This is a constant, not a schedule.

# The child anatomy, fixed once per import (campaign constant, never searched)
_L_CHILD, _NEUTRAL44 = geometry.child_area(AGE_MONTHS)
N_MAIN = T.n_sections_for(_L_CHILD)
_NAS = geometry.nasal_geometry(_L_CHILD)
N_NOSE = T.n_sections_for(_NAS["length_cm"])
NOSE_AREAS = geometry.resample_areas(_NAS["areas_cm2"], N_NOSE)
L_LADDER = N_MAIN * T.SECTION_CM


def _finish(lip16, nose16):
    """Sum the two radiating ports, peak-normalize to 0.7 (mouth34
    convention), float32. None if the render ran away."""
    y = np.asarray(lip16, dtype=np.float64) + np.asarray(nose16, np.float64)
    if not np.all(np.isfinite(y)) or float(np.max(np.abs(y))) > 1e12:
        return None
    m = float(np.max(np.abs(y)))
    y = (y / m * 0.7) if m > 0 else y
    return y.astype(np.float32)


def _render(area_track, velum_track, seconds, f0_knots, ten_knots, seed,
            intensity_env=None, tenseness_env=None, return_ports=False,
            backend="ref", burst_over=None):
    """Shared spine: glottis -> tract -> decimate -> normalize.

    backend="ref" (default): the pure-numpy reference -- THE TRUTH.
    backend="c":  the voc_eran.c twin via fastcore.py, gated by
                  validate/v_parity.py. Identical param blocks, identical
                  noise streams (drawn in numpy, passed in), identical
                  post-processing below -- only the inner loops move to C.
    """
    if backend == "c":
        import fastcore
        lip, nose = fastcore.render_c(area_track, velum_track, seconds,
                                      f0_knots, ten_knots, seed, NOSE_AREAS,
                                      intensity_env=intensity_env,
                                      tenseness_env=tenseness_env, burst_over=burst_over)
    elif backend == "ref":
        src = G.GlottalSource(f0_knots, ten_knots, seconds, T.FS_INTERNAL,
                              seed, intensity_env=intensity_env,
                              tenseness_env=tenseness_env)
        v, a, m = src.render()
        lip, nose = T.render(area_track, velum_track, v, a, m, seed,
                             NOSE_AREAS)
    else:
        raise ValueError("backend must be 'ref' or 'c', got %r" % (backend,))
    lip16 = T.decimate_16k(lip)
    nose16 = T.decimate_16k(nose)
    if return_ports:
        return lip16, nose16
    return _finish(lip16, nose16)


def _blocks(seconds):
    n = int(round(float(seconds) * T.FS_INTERNAL))
    return int(np.ceil(n / (T.BLOCK_S * T.FS_INTERNAL))), n


def _fence34(areas, lo=AREA_MIN):
    a = np.asarray(areas, dtype=float)
    if a.ndim != 1 or a.size < 8 or not np.all(np.isfinite(a)):
        return None
    return np.clip(a, lo, AREA_MAX)


def say(areas, f0=260.0, seconds=0.5, seed=0, return_ports=False,
        backend="ref"):
    """One posture, held. mouth34.say contract on the CHILD tract.

    areas: 34 (or any >=8) areas, fenced [0.15, 4.0], resampled onto the
    child ladder by normalized position. Flat f0, velum closed,
    tenseness 0.6. float32 @16 kHz peak 0.7, or None."""
    a = _fence34(areas)
    if a is None or seconds * SR < 8:
        return None
    aN = geometry.resample_areas(a, N_MAIN)
    n_blocks, _ = _blocks(seconds)
    track = np.tile(aN, (n_blocks, 1))
    velum = np.zeros(n_blocks)
    f0 = float(np.clip(f0, F0_MIN, F0_MAX))
    return _render(track, velum, seconds, [f0] * 3, [TEN_REF] * 3, seed,
                   return_ports=return_ports, backend=backend)


def say_sequence(keyframes, glide=0.35, f0=260.0, seed=0, backend="ref"):
    """A movement: [(areas34, secs), ...]. mouth34.say_sequence contract:
    linear glide from the previous posture over the first `glide`
    fraction of each segment, then hold; ladder state carried across --
    a closure and its release are one continuous tube, not a splice.

    Fence note: floor here is the AREA FLOOR, not 0.15 -- mouth34's own
    closed_lips() drives sections to 0.02 cm^2, i.e. its say_sequence
    contract INCLUDES sub-fence closures; clipping at 0.15 would
    silently delete every stop gesture ever searched."""
    frames = [(_fence34(a, lo=T.AREA_FLOOR), float(s)) for a, s in keyframes]
    if not frames or any(a is None for a, _ in frames):
        return None
    total = sum(s for _, s in frames)
    if total <= 0 or total * SR < 8:
        return None
    n_blocks, _ = _blocks(total)
    track = np.zeros((n_blocks, N_MAIN))
    prev = geometry.resample_areas(frames[0][0], N_MAIN)
    b0 = 0
    for a34, secs in frames:
        aN = geometry.resample_areas(a34, N_MAIN)
        nb = min(max(1, int(round(secs / T.BLOCK_S))), n_blocks - b0)
        if nb <= 0:
            break
        gl = max(1, int(nb * float(glide)))
        w = np.clip(np.arange(nb) / float(gl), 0.0, 1.0)[:, None]
        track[b0:b0 + nb] = prev[None, :] * (1 - w) + aN[None, :] * w
        prev = aN
        b0 += nb
    if b0 < n_blocks:
        track[b0:] = prev
    velum = np.zeros(n_blocks)
    f0 = float(np.clip(f0, F0_MIN, F0_MAX))
    return _render(track, velum, total, [f0] * 3, [TEN_REF] * 3, seed,
                   backend=backend)


def _kf_clip(kf):
    """Clip one 13-dim keyframe into its documented ranges."""
    v = np.asarray(kf, dtype=float).copy()
    if v.shape != (13,):
        raise ValueError("keyframe must have 13 dims, got %r" % (v.shape,))
    # k1..k8 are log2-areas; fence the AREAS to [0.15, 4.0]
    v[:8] = np.clip(v[:8], np.log2(AREA_MIN), np.log2(AREA_MAX))
    v[8] = np.clip(v[8], 0.30, 1.00)       # c_pos
    v[9] = np.clip(v[9], 0.0, 2.0)         # c_area
    v[10] = np.clip(v[10], 0.0, 0.8)       # velum
    v[11] = np.clip(v[11], TEN_MIN, TEN_MAX)   # tenseness
    v[12] = np.clip(v[12], 0.0, 1.0)       # voicing
    return v


def say_gesture(g, seed=0, return_ports=False, backend="ref"):
    """The NEW gesture space. See the module docstring for the format.

    float32 @16 kHz peak 0.7, or None. With return_ports=True returns
    (lip16, nose16) unnormalized -- the validation scripts need the
    separate radiating ports."""
    # 2026-08-28: per-gesture burst dials. Only `ba` sets them. They reach the C
    # ladder, which already took the four burst constants as a per-call config
    # array; the numpy reference reads module globals inside its loop, so rather
    # than let the two backends silently disagree we refuse the combination.
    burst_over = g.get("burst")
    if burst_over and backend == "ref":
        raise ValueError("burst overrides are C-backend only; ref would ignore them")
    kfs = [_kf_clip(k) for k in g["keyframes"]]
    durs = [float(d) for d in g["durations"]]
    if len(kfs) != len(durs) or not kfs:
        raise ValueError("keyframes and durations must match, non-empty")
    glide = float(g.get("glide", 0.35))
    f0_knots = np.clip(np.asarray(g["f0_knots"], float), F0_MIN, F0_MAX)
    ten_knots = np.clip(np.asarray(g["tenseness_knots"], float),
                        TEN_MIN, TEN_MAX)
    total = sum(durs)
    if total <= 0:
        return None

    n_blocks, n_samp = _blocks(total)
    # 13-dim trajectory: glide from previous keyframe, then hold
    kf_track = np.zeros((n_blocks, 13))
    prev = kfs[0]
    b0 = 0
    for kf, secs in zip(kfs, durs):
        nb = min(max(1, int(round(secs / T.BLOCK_S))), n_blocks - b0)
        if nb <= 0:
            break
        gl = max(1, int(nb * glide))
        w = np.clip(np.arange(nb) / float(gl), 0.0, 1.0)[:, None]
        kf_track[b0:b0 + nb] = prev[None, :] * (1 - w) + kf[None, :] * w
        prev = kf
        b0 += nb
    if b0 < n_blocks:
        kf_track[b0:] = prev

    # per-block: spline knots -> areas -> constriction. Batched over all
    # blocks -- bit-identical to the original per-block loop (verified on
    # PC + eran2; see geometry.spline_knots_to_areas_batch), which cost
    # ~109 ms/render in 500 PchipInterpolator constructions.
    areas_b = geometry.spline_knots_to_areas_batch(
        2.0 ** kf_track[:, :8], N_MAIN)
    areas_b = np.clip(areas_b, AREA_MIN, AREA_MAX)
    track = geometry.constriction_batch(
        areas_b, kf_track[:, 8],
        np.maximum(kf_track[:, 9], T.AREA_FLOOR), length_cm=L_LADDER)
    velum = kf_track[:, 10].copy()

    # per-sample envelopes at the internal rate
    block_len = int(round(T.BLOCK_S * T.FS_INTERNAL))
    ten_blocks = kf_track[:, 11]
    voi_blocks = kf_track[:, 12]
    ten_samp = np.repeat(ten_blocks, block_len)[:n_samp]
    voi_samp = np.repeat(voi_blocks, block_len)[:n_samp]
    if ten_samp.size < n_samp:      # tail guard
        pad = n_samp - ten_samp.size
        ten_samp = np.concatenate([ten_samp, np.full(pad, ten_blocks[-1])])
        voi_samp = np.concatenate([voi_samp, np.full(pad, voi_blocks[-1])])
    # utterance contour x keyframe multiplier (documented in header)
    t01 = np.arange(n_samp) / max(1, n_samp - 1)
    contour = G.cosine_knots(ten_knots, t01)
    ten_env = np.clip(contour * ten_samp / TEN_REF, TEN_MIN, TEN_MAX)
    # voicing -> intensity, 10 ms one-pole smoothing (no clicks)
    c_v = float(np.exp(-1.0 / (0.010 * T.FS_INTERNAL)))
    int_env = G.one_pole_lowpass(voi_samp, c_v)

    return _render(track, velum, total, f0_knots, ten_knots, seed,
                   intensity_env=int_env, tenseness_env=ten_env,
                   return_ports=return_ports, backend=backend, burst_over=burst_over)


# ---------------------------------------------------------------- presets

def vowel_knots(vowel, age_months=AGE_MONTHS):
    """8 log2-area spline knots summarizing a geometry vowel preset."""
    _, areas = geometry.child_area(age_months, vowel=vowel)
    pos = (np.arange(areas.size) + 0.5) / areas.size
    k = np.interp(np.linspace(0, 1, 8), pos, areas)
    return np.log2(np.clip(k, AREA_MIN, AREA_MAX))


def keyframe(knots8, c_pos=0.65, c_area=2.0, velum=0.0,
             tenseness=TEN_REF, voicing=1.0):
    return np.concatenate([np.asarray(knots8, float),
                           [c_pos, c_area, velum, tenseness, voicing]])


if __name__ == "__main__":
    print("MOUTH2 smoke test (structural; physics gates in validate/)")
    print("child tract: %.2f cm -> %d sections (%.2f cm ladder), nose %d"
          % (_L_CHILD, N_MAIN, L_LADDER, N_NOSE))
    L, a44 = geometry.child_area(60, vowel="a")
    y = say(geometry.resample_areas(a44, 34), f0=260.0, seconds=0.4, seed=0)
    print("say(/a/ 34 areas): %s, %d samples @16k, peak %.3f"
          % (type(y).__name__, -1 if y is None else y.size,
             0 if y is None else np.abs(y).max()))
    y2 = say(geometry.resample_areas(a44, 34), f0=260.0, seconds=0.4, seed=0)
    print("determinism: %s" % ("PASS" if np.array_equal(y, y2) else "FAIL"))
    ka = vowel_knots("a")
    gest = {"keyframes": [keyframe(ka),
                          keyframe(ka, c_pos=0.97, c_area=0.0, voicing=0.35),
                          keyframe(ka)],
            "durations": [0.20, 0.09, 0.25],
            "f0_knots": [300, 285, 250],
            "tenseness_knots": [0.6, 0.6, 0.55]}
    yg = say_gesture(gest, seed=0)
    print("say_gesture(aba): %s, %d samples, peak %.3f"
          % (type(yg).__name__, -1 if yg is None else yg.size,
             0 if yg is None else np.abs(yg).max()))
    yg2 = say_gesture(gest, seed=0)
    print("gesture determinism: %s"
          % ("PASS" if np.array_equal(yg, yg2) else "FAIL"))
