# לזכרה של עלמה ז״ל
"""QUORUM · judge · tests — including the two that matter most.

Most of these are ordinary. Two are not:

  test_ledger_is_derived_not_baked   perturbs ONE structural fact at a time and
                                     demands the verdict move. If the Kropotkin
                                     ledger came out right because the answer was
                                     smuggled into the case file, these fail.

  test_the_judge_refuses             a claim nobody attacked, with evidence
                                     nobody checked and no concession, must come
                                     back CANNOT RULE. A judge that never refuses
                                     always rules, which is worthless.

    python test_judge.py     (also runs under pytest)
"""
from __future__ import annotations

import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import dung                       # noqa: E402
import entail                     # noqa: E402
import quorum_bridge              # noqa: E402
from rules import (HELD, NORULE, PARTIAL, REJECTED, judge_case)   # noqa: E402
from schema import Case, load_case                                # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
KROP = os.path.join(HERE, "cases", "kropotkin-mutual-aid.json")


def _raw():
    with open(KROP, "r", encoding="utf-8") as f:
        return json.load(f)


def _judge(raw):
    return judge_case(Case(**copy.deepcopy(raw)))


def _v(res, cid):
    return next(v for v in res["verdicts"] if v.claim_id == cid)


# ─────────────────────────────────────────────────────── the formal engines ──
def test_grounded_semantics():
    assert dung.grounded(["C", "K"], [("K", "C")])["C"] == dung.OUT
    assert dung.grounded(["C", "K", "T"], [("K", "C"), ("T", "K")])["C"] == dung.IN
    assert dung.grounded(["C", "K"], [("K", "C"), ("C", "K")])["C"] == dung.UNDECIDED
    # a malformed edge must not be able to flip a verdict, nor crash a ruling
    assert dung.grounded(["C"], [("ghost", "C")])["C"] == dung.IN


def test_z3_says_no_when_it_should():
    assert entail.check(["a", "implies(a, b)"], "b")["status"] == "valid"
    bad = entail.check(["widespread", "species_benefit"], "not needs_explanation")
    assert bad["status"] == "invalid" and bad["countermodel"]
    assert entail.check(["a", "not a"], "b")["status"] == "unsound"


def test_z3_refuses_to_be_a_shell():
    r = entail.check(['__import__("os").system("echo pwned")'], "x")
    assert r["status"] == "error"
    assert entail.check(["a; import os"], "x")["status"] == "error"


def test_scope_attack_kills_the_universal_but_not_the_scoped():
    assert entail.coherent(["forall p: holds(p)"], "",
                           ["exists p: dense(p) and not holds(p)"]
                           )["status"] == "incompatible"
    assert entail.coherent(["forall p: implies(sparse(p), holds(p))"], "",
                           ["exists p: dense(p) and not holds(p)"]
                           )["status"] == "coherent"


# ──────────────────────────────────────────────── the case file cannot cheat ──
def test_case_file_may_not_smuggle_a_verdict():
    raw = _raw()
    raw["claims"][0]["verdict"] = "held"
    try:
        Case(**raw)
    except TypeError:
        pass                                   # unknown field -> rejected anyway
    from schema import _reject_truth_fields
    for bad in ("verdict", "held", "true", "expected"):
        try:
            _reject_truth_fields({"claims": [{"id": "x", bad: 1}]})
            raise AssertionError("smuggled '%s' was accepted" % bad)
        except ValueError:
            pass


# ──────────────────────────────────────────────────── the validation ledger ──
def test_kropotkin_ledger_matches_the_booklet():
    res = _judge(_raw())
    assert res["tally"] == {"held": 3, "partial": 2, "rejected": 3, "norule": 0}, \
        res["tally"]
    assert res["rejected_total"] == 3
    assert res["rejected_why"] == 2 and res["rejected_what"] == 1
    assert [_v(res, c).verdict for c in ("K1", "K2", "K3")] == [HELD] * 3
    assert [_v(res, c).verdict for c in ("K4", "K8")] == [PARTIAL] * 2
    assert [_v(res, c).verdict for c in ("K5", "K6", "K7")] == [REJECTED] * 3
    assert _v(res, "K5").layer == "why"
    assert _v(res, "K6").layer == "why"
    assert _v(res, "K7").layer == "what"


