# -*- coding: utf-8 -*-
"""protocol.py -- the ONE shared contract between the Python bridge and the
Mixcraft controller script (controller/ALMA/dj_alma_control.js).

THERE IS NO WAY TO SHARE CODE between Python and the Mixcraft script sandbox
(measured: the Mixcraft 10 JS API is a fixed ES5-only subset -- no modules,
no import, no require; see docs/getting-started/javascript-limitations.md
mirrored in the smoke test). So this table is hand-duplicated in the .js
file's COMMANDS object. smoke_test.py parses both and diffs them so drift
is caught mechanically, not by hoping two files stay in sync by memory.

WIRE FORMAT (our own design -- nothing in the Mixcraft docs prescribes one):
  Every DJ command is one MIDI NOTE_ON immediately followed by NOTE_OFF, on
  a single reserved channel, so it looks like a normal control-surface key
  press to anything else listening on the port:
    note (value1)     = command id, 1-127 (this table)
    velocity (value2)  = one parameter byte, 0-127 (meaning depends on command)
    channel            = CHANNEL (see below)
  A single NOTE_ON/OFF pair carries exactly one number. Commands that
  conceptually need two numbers (e.g. "track X to level Y") are avoided in
  v1 by giving each named stem (bass/lead/drums/fx) its own command id
  instead of a generic (track_index, value) pair -- simpler, and matches
  how Iddo actually talks to it ("the BASS", not "track 3").

CHANNEL NOTE (measured API inconsistency, see MIXCRAFT-API-MAP.md):
  MIDI.md documents OnMIDI's midiChannel as 0x0-0xF (0-based, so channel 16
  is 0xF/15) but documents SendMIDI's chan parameter as 1-16 (1-based). Both
  names refer to the SAME physical MIDI channel 16 -- this file uses the
  0-based OnMIDI convention (CHANNEL = 0xF) since that is what the script's
  OnMIDI() switch checks against.
"""

CHANNEL = 0x0F  # MIDI channel 16, 0-based (OnMIDI convention) -- reserved for ALMA DJ commands only

# ---- BPM mapping for SET_TEMPO -------------------------------------------
# value2 (0-127) maps LINEARLY onto this BPM span. Psytrance sits 130-150;
# padded to 120-160 so slow builds and fast peak-time both fit.
TEMPO_MIN_BPM = 120.0
TEMPO_MAX_BPM = 160.0


def bpm_to_param(bpm: float) -> int:
    bpm = max(TEMPO_MIN_BPM, min(TEMPO_MAX_BPM, bpm))
    frac = (bpm - TEMPO_MIN_BPM) / (TEMPO_MAX_BPM - TEMPO_MIN_BPM)
    return round(frac * 127)


def param_to_bpm(param: int) -> float:
    frac = max(0, min(127, param)) / 127.0
    return TEMPO_MIN_BPM + frac * (TEMPO_MAX_BPM - TEMPO_MIN_BPM)


# ---- nudge encoding for *_VOL commands -------------------------------------
# Voice commands like "lower the bass" carry no target level, only a
# direction -- and reading a value back from Mixcraft to compute a proper
# relative-from-current move would need a second round trip (Notify() ->
# python) that v1 does not build (see status report, "what v1 does not do").
# So *_VOL is a NUDGE, not an absolute set: param 64 = no-op, below 64 = move
# volume DOWN, above 64 = move volume UP, and the distance from 64 sets the
# step size. The .js script must compute the exact same formula -- mirrored
# by hand in dj_alma_control.js, see NUDGE_UNIT_FRACTION there.
NUDGE_UNIT_FRACTION = 0.08  # fraction of full 0..1.0 track volume per unit of |param-64| / 16


def nudge_param(direction: str, steps: int = 1) -> int:
    """direction: 'up' or 'down'. steps: how many default-size nudges (1 for
    a single "תוריד את הבס", more if a caller wants a bigger jump)."""
    delta = 16 * max(1, steps)
    if direction == "down":
        return max(0, 64 - delta)
    if direction == "up":
        return min(127, 64 + delta)
    raise ValueError(f"direction must be 'up' or 'down', got {direction!r}")


# ---- command table ---------------------------------------------------------
# id : (NAME, param meaning)
# Kept 1-127 (0 is not a usable MIDI note-safe sentinel in some hosts).
COMMANDS = {
    1:  ("PLAY",              "none"),
    2:  ("STOP",              "none"),
    3:  ("RECORD_TOGGLE",     "none"),
    4:  ("SET_TEMPO",         "0-127 -> BPM 120-160 linear, see bpm_to_param()"),
    5:  ("TEMPO_NUDGE_UP",    "0-127 -> number of 0.5 BPM steps (param, not scaled)"),
    6:  ("TEMPO_NUDGE_DOWN",  "0-127 -> number of 0.5 BPM steps (param, not scaled)"),

    10: ("BASS_VOL",          "NUDGE: 64=no-op, <64 down, >64 up -- see nudge_param()"),
    11: ("BASS_MUTE_TOGGLE",  "none"),
    12: ("LEAD_VOL",          "NUDGE: 64=no-op, <64 down, >64 up -- see nudge_param()"),
    13: ("LEAD_MUTE_TOGGLE",  "none"),
    14: ("DRUMS_VOL",         "NUDGE: 64=no-op, <64 down, >64 up -- see nudge_param()"),
    15: ("DRUMS_MUTE_TOGGLE", "none"),
    16: ("FX_VOL",            "NUDGE: 64=no-op, <64 down, >64 up -- see nudge_param()"),
    17: ("FX_MUTE_TOGGLE",    "none"),
    18: ("MASTER_VOL",        "NUDGE: 64=no-op, <64 down, >64 up -- see nudge_param()"),

    20: ("SECTION_INTRO",     "none -- Perform.TriggerSet(col) for the intro column"),
    21: ("SECTION_BUILD",     "none -- Perform.TriggerSet(col) for the build/riser column"),
    22: ("SECTION_DROP",      "none -- Perform.TriggerSet(col) for the drop column"),
    23: ("SECTION_BREAK",     "none -- Perform.TriggerSet(col) for the breakdown column"),
    24: ("SECTION_OUTRO",     "none -- Perform.TriggerSet(col) for the outro column"),
    25: ("EXTEND_SECTION",    "bars: 0=8, 1=16, 2=32 -- re-triggers the current column"),
    26: ("STOP_ALL_CLIPS",    "none -- Perform.StopAll()"),
}

# Which named stem (BASS/LEAD/DRUMS/FX) maps to which Mixcraft track index.
# THESE ARE PLACEHOLDERS (0,1,2,3) -- Iddo's real project layout is unknown
# because Mixcraft is not installed/running on this machine (see the status
# report). Edit this table to match the real track order before first use;
# the .js file has the identical table under the same name, edit both.
STEM_TRACK_INDEX = {
    "BASS":  0,
    "LEAD":  1,
    "DRUMS": 2,
    "FX":    3,
}

# Which Performance-grid COLUMN (Perform.TriggerSet(col)) holds which
# arrangement section. Also a PLACEHOLDER for the same reason as above --
# Iddo lays out his own Performance grid; this must be edited to match it.
SECTION_COLUMN = {
    "INTRO": 0,
    "BUILD": 1,
    "DROP":  2,
    "BREAK": 3,
    "OUTRO": 4,
}


def command_id_by_name(name: str) -> int:
    for cid, (cname, _) in COMMANDS.items():
        if cname == name:
            return cid
    raise KeyError(f"no such command: {name!r}")
