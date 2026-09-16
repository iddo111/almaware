> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY. Test the REAL output, not a proxy.

# NEEDS-IDDO — המיק לא מקליד לחלונות מנהל / the mic cannot type into ADMIN windows (2026-09-06)

1. **מה קרה:** חלון ה-Claude CLI של הבוקר נפתח "כמנהל" (Administrator). ווינדוס (UIPI) זורק בשקט כל הקלדה מאפליקציה רגילה לחלון כזה — קשב לא יכול להקליד לשם, ואף אחד לא יכול. / **What happened:** this morning's Claude CLI window was opened elevated; Windows (UIPI) silently drops keystrokes from a normal app into it — KESHEV cannot type there, nothing can.
2. **מה תוקן היום:** קשב מזהה חלון כזה, מסרב להקליד, ומראה באנר אדום דו-לשוני + שורה "נחסם" בטבלה במקום "הוקלד". / **Fixed today:** KESHEV detects it, refuses, shows a bilingual red banner and counts the sentence as נחסם, not הוקלד.
3. **דרך א' (בוצעה):** קיצור דרך חדש על שולחן העבודה — **"Claude CLI - מיק"** — פותח Claude Code בחלון רגיל (לא מנהל); המיק מקליד לתוכו. אל תפתח CLI מ-PowerShell "כמנהל" (Win+X). / **Way (a) — DONE:** new Desktop shortcut **"Claude CLI - מיק"** opens Claude Code non-elevated; the mic types into it. Never launch a CLI from an admin PowerShell (Win+X).
4. **דרך ב' (ההחלטה שלך):** להריץ את קשב עצמו כמנהל. המחיר: המיק מחזיק הרשאות מנהל כל היום, ומקליד גם לחלונות מנהל. לא בוצע — רק אתה מחליט. / **Way (b) — YOUR call:** run KESHEV itself as Administrator. Tradeoff: the mic holds admin rights all day and types into admin windows too. NOT done — only you decide.
5. החלון המורם של הבוקר (hwnd 2362548, WindowsTerminal pid 23460) עדיין פתוח — סגור אותו ופתח מהקיצור החדש. / The morning's elevated window (hwnd 2362548, WT pid 23460) is still open — close it and use the new shortcut.

6. **אזהרה שנמדדה היום (17:00):** אם הפוקוס על **שולחן העבודה** כשאתה מדבר, ה-Enter של המיק מפעיל את הסמל המסומן — ראיתי את הקיצור החדש נפתח שוב ושוב ככה. דבר לתוך חלון, לא לשולחן העבודה. / **Measured today (17:00):** if the DESKTOP has the focus while you speak, the mic's Enter launches the selected icon — I watched the new shortcut relaunch itself repeatedly. Speak into a window, never the desktop.
