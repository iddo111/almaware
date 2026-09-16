# -*- coding: utf-8 -*-
"""score_bridge.py -- converts a booth/compose.py Score (the Darwish model's
own composition -- see compose.py's docstring for exactly what it does and,
as importantly, does NOT do: it does not compose, harmonize, or invent
anything the model didn't write) into the note-spec list DJ_ALMIDO's
WRITE_NOTES command expects: {"pitch", "start_time", "duration", "velocity",
"mute"} dicts, times in BEATS (Live's clip-editing unit) rather than the
model's own 16th-note "step" grid.

Does NOT reimplement composition, tokenization, or voice/role assignment --
all of that stays in booth/compose.py (imported here unmodified, which in
turn imports darwish-ai/poly_tok.py for STEPS_PER_BAR and the Note/Score
dataclasses). This file's only job is the grid -> beats conversion and the
dict shape WRITE_NOTES needs.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOOTH_DIR = os.path.join(os.path.dirname(HERE), "booth")  # D:\CLAUDE\dj-alma\booth
if BOOTH_DIR not in sys.path:
    sys.path.insert(0, BOOTH_DIR)

import compose  # booth/compose.py, unmodified -- pulls in poly_tok (STEPS_PER_BAR) itself

# Mirrors compose.write_midi's own per-role velocities exactly (not
# re-derived) -- see compose.py's "VOICE SEPARATION" section for why
# lead/bass/pad exist and what problem they fix.
ROLE_VELOCITY = {"lead": 100, "bass": 104, "pad": 78}


def steps_per_beat() -> float:
    """poly_tok.STEPS_PER_BAR (16, one sixteenth-note grid step) / 4 beats
    per bar -- 4/4 time, the same assumption compose.py/psy_render_v2 make
    throughout (there is no time-signature field on PT.Score to read
    instead)."""
    return compose.PT.STEPS_PER_BAR / 4.0


def score_to_notes(sc, assign_roles: bool = True) -> list:
    """sc: a compose.PT.Score, e.g. the first element of compose.compose().
    Returns a list of note-spec dicts ready for DJ_ALMIDO's WRITE_NOTES
    command. Notes whose MIDI pitch falls outside 0..127 are DROPPED, not
    clamped -- clamping would silently transpose a note the model never
    played at that register."""
    spb = steps_per_beat()
    roles = compose.split_roles(sc) if assign_roles else ["lead"] * len(sc.notes)

    notes = []
    for n, role in zip(sc.notes, roles):
        pitch = int(n.midi)
        if not (0 <= pitch <= 127):
            continue
        dur_steps = max(1, int(n.dur))  # a zero/negative dur would be a silent, inaudible "note"
        notes.append({
            "pitch": pitch,
            "start_time": n.step / spb,
            "duration": dur_steps / spb,
            "velocity": ROLE_VELOCITY.get(role, 100),
            "mute": 0,
        })
    return notes


def score_length_beats(sc) -> float:
    return sc.n_steps / steps_per_beat()
