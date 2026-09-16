# -*- coding: utf-8 -*-
"""tract_core.py -- Kelly-Lochbaum ladder with a nasal branch, MOUTH v2.

The reference (pure-numpy) tract of the new mouth: a travelling-wave
ladder in Pink Trombone's exact update structure, grown a nasal side
branch, a sealed-tube pressure/burst mechanism, per-1-ms time-varying
areas with PT's within-block reflection interpolation, and honest
round-trip-normalized losses. Runs internally at 48 kHz, decimates to
16 kHz with scipy.signal.resample_poly (the ONE scipy use, documented
below). Correctness over speed: this is the truth twin; the C twin
must match it, not the other way round.

PORTED SOURCES (honest list)
============================
* Pink Trombone (IMAGINARY/pink-trombone, MIT; fetched 2026-08-26,
  raw.githubusercontent.com/IMAGINARY/pink-trombone/master/index.html):
    - Tract.runStep: the junction pass (w = r*(R[i-1]+L[i]);
      jR[i]=R[i-1]-w; jL[i]=L[i]+w; then R[i]=jR[i]*loss,
      L[i]=jL[i+1]*loss), glottal end jR[0]=L[0]*g_refl+source,
      lip end jL[N]=R[N-1]*lip_refl, lip output = R[N-1].
      DEVIATION: PT clamps R,L to [-1,1]; we do not (a clamp is a
      nonlinearity; the ladder here is passive with loss<1, measured
      stable). PT's flat 0.999 per-sample loss is replaced by the
      round-trip-normalized loss below (tract.py scar).
    - Tract.calculateNoseReflections / the 3-way velum junction:
      sum = A[jn]+A[jn+1]+A_velum; r_k = (2 A_k - sum)/sum; outgoing
      formulas verbatim (jL[jn]=rL*R[jn-1]+(1+rL)*(noseL0+L[jn]) etc).
      NOTE, honestly: PT's 3-way weights the incoming SUM by the
      outgoing port's area -- not the textbook scattering junction
      (which weights each incoming by its own port area). Ported
      verbatim per the plan ("port PT's semantics"); velum_area=0
      reduces exactly to a hard-walled port (verified in self-test).
    - reflection r=(A[i-1]-A[i])/(A[i-1]+A[i]), r=0.999 guard when an
      area is zero (we floor areas at AREA_FLOOR instead, same effect).
    - within-block reflection interpolation: r(t) = r_old*(1-lambda) +
      r_new*lambda, lambda ramping over the 1 ms block (PT runStep).
    - addTurbulenceNoiseAtIndex: thinness = clamp(8*(0.7-d),0,1),
      openness = clamp(30*(d-0.3),0,1), amplitude 0.66 * noise *
      noise_mod, injected half into R and half into L at the
      constriction. d is PT's "diameter" convention, area = d^2 with
      NO pi/4 -- so here d = sqrt(A_cm2) (documented approximation).
      DEVIATIONS: PT splits the injection over two fractional indices;
      we inject at the single integer section past the constriction.
      PT's noise source is an AudioContext white buffer bandpassed
      500-1000 Hz; the plan orders 1-3 kHz -- we bandpass 1-3 kHz with
      a one-pole high-pass at 1 kHz + one-pole low-pass at 3 kHz.
* D:/CLAUDE/voice-ant-farm/mouth.py synth_sequence -- the sealed-tube
  pressure + burst: seal when the constriction closes (their
  CLOSURE_MM=0.9 diameter -> here an AREA floor: pi/4*(0.09 cm)^2 =
  0.0064 cm2, rounded to the plan's gesture convention 0.01 cm2);
  pressure accumulates while sealed (their `pressure = min(pressure +
  drive*0.01, 1)` per 16 kHz sample -> here 0.01*(16000/fs)*|drive|,
  same buildup per second; |.| because our LF source is a zero-mean
  flow DERIVATIVE where theirs was a positive flow); on opening the
  stored pressure releases as a burst AT THE CONSTRICTION with
  BURST_GAIN=2.2 and per-sample decay 0.55 at 16 kHz ->
  0.55**(16000/fs) here (same decay per second).
  ADDITION from PT reshapeTract: no pressure accumulates while the
  velum is open (PT: transient only "if noseA[0] < 0.05") -- that is
  why /m/ has no plosive burst and /b/ does.
* D:/CLAUDE/eran-brain/voice/tract.py -- two scars, kept:
    1. THE IMPULSE PROBE. Section length is MEASURED, never assumed:
       calibrate() fires an impulse through a lossless uniform ladder,
       times the first lip arrival and the echo spacing, and sets
       SECTION_CM from the measurement (their "factor of two" scar).
    2. ROUND-TRIP LOSS. loss_per_sample = round_trip_gain**(1/rt),
       rt = the MEASURED round-trip in samples -- never a bare
       per-sample constant (their 124-section death scar).
* Extra HF damping: one-pole low-pass INSIDE the lip, nostril and
  glottal reflections (reflected wave is low-passed; DC reflectance
  unchanged). PT has no such filter -- this is the plan's "extra HF
  damping via one-pole in the end reflections".

SCIPY USE (sparing, per plan): scipy.signal.resample_poly(y, 1, 3)
for 48 kHz -> 16 kHz, with its default window ('kaiser', 5.0) -- a
polyphase FIR anti-alias filter, documented here so the C twin knows
exactly what to match (or to keep calling scipy for).

numpy + that one scipy call. No file I/O, no wall clock.
"""
from __future__ import annotations

