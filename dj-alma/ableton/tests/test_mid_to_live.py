# -*- coding: utf-8 -*-
"""test_mid_to_live.py -- tests for the Chai-MIDI -> Ableton import path
(../mid_to_live.py) and for the two JSON-only dispatch commands it needs
(SET_TEMPO_EXACT, SET_SONG_SCALE) plus WRITE_NOTES' optional clip_name.

No Ableton process, no Live import, no socket, no audio device. The MIDI
fixtures are two real compositions by Chai the Songbird, fetched read-only
from eran4's ~/darwish-midi/songs/outbox/ -- testing against his ACTUAL output
rather than a synthetic file is the point: the importer exists to handle what
he really writes (type-0, one track, channels 0 and 9, 140 BPM, monophonic
pitched line).
"""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ABLETON_DIR = os.path.dirname(HERE)  # D:\CLAUDE\dj-alma\ableton
for _p in (ABLETON_DIR, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import fake_live
import mid_to_live
from DJ_ALMIDO.dispatch import dispatch, DispatchState

CHAI_MID = os.path.join(ABLETON_DIR, "chai-in", "chai-20260912-020906.mid")


def make_state(**kw):
    song = fake_live.FakeSong(**kw)
    return song, DispatchState(song=song, live_module=fake_live.FakeLiveModule,
                               log_fn=lambda *_: None)


# --------------------------------------------------------- SET_TEMPO_EXACT
def test_set_tempo_exact_is_not_quantized():
    """The whole reason this command exists: the 0-127 SET_TEMPO cannot
    represent 140.000, and lands on 140.157 instead."""
    song, state = make_state()
    r = dispatch(state, {"cmd": "SET_TEMPO_EXACT", "bpm": 140.0})
    assert r["ok"] is True
    assert song.tempo == 140.0
    assert r["result"]["was_clamped"] is False

    # and prove the old path really does drift, so this test documents WHY
    from DJ_ALMIDO.protocol_bridge import protocol
    quantized = protocol.param_to_bpm(protocol.bpm_to_param(140.0))
    assert quantized != 140.0
    assert abs(quantized - 140.0) > 0.1


def test_set_tempo_exact_clamps_absurd_values():
    song, state = make_state()
    r = dispatch(state, {"cmd": "SET_TEMPO_EXACT", "bpm": 9000.0})
    assert r["ok"] is True
    assert r["result"]["was_clamped"] is True
    assert song.tempo == 160.0  # protocol.TEMPO_MAX_BPM


def test_set_tempo_exact_missing_bpm_fails_loudly():
    _, state = make_state()
    r = dispatch(state, {"cmd": "SET_TEMPO_EXACT"})
    assert r["ok"] is False


# --------------------------------------------------------- SET_SONG_SCALE
def test_set_song_scale_reports_failure_when_live_lacks_it():
    """Must NEVER claim success it did not achieve -- a wrong key showing in
    Live silently conforms every scale-aware device downstream."""
    _, state = make_state(supports_scale=False)
    r = dispatch(state, {"cmd": "SET_SONG_SCALE", "root_note": 9,
                         "scale_name": "Minor"})
    assert r["ok"] is False
    assert "root_note" in r["error"]


def test_set_song_scale_sets_it_when_available():
    song, state = make_state(supports_scale=True)
    r = dispatch(state, {"cmd": "SET_SONG_SCALE", "root_note": 9,
                         "scale_name": "Minor"})
    assert r["ok"] is True
    assert song.root_note == 9
    assert song.scale_name == "Minor"


def test_set_song_scale_rejects_out_of_range_root():
    _, state = make_state(supports_scale=True)
    r = dispatch(state, {"cmd": "SET_SONG_SCALE", "root_note": 12,
                         "scale_name": "Minor"})
    assert r["ok"] is False


# ------------------------------------------------------ WRITE_NOTES naming
def test_write_notes_names_the_clip():
    song, state = make_state()
    r = dispatch(state, {
        "cmd": "WRITE_NOTES", "track_index": 0, "clip_slot_index": 0,
        "notes": [{"pitch": 60, "start_time": 0.0, "duration": 1.0}],
        "clip_length_beats": 4.0, "clip_name": "chai Lead",
    })
    assert r["ok"] is True
    assert r["result"]["named"] is True
    assert song.tracks[0].clip_slots[0].clip.name == "chai Lead"


def test_write_notes_without_clip_name_still_works():
    _, state = make_state()
    r = dispatch(state, {
        "cmd": "WRITE_NOTES", "track_index": 0, "clip_slot_index": 0,
        "notes": [{"pitch": 60, "start_time": 0.0, "duration": 1.0}],
        "clip_length_beats": 4.0,
    })
    assert r["ok"] is True
    assert r["result"]["named"] is False
    assert r["result"]["clip_name"] is None


# ------------------------------------------------------------ note reading
@pytest.mark.skipif(not os.path.exists(CHAI_MID), reason="Chai fixture not fetched")
def test_reads_chai_file_structure():
    notes, bpm, tpb = mid_to_live.read_notes(CHAI_MID)
    assert bpm == 140.0
    assert tpb == 480
    channels = {n.channel for n in notes}
    assert channels == {0, 9}, f"expected Chai's ch0+ch9, got {channels}"
    assert len(notes) > 900
    # every note must have positive duration -- a zero-length note is silent
    assert all(n.duration_beats > 0 for n in notes)
    assert all(0 <= n.pitch <= 127 for n in notes)


@pytest.mark.skipif(not os.path.exists(CHAI_MID), reason="Chai fixture not fetched")
def test_chai_pitched_line_is_monophonic():
    """A measured property of his vocabulary, not a bug in the importer:
    every token is one drum + one bass degree, so at most one pitched note can
    sound at a time. If this ever fails, Chai gained harmony -- a real event."""
    notes, _, _ = mid_to_live.read_notes(CHAI_MID)
    pitched = [n for n in notes if n.channel != mid_to_live.DRUM_CHANNEL]
    assert mid_to_live.max_simultaneous(pitched) == 1


def test_note_off_as_note_on_velocity_zero(tmp_path):
    """Most writers encode note-off as note_on velocity 0; both must parse."""
    import mido
    mf = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    mf.tracks.append(track)
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(140), time=0))
    track.append(mido.Message("note_on", note=60, velocity=100, time=0))
    track.append(mido.Message("note_on", note=60, velocity=0, time=480))
    path = tmp_path / "zero_velocity.mid"
    mf.save(str(path))

    notes, bpm, _ = mid_to_live.read_notes(str(path))
    assert len(notes) == 1
    assert notes[0].duration_beats == pytest.approx(1.0)
    assert bpm == pytest.approx(140.0)


