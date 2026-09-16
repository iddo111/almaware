# -*- coding: utf-8 -*-
"""The exact-ground-truth corpus: all 256 categorical syllogisms.

WHY THIS AND NOT A DOWNLOADED TALMUD
------------------------------------
Because the label here is not an opinion. A categorical syllogism is valid or
invalid by a proof that is 2,300 years old, and the whole space is 4 moods^3 x
4 figures = 256 items — every one of which can be generated and labelled on
this machine, tonight, with no download and nothing to trust.

And it is not off-topic. Aristotle's syllogistic reached Hebrew as
**מילות ההגיון** (Maimonides, *Millot ha-Higgayon*, ch. 6–7), and the
medieval Jewish logicians argued in exactly these terms. It is the shared
skeleton under "logic" and under "גמרא" both.

THE DIALECTIC READING — this is what makes it a שקלא וטריא and not a quiz
------------------------------------------------------------------------
Every syllogism is staged as a two-seat machloket:

    מתרץ  (the defender) holds: the conclusion FOLLOWS.
    מקשן  (the challenger) holds: it does not — there is a פירכא,
                                  a case where the premises stand and the
                                  conclusion falls.

That is not a costume. Proving a syllogism invalid IS counterexample
construction, in Aristotle and in the Gemara both ("ודלמא…"). The verdict is
which seat is left standing: מתרץ if valid, מקשן if the פירכא lands.

THE FOUR PROPOSITIONS (the מרובע / square of opposition)
-------------------------------------------------------
    A   All X are Y        universal affirmative    כל
    E   No X are Y         universal negative       אין
    I   Some X are Y       particular affirmative   יש
    O   Some X are not Y   particular negative      יש שאינו

A term is **distributed** in a proposition when the proposition says
something about every member of it.

THE FOUR FIGURES (where the middle term M sits)
-----------------------------------------------
    fig 1:  M-P, S-M        fig 2:  P-M, S-M
    fig 3:  M-P, M-S        fig 4:  P-M, M-S
Conclusion is always S-P.

THE RULES (traditional / Aristotelian reading, with existential import)
----------------------------------------------------------------------
    1. the middle term must be distributed at least once
    2. a term distributed in the conclusion must be distributed in its premise
    3. two negative premises prove nothing
    4. a negative premise iff a negative conclusion

These four alone select exactly the classical **24** valid moods, and
`self_test()` asserts that against the 24 medieval names (Barbara, Celarent,
Darii, …). If the count is not 24 this module refuses to be imported as
correct. That assertion is the reason to trust the labels.

Note for later, and it is a real מחלוקת and not a footnote: under the modern
Boolean reading, existential import is denied and the five "subaltern" moods
(Barbari, Celaront, Cesaro, Camestrop, Camenop) plus Darapti, Felapton,
Bramantip and Fesapo fall, leaving 15. We label under the traditional reading
— the one Maimonides transmits. `boolean_valid()` gives the other side.
"""
from __future__ import annotations

from dataclasses import dataclass

MOODS = ("A", "E", "I", "O")
FIGURES = (1, 2, 3, 4)

# (subject distributed, predicate distributed) for each proposition type
DISTRIBUTION = {
    "A": (True, False),    # All X are Y      — about every X, not every Y
    "E": (True, True),     # No X are Y       — about every X and every Y
    "I": (False, False),   # Some X are Y     — about neither, entirely
    "O": (False, True),    # Some X are not Y — about every Y (excluded from some X)
}
NEGATIVE = {"A": False, "E": True, "I": False, "O": True}
UNIVERSAL = {"A": True, "E": True, "I": False, "O": False}

HEBREW = {"A": "כל", "E": "אין", "I": "יש", "O": "יש שאינו"}

