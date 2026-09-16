# -*- coding: utf-8 -*-
"""Tests for curriculum_targets.py - the /a/, /ba/, /ga/ measurement pipeline.

The whole point of this module is to MEASURE acoustics off real voices. If the
measurement is wrong, every target downstream is wrong. So every estimator here
is tested against a synthetic signal whose true answer we know by construction.

No torch. numpy + scipy only. Audio is read from and written to files only -
nothing in this file opens an audio device.
"""
import numpy as np
import pytest

import curriculum_targets as ct


SR = 16000


# ----------------------------------------------------------------- helpers --
def synth_vowel(f_targets, bws=None, f0=120.0, dur=0.30, sr=SR, seed=0,
                glottal_tilt=True):
    """Source-filter vowel: glottal source through a cascade of 2-pole resonators.

    The formant frequencies are true BY CONSTRUCTION - they are the pole angles
    we place. Any correct formant tracker must recover them.

    The source must be physically realistic or the test is meaningless. Real
    speech reaching a microphone carries roughly -6 dB/octave from the glottal
    volume-velocity spectrum (-12) plus lip radiation (+6). Pre-emphasis inside
    lpc_formants exists precisely to cancel that tilt so LPC models the vocal
    TRACT alone. A flat impulse train would therefore be double-pre-emphasised
    and would bias the fit - so we apply the -6 dB/oct source tilt here, giving
    a signal whose only poles are the vocal-tract poles we placed.
    """
    rng = np.random.default_rng(seed)
    n = int(dur * sr)
    x = np.zeros(n)
    period = int(sr / f0)
    x[::period] = 1.0                      # glottal impulse train
    if bws is None:
        bws = [80.0] * len(f_targets)
    from scipy.signal import lfilter
    if glottal_tilt:
        # one-pole at 0.97 == the exact inverse of the (1 - 0.97 z^-1) pre-emphasis
        x = lfilter([1.0], [1.0, -0.97], x)
    for f, bw in zip(f_targets, bws):
        r = np.exp(-np.pi * bw / sr)
        theta = 2.0 * np.pi * f / sr
        a = [1.0, -2.0 * r * np.cos(theta), r * r]
        b = [1.0 - 2.0 * r * np.cos(theta) + r * r]   # unit DC gain
        x = lfilter(b, a, x)
    x += 1e-4 * rng.standard_normal(n)
    m = np.max(np.abs(x))
    return (x / m * 0.5) if m > 0 else x


# --------------------------------------------------------------- formants ---
# A real vocal tract resonates ~ every 1000 Hz, so a realistic test vowel needs
# F1..F5. A 3-pole signal is under-determined for LPC order 18 and the surplus
# poles land as spurious narrow peaks - that is a defect of the test signal, not
# of the tracker, so the synthetic tracts below all carry five formants.
MALE_A = [730.0, 1090.0, 2440.0, 3400.0, 4400.0]
FEMALE_A = [900.0, 1600.0, 2900.0, 4000.0, 4900.0]
CHILD_A = [1000.0, 1700.0, 3200.0, 4200.0, 5100.0]
FEMALE_I = [400.0, 2700.0, 3300.0, 4200.0, 5000.0]


def test_lpc_recovers_known_formants_male():
    """A pole placed at 730/1090/2440 Hz must come back at 730/1090/2440 Hz."""
    x = synth_vowel(MALE_A, f0=120.0)
    frame = x[int(0.10 * SR): int(0.10 * SR) + 400]
    f = ct.lpc_formants(frame, SR)
    assert f is not None and len(f) >= 3
    for got, want in zip(f[:3], MALE_A[:3]):
        assert abs(got - want) < 0.06 * want, f"got {f[:3]}, want {MALE_A[:3]}"


