"""ALMA Language v0.4 — a weave of knots. ALMAWARE, 100% ours.

v0.4 THE CHORD: a spark may be several numbers sounded on one beat. See
`alma/chords.py` — it opens the door SPEC.md §4 and §5a marked reserved, and
names the one it deliberately leaves shut.
"""
from .chords import Chord, ChordWidthError, chord
from .loom import (Knot, Loom, Result, Seed, Strand, Thread, Weave,
                   WeaveError, MIN_DELAY, VERBS)
from .text import from_dict, from_json, parse_voice, to_dict, to_json, to_voice
from . import spells

__version__ = "0.4.0"
__all__ = [
    "Weave", "Loom", "Result", "Knot", "Thread", "Strand", "Seed",
    "WeaveError", "MIN_DELAY", "VERBS",
    "Chord", "chord", "ChordWidthError",
    "to_dict", "from_dict", "to_json", "from_json",
    "parse_voice", "to_voice", "spells",
]
