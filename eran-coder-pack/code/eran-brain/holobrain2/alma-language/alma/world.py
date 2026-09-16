"""ALMA as game state — the layer that makes the weave an engine, not a program.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

Godot models a game as a **tree**: parent, child, child. That is right for
drawing and wrong for relationships — two siblings who need to affect each other
must be wired by hand through signals, and a quest that depends on who trusts
whom has nowhere to live except script.

ALMA already models a **graph**, and the graph it models is exactly the one a
game needs:

    a knot is a thing        — a person, a component, a place, a lock
    a strand's WEIGHT is a relation   — how much A trusts B; whether a wire conducts
    a strand's DELAY is distance      — news travels, current does not arrive first
    a knot's TRIGGER is a threshold   — he speaks only if enough reaches him

This module adds no new physics. It is a naming layer over `alma.loom`, and its
whole claim is one line long:

    **a gang of children and a broken radio are the same object.**

`tests/test_world.py` proves that literally — the gossip test and the circuit
test call the same three methods and differ only in what the numbers are called.
"""

from __future__ import annotations

from .loom import Loom, Strand, Weave, WeaveError

__all__ = ["World"]


class World:
    """A weave held as living game state: things, bonds, and one question.

    A `World` is mutable where a `Weave` is not — bonds change while the game
    runs, because that is what a relationship is. Every query builds a clean
    run: seeds are replaced, never accumulated, so asking twice asks twice
    rather than asking louder.
    """

    def __init__(self, name: str = "world") -> None:
        self.weave = Weave(name)
        self._bonds: dict[tuple[str, str], Strand] = {}

    # ---------------------------------------------------------------- things

    def thing(self, name: str, *, listens: float = 0.5,
              bias: float = 0.0) -> "World":
        """A person, a component, a place — anything that can pass something on.

        `listens` is the threshold: how much has to reach it before it acts.
        A trusting child has a low one; a suspicious one has a high one; a lamp
        has whatever the bulb needs.
        """
        self.weave.knot(name, verb="sum", trigger="rise %g" % listens, bias=bias)
        return self

    def ear(self, name: str) -> "World":
        """Something you can read afterwards — a lamp, a rumour heard, a witness.

        Fringe knots have no outgoing voice (loom.validate enforces it), which
        is exactly right: an outcome is where the graph stops, not a relay.
        """
        self.weave.knot(name, verb="fringe", trigger="any")
        return self

    # ----------------------------------------------------------------- bonds

    def bond(self, a: str, b: str, weight: float = 1.0,
             delay: int = 1) -> "World":
        """Tie A to B with a strength. Trust, a wire, a debt, a suspicion.

        The same call in both worlds. `weight` 0 is a bond that exists and
        carries nothing — a cut wire, a friendship that has gone cold — which
        is a different thing from no bond at all, and the graph keeps that
        difference.
        """
        if (a, b) in self._bonds:
            raise WeaveError("bond %s->%s already tied; use set_bond" % (a, b))
        s = Strand(weight=float(weight), delay=int(delay))
        self.weave.thread(a, b, strands=[s])
        self._bonds[(a, b)] = s
        return self

    def set_bond(self, a: str, b: str, weight: float) -> "World":
        """Move a relation. Trust earned, a wire repaired, a wire cut."""
        self._bonds[(a, b)].weight = float(weight)
        return self

    def nudge(self, a: str, b: str, delta: float) -> "World":
        """What actually happens in play: a relation moves by a little."""
        return self.set_bond(a, b, self.bond_of(a, b) + delta)

    def bond_of(self, a: str, b: str) -> float:
        return self._bonds[(a, b)].weight

    # ------------------------------------------------------------- the question

    def tell(self, who: str, strength: float = 1.0,
             beats: int = 8) -> dict[str, list[float]]:
        """Push something into `who` and report what came out at every ear.

        Say a secret to a child, or close a switch on a battery. It is one
        method because it is one mechanism.
        """
        self.weave.seeds = []
        self.weave.seed(who, float(strength), beat=1)
        self.weave.validate()
        result = Loom().run(self.weave, beats)
        return {name: result.fringe(name)
                for name, k in self.weave.knots.items() if k.verb == "fringe"}

    def heard(self, who: str, strength: float = 1.0,
              beats: int = 8) -> list[str]:
        """The ears that lit up at all — the readable half of `tell`."""
        return [n for n, vs in self.tell(who, strength, beats).items() if vs]
