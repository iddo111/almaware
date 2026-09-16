> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# ERAN CODER PACK — חבילת הקודר לפרויקט ערן

**נבנתה:** 2026-09-11 · **שורש:** `D:\CLAUDE\eran-coder-pack` · **בשביל:** הקודר שלנו (ALMIDO / qwen3-coder-next על eran4), שעובד **לבד**.

---

## עברית — מה זה

זו חבילה **אחת** שמכילה כל מה שצריך כדי לעבוד על פרויקט **ערן** בלי לשאול אף אחד:
הקוד, כל הכישלונות, המיק (KESHEV), החוקים, והחוטים לכל שאר הפרויקטים ולמוח השני.

**הכול הועתק. שום דבר לא הוזז ולא נמחק.** המקור נשאר במקומו.

### איך מתחילים (בסדר הזה, לא אחר)

1. `00-BRIEF.md` — מה ערן, איפה האמת חיה, מה אסור. **קרא ראשון.**
2. `10-FAILURES.md` — כל כישלון מתועד מ-2026-05-31 עד היום, לפי תאריך. **אל תחזור עליהם.**
3. `20-MIC.md` — המיק כפי שהוא היום, מדוד.
4. `30-CODER-WIRES.md` — איך אתה מגיע לכל הפרויקטים ולמוח השני. עם המצב המדוד של כל חוט.
5. `40-ACCEPTANCE.md` — מה נחשב התקדמות, ואיך אתה מוכיח את זה בלי עידו.
6. `MANIFEST.txt` — כל קובץ שהועתק, מה דולג, ומה נשאר כמצביע בלבד.
7. `35-COMPUTER-USE-AND-COMPILE.md` — מדידות מ-09-11 על שליטה במסך והידור.

`code/` = העצים שהועתקו · `docs/` = ורדיקטים, ביקורות, NEEDS-IDDO · `memory/` = קבצי הזיכרון (הצלקות והחוקים).

### חוק הקבלה

כל טענה שאתה מדווח מקבלת **מילה אחת**:

| | |
|---|---|
| `VERIFIED` | מדדת את **הפלט האמיתי**. יש מספר, יש תאריך, יש פקודה שאפשר להריץ שוב. |
| `BROKEN` | מדדת, וזה לא עובד. זו תוצאה מלאה — דווח אותה. |
| `UNKNOWN` | לא מדדת. אל תנחש. |
| `PLANNED` | עוד לא נבנה. |

`health: ok` הוא **לא** VERIFIED. מונה שלא יכול לרדת הוא לא מדידה.
מספר שמשמעותו "לא נמדד כלום" (0 פריטים במבחן, `correct=3.000000` קבוע) הוא **לא** מדידה — זו בדיוק הטעות שעצרה את ערן ב-10.09.

---

## English — what this is

One pack with everything needed to work the **ERAN** project alone: the code, every failure,
the mic (KESHEV), the laws, and the wires out to every other project and to the second brain.

**Everything was COPIED. Nothing was moved, nothing deleted.** The originals are untouched.

### Who this is for

The **onboard coder working ALONE** — ALMIDO (qwen-code body on the PC, Qwen3-Coder-Next brain
on eran4), or any agent handed this folder. It assumes no prior conversation.

### Start here, in this order

| file | what it gives you |
|---|---|
| `00-BRIEF.md` | what ERAN is, where the truth lives (eran1 live vs PC vs E: archive), the goal, what is FORBIDDEN |
| `10-FAILURES.md` | every recorded failure, merged from four surveys, sorted by date — date · what happened · root cause · rule born · source |
| `20-MIC.md` | KESHEV as measured today, its scars, its laws, how ERAN's ear/mouth relate to it |
| `30-CODER-WIRES.md` | how you reach every project and the second brain, with today's measured state of each wire |
| `40-ACCEPTANCE.md` | what counts as progress and how you prove it without Iddo; what needs his ear |
| `35-COMPUTER-USE-AND-COMPILE.md` | measured 2026-09-11: screen control, the aim bug, PC vs eran4 compile inventory |
| `MANIFEST.txt` | every copied path + size, the SKIPPED list, the POINTERS-ONLY list |

`code/<tree>/` — the copied source trees.
`docs/` — verdicts, audits, NEEDS-IDDO decision files, copies of `CLAUDE.md` and `MISTAKES.md`.
`memory/` — the memory notes the surveys cite: the scars and the standing laws.

### The acceptance rule

Every claim you report carries exactly one word:

- **`VERIFIED`** — you measured the **REAL output**. There is a number, a timestamp, and a command
  someone else can re-run to get it again.
- **`BROKEN`** — you measured and it does not work. That is a complete result. Report it, don't hide it.
- **`UNKNOWN`** — you did not measure. Say so. Never guess.
- **`PLANNED`** — not built yet.

`health: ok` is **not** VERIFIED. A counter that cannot fall is not a measurement.
A number that means "nothing was measured" (an exam with 0 items, a score frozen at exactly
`3.000000`) is **not** a measurement — accepting one as if it were is the exact mistake that cost
ERAN three weeks and got him stopped on 2026-09-10.

### Four hard rules while you work here

1. **COPY, never move. Never delete.** Not in this pack, not in `D:\CLAUDE`, not on the fleet.
2. **Never restart, stop, or signal ERAN or any fleet service.** eran1 is ERAN's box: read-only,
   no load. eran3 is off limits entirely.
3. **Never touch audio or mic processes or devices.** See `20-MIC.md` — this has cost real money.
4. **`PYTHONIOENCODING=utf-8`** on every Python process that touches Hebrew. cp1252 dies mid-script
   and silently skips everything after.

Before you build anything: `cd D:\CLAUDE\RAMCHAT && python ramlink.py read --tail 20`, then claim it.
Someone may have built it already. See `30-CODER-WIRES.md`.