def test_hanging_note_is_closed_not_dropped(tmp_path):
    import mido
    mf = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    mf.tracks.append(track)
    track.append(mido.Message("note_on", note=64, velocity=90, time=0))
    track.append(mido.MetaMessage("end_of_track", time=960))
    path = tmp_path / "hanging.mid"
    mf.save(str(path))

    notes, _, _ = mid_to_live.read_notes(str(path))
    assert len(notes) == 1, "a sustained final note must not be silently dropped"
    assert notes[0].duration_beats > 0


# -------------------------------------------------------------- key detect
@pytest.mark.skipif(not os.path.exists(CHAI_MID), reason="Chai fixture not fetched")
def test_detects_a_minor_in_chai():
    notes, _, _ = mid_to_live.read_notes(CHAI_MID)
    root, scale, confidence, _ = mid_to_live.detect_key(notes)
    assert root == 9, f"expected A (9), got {root}"
    assert scale == "Minor"
    assert confidence > mid_to_live.KEY_CONFIDENCE_FLOOR


def test_key_detection_ignores_drums():
    """Drum notes are pitch numbers too; counting them would poison the key."""
    notes = [
        mid_to_live.Note(9, 36, 0.0, 0.25, 100),
        mid_to_live.Note(9, 42, 0.5, 0.25, 100),
    ]
    root, scale, confidence, _ = mid_to_live.detect_key(notes)
    assert root is None and scale is None and confidence == 0.0


def test_key_detection_is_duration_weighted():
    """A long tonic should outweigh a short passing tone."""
    long_c = [mid_to_live.Note(0, 60, 0.0, 16.0, 100)]
    root, _, _, _ = mid_to_live.detect_key(long_c)
    assert root == 0  # C


# ------------------------------------------------------------ part splitting
def test_default_split_is_one_part_per_channel():
    notes = [
        mid_to_live.Note(0, 45, 0.0, 1.0, 100),   # below MIDI 52
        mid_to_live.Note(0, 64, 1.0, 1.0, 100),   # above MIDI 52
        mid_to_live.Note(9, 36, 0.0, 0.25, 100),
    ]
    parts = mid_to_live.split_parts(notes, split_register=False)
    assert [name for name, _ in parts] == ["Lead", "Drums"]
    assert len(parts[0][1]) == 2, "a monophonic line must NOT be split by default"


def test_split_register_is_opt_in_and_splits():
    notes = [
        mid_to_live.Note(0, 45, 0.0, 1.0, 100),
        mid_to_live.Note(0, 64, 1.0, 1.0, 100),
        mid_to_live.Note(9, 36, 0.0, 0.25, 100),
    ]
    parts = dict((name, ns) for name, ns in
                 mid_to_live.split_parts(notes, split_register=True))
    assert set(parts) == {"Bass", "Lead", "Drums"}
    assert parts["Bass"][0].pitch == 45
    assert parts["Lead"][0].pitch == 64


def test_split_register_does_not_make_empty_tracks():
    """If everything is above the line there is no bass part to make."""
    notes = [mid_to_live.Note(0, 64, 0.0, 1.0, 100),
             mid_to_live.Note(0, 67, 1.0, 1.0, 100)]
    parts = mid_to_live.split_parts(notes, split_register=True)
    assert [name for name, _ in parts] == ["Lead"]


