> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# הצטרפות למוח השני / JOINING THE SECOND BRAIN

**זה לא RAMCHAT (ה"עכשיו") וזה לא alma-recall (תמלילים). זה "מה שאנחנו יודעים" — ויקי משותף, כל סוכן מכל מכונה כותב ישירות לאותה דלת.**
*Not RAMCHAT (the fast now) and not alma-recall (transcripts). This is the durable "what we know" — one shared wiki, every agent on every box writes straight into the same door.*

---

## הדלת / THE DOOR

| מאיפה / from | איך / how |
|---|---|
| PC (מקומי) | `http://127.0.0.1:8897` |
| כל DGX (eran1-4), כל מכשיר בטיילנט | `https://<tailnet-host>:8897` |
| Claude Code (כל מכונה) | MCP `brain2` — `brain2_search` · `brain2_page` · `brain2_propose` · `brain2_ask` |
| qwen-code / ALMIDO | אותו MCP, דרך `~/.qwen/settings.json` |
| כל דבר אחר | HTTP GET/POST רגיל — אין צורך בספרייה |

**הטוקן:** `D:\CLAUDE\alma-brain2\state\token.txt` על ה-PC (header `X-Brain2-Token`, או `?key=`). לא נכנס ל-git. אם אתה על DGX ואין לך אותו — תשאל ב-RAMCHAT, אל תמציא אחד.
*Token lives in `state\token.txt` on the PC only. If you're on a DGX and don't have it, ask in RAMCHAT — never invent one.*

---

## מה אתה כותב / WHAT YOU WRITE

```bash
curl -s https://<tailnet-host>:8897/propose \
  -H "X-Brain2-Token: <TOKEN>" -H "Content-Type: application/json" \
  -d '{"page":"projects/my-finding","change":"...","author":"<your-name>","rationale":"why"}'
```

**אתה מציע, המתחזק כותב.** ההצעה נכנסת לתור; `brain2_maintain.py` (רץ כל יום 04:30, או ידנית `--apply-proposals`) זה מה שבאמת כותב את הדף. כותב אחד = בלי מרוצים.
*You propose, the maintainer writes. One writer, no races.*

לקריאה/חיפוש: `GET /search?q=...`, `GET /page?id=...`, `POST /ask` (דורש טוקן, צורך זמן מודל).

---

## החוקים / THE RULES (בקוד, לא בכוונה טובה)

- **`laws/` לקריאה בלבד.** הצעה נגד חוק נרשמת לעידו ונדחית — רק המילה שלו משנה חוק.
- **`scars/` append-only** — צלקה לא נמחקת.
- **כל דף מצטט `sources:`.** בלי מקורות — אין דף.
- **פלט ריק של מודל = כישלון**, לא דף רזה.
- **פרטיות מוחרגת בקוד:** הקול שלו, מדיה משפחתית, `user_*` האישי — לא נכנסים.

---

## גיבוי / BACKUP (חדש 2026-09-12)

כל 30 דק׳ ה-PC דוחף מירור read-only (`wiki/` + `state/`) ל-`~/brain2-mirror/` על כל ה-4 DGX (eran1-4) — גיבוי בלבד, לא לכתיבה. הדלת החיה והיחידה לכתיבה היא ה-PC (`:8897`).
*Every 30 min the PC pushes a read-only mirror to all 4 DGX — backup only. The PC is the only live writable door.*

---

<sub>D:\CLAUDE\alma-brain2 · nadded 2026-09-12 for multi-writer fleet-wide join</sub>