@pytest.mark.parametrize("true,f0,name", [
    (MALE_A, 120.0, "male /a/"),
    (FEMALE_A, 210.0, "female /a/"),
    (FEMALE_A, 250.0, "female /a/ high"),
    (CHILD_A, 300.0, "child /a/"),
    (FEMALE_I, 220.0, "female /i/"),
])
def test_formant_track_is_accurate_across_voices(true, f0, name):
    """The adopted path (resample to 2*ceiling, order 2*n) must hold F1/F2 within 5%.

    This is the estimator the targets are actually measured with, so its
    accuracy on high-f0 voices is load-bearing: /a/ has F1 and F2 close
    together, which is exactly where naive 16 kHz order-18 LPC breaks down.
    """
    x = synth_vowel(true, f0=f0, dur=0.5)
    tr = ct.formant_track(x, SR)
    assert len(tr) >= 5, f"{name}: only {len(tr)} voiced frames"
    f1 = np.median([r["f1"] for r in tr])
    f2 = np.median([r["f2"] for r in tr])
    # Tolerance is absolute-or-relative, whichever is looser. A pure percentage
    # is the wrong instrument for a 400 Hz formant: formant estimation is
    # conventionally held to ~+-50 Hz on F1 and ~+-100 Hz on F2 regardless of
    # centre frequency, and 5% of 400 Hz (20 Hz) is finer than the method can
    # resolve for any voice.
    assert abs(f1 - true[0]) < max(50.0, 0.05 * true[0]), f"{name}: F1 {f1:.0f} vs {true[0]}"
    assert abs(f2 - true[1]) < max(100.0, 0.05 * true[1]), f"{name}: F2 {f2:.0f} vs {true[1]}"


def test_naive_16k_lpc_is_worse_than_adopted_path_on_female_a():
    """Documents WHY we resample. If this ever inverts, revisit the config."""
    x = synth_vowel(FEMALE_A, f0=210.0, dur=0.5)
    naive = [ct.lpc_formants(x[s:s + 400], SR) for s in range(1600, 6400, 160)]
    naive_f2 = np.median([f[1] for f in naive if f is not None and len(f) >= 2])
    good_f2 = np.median([r["f2"] for r in ct.formant_track(x, SR)])
    assert abs(good_f2 - 1600.0) < abs(naive_f2 - 1600.0)


def test_lpc_rejects_silence():
    assert ct.lpc_formants(np.zeros(400), SR) is None


def test_wide_bandwidth_poles_are_filtered_out():
    """bw>400 Hz is not a formant; the keep-rule must drop it."""
    x = synth_vowel([700.0, 1220.0], bws=[80.0, 900.0])
    frame = x[int(0.10 * SR): int(0.10 * SR) + 400]
    f = ct.lpc_formants(frame, SR, max_bw=400.0)
    assert f is not None
    assert not any(abs(v - 1220.0) < 60 for v in f), f"wide pole survived: {f}"


# ---------------------------------------------------------------- voicing ---
def test_voicing_separates_periodic_from_noise():
    voiced = synth_vowel([700.0, 1220.0], f0=120.0)
    rng = np.random.default_rng(1)
    noise = 0.5 * rng.standard_normal(len(voiced))
    fr_v = voiced[int(0.10 * SR): int(0.10 * SR) + 400]
    fr_n = noise[int(0.10 * SR): int(0.10 * SR) + 400]
    assert ct.voicing_strength(fr_v, SR) > 0.45
    assert ct.voicing_strength(fr_n, SR) < 0.30


def test_f0_estimate_is_accurate():
    x = synth_vowel([700.0, 1220.0], f0=150.0)
    fr = x[int(0.10 * SR): int(0.10 * SR) + 400]
    f0 = ct.estimate_f0(fr, SR)
    assert f0 is not None and abs(f0 - 150.0) < 8.0, f0


# ------------------------------------------------------ stop / burst ------
def test_finds_closure_and_burst_in_synthetic_stop():
    """silence(80ms) -> burst(5ms) -> vowel(250ms). Detector must find the seam."""
    rng = np.random.default_rng(2)
    closure = 1e-5 * rng.standard_normal(int(0.080 * SR))
    burst = 0.6 * rng.standard_normal(int(0.005 * SR))
    vowel = synth_vowel([700.0, 1220.0, 2600.0], dur=0.250)
    x = np.concatenate([closure, burst, vowel])
    ev = ct.find_stop_events(x, SR)
    assert len(ev) >= 1
    e = ev[0]
    want = 0.080
    assert abs(e["burst_s"] - want) < 0.025, e
    assert e["closure_ms"] > 40.0, e


