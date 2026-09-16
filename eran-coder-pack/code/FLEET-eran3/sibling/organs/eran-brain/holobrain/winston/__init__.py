"""WINSTON — ERAN's imaginer, rewritten as a HOLOBRAIN organ in full ALMA.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

לזכרה של עלמה ז"ל — the language is a memorial and the organ must be worthy
of the name it is written in.

Iddo, 2026-08-31 (verbatim): "אני רוצה שווינסטון יעבור כתיבה מחדש כחלק
מההולובריין של ערן בשפת עלמה מלא."

What "full ALMA" means here, honestly: the painting PROCESS is loom semantics
— stroke waking is a strand weight against `rise theta`, order is delay,
coarse->fine is topology + earned `rise T`, keep/revert is `rise eps` + a
settle spell, lifetime merit is drift transcribed into next sitting's opacity,
pruning is a cord thinning below theta. Gradient-free, all of it. Torch
remains in exactly three frozen forward passes inside taught spells on
eran3/4 (propose / behold / hear_back) plus render_big for 4K; the PC side is
numpy only, pinned to winston.py's numbers by the eran4 equality test.

Standing rule (the facade test): a knot exists only if it accumulates a
measured scalar, makes a fire-or-silence decision, or produces a real
measurement. If deleting it changes no number and no decision, it is not
built.

    from winston import Easel, teach_all
    e = Easel(subject, n_strokes=64, bands=(8, 16, 40))
    e.sitting()          # runs the weave, prints the floor verdict, learns
"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
if _HERE not in _sys.path:
    _sys.path.insert(0, _HERE)

from easel import Easel                    # noqa: E402,F401
from brushes import teach_all              # noqa: E402,F401

__version__ = "0.1.0"
__all__ = ["Easel", "teach_all", "__version__"]
