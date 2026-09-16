# -*- coding: utf-8 -*-
"""Tests for ah_criterion.py - the rung-1 (/a/) judge.

Written BEFORE the implementation. The order matters: the law is written first,
then something is built that can satisfy it. If nothing can satisfy it, the law
is wrong and the law gets fixed - the test never does.

No torch. No audio device is opened anywhere in this file: wav files are read
from disk and synthetic waveforms are built in memory.
"""
from __future__ import annotations

import json
import os
import sys
import textwrap
import wave

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import ah_criterion as ahc          # noqa: E402
import glottis                       # noqa: E402  (the queen's mouth)

SR = 16000

# --------------------------------------------------------------------------
# The held-out fixture. Session 2026-06-25 is reserved for evaluation and is
# never fitted on; using it HERE, to test a frozen judge, is exactly its job.
# --------------------------------------------------------------------------
HELDOUT_CLIP = os.path.join(
    HERE, "corpus-big", "human", "heldout",
    "vinput__20260625_063500_615502_rec_20260625_093458.wav")
HELDOUT_WINDOW = (3.55, 3.95)        # a real /a/, located by the frozen judge


def _read(path, sr=SR):
    import curriculum_targets as ct
    return ct.read_wav_mono16k(path, target_sr=sr)


@pytest.fixture(scope="module")
def real_a():
    """A real /a/ spoken by Iddo, from the held-out corpus."""
    if not os.path.exists(HELDOUT_CLIP):
        pytest.skip(f"held-out fixture not on this machine: {HELDOUT_CLIP}")
    x = _read(HELDOUT_CLIP)
    t0, t1 = HELDOUT_WINDOW
    return x[int(t0 * SR):int(t1 * SR)]


@pytest.fixture(scope="module")
def real_codebook():
    """An exemplar bank built the way acoustic_units.py builds one: raw PCM
    frames lifted straight out of the corpus."""
    if not os.path.exists(HELDOUT_CLIP):
        pytest.skip("held-out fixture not on this machine")
    x = _read(HELDOUT_CLIP)
    frame, hop = 400, 200
    n = 1 + (len(x) - frame) // hop
    return np.stack([x[i * hop:i * hop + frame] for i in range(n)])


# ==========================================================================
# GATE 1 - IDENTITY
# ==========================================================================
def test_identity_is_mahalanobis_not_raw_hz():
    """Raw-Hz Euclidean over-weights F2. Two points the same number of Hz away
    from the centroid must NOT be the same distance away in the judge's metric,
    because F1 varies by ~41 Hz in the measured cluster and F2 by ~262 Hz."""
    f1c, f2c = ahc.AH_TARGET["F1"], ahc.AH_TARGET["F2"]
    d_hz = 150.0
    along_f1 = ahc.mahalanobis_to_a(f1c + d_hz, f2c)
    along_f2 = ahc.mahalanobis_to_a(f1c, f2c + d_hz)
    assert along_f1 > 3.0 * along_f2, (
        f"metric is behaving like raw Hz: {along_f1:.2f} vs {along_f2:.2f}")


def test_vowel_space_is_a_real_triangle():
    """The competitor set must span the space, or 'nearest vowel is /a/' is
    vacuous."""
    sp = ahc.VOWEL_SPACE_HZ
    assert set(sp) >= {"a", "e", "i", "o", "u"}
    assert sp["i"][1] > sp["e"][1] > sp["a"][1] > sp["o"][1] > sp["u"][1], \
        "F2 must fall monotonically i > e > a > o > u"
    assert sp["a"][0] == max(v[0] for v in sp.values()), "/a/ must be the most open"


@pytest.mark.parametrize("vowel", ["i", "e", "o", "u"])
def test_other_vowels_fail_gate_1(vowel):
    """A well-formed, perfectly voiced, perfectly steady /i/ is still not /a/."""
    f1, f2 = ahc.VOWEL_SPACE_HZ[vowel]
    y = glottis.articulate_vowel(f0_hz=150.0, formants_hz=(f1, f2, 2600.0),
                                 duration_s=0.40, sr=SR, seed=5)
    v = ahc.judge_ah(y, SR, production_module=glottis.__file__)
    assert not v.gates["identity"].passed, f"/{vowel}/ was accepted as /a/"
    assert not v.passed


def test_real_a_passes_identity(real_a):
    v = ahc.judge_ah(real_a, SR)
    assert v.gates["identity"].passed, v.gates["identity"].detail


