# NEEDS-IDDO — sense_organ / eran2, 2026-09-06

> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

**שלוש החלטות שאני לא לוקח לבד. הקוד מוכן, שום דבר לא הופעל.**
**Three decisions I do not take alone. The code is ready, nothing was applied.**

13 מתוך 16 הליקויים תוקנו על הדיסק והוכחו (`_deliverables/code-revision/sense_organ-proofs/`).
שלושת אלה נוגעים במה שערן מקבל או במה שהאוזן שלך מחליטה — ולכן הם שלך.
*13 of 16 defects are fixed on disk and proven. These three touch what ERAN is fed or what
your ear decides, so they are yours.*

---

## SO-01 — האיבר חי אבל אף אחד לא מדבר איתו / the organ is alive and nobody calls it

**המדידה / measured.** `sense_organ.py` על eran2:8830 רץ מאז 09-02 07:44 וצרך **0.49 שניות CPU
בארבעה ימים**, 0 חיבורים פתוחים. `eran_life.py` על eran1 — **0 אזכורים** ל-8830 / eran2 /
sense_organ. גם ב-PC 0. הלקוחות היחידים: `~/babble.py` ו-`reproduce_firstlearning.py`, שניהם
לא רצים. הפה של ערן עצמו על eran1 (`voice/mouth34.py`) הוא **העתק מילה-במילה** של הצינור הזה,
עם הערה בכותרת: *"wired to nothing: there were zero references"*.
*The SENSES lobe computes its learning signal (`loop` → error) for a caller that does not exist.*

**מה זה אומר / what it means.** כל הרעיון של האיבר הוא הלולאה: ערן מכוון, הצינור מנגן, האוזן
שופטת את מה שבאמת יצא, וההפרש הוא אות הלמידה. ההפרש הזה מחושב — ונזרק. ובינתיים המסמכים
(CLAUDE.md, ה-unit, הזיכרון) קוראים לזה "האוזן והפה החיים של ערן".

**שתי דרכים — תבחר / two roads, pick one:**

| | (א) לחבר / wire it | (ב) לפרוש אותו לכלי / retire it to a tool |
|---|---|---|
| מה עושים | ב-`eran_life.py`: ping ל-`<fabric-ip>:8830` באתחול, `loop` פעם בביט, `loop_error` נכתב ל-metrics.jsonl | משאירים את היחידה כ**כלי** ומתקנים את התיאור בכל מקום |
| המחיר | נגיעה ב-eran1 — **החיים שלו**. לא נוגע בלי מילה ממך | ערן נשאר בלי לולאת שמיעה-עצמית משלו |
| הרווח | אות למידה אמיתי חוזר הביתה | אפס סיכון, והאמת חוזרת למסמכים |

בשני המקרים אני מוסיף שורת לוג לכל בקשה ומונה "כמה קריאות מאז אתחול", כדי ש**"חי" ו"בשימוש"
יפסיקו להיות אותה מילה**. *Either way: a per-request log line and a request counter, so
"alive" and "used" stop being the same word.*

---

## SO-03 — הדף אומר "חי", והיצרן מת מאז 09-02 / the page says live, the producer is dead

**המדידה / measured.** `eran-throat-listen` על :8845 כותב *"חי · מתעדכן בכל רענון"*. הוא באמת
מרענן — אבל **אין ולו worker אחד חי** של חיפוש הגרון מאז הכיבוי ב-09-02 07:41
(`pgrep arms_v3|cma|run_worker` ריק, אין tmux). ה-best.json האחרון ב-v3 הוא מ-**08-30 06:58**,
והטבלה מדפיסה `06:58` **בלי תאריך** — כך שבן שבוע נקרא כמו הבוקר.

**מוכן ליישום ברגע שתגיד / ready the moment you say go:**
1. באנר בראש הדף: *"הכתיבה האחרונה לפני N שעות — אין worker חי"*, כשהסף **נגזר** מקצב הכתיבה
   של אותה תיקייה עצמה (3× המרווח הנצפה), לא מספר שבחרתי ביד.
2. תאריך + שעה בעמודה "עודכן".
3. הכותרת נצבעת אזהרה כשהגיל > יממה.

**מה שדורש את המילה שלך:** האם **להפעיל מחדש את החיפוש**. `launch.sh:9` אומר במפורש
*"DO NOT RUN until Iddo says go"*. אני לא מפעיל. *Relaunching the search is yours to say.*

---

## SO-04 — הדף שואל אותך שאלה ואין לו איפה לקבל תשובה / the question with no answer box

**המדידה / measured.** הדף שואל את השאלה שרק אתה יכול לענות עליה — *"ba ו-ma: שני דברים או
אותו דבר פעמיים?"* — ואין **שום** דרך לרשום את התשובה: `do_GET` בלבד, אין POST, ואין קובץ
verdict אחד בכל `throat-search-v3/v4`. בינתיים `review/` אוסף **1,536 + 416 מועמדים** שאיש
לא מיין. לפי `gates_v3.py:367` **ההאזנה שלך היא הקידום היחיד** — והלולאה הזאת עוברת דרך
קלוד שעורך קוד ביד (velum, glide, burst), לא דרך הדף.

**התוכנית / the plan:**
- שני כפתורים לכל קליפ של ערן: **אותו דבר / שונה**, ועוד **"זה לא ba בכלל"**.
- `POST /verdict` → שורה ל-`~/throat-search-v3/verdicts.jsonl`: `{arm, wav sha256, verdict, ts}`.
- `run_worker.report()` קורא את הקובץ: **"לא ba" על מנצח ב-wdist = קנס קשה** (האוזן מנצחת את המדד).
- ה-pruner שכבר הותקן היום (SO-13) **כבר מכבד verdicts.jsonl** — מה שקיבל פסק דין לא מועבר לארכיון.

**מה שדורש את המילה שלך:** אוצר המילים של הפסיקה — אילו תשובות בכלל קיימות, ומה כל אחת שווה
בחיפוש. זה החוק שלך, לא שלי. *The verdict vocabulary and what each verdict is worth is yours to set.*

---

## מה נגעתי בו היום, ומה לא / what I touched today, and what I did not

* **תוקן והוכח (13):** SO-02 restart-storm backoff · SO-05 ear-said-nothing · SO-06 NaN על החוט
  ומדידה שישבה במפתח של תקלה · SO-07 seed/seconds שלא הגיעו לצינור · SO-08 לוג 12.8MB בלי רוטציה ·
  SO-09 bind ל-0.0.0.0 · SO-10 בלי timeout ובלי תקרת אורך · SO-11/12/14 דף ההאזנה ·
  SO-13 review/ בלי גיזום · SO-15 שורת החוק ב-CLAUDE.md.
* **אף תהליך לא הופעל, נעצר, או קיבל סיגנל.** eranb-life של ערן עדיין PID 120630 מ-21.8 17:19.
  התיקונים הם **רשת לאתחול הבא** — התהליכים החיים (3251, 3252) עדיין מריצים את הקוד הישן מהזיכרון.
* **גיבויים:** כל קובץ ששונה יש לו `.bak-rev-20260906` לידו.

*Nothing was restarted, stopped or signalled. Every fix is a net for the next restart; the
live processes still run the old code from memory. Backups sit beside every changed file.*
