# -*- coding: utf-8 -*-
"""fake_live.py -- a minimal fake of the pieces of Ableton's Live Object
Model (LOM) that DJ_ALMIDO/dispatch.py touches, so dispatch.py can be unit
tested with no Ableton process anywhere nearby (this is explicitly what the
task called for: test the protocol-command-to-LiveAPI mapping without a live
Ableton, never fake being inside Live's own process).

Deliberately NOT a general Live mock -- only the surface dispatch.py
actually uses: Song (tracks, scenes, tempo, record_mode, master_track,
create_midi_track, start/stop_playing, stop_all_clips), Track (name, mute,
solo, mixer_device, clip_slots), MixerDevice/VolumeParameter (.value),
ClipSlot (has_clip, create_clip, delete_clip, clip), Clip (add_new_notes),
Scene (fire), and a fake `Live.Clip.MidiNoteSpecification` matching the real
constructor's keyword signature confirmed against ideoforms/AbletonOSC's
clip.py (start_time=, duration=, pitch=, velocity=, mute=) -- see
DJ_ALMIDO/__init__.py's docstring for how that was verified against real,
current, Live-12-compatible source rather than guessed.
"""


class FakeVolumeParameter:
    def __init__(self, value=0.85):
        self.value = value


class FakeMixerDevice:
    def __init__(self):
        self.volume = FakeVolumeParameter()


class FakeClip:
    def __init__(self, length_beats):
        self.length = length_beats
        self.added_notes = []  # list of tuples of note-spec objects, one tuple per add_new_notes call

    def add_new_notes(self, notes):
        self.added_notes.append(tuple(notes))


class FakeClipSlot:
    def __init__(self):
        self.has_clip = False
        self.clip = None
        self.calls = []

    def create_clip(self, length_beats):
        self.calls.append(("create_clip", length_beats))
        self.clip = FakeClip(length_beats)
        self.has_clip = True

    def delete_clip(self):
        self.calls.append(("delete_clip",))
        self.clip = None
        self.has_clip = False


class FakeTrack:
    def __init__(self, name="", n_clip_slots=8):
        self.name = name
        self.mute = False
        self.solo = False
        self.mixer_device = FakeMixerDevice()
        self.clip_slots = [FakeClipSlot() for _ in range(n_clip_slots)]


class FakeScene:
    def __init__(self, name=""):
        self.name = name
        self.fired = 0

    def fire(self):
        self.fired += 1


class FakeSong:
    """supports_scale mirrors the real uncertainty: root_note/scale_name exist
    in Live 12.4.5's LOM type table but nothing on disk says the Song owns
    them, and they moved between Live versions. Default False so the
    NOT-supported branch is the one exercised unless a test asks otherwise."""

    def __init__(self, n_tracks=4, n_scenes=5, supports_scale=False):
        if supports_scale:
            self.root_note = 0
            self.scale_name = "Major"
        self.tracks = [FakeTrack(name=f"Track {i}") for i in range(n_tracks)]
        self.scenes = [FakeScene(name=f"Scene {i}") for i in range(n_scenes)]
        self.master_track = FakeTrack(name="Master")
        self.tempo = 140.0
        self.record_mode = False
        self.is_playing = False
        self.play_calls = 0
        self.stop_calls = 0
        self.stop_all_clips_calls = 0
        self.created_tracks = []  # log of create_midi_track(index) calls, for assertions

    def start_playing(self):
        self.play_calls += 1
        self.is_playing = True

    def stop_playing(self):
        self.stop_calls += 1
        self.is_playing = False

    def stop_all_clips(self):
        self.stop_all_clips_calls += 1

    def create_midi_track(self, index=-1):
        self.created_tracks.append(index)
        new_track = FakeTrack(name="")
        if index is None or index < 0:
            self.tracks.append(new_track)
        else:
            self.tracks.insert(index, new_track)


class FakeMidiNoteSpecification:
    """Matches the real Live.Clip.MidiNoteSpecification(start_time=,
    duration=, pitch=, velocity=, mute=) keyword signature."""

    def __init__(self, start_time, duration, pitch, velocity=100, mute=0):
        self.start_time = start_time
        self.duration = duration
        self.pitch = pitch
        self.velocity = velocity
        self.mute = mute

    def __repr__(self):
        return (f"FakeMidiNoteSpecification(pitch={self.pitch}, "
                f"start_time={self.start_time}, duration={self.duration}, "
                f"velocity={self.velocity}, mute={self.mute})")


class _FakeClipNamespace:
    MidiNoteSpecification = FakeMidiNoteSpecification


class FakeLiveModule:
    """Stands in for `import Live` -- only DJ_ALMIDO's own usage
    (Live.Clip.MidiNoteSpecification) is implemented."""
    Clip = _FakeClipNamespace
