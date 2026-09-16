# -*- coding: utf-8 -*-
"""dispatch.py -- maps one incoming JSON command to Live Object Model (LOM)
calls, using the SAME command names/param encodings as bridge/protocol.py
(imported via protocol_bridge.py, not re-typed here) plus two commands
Mixcraft's controller script could never have: CREATE_MIDI_TRACK and
WRITE_NOTES.

Kept free of any Live-specific import at module scope except through the
`state.live_module` indirection, so this file can be unit-tested against a
fake Live with no Ableton process anywhere nearby -- see
../tests/fake_live.py and ../tests/test_dispatch.py. state.song and
state.live_module are the only two things this file ever touches; nothing
here imports the real `Live` package directly.

Every handler takes (state, msg) and returns a plain dict (the "result" of a
successful call) OR raises -- dispatch() below converts a raised exception
into {"ok": false, "error": ...} so a bad command from voice_to_live.py can
never take the tick loop down.
"""
from .protocol_bridge import protocol


class DispatchState:
    """Everything a handler needs, injected once (real Live objects from
    manager.py, or fakes from the tests)."""

    def __init__(self, song, live_module, log_fn=None):
        self.song = song
        self.live_module = live_module  # object exposing .Clip.MidiNoteSpecification
        self.log_fn = log_fn or (lambda *a, **k: None)
        self.last_scene_index = None  # for EXTEND_SECTION's "re-fire the last one"

    def log(self, msg):
        self.log_fn(msg)


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


# ---------------------------------------------------------------- transport
def _play(state, msg):
    state.song.start_playing()
    return {}


def _stop(state, msg):
    state.song.stop_playing()
    return {}


def _record_toggle(state, msg):
    state.song.record_mode = not state.song.record_mode
    return {"record_mode": state.song.record_mode}


def _stop_all_clips(state, msg):
    state.song.stop_all_clips()
    return {}


# -------------------------------------------------------------------- tempo
def _set_tempo(state, msg):
    param = int(msg.get("param", 0))
    bpm = protocol.param_to_bpm(param)
    state.song.tempo = bpm
    return {"bpm": bpm}


def _tempo_nudge(state, msg, direction: str):
    # protocol.py: "0-127 -> number of 0.5 BPM steps (param, not scaled)"
    steps = int(msg.get("param", 0))
    delta = 0.5 * steps * (1 if direction == "up" else -1)
    new_bpm = _clamp(state.song.tempo + delta, protocol.TEMPO_MIN_BPM, protocol.TEMPO_MAX_BPM)
    state.song.tempo = new_bpm
    return {"bpm": new_bpm}


# --------------------------------------------------------- stems (mixer)
def _resolve_track(state, stem_name: str):
    """stem_name is a key of protocol.STEM_TRACK_INDEX (BASS/LEAD/DRUMS/FX)
    or the literal 'MASTER'. Raises IndexError with a clear message if the
    placeholder index does not exist on this project yet -- these indices
    are PLACEHOLDERS in protocol.py, same caveat as the Mixcraft bridge:
    Iddo's real Ableton track layout must be reflected there before this is
    trusted blind."""
    if stem_name == "MASTER":
        return state.song.master_track
    idx = protocol.STEM_TRACK_INDEX[stem_name]
    tracks = state.song.tracks
    if idx >= len(tracks):
        raise IndexError(
            f"STEM_TRACK_INDEX[{stem_name!r}]={idx} but song only has "
            f"{len(tracks)} track(s) -- edit protocol.STEM_TRACK_INDEX to "
            f"match the real Ableton project layout."
        )
    return tracks[idx]


def _stem_vol(state, msg, stem_name: str):
    track = _resolve_track(state, stem_name)
    param = int(msg.get("param", 64))
    # Mirrors protocol.py's NUDGE_UNIT_FRACTION design (same formula the
    # Mixcraft .js script used) -- see protocol.py's docstring on *_VOL.
    delta_units = (param - 64) / 16.0
    delta = delta_units * protocol.NUDGE_UNIT_FRACTION
    vol_param = track.mixer_device.volume
    new_value = _clamp(vol_param.value + delta, 0.0, 1.0)
    vol_param.value = new_value
    return {"track_volume": new_value}


def _stem_mute_toggle(state, msg, stem_name: str):
    track = _resolve_track(state, stem_name)
    track.mute = not track.mute
    return {"mute": track.mute}


# ------------------------------------------------------------- sections
def _section(state, msg, section_name: str):
    idx = protocol.SECTION_COLUMN[section_name]
    scenes = state.song.scenes
    if idx >= len(scenes):
        raise IndexError(
            f"SECTION_COLUMN[{section_name!r}]={idx} but song only has "
            f"{len(scenes)} scene(s) -- edit protocol.SECTION_COLUMN to "
            f"match Iddo's real Ableton Session View layout."
        )
    scenes[idx].fire()
    state.last_scene_index = idx
    return {"scene_index": idx}


