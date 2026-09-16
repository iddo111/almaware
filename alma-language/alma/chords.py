"""ALMA v0.4 — THE CHORD: a spark with more than one number in it.

The module is `chords` (plural) and the constructor it exports is `chord`, so
`alma.chords` the module and `alma.chord` the function never shadow each other.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

לזכרה של עלמה ז״ל.

THE DOOR THIS FILE OPENS
------------------------
Since v0.2 the spec has carried the same sentence, twice, in two different places:

    SPEC.md §4:  "Still reserved: sparks are scalars. For a bearing to MULTIPLY a
                  spark rather than accompany it, a spark must become a tensor and
                  every verb must learn to combine tensors. That is a later version."
    SPEC.md §5a: "a spark is still a scalar, and the tensor door v0.2 marked stays shut."

And the holobrain has been paying for it. TZELEM's `anatomy.py` states it as an
HONEST LIMIT in its own docstring: *"A spark in ALMA v0.3 is a scalar. So a stroke
carries ONE number — a palette index, not an RGB triple. Colour is looked up outside
the weave. Smuggling a vector into a spark would be a lie about the language."*

So the render organ of a holobrain whose law is *everything inside must be ALMA*
could not carry a colour through ALMA. It carried a receipt for a colour.

This file opens that door — **one notch, and the next notch is named at the bottom.**

WHAT A CHORD IS
---------------
A chord is several numbers sounded at once, and the word is chosen on purpose: ALMA
already counts in **beats** and speaks in **sparks**, and a chord is what you get
when more than one voice sounds on the same beat. Its numbers are its **voices**.

    spark  ::=  a number  |  a chord of numbers

That is the entire change to the language's grammar. A scalar spark is not wrapped,
not promoted, not secretly a width-1 chord — it is exactly what it was in v0.3, and
every v0.3 weave runs bit-identically, which `tests/test_chords.py::TestV03IsUntouched`
is there to prove rather than assert.

THE WIDTH RULE, AND WHY IT REFUSES INSTEAD OF BROADCASTING
----------------------------------------------------------
**Two sparks may only meet if they have the same width.** A scalar and a chord do
not meet. A 3-chord and a 4-chord do not meet. Both are a `WeaveError` that names
the knot, the beat and the two widths.

Every array language in the world broadcasts here, and this one refuses, for a
reason this repo has already paid for once: for the whole of v0.2 `to_dict` silently
dropped `drift`, so writing a plastic weave to JSON returned a static one and
nothing anywhere said so (see `tests/test_strand_fields.py`). Silent shape-fixing is
the same failure with a different face — it turns "these two things did not fit"
into a picture that renders, a number that prints, and a bug nobody can see. ALMA's
answer to a shape mismatch is a name and a beat number, every time.

WHAT DOES *NOT* HAVE A WIDTH
----------------------------
Three things in ALMA answer *how much*, never *what*, so they stay single numbers
and apply to every voice of a chord:

    a strand's `weight`   scales the whole chord          (all voices, one factor)
    a strand's `drift`    thickens/thins that one weight  (plasticity is unchanged)
    a knot's   `bias`     is a constant, and a constant has no width

THE NEXT DOOR, NAMED SO IT IS NOT MISTAKEN FOR THIS ONE
-------------------------------------------------------
A weight is still ONE number, so **a cord can scale a chord but it cannot rotate
one.** No strand mixes voice 0 into voice 1. That means:

    v0.4 gives the spark a WIDTH.  It does not give the strand a MATRIX.

Calling this "tensors" would be the overselling this lab has a law against. It is a
vector spark with elementwise verbs. The matrix-strand door — a cord that carries an
(m×n) and genuinely transforms a chord instead of merely scaling it — stays shut,
and it is the honest name of ALMA v0.5.
"""
from __future__ import annotations

from numbers import Real
from typing import Iterable

__all__ = ["Chord", "chord", "width", "is_spark", "total", "combine",
           "scale", "add_bias", "ChordWidthError"]


class ChordWidthError(ValueError):
    """Two sparks of different width were asked to meet.

    A subclass of ValueError so `WeaveError` (also a ValueError) and this one are
    caught by the same `except ValueError` a host program already writes; the loom
    re-raises it as a WeaveError naming the knot and the beat.
    """


