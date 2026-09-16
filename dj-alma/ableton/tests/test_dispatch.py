# -*- coding: utf-8 -*-
"""test_dispatch.py -- tests the mapping from protocol-style commands
(bridge/protocol.py's own command table, reused unchanged) to Live Object
Model calls, against fake_live.py. No Ableton process, no Live import, no
audio device anywhere in this test -- run with plain pytest or directly with
`python test_dispatch.py`.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ABLETON_DIR = os.path.dirname(HERE)  # D:\CLAUDE\dj-alma\ableton
if ABLETON_DIR not in sys.path:
    sys.path.insert(0, ABLETON_DIR)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import fake_live
from DJ_ALMIDO.dispatch import dispatch, DispatchState, HANDLERS
from DJ_ALMIDO.protocol_bridge import protocol


def make_state(**kw):
    song = fake_live.FakeSong(**kw)
    state = DispatchState(song=song, live_module=fake_live.FakeLiveModule, log_fn=lambda *_: None)
    return song, state


def test_all_protocol_commands_have_handlers():
    missing = [name for _, (name, _) in protocol.COMMANDS.items() if name not in HANDLERS]
    assert not missing, f"protocol commands with no DJ_ALMIDO handler: {missing}"


def test_play_stop():
    song, state = make_state()
    r = dispatch(state, {"cmd": "PLAY"})
    assert r["ok"] is True
    assert song.play_calls == 1
    r = dispatch(state, {"cmd": "STOP"})
    assert r["ok"] is True
    assert song.stop_calls == 1


def test_record_toggle():
    song, state = make_state()
    assert song.record_mode is False
    r = dispatch(state, {"cmd": "RECORD_TOGGLE"})
    assert r["ok"] and r["result"]["record_mode"] is True
    assert song.record_mode is True


def test_stop_all_clips():
    song, state = make_state()
    r = dispatch(state, {"cmd": "STOP_ALL_CLIPS"})
    assert r["ok"]
    assert song.stop_all_clips_calls == 1


def test_set_tempo_uses_protocol_mapping():
    song, state = make_state()
    r = dispatch(state, {"cmd": "SET_TEMPO", "param": 0})
    assert r["ok"]
    assert abs(song.tempo - protocol.TEMPO_MIN_BPM) < 1e-6
    r = dispatch(state, {"cmd": "SET_TEMPO", "param": 127})
    assert abs(song.tempo - protocol.TEMPO_MAX_BPM) < 1e-6


def test_tempo_nudge_up_down():
    song, state = make_state()
    song.tempo = 140.0
    r = dispatch(state, {"cmd": "TEMPO_NUDGE_UP", "param": 2})  # 2 steps = 1.0 BPM
    assert r["ok"]
    assert abs(song.tempo - 141.0) < 1e-6
    r = dispatch(state, {"cmd": "TEMPO_NUDGE_DOWN", "param": 2})
    assert abs(song.tempo - 140.0) < 1e-6


def test_bass_vol_nudge_up_and_down():
    song, state = make_state()
    track = song.tracks[protocol.STEM_TRACK_INDEX["BASS"]]
    before = track.mixer_device.volume.value
    r = dispatch(state, {"cmd": "BASS_VOL", "param": protocol.nudge_param("up")})
    assert r["ok"]
    assert track.mixer_device.volume.value > before
    after_up = track.mixer_device.volume.value
    r = dispatch(state, {"cmd": "BASS_VOL", "param": protocol.nudge_param("down")})
    assert track.mixer_device.volume.value < after_up


def test_mute_toggle():
    song, state = make_state()
    track = song.tracks[protocol.STEM_TRACK_INDEX["LEAD"]]
    assert track.mute is False
    r = dispatch(state, {"cmd": "LEAD_MUTE_TOGGLE"})
    assert r["ok"] and track.mute is True
    dispatch(state, {"cmd": "LEAD_MUTE_TOGGLE"})
    assert track.mute is False


def test_section_fires_the_mapped_scene():
    song, state = make_state()
    r = dispatch(state, {"cmd": "SECTION_DROP"})
    assert r["ok"]
    idx = protocol.SECTION_COLUMN["DROP"]
    assert song.scenes[idx].fired == 1


def test_extend_section_refires_last_scene_and_errors_if_none_fired():
    song, state = make_state()
    r = dispatch(state, {"cmd": "EXTEND_SECTION", "param": 0})
    assert r["ok"] is False  # nothing fired yet this session -> honest error, not a silent no-op

    dispatch(state, {"cmd": "SECTION_BUILD"})
    r = dispatch(state, {"cmd": "EXTEND_SECTION", "param": 0})
    assert r["ok"] is True
    idx = protocol.SECTION_COLUMN["BUILD"]
    assert song.scenes[idx].fired == 2


def test_create_midi_track_appends_and_names():
    song, state = make_state(n_tracks=2)
    r = dispatch(state, {"cmd": "CREATE_MIDI_TRACK", "name": "ALMIDO Drop"})
    assert r["ok"], r
    assert r["result"]["track_index"] == 2
    assert len(song.tracks) == 3
    assert song.tracks[2].name == "ALMIDO Drop"


def test_write_notes_creates_clip_and_adds_notes():
    song, state = make_state()
    notes = [
        {"pitch": 60, "start_time": 0.0, "duration": 0.5, "velocity": 100},
        {"pitch": 64, "start_time": 0.5, "duration": 0.5, "velocity": 90, "mute": 0},
    ]
    r = dispatch(state, {
        "cmd": "WRITE_NOTES", "track_index": 0, "clip_slot_index": 0,
        "notes": notes, "clip_length_beats": 4.0,
    })
    assert r["ok"], r
    assert r["result"]["n_notes"] == 2
    clip = song.tracks[0].clip_slots[0].clip
    assert clip is not None
    assert len(clip.added_notes[0]) == 2
    spec0 = clip.added_notes[0][0]
    assert spec0.pitch == 60
    assert spec0.duration == 0.5


def test_write_notes_rejects_out_of_range_pitch():
    song, state = make_state()
    notes = [{"pitch": 200, "start_time": 0.0, "duration": 0.5}]
    r = dispatch(state, {
        "cmd": "WRITE_NOTES", "track_index": 0, "clip_slot_index": 0,
        "notes": notes, "clip_length_beats": 4.0,
    })
    assert r["ok"] is False
    assert "pitch" in r["error"]


def test_write_notes_rejects_negative_duration():
    song, state = make_state()
    notes = [{"pitch": 60, "start_time": 0.0, "duration": -1.0}]
    r = dispatch(state, {
        "cmd": "WRITE_NOTES", "track_index": 0, "clip_slot_index": 0,
        "notes": notes, "clip_length_beats": 4.0,
    })
    assert r["ok"] is False


def test_write_notes_rejects_bad_track_index():
    song, state = make_state(n_tracks=2)
    r = dispatch(state, {
        "cmd": "WRITE_NOTES", "track_index": 99, "clip_slot_index": 0,
        "notes": [], "clip_length_beats": 4.0,
    })
    assert r["ok"] is False


def test_write_notes_overwrites_existing_clip():
    song, state = make_state()
    slot = song.tracks[0].clip_slots[0]
    slot.create_clip(4.0)  # pre-existing clip
    assert slot.has_clip is True
    r = dispatch(state, {
        "cmd": "WRITE_NOTES", "track_index": 0, "clip_slot_index": 0,
        "notes": [{"pitch": 60, "start_time": 0.0, "duration": 1.0}],
        "clip_length_beats": 8.0,
    })
    assert r["ok"], r
    assert ("delete_clip",) in slot.calls


def test_unknown_command():
    song, state = make_state()
    r = dispatch(state, {"cmd": "NOT_A_REAL_COMMAND"})
    assert r["ok"] is False


def test_missing_cmd_field():
    song, state = make_state()
    r = dispatch(state, {})
    assert r["ok"] is False


def test_ping():
    song, state = make_state(n_tracks=3, n_scenes=5)
    r = dispatch(state, {"cmd": "PING"})
    assert r["ok"]
    assert r["result"]["n_tracks"] == 3
    assert r["result"]["n_scenes"] == 5


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