import numpy as np
from scipy.signal import resample_poly

C_SOUND = 35000.0            # cm/s, house constant
FS_INTERNAL = 48000          # ladder rate (plan: internal 48 kHz)
SR_OUT = 16000               # ear rate
DECIM = FS_INTERNAL // SR_OUT
BLOCK_S = 0.001              # parameters re-cut per 1 ms (mouth34 convention)

GLOTTAL_REFLECT = 0.9        # house termination (analytic2/tract_analytic)
LIP_REFLECT = -0.85          # house termination (also PT's lipReflection)
ROUND_TRIP_GAIN = 0.95       # broadband loss per round trip, ON TOP of the
                             # terminations (|0.9 * -0.85| = 0.765/trip).
                             # Total/trip ~0.73 -> F1 bandwidth ~150 Hz for
                             # the child tube (arithmetic in STATUS.md).
HF_POLE_HZ = 4500.0          # one-pole low-pass inside end reflections
DC_POLE = 0.995              # output DC blocker pole (~38 Hz at 48 kHz)

AREA_FLOOR = 1e-3            # cm^2; reflection floor (PT's r=0.999 guard)
AREA_SEAL = 0.01             # cm^2; below this the tract is SEALED
                             # (plan: gesture c_area < 0.01 = sealed;
                             # ant-farm equivalent 0.0064 cm^2)
VELUM_LEAK = 0.05            # cm^2; velum open past this -> no pressure
                             # buildup (PT: noseA[0] < 0.05 gates transients)
BURST_GAIN = 2.2             # ant-farm mouth.py
PRESSURE_RATE = 0.01 * (16000.0 / FS_INTERNAL)   # ant-farm 0.01 @16k
# BURST VENTING -- ADAPTED from the ant-farm's `pressure *= 0.55` @16k
# (tau ~0.3 ms), measured 2026-08-26 in three steps:
#   1. ported verbatim, the burst radiated ~8x weaker than intended --
#      the ant-farm frames snap open instantly, ours GLIDE, and at the
#      seal threshold the lip junction still transmits only ~12%
#      (r ~ 0.875), so a 0.5 ms burst died inside the closed mouth;
#   2. venting was scaled by gap openness (flow ~ pressure x gap
#      conductance, BURST_OPEN_REF below) -- still too fast: pressure
#      was spent before the lips reached 20% open;
#   3. the full-open time constant was set to a real stop-burst
#      transient scale, ~3 ms (real bursts run 5-25 ms). This is the
#      one place the ant-farm NUMBER was changed, and this is why.
BURST_TAU_S = 0.003
BURST_DECAY = float(np.exp(-1.0 / (BURST_TAU_S * FS_INTERNAL)))
BURST_OPEN_REF = 0.3         # cm^2; gap area at which venting runs at
                             # the full 1/BURST_TAU_S rate