# Where each premise's subject and predicate come from, by figure.
# (major premise terms, minor premise terms); conclusion is always (S, P).
FIGURE_TERMS = {
    1: (("M", "P"), ("S", "M")),
    2: (("P", "M"), ("S", "M")),
    3: (("M", "P"), ("M", "S")),
    4: (("P", "M"), ("M", "S")),
}

# The 24 classical names, as the control on the rule engine.
CLASSICAL = {
    (1, "AAA"): "Barbara",   (1, "EAE"): "Celarent",  (1, "AII"): "Darii",
    (1, "EIO"): "Ferio",     (1, "AAI"): "Barbari",   (1, "EAO"): "Celaront",
    (2, "EAE"): "Cesare",    (2, "AEE"): "Camestres", (2, "EIO"): "Festino",
    (2, "AOO"): "Baroco",    (2, "EAO"): "Cesaro",    (2, "AEO"): "Camestrop",
    (3, "AAI"): "Darapti",   (3, "IAI"): "Disamis",   (3, "AII"): "Datisi",
    (3, "EAO"): "Felapton",  (3, "OAO"): "Bokardo",   (3, "EIO"): "Ferison",
    (4, "AAI"): "Bramantip", (4, "AEE"): "Camenes",   (4, "IAI"): "Dimaris",
    (4, "EAO"): "Fesapo",    (4, "EIO"): "Fresison",  (4, "AEO"): "Camenop",
}

# The nine moods that stand only under existential import — the ones the
# modern Boolean reading strikes out. 24 - 9 = 15.
EXISTENTIAL_ONLY = {
    (1, "AAI"), (1, "EAO"), (2, "EAO"), (2, "AEO"), (3, "AAI"),
    (3, "EAO"), (4, "AAI"), (4, "EAO"), (4, "AEO"),
}


@dataclass(frozen=True)
class Syllogism:
    figure: int
    mood: str                     # three letters: major, minor, conclusion

    @property
    def major(self) -> str:
        return self.mood[0]

    @property
    def minor(self) -> str:
        return self.mood[1]

    @property
    def conclusion(self) -> str:
        return self.mood[2]

    @property
    def name(self) -> str:
        return CLASSICAL.get((self.figure, self.mood), "")

    def key(self) -> str:
        return f"{self.mood}-{self.figure}"

    # ---- distribution of each of the three terms, where it appears ----
    def _term_distributed(self, term: str, prop_type: str,
                          terms: tuple[str, str]) -> bool | None:
        """Is `term` distributed in a proposition of `prop_type` over `terms`?

        None when the term does not appear in that proposition at all.
        """
        subj_d, pred_d = DISTRIBUTION[prop_type]
        if terms[0] == term:
            return subj_d
        if terms[1] == term:
            return pred_d
        return None

    def facts(self) -> dict[str, bool]:
        """The structural observations a reader can make WITHOUT knowing the rules.

        Distribution, negativity, universality. Not one of these is "is it
        valid" — the rules are conjunctions and a biconditional OVER these,
        and assembling them is the thing left to learn.
        """
        maj_terms, min_terms = FIGURE_TERMS[self.figure]
        con_terms = ("S", "P")
        f = {
            "mid_dist_maj": bool(self._term_distributed("M", self.major, maj_terms)),
            "mid_dist_min": bool(self._term_distributed("M", self.minor, min_terms)),
            "maj_dist_con": bool(self._term_distributed("P", self.conclusion, con_terms)),
            "maj_dist_prem": bool(self._term_distributed("P", self.major, maj_terms)),
            "min_dist_con": bool(self._term_distributed("S", self.conclusion, con_terms)),
            "min_dist_prem": bool(self._term_distributed("S", self.minor, min_terms)),
            "neg_maj": NEGATIVE[self.major],
            "neg_min": NEGATIVE[self.minor],
            "neg_con": NEGATIVE[self.conclusion],
            "univ_maj": UNIVERSAL[self.major],
            "univ_min": UNIVERSAL[self.minor],
            "univ_con": UNIVERSAL[self.conclusion],
        }
        return f

    # ---- the verdict ----
    def valid(self) -> bool:
        """Traditional (Aristotelian) validity. The label."""
        f = self.facts()
        if not (f["mid_dist_maj"] or f["mid_dist_min"]):
            return False                                   # undistributed middle
        if f["maj_dist_con"] and not f["maj_dist_prem"]:
            return False                                   # illicit major
        if f["min_dist_con"] and not f["min_dist_prem"]:
            return False                                   # illicit minor
        if f["neg_maj"] and f["neg_min"]:
            return False                                   # two negatives
        if (f["neg_maj"] or f["neg_min"]) != f["neg_con"]:
            return False                                   # the biconditional — an XNOR
        return True

    def boolean_valid(self) -> bool:
        """The modern reading, for the record. Denies existential import."""
        return self.valid() and (self.figure, self.mood) not in EXISTENTIAL_ONLY

    def fault(self) -> str:
        """Which פירכא the מקשן has, when he has one. '' when the position stands."""
        f = self.facts()
        if not (f["mid_dist_maj"] or f["mid_dist_min"]):
            return "undistributed-middle"
        if f["maj_dist_con"] and not f["maj_dist_prem"]:
            return "illicit-major"
        if f["min_dist_con"] and not f["min_dist_prem"]:
            return "illicit-minor"
        if f["neg_maj"] and f["neg_min"]:
            return "two-negatives"
        if (f["neg_maj"] or f["neg_min"]) != f["neg_con"]:
            return "quality-mismatch"
        return ""

    # ---- how it reads to a person ----
    def _say(self, prop_type: str, terms: tuple[str, str]) -> str:
        x, y = terms
        return {
            "A": f"All {x} are {y}",
            "E": f"No {x} are {y}",
            "I": f"Some {x} are {y}",
            "O": f"Some {x} are not {y}",
        }[prop_type]

    def text(self) -> str:
        maj_terms, min_terms = FIGURE_TERMS[self.figure]
        return (f"{self._say(self.major, maj_terms)}; "
                f"{self._say(self.minor, min_terms)}; "
                f"therefore {self._say(self.conclusion, ('S', 'P'))}")


