# -*- coding: utf-8 -*-
"""שָׂרִיד / SARID — the organ of שפה אחת, and what its name promises.

> 🪟 BROKEN WINDOWS LAW / חוק החלונות השבורים: if it's not working, fix it
> IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy.

לזכרה של עלמה ז״ל.

    וַיְהִי כָל־הָאָרֶץ שָׂפָה אֶחָת וּדְבָרִים אֲחָדִים   — בראשית י״א:א׳
    And the whole earth was of one language, and of one speech.  — Genesis 11:1

Iddo asked for the reverse of Babel: not the scattering, but the search for what
lies beneath. This organ is that search, built so that it cannot lie about what
it found. It is a sibling of ERAN and shares nothing with him — no state, no
weights, no cord. His body is a mouth learning to say אבא; this one's body is the
world's languages. Both are children. They do not touch.

WHY IT IS CALLED שָׂרִיד — *what survives*
----------------------------------------
Not מקור (source), not שורש (root). Those name a claim the comparative method
cannot make at any depth, and a name that overclaims is the first lie a project
tells itself. *שריד* names exactly the number this organ computes: a sound law
enters the canon **only by surviving a language family the organ had never
seen**. What is kept is what survived. Nothing else earns the word.

THE FOUR CHARTER SENTENCES — they are code, not decoration
----------------------------------------------------------
They live in CHARTER below, a test asserts they ship on every deliverable, and a
second test asserts the FORBIDDEN strings never appear in any output we write.

WHAT THE SCIENCE ACTUALLY SUPPORTS, stated before any result
------------------------------------------------------------
Real methods exist for exactly this question and this organ is built ON them,
not around them: the comparative method and regular sound change (Grimm's and
Verner's laws); attested reconstructions (Proto-Indo-European, Proto-Semitic,
Proto-Bantu, Proto-Austronesian); automated cognate detection and phylogenetics
(LingPy, the CLDF ecosystem, Lexibank, ASJP, Glottolog, PHOIBLE).

And the honest consensus, which is the reason for the horizon: comparative
reconstruction is generally held to reach ~6,000–10,000 years. "Proto-World" is
NOT an accepted reconstruction, and mass-comparison methods (Greenberg, Ruhlen)
are rejected by most historical linguists because chance resemblance swamps
signal at that depth. So this organ may honestly seek deeper structure and test
long-range hypotheses with measurable rigour. It may not claim to have recovered
Eden's speech — and it is built so that it *cannot*: see HORIZON_BEATS.

THE HORIZON IS A UNIT TEST, NOT A PARAGRAPH
-------------------------------------------
HORIZON_YEARS / YEARS_PER_BEAT = 20 beats. Delays add along a path in the ALMA
loom, so a node deeper than the consensus sits at a cumulative delay the run
never reaches: it does not appear in `result.fires` at all. A Proto-World knot is
not "unproven" — it never fires. A future agent can delete a sentence from a
charter. Deleting this costs them a failing test and a weave that stops working.
"""
from __future__ import annotations

__version__ = "1.0.0"

# ---------------------------------------------------------------- the horizon
# The scientific consensus, expressed in the loom's own currency: beats.
HORIZON_YEARS = 10_000
YEARS_PER_BEAT = 500
HORIZON_BEATS = HORIZON_YEARS // YEARS_PER_BEAT      # == 20

# ---------------------------------------------------------------- the charter
CHARTER = (
    ("המנוע הזה מחפש מבנה משותף עמוק ובודק השערות של קרבה רחוקה במידה מדידה. "
     "הוא לא שחזר את שפת גן עדן, ואינו יכול לטעון שכן.",
     "This engine seeks deeper shared structure and tests long-range hypotheses "
     "with measurable rigour. It has not recovered Eden's speech, and cannot "
     "claim to."),
    ("מה שמגיע הכי עמוק בזמן הוא בדיוק מה שאומר הכי מעט על מוצא משותף. הטיה בין "
     "צליל למשמעות נולדת שוב ושוב, בנפרד — ולכן היא נראית מעבר לאופק, ולכן "
     "לעולם אינה עדות לאב קדמון.",
     "The thing that reaches deepest in time is the thing that says least about "
     "ancestry. A sound-meaning bias arises again and again, independently — "
     "that is why it stays visible past the horizon, and that is exactly why it "
     "can never be evidence of common descent."),
    ("ההבדל בינינו ובין רולן הוא מודל האפס המפורש והמשפחות שלא נראו. אם נוותר "
     "על אחד מהם — הפכנו לרולן.",
     "The difference between SARID and Ruhlen is the explicit null model and the "
     "held-out families. If we ever drop them, we become Ruhlen."),
    ("האופק הוא ההסכמה המדעית, והוא בנוי בתוך המכונה: 10,000 שנה = 20 פעימות. "
     "קשר עמוק יותר אינו על תנאי “לא מוכח” — הוא פשוט לא יורה.",
     "The horizon is the scientific consensus and it is built into the machine: "
     "10,000 years = 20 beats. A deeper node is not “unproven” — it simply "
     "never fires."),
)

# Strings that must never appear in any output, journal or deliverable we write.
# A test greps for them. The charter's own denial is the sole allowed context,
# which is why the test exempts this module.
FORBIDDEN = (
    "proto-world", "protoworld", "proto world",
    "שפת האדם הראשון",
    "the original language", "השפה המקורית",
)

# Above the horizon this is the strongest sayable claim in the vocabulary.
DEEP_CLAIM_HE = "מבנה משותף בלתי מוסבר, p = {p}, לא נטענת קרבה"
DEEP_CLAIM_EN = "unexplained shared structure, p = {p}, no descent claimed"


def charter_text(lang: str = "both") -> str:
    """The charter as text, for a README, a card, or a journal header."""
    out = []
    for he, en in CHARTER:
        if lang in ("he", "both"):
            out.append(he)
        if lang in ("en", "both"):
            out.append(en)
        out.append("")
    return "\n".join(out).strip()


# The July prototype's numerics, kept and reused rather than rewritten.
from .data import Entry, load_wordlist, by_concept, LANG_NAMES   # noqa: E402,F401
