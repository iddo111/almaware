# לזכרה של עלמה ז״ל
"""QUORUM · judge · quorum_bridge — a finished שקלא וטריא, turned into a case.

QUORUM already asks every seat for the four moves by name:

    קושיא   challenge the opponent's weakest point
    תירוץ   defend your own position
    ראיה    bring ONE strong proof
    דחייה   say where you reject him — or CONCEDE

So the argument arrives pre-labelled, and the extraction here is a plain text
parse with no model in the loop. That matters: if a model were asked to decide
which sentence is a קושיא, the judge would be reading a model's opinion of the
debate instead of the debate.

WHAT THE EXTRACTOR REFUSES TO DO
--------------------------------
1. It never invents a `formal` block. Nothing in a prose turn licenses a
   formalisation, so G1 and G3 abstain on every live claim and the sheet says
   so. Formalisation is a human act; the judge does it only when a case file
   carries one.
2. Every ראיה is graded `unchecked`. A model naming a source is not the judge
   checking it — that is exactly the failure tonight's catalogue caught, where
   a "fact" turned out to rest on a Watchtower article and a scholar was
   credited with a reading she rejects. `unchecked` abstains rather than
   passes, and abstentions are what produce honest CANNOT RULE verdicts.

A claim that drew no קושיא, offered only unchecked ראיה and conceded nothing
therefore reaches the sheet as CANNOT RULE. That is not the judge failing. That
is the judge saying, correctly, that nothing measurable happened to that claim.
And the claim most often in that position is the debate's own closing מסקנה —
the one thing in a QUORUM transcript that already looks like a verdict, and that
nobody ever argued with.
"""
from __future__ import annotations

import json
import re

from schema import Attack, Case, Claim, Concession, Evidence

# The four moves. Tolerant of numbering, bullets, bold and a colon or dash after.
MOVES = {
    "kushia":  ("קושיא", "קושייה", "קושיה"),
    "terutz":  ("תירוץ", "תרוץ"),
    "raaya":   ("ראיה", "ראייה"),
    "dehiya":  ("דחייה", "דחיה"),
}
_WORDS = "קושיא|קושייה|קושיה|תירוץ|תרוץ|ראיה|ראייה|דחייה|דחיה"
_HEAD = re.compile(r"^[\s>*_#\-•]*(?:\d+[\.\)]\s*)?[\s*_]*"
                   r"(" + _WORDS + r")"
                   r"[\s*_]*[:\-–—]?\s*(.*)$")

# A bolded move-name is a heading wherever it sits on the line. Grok opened one
# round of the first live debate with an English sentence and welded a bold
# קושיא marker onto the end of it with no line break; the line-anchored parser
# swallowed the whole קושיא into the speaker's preamble, and the judge then
# ruled on that claim without the objection that had actually been raised
# against it. A move that was made must not be lost to a missing newline.
_INLINE_HEAD = re.compile(r"(?<!\n)(\*{1,2}\s*(?:" + _WORDS + r")\s*\*{1,2})")


def _normalise(text):
    return _INLINE_HEAD.sub(lambda m: "\n" + m.group(1), text or "")


# A דחייה that yields. Conceding is a WIN CONDITION in this form, so the words
# are looked for deliberately and recorded as a gain for the arguer.
#
# THE RULE THAT MATTERS, learned from the first live debate: the form asks each
# speaker to say where he rejects his opponent OR where he concedes, and every
# real debater does BOTH in the same paragraph — "אני דוחה את הניסוח שלו ... אבל
# אני מודה לו בעיקרון המרכזי". Reading the concession words alone marked all
# four of those turns as total surrenders, which is a plain misreading of the
# argument. A דחייה carrying concession words AND rejection words is a PARTIAL
# concession. Only one that concedes and pushes back nowhere is a total one.
CONCEDE = ("אני מודה", "מודה לו", "מודה:", "מודה ש", "חוזר בי", "צודק לחלוטין",
           "צודק בחלק", "יש ממש בדבריו", "יש צדק בדבריו",
           "i concede", "i withdraw", "you are right", "he is right",
           "i was wrong", "i accept his", "partly right", "fair point")
