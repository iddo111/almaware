# -*- coding: utf-8 -*-
"""מי אתה עכשיו — the identity block the window's brain gets every turn.

2026-09-12 03:2x. Iddo, about his own app: "הוא לא יודע איזה מודל הוא."
He was right — nothing in the prompt ever told the model which model it was,
so it guessed, and sometimes guessed that it was Claude. One short block,
built from THIS window's live settings, fixes it.

2026-09-15, harnessswarm: BRAIN_FACTS used to be its own hand-kept dict here,
a second copy of facts coder_desktop.py's BRAINS table also knew (drifted
twice already — appqa 2026-09-15 found two brains missing from this dict).
FIVE LAWS #1 (2026-09-14): one source of truth beats a fresher private copy.
coder_brains.py is now that one source; this file only reshapes it into the
{model: (name, where)} lookup identity_line() has always used. The only
import here is the sibling module in this same folder — still no network, no
other I/O, and the import is wrapped so a broken coder_brains.py can never
take this function down with it (it is called on every turn).
"""

try:
    import coder_brains as _brains
    BRAIN_FACTS = {b["model"]: (b["human_name"], b["where_he"])
                   for b in _brains.all_brains()}
except Exception:
    BRAIN_FACTS = {}

_TEMPLATE = (
    "אתה רץ כרגע כ**{name}** (מזהה המודל: `{model}`), {where}.\n"
    "הדלת שדרכה אתה עונה: {door}\n"
    "אם עידו שואל איזה מודל אתה, זו התשובה — אל תנחש ואל תמציא. "
    "אתה לא Claude ולא ChatGPT, ואתה לא יודע דברים שהם יודעים אלא אם הם כתובים לך כאן."
)


def identity_line(settings, default_model="", default_door=""):
    """One short Hebrew block naming the live brain. Never raises."""
    try:
        settings = settings or {}
        model = settings.get("model") or default_model or "?"
        door = settings.get("door") or default_door or "?"
        name, where = BRAIN_FACTS.get(model, (model, "מוגש מהדלת שלמטה"))
        return _TEMPLATE.format(name=name, model=model, where=where, door=door)
    except Exception:
        return ""
