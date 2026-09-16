"""ALMA Language v0.3 — a weave of knots. ALMAWARE, 100% ours."""
from .loom import (Knot, Loom, Result, Seed, Strand, Thread, Weave,
                   WeaveError, MIN_DELAY, VERBS)
from .text import from_dict, from_json, parse_voice, to_dict, to_json, to_voice
from . import spells

__version__ = "0.3.0"
__all__ = [
    "Weave", "Loom", "Result", "Knot", "Thread", "Strand", "Seed",
    "WeaveError", "MIN_DELAY", "VERBS",
    "to_dict", "from_dict", "to_json", "from_json",
    "parse_voice", "to_voice", "spells",
]