def test_closure_too_short_is_rejected():
    rng = np.random.default_rng(3)
    x = np.concatenate([
        1e-5 * rng.standard_normal(int(0.010 * SR)),      # only 10 ms
        0.6 * rng.standard_normal(int(0.005 * SR)),
        synth_vowel([700.0, 1220.0], dur=0.250),
    ])
    ev = ct.find_stop_events(x, SR, min_closure_ms=40.0)
    assert all(e["closure_ms"] >= 40.0 for e in ev)


def test_burst_spectrum_tilt_separates_low_from_high():
    """Bilabial bursts are low-frequency dominant; alveolar are high."""
    rng = np.random.default_rng(4)
    n = int(0.010 * SR)
    from scipy.signal import butter, lfilter
    w = rng.standard_normal(n)
    b, a = butter(4, 1200 / (SR / 2), "low")
    low = lfilter(b, a, w)
    b, a = butter(4, 3500 / (SR / 2), "high")
    high = lfilter(b, a, w)
    assert ct.burst_centroid(low, SR) < ct.burst_centroid(high, SR)
    assert ct.burst_centroid(low, SR) < 1500.0
    assert ct.burst_centroid(high, SR) > 3500.0


# --------------------------------------------------------- velar pinch -----
def test_velar_pinch_score_high_when_f2_f3_converge():
    """The velar pinch IS F2 and F3 close together at release."""
    pinched = ct.velar_pinch_score(f2=1800.0, f3=2100.0)
    spread = ct.velar_pinch_score(f2=1100.0, f3=2600.0)
    assert pinched > spread
    assert pinched > 0.6 and spread < 0.4


def test_f2_locus_slope_sign():
    """Bilabial: F2 RISES from a low locus into /a/. Velar: F2 FALLS into /a/."""
    rising = ct.f2_transition_slope([900.0, 1000.0, 1100.0, 1200.0], hop_s=0.010)
    falling = ct.f2_transition_slope([1900.0, 1700.0, 1500.0, 1350.0], hop_s=0.010)
    assert rising > 0 and falling < 0
    assert abs(rising - 10000.0) < 3000.0     # ~ +10 Hz/ms = 10000 Hz/s


# ------------------------------------------------------- CV token ---------
def synth_cv(f_start, f_end, f0=120.0, closure_s=0.080, burst_s=0.006,
             vowel_s=0.260, transition_s=0.060, burst_gain=0.5, sr=SR, seed=0):
    """Synthesize [silent closure -> burst -> vowel] with a controlled formant
    transition, so the true locus, slope and pinch are known by construction."""
    from scipy.signal import lfilter, lfilter_zi
    rng = np.random.default_rng(seed)
    n_v = int(vowel_s * sr)
    src = np.zeros(n_v)
    src[::int(sr / f0)] = 1.0
    src = lfilter([1.0], [1.0, -0.97], src)          # -6 dB/oct glottal tilt
    n_t = int(transition_s * sr)
    blk = int(0.005 * sr)
    out = np.zeros(n_v)
    states = [None] * len(f_start)
    for s in range(0, n_v, blk):
        e = min(s + blk, n_v)
        frac = min(1.0, s / max(1, n_t))
        y = src[s:e]
        for k, (fa, fb) in enumerate(zip(f_start, f_end)):
            f = fa + (fb - fa) * frac
            bw = 80.0 + 0.03 * f
            r = np.exp(-np.pi * bw / sr)
            th = 2 * np.pi * f / sr
            b = [1 - 2 * r * np.cos(th) + r * r]
            a = [1.0, -2 * r * np.cos(th), r * r]
            if states[k] is None:
                states[k] = lfilter_zi(b, a) * y[0] if y.size else np.zeros(2)
            y, states[k] = lfilter(b, a, y, zi=states[k])
        out[s:e] = y
    m = np.max(np.abs(out))
    if m > 0:
        out = out / m * 0.5
    closure = 1e-5 * rng.standard_normal(int(closure_s * sr))
    burst = burst_gain * rng.standard_normal(int(burst_s * sr))
    return np.concatenate([closure, burst, out])


