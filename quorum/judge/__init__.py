# לזכרה של עלמה ז״ל
"""QUORUM · THE JUDGE — the organ that RULES, where shakla only argues.

QUORUM produces שקלא וטריא. Five models arguing is five opinions and zero ruling.
This package turns a finished argument into a **verdict ledger**: one line per
claim, a score, and the reason.

THE ONE DESIGN CONSTRAINT — read it before changing anything here:

    The judge does NOT rule on whether a claim is TRUE.
    It rules on whether a claim HOLDS.

There is deliberately NO field anywhere in the case schema that says a claim is
true or false, and no gate consults one. A model asked for truth returns
confidence without knowledge (MIKO measured the cost: every neural arm sat at the
variance floor, beaten by 40 lines of BM25). "Holds" is structural, and structure
is measurable:

  G1 היסק        does the conclusion follow from the STATED premises?      (Z3)
  G2 עמידה       does it survive the strongest קושיא raised against it?    (Dung)
  G3 קוהרנטיות   can it coexist with the attacks that DID survive?         (Z3)
  G4 ראיה        is the evidence actually what it claims to be?            (provenance)
  G5 הודאה       did the arguer himself concede?                           (record)

The solver is the ruler, not a member: Z3 and the grounded extension do not agree
politely. Where an argument is not formalisable the judge says so and ABSTAINS on
that gate — it never fakes a formalisation. When no gate applies at all the
verdict is CANNOT RULE, out loud. A judge that never refuses always rules, which
is worthless.
"""
import os as _os
import sys as _sys

# rules/entail/dung/quorum_bridge import each other flat so every one of them can
# also be run as a plain script from this directory. Putting the package dir on
# the path makes BOTH work: `import judge` from the quorum root, and
# `python render.py` from inside judge/.
_HERE = _os.path.dirname(_os.path.abspath(__file__))
if _HERE not in _sys.path:
    _sys.path.insert(0, _HERE)

from .schema import Case, Claim, Attack, Evidence, load_case          # noqa: F401
from .rules import judge_case, Verdict, HELD, PARTIAL, REJECTED, NORULE  # noqa: F401

__all__ = ["Case", "Claim", "Attack", "Evidence", "load_case",
           "judge_case", "Verdict", "HELD", "PARTIAL", "REJECTED", "NORULE"]