# ==========================================================================
# GATE 2 - VOICING   |   GATE 3 - STABILITY
# ==========================================================================
def test_white_noise_fails(real_codebook):
    rng = np.random.default_rng(0)
    y = rng.normal(0, 0.1, int(0.5 * SR)).astype(np.float32)
    v = ahc.judge_ah(y, SR, production_module=glottis.__file__,
                     codebook=real_codebook)
    assert not v.passed
    assert not v.gates["voicing"].passed, "white noise was called voiced"


def test_pure_sine_fails_voicing_or_stability():
    """A sine is perfectly periodic, so a naive autocorrelation voicing test
    passes it. It must still fail: a vowel is a glottal source through a filter
    and therefore HARMONICALLY RICH. One partial is not a voice."""
    t = np.arange(int(0.5 * SR)) / SR
    y = (0.3 * np.sin(2 * np.pi * 700.0 * t)).astype(np.float32)
    v = ahc.judge_ah(y, SR, production_module=glottis.__file__)
    assert not v.passed
    assert not (v.gates["voicing"].passed and v.gates["stability"].passed)
    assert not v.gates["voicing"].passed, "a single partial was accepted as a voice"


def test_click_fails_voicing():
    y = np.zeros(int(0.4 * SR), dtype=np.float32)
    y[1000] = 1.0
    y[1400] = -0.8
    v = ahc.judge_ah(y, SR, production_module=glottis.__file__)
    assert not v.gates["voicing"].passed


def test_fast_formant_sweep_fails_stability():
    """A smear is not a vowel. This sweep moves faster than real human /a/ ever
    does (measured train p90: 768 Hz/s on F1, 3193 Hz/s on F2)."""
    y = glottis.articulate_vowel(
        f0_hz=150.0, formants_hz=(500.0, 1000.0, 2600.0),
        formants_hz_end=(1000.0, 2200.0, 2600.0),
        duration_s=0.25, sr=SR, seed=5)
    v = ahc.judge_ah(y, SR, production_module=glottis.__file__)
    assert not v.gates["stability"].passed, "a formant sweep was called steady"


def test_a_sweep_gentler_than_human_speech_is_NOT_caught():
    """The honest limit of gate 3, recorded rather than hidden.

    A slow glide through the /a/ centroid passes, and it SHOULD: within any
    120 ms window it moves less than real human /a/ moves (measured median
    |dF2/dt| in real /a/ stretches = 1319 Hz/s). Tightening the gate until this
    failed would reject the corpus itself - which is the exact sin, bending a
    threshold, that this module exists to stop. Gate 3 asks 'did it hold still
    for 120 ms', not 'did it hold still forever'.
    """
    y = glottis.articulate_vowel(
        f0_hz=150.0, formants_hz=(500.0, 1100.0, 2600.0),
        formants_hz_end=(900.0, 1900.0, 2600.0),
        duration_s=0.40, sr=SR, seed=5)
    v = ahc.judge_ah(y, SR, production_module=glottis.__file__)
    assert v.gates["stability"].passed, (
        "documented limitation changed: the gentle glide is now rejected, so "
        "re-check that real human /a/ still passes")
    assert ahc.STABILITY_LIMITS["gentle_glide_passes"] is True


def test_too_short_fails(real_a):
    short = real_a[:int(0.06 * SR)]
    v = ahc.judge_ah(short, SR)
    assert not v.gates["voicing"].passed
    assert "duration" in v.gates["voicing"].detail.lower()


def test_real_a_passes_gates_1_to_3(real_a):
    """(a) A real /a/ from the held-out corpus passes identity, voicing and
    stability. If it does not, the law rejects human speech and the law is
    wrong."""
    v = ahc.judge_ah(real_a, SR)
    for g in ("identity", "voicing", "stability"):
        assert v.gates[g].passed, f"gate {g} rejected real human /a/: " \
                                  f"{v.gates[g].detail}"


# ==========================================================================
# GATE 4a - PROVENANCE, STATIC
# ==========================================================================
def test_audit_clears_the_genuine_mouth():
    """glottis.py is the production path. It must be structurally incapable of
    touching a recorded waveform."""
    violations = ahc.audit_production_module(glottis.__file__)
    assert violations == [], "\n".join(str(v) for v in violations)


def test_audit_catches_the_exemplar_replay_path():
    """A gate that never fires is not a gate. acoustic_units.py IS the replay
    path this whole exercise exists to outlaw - the audit must reject it."""
    target = os.path.join(HERE, "acoustic_units.py")
    assert os.path.exists(target)
    violations = ahc.audit_production_module(target)
    assert violations, "the audit cleared the known replay path"
    reasons = " ".join(v.reason for v in violations)
    assert "exemplars_pcm16" in reasons