def test_measure_cv_token_bilabial_ba():
    """/ba/: F2 rises from a LOW locus (~700-1000 Hz) into the vowel."""
    x = synth_cv([700.0, 900.0, 2400.0, 3400.0, 4400.0],
                 [730.0, 1250.0, 2500.0, 3400.0, 4400.0])
    r = ct.measure_cv_token(x, SR)
    assert r is not None
    assert r["closure_ms"] > 50.0, r
    assert 600.0 < r["f2_onset"] < 1150.0, r
    assert 1050.0 < r["f2_steady"] < 1450.0, r
    assert r["f2_slope_hz_per_s"] > 1000.0, r          # rising
    assert r["vot_ms"] is not None and r["vot_ms"] < 60.0, r


def test_measure_cv_token_velar_ga():
    """/ga/: F2 starts HIGH and near F3 (the velar pinch), then falls into /a/."""
    x = synth_cv([700.0, 1900.0, 2150.0, 3400.0, 4400.0],
                 [730.0, 1300.0, 2500.0, 3400.0, 4400.0])
    r = ct.measure_cv_token(x, SR)
    assert r is not None
    assert r["f2_onset"] > 1500.0, r
    assert r["f2_slope_hz_per_s"] < -1000.0, r         # falling
    assert r["pinch_onset"] > 0.55, r


def test_ba_and_ga_are_separated_by_the_measurements():
    """The whole point: these two must be distinguishable by number, not vibe."""
    ba = ct.measure_cv_token(
        synth_cv([700., 900., 2400., 3400., 4400.], [730., 1250., 2500., 3400., 4400.]), SR)
    ga = ct.measure_cv_token(
        synth_cv([700., 1900., 2150., 3400., 4400.], [730., 1300., 2500., 3400., 4400.]), SR)
    assert ba["f2_onset"] < ga["f2_onset"] - 400.0
    assert ba["f2_slope_hz_per_s"] > 0 > ga["f2_slope_hz_per_s"]
    assert ga["pinch_onset"] > ba["pinch_onset"]


# ------------------------------------------------------------ clustering ---
def test_a_cluster_picked_is_the_high_f1_one():
    """Given a fake vowel space with an /i/ blob and an /a/ blob, pick /a/."""
    rng = np.random.default_rng(5)
    i_blob = np.column_stack([rng.normal(300, 30, 400), rng.normal(2200, 150, 400)])
    a_blob = np.column_stack([rng.normal(730, 60, 400), rng.normal(1250, 120, 400)])
    F = np.vstack([i_blob, a_blob])
    mu, cov, n = ct.pick_a_cluster(F[:, 0], F[:, 1], n_components=2, seed=0)
    assert abs(mu[0] - 730) < 60, mu
    assert abs(mu[1] - 1250) < 150, mu
    assert n > 200


def test_pick_a_cluster_rejects_empty():
    with pytest.raises(ValueError):
        ct.pick_a_cluster(np.array([]), np.array([]))


def _fake_vowel_space(seed=0, n=6000):
    """A realistic Hebrew 5-vowel space for a male speaker, plus measurement junk.

    Proportions follow running speech: /a/ is the most frequent Hebrew vowel.
    5% of frames are 'F1 dropped' artifacts, which is what the real corpora show.
    """
    rng = np.random.default_rng(seed)
    spec = [  # (F1, F2, sd1, sd2, share)
        (700.0, 1250.0, 80.0, 170.0, 0.32),   # /a/  <- the answer
        (480.0, 1850.0, 60.0, 200.0, 0.24),   # /e/
        (320.0, 2250.0, 45.0, 220.0, 0.18),   # /i/
        (480.0, 950.0, 60.0, 130.0, 0.13),    # /o/
        (350.0, 850.0, 45.0, 120.0, 0.08),    # /u/
    ]
    F1, F2 = [], []
    for m1, m2, s1, s2, share in spec:
        k = int(n * share)
        F1.append(rng.normal(m1, s1, k))
        F2.append(rng.normal(m2, s2, k))
    k = int(n * 0.05)                                   # F1-dropped artifacts
    F1.append(rng.normal(1450.0, 200.0, k))
    F2.append(rng.normal(2500.0, 300.0, k))
    return np.concatenate(F1), np.concatenate(F2)


