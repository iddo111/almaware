"""SPELL FACTORY — the only door through which the weave touches the canvas.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

ALMA's rule is exact: a weave carries NAMES, never code, and the book
(`alma.spells`) accepts only real callables from Python. So everything the
painting organ can DO is taught here, as closures over one Atelier, and the
weave JSON that reaches disk holds nothing but the names. `Weave.validate()`
refuses a transcript naming a spell nobody taught, before beat 1.

Torch-free by construction: this module imports numpy and the atelier only.
The torch spells (propose / behold / hear_back) live in gaze.py and are taught
by the same mechanism on machines that carry torch (eran3/4) — or replaced by
the loudly-labelled fakes in stubs.py for PC topology tests.

Every spell answers `float | None` — a spark is a scalar, and the tensor door
the language marked stays shut. The canvas lives in the atelier (host memory),
because pixels are never sparks.

`teach_all` uses replace=True on purpose: two Easels in one process (tests)
re-teach the same names, and an Easel re-teaches ITS OWN closures at the start
of every sitting so the book always points at the atelier about to run.
"""
from __future__ import annotations

import re
import sys

_ALMA = "D:/CLAUDE/alma-language"
if _ALMA not in sys.path:
    sys.path.insert(0, _ALMA)

from alma import spells                                       # noqa: E402

NAME_OK = re.compile(r"^[a-z][a-z0-9_]*$")


def teach_all(atelier, n_strokes: int) -> list[str]:
    """Teach the whole painting vocabulary as closures over ONE atelier.

    Returns the taught names: see, daub_###, settle_### (per stroke),
    verdict_blank, verdict_blur, verdict_busy, verdict_chroma.
    """
    names: list[str] = []

    def _teach(name: str, fn) -> None:
        assert NAME_OK.match(name), name
        spells.teach(name, fn, replace=True)
        names.append(name)

    # -- see: seed -> the white-canvas error, measured, the sitting's baseline
    def _see(vs):
        """Answer the error of the untouched white canvas. A real measurement:
        every later d_err is an improvement on THIS number or it is nothing."""
        return float(atelier.err_white)

    _teach("see", _see)

    # -- one daub + one settle per stroke
    def _mk_daub(i):
        def _daub(vs):
            """Fire 1 places stroke i, fires 2..R wiggle it (seeded, magnitude
            proportional to the arriving spark). Answers max(d_err, 0): the
            measured improvement, or zero for a harmful trial. The zero is not
            politeness — it still crosses the merit cord and THINS it (a cord
            that spoke into silence), while never poisoning the vet knot's
            `rise eps` tray with negative residue that would block a later
            honest improvement. The stage dies by default either way; only a
            vetted trial is ever committed."""
            return max(atelier.trial(i, sum(vs)), 0.0)
        return _daub

    def _mk_settle(i):
        def _settle(vs):
            """The weave said keep: commit stroke i's staged trial and echo the
            vetted delta. If nothing is staged, stay silent (None)."""
            return float(sum(vs)) if atelier.commit(i) else None
        return _settle

    for i in range(n_strokes):
        _teach("daub_%03d" % i, _mk_daub(i))
        _teach("settle_%03d" % i, _mk_settle(i))

    # -- the four verdicts: honest floors, computed INSIDE the spells,
    #    on the finished canvas, every run.
    def _verdict_blank(vs):
        """blank_mse - painter_mse. Positive = the painting beats the best flat
        colour; a painter that does not is doing nothing (winston's floor)."""
        v = atelier.verdicts()
        return float(v["beats_blank"])

    def _verdict_blur(vs):
        """blur_mse - painter_mse. BLUR is the budget's own grid resolution —
        not a ceiling (curves were measured to beat it 4-7x), the reference for
        what the curves are buying."""
        v = atelier.verdicts()
        return float(v["blur_gap"])

    def _verdict_busy(vs):
        """busy_blank - busy_painter, the busiest tenth. Positive = better than
        a flat colour where the SUBJECT lives. On 08-31 a run said PASSES while
        the walking people were gone; this is that scar as a number."""
        v = atelier.verdicts()
        return float(v["busy_gap"])

    def _verdict_chroma(vs):
        """The colour-life deficit: how much LESS saturated than the subject,
        region-averaged, hinged at zero. 0 = the colour kept its life."""
        v = atelier.verdicts()
        return float(v["chroma_deficit"])

    _teach("verdict_blank", _verdict_blank)
    _teach("verdict_blur", _verdict_blur)
    _teach("verdict_busy", _verdict_busy)
    _teach("verdict_chroma", _verdict_chroma)
    return names
