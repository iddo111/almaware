# לזכרה של עלמה ז״ל
"""QUORUM · judge · rules — THE FIVE GATES AND THE DECISION TABLE.

This is where the ruling actually happens, and it happens in a written-out table
rather than in a model's opinion, so a reader can audit every step and disagree
with a specific line.

THE FIVE GATES (each returns pass / fail / abstain, never true / false):

  G1  היסק        entailment  — does the conclusion follow from the STATED
                                premises?                            [Z3]
  G2  עמידה       survival    — does the claim survive the strongest קושיא
                                raised against it?                   [grounded]
  G3  קוהרנטיות   coherence   — can it be held together with the קושיות that
                                DID survive?                         [Z3]
  G4  ראיה        evidence    — is the evidence actually what it claims to be?
                                                                     [provenance]
  G5  הודאה       concession  — did the arguer himself concede? A concession is
                                a WIN CONDITION of this form, not a loss: it is
                                recorded as the claim yielding, and the arguer
                                gaining.                             [record]

ABSTAIN IS NOT A PASS. A gate that could not be applied is removed from the
denominator and named in the verdict. When NO gate applies the verdict is
CANNOT RULE — the refusal the whole design turns on. A judge that never returns
"cannot rule" is a judge that always rules, which is worthless.

WHAT / WHY / SCOPE. Every קושיא is aimed at a layer. An attack on a premise or on
the evidence hits the WHAT; an attack on the inference or the mechanism hits the
WHY; an attack that only bites inside a named region hits the SCOPE. That single
distinction is what let the Kropotkin ledger end in the sentence worth having:
three rejections, and two of the three are about the why rather than the what.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import dung
import entail
from schema import ABSTAIN_PROVENANCE, PROVENANCE

HELD = "held"
PARTIAL = "partial"
REJECTED = "rejected"
NORULE = "norule"

VERDICT_HE = {HELD: "עמד", PARTIAL: "חלקית", REJECTED: "נדחה", NORULE: "אין פסק"}
VERDICT_EN = {HELD: "Held", PARTIAL: "Partly", REJECTED: "Rejected",
              NORULE: "Cannot rule"}

PASS, FAIL, ABSTAIN = "pass", "fail", "abstain"

GATES = [
    ("G1", "היסק", "entailment", 30),
    ("G2", "עמידה בקושיא", "survival", 25),
    ("G3", "קוהרנטיות", "coherence", 25),
    ("G4", "ראיה", "evidence", 15),
    ("G5", "הודאה", "concession", 5),
]
GATE_WEIGHT = {g[0]: g[3] for g in GATES}


@dataclass
class GateResult:
    gate: str
    result: str                    # pass | fail | abstain
    layer: str = ""                # what | why | scope
    note_he: str = ""
    note_en: str = ""
    detail: str = ""               # countermodel / witness / source, verbatim


@dataclass
class Verdict:
    claim_id: str
    verdict: str
    score: int                     # 0..100 over the APPLICABLE gates only
    applicable: int
    gates: list = field(default_factory=list)
    layer: str = ""                # which layer decided it
    reason_he: str = ""
    reason_en: str = ""
    decided_by: str = "-"          # WHICH gate carried the ruling, so the sheet
                                   # can print the countermodel or the source that
                                   # actually decided it and not merely the first
                                   # failure it happens to find.
    thin: bool = False             # ruled on ONE gate only — a real verdict, but
                                   # a thin one, and the sheet must say so rather
                                   # than let one passed gate read like five.

    def to_dict(self):
        return {
            "claim_id": self.claim_id, "verdict": self.verdict,
            "score": self.score, "applicable": self.applicable,
            "layer": self.layer, "reason_he": self.reason_he,
            "reason_en": self.reason_en, "thin": self.thin,
            "decided_by": self.decided_by,
            "gates": [g.__dict__ for g in self.gates],
        }


# ─────────────────────────────────────────────────────────── the gates ──
def gate_entailment(claim):
    """G1. Formalisable or not — and if not, SAY SO instead of pretending."""
    f = claim.formal or {}
    prem, concl = f.get("premises") or [], f.get("conclusion") or ""
    if not prem or not concl:
        return GateResult("G1", ABSTAIN, "",
                          "הטענה לא נוסחה בצורה פורמלית — אין פסק על ההיסק",
                          "the claim was not formalised — no ruling on the inference",
                          "")
    r = entail.check(prem, concl)
    st = r["status"]
    if st == "valid":
        return GateResult("G1", PASS, "why",
                          "המסקנה נובעת מן ההנחות כפי שנוסחו",
                          "the conclusion follows from the premises as stated", "")
    if st == "invalid":
        return GateResult("G1", FAIL, "why",
                          "המסקנה אינה נובעת: קיים עולם שבו כל ההנחות מתקיימות והמסקנה נופלת",
                          "the conclusion does not follow: a countermodel exists",
                          r["countermodel"])
    if st == "unsound":
        return GateResult("G1", FAIL, "what",
                          "ההנחות סותרות זו את זו",
                          "the stated premises contradict each other", "")
    return GateResult("G1", ABSTAIN, "", r["note"], r["note"], "")


def gate_survival(claim, case, label):
    """G2. The grounded extension already computed who survived. This gate only
    reads it — no taste is exercised here."""
    aimed = case.attacks_on(claim.id)
    if not aimed:
        return GateResult("G2", ABSTAIN, "",
                          "לא הועלתה קושיא נגד הטענה — אין במה לעמוד",
                          "no קושיא was raised against it — nothing to survive", "")
    alive = dung.surviving_attacks(claim.id, case.attacks, label)
    status = label.get(claim.id, dung.UNDECIDED)
    if not alive and status == dung.IN:
        return GateResult("G2", PASS, "",
                          "כל קושיא נגדה נדחתה בתירוץ שעמד בעצמו",
                          "every קושיא against it was answered by a תירוץ that itself stood",
                          "")
    if status == dung.UNDECIDED:
        return GateResult("G2", ABSTAIN, "",
                          "תיקו: הקושיא והתירוץ מכים זה בזה ואיש אינו מוכרע",
                          "standoff: קושיא and תירוץ strike each other, neither resolves",
                          "; ".join(a.id for a in alive))
    layers = [a.layer for a in alive]
    layer = ("scope" if layers and all(x == "scope" for x in layers)
             else ("why" if "why" in layers else "what"))
    return GateResult("G2", FAIL, layer,
                      "קושיא שלא נענתה: " + "; ".join(
                          (a.text_he or a.id) for a in alive),
                      "unanswered קושיא: " + "; ".join(
                          (a.text_en or a.id) for a in alive),
                      "; ".join(a.id for a in alive))


def gate_coherence(claim, case, label):
    """G3. Z3 against the objections that actually survived. Only the surviving
    ones — an objection that was put down has no say here."""
    f = claim.formal or {}
    prem = f.get("premises") or []
    concl = f.get("conclusion") or ""
    alive = dung.surviving_attacks(claim.id, case.attacks, label)
    formulas = [a.formal for a in alive if (a.formal or "").strip()]
    if not prem and not concl:
        return GateResult("G3", ABSTAIN, "",
                          "הטענה לא נוסחה בצורה פורמלית",
                          "the claim was not formalised", "")
    if not formulas:
        return GateResult("G3", ABSTAIN, "",
                          "אף קושיא ששרדה לא נוסחה בצורה פורמלית",
                          "no surviving קושיא was formalised", "")
    r = entail.coherent(prem, concl, formulas)
    if r["status"] == "coherent":
        return GateResult("G3", PASS, "",
                          "הטענה והקושיא ששרדה יכולות להתקיים יחד",
                          "claim and surviving קושיא can both be held", r["witness"])
    if r["status"] == "incompatible":
        layers = [a.layer for a in alive if (a.formal or "").strip()]
        layer = ("scope" if layers and all(x == "scope" for x in layers)
                 else ("why" if "why" in layers else "what"))
        return GateResult("G3", FAIL, layer,
                          "בלתי אפשרי להחזיק בטענה יחד עם הקושיא ששרדה",
                          "the claim is formally incompatible with the surviving קושיא",
                          "; ".join(a.id for a in alive if (a.formal or "").strip()))
    return GateResult("G3", ABSTAIN, "", r["note"], r["note"], "")


def gate_evidence(claim):
    """G4. Graded on WHAT THE SOURCE IS. Never on whether the reader agrees.
    Two grades are fatal and both were caught in the wild tonight: a "fact" whose
    only source was an interested party, and a scholar credited with a reading
    she explicitly rejects."""
    if not claim.evidence:
        return GateResult("G4", ABSTAIN, "",
                          "לא הוצגה ראיה — אין מה לבדוק",
                          "no evidence was offered — nothing to check", "")
    worst, worst_ev = None, None
    for ev in claim.evidence:
        score, fatal, he, en = ev.grade()
        if fatal:
            return GateResult("G4", FAIL, "what",
                              "הראיה אינה מה שהיא מתיימרת להיות: " + he,
                              "the evidence is not what it claims to be: " + en,
                              ev.source)
        if score is None:
            continue
        if worst is None or score < worst:
            worst, worst_ev = score, ev
    if worst is None:
        grades = ", ".join(PROVENANCE.get(e.provenance, PROVENANCE["absent"])[3]
                           for e in claim.evidence)
        return GateResult("G4", ABSTAIN, "",
                          "הראיה מעולם לא נבדקה מול המקור",
                          "the evidence was never checked against the source", grades)
    _, _, he, en = worst_ev.grade()
    if worst > 0:
        return GateResult("G4", PASS, "", he, en, worst_ev.source)
    if worst < 0:
        return GateResult("G4", FAIL, "what", he, en, worst_ev.source)
    return GateResult("G4", ABSTAIN, "", he, en, worst_ev.source)


def gate_concession(claim):
    """G5. A concession is a win condition in this form, not a loss. The gate
    records it against the CLAIM and credits it to the ARGUER — those are two
    different books and the verdict sheet keeps them apart."""
    if not claim.concessions:
        return GateResult("G5", ABSTAIN, "",
                          "לא הייתה הודאה",
                          "no concession was made", "")
    total = [c for c in claim.concessions if c.total]
    if total:
        c = total[0]
        return GateResult("G5", FAIL, "what",
                          "בעל הטענה הודה בה במפורש (" + (c.by or "המערער") + ")",
                          "the arguer conceded the claim outright (" + (c.by or "arguer") + ")",
                          c.text_en or c.text_he)
    c = claim.concessions[0]
    return GateResult("G5", FAIL, "scope",
                      "בעל הטענה הודה בחלקה (" + (c.by or "המערער") + ")",
                      "the arguer conceded it in part (" + (c.by or "arguer") + ")",
                      c.text_en or c.text_he)


# ───────────────────────────────────────────────── the decision table ──
def _decide(gates):
    """The whole ruling, in one readable table. Order matters and the order is
    the argument: what the evidence IS comes before what follows from it,
    because a misattributed source makes the rest of the reasoning moot."""
    g = {x.gate: x for x in gates}
    applicable = [x for x in gates if x.result != ABSTAIN]

    if not applicable:
        return (NORULE, "", "-",
                "אף שער לא היה ישים — אין בסיס לפסק",
                "no gate could be applied — there is no basis for a ruling")

    if g["G4"].result == FAIL:
        return (REJECTED, "what", "G4",
                "נדחה על הראיה: " + g["G4"].note_he,
                "rejected on the evidence: " + g["G4"].note_en)

    if g["G5"].result == FAIL and g["G5"].layer == "what":
        return (REJECTED, "what", "G5",
                "נדחה בהודאת בעל דין: " + g["G5"].note_he,
                "rejected by the arguer's own concession: " + g["G5"].note_en)

    # THE SCOPE RULE, and it outranks every gate that could report a failure.
    # A קושיא that only bites inside a named region does not defeat a claim, it
    # NARROWS it: "true where populations are sparse, false where they are
    # dense" is a partial verdict no matter whether the graph or the solver was
    # the one that noticed. Without this rule Z3 would reject a scoped claim
    # outright — formally correct about the unquantified reading, and unfair
    # about what the arguer meant.
    failures = [x for x in gates if x.result == FAIL]
    if failures and all(x.layer == "scope" for x in failures):
        first = failures[0]
        return (PARTIAL, "scope", first.gate,
                "עמד מחוץ לתחום שבו הקושיא נושכת: " + first.note_he,
                "holds outside the region where the קושיא bites: " + first.note_en)

    # G1 BEFORE G3, deliberately. An invalid step is the deeper fault: it is a
    # defect in the argument itself and it holds whether or not anybody happened
    # to object. Incoherence with a surviving קושיא is a defect relative to an
    # opponent who showed up. When both fail, name the one that would still be
    # there in an empty room.
    if g["G1"].result == FAIL:
        return (REJECTED, g["G1"].layer, "G1",
                "נדחה על ההיסק: " + g["G1"].note_he,
                "rejected on the inference: " + g["G1"].note_en)

    if g["G3"].result == FAIL:
        return (REJECTED, g["G3"].layer, "G3",
                "נדחה על קוהרנטיות: " + g["G3"].note_he,
                "rejected on coherence: " + g["G3"].note_en)

    if g["G2"].result == FAIL:
        return (REJECTED, g["G2"].layer, "G2",
                "לא עמד בקושיא: " + g["G2"].note_he,
                "did not survive the קושיא: " + g["G2"].note_en)

    if g["G5"].result == FAIL:
        return (PARTIAL, "scope", "G5",
                "עמד חלקית — " + g["G5"].note_he,
                "partly held — " + g["G5"].note_en)

    if g["G2"].result == ABSTAIN and g["G2"].detail:
        return (NORULE, "", "G2",
                "תיקו בין קושיא לתירוץ — המחלוקת לא הוכרעה",
                "standoff between קושיא and תירוץ — the מחלוקת is unresolved")

    passes = [x for x in applicable if x.result == PASS]
    if not passes:
        return (NORULE, "", "-",
                "שום שער לא נכשל ושום שער לא עבר — אין בסיס לפסק",
                "no gate failed and no gate passed — there is no basis for a ruling")

    return (HELD, "", "-",
            "עמד בכל שער שהיה ישים (" + str(len(passes)) + " מתוך " +
            str(len(applicable)) + ")",
            "held at every gate that could be applied (" + str(len(passes)) +
            " of " + str(len(applicable)) + ")")


def _score(gates):
    got = tot = 0
    for x in gates:
        if x.result == ABSTAIN:
            continue
        w = GATE_WEIGHT[x.gate]
        tot += w
        if x.result == PASS:
            got += w
    if not tot:
        return 0, 0
    return int(round(100.0 * got / tot)), sum(1 for x in gates if x.result != ABSTAIN)


def judge_claim(claim, case, label):
    gates = [gate_entailment(claim), gate_survival(claim, case, label),
             gate_coherence(claim, case, label), gate_evidence(claim),
             gate_concession(claim)]
    verdict, layer, decided_by, he, en = _decide(gates)
    score, applicable = _score(gates)
    if verdict == NORULE:
        score = 0
    return Verdict(claim.id, verdict, score, applicable, gates, layer, he, en,
                   thin=(verdict != NORULE and applicable <= 1),
                   decided_by=decided_by)


def judge_case(case):
    """Case -> the ledger. Deterministic: same case in, same ledger out, always.
    No model is consulted anywhere in this function."""
    label, _edges = dung.build(case)
    verdicts = [judge_claim(c, case, label) for c in case.claims]
    tally = {HELD: 0, PARTIAL: 0, REJECTED: 0, NORULE: 0}
    for v in verdicts:
        tally[v.verdict] += 1
    rejected = [v for v in verdicts if v.verdict == REJECTED]
    why = sum(1 for v in rejected if v.layer == "why")
    return {
        "title_he": case.title_he, "title_en": case.title_en,
        "source": case.source, "kind": case.kind,
        "verdicts": verdicts, "labels": label, "tally": tally,
        "rejected_total": len(rejected), "rejected_why": why,
        "rejected_what": len(rejected) - why,
        "z3": entail.Z3_VERSION or "unavailable",
    }
