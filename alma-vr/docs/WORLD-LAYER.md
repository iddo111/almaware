# 🪟 BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

# The World layer — where ALMA stops being a language and becomes an engine

**Iddo, 2026-08-28:** *"שפת עלמה צריכה לאפשר לכל כותב לכתוב כמו שכותבים נוירונים
ומשקלים ביניהם. גם מנוע עלמה יהיה בדיוק כמו גודוט רק טוב יותר ומאפשר יותר קישוריות
וקווסטים — לא רק גרפיקה, גם יחסים. מנוע משחק מלא."*

Then, 2026-08-28 16:16, one word: **`vr`**.

---

## The one claim

> **Godot models a game as a tree. A game is a graph.**

A Godot scene is parent → child → child. That is correct for drawing and wrong for
relationships: two siblings who must affect each other are wired by hand through
signals, and "who trusts whom" has nowhere to live except script.

ALMA already models a graph, and it is the graph a game needs:

| ALMA (SPEC.md) | in a world |
|---|---|
| **knot** | a thing — a person, a component, a place, a lock |
| **strand weight** | a relation — how much A trusts B; whether a wire conducts |
| **strand delay** | distance — news travels; current does not arrive first |
| **knot trigger** (`rise x`) | a threshold — he speaks only if enough reaches him |
| **fringe knot** | an outcome you can read — a lamp, a rumour, a witness |

## What was built (2026-08-28)

`alma-language/alma/world.py` — ~120 lines, **no new physics.** A naming layer over
`alma.loom` with five methods: `thing`, `ear`, `bond`, `set_bond` / `nudge`, `tell`.

`alma-language/tests/test_world.py` — 11 tests. **Suite: 47/47 passing.**

## The proof, and it is literal

Two worlds. Same five methods. `world.py` never learns which one it is running.

```python
def alley():                            def radio():
    w = World("alley")                      w = World("radio")
    w.thing("shmulik"); w.thing("rachel")   w.thing("battery"); w.thing("coil")
    w.thing("templar"); w.ear("rumour")     w.thing("aerial");  w.ear("speaker")
    w.bond("shmulik", "rachel",  0.8)       w.bond("battery", "coil",   1.0)
    w.bond("shmulik", "templar", 0.2)       w.bond("battery", "aerial", 0.0)  # cut
```

- `alley().tell("shmulik")` → `rumour: [0.8]` — Rachel passes it on, the Templar
  does not: 1.0 × 0.2 never clears his `rise 0.5`.
- `radio().tell("battery")` → `speaker: [1.0]` — one path only; the aerial lead is cut.
- **`set_bond(a, b, 0.7)` raises the ear by exactly 0.7 in BOTH worlds.**
  A favour and a soldering iron are the same move on the same graph.

## What the engine taught us while we wrote it

Two paths arriving on the same beat do **not** produce two readings — the fringe
gathers them into one, louder. `[1.0, 1.0]` was the guess; `[2.0]` is the truth.
Strength adds. The first test expectations were wrong and were corrected to what
the loom actually does, not the other way round.

## It is already walkable

`alma-vr/godot/weaves/alley.json` — exported through the existing bridge
(`alma/godot.py` → `scripts/alma_weave.gd`, see `WEAVE-BRIDGE.md`): 4 knots, a
deterministic 3D layout, and a 5-event trace. Open `alma_weave.tscn` and walk into
the alley; the sparks travel the cords on the beats the loom says they travel.

```
cd D:\CLAUDE\alma-language
python -m unittest discover -s tests          # 47/47
```

## What is NOT built — say it plainly

- No NPC yet speaks *from* a bond. `bridge/npc.py` talks to the fleet; nothing
  connects the fleet's answer to `bond_of()`. That is the next honest step.
- No minigame UI. The circuit is proven as data, not as something you touch.
- Quests are not modelled. A quest is a bond that must cross a threshold — the
  primitive is there, the vocabulary is not written.
- **This is not "Godot but better."** Godot draws, simulates and imports; ALMA
  holds the graph. Ten years of renderer are not being rewritten and do not need to be.

Related: [[WEAVE-BRIDGE]] · [[GAME-DESIGN]] · [[NPC-SHMULIK]] · [[VAULT-MINIGAME]] ·
`alma-language/SPEC.md`