TURB_GAIN = 0.66             # PT addTurbulenceNoise
TURB_HP_HZ, TURB_LP_HZ = 1000.0, 3000.0          # plan: bandpass 1-3 kHz


# ----------------------------------------------------------------------
# Calibration: measure the section length, never assume it (tract.py scar)
# ----------------------------------------------------------------------

def _run_uniform_impulse(n_sections=24, n_samples=400):
    """Lossless uniform ladder, delta at the glottal input, PT update.
    Returns the lip-output time series. Used only by calibrate()."""
    N = n_sections
    R = np.zeros(N)
    L = np.zeros(N)
    out = np.zeros(n_samples)
    for t in range(n_samples):
        src = 1.0 if t == 0 else 0.0
        jR0 = L[0] * GLOTTAL_REFLECT + src
        jLN = R[N - 1] * LIP_REFLECT
        # interior junctions: uniform areas -> r = 0 -> pure delay
        newR = np.empty(N)
        newL = np.empty(N)
        newR[0] = jR0
        newR[1:] = R[:-1]
        newL[:-1] = L[1:]
        newL[-1] = jLN
        R, L = newR, newL
        out[t] = R[N - 1]
    return out


def calibrate(n_sections=24, fs=FS_INTERNAL):
    """Impulse-probe the ladder; return (section_cm, roundtrip_samples_per_section).

    MEASURED 2026-08-26 on this exact update (N=24): first lip arrival
    at t = 23 = N-1 samples (the impulse enters section 0 AT t=0, so it
    crosses N-1 boundaries to reach the lip), echo spacing exactly
    2N = 48 samples (each end reflection costs one extra sample). The
    ROUND TRIP is what sets the mode structure, so SECTION_CM derives
    from the echo spacing: C_SOUND * rt / (fs * 2N). The first arrival
    only sanity-checks the probe (must be N-1); a naive first-arrival
    calibration would have been the factor-of-(N-1)/N cousin of the
    2026-08-23 factor-of-two scar."""
    N = n_sections
    y = _run_uniform_impulse(n_sections=N)
    nz = np.where(np.abs(y) > 1e-12)[0]
    t1 = int(nz[0])                              # first arrival, samples
    later = nz[nz > t1]
    t2 = int(later[0]) if later.size else -1     # first echo
    rt = t2 - t1
    if t1 != N - 1 or rt != 2 * N:
        raise RuntimeError("calibration probe inconsistent: arrival %d "
                           "(want %d), echo spacing %d (want %d)"
                           % (t1, N - 1, rt, 2 * N))
    section_cm = C_SOUND * (rt / fs) / (2 * N)
    return section_cm, rt / n_sections


# Measured at import (cheap: 400 samples, one uniform ladder). With the
# PT update a wave crosses one section per sample -> expect one-way = N
# samples, SECTION_CM = C_SOUND/FS_INTERNAL = 0.7292 cm -- but we run the
# probe anyway, every import, because "expected" is how the factor-of-two
# scar happened.
SECTION_CM, _RT_PER_SECTION = calibrate()

# END CORRECTION -- measured 2026-08-26, gate (a) first run: a uniform
# 16-section tube rendered ALL its resonances ~7% below the ideal-
# termination analytic peaks, ratios intact (692/2123/3481 vs
# 750/2250/3750; F2/F1 = 3.07, F3/F1 = 5.03). Cause: the deliberate HF
# one-pole inside each end reflection has DC group delay a/(1-a)
# samples (~1.25 at 4500 Hz/48 kHz), so every bounce lengthens the
# acoustic tube -- the discrete cousin of the physical radiation end
# correction at real lips. Verified: an analytic twin with the same
# filtered terminations predicts 695/2097/3523 (0.4-1.2% from the
# render). The anatomy must therefore aim N at the EFFECTIVE length:
# n_sections_for subtracts this correction so a child tract of
# 11.98 cm actually resonates like ~11.98 cm, not like 12.9.
_A_HF = float(np.exp(-2.0 * np.pi * HF_POLE_HZ / FS_INTERNAL))
END_CORRECTION_SECTIONS = _A_HF / (1.0 - _A_HF)   # ~1.25 @ 4500 Hz


