# -*- coding: utf-8 -*-
r"""DJ_ALMIDO -- Ableton Live 12 Remote Script, the ARRANGE side of DJ ALMIDO.

עלמה + עידו על הדקים. This is the half of the bridge Mixcraft could not be:
Mixcraft's JS Controller Script API can play live into an armed track but
cannot create a track or write a MIDI note into one (measured, see
D:\CLAUDE\dj-alma\README.md and bridge/protocol.py's header). Ableton's Live
Object Model (LOM) can do both, so this script opens a small TCP/JSON socket
server INSIDE Live and executes the same command vocabulary the Mixcraft
bridge already speaks (bridge/protocol.py, unmodified, imported straight from
its real location -- see protocol_bridge.py) plus two new commands Mixcraft
never had: CREATE_MIDI_TRACK and WRITE_NOTES.

INSTALLATION: see ../INSTALL.md. In short -- copy this whole DJ_ALMIDO/
folder into
    C:\Users\<user>\Documents\Ableton\User Library\Remote Scripts\DJ_ALMIDO\
then Live -> Preferences -> Link/MIDI -> Control Surface -> DJ_ALMIDO.

API SURFACE, confirmed against this exact installed version (Live 12.4.5
Trial, embedded Python 3.11) 2026-09-08 by fetching the real, current,
Live-12-compatible source of two independently maintained remote scripts --
NOT guessed:
  - gluon/AbletonLive12_MIDIRemoteScripts (decompiled mirror of Ableton's own
    12.4-era ableton/v2/control_surface/control_surface.py) -- confirms
    `self.song` is a @property (`return self._c_instance.song()`), and
    `schedule_message(self, delay_in_ticks, callback, parameter=None)` is
    the real non-blocking scheduler method on ControlSurface (re-arms itself
    by calling schedule_message again from inside the callback -- there is
    no "update_display" hook used for this in current Live; that was an
    older/other-framework pattern and this script does NOT use it).
  - ideoforms/AbletonOSC (a real, currently-maintained Live 11/12 remote
    script that opens a socket server inside Live's own process and polls it
    every tick -- the direct prior art for what this package does, just UDP+
    OSC there where this is TCP+JSON). Its manager.py is the template this
    package's manager.py follows: `class Manager(ControlSurface)`,
    `self.schedule_message(0, self.tick)` in __init__, `tick()` processes the
    socket then re-arms itself with `self.schedule_message(1, self.tick)`.
    Its song.py / clip.py confirmed the exact LOM calls this package needs:
    `self.song.create_midi_track(index)`, `track.clip_slots[i].create_clip(
    length)`, `Live.Clip.MidiNoteSpecification(start_time=, duration=,
    pitch=, velocity=, mute=)`, `clip.add_new_notes(tuple(notes))`.
"""
def create_instance(c_instance):
    """The one entry point Live calls when this Control Surface is enabled
    in Preferences -> Link/MIDI. Must return an object whose class ultimately
    derives from ControlSurface -- see manager.py.

    The import of manager.py (and, through it, `ableton.v2.control_surface`
    and `Live`, both of which exist ONLY inside Live's own embedded
    interpreter) is deliberately done HERE, inside the function, not at
    module scope. That keeps `import DJ_ALMIDO`, `import DJ_ALMIDO.dispatch`,
    `import DJ_ALMIDO.server` etc. safe to do from a normal host Python (no
    Live, no `ableton` package) -- which is exactly what ../tests/ needs to
    do to unit-test dispatch.py and server.py without Ableton running."""
    from .manager import Manager
    return Manager(c_instance)
