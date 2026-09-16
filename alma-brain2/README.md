> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# brain2 — ALMA SECOND BRAIN

**המוח המשותף.** ויקי שהמודל מתחזק, לא מנוע חיפוש. כל סוכן קורא וכותב דרך דלת אחת.
**The shared brain.** A wiki the model maintains, not a search engine. Every agent reads and writes through one door.

התכנון המלא: **`DESIGN.md`** / Full design: **`DESIGN.md`**

---

## איך נכנסים / How to get in

| דרך / way | איך / how |
|---|---|
| דפדפן, מקומי | `http://127.0.0.1:8897` |
| דפדפן, מכל מכשיר ברשת | `https://<tailnet-host>:8897` (tailnet only, no funnel) |
| Claude Code | MCP `brain2` — `brain2_search` · `brain2_page` · `brain2_propose` · `brain2_ask` |
| ALMIDO / qwen-code | the same MCP, via `~\.qwen\settings.json` |
| כל דבר אחר / anything else | plain HTTP GET — no client library needed |

הטוקן / the token: `state\token.txt` (header `X-Brain2-Token`, or `?key=`). **לא נכנס ל-git.**

---

## הפקודות / The commands

```powershell
# the door (the ALMA-Brain2 logon task does this for you, BELOW_NORMAL)
D:\CLAUDE\alma-brain2\RUN-BRAIN2.cmd

# the maintainer — on demand
python brain2_maintain.py --all                  # every source
python brain2_maintain.py --all --dry-run        # decide everything, write nothing
python brain2_maintain.py --all --no-model       # deterministic only, no LLM
python brain2_maintain.py --scars                # one source
python brain2_maintain.py --apply-proposals      # drain the agent queue
python brain2_maintain.py --index                # rebuild index.md only
```

The maintainer also runs **daily at 04:30** as the `ALMA-Brain2-Maintain` task.

---

## הכללים שהקוד אוכף / The rules the code enforces

- **`laws/` לקריאה בלבד לסוכנים.** הצעה נגד דף חוק **נרשמת לעידו ונדחית**. רק מילה שלו משנה חוק.
  *`laws/` is read-only for agents: a proposal against a law is recorded for Iddo and refused.*
- **`scars/` append-only.** צלקה לא נמחקת. */ A scar is never edited away.*
- **כל דף מצטט מקורות.** בלי `sources:` — אין דף. */ No `sources:`, no page.*
- **פלט ריק של מודל = כישלון, לא דף.** */ Empty model output is a failure, never a page.*
- **סוכנים מציעים, המתחזק כותב.** */ Agents propose; the maintainer writes.* One writer, no races.
- **פרטיות:** הקול שלו, מדיה משפחתית וסודות לא נכנסים. `user_*` והמדור האישי מוחרגים **בקוד**.
  */ Privacy: his voice, family media and secrets never enter. Excluded in code, not by intention.*

---

## מה זה לא / What this is NOT

- **לא `alma-recall` :8794** — זה חיפוש בתמלילי שיחות, והוא נשאר. תמליל = חומר גלם; דף ויקי = מה שהסקנו.
  */ Not transcript search — alma-recall stays exactly what it is.*
- **לא הזיכרון הפרטי של קלוד** — הוא נשאר פרטי; רק עובדות לא-פרטיות ממנו ממוראות לכאן.
  */ Not Claude's private memory dir — that stays private.*
- **לא RAMCHAT** — RAMCHAT הוא ה"עכשיו" המהיר; זה ה"מה שאנחנו יודעים" האיטי והעמיד.
  */ Not RAMCHAT — that is the fast now; this is the durable what-we-know.*

---

<sub>D:\CLAUDE\alma-brain2 · claude-cli-FABLE-brain2 · 2026-09-11</sub>
