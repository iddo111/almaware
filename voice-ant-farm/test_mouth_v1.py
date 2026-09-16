# -*- coding: utf-8 -*-
"""Tests for mouth_v1 - written BEFORE the module exists.

The law first, then something built to satisfy it.

mouth_v1 must be an ARTICULATORY mouth: articulator numbers in, waveform out.
Not a formant dial (glottis.py already is one, and it passes) - a real tube whose
resonances EMERGE from a tongue position, a jaw angle and a lip aperture. That is
what a colony can learn to drive, and what a body can later be built to match.

The hard requirement is structural: this module must reach no recorded waveform.
head_sim.py - the existing articulatory synth - FAILS that audit today, not
because it replays anything but because its write_wav() helper imports `wave`.
The mouth may not carry a file writer. mouth_v1 carries none.
"""
from __future__ import annotations

import inspect
import math

import numpy as np
import pytest

import ah_criterion as A
import mouth_v1 as M

SR = 16000


# ==========================================================================
# PROVENANCE - the load-bearing tests. A mouth that can open a file is not a
# mouth, it is a tape deck with extra steps.
# ==========================================================================
def test_mouth_v1_passes_the_static_provenance_audit():
    viols = A.audit_production_module(M.__file__)
    assert viols == [], "mouth_v1 must reach no recorded waveform: " + \
        "; ".join(str(v) for v in viols)


def test_grep_agrees_with_the_ast_audit():
    hits = A.grep_proof(M.__file__)
    assert hits == [], f"grep found a waveform bank reference: {hits}"


def test_the_audit_still_fires_on_the_known_replay_path():
    """A gate that never fires is not a gate. acoustic_units.py must fail."""
    viols = A.audit_production_module("acoustic_units.py")
    assert len(viols) > 0


def test_head_sim_fails_the_audit_only_because_it_carries_a_file_writer():
    """Documents exactly why the pre-existing articulatory synth cannot be
    crowned as-is. This is a structural failure, not a replay one."""
    viols = A.audit_production_module("head_sim.py")
    reasons = "; ".join(str(v) for v in viols)
    assert viols, "expected head_sim to fail the audit"
    assert all(("wave" in str(v)) for v in viols), reasons


def test_the_old_articulatory_synth_can_say_ah_it_just_cannot_prove_it():
    """The finding that matters most for the throne, pinned so it cannot be
    lost: head_sim's tube reaches the /a/ target DEAD ON when it is actually
    driven. What stops it being crowned is `import wave` sitting in its call
    graph - a file writer, not a tape. The gap is provenance, not physics."""
    import head_sim as H
    motor = {"breath": 0.80, "pitch": 0.46, "press": 0.8922,
             "tongue_x": 0.6133, "tongue_y": 0.2714, "lips": 1.00, "jaw": 1.00}
    y = H.synth(motor, seconds=0.45, seed=5)
    v = A.judge_ah(y, SR, production_module="head_sim.py")
    assert v.gates["identity"].passed, v.gates["identity"].detail
    assert v.gates["voicing"].passed, v.gates["voicing"].detail
    assert v.gates["stability"].passed, v.gates["stability"].detail
    assert not v.gates["provenance"].passed, "head_sim must still fail gate 4"


def test_the_signature_takes_only_numbers():
    sig = inspect.signature(M.articulate)
    for name, p in sig.parameters.items():
        assert p.default is inspect.Parameter.empty or \
            isinstance(p.default, (int, float)), \
            f"parameter {name} defaults to a non-number: {p.default!r}"


# ==========================================================================
# PHYSICS - it must be a real tube, not a filter bank pretending
# ==========================================================================
def _spectrum_peaks(y, sr, n_peaks=3, fmax=3000.0):
    w = np.asarray(y, dtype=np.float64)
    w = w * np.hanning(w.size)
    mag = np.abs(np.fft.rfft(w, n=8192))
    fr = np.fft.rfftfreq(8192, 1.0 / sr)
    keep = fr <= fmax
    mag, fr = mag[keep], fr[keep]
    idx = [i for i in range(1, len(mag) - 1)
           if mag[i] > mag[i - 1] and mag[i] > mag[i + 1]]
    idx.sort(key=lambda i: -mag[i])
    return sorted(float(fr[i]) for i in idx[:n_peaks])


def test_a_uniform_tube_resonates_at_odd_multiples():
    """Closed at the glottis, open at the lips: 1:3:5. If this fails, the
    waveguide is not a tube and no vowel it makes means anything."""
    bore = np.full(M.N_SECTIONS, 1.8)
    imp = np.zeros(4096)
    imp[0] = 1.0
    y = M.run_tract(imp, bore, loss=0.995)
    peaks = _spectrum_peaks(y, SR, n_peaks=3)
    expect = [500.0, 1500.0, 2500.0]
    for got, want in zip(peaks, expect):
        assert abs(got - want) / want < 0.10, f"peaks {peaks} vs {expect}"