def n_sections_for(length_cm: float) -> int:
    return max(6, int(round(float(length_cm) / SECTION_CM
                            - END_CORRECTION_SECTIONS)))


def effective_length_cm(n_sections: int) -> float:
    """The acoustic length the ladder actually resonates at: N sections
    plus the end-correction delay of the filtered terminations."""
    return (n_sections + END_CORRECTION_SECTIONS) * SECTION_CM


# ----------------------------------------------------------------------
# The ladder
# ----------------------------------------------------------------------

def _reflections(areas: np.ndarray) -> np.ndarray:
    a = np.maximum(areas, AREA_FLOOR)
    return (a[:-1] - a[1:]) / (a[:-1] + a[1:])


def _junction3(a_main: np.ndarray, jn: int, velum_area: float):
    """PT calculateReflections' nose-junction coefficients (verbatim
    indexing: the two oral areas are A[jn] and A[jn+1])."""
    A_L = max(a_main[jn], AREA_FLOOR)
    A_R = max(a_main[min(jn + 1, a_main.size - 1)], AREA_FLOOR)
    A_N = max(float(velum_area), 0.0)
    s = A_L + A_R + A_N
    return ((2.0 * A_L - s) / s, (2.0 * A_R - s) / s, (2.0 * A_N - s) / s)


class TractState:
    """Wave state carried across blocks -- never spliced."""

    def __init__(self, n_main: int, n_nose: int):
        self.R = np.zeros(n_main)
        self.L = np.zeros(n_main)
        self.noseR = np.zeros(n_nose)
        self.noseL = np.zeros(n_nose)
        self.pressure = 0.0          # sealed-tube accumulator (ant-farm)
        self.bursting = False
        self.seal_cons = -1          # WHERE the seal was: the burst must
                                     # release at the constriction that
                                     # held the pressure, not at whatever
                                     # argmin says after the lips open
                                     # (measured scar 2026-08-26: the
                                     # release-block argmin had already
                                     # jumped to the epilarynx and the
                                     # burst fired mid-tract)
        self.lp_lip = 0.0            # one-pole HF states in end reflections
        self.lp_nose = 0.0
        self.lp_glot = 0.0
        self.dc_lip = (0.0, 0.0)     # DC-blocker (x1, y1) per output
        self.dc_nose = (0.0, 0.0)