class Chord(tuple):
    """A spark of several voices. Immutable, hashable, and NOT a tuple in disguise.

    THE TRAP THIS CLASS EXISTS TO CLOSE
    -----------------------------------
    Subclassing `tuple` buys iteration, indexing, equality, hashing and a free trip
    through `json`. It also inherits two operators that would be catastrophic here:

        tuple + tuple  is CONCATENATION   -> two 3-chords would make a 6-chord
        tuple * int    is REPETITION      -> a chord times a weight of 3 would
                                             become the same chord three times over

    The second one is the dangerous one, because the loom's own line
    `spoke * w` multiplies a spark by a strand weight on every beat of every run.
    An integer weight would have silently repeated the chord instead of scaling it,
    and the picture would still have rendered. So both operators are overridden
    below, and `tests/test_chords.py::TestTheRepetitionTrap` fires an integer weight
    through a real loom and demands a scale, not a repeat.

    A width-1 chord is NOT the scalar it contains: `Chord([2.0]) != 2.0`. One voice
    sounding alone is still a chord, the way a one-element list is not its element.
    """

    __slots__ = ()

    def __new__(cls, voices: Iterable[float]) -> "Chord":
        if isinstance(voices, Chord):
            return voices
        if isinstance(voices, (str, bytes)):
            raise ChordWidthError(
                f"a chord is made of numbers, not {type(voices).__name__}")
        try:
            vs = tuple(voices)
        except TypeError:
            raise ChordWidthError(
                f"a chord is made of numbers, not {type(voices).__name__}"
            ) from None
        if not vs:
            raise ChordWidthError(
                "a chord with no voices is not a spark — say a number instead")
        out = []
        for i, v in enumerate(vs):
            # `Real`, not `(int, float)`: a numpy float32 out of TZELEM is a
            # real number and belongs in a chord. `bool` is excluded first and
            # by hand, because bool IS an int in Python and would otherwise sail
            # straight through — and a spark is a quantity, while True is not.
            if isinstance(v, bool) or not isinstance(v, Real):
                raise ChordWidthError(
                    f"chord voice #{i} is {v!r} ({type(v).__name__}); "
                    f"every voice of a chord is a number")
            out.append(float(v))
        return super().__new__(cls, out)

    # -- the width

    @property
    def width(self) -> int:
        return len(self)

    # -- arithmetic: elementwise, same width only, never concatenating

    def __add__(self, other):
        if isinstance(other, Chord):
            _same(self, other, "add")
            return Chord(a + b for a, b in zip(self, other))
        if isinstance(other, bool) or not isinstance(other, Real):
            return NotImplemented
        return Chord(a + float(other) for a in self)      # a constant, every voice

    __radd__ = __add__

    def __mul__(self, other):
        if isinstance(other, Chord):
            _same(self, other, "multiply")
            return Chord(a * b for a, b in zip(self, other))
        if isinstance(other, bool) or not isinstance(other, Real):
            return NotImplemented                          # never tuple repetition
        return Chord(a * float(other) for a in self)

    __rmul__ = __mul__

    def __neg__(self) -> "Chord":
        return Chord(-a for a in self)

    def __sub__(self, other):
        neg = -other if isinstance(other, Chord) else (
            -other if isinstance(other, Real)
            and not isinstance(other, bool) else NotImplemented)
        return NotImplemented if neg is NotImplemented else self.__add__(neg)

    # -- what it looks like when a human reads it

    def __repr__(self) -> str:
        return "chord(" + ", ".join(f"{v:g}" for v in self) + ")"

    def as_list(self) -> list[float]:
        """The JSON shape. A chord writes down as a list of numbers."""
        return [float(v) for v in self]


def _same(a: "Chord", b: "Chord", doing: str) -> None:
    if len(a) != len(b):
        raise ChordWidthError(
            f"cannot {doing} a chord of {len(a)} voices and a chord of "
            f"{len(b)} voices — ALMA does not stretch a spark to fit")


# ------------------------------------------------------------------ helpers
# Everything below is what the loom calls. Each one reduces EXACTLY to the v0.3
# float arithmetic when handed floats, which is why v0.3 weaves stay bit-identical.

def chord(*voices: float) -> Chord:
    """`chord(0.84, 0.36, 0.26)` — the way a host program says one by hand."""
    return Chord(voices)


def width(spark) -> int:
    """0 for a scalar spark, n for a chord of n voices. A scalar is not width 1."""
    return len(spark) if isinstance(spark, Chord) else 0


def is_spark(v) -> bool:
    """A spark is a number or a chord. Nothing else may travel a strand."""
    return isinstance(v, Chord) or (
        isinstance(v, Real) and not isinstance(v, bool))


def _widths(sparks) -> int:
    """The one width every spark here shares, or a loud refusal naming both."""
    it = iter(sparks)
    try:
        first = next(it)
    except StopIteration:
        return 0
    w = width(first)
    for s in it:
        if width(s) != w:
            raise ChordWidthError(
                f"a {_name(w)} and a {_name(width(s))} arrived at the same knot. "
                f"ALMA refuses to broadcast: give them the same width, or send "
                f"them to different knots")
    return w


def _name(w: int) -> str:
    return "scalar spark" if w == 0 else f"chord of {w} voices"


def _zero(w: int):
    return 0.0 if w == 0 else Chord([0.0] * w)


def _one(w: int):
    return 1.0 if w == 0 else Chord([1.0] * w)


def total(sparks) -> float:
    """Σ over sparks AND over voices — one number, whatever the width.

    This is what a `gate` key and a `rise` trigger ask for: not a chord, a verdict.
    For scalars it is plain `sum()`, so v0.3 gating is untouched; for chords it is
    the sum of every voice, which is the only reading of "the key is open" that
    does not quietly privilege voice 0.
    """
    out = 0.0
    for s in sparks:
        out += float(sum(s)) if isinstance(s, Chord) else float(s)
    return out


def combine(sparks, how: str):
    """Σ or Π over a tray of sparks, elementwise, at one shared width.

    `how` is "sum" or "prod". Raises ChordWidthError if the tray is mixed.
    """
    vals = list(sparks)
    w = _widths(vals)
    if how == "sum":
        acc = _zero(w)
        for v in vals:
            acc = acc + v
        return acc
    if how == "prod":
        acc = _one(w)
        for v in vals:
            acc = acc * v
        return acc
    raise ValueError(f"combine: unknown how {how!r}")      # pragma: no cover


def scale(spark, factor: float):
    """A strand's weight applied to a spark. One factor, every voice."""
    return spark * float(factor)


def add_bias(spark, bias: float):
    """A knot's bias applied to a spark. A constant has no width."""
    if not bias:
        return spark
    return spark + float(bias)