def _measure_f1_f2(y, sr=SR):
    """Measuring is the JUDGE's job, never the mouth's - so this helper lives
    in the test file and uses ah_criterion's own tracker."""
    tr = A._track_for_judging(np.asarray(y, dtype=np.float64), sr)
    assert tr, "no formant track at all"
    f1 = float(np.median([f["f1"] for f in tr]))
    f2 = float(np.median([f["f2"] for f in tr]))
    return f1, f2


def test_the_tongue_actually_moves_the_vowel():
    """Front vs back tongue must change F2 by hundreds of Hz. If it does not,
    the articulators are decoration."""
    front = M.articulate(tongue_x=0.05, tongue_y=0.70, lips=0.9, jaw=0.6,
                         seconds=0.35, seed=1)
    back = M.articulate(tongue_x=0.95, tongue_y=0.70, lips=0.9, jaw=0.6,
                        seconds=0.35, seed=1)
    f_front = _measure_f1_f2(front)
    f_back = _measure_f1_f2(back)
    assert abs(f_front[1] - f_back[1]) > 200.0, (f_front, f_back)


def test_no_breath_no_sound():
    y = M.articulate(breath=0.0, seconds=0.2)
    assert float(np.max(np.abs(y))) < 1e-6


def test_same_seed_same_waveform():
    a = M.articulate(seconds=0.2, seed=3)
    b = M.articulate(seconds=0.2, seed=3)
    assert np.array_equal(a, b)
    c = M.articulate(seconds=0.2, seed=4)
    assert not np.array_equal(a, c)


def test_returns_float32_of_the_right_length():
    y = M.articulate(seconds=0.4)
    assert y.dtype == np.float32
    assert abs(len(y) - int(0.4 * SR)) <= 1


# ==========================================================================
# THE POINT - it must actually be able to say /a/
# ==========================================================================
def test_the_tuned_articulation_is_declared():
    for k in ("breath", "pitch", "press", "tongue_x", "tongue_y", "lips", "jaw"):
        assert k in M.AH, f"AH is missing motor {k}"
        assert 0.0 <= M.AH[k] <= 1.0


def test_it_can_say_ah():
    """The whole reason the module exists. All four gates, judged by
    ah_criterion, with mouth_v1 itself as the audited production module."""
    y = M.articulate(seconds=0.45, seed=5, **M.AH)
    v = A.judge_ah(y, SR, production_module=M.__file__)
    assert v.passed, v.summary()


def test_saying_ah_is_not_one_lucky_seed():
    ok = 0
    for seed in (1, 2, 3, 4, 5, 6):
        y = M.articulate(seconds=0.45, seed=seed, **M.AH)
        v = A.judge_ah(y, SR, production_module=M.__file__)
        if all(v.gates[g].passed for g in ("identity", "voicing", "stability")):
            ok += 1
    assert ok >= 5, f"only {ok}/6 seeds passed gates 1-3"


def test_saying_ah_survives_a_change_of_pitch():
    """A vowel is a tube shape, not a pitch. Moving f0 must not lose /a/."""
    ok = 0
    for pitch in (0.25, 0.35, 0.46, 0.60):
        y = M.articulate(seconds=0.45, seed=2, **{**M.AH, "pitch": pitch})
        v = A.judge_ah(y, SR, production_module=M.__file__)
        if v.gates["identity"].passed:
            ok += 1
    assert ok >= 3, f"identity held for only {ok}/4 pitches"


def test_a_different_vowel_is_rejected():
    """The gate must not crown anything the tube happens to emit."""
    y = M.articulate(seconds=0.45, seed=5, **M.EE)
    v = A.judge_ah(y, SR, production_module=M.__file__)
    assert not v.gates["identity"].passed, v.gates["identity"].detail


def test_jitter_is_load_bearing_not_decoration():
    """With zero jitter and zero shimmer the source is a pulse oscillator.
    It should still be voiced - but the module must expose the knob, and the
    living setting must be the default."""
    sig = inspect.signature(M.articulate)
    assert sig.parameters["jitter"].default > 0.0
    assert sig.parameters["shimmer"].default > 0.0


def test_it_is_not_reconstructible_from_a_bank_of_recorded_frames():
    """Gate 4b, empirically: the honest mouth must NOT rebuild out of the
    reigning queen's stored frames."""
    ck = M_codebook()
    if ck is None:
        pytest.skip("no checkpoint bank on disk to test against")
    y = M.articulate(seconds=0.45, seed=5, **M.AH)
    flagged, snr = A.looks_like_replay(y, ck)
    assert not flagged, f"honest articulation rebuilt at {snr:.1f} dB"


def M_codebook():
    """The REIGNING QUEEN's own stored frame bank, 512 x 400 raw recorded PCM -
    the very thing acoustic_units.synthesize_units() overlap-adds. THE TEST may
    read files; the MOUTH may not. That asymmetry is the whole design."""
    import json
    from pathlib import Path
    p = Path("state-hebbian/vowel-cochlea/queen-ant-a/current.json")
    if not p.exists():
        return None
    with open(p, "r", encoding="utf-8") as fh:
        ck = json.load(fh)
    bank = ck.get("exemplars_pcm16")
    if bank is None:
        return None
    return np.asarray(bank, dtype=np.float64) / 32768.0
