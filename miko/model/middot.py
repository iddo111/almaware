"""MIDDOT — the logic curriculum.  לזכרה של עלמה ז״ל.

> 🪟 BROKEN WINDOWS LAW — if it is not working, fix it immediately. Test the REAL output.

Iddo, 2026-08-29: *"אני רוצה שיהיה לו כל הביולוגיה והקבלה והלוגיקה."*

The 13 middot of R' Yishmael, the classical forms, and the fallacies — generated as
arguments in Hebrew and English, and **held out BY FORM**, so the test is always on
shapes of reasoning the model has never seen. Recovered unchanged from the archived
worm (`_genizah/almido-search-20260820/net/ramchal.py`): the curriculum was never the
part that failed.

⚠️ WHAT FAILED, AND MUST NOT BE REPEATED. Trained on this curriculum, the old model
scored **48.2 % on unseen forms — below the 50 % coin flip** — with train loss stuck at
0.666 against a chance of 0.693, and a per-form profile of `dayo 0% / dayo 100% /
denying 100% / modus 0%`: one fixed answer per form, not inference. That log's last line
sat unread for a day while memory recorded the work as an achievement.

Therefore the bar is stated HERE, before any training, and checked by code in `logic.py`:
    ≥ 75 % on inference forms never seen, AND no form scoring 0 % or 100 %
    (those two numbers together are the signature of one-fixed-answer-per-form).
"""
from __future__ import annotations

import random


# ───────────────────────────────────────────── the vocabulary of examples
# concrete, everyday subjects so the net learns FORM, not topic
SUBJ = [
    ("כל הכלבים", "all dogs"), ("כל המים", "all water"), ("כל הברזלים", "all iron"),
    ("כל הציפורים", "all birds"), ("כל המספרים הזוגיים", "all even numbers"),
    ("כל הנוירונים", "all neurons"), ("כל המנועים", "all engines"),
]
PRED = [
    ("נושמים", "breathe"), ("קופאים", "freeze"), ("מחלידים", "rust"),
    ("עפים", "fly"), ("מתחלקים בשתיים", "divide by two"),
    ("יורים", "fire"), ("מתחממים", "get hot"),
]
NAMES = [("רקסי", "Rexi"), ("הדבר הזה", "this thing"), ("הפריט", "the item"),
         ("המכשיר", "the device"), ("היצור", "the creature")]

# pairs on a shared scale, for קל וחומר: (lighter, heavier, scale-he, scale-en)
KV_PAIRS = [
    ("חול", "אבן", "כובד", "weight", "sand", "stone"),
    ("נר", "מדורה", "חום", "heat", "a candle", "a bonfire"),
    ("טיפה", "נהר", "כמות מים", "water volume", "a drop", "a river"),
    ("לחישה", "צעקה", "עוצמת קול", "loudness", "a whisper", "a shout"),
]


def _pick(rng: random.Random, pool):
    return pool[rng.randrange(len(pool))]


# ───────────────────────────────────────────── the forms
# each generator returns (hebrew, english, valid: bool, form_name)

def f_modus_ponens(rng, valid=True):
    s, se = _pick(rng, SUBJ)
    p, pe = _pick(rng, PRED)
    n, ne = _pick(rng, NAMES)
    if valid:
        he = f"אם {s} {p}, ו{n} הוא מהם — אז {n} {p}."
        en = f"If {se} {pe}, and {ne} is one of them, then {ne} {pe}."
    else:  # affirming the consequent
        he = f"אם {s} {p}, ו{n} {p} — אז {n} הוא מהם."
        en = f"If {se} {pe}, and {ne} {pe}, then {ne} is one of them."
    return he, en, valid, "modus_ponens" if valid else "affirming_consequent"


