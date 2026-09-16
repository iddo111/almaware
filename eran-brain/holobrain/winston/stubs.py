"""STUBS — loudly-fake gaze spells so the PC can test the TOPOLOGY, not the eyes.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

Every function in this file is a STUB. None of them sees, hears or imagines.
They exist so the show -> behold -> hear_back path of the weave can be proven
to fire, in order, on a machine that is not allowed to carry torch. The real
spells live in gaze.py and run only where the frozen checkpoints do (eran3/4).

The fakes are DETERMINISTIC and still honest about being measurements of
*something*: each answers a real, reproducible number computed from the canvas
by plain numpy — just not the number the real organ would give. A stub's
answer must NEVER be quoted as a gist or an ear resemblance. The name of every
fringe they feed stays a recorded observation of a STUB.
"""
from __future__ import annotations

import numpy as np


def stub_gaze(atelier) -> dict:
    """The three fakes, closed over one atelier. STUBS — see module docstring."""

    def propose(vs):
        """STUB propose: does not consult any painter. Leaves the atelier's own
        seeded table exactly as it is and answers how many strokes it holds."""
        return float(atelier.n)

    def behold(vs):
        """STUB behold: not an eye. Answers 1 - 2*mean|canvas - subject|,
        clipped to [-1, 1] — a deterministic canvas-vs-subject agreement
        number that merely OCCUPIES the cosine's seat in the weave."""
        d = float(np.abs(atelier.canvas() - atelier.x).mean())
        return float(np.clip(1.0 - 2.0 * d, -1.0, 1.0))

    def hear_back(vs):
        """STUB hear_back: not an ear. Answers the canvas's mean darkness in
        [0, 1] — deterministic, reproducible, and meaningless as sound."""
        return float(1.0 - atelier.canvas().mean())

    return {"propose": propose, "behold": behold, "hear_back": hear_back}