def render(area_track: np.ndarray, velum_track: np.ndarray,
           voiced: np.ndarray, aspiration: np.ndarray,
           noise_mod: np.ndarray, seed: int,
           nasal_areas: np.ndarray,
           fs: int = FS_INTERNAL) -> tuple:
    """Run the time-varying branched ladder. The reference loop.

    area_track   (n_blocks, N) main-tract areas cm^2, one row per 1 ms
    velum_track  (n_blocks,) velopharyngeal port area cm^2 (0 = closed)
    voiced, aspiration, noise_mod  per-sample @ fs from glottis.render()
    nasal_areas  (M,) nasal branch areas, index 0 = velum port (its
                 value is REPLACED by velum_track each block, PT-style)
    Returns (lip_out, nose_out) @ fs (decimate with decimate_16k()).
    """
    n_blocks, N = area_track.shape
    M = nasal_areas.size
    jn = int(np.clip(round((17.0 / 44.0) * N), 1, N - 2))
    block = int(round(BLOCK_S * fs))
    n = min(voiced.size, n_blocks * block)

    st = TractState(N, M)
    hf_a = float(np.exp(-2.0 * np.pi * HF_POLE_HZ / fs))
    hf_g = 1.0 - hf_a

    # nasal interior reflections: fixed geometry except the velum port
    nose_fix = nasal_areas.copy()

    # turbulence noise: its own stream (seed+6000), full block up front,
    # bandpassed 1-3 kHz (one-pole HP @1k + one-pole LP @3k)
    from glottis import stream_rng, one_pole_lowpass
    turb_white = stream_rng(seed, "turbulence").standard_normal(n)
    c_lp = float(np.exp(-2.0 * np.pi * TURB_LP_HZ / fs))
    low = one_pole_lowpass(turb_white, c_lp)
    c_hp = float(np.exp(-2.0 * np.pi * TURB_HP_HZ / fs))
    turb = low - one_pole_lowpass(low, c_hp)      # LP then subtract-lower = bandpass

    lip_out = np.zeros(n)
    nose_out = np.zeros(n)

    # previous-block coefficients for PT's lambda interpolation
    a0 = np.maximum(area_track[0], AREA_FLOOR)
    r_prev = _reflections(a0)
    j3_prev = _junction3(a0, jn, velum_track[0])
    na0 = nose_fix.copy()
    na0[0] = max(velum_track[0], AREA_FLOOR)
    nr_prev = _reflections(na0)
    sealed_prev = bool(a0.min() < AREA_SEAL)

    for b in range(n_blocks):
        i0 = b * block
        i1 = min(n, i0 + block)
        if i0 >= n:
            break
        a = np.maximum(area_track[b], AREA_FLOOR)
        r_new = _reflections(a)
        vel = float(velum_track[b])
        j3_new = _junction3(a, jn, vel)
        na = nose_fix.copy()
        na[0] = max(vel, AREA_FLOOR)
        nr_new = _reflections(na)

        # Constriction search: supraglottal band only, LIP SECTION
        # INCLUDED. Measured scar 2026-08-26: an interior-only argmin
        # (a[1:-1]) missed a lip seal at c_pos=0.97 -- the burst never
        # fired (diff-render proved it: |y_burst - y_noburst| == 0).
        # The band starts at the gesture space's own c_pos floor (0.30
        # of tract length), which also keeps the child's permanently
        # narrow epilarynx (S&B elements 1-4) from being mistaken for
        # an articulator constriction and fricated.
        i0_c = int(np.ceil(0.30 * N - 0.5))
        cons = i0_c + int(np.argmin(a[i0_c:]))
        cons_area = float(a[cons])
        d_pt = float(np.sqrt(max(cons_area, 0.0)))          # PT diameter = sqrt(A)
        thin = float(np.clip(8.0 * (0.7 - d_pt), 0.0, 1.0))  # PT thinness0
        openn = float(np.clip(30.0 * (d_pt - 0.3), 0.0, 1.0))  # PT openness
        turb_amp = TURB_GAIN * thin * openn
        inj = min(cons + 1, N - 2)                # PT injects past the constriction

        sealed = cons_area < AREA_SEAL
        velum_open = vel > VELUM_LEAK
        if sealed:
            st.seal_cons = cons
            st.bursting = False                   # a new seal ends any release
        if sealed_prev and not sealed and st.pressure > 1e-4:
            st.bursting = True                    # seal just opened: release
        sealed_prev = sealed
        # how open is the released gap RIGHT NOW (this block)?
        if st.seal_cons >= 0:
            g_open = float(min(a[st.seal_cons] / BURST_OPEN_REF, 1.0))
        else:
            g_open = 1.0
        # burst injection index: the REMEMBERED seal location, clamped to
        # <= N-2 -- measured 2026-08-26: an injection into the LAST
        # section never reaches lip_out (the output tap R[N-1] is rebuilt
        # from R[N-2] every sample; the last-section wave only feeds the
        # lip REFLECTION).
        binj = min(st.seal_cons if st.seal_cons >= 0 else cons, N - 2)

        # round-trip loss, normalized by the MEASURED round trip
        rt_main = _RT_PER_SECTION * N
        rt_nose = _RT_PER_SECTION * M
        loss = ROUND_TRIP_GAIN ** (1.0 / rt_main)
        loss_n = ROUND_TRIP_GAIN ** (1.0 / rt_nose)

        nb = i1 - i0
        lam = (np.arange(nb) + 1.0) / nb          # PT lambda ramp within block
        R, L = st.R, st.L
        nR, nL = st.noseR, st.noseL
        for k in range(nb):
            t = i0 + k
            lm = lam[k]
            r = r_prev * (1.0 - lm) + r_new * lm
            rL3 = j3_prev[0] * (1.0 - lm) + j3_new[0] * lm
            rR3 = j3_prev[1] * (1.0 - lm) + j3_new[1] * lm
            rN3 = j3_prev[2] * (1.0 - lm) + j3_new[2] * lm
            nr = nr_prev * (1.0 - lm) + nr_new * lm

            # --- injections into the OLD state (PT order: before the pass)
            if turb_amp > 0.0:
                tn = turb_amp * turb[t] * noise_mod[t]
                R[inj] += 0.5 * tn
                L[inj] += 0.5 * tn
            if st.bursting:
                bamp = BURST_GAIN * st.pressure * g_open
                R[binj] += 0.5 * bamp
                L[binj] += 0.5 * bamp
                st.pressure *= 1.0 - g_open * (1.0 - BURST_DECAY)
                if st.pressure <= 1e-4:
                    st.pressure = 0.0
                    st.bursting = False

            src = voiced[t] + aspiration[t]
            if sealed and not velum_open:
                # air arrives, nothing leaves: store it (ant-farm; |.|
                # because the LF source is a zero-mean derivative)
                st.pressure = min(st.pressure
                                  + PRESSURE_RATE * abs(src), 1.0)

            # --- glottal end: reflected wave low-passed (HF damping)
            st.lp_glot = hf_g * (GLOTTAL_REFLECT * L[0]) + hf_a * st.lp_glot
            jR0 = st.lp_glot + src
            # --- lip end
            st.lp_lip = hf_g * (LIP_REFLECT * R[N - 1]) + hf_a * st.lp_lip
            jLN = st.lp_lip

            # --- interior junction pass (vector, from OLD R, L)
            w = r * (R[:-1] + L[1:])
            jR = np.empty(N)
            jL = np.empty(N + 1)
            jR[0] = jR0
            jR[1:] = R[:-1] - w
            jL[N] = jLN
            jL[1:N] = L[1:] + w
            jL[0] = 0.0                            # unused (kept for clarity)

            # --- 3-way velum junction overwrites index jn (PT verbatim)
            nose_in0 = nL[0]
            jL[jn] = rL3 * R[jn - 1] + (1.0 + rL3) * (nose_in0 + L[jn])
            jR[jn] = rR3 * L[jn] + (1.0 + rR3) * (R[jn - 1] + nose_in0)
            njR0 = rN3 * nose_in0 + (1.0 + rN3) * (L[jn] + R[jn - 1])

            R = jR * loss
            L = jL[1:] * loss
            lip_out[t] = R[N - 1]

            # --- nasal branch
            st.lp_nose = hf_g * (LIP_REFLECT * nR[M - 1]) + hf_a * st.lp_nose
            njLM = st.lp_nose
            wn = nr * (nR[:-1] + nL[1:])
            njR = np.empty(M)
            njL = np.empty(M + 1)
            njR[0] = njR0
            njR[1:] = nR[:-1] - wn
            njL[M] = njLM
            njL[1:M] = nL[1:] + wn
            nR = njR * loss_n
            nL = njL[1:] * loss_n
            nose_out[t] = nR[M - 1]

        st.R, st.L, st.noseR, st.noseL = R, L, nR, nL
        r_prev, j3_prev, nr_prev = r_new, j3_new, nr_new

    # DC blockers (one per output): y[t] = x[t]-x[t-1] + DC_POLE*y[t-1]
    def _dcblock(x):
        y = np.empty_like(x)
        x1 = y1 = 0.0
        for t in range(x.size):
            y1 = x[t] - x1 + DC_POLE * y1
            x1 = x[t]
            y[t] = y1
        return y

    return _dcblock(lip_out), _dcblock(nose_out)


