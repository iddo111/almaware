"""ALMA VR — fleet NPC bridge. NPCs think on the real DGX fleet.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

Godot calls this same HTTP contract from GDScript; this module is the
reference implementation + smoke test. Pure stdlib.

Two things changed on 2026-08-28:

**1. The hardcoded router was dead and said nothing about it.** `ROUTER` pointed at
`<lan-ip>:8010` with model `qwen3-coder-next-fp8` — the Qwen 480B cluster that was
retired on 08-24 (see CLAUDE.md). The port still answers 200 on `/v1/models`, returns an
empty list, and gives **502 Bad Gateway** on the first real call. Endpoints are now a
list, tried in order, overridable by `ALMA_NPC_ROUTERS`, and a failure names every one
it tried instead of raising a bare HTTPError.

**2. The NPC now speaks FROM the graph.** `npc_say` takes a `bond` — the strand weight
between the player and this character in `alma.world` — and that number decides how much
he will say. This is the whole engine claim made audible: the relationship is not a
variable beside the dialogue, it IS the dialogue's input.

Usage:  python bridge/npc.py            # smoke: what Shmulik says at three trust levels
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

# In order. The first that answers wins. Override with ALMA_NPC_ROUTERS=a,b,c
ROUTERS = [r.strip() for r in os.environ.get(
    "ALMA_NPC_ROUTERS",
    "http://<lan-ip>:8010/v1/chat/completions,"
    "http://127.0.0.1:11434/v1/chat/completions").split(",") if r.strip()]
MODEL = os.environ.get("ALMA_NPC_MODEL", "qwen3-coder-next-fp8")

INFORMANT = """You are שמוליק, a nervous informant in a Tel Aviv shuk stall at
2am, in the game ALMA-VR. You speak Hebrew with bits of English. You know one
secret: tonight's dive target is a bank's fraud-model, and something LIVES in
it that is not the bank's. You want payment (fresh rambutan, obviously) before
you say anything real. Stay in character, 2-3 sentences, never break the
fourth wall."""


# ------------------------------------------------------------------ the bond

# What a strand weight means at the mouth. The thresholds are the same numbers a
# knot's `rise` trigger uses in alma.world — a character is a knot, and this is
# what firing sounds like.
POSTURES = (
    (0.00, "You do not trust this person at all. Deflect. Talk about fruit, "
           "prices, the heat — anything but what they asked. Give nothing."),
    (0.35, "You half-trust this person. Hint at the edges of what you know, "
           "hedge everything, and name your price before you say more."),
    (0.70, "You trust this person. Say the thing you know, plainly, and warn "
           "them what it costs you to have said it."),
)


def posture(bond: float) -> str:
    """The one line of system prompt that a relationship earns."""
    out = POSTURES[0][1]
    for threshold, text in POSTURES:
        if bond >= threshold:
            out = text
    return out


def system_for(character: str, bond: float) -> str:
    return "%s\n\nTRUST TOWARD THE PLAYER: %.2f. %s" % (
        character, bond, posture(bond))


# ------------------------------------------------------------------ the fleet

def npc_say(system: str, user_line: str, model: str | None = None,
            timeout_s: float = 60.0, routers: list[str] | None = None) -> str:
    """Ask the fleet. Tries every router in order; names all of them if none answer."""
    body = json.dumps({
        "model": model or MODEL,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user_line}],
        "max_tokens": 200,
        "temperature": 0.9,
    }).encode()
    tried = []
    for url in (routers or ROUTERS):
        req = urllib.request.Request(
            url, data=body, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as r:
                out = json.load(r)
            text = (out["choices"][0]["message"]["content"] or "").strip()
            if text:
                return text
            tried.append("%s: answered with nothing" % url)
        except (urllib.error.URLError, OSError, KeyError, ValueError) as e:
            tried.append("%s: %s" % (url, e))
    raise RuntimeError(
        "no NPC router answered. Tried:\n  " + "\n  ".join(tried) +
        "\nSet ALMA_NPC_ROUTERS / ALMA_NPC_MODEL, or bring a backend up. "
        "The 480B cluster these defaults were written for was retired 2026-08-24.")


def ask(character: str, line: str, bond: float, **kw) -> str:
    """The call a scene makes: who, what was said to them, and how much they trust you."""
    return npc_say(system_for(character, bond), line, **kw)


if __name__ == "__main__":
    ok = 0
    for trust in (0.1, 0.5, 0.9):
        print("--- trust %.1f -> %s" % (trust, posture(trust)[:52]))
        try:
            print(ask(INFORMANT, "שמוליק, אין זמן. מה מחכה לי בפנים הלילה?", trust))
            ok += 1
        except RuntimeError as e:
            print("  [no fleet] %s" % str(e).splitlines()[0])
    sys.exit(0 if ok else 2)
