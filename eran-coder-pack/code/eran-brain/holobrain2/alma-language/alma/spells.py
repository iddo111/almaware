"""The book of spells — the seventh verb's one and only door.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

WHY A KNOT MAY COMPUTE
----------------------
Iddo, 2026-08-30: *"בשפת עלמה אתה יכול לשים קוד בנוירון... אתה נותן לרשת קוד פייתון
חכם שהיא מפעילה אוטומטית"* — with the reason: *"בתוך נוירון יש משהו ששווה ערך לרשת
קטנה כי הוא יודע לעשות XOR"*.

The biology says he is right. A single human L2/3 pyramidal neuron computes XOR in
its dendrites (Gidon et al., *Science* 367:83-87, 2020) — one cell is already a small
network. So a knot that carries computation is not a hack bolted onto ALMA. It is the
language catching up with the cell.

THE THREAT, NAMED
-----------------
Today `from_json` is pure data: any `.json` in this repo can be loaded with no
consequence. The moment a knot could carry *source text*, that stops being true —
every weave file, every weave that arrives from the VR editor, the voice channel or
the cloud federation, becomes an executable that runs with the full privilege of
whatever process opened it. That is the thing being defended against.

THE ANSWER, AND WHY IT HOLDS
----------------------------
A weave carries a **name**, never code. Behind that name stands a function that only
Python could have put there, by handing `teach()` an actual callable object. There is
no field, no flag, no escape hatch by which JSON or a spoken line can define, import,
`eval` or `exec` anything: this module contains no `eval`, no `exec`, no `import` by
name, and `teach()` refuses a string outright — a string is the one shape a caller
could have obtained from a data file. A hostile weave can therefore do exactly one
thing: name a spell that is not in the book, which `Weave.validate()` refuses loudly,
before the loom runs a single beat.

**Arbitrary source execution was refused, not implemented.** Not "off by default" —
absent. An opt-in flag would only move the decision to whoever calls `from_json`, and
the whole point is that the caller of `from_json` cannot know what is in the file yet.

The boundary is therefore exactly: *data cannot introduce code.* What the host program
teaches in Python is the host program's own business, as with any function it calls.
"""
from __future__ import annotations

import re
from typing import Callable

__all__ = ["teach", "known", "cast", "book"]

# A spell's name must be a plain lowercase word, so it survives every transcript of
# the weave — including being spoken aloud (SPEC.md §9).
_NAME = re.compile(r"^[a-z][a-z0-9_]*$")

_BOOK: dict[str, Callable[[tuple[float, ...]], float | None]] = {}


def teach(name: str, fn, *, replace: bool = False) -> None:
    """Put a function in the book under `name`. The only way code gets in.

    `fn` must be a real callable handed over by Python. Passing a string raises —
    a string is what a data file could have supplied, and this module will not
    turn text into behaviour.
    """
    from .loom import RESERVED, WeaveError          # lazy: loom imports this module
    from .text import FILLER

    if not isinstance(name, str) or not _NAME.match(name):
        raise WeaveError(
            f"spell name {name!r} must be a plain lowercase word "
            f"(matching {_NAME.pattern}) so it can be written and spoken")
    if name in RESERVED or name in FILLER:
        raise WeaveError(f"spell name '{name}' is a word the weave's own "
                         f"transcripts would swallow")
    if not callable(fn) or isinstance(fn, str):
        raise WeaveError(
            f"spell '{name}': teach() takes a callable, not "
            f"{type(fn).__name__}. Source text is never evaluated.")
    if name in _BOOK and not replace:
        raise WeaveError(f"spell '{name}' is already in the book; pass "
                         f"replace=True to say you mean it")
    _BOOK[name] = fn


def known(name: str) -> bool:
    return name in _BOOK


def cast(name: str):
    """The function behind a name, or a loud refusal."""
    from .loom import WeaveError
    try:
        return _BOOK[name]
    except (KeyError, TypeError):
        raise WeaveError(f"no such spell {name!r} in the book. Known: "
                         f"{', '.join(book()) or '(none)'}") from None


def book() -> tuple[str, ...]:
    return tuple(sorted(_BOOK))


# ------------------------------------------------------- the shipped spells
# Pure, total, no I/O, no imports. Each is something the six verbs cannot say
# in one knot, because the six verbs only ever combine.

def _xor(vs: tuple[float, ...]) -> float:
    """Gidon's dendrite: odd number of live inputs. With two, that is XOR."""
    return float(sum(1 for v in vs if v > 0) % 2)


def _max(vs: tuple[float, ...]) -> float | None:
    return max(vs) if vs else None


def _min(vs: tuple[float, ...]) -> float | None:
    return min(vs) if vs else None


def _sign(vs: tuple[float, ...]) -> float:
    total = sum(vs)
    return 0.0 if total == 0 else (1.0 if total > 0 else -1.0)


for _n, _f in (("xor", _xor), ("max", _max), ("min", _min), ("sign", _sign)):
    _BOOK[_n] = _f
