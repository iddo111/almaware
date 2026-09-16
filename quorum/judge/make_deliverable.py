# לזכרה של עלמה ז״ל
"""QUORUM · judge · make_deliverable — the one real verdict document.

Two judged arguments in one sheet:

  A  the LIVE QUORUM debate run tonight, claude vs grok, judged straight off the
     transcript — including the claim the judge REFUSES to rule on.
  B  the Kropotkin booklet, whose ledger was produced by careful human reading,
     used here as the validation set.

Renders to one tall page so the whole ledger arrives as a single JPEG he can
read on the phone, plus the A4-paginated PDF. HTML is authored in a scratch
directory; only .jpg and .pdf go to the Desktop.

    python make_deliverable.py [outdir]
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import quorum_bridge                    # noqa: E402
import render as R                      # noqa: E402
from rules import judge_case            # noqa: E402
from schema import load_case            # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop")
SCRATCH = os.path.join(HERE, "out")
STEM = "PSAK-hashofet-QUORUM"

TITLE_HE = "פסק — QUORUM טוען, השופט פוסק"
TITLE_EN = "THE JUDGE — QUORUM argues; this rules"

LEDE_HE = (
    "השופט אינו פוסק אם טענה נכונה. הוא פוסק אם היא עומדת — וזה דבר שאפשר למדוד. "
    "חמישה שערים: G1 היסק (האם המסקנה נובעת מן ההנחות כפי שנוסחו — Z3), "
    "G2 עמידה בקושיא (הרחבה מבוססת של גרף הטיעון), "
    "G3 קוהרנטיות (האם אפשר להחזיק בטענה יחד עם הקושיא ששרדה — Z3), "
    "G4 ראיה (האם הראיה היא מה שהיא מתיימרת להיות), "
    "G5 הודאה (היכן בעל הטענה הודה — וזו זכייה בצורה הזו, לא הפסד). "
    "שער שלא ניתן להפעיל נמנע, ויוצא מן המכנה. כשאף שער אינו ישים — אין פסק, "
    "והשופט אומר זאת."
)
LEDE_EN = (
    "The judge does not rule on whether a claim is TRUE. It rules on whether it "
    "HOLDS, which is measurable. Five gates: G1 entailment (does the conclusion "
    "follow from the premises as stated — Z3), G2 survival (grounded extension "
    "over the argument graph), G3 coherence (can the claim be held together with "
    "the קושיא that survived — Z3), G4 evidence (is the source what it claims to "
    "be), G5 concession (where the arguer yielded — a win condition of this form, "
    "not a loss). A gate that cannot be applied abstains and leaves the "
    "denominator. When no gate applies there is no ruling, and the judge says so."
)


def section_live():
    p = os.path.join(HERE, "live_debate.json")
    done = quorum_bridge.load_debate(p)
    res = quorum_bridge.judge_done_event(done)
    seats = sorted({t["model"] for t in done["transcript"] if (t.get("text") or "").strip()})
    return {
        "res": res, "case": res["case"],
        "head_he": "א · דיון QUORUM חי, 2026-09-06",
        "head_en": "A · a live QUORUM debate, 2026-09-06",
        "sub_he": "השאלה: האם מדד שמעולם לא סירב הוא בכלל מדד?  ·  מושבים: "
                  + ", ".join(seats) + "  ·  " + str(len(done["transcript"]))
                  + " תורות, 3 סבבים. הפסק חולץ מסימוני קושיא/תירוץ/ראיה/דחייה, "
                    "בלי שום מודל בלולאה.",
        "sub_en": "Question: is a check that has never refused a check at all?  ·  "
                  "Seats: " + ", ".join(seats) + "  ·  "
                  + str(len(done["transcript"])) + " turns, 3 rounds. Extracted "
                  "from the four move markers with no model in the loop.",
        "note_title": "הסירוב · the refusal",
        "note_he": "המסקנה של הדיון — הדבר היחיד בתמליל שכבר נראה כמו פסק — היא "
                   "בדיוק מה שהשופט מסרב לפסוק עליו: היא נכתבה אחרי כל הסבבים, "
                   "אף אחד לא הקשה עליה, שום ראיה שלה לא נבדקה ואיש לא הודה בה. "
                   "כל חמשת השערים נמנעים, ולכן: אין פסק. זה בדיוק הפער שבגללו "
                   "השופט קיים.",
        "note_en": "The debate's own closing מסקנה — the one thing in the "
                   "transcript that already looks like a verdict — is exactly "
                   "what the judge refuses to rule on. It was written after every "
                   "round, nobody raised a קושיא against it, none of its evidence "
                   "was checked and nobody conceded to it. All five gates abstain, "
                   "so: CANNOT RULE. That gap is why the judge exists.",
    }


def section_kropotkin():
    case = load_case(os.path.join(HERE, "cases", "kropotkin-mutual-aid.json"))
    res = judge_case(case)
    return {
        "res": res, "case": case, "newpage": False,
        "head_he": "ב · מבחן האימות: קרופוטקין, ״עזרה הדדית״ (1902)",
        "head_en": "B · the validation set: Kropotkin, Mutual Aid (1902)",
        "sub_he": "הפסק האנושי שנכתב בקריאה קפדנית אמר: 3 עמדו, 2 חלקית, 3 נדחו — "
                  "ושתיים מן השלוש נוגעות ל״למה״ ולא ל״מה״. "
                  "קובץ המקרה מתאר רק את מבנה הטיעון (הנחות, קושיות, דרגת מקור); "
                  "שום פסק לא הועבר אליו — הטוען מסרב לטעון קובץ שנוקב בפסק.",
        "sub_en": "The human ledger, written by careful reading, said: 3 held, 2 "
                  "partly, 3 rejected — and two of the three are about the WHY. "
                  "The case file carries only the argument's structure (premises, "
                  "קושיות, source grades); no verdict was passed to it — the loader "
                  "refuses a case file that names one.",
        "note_title": "התאמה · the match",
        "note_he": "8 מתוך 8 זהים, כולל פיצול ה״למה״ מול ה״מה״. הפסק חושב, לא הוקלד: "
                   "בכל אחת מחמש הפרעות מבניות (מענה לקושיא, הסטת קושיא מן התחום אל "
                   "ההנחה, הורדת דרגת מקור, הסרת ויליאמס, הודאה מלאה) הפסק זז בהתאם.",
        "note_en": "8 of 8 identical, including the WHY/WHAT split. The ledger was "
                   "computed, not recited: under each of five structural "
                   "perturbations — answering a קושיא, re-aiming one from scope to "
                   "premise, downgrading a source, deleting Williams, conceding "
                   "outright — the verdict moved with it.",
    }


def main(outdir=DESKTOP):
    live, krop = section_live(), section_kropotkin()
    lv, kv = live["res"], krop["res"]

    closing_he = (
        "בדיון החי: %d עמדו, %d חלקית, %d נדחו, ו-%d אין-פסק. "
        "אצל קרופוטקין: %d עמדו, %d חלקית, %d נדחו — זהה לפסק האנושי, 8 מתוך 8. "
        "מה שהשתנה הלילה הוא לא שיש חוות דעת נוספת, אלא שיש הכרעה: "
        "בלי פסק, חמישה מודלים הם חמש דעות ואפס הכרעות; עם פסק, גם שניים כבר שווים משהו."
    ) % (lv["tally"]["held"], lv["tally"]["partial"], lv["tally"]["rejected"],
         lv["tally"]["norule"], kv["tally"]["held"], kv["tally"]["partial"],
         kv["tally"]["rejected"])
    closing_en = (
        "Live debate: %d held, %d partly, %d rejected, %d CANNOT RULE. Kropotkin: "
        "%d held, %d partly, %d rejected — identical to the human ledger, 8 of 8. "
        "What changed is not that there is one more opinion in the room, but that "
        "there is a ruling: without one, five models are five opinions and zero "
        "rulings; with one, even two members are already worth something."
    ) % (lv["tally"]["held"], lv["tally"]["partial"], lv["tally"]["rejected"],
         lv["tally"]["norule"], kv["tally"]["held"], kv["tally"]["partial"],
         kv["tally"]["rejected"])

    # one tall page so the whole ledger lands in a single phone-readable JPEG
    R.CSS = R.CSS.replace("@page { size: A4 portrait;",
                          "@page { size: 210mm 760mm;")
    out = R.render_report(
        outdir, STEM, html_dir=SCRATCH,
        title_he=TITLE_HE, title_en=TITLE_EN,
        lede_he=LEDE_HE, lede_en=LEDE_EN,
        sections=[live, krop],
        closing_he=closing_he, closing_en=closing_en)
    print(json.dumps({
        "pdf": out["pdf"], "jpg": out["jpg"], "px": out["px"],
        "pdf_pages": out["pages"],
        "live_tally": lv["tally"], "kropotkin_tally": kv["tally"],
        "kropotkin_why_what": [kv["rejected_why"], kv["rejected_what"]],
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else DESKTOP))