def _extend_section(state, msg):
    # v1: re-fire the last section fired. There is no generic Ableton concept
    # of "make this scene's clips N bars longer" from outside -- Ableton
    # clips are pre-authored, unlike Mixcraft's Performance-grid columns
    # which protocol.py's EXTEND_SECTION comment was written against. Honest
    # partial implementation, not a silent no-op: if nothing has fired yet
    # this raises, so voice_to_live.py's caller sees a real error rather than
    # a command that looks like it worked.
    if state.last_scene_index is None:
        raise RuntimeError("EXTEND_SECTION: no section has been fired yet this session")
    scenes = state.song.scenes
    scenes[state.last_scene_index].fire()
    return {"scene_index": state.last_scene_index, "note": "re-fired last section (v1 has no bar-count extend)"}


# ---------------------------------------------------- the two new commands
def _create_midi_track(state, msg):
    name = msg.get("name") or "ALMIDO"
    index = int(msg.get("index", -1))
    before = len(state.song.tracks)
    state.song.create_midi_track(index)
    after = state.song.tracks
    if len(after) != before + 1:
        raise RuntimeError(f"create_midi_track did not add a track (before={before}, after={len(after)})")
    # LOM convention (mirrored from AbletonOSC's create_midi_track handling,
    # and Live's own Session View behaviour): index -1 appends at the end;
    # a non-negative index inserts there.
    new_index = (len(after) - 1) if index < 0 else index
    track = after[new_index]
    track.name = name
    return {"track_index": new_index, "name": track.name}


def _write_notes(state, msg):
    track_index = int(msg["track_index"])
    clip_slot_index = int(msg["clip_slot_index"])
    notes = msg["notes"]
    clip_length_beats = float(msg.get("clip_length_beats", 4.0))

    tracks = state.song.tracks
    if not (0 <= track_index < len(tracks)):
        raise IndexError(f"track_index {track_index} out of range (0..{len(tracks) - 1})")
    track = tracks[track_index]

    clip_slots = track.clip_slots
    if not (0 <= clip_slot_index < len(clip_slots)):
        raise IndexError(f"clip_slot_index {clip_slot_index} out of range (0..{len(clip_slots) - 1})")
    clip_slot = clip_slots[clip_slot_index]

    if getattr(clip_slot, "has_clip", False):
        clip_slot.delete_clip()  # v1 overwrites; no append-to-existing-clip mode yet
    clip_slot.create_clip(clip_length_beats)
    clip = clip_slot.clip

    spec_cls = state.live_module.Clip.MidiNoteSpecification
    specs = []
    for n in notes:
        pitch = int(n["pitch"])
        if not (0 <= pitch <= 127):
            raise ValueError(f"note pitch {pitch} out of MIDI range 0..127")
        duration = float(n["duration"])
        if duration <= 0:
            raise ValueError(f"note duration {duration} must be > 0")
        start_time = float(n["start_time"])
        if start_time < 0:
            raise ValueError(f"note start_time {start_time} must be >= 0")
        velocity = int(n.get("velocity", 100))
        mute = int(n.get("mute", 0))
        specs.append(spec_cls(start_time=start_time, duration=duration,
                              pitch=pitch, velocity=velocity, mute=mute))
    clip.add_new_notes(tuple(specs))

    # Optional clip name, so a Session View full of imported clips is readable
    # ("chai-20260912-020906 Lead") instead of five identically-blank slots.
    # Best effort on purpose: a Live that refuses the rename must not throw
    # away notes that were already written successfully.
    clip_name = msg.get("clip_name")
    named = False
    if clip_name:
        try:
            clip.name = str(clip_name)
            named = True
        except Exception:
            named = False

    return {"track_index": track_index, "clip_slot_index": clip_slot_index,
            "n_notes": len(specs), "clip_length_beats": clip_length_beats,
            "clip_name": str(clip_name) if named else None, "named": named}


def _set_tempo_exact(state, msg):
    """SET_TEMPO_EXACT -- set the tempo to a real float BPM.

    The original SET_TEMPO carries its value in ONE MIDI velocity byte
    (protocol.py: 0-127 linear across 120-160 BPM) because the Mixcraft wire
    format had nothing wider. That quantizes to ~0.315 BPM per step, so a
    140.000 BPM file lands in Live at 140.157 -- a silent mis-sync that makes
    an imported clip drift against anything else in the set. This command
    exists because DJ_ALMIDO speaks JSON, not MIDI: a float fits on the wire,
    so send the float.

    protocol.py is deliberately NOT modified to add this -- that file is the
    shared contract with the Mixcraft controller script, which genuinely
    cannot carry a float. This is a JSON-side-only command.

    Still clamped to protocol.py's TEMPO_MIN/MAX_BPM so a typo cannot drive
    Live to an absurd tempo in the middle of a set.
    """
    bpm = float(msg["bpm"])
    clamped = _clamp(bpm, protocol.TEMPO_MIN_BPM, protocol.TEMPO_MAX_BPM)
    state.song.tempo = clamped
    return {"bpm": clamped, "requested_bpm": bpm, "was_clamped": clamped != bpm}


