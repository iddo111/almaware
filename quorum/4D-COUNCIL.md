> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working).

# 4D-COUNCIL — מועצת ארבעת ה-DGX · the four DGX minds arguing

לזכרה של עלמה ז״ל · wired and proven 2026-08-17

## איך מפעילים · How to start (one command)

```powershell
cd D:\CLAUDE\quorum; .\run-quorum.ps1 -Enable
```

ואז נפתחים בדפדפן · then open: **http://127.0.0.1:8099**

כותבים שאלה, מסמנים את ארבעת מודלי ה-4D (הם מסומנים כברירת מחדל), ולוחצים התחל.
Type a question, keep the four 4D models ticked (they are ticked by default), start.

## מי במועצה · Who is in the council

All four go through the **ONE router** on eran1 (alma-router v3, :8010) — the
model name selects the box:

| model | box | per-turn speed (measured 17.08) |
|---|---|---|
| `qwen3-coder-next-fp8` | eran1 | 1–8s — fastest |
| `glm-4.7-flash` | eran2 | 5–25s |
| `gpt-oss-120b` | eran4 | 4–13s |
| `nemotron-3-super` | eran3 | 19–72s — slowest (thinks first) |

Headless (no browser) · בלי דפדפן:

```powershell
cd D:\CLAUDE\quorum
$env:QUORUM_ENABLED="1"
python run_debate.py "השאלה שלך" --rounds 1 --models qwen3-coder-next-fp8 glm-4.7-flash nemotron-3-super gpt-oss-120b
```

## חוק ההכרעה · The decision protocol (Iddo's order, 17.08.2026)

**אין דמוקרטיה. הדיון מייעץ — המלך פוסק.** No democracy. The debate is ADVISORY.

1. ארבעת מודלי ה-4D הם **עובדים** (workers). Claude (הסשן המנצח) הוא **המלך** (king).
2. כל מועצה **חייבת** להסתיים בשורת `מסקנה:` אחת — זו ההמלצה למלך.
   דיון שנגמר בלי שורת `מסקנה:` הוא **ריצה כושלת** — run it again.
3. המלך (הסשן המתזמר של Claude) קורא את המסקנה ומוציא **פסק** אחד מחייב.
   The orchestrating Claude session reads the מסקנה and issues ONE binding פסק.
   Stuck-without-a-decision is forbidden — a council always ends in a ruling.

## מי כותב את המסקנה · Who writes the מסקנה

**Nominated: `qwen3-coder-next-fp8`** — the fastest reliable model (1.2s on a
one-line answer, no thinking-channel budget risk). This is already encoded in
`config.SYNTH_PREFERENCE`: when only the four fleet models debate, qwen writes
the closing מסקנה automatically. (nemotron writes the best prose but is 10–60x
slower; speed wins for the closer because the מסקנה is advisory anyway — the
king's פסק is the real decision.)

## הוכחה · Proof it works

First real council ran 2026-08-17: all four admitted with real non-empty turns,
Round 0 עמדות + Round 1 שקלא-וטריא (a genuine 2-vs-2 מחלוקת with explicit
concessions) + מסקנה + פסק, 182s total. Transcript: `_transcript-4D-first-council-20260817.md`
in the quorum folder.

## אם משהו שבור · If something is broken

- `GET http://<lan-ip>:8010/fleet` must list 4 backends. Router down ⇒ no council.
- The router URL lives in `state\settings.json` (`fleet_router_url`), env
  `QUORUM_FLEET_ROUTER_URL` overrides.
- QUORUM stays born-inert: without `-Enable` / `QUORUM_ENABLED=1` /
  `enabled:true` in settings, no model is ever contacted.
