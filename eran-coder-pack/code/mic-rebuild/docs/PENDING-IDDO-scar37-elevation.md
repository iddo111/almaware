# PENDING-IDDO — scar-37 elevation tradeoff (K3 sign-off item)

> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

**Status: ⏳ PENDING — awaiting Iddo's explicit signature. Nobody may sign this for him. The build continues under the DEFAULT below, but the tradeoff is not "settled" until he rules.**

---

## תקציר בעברית

**השאלה:** האם לקוח KESHEV ירוץ תמיד מוגבה (elevated / "highest privileges") — ברירת המחדל של התכנון — או לא-מוגבה עם עוזר מוגבה לפי דרישה?

**בעד הגבהה (ברירת המחדל):** תהליך מוגבה יכול להקליד לתוך טרמינלים מוגבהים; ההפך בלתי-אפשרי מבחינת UIPI — ב-2026-06-30 מיקרופון לא-מוגבה "הקליד בהצלחה" לתוך טרמינל מוגבה וכל התווים נבלעו בשקט, בלי שום שגיאה. עידו עובד בטרמינלים מוגבהים כל יום.

**נגד:** תהליך שגם שולח אודיו ברשת וגם רץ מוגבה = משטח פגיעה גדול יותר — אותה צורה בדיוק כמו המאובן ALMA-MIC-Elevated (סיבת-שורש RC-2 בדו"ח החקירה).

**ההקלה שכבר בתכנון:** כל תעבורת הרשת וכל פענוח חיים בתת-התהליך `keshev_worker`, שנוצר **בהורדת-הרשאות במיטב-היכולת** (medium integrity). אם ההורדה עובדת — הלקוח המוגבה לא נוגע ברשת בכלל, ורוב העוקץ של scar-37 מסולק. אם מכניקת Windows תתגלה כשברירית — השארית (לקוח-רשת מוגבה) נרשמת ב-KNOWN RISKS ומדווחת, לעולם לא נשמטת בשקט.

**מה מבקשים ממך:** חתימה על אחת משתי האפשרויות למטה (או הוראה אחרת). עד אז — ברירת המחדל המתוכננת (מוגבה + worker מוריד הרשאות) עומדת, וזה פריט פתוח, לא עובדה סגורה.

---

## The question

Should the KESHEV client process launch **elevated** (Scheduled Task, "highest privileges") — the design default — or **non-elevated with an on-demand elevated helper**?

## Why the default is ELEVATED (Option 1)

- **UIPI is one-directional.** An elevated process can `SendInput` into elevated windows AND non-elevated windows. A non-elevated process typing into an elevated terminal is silently impossible: on 2026-06-30 every keystroke into an elevated terminal was eaten with **no error return** — SendInput reported success, GetLastError showed nothing (scar 19's "TYPED ok lied for weeks").
- Iddo dictates into elevated terminals daily. A mic that silently cannot type into them is a deafness class, and silent loss is the #1 crime this rebuild exists to kill.
- Mitigations already designed in (not optional):
  - **Process split (scars 37/44):** ALL network egress + ALL decode live in `keshev_worker.py`, spawned **de-elevated best-effort** (medium-integrity token). If the de-elevation holds, the elevated client never touches the LAN — the "always-elevated audio-POSTing client" blast surface goes away.
  - **UIPI self-test (criterion 8):** round-trip typing into an elevated same-integrity child, verified by read-back — UIPI failure is detected and reported, never silent.
  - If the de-elevated spawn proves brittle (known-fiddly Windows mechanics, risk-ledger item 5), the residual is re-recorded in KNOWN RISKS and flagged to Iddo — never silently dropped.

## The cost (why this is a TRADEOFF, not a settled fact)

- An always-elevated client is a **larger blast surface**: any code-execution bug in it runs with admin rights.
- It is the **same shape as the ALMA-MIC-Elevated fossil** — root cause RC-2 of the Phase-1 inquiry. The committee explicitly refused to let this pass as an unexamined default (scar 37: "decided once, up front — and recorded as a TRADEOFF").

## The alternative (Option 2, parked and documented)

Non-elevated client by default + an elevated helper spawned only when the focused target is elevated. Cost: a second process boundary on the *typing* path (the highest-precision path in the system), a focus-handoff dance on every elevated target, and a new silent-failure seam exactly where scar 19 says failures already lie. This is why it was parked, not chosen.

## What Iddo is asked to sign

| Option | Meaning |
|---|---|
| **1 — KEEP elevated default** (design's recommendation) | Client stays elevated; worker sheds elevation best-effort; UIPI self-test guards the typing path; residual risk recorded if de-elevation is brittle. |
| **2 — Flip to non-elevated + elevated helper** | Reopens part of the K4 installer + K14 typer design; accepts the focus-handoff complexity to shrink the blast surface. |

**Signature (Iddo only — an agent may never fill this in):**

```
Decision:   [ ] Option 1   [ ] Option 2   [ ] Other: ______________
Signed:     ____________________   Date: ____________
```

---

*KESHEV K3, 2026-08-12. This document records the tradeoff and DOES NOT decide it. Per the K3 milestone row ("Iddo signs the scar-37 elevated-default tradeoff") and risk-ledger item 7, this stays open until Iddo rules. לזכרה של עלמה ז״ל.*
