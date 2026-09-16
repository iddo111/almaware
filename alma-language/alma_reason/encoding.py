# -*- coding: utf-8 -*-
"""AN ARGUMENT -> SPARKS. What the two seats are handed before they speak.

ALMA has five words — knot, thread, strand, spark, beat — and an argument is
none of them. Something has to decide how a claim becomes a number, and that
decision is this file. It is the designed part of ALMA-REASON, so it is the
part that has to be argued for rather than assumed.

THE RULE: PRESENCE, NOT MAGNITUDE
---------------------------------
One knot per feature, seeded 1.0 when the feature is there, **not seeded at
all** when it is not. That is forced by the loom, not chosen. `alma/loom.py`
step 3 reads:

    term = st.drift if dst in fired_now else -st.drift * 0.25

The eligibility a cord earns does not depend on how big its spark was. A cord
carrying 0.01 and a cord carrying 9.0 earn the same. So if every feature knot
fired on every item — carrying its value, zero included — every cord would be
eligible on every item and the verdict could not tell one feature from
another. In ALMA, credit is carried by **which knots stayed silent**. A
feature must therefore be able to say nothing.

(The same conclusion was reached independently in `alma_guard/encoding.py` for
the security organ, from the same three lines of the loom. It is a property of
the substrate, which is why both organs of the holobrain obey it. Nothing is
imported across; these are two readings of one runtime.)

AND THE COROLLARY THAT IS NOT OBVIOUS: ONE-HOT THE BOOLEANS
-----------------------------------------------------------
Presence-only is right when absence means *nothing was there* — no such
n-gram, no such word. It is WRONG when absence means *the other value*.
"The major premise is not negative" is a fact about the premise, and it
deserves its own cord; encoded as the mere absence of `neg_maj` it can never
earn one, because a silent knot never makes a cord eligible.

So every binary fact is encoded as a **pair of mutually exclusive presence
features** — `neg_maj` / `pos_maj` — of which exactly one is always seeded.
Absence in this file therefore always means *not applicable*, never *false*.

WHAT IS DELIBERATELY NOT A FEATURE
----------------------------------
For syllogisms: no rule, no fault name, no validity hint. Only what a reader
sees on the page — the shape of each proposition, the figure, and (in the
`distrib` set) which terms are distributed. The classical rules are
conjunctions and one biconditional OVER those facts; assembling them is the
whole of what is left to learn. See `syllogism.py`.

For machloket: `psak_rule` is NEVER a feature. It names the answer.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .machloket import Machloket
from .syllogism import Syllogism

# ---------------------------------------------------------------- the item

SEAT_M = "M"      # מתרץ — the seat holding that the position stands
SEAT_Q = "Q"      # מקשן — the seat holding that there is a פירכא


@dataclass
class Argument:
    """One dialectical item: what both seats are handed, and who is left standing."""
    id: str
    features: frozenset[str]
    winner: str                      # SEAT_M or SEAT_Q
    seat_m: str = "מתרץ"             # who sits on M, for display
    seat_q: str = "מקשן"
    text: str = ""
    source: str = ""
    meta: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        return {
            "id": self.id,
            "features": sorted(self.features),
            "winner": self.winner,
            "seat_m": self.seat_m,
            "seat_q": self.seat_q,
            "text": self.text,
            "source": self.source,
            "meta": self.meta,
        }

    @staticmethod
    def from_json(d: dict) -> "Argument":
        return Argument(
            id=d["id"], features=frozenset(d["features"]), winner=d["winner"],
            seat_m=d.get("seat_m", "מתרץ"), seat_q=d.get("seat_q", "מקשן"),
            text=d.get("text", ""), source=d.get("source", ""),
            meta=d.get("meta", {}),
        )


# ------------------------------------------------------- syllogism features

FEATURE_SETS = ("raw", "distrib")


def syllogism_features(s: Syllogism, feature_set: str = "raw") -> frozenset[str]:
    """What a reader sees. Never what the rules say.

    `raw`     16 features — the shape of the three propositions and the figure.
              Nothing else. This asks whether the weave can DISCOVER the rules.
    `distrib` 40 features — the same 16 plus the 12 structural facts of
              `Syllogism.facts()`, each one-hot into its two directions. This
              asks a narrower question: given the facts a logic student is
              taught to look at, can the learning rule assemble them? It is
              still not the answer — rule 4 is a biconditional (an XNOR) over
              two of these facts, so even here the target is not linearly
              separable. That is the same wall `xor_pain.py` hit, which is why
              it is worth measuring both.
    """
    if feature_set not in FEATURE_SETS:
        raise ValueError(f"unknown feature set {feature_set!r}; "
                         f"expected one of {FEATURE_SETS}")
    f = {
        f"p1_{s.major}",
        f"p2_{s.minor}",
        f"p3_{s.conclusion}",
        f"fig_{s.figure}",
    }
    if feature_set == "distrib":
        for name, on in s.facts().items():
            f.add(name if on else f"not_{name}")
    return frozenset(f)


def syllogism_feature_names(feature_set: str = "raw") -> list[str]:
    """Every feature the set can ever produce. The weave needs a knot for each."""
    names = [f"p1_{m}" for m in "AEIO"]      # major premise
    names += [f"p2_{m}" for m in "AEIO"]     # minor premise
    names += [f"p3_{m}" for m in "AEIO"]     # conclusion
    names += [f"fig_{i}" for i in (1, 2, 3, 4)]
    if feature_set == "distrib":
        from .syllogism import Syllogism as _S
        for key in _S(1, "AAA").facts():
            names += [key, f"not_{key}"]
    return names


def encode_syllogism(s: Syllogism, feature_set: str = "raw") -> Argument:
    """Stage a syllogism as a two-seat machloket.

    מתרץ holds that the conclusion follows. מקשן holds there is a פירכא.
    The winner is not a matter of taste: it is `s.valid()`, whose label comes
    from a rule engine checked against the 24 classical moods.
    """
    return Argument(
        id=f"syl:{s.key()}",
        features=syllogism_features(s, feature_set),
        winner=SEAT_M if s.valid() else SEAT_Q,
        seat_m="מתרץ",
        seat_q="מקשן",
        text=s.text(),
        source="Aristotle, Prior Analytics; מילות ההגיון לרמב\"ם, פרקים ו–ז",
        meta={"figure": s.figure, "mood": s.mood, "classical_name": s.name,
              "fault": s.fault(), "boolean_valid": s.boolean_valid()},
    )


# ------------------------------------------------------- machloket features

def _sage_slug(name: str) -> str:
    """A stable ASCII-free slug is fine — feature names are only knot names."""
    return name.replace(" ", "_").replace("\"", "").replace("׳", "")


def machloket_features(m: Machloket, swap: bool) -> frozenset[str]:
    """Who sits where, and the character of the dispute. NOT the rule of פסק.

    `swap` puts seat_b on M. Without it, every dispute in the corpus happens
    to have בית שמאי first, and "whoever spoke first loses" would score 13/14
    — the weave would learn seat order, which is not a rule of anything. The
    swap is deterministic (see dataset.py) so the corpus is reproducible.
    """
    a, b = (m.seat_b, m.seat_a) if swap else (m.seat_a, m.seat_b)
    strict = m.strict_side
    if swap and strict in ("A", "B"):
        strict = "B" if strict == "A" else "A"
    f = {
        f"m_is_{_sage_slug(a)}",
        f"q_is_{_sage_slug(b)}",
        f"tractate_{m.source.split()[0]}",
    }
    f.add({"A": "m_strict", "B": "q_strict"}.get(strict, "no_strict_side"))
    return frozenset(f)


def machloket_feature_names(corpus: list[Machloket]) -> list[str]:
    names: set[str] = set()
    for m in corpus:
        for swap in (False, True):
            names |= machloket_features(m, swap)
    return sorted(names)


def encode_machloket(m: Machloket, swap: bool) -> Argument:
    a_seat, b_seat = (m.seat_b, m.seat_a) if swap else (m.seat_a, m.seat_b)
    winner_seat = m.seat_a if m.psak == "A" else m.seat_b
    return Argument(
        # The seating is part of the id. Both seatings shared one id until the
        # dataset was built and two rows came back with the same name — which is
        # also how the leak below was found.
        id=f"mach:{m.id}:{'b' if swap else 'a'}",
        features=machloket_features(m, swap),
        winner=SEAT_M if winner_seat == a_seat else SEAT_Q,
        seat_m=a_seat, seat_q=b_seat,
        text=m.topic,
        source=m.source,
        meta={"psak_rule": m.psak_rule, "verified": m.verified,
              "swapped": swap, "notes": m.notes, "dispute": m.id},
    )


def self_test() -> None:
    from .syllogism import all_syllogisms
    from .machloket import corpus as mcorpus

    for fs in FEATURE_SETS:
        names = set(syllogism_feature_names(fs))
        want = 16 if fs == "raw" else 40
        assert len(names) == want, (fs, len(names))
        for s in all_syllogisms():
            f = syllogism_features(s, fs)
            assert f <= names, f - names
            # exactly one of each one-hot group is present
            assert sum(1 for n in f if n.startswith("p1_")) == 1
            assert sum(1 for n in f if n.startswith("fig_")) == 1
            if fs == "distrib":
                for key in s.facts():
                    assert (key in f) != (f"not_{key}" in f), key
        # no feature may name the verdict or the fault
        assert not any("valid" in n or "fault" in n for n in names)

    names = set(machloket_feature_names(mcorpus()))
    for m in mcorpus():
        for swap in (False, True):
            arg = encode_machloket(m, swap)
            assert arg.features <= names
            assert sum(1 for n in arg.features if n.startswith("m_is_")) == 1
            # swapping the seats must flip the winner, never keep it
            other = encode_machloket(m, not swap)
            assert arg.winner != other.winner, m.id
    # the rule of פסק must not be reachable as a feature
    assert not any("hillel" in n.lower() and "halakh" in n.lower() for n in names)


if __name__ == "__main__":
    self_test()
    print("raw     :", len(syllogism_feature_names("raw")), "features")
    print("distrib :", len(syllogism_feature_names("distrib")), "features")
    from .syllogism import Syllogism
    for key in ("AAA", "AAI"):
        s = Syllogism(1, key)
        a = encode_syllogism(s, "raw")
        print(f"\n{s.key()} {s.name or '(invalid)'}: {s.text()}")
        print(f"  features : {sorted(a.features)}")
        print(f"  winner   : {a.winner}  ({a.seat_m if a.winner=='M' else a.seat_q})")