def test_ledger_is_derived_not_baked():
    """Move one structural fact; the verdict must move with it. If these pass
    while the ledger above also passes, the ledger was computed, not recited."""
    # 1. Answering the objection to K5 is NOT enough, and that is the point: the
    #    inference is invalid whether or not anyone objected, so Z3 keeps saying
    #    no. Supply the premise Kropotkin suppressed AND answer the objection and
    #    only then does the claim hold. G1 is nobody's ally.
    raw = _raw()
    raw["attacks"].append({"id": "T_k5", "by": "defender", "attacks": "A_needs_why",
                           "target": "evidence", "text_en": "a תירוץ that stands"})
    still = _v(_judge(raw), "K5")
    assert still.verdict == REJECTED and still.layer == "why"

    raw = _raw()
    for c in raw["claims"]:
        if c["id"] == "K5":
            c["formal"]["premises"].append(
                "implies(widespread and species_benefit, not needs_explanation)")
    raw["attacks"].append({"id": "T_k5", "by": "defender", "attacks": "A_needs_why",
                           "target": "evidence", "text_en": "a תירוץ that stands"})
    assert _v(_judge(raw), "K5").verdict == HELD

    # 2. Re-aim the dense-population objection from the SCOPE at the PREMISE and
    #    the partial becomes a rejection. The scope rule is doing real work.
    raw = _raw()
    for a in raw["attacks"]:
        if a["id"] == "A_dense":
            a["target"] = "premise"
    assert _v(_judge(raw), "K4").verdict == REJECTED

    # 3. Downgrade K3's source to an interested party and a held claim falls.
    raw = _raw()
    for c in raw["claims"]:
        if c["id"] == "K3":
            c["evidence"][0]["provenance"] = "partisan"
    assert _v(_judge(raw), "K3").verdict == REJECTED

    # 4. Remove Williams and K6 stops being rejected on coherence.
    raw = _raw()
    raw["attacks"] = [a for a in raw["attacks"] if a["id"] != "A_williams"]
    assert _v(_judge(raw), "K6").verdict != REJECTED

    # 5. Have Kropotkin concede K1 outright and the strongest claim falls.
    raw = _raw()
    for c in raw["claims"]:
        if c["id"] == "K1":
            c["concessions"] = [{"by": "kropotkin", "total": True,
                                 "text_en": "I withdraw it"}]
    assert _v(_judge(raw), "K1").verdict == REJECTED


def test_a_concession_is_recorded_against_the_claim():
    raw = _raw()
    for c in raw["claims"]:
        if c["id"] == "K2":
            c["concessions"] = [{"by": "kropotkin", "total": False,
                                 "text_en": "partly right"}]
    assert _v(_judge(raw), "K2").verdict == PARTIAL


# ─────────────────────────────────────────────────────────── THE REFUSAL ──
def test_the_judge_refuses():
    """Nobody attacked it, nobody checked the source, nobody conceded. Every
    gate abstains, so there is no basis for a ruling and the judge says so."""
    case = Case(title_en="refusal", claims=[{
        "id": "R1", "by": "someone",
        "text_en": "The organisation is more resilient than its competitors",
        "evidence": [{"provenance": "unchecked", "source": "asserted in the debate"}],
    }])
    res = judge_case(case)
    v = _v(res, "R1")
    assert v.verdict == NORULE, v.verdict
    assert v.score == 0 and v.applicable == 0
    assert all(g.result == "abstain" for g in v.gates)


def test_a_standoff_is_also_a_refusal():
    """קושיא and תירוץ striking each other with nothing outside to break the tie
    is an unresolved מחלוקת, and reporting it as a ruling would be a lie."""
    case = Case(title_en="standoff",
                claims=[{"id": "S1", "text_en": "a claim"}],
                attacks=[{"id": "KA", "attacks": "S1", "target": "premise"},
                         # KA and KB strike each other and nothing outside breaks
                         # the tie, so neither is grounded and neither is S1
                         {"id": "KB", "attacks": "KA", "target": "premise"},
                         {"id": "KA2", "attacks": "KB", "target": "premise"}])
    case.attacks[2].id = "KA"          # KA <-> KB, a genuine deadlock
    res = judge_case(case)
    assert _v(res, "S1").verdict == NORULE


# ─────────────────────────────────────────────────── the QUORUM extractor ──
def test_extractor_reads_the_four_moves():
    transcript = [
        {"round": 0, "model": "alef", "text": "עמדתי: כל בדיקה חייבת להיכשל לפחות פעם אחת."},
        {"round": 0, "model": "bet", "text": "עמדתי: די בכך שהבדיקה רצה."},
        {"round": 1, "model": "alef", "text":
            "קושיא: מהיכן לך שהיא בודקת משהו? אין ראיה שהיא נכשלה מעולם.\n"
            "תירוץ: עמדתי עומדת.\n"
            "ראיה: 32 שומרים נבדקו ו-23 מהם לא סירבו מעולם.\n"
            "דחייה: דעתו נדחית."},
        {"round": 1, "model": "bet", "text":
            "קושיא: הדרישה שלך מחמירה מדי.\n"
            "תירוץ: בדיקת חיות היא עדיין בדיקה.\n"
            "ראיה: שרת שמת מתגלה בלי אף כישלון-סף.\n"
            "דחייה: אני מודה לו שבדיקה שלא סירבה מעולם לא הודגמה."},
    ]
    case = quorum_bridge.transcript_to_case("topic", transcript)
    assert len(case.claims) == 2
    kushiot = [a for a in case.attacks if a.id.startswith("K:")]
    assert len(kushiot) == 2
    # every ראיה is unchecked: naming a source is not checking it
    for c in case.claims:
        assert c.evidence and all(e.provenance == "unchecked" for e in c.evidence)
    # the concession was caught and credited
    bet = case.claim("C:bet")
    assert bet.concessions and bet.concessions[0].total
    # NOTHING was formalised — the extractor never invents a formal block
    assert all(c.formal is None for c in case.claims)


def test_live_debate_if_present():
    p = os.path.join(HERE, "live_debate.json")
    if not os.path.exists(p):
        return
    res = quorum_bridge.judge_done_event(quorum_bridge.load_debate(p))
    assert res["verdicts"], "a real debate produced no judgeable claim"


def _run():
    fails = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            fn()
            print("PASS", name)
        except Exception as e:
            fails += 1
            print("FAIL", name, "->", repr(e))
    print()
    print("FAILURES:", fails)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(_run())
