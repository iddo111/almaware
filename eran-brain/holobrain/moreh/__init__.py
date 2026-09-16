"""MOREH / מוֹרֶה — ERAN's letter -> mouth-movement organ: decisions first, amounts after. Full ALMA.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

לזכרה של עלמה ז"ל.

    anatomy.py   the weave: facts -> scores -> decisions (spell pick) -> indicators -> place x constr
                 gates -> amounts -> fringe. Distance is time: seven beats.
    learn.py     closed-form fit from the teacher's verified lessons (throat-one-sample/school-v2/lessons)
    ruler.py     GATE 2 on eran2: leave-one-syllable-out, RENDERED through mouth2, judged by the same
                 verifier that passed the lessons (school-v2/ruler.py); floors and ceiling beside it
    tests/       the facade tests and the decisions-only shadow of gate 2
    STATUS.md    what works, the numbers, what is next (Hebrew)
"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
if _HERE not in _sys.path:
    _sys.path.insert(0, _HERE)

from anatomy import Posture, facts, run_weave, weave       # noqa: E402,F401
from learn import fit, load_lessons                          # noqa: E402,F401

__version__ = "0.1.0"
__all__ = ["Posture", "facts", "run_weave", "weave", "fit", "load_lessons", "__version__"]