def test_audit_catches_a_wav_loader(tmp_path):
    m = tmp_path / "sneaky_mouth.py"
    m.write_text(textwrap.dedent("""
        import numpy as np
        import wave
        def speak():
            with wave.open("x.wav") as w:
                return np.frombuffer(w.readframes(10), "<i2")
    """), encoding="utf-8")
    violations = ahc.audit_production_module(str(m))
    assert any("wave" in v.reason for v in violations)


def test_audit_is_transitive(tmp_path):
    """Hiding the wav loader one import away must not launder it."""
    (tmp_path / "helper.py").write_text(
        "import soundfile\ndef load(p):\n    return soundfile.read(p)\n",
        encoding="utf-8")
    m = tmp_path / "mouth2.py"
    m.write_text("import helper\ndef speak():\n    return helper.load('a.wav')\n",
                 encoding="utf-8")
    violations = ahc.audit_production_module(str(m))
    assert any("helper" in v.module or "soundfile" in v.reason
               for v in violations), [str(v) for v in violations]


def test_grep_agrees_with_the_ast_audit():
    """The same claim by the crudest possible instrument. If the AST audit and
    plain grep ever disagree, neither is trustworthy until they are reconciled.

    Reproduce from a shell:
        grep -n exemplars_pcm16 glottis.py       -> no output
        grep -n exemplars_pcm16 acoustic_units.py -> hits
    """
    assert ahc.grep_proof(glottis.__file__) == [], \
        "grep found a waveform bank inside the mouth"
    hits = ahc.grep_proof(os.path.join(HERE, "acoustic_units.py"))
    assert hits, "grep cleared the known replay path - the token list is wrong"
    assert any(t == "exemplars_pcm16" for _, t, _ in hits)


def test_the_judge_itself_would_fail_the_audit():
    """Deliberate and important. ah_criterion.py reads wav files - it must, it is
    the judge. It is therefore NOT a legal production module, and the audit says
    so. If the judge passed its own audit, the audit would be measuring nothing.
    """
    assert ahc.audit_production_module(ahc.__file__), \
        "the audit cleared a module that opens files - it is vacuous"


def test_audit_catches_np_load(tmp_path):
    m = tmp_path / "mouth3.py"
    m.write_text("import numpy as np\ndef speak():\n"
                 "    return np.load('exemplars.npy')\n", encoding="utf-8")
    assert ahc.audit_production_module(str(m))


# ==========================================================================
# GATE 4b - PROVENANCE, EMPIRICAL (defence in depth)
# ==========================================================================
def test_mosaic_detector_flags_exact_overlap_add_replay(real_codebook):
    """The exact construction acoustic_units.synthesize_units() performs."""
    rng = np.random.default_rng(1)
    ids = rng.integers(0, len(real_codebook), 24)
    y = ahc.overlap_add(real_codebook[ids], hop=200)
    flagged, snr = ahc.looks_like_replay(y, real_codebook, frame=400, hop=200)
    assert flagged, f"exact OLA replay slipped through at {snr:.1f} dB"
    assert snr >= ahc.GATES["replay_snr_db"]


def test_mosaic_detector_clears_the_genuine_mouth(real_codebook):
    """Imitation must NOT be flagged. The synth is aiming at the same /a/ as the
    codebook; resemblance is the goal, so the detector must key on mechanism."""
    y = glottis.articulate_vowel(
        f0_hz=ahc.AH_TARGET["f0_median_hz"],
        formants_hz=(ahc.AH_TARGET["F1"], ahc.AH_TARGET["F2"], 2600.0),
        duration_s=0.40, sr=SR, seed=5)
    flagged, snr = ahc.looks_like_replay(y, real_codebook, frame=400, hop=200)
    assert not flagged, f"honest imitation was called replay at {snr:.1f} dB"


def test_mosaic_detector_catches_lightly_crossfaded_two_frame_mosaics(
        real_codebook):
    """A lightly crossfaded 2-frame mosaic is the obvious evasion, and the
    question the law must answer out loud. Measured over 8 seeded pairs per fade
    length rather than one lucky pair - a single pair sitting 1 dB over the
    threshold would be evidence of nothing."""
    rng = np.random.default_rng(4)
    for overlap in (25, 50, 100):
        snrs = []
        for _ in range(8):
            i, j = rng.integers(0, len(real_codebook), 2)
            y = ahc.crossfade(real_codebook[i], real_codebook[j],
                              overlap=overlap)
            snrs.append(ahc.looks_like_replay(y, real_codebook,
                                              frame=400, hop=200)[1])
        rate = float(np.mean(np.array(snrs) >= ahc.GATES["replay_snr_db"]))
        assert rate >= 0.75, (
            f"crossfade fade={overlap} samples evades the detector "
            f"{100 * (1 - rate):.0f}% of the time (median "
            f"{np.median(snrs):.1f} dB). Either fix the detector or correct "
            f"CROSSFADE_EVASION - do not leave the doc claiming it is caught.")
    assert ahc.CROSSFADE_EVASION["caught"] is True


