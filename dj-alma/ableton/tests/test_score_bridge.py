# -*- coding: utf-8 -*-
"""test_score_bridge.py -- validates the Score -> WRITE_NOTES note-spec
conversion (score_bridge.py): every note lands in MIDI pitch range, no
negative/zero durations, and the beats-per-step arithmetic matches
poly_tok.STEPS_PER_BAR.

Builds a small synthetic PT.Score directly rather than running the Darwish
model -- poly_tok.py is pure tokenization/dataclass code with no torch or
checkpoint dependency (verified by reading its imports), so this needs no
GPU and no trained model to run.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ABLETON_DIR = os.path.dirname(HERE)  # D:\CLAUDE\dj-alma\ableton
if ABLETON_DIR not in sys.path:
    sys.path.insert(0, ABLETON_DIR)

import score_bridge          # ableton/score_bridge.py -- inserts booth/ onto sys.path itself
from compose import PT       # booth/compose.py's own `import poly_tok as PT`, reused


def make_score():
    notes = [
        PT.Note(step=0, midi=60, dur=4),   # beat 0, quarter note, alone -> lead (>=52)
        PT.Note(step=4, midi=64, dur=2),   # beat 1 -- sounds with the next note -> chord
        PT.Note(step=4, midi=67, dur=2),   # simultaneous with the above
        PT.Note(step=8, midi=36, dur=8),   # low register, alone -> bass (<52)
    ]
    return PT.Score(bpm=143.55, key_pc=0, n_steps=32, notes=notes, drums=[], source="unit-test")


def test_steps_per_beat_matches_poly_tok():
    assert score_bridge.steps_per_beat() == PT.STEPS_PER_BAR / 4.0


def test_note_count_preserved():
    sc = make_score()
    notes = score_bridge.score_to_notes(sc)
    assert len(notes) == len(sc.notes)


def test_all_pitches_in_midi_range():
    sc = make_score()
    for n in score_bridge.score_to_notes(sc):
        assert 0 <= n["pitch"] <= 127


def test_no_negative_or_zero_durations():
    sc = make_score()
    for n in score_bridge.score_to_notes(sc):
        assert n["duration"] > 0
        assert n["start_time"] >= 0


def test_start_time_and_duration_are_beats_not_steps():
    sc = make_score()
    notes = score_bridge.score_to_notes(sc)
    spb = score_bridge.steps_per_beat()
    first = notes[0]
    assert first["pitch"] == 60
    assert abs(first["start_time"] - 0 / spb) < 1e-9
    assert abs(first["duration"] - 4 / spb) < 1e-9


def test_out_of_range_pitch_is_dropped_not_clamped():
    sc = make_score()
    sc.notes.append(PT.Note(step=16, midi=200, dur=4))
    notes = score_bridge.score_to_notes(sc)
    assert all(n["pitch"] != 200 for n in notes)
    assert len(notes) == 4  # the 4 valid notes; the out-of-range one is dropped, not clamped in


def test_zero_or_negative_source_dur_becomes_at_least_one_step():
    sc = make_score()
    sc.notes.append(PT.Note(step=20, midi=50, dur=0))
    notes = score_bridge.score_to_notes(sc)
    added = [n for n in notes if n["pitch"] == 50][0]
    assert added["duration"] >= 1.0 / score_bridge.steps_per_beat()


def test_score_length_beats():
    sc = make_score()
    expected = sc.n_steps / (PT.STEPS_PER_BAR / 4.0)
    assert abs(score_bridge.score_length_beats(sc) - expected) < 1e-9


def test_roles_produce_only_known_role_velocities():
    sc = make_score()
    notes = score_bridge.score_to_notes(sc, assign_roles=True)
    velocities = {n["velocity"] for n in notes}
    assert velocities.issubset(set(score_bridge.ROLE_VELOCITY.values()))


def test_assign_roles_false_uses_flat_lead_velocity():
    sc = make_score()
    notes = score_bridge.score_to_notes(sc, assign_roles=False)
    assert all(n["velocity"] == score_bridge.ROLE_VELOCITY["lead"] for n in notes)


if __name__ == "__main__":
    import inspect
    fails = 0
    tests = [obj for name, obj in sorted(globals().items())
             if name.startswith("test_") and inspect.isfunction(obj)]
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            fails += 1
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            fails += 1
            print(f"ERROR {t.__name__}: {e!r}")
    print(f"\n{len(tests) - fails}/{len(tests)} passed")
    sys.exit(1 if fails else 0)