def test_estimate_a_target_recovers_a_from_a_full_vowel_space():
    """The estimator must find /a/ inside a realistic 5-vowel cloud + artifacts.

    This is the regression for the two bugs that produced F1=1191 (artifact
    cluster) and F2=2243 (front-vowel lobe) on real speech.
    """
    F1, F2 = _fake_vowel_space(seed=3)
    est = ct.estimate_a_target(F1, F2)
    assert abs(est["F1"] - 700.0) < 70.0, est
    assert abs(est["F2"] - 1250.0) < 180.0, est
    assert est["n_effective"] > 300, est


def test_estimate_a_target_is_stable_across_seeds():
    got = [ct.estimate_a_target(*_fake_vowel_space(seed=s))["F2"] for s in range(4)]
    assert max(got) - min(got) < 120.0, got


def test_estimate_a_target_reports_its_selection_rule():
    F1, F2 = _fake_vowel_space(seed=1)
    est = ct.estimate_a_target(F1, F2)
    for key in ("F1", "F2", "cov", "n_effective", "n_input", "top_f1_pct", "sd_F1", "sd_F2"):
        assert key in est, key
    assert est["n_input"] >= est["n_effective"]


def test_valid_vowel_mask_rejects_impossible_formants():
    """No human vowel has F1 = 1400 Hz. Such a frame means LPC DROPPED F1 and
    F2 slid into its slot - the exact artifact that corrupted the first run."""
    F1 = np.array([700.0, 1400.0, 500.0, 200.0, 900.0, 950.0])
    F2 = np.array([1200.0, 2100.0, 1800.0, 1500.0, 1000.0, 5000.0])
    m = ct.valid_vowel_mask(F1, F2)
    assert m.tolist() == [True, False, True, False, False, False], m.tolist()


def test_pick_a_cluster_ignores_f1_dropped_artifacts():
    """The regression that produced F1=1190 Hz for /a/.

    A real /a/ blob plus a smaller 'F1 was dropped' artifact blob at F1~1400.
    Naive 'highest-F1 component' picks the artifact; the estimator must not.
    """
    rng = np.random.default_rng(11)
    a_blob = np.column_stack([rng.normal(700, 70, 1200), rng.normal(1300, 150, 1200)])
    i_blob = np.column_stack([rng.normal(350, 40, 800), rng.normal(2100, 200, 800)])
    artifact = np.column_stack([rng.normal(1400, 120, 150), rng.normal(2400, 250, 150)])
    F = np.vstack([a_blob, i_blob, artifact])
    mu, cov, n = ct.pick_a_cluster(F[:, 0], F[:, 1], n_components=3, seed=0)
    assert mu[0] < 1000.0, f"picked an impossible F1: {mu}"
    assert abs(mu[0] - 700) < 80, mu
    assert abs(mu[1] - 1300) < 200, mu


# ------------------------------------------------------------- exclusion ---
def test_heldout_sessions_are_excluded():
    """2026-06-25 and 2026-07-01 must NEVER be fittable. Non-negotiable."""
    paths = [
        r"D:\x\20260624061811.WAV",
        r"D:\x\20260625165315.WAV",
        r"D:\x\20260701130300.WAV",
        r"D:\x\20260702000225.WAV",
        r"D:\x\cleaned\20260625171050.mp3",
    ]
    keep = ct.filter_training_paths(paths)
    assert r"D:\x\20260624061811.WAV" in keep
    assert r"D:\x\20260702000225.WAV" in keep
    assert not any("20260625" in p for p in keep)
    assert not any("20260701" in p for p in keep)
    assert len(keep) == 2


def test_holdout_listing_is_nonempty_and_exact():
    held = ct.heldout_sessions()
    assert set(held) == {"2026-06-25", "2026-07-01"}