def decimate_16k(y48: np.ndarray) -> np.ndarray:
    """48 kHz -> 16 kHz. scipy.signal.resample_poly(y, 1, 3), default
    window ('kaiser', 5.0) -- the documented anti-alias filter."""
    return resample_poly(np.asarray(y48, dtype=np.float64), 1, DECIM)


# ----------------------------------------------------------------------
# Self-tests (structural; the physics gates live in validate/)
# ----------------------------------------------------------------------

def _selftest():
    import geometry
    print("TRACT_CORE self-tests")
    print("=" * 64)

    print("[0] impulse-probe calibration (measured, not assumed)")
    print("    SECTION_CM = %.4f cm  (c/fs would predict %.4f); "
          "round trip = %.1f samples/section"
          % (SECTION_CM, C_SOUND / FS_INTERNAL, _RT_PER_SECTION))
    L_child, areas44 = geometry.child_area(60)
    N = n_sections_for(L_child)
    print("    child %.2f cm -> N = %d sections (ladder %.2f cm, %.1f%% "
          "length quantization)"
          % (L_child, N, N * SECTION_CM,
             100 * abs(N * SECTION_CM - L_child) / L_child))

    nas = geometry.nasal_geometry(L_child)
    M = n_sections_for(nas["length_cm"])
    nose = geometry.resample_areas(nas["areas_cm2"], M)

    import glottis as G
    src = G.GlottalSource([280.0] * 3, [0.6] * 3, 0.25, FS_INTERNAL, 0)
    v, a, m = src.render()
    n_blocks = int(np.ceil(v.size / (BLOCK_S * FS_INTERNAL)))
    uni = np.full((n_blocks, N), 1.5)

    print("[1] velum closed: nose output must be ~zero, lip alive")
    lip, nose_o = render(uni, np.zeros(n_blocks), v, a, m, 0, nose)
    r_lip = np.sqrt(np.mean(lip ** 2))
    r_nose = np.sqrt(np.mean(nose_o ** 2))
    ok1 = r_lip > 1e-4 and r_nose < 1e-9 * max(r_lip, 1.0) + 1e-12
    print("    lip rms %.4e, nose rms %.4e -> %s"
          % (r_lip, r_nose, "PASS" if ok1 else "FAIL"))

    print("[2] determinism: same seed twice, bit-identical")
    lip2, _ = render(uni, np.zeros(n_blocks), v, a, m, 0, nose)
    ok2 = np.array_equal(lip, lip2)
    print("    ->", "PASS" if ok2 else "FAIL")

    print("[3] stability: 0.25 s uniform render bounded")
    ok3 = bool(np.all(np.isfinite(lip)) and np.abs(lip).max() < 1e3)
    print("    peak %.3f -> %s" % (np.abs(lip).max(), "PASS" if ok3 else "FAIL"))

    print("[4] seal blocks the lip; pressure accumulates; release bursts")
    sealed_areas = np.full((n_blocks, N), 1.5)
    sealed_areas[:, -2] = 0.001
    lip_s, _ = render(sealed_areas, np.zeros(n_blocks), v, a, m, 0, nose)
    r_sealed = np.sqrt(np.mean(lip_s[len(lip_s) // 3:] ** 2))
    # seal for the first half, open for the second
    half = np.full((n_blocks, N), 1.5)
    half[: n_blocks // 2, -2] = 0.001
    lip_h, _ = render(half, np.zeros(n_blocks), v, a, m, 0, nose)
    mid = int(n_blocks // 2 * BLOCK_S * FS_INTERNAL)
    peak_after = np.abs(lip_h[mid: mid + 480]).max()
    peak_vowel = np.abs(lip_h[mid + 2400:]).max()
    # structural only: seal leaks < -25 dB and a release transient rises
    # above the steady vowel. The REAL closure/burst timing gate is
    # validate/v_e_stop_b.py, not this.
    ok4 = (r_sealed < 0.06 * r_lip) and peak_after > peak_vowel
    print("    sealed rms %.2e (open-lip %.2e); release peak %.3f vs "
          "steady %.3f -> %s"
          % (r_sealed, r_lip, peak_after, peak_vowel, "PASS" if ok4 else "FAIL"))

    print("=" * 64)
    print("ALL PASS" if (ok1 and ok2 and ok3 and ok4) else "SOME FAILED")
    return ok1 and ok2 and ok3 and ok4


if __name__ == "__main__":
    _selftest()