# --------------------------------------------------------------- clip length
def test_clip_length_rounds_up_to_whole_bars():
    """A clip ending mid-bar loops off-grid, which ruins the one job it has."""
    notes = [mid_to_live.Note(0, 60, 0.0, 9.5, 100)]  # ends at beat 9.5
    assert mid_to_live.clip_length_beats(notes) == 12.0  # 3 bars


def test_clip_length_exact_bar_is_not_extended():
    notes = [mid_to_live.Note(0, 60, 0.0, 8.0, 100)]
    assert mid_to_live.clip_length_beats(notes) == 8.0


def test_clip_length_of_empty_part():
    assert mid_to_live.clip_length_beats([]) == 4.0


def test_max_simultaneous_counts_overlap_correctly():
    overlapping = [
        mid_to_live.Note(0, 60, 0.0, 2.0, 100),
        mid_to_live.Note(0, 64, 1.0, 2.0, 100),
        mid_to_live.Note(0, 67, 1.5, 2.0, 100),
    ]
    assert mid_to_live.max_simultaneous(overlapping) == 3
    # a note ending exactly where the next begins is NOT simultaneous
    adjacent = [
        mid_to_live.Note(0, 60, 0.0, 1.0, 100),
        mid_to_live.Note(0, 64, 1.0, 1.0, 100),
    ]
    assert mid_to_live.max_simultaneous(adjacent) == 1


# ---------------------------------------------------------------- the plan
@pytest.mark.skipif(not os.path.exists(CHAI_MID), reason="Chai fixture not fetched")
def test_build_plan_on_real_chai_file():
    plan = mid_to_live.build_plan(CHAI_MID)
    assert plan["bpm"] == 140.0
    assert plan["key_root_name"] == "A"
    assert plan["key_scale"] == "Minor"
    assert plan["key_will_be_sent"] is True
    assert [p["part_name"] for p in plan["parts"]] == ["Lead", "Drums"]
    # every note the file contains must reach the plan -- none dropped
    assert sum(p["n_notes"] for p in plan["parts"]) == plan["n_notes_total"]
    for p in plan["parts"]:
        assert p["clip_length_beats"] % mid_to_live.BEATS_PER_BAR == 0
        assert p["clip_name"].startswith("chai-20260912-020906")


@pytest.mark.skipif(not os.path.exists(CHAI_MID), reason="Chai fixture not fetched")
def test_all_clips_share_one_length_so_they_loop_in_phase():
    """Chai's lead runs 224 beats and his drums 220. Written at their own
    lengths they loop at different periods and walk out of phase after the
    first pass, which destroys the only thing this importer is for."""
    plan = mid_to_live.build_plan(CHAI_MID)
    lengths = {p["clip_length_beats"] for p in plan["parts"]}
    assert len(lengths) == 1, f"clips would drift apart: {lengths}"
    assert lengths.pop() == max(p["own_length_beats"] for p in plan["parts"])


def test_padding_never_moves_a_note():
    """Unifying clip length must change only the loop brace, never a note."""
    notes = [mid_to_live.Note(0, 60, 0.0, 40.0, 100),
             mid_to_live.Note(9, 36, 0.0, 1.0, 100)]
    parts = mid_to_live.split_parts(notes)
    unified = max(mid_to_live.clip_length_beats(ns) for _, ns in parts)
    assert unified == 40.0
    for _, ns in parts:
        for n in ns:
            assert n.start_beats + n.duration_beats <= unified


@pytest.mark.skipif(not os.path.exists(CHAI_MID), reason="Chai fixture not fetched")
def test_plan_preserves_every_pitch_exactly():
    """The discipline this file claims: no transposition, no quantization."""
    notes, _, _ = mid_to_live.read_notes(CHAI_MID)
    plan = mid_to_live.build_plan(CHAI_MID)
    source = sorted((n.pitch, round(n.start_beats, 6)) for n in notes)
    planned = sorted((s["pitch"], round(s["start_time"], 6))
                     for p in plan["parts"] for s in p["notes"])
    assert source == planned


def test_dry_run_opens_no_socket(monkeypatch, tmp_path):
    """--dry-run must be provably inert: if it opened a socket this fails."""
    import socket as socket_module

    def explode(*a, **kw):
        raise AssertionError("dry run tried to open a socket")

    monkeypatch.setattr(socket_module, "create_connection", explode)

    import mido
    mf = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    mf.tracks.append(track)
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(140), time=0))
    track.append(mido.Message("note_on", note=57, velocity=100, time=0))
    track.append(mido.Message("note_off", note=57, velocity=0, time=480))
    path = tmp_path / "tiny.mid"
    mf.save(str(path))

    plan = mid_to_live.build_plan(str(path))
    assert mid_to_live.send_plan(plan, "127.0.0.1", 8865, dry_run=True) == 0


def test_missing_file_exits_nonzero(capsys):
    assert mid_to_live.main(["no-such-file.mid"]) == 2