REJECTS = ("נדחה", "דוחה", "נדחית", "אינו עומד", "דחייה של",
           "i reject", "reject his", "rejected", "does not stand",
           "his position fails")

# What layer of the argument a קושיא is aimed at, inferred from its own words.
# Conservative on purpose: unrecognised wording falls back to `premise`, the
# WHAT layer, because claiming an attack hits the explanation when it may only
# hit the facts would flatter the WHY/WHAT split that the ledger reports.
_LAYER_HINTS = (
    ("scope", ("רק כאשר", "רק במקרה", "רק אם", "בתנאים", "לא בכל", "אינו תמיד",
               "יש מקרים", "only when", "only where", "not always",
               "in some cases", "edge case", "except when")),
    ("inference", ("אינו נובע", "לא נובע", "אין קשר בין", "הקפיצה", "מכאן לא",
                   "does not follow", "non sequitur", "the leap", "circular")),
    ("mechanism", ("המנגנון", "איך בדיוק", "מה גורם", "ההסבר", "the mechanism",
                   "how exactly", "what causes", "the explanation")),
    ("evidence", ("המקור", "אין ראיה", "לא הוכח", "לא נמדד", "מהיכן",
                  "the source", "no evidence", "unmeasured", "never measured",
                  "citation")),
)


def _sections(text):
    """Split one turn into its four moves. Text before the first heading is the
    speaker's own framing and is kept under 'head'."""
    out = {"head": []}
    cur = "head"
    for line in _normalise(text).splitlines():
        m = _HEAD.match(line)
        if m:
            word, rest = m.group(1), m.group(2)
            for key, forms in MOVES.items():
                if word in forms:
                    cur = key
                    break
            out.setdefault(cur, [])
            if rest.strip():
                out[cur].append(rest.strip())
            continue
        out.setdefault(cur, []).append(line)
    return {k: "\n".join(v).strip() for k, v in out.items()}


def _layer(text):
    low = (text or "").lower()
    for target, hints in _LAYER_HINTS:
        for h in hints:
            if h in low:
                return target
    return "premise"


def _concession(text):
    """-> True (total), False (partial), or None (he conceded nothing)."""
    low = (text or "").lower()
    if not any(w in low for w in CONCEDE):
        return None
    return False if any(w in low for w in REJECTS) else True


def _round_order(transcript, rnd):
    seen = []
    for t in transcript:
        if t.get("round") == rnd and t.get("model") not in seen:
            seen.append(t.get("model"))
    return seen