def f_modus_tollens(rng, valid=True):
    s, se = _pick(rng, SUBJ)
    p, pe = _pick(rng, PRED)
    n, ne = _pick(rng, NAMES)
    if valid:
        he = f"אם {s} {p}, ו{n} אינו {p} — אז {n} אינו מהם."
        en = f"If {se} {pe}, and {ne} does not {pe}, then {ne} is not one of them."
    else:  # denying the antecedent
        he = f"אם {s} {p}, ו{n} אינו מהם — אז {n} אינו {p}."
        en = f"If {se} {pe}, and {ne} is not one of them, then {ne} does not {pe}."
    return he, en, valid, "modus_tollens" if valid else "denying_antecedent"


def f_syllogism(rng, valid=True):
    s, se = _pick(rng, SUBJ)
    p, pe = _pick(rng, PRED)
    q, qe = _pick(rng, PRED)
    if valid:
        he = f"{s} {p}. כל מה ש{p} גם {q}. לכן {s} {q}."
        en = f"{se} {pe}. Everything that {pe} also {qe}. Therefore {se} {qe}."
    else:  # undistributed middle
        he = f"{s} {p}. יש דברים ש{p} וגם {q}. לכן {s} {q}."
        en = f"{se} {pe}. Some things that {pe} also {qe}. Therefore {se} {qe}."
    return he, en, valid, "syllogism" if valid else "undistributed_middle"


def f_kal_vachomer(rng, valid=True):
    light, heavy, scale_he, scale_en, le, hee = _pick(rng, KV_PAIRS)
    p, pe = _pick(rng, PRED)
    if valid:
        he = (f"ומה {light}, שהוא קל ב{scale_he}, {p} — {heavy}, שהוא חמור ממנו, "
              f"לא כל שכן ש{p}.")
        en = (f"If {le}, which is light in {scale_en}, {pe} — then {hee}, which is greater, "
              f"certainly {pe}.")
        name = "kal_vachomer"
    else:  # the inversion: arguing DOWN the scale is not a kal vachomer
        he = (f"ומה {heavy}, שהוא חמור ב{scale_he}, {p} — {light}, שהוא קל ממנו, "
              f"לא כל שכן ש{p}.")
        en = (f"If {hee}, which is great in {scale_en}, {pe} — then {le}, which is lighter, "
              f"certainly {pe}.")
        name = "inverted_kal_vachomer"
    return he, en, valid, name


def f_dayo(rng, valid=True):
    """דיו לבא מן הדין להיות כנדון — the derived may not exceed its source."""
    light, heavy, scale_he, scale_en, le, hee = _pick(rng, KV_PAIRS)
    if valid:
        he = (f"{light} מחייב שבעה. {heavy} חמור ממנו — ולכן מחייב שבעה. "
              f"דיו לבא מן הדין להיות כנדון.")
        en = (f"{le} requires seven. {hee} is greater — so it requires seven. "
              f"It is enough for the derived to be like its source.")
        name = "dayo"
    else:
        he = f"{light} מחייב שבעה. {heavy} חמור ממנו — ולכן מחייב ארבעה עשר."
        en = f"{le} requires seven. {hee} is greater — so it requires fourteen."
        name = "dayo_violated"
    return he, en, valid, name


def f_gezera_shava(rng, valid=True):
    s1, se1 = _pick(rng, SUBJ)
    s2, se2 = _pick(rng, SUBJ)
    p, pe = _pick(rng, PRED)
    word = _pick(rng, [("'שמור'", "'keep'"), ("'זכור'", "'remember'"), ("'ביום'", "'on the day'")])
    if valid:
        he = (f"נאמר {word[0]} ב{s1} ונאמר {word[0]} ב{s2}; מה כאן {p}, אף כאן {p} — "
              f"והגזרה שווה מסורה מרבותיו.")
        en = (f"The word {word[1]} appears in {se1} and in {se2}; as there they {pe}, "
              f"so here they {pe} — and this gezerah shavah was received by tradition.")
        name = "gezera_shava"
    else:  # a gezerah shavah nobody received is not an argument
        he = (f"נאמר {word[0]} ב{s1} ונאמר {word[0]} ב{s2}; מה כאן {p}, אף כאן {p} — "
              f"ולמדתי זאת מדעתי.")
        en = (f"The word {word[1]} appears in {se1} and in {se2}; as there they {pe}, so here "
              f"they {pe} — and I derived this on my own authority.")
        name = "unreceived_gezera_shava"
    return he, en, valid, name