def test_the_crossfade_weakness_is_documented_not_hidden():
    """The catch rate degrades on longer mosaics with longer fades - 50% at 8
    frames with a 12.5 ms fade. That belongs in the docs, not in a drawer."""
    doc = ahc.CROSSFADE_EVASION
    assert "50%" in doc["measured_catch_rate"]["8_frame_fade_12.5ms"]
    assert doc["the_honest_part"]
    assert len(doc["what_it_does_NOT_catch"]) >= 4


def test_documented_detector_numbers_still_hold(real_codebook):
    """The three headline numbers are reproduced, not trusted."""
    m = ahc.measure_detector(real_codebook)
    doc = ahc.MOSAIC_DETECTOR_MEASUREMENTS
    assert m["exact_ola_replay_snr_db"] > 100, m
    assert m["source_filter_synth_snr_db"] < 15, m
    assert abs(m["source_filter_synth_snr_db"]
               - doc["source_filter_synth_snr_db"]) < 3.0, (
        f"documented synth SNR {doc['source_filter_synth_snr_db']} dB no longer "
        f"matches measured {m['source_filter_synth_snr_db']:.2f} dB")


def test_gate4_flags_a_recorded_clip(real_a, real_codebook):
    """(a) continued - the same real /a/ that passes gates 1-3 must be caught by
    gate 4 the moment its own frames are in the codebook. It is a recording."""
    v = ahc.judge_ah(real_a, SR, production_module=glottis.__file__,
                     codebook=real_codebook)
    assert not v.gates["provenance"].passed
    assert not v.passed, "a recording was crowned"


def test_provenance_unknown_is_a_failure():
    """No proof of provenance means no crown. An empty throne is the default."""
    y = glottis.articulate_vowel(
        f0_hz=ahc.AH_TARGET["f0_median_hz"],
        formants_hz=(ahc.AH_TARGET["F1"], ahc.AH_TARGET["F2"], 2600.0),
        duration_s=0.40, sr=SR, seed=5)
    v = ahc.judge_ah(y, SR)                       # no module, no codebook
    assert not v.gates["provenance"].passed
    assert not v.passed
    assert "unverified" in v.gates["provenance"].detail.lower()


# ==========================================================================
# (d) ACHIEVABILITY - MANDATORY
# ==========================================================================
def test_a_genuine_source_filter_vowel_passes_all_four_gates(real_codebook):
    """If nothing can pass, the law is worthless. This is the proof that a real
    synthesiser - impulse train through formant resonators, zero recorded
    samples anywhere in its call graph - can be crowned."""
    y = glottis.articulate_vowel(
        f0_hz=ahc.AH_TARGET["f0_median_hz"],
        formants_hz=(ahc.AH_TARGET["F1"], ahc.AH_TARGET["F2"], 2600.0),
        duration_s=0.40, sr=SR, seed=5)
    v = ahc.judge_ah(y, SR, production_module=glottis.__file__,
                     codebook=real_codebook)
    failed = [k for k, g in v.gates.items() if not g.passed]
    assert v.passed, "achievability FAILED, so the law is unsatisfiable: " + \
        "; ".join(f"{k}: {v.gates[k].detail}" for k in failed)


def test_achievability_is_robust_across_plausible_voices():
    """Not a single lucky seed: the law must be passable across the f0 range the
    corpus actually contains (male 113 Hz .. female 212 Hz)."""
    ok = 0
    for f0 in (115.0, 145.0, 186.0, 210.0):
        for seed in (1, 2, 3):
            y = glottis.articulate_vowel(
                f0_hz=f0, formants_hz=(ahc.AH_TARGET["F1"],
                                       ahc.AH_TARGET["F2"], 2600.0),
                duration_s=0.40, sr=SR, seed=seed)
            v = ahc.judge_ah(y, SR, production_module=glottis.__file__)
            ok += bool(v.gates["identity"].passed and v.gates["voicing"].passed
                       and v.gates["stability"].passed)
    assert ok >= 10, f"only {ok}/12 plausible voices could pass gates 1-3"