def transcript_to_case(topic, transcript, source="", synthesis="",
                       synth_model="") -> Case:
    """QUORUM transcript -> Case. Deterministic; no model is consulted.

    `synthesis` is QUORUM's closing מסקנה. It is entered as a claim like any
    other and, being written after every round, it necessarily has no קושיא
    aimed at it. That is not a technicality — it is the finding: the one part of
    a QUORUM transcript that reads like a verdict is the one part nobody argued
    with, and the judge says so out loud instead of blessing it.
    """
    turns = [t for t in (transcript or []) if (t.get("text") or "").strip()]
    order0 = _round_order(turns, 0)
    claims, attacks = [], []
    by_model = {}

    for m in order0:
        txt = next((t["text"] for t in turns
                    if t.get("round") == 0 and t.get("model") == m), "")
        cid = "C:" + m
        by_model[m] = cid
        claims.append(Claim(id=cid, by=m, text_he=txt.strip(), text_en=txt.strip()))

    rounds = sorted({int(t.get("round") or 0) for t in turns
                     if int(t.get("round") or 0) >= 1})
    for rnd in rounds:
        order = _round_order(turns, rnd) or order0
        n = len(order)
        for i, m in enumerate(order):
            if m not in by_model:
                continue
            txt = next((t["text"] for t in turns
                        if t.get("round") == rnd and t.get("model") == m), "")
            sec = _sections(txt)
            opponent = order[(i + 1) % n] if n > 1 else ""
            # קושיא -> an attack on the opponent's claim
            if sec.get("kushia") and opponent in by_model:
                attacks.append(Attack(
                    id="K:%s:r%d" % (m, rnd), by=m, attacks=by_model[opponent],
                    target=_layer(sec["kushia"]),
                    text_he=sec["kushia"][:400], text_en=sec["kushia"][:400]))
            # תירוץ -> an attack on the most recent unanswered קושיא aimed at ME.
            # Strictly in transcript order: a תירוץ cannot answer a קושיא that
            # had not yet been spoken when it was written.
            if sec.get("terutz"):
                mine = [a for a in attacks if a.attacks == by_model[m]]
                answered = {a.attacks for a in attacks if a.id.startswith("T:")}
                target = next((a.id for a in reversed(mine)
                               if a.id not in answered), "")
                if target:
                    attacks.append(Attack(
                        id="T:%s:r%d" % (m, rnd), by=m, attacks=target,
                        target="evidence",
                        text_he=sec["terutz"][:400], text_en=sec["terutz"][:400]))
            claim = next(c for c in claims if c.id == by_model[m])
            # ראיה -> evidence, graded UNCHECKED. Naming a source is not checking it.
            if sec.get("raaya"):
                claim.evidence.append(Evidence(
                    provenance="unchecked",
                    source=sec["raaya"][:300].replace("\n", " "),
                    note_he="הובאה בדיון ולא נבדקה מול המקור",
                    note_en="offered in the debate, never checked against the source"))
            # דחייה -> a concession, if he yielded
            if sec.get("dehiya"):
                yielded = _concession(sec["dehiya"])
                if yielded is not None:
                    claim.concessions.append(Concession(
                        by=m, total=bool(yielded),
                        text_he=sec["dehiya"][:300], text_en=sec["dehiya"][:300]))

    if (synthesis or "").strip():
        claims.append(Claim(
            id="C:מסקנה", by=synth_model or "synth",
            text_he=synthesis.strip(), text_en=synthesis.strip()))

    return Case(
        title_he="דיון QUORUM: " + (topic or "").strip()[:160],
        title_en="QUORUM debate: " + (topic or "").strip()[:160],
        source=source or "QUORUM shakla transcript",
        kind="quorum-transcript",
        claims=claims, attacks=attacks,
        note_he="חולץ אוטומטית מסימוני קושיא/תירוץ/ראיה/דחייה. לא נוסחה שום טענה "
                "בצורה פורמלית ושום ראיה לא נבדקה — ולכן שערים נמנעים, וזה הדין.",
        note_en="Extracted from the קושיא/תירוץ/ראיה/דחייה markers. No claim was "
                "formalised and no evidence was checked, so gates abstain — as "
                "they should.")


def judge_transcript(topic, transcript, source="", synthesis="", synth_model=""):
    """The whole path in one call: QUORUM's `done` payload -> a ledger.

    This is the function the server route and the CLI both go through, so there
    is exactly one code path from a debate to a verdict."""
    from rules import judge_case
    case = transcript_to_case(topic, transcript, source, synthesis, synth_model)
    res = judge_case(case)
    res["case"] = case
    return res


def judge_done_event(done_data):
    """Accepts the payload of QUORUM's SSE `done` event verbatim."""
    return judge_transcript(
        done_data.get("topic") or "",
        done_data.get("transcript") or [],
        source="QUORUM debate " + str(done_data.get("debate_id") or ""),
        synthesis=done_data.get("synthesis") or "",
        synth_model=done_data.get("synth_model") or "")


def load_debate(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