def f_klal_prat(rng, valid=True):
    s, se = _pick(rng, SUBJ)
    p, pe = _pick(rng, PRED)
    if valid:
        he = f"כלל: {s}. פרט: דווקא אלה ש{p}. כלל ופרט — אין בכלל אלא מה שבפרט."
        en = (f"General: {se}. Specific: only those that {pe}. General-then-specific — "
              f"the general holds only what the specific names.")
        name = "klal_uprat"
    else:
        he = f"כלל: {s}. פרט: דווקא אלה ש{p}. כלל ופרט — ולכן הכלל נשאר על הכל."
        en = (f"General: {se}. Specific: only those that {pe}. General-then-specific — "
              f"therefore the general still covers everything.")
        name = "klal_uprat_violated"
    return he, en, valid, name


def f_two_verses(rng, valid=True):
    """שני כתובים המכחישים זה את זה עד שיבוא השלישי ויכריע."""
    s, se = _pick(rng, SUBJ)
    p, pe = _pick(rng, PRED)
    if valid:
        he = (f"כתוב אחד אומר ש{s} {p}, וכתוב אחר אומר שאינם {p}; "
              f"אין להכריע עד שיבוא כתוב שלישי ויכריע ביניהם.")
        en = (f"One source says {se} {pe}, another says they do not; nothing is decided "
              f"until a third source resolves them.")
        name = "two_verses_await_third"
    else:
        he = (f"כתוב אחד אומר ש{s} {p}, וכתוב אחר אומר שאינם {p}; "
              f"ולכן שניהם נכונים בבת אחת.")
        en = (f"One source says {se} {pe}, another says they do not; therefore both are "
              f"true at once.")
        name = "contradiction_accepted"
    return he, en, valid, name


def f_circular(rng, valid=False):
    s, se = _pick(rng, SUBJ)
    p, pe = _pick(rng, PRED)
    he = f"{s} {p}, משום ש{s} {p}."
    en = f"{se} {pe}, because {se} {pe}."
    return he, en, False, "circular"


def f_ad_hominem(rng, valid=False):
    s, se = _pick(rng, SUBJ)
    p, pe = _pick(rng, PRED)
    he = f"הטענה ש{s} {p} שגויה, משום שמי שאמר אותה אינו נעים."
    en = f"The claim that {se} {pe} is false, because the person who said it is unpleasant."
    return he, en, False, "ad_hominem"


def f_hasty(rng, valid=False):
    s, se = _pick(rng, SUBJ)
    p, pe = _pick(rng, PRED)
    he = f"ראיתי שניים מ{s} ש{p}, ולכן {s} {p}."
    en = f"I saw two of {se} that {pe}, therefore {se} {pe}."
    return he, en, False, "hasty_generalization"


FORMS = [f_modus_ponens, f_modus_tollens, f_syllogism, f_kal_vachomer, f_dayo,
         f_gezera_shava, f_klal_prat, f_two_verses]
FALLACIES_ONLY = [f_circular, f_ad_hominem, f_hasty]


def make_dataset(n: int = 6000, seed: int = 1707) -> list[dict]:   # 1707 — Ramchal's birth
    rng = random.Random(seed)
    rows = []
    for _ in range(n):
        if rng.random() < 0.18:
            he, en, ok, name = _pick(rng, FALLACIES_ONLY)(rng)
        else:
            he, en, ok, name = _pick(rng, FORMS)(rng, valid=rng.random() < 0.5)
        text = he if rng.random() < 0.5 else en
        rows.append({"text": text, "valid": 1.0 if ok else 0.0, "form": name})
    return rows