def test_the_mouth_holds_no_recorded_audio():
    """Belt and braces: no array in the module's namespace is long enough to be
    a stashed waveform."""
    for name in dir(glottis):
        obj = getattr(glottis, name)
        if isinstance(obj, np.ndarray):
            assert obj.size < 64, f"glottis.{name} looks like stored audio"


# ==========================================================================
# THE REAL OUTPUT - the thing Iddo actually listened to
# ==========================================================================
QUEEN_WAV = os.path.join(HERE, "state", "queen-listen", "queen_RAW_20260813.wav")
QUEEN_CKPT = os.path.join(HERE, "state-hebbian", "vowel-cochlea",
                          "queen-ant-a", "current.json")


def test_the_reigning_queens_actual_production_fails_all_four_gates():
    """The one test that matters most.

    state/coronation.json crowns this queen on syllable_cos_top1 = 0.758, a
    PERCEPTION score. Iddo listened to what she PRODUCES and said it is garbage.
    A judge that cannot reproduce that verdict is worthless, however elegant.

    Both facts stay true: the 0.758 is real, and the sound is bad. This test
    pins the second one so it can never again be lost behind the first.
    """
    if not (os.path.exists(QUEEN_WAV) and os.path.exists(QUEEN_CKPT)):
        pytest.skip("queen render / checkpoint not on this machine")
    ck = json.load(open(QUEEN_CKPT, encoding="utf-8"))
    codebook = np.asarray(ck["exemplars_pcm16"], dtype=np.float32) / 32768.0
    y = _read(QUEEN_WAV)
    v = ahc.judge_ah(y, SR,
                     production_module=os.path.join(HERE, "acoustic_units.py"),
                     codebook=codebook,
                     codebook_frame=ck["exemplar_frame_samples"],
                     codebook_hop=ck["exemplar_hop_samples"])
    assert not v.passed
    for g in ("identity", "voicing", "stability", "provenance"):
        assert not v.gates[g].passed, \
            f"gate {g} PASSED the production Iddo called garbage: " \
            f"{v.gates[g].detail}"
    # and specifically: it is a mosaic of its own exemplar bank
    assert "REPLAY" in v.gates["provenance"].detail


# ==========================================================================
# Rungs 2 and 3 - declared, not yet implemented
# ==========================================================================
def test_ba_and_ga_are_declared_but_not_open():
    for fn, extra in ((ahc.judge_ba, ahc.EXTRA_GATES_BA),
                      (ahc.judge_ga, ahc.EXTRA_GATES_GA)):
        assert callable(fn)
        assert {"closure", "burst", "transition"} <= set(extra)
        with pytest.raises(NotImplementedError):
            fn(np.zeros(SR, dtype=np.float32), SR)


def test_ga_does_not_gate_on_the_unmeasured_velar_pinch():
    """The velar pinch extraction failed on real speech (0.3 velar vs 0.3
    bilabial - no separation). It must not be a gate until it is fixed."""
    assert ahc.EXTRA_GATES_GA["velar_pinch"]["gating"] is False


# ==========================================================================
# Thresholds must be honest
# ==========================================================================
def test_the_law_does_not_reject_human_speech():
    """A law that no human /a/ can satisfy is not strict, it is broken. The
    held-out calibration must show the non-circular gates accepting the majority
    of real /a/."""
    c = ahc.HELDOUT_CALIBRATION["on_60_real_a_segments"]
    assert int(c["gate2_voicing_pass"].rstrip("%")) >= 60
    assert int(c["gate3_stability_pass"].rstrip("%")) >= 60
    assert ahc.HELDOUT_CALIBRATION["what_this_does_NOT_establish"]


def test_no_crown_without_a_listening_test():
    """The failure being fixed is a good number over a bad sound. Nothing in this
    file may be read as authority to crown anyone."""
    assert "LISTEN" in ahc.HELDOUT_CALIBRATION["what_this_does_NOT_establish"]
    assert "empty throne" in ahc.__doc__.lower()


def test_every_threshold_declares_where_it_came_from():
    for name, meta in ahc.THRESHOLD_PROVENANCE.items():
        assert name in ahc.GATES, f"{name} documented but not used"
        assert meta.get("source"), f"{name} has no stated source"
        assert "heldout" not in meta["source"].lower(), \
            f"{name} was fitted on held-out data"
    for name in ahc.GATES:
        assert name in ahc.THRESHOLD_PROVENANCE, f"{name} has no provenance"
