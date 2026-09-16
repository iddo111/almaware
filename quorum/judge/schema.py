# לזכרה של עלמה ז״ל
"""QUORUM · judge · schema — the JUDGEABLE form of an argument.

A case is not prose. It is the structure a ruling can be derived from:
claims, the premises each claim was actually rested on, the קושיות raised
against it, where the arguer conceded, and what grade of source the ראיה is.

WHAT IS DELIBERATELY ABSENT: there is no `true`, no `false`, no `correct`
field. Nothing in this schema, and nothing in rules.py, can express "this
claim is true". A case can only say what was ARGUED and how. That absence is
the whole safety property of the judge — do not add such a field.

100% stdlib.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional

# ── evidence provenance grades ───────────────────────────────────────────────
# Graded on WHAT THE SOURCE IS, never on whether the reader agrees with it.
PROVENANCE = {
    # grade            : (score in [-1..1], is_fatal, label_he,               label_en)
    "primary":           (1.0,  False, "מקור ראשוני, נבדק",      "primary source, checked"),
    "replicated":        (1.0,  False, "ממצא ששוחזר",            "replicated finding"),
    "secondary":         (0.5,  False, "מקור משני",              "secondary source"),
    "contested":         (0.0,  False, "מקור שנוי במחלוקת",      "contested source"),
    "unchecked":         (None, False, "לא נבדק מול המקור",      "never checked against the source"),
    "absent":            (None, False, "לא הוצגה ראיה",          "no evidence offered"),
    "superseded":        (-1.0, False, "הוחלף בקונצנזוס מאוחר",  "superseded by later consensus"),
    # the two fatal ones. tonight's catalogue caught both in the wild:
    "partisan":          (-1.0, True,  "המקור היחיד הוא בעל דבר", "only source is an interested party"),
    "misattributed":     (-1.0, True,  "מיוחס למי שדחה אותו",    "credited to someone who rejects it"),
}
FATAL_PROVENANCE = tuple(k for k, v in PROVENANCE.items() if v[1])
ABSTAIN_PROVENANCE = ("unchecked", "absent")

# what layer of the argument a קושיא is aimed at. This is the distinction that
# produced the single most useful line of the Kropotkin ledger: two of the three
# rejections were about the WHY, not the WHAT.
TARGETS = {
    "premise":   "what",   # the claim's factual base
    "evidence":  "what",
    "inference": "why",    # the step from base to conclusion — the explanation
    "mechanism": "why",
    "scope":     "scope",  # true here, false there -> partial, never total
}


@dataclass
class Evidence:
    provenance: str = "absent"
    source: str = ""
    note_he: str = ""
    note_en: str = ""

    def grade(self) -> tuple:
        return PROVENANCE.get(self.provenance, PROVENANCE["absent"])


@dataclass
class Attack:
    """A קושיא. `by` is who raised it; `answers` is the id of the attack this
    argument itself answers (a תירוץ is modelled as an attack on the attack —
    that is what makes the grounded extension the right formalism)."""
    id: str
    by: str = ""
    target: str = "premise"          # premise|evidence|inference|mechanism|scope
    attacks: str = ""                # id of the claim or attack it is aimed at
    text_he: str = ""
    text_en: str = ""
    formal: str = ""                 # optional Z3 expression for G3
    scope_he: str = ""               # for target=="scope": WHERE it bites
    scope_en: str = ""

    @property
    def layer(self) -> str:
        return TARGETS.get(self.target, "what")


@dataclass
class Concession:
    by: str = ""
    total: bool = False              # conceded the claim outright, or only in part
    text_he: str = ""
    text_en: str = ""


@dataclass
class Claim:
    id: str
    by: str = ""
    text_he: str = ""
    text_en: str = ""
    # the premises AS STATED. If the arguer never stated them, leave empty —
    # an empty premise list is a fact about the argument, not a gap to fill in.
    premises: list = field(default_factory=list)          # [str] free text
    formal: Optional[dict] = None    # {"premises":[expr...], "conclusion":expr}
    universal_over: str = ""         # e.g. "population" -> the claim is a ∀ claim
    evidence: list = field(default_factory=list)          # [Evidence]
    concessions: list = field(default_factory=list)       # [Concession]

    def __post_init__(self):
        self.evidence = [e if isinstance(e, Evidence) else Evidence(**e) for e in self.evidence]
        self.concessions = [c if isinstance(c, Concession) else Concession(**c)
                            for c in self.concessions]


@dataclass
class Case:
    """One argument, put in a form a ruling can be derived from."""
    title_he: str = ""
    title_en: str = ""
    source: str = ""                 # where the argument came from
    kind: str = "document"           # document | quorum-transcript
    claims: list = field(default_factory=list)
    attacks: list = field(default_factory=list)
    note_he: str = ""
    note_en: str = ""

    def __post_init__(self):
        self.claims = [c if isinstance(c, Claim) else Claim(**c) for c in self.claims]
        self.attacks = [a if isinstance(a, Attack) else Attack(**a) for a in self.attacks]

    def attacks_on(self, node_id: str) -> list:
        return [a for a in self.attacks if a.attacks == node_id]

    def claim(self, cid: str) -> Optional[Claim]:
        for c in self.claims:
            if c.id == cid:
                return c
        return None


def load_case(path: str) -> Case:
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    _reject_truth_fields(raw)
    return Case(**raw)


_BANNED = {"true", "false", "correct", "truth", "is_true", "verdict", "ruling",
           "held", "rejected", "partial", "expected"}


def _reject_truth_fields(obj, path="case"):
    """A case file that carries the answer is not a test, it is a transcript of
    one. Refuse to load any case that names a verdict or a truth value: the
    ledger must be DERIVED, and a smuggled answer would make every validation
    circular. Raised loudly, not swallowed — this one is worth crashing over."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() in _BANNED:
                raise ValueError(
                    f"case file smuggles an answer at {path}.{k} — "
                    f"the judge derives verdicts, it does not read them")
            _reject_truth_fields(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _reject_truth_fields(v, f"{path}[{i}]")