# The Song attributes Live 12 uses for the global key. Both were measured to
# exist in this install's own LOM type table
# (Resources/MIDI Remote Scripts/_MxDCore/LomTypes.pyc, one occurrence each,
# alongside scale_intervals and scale_mode) -- but that table does not record
# which object owns them, and the attribute has moved between Live versions.
# Hence the hasattr check below rather than a bare assignment.
SCALE_ATTRS = ("root_note", "scale_name")


def _set_song_scale(state, msg):
    """SET_SONG_SCALE -- tell Live the key of the music just imported.

    BEST EFFORT BY DESIGN. If this Live's Song does not expose the scale
    attributes, this raises, dispatch() turns it into {"ok": false, ...}, and
    the caller reports it. It must NEVER report success it did not achieve:
    a wrong key silently showing in Live is worse than no key at all, because
    every scale-aware device downstream would then quietly conform to it.

    root_note is 0-11 with C=0, matching Live's own convention.
    """
    root_note = int(msg["root_note"])
    if not (0 <= root_note <= 11):
        raise ValueError(f"root_note {root_note} out of range 0..11 (C=0)")
    scale_name = str(msg["scale_name"])

    song = state.song
    missing = [a for a in SCALE_ATTRS if not hasattr(song, a)]
    if missing:
        raise RuntimeError(
            "this Live's Song object does not expose %s, so the key was NOT "
            "set -- the imported notes and the tempo are unaffected"
            % ", ".join(missing))

    song.root_note = root_note
    song.scale_name = scale_name
    return {"root_note": song.root_note, "scale_name": song.scale_name}


def _ping(state, msg):
    return {"pong": True, "n_tracks": len(state.song.tracks), "n_scenes": len(state.song.scenes)}


# --------------------------------------------------------------- the table
HANDLERS = {
    "PING":              _ping,
    "PLAY":              _play,
    "STOP":              _stop,
    "RECORD_TOGGLE":     _record_toggle,
    "STOP_ALL_CLIPS":    _stop_all_clips,
    "SET_TEMPO":         _set_tempo,
    "TEMPO_NUDGE_UP":    lambda s, m: _tempo_nudge(s, m, "up"),
    "TEMPO_NUDGE_DOWN":  lambda s, m: _tempo_nudge(s, m, "down"),

    "BASS_VOL":          lambda s, m: _stem_vol(s, m, "BASS"),
    "BASS_MUTE_TOGGLE":  lambda s, m: _stem_mute_toggle(s, m, "BASS"),
    "LEAD_VOL":          lambda s, m: _stem_vol(s, m, "LEAD"),
    "LEAD_MUTE_TOGGLE":  lambda s, m: _stem_mute_toggle(s, m, "LEAD"),
    "DRUMS_VOL":         lambda s, m: _stem_vol(s, m, "DRUMS"),
    "DRUMS_MUTE_TOGGLE": lambda s, m: _stem_mute_toggle(s, m, "DRUMS"),
    "FX_VOL":            lambda s, m: _stem_vol(s, m, "FX"),
    "FX_MUTE_TOGGLE":    lambda s, m: _stem_mute_toggle(s, m, "FX"),
    "MASTER_VOL":        lambda s, m: _stem_vol(s, m, "MASTER"),

    "SECTION_INTRO":     lambda s, m: _section(s, m, "INTRO"),
    "SECTION_BUILD":     lambda s, m: _section(s, m, "BUILD"),
    "SECTION_DROP":      lambda s, m: _section(s, m, "DROP"),
    "SECTION_BREAK":     lambda s, m: _section(s, m, "BREAK"),
    "SECTION_OUTRO":     lambda s, m: _section(s, m, "OUTRO"),
    "EXTEND_SECTION":    _extend_section,

    "CREATE_MIDI_TRACK": _create_midi_track,
    "WRITE_NOTES":       _write_notes,

    # JSON-only commands -- deliberately absent from protocol.py, which is the
    # shared contract with the Mixcraft controller script and cannot express a
    # float or a string. See each handler's docstring. test_dispatch.py's
    # test_all_protocol_commands_have_handlers checks protocol -> handler, so
    # extra handlers here are correct, not drift.
    "SET_TEMPO_EXACT":   _set_tempo_exact,
    "SET_SONG_SCALE":    _set_song_scale,
}


def dispatch(state: DispatchState, msg: dict) -> dict:
    """The one function server.py calls per received line. Never raises --
    converts any handler exception into an {"ok": false, ...} reply."""
    cmd = msg.get("cmd") if isinstance(msg, dict) else None
    if not cmd:
        return {"ok": False, "error": "missing 'cmd' field"}
    handler = HANDLERS.get(cmd)
    if handler is None:
        return {"ok": False, "cmd": cmd, "error": f"unknown command {cmd!r}"}
    try:
        result = handler(state, msg)
        state.log(f"OK   cmd={cmd} msg={msg} result={result}")
        return {"ok": True, "cmd": cmd, "result": result}
    except Exception as e:
        state.log(f"FAIL cmd={cmd} msg={msg} error={e!r}")
        return {"ok": False, "cmd": cmd, "error": repr(e)}