def all_syllogisms() -> list[Syllogism]:
    """All 256. The complete space, not a sample of it."""
    out = []
    for fig in FIGURES:
        for a in MOODS:
            for b in MOODS:
                for c in MOODS:
                    out.append(Syllogism(fig, a + b + c))
    return out


def self_test() -> None:
    """The rule engine against the 24 medieval names. This is why the labels stand."""
    syls = all_syllogisms()
    assert len(syls) == 256, len(syls)
    valid = {(s.figure, s.mood) for s in syls if s.valid()}
    named = set(CLASSICAL)
    missing = named - valid
    extra = valid - named
    assert not missing, f"rules reject a classical mood: {sorted(missing)}"
    assert not extra, f"rules accept a non-classical mood: {sorted(extra)}"
    assert len(valid) == 24, len(valid)
    boolean = {(s.figure, s.mood) for s in syls if s.boolean_valid()}
    assert len(boolean) == 15, len(boolean)
    # Every invalid syllogism must name a fault, every valid one must name none.
    for s in syls:
        assert bool(s.fault()) != s.valid(), s.key()


if __name__ == "__main__":
    self_test()
    syls = all_syllogisms()
    v = [s for s in syls if s.valid()]
    print(f"{len(syls)} syllogisms, {len(v)} valid (traditional), "
          f"{sum(1 for s in syls if s.boolean_valid())} valid (Boolean).")
    print("\nThe 24 that stand:")
    for s in v:
        print(f"  {s.key():7s} {s.name:11s} {s.text()}")
    from collections import Counter
    print("\nWhy the other 232 fall:")
    for fault, n in Counter(s.fault() for s in syls if not s.valid()).most_common():
        print(f"  {n:4d}  {fault}")
