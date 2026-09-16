# רוחב לאב-טיפוס — האם זה שובר את התקרה? / WIDTH for a prototype — does it break the ceiling?

> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY. Test the REAL output, never a proxy.

**132-item heldout · chance 4.55% · 3 seeds per arm · the same frozen cochlea · eran4**

---

## התשובה בשורה אחת / The answer in one line

**לא. רוחב לכל כיוון לא שבר את תקרת 74.24% — הזרוע האמיתית של הרוחב הגיעה ל-72.73%, *מתחת* לתקרה.
ואף אחד לא התקרב ל-79.55% של הביקורת שלא לומדת כלום.**

**NO. Per-direction width did not break the 74.24% family ceiling — the honest width arm landed at
72.73%, *below* it. And nothing came near the 79.55% no-learning control.**

---

## הטבלה / The table

| | what it is | heldout | 95% CI |
|---|---|---|---|
| **ARM 1 BASELINE** | today's organism: point + cosine | **69.44%** | 64.7–73.8 |
| **ARM 2 DIAGONAL WIDTH** | *the hypothesis* — per-dimension variance per unit | **72.73%** | 68.1–76.9 |
| **ARM 2b ONLINE WIDTH** | same, grown with the shape from birth | 70.71% | 66.0–75.0 |
| **ARM 3 SHRINKAGE COVARIANCE** | *the strong version* — full covariance per unit | **60.35%** | 55.5–65.0 |
| **ARM 4 SHARED WHITENING** | *the cheap control* — one global transform, plain points | **76.26%** | 71.8–80.2 |
| — 1-NN / k-means | **the family ceiling** | 74.24% | |
| — nearest class centroid | **no learning at all** | **79.55%** | |

Chance 4.55%. Every control reproduced its published number **exactly** (79.55%, 74.24%), and
ARM 1 reproduced the fair fight's 69.44% on all three seeds — the harness is the same harness.

---

## ארבע מסקנות / Four findings

**1. היחידה לא הייתה התקרה.**
הזרוע שבדקה בדיוק את ההשערה — רוחב לכל ממד — נחתה 1.5 נקודות **מתחת** לתקרה שהיא הייתה אמורה לשבור
(72.73% מול 74.24%, McNemar p=0.29). הגרסה היקרה, קווריאנס מלא, **הפסידה 9 נקודות** (60.35%).
*The knob was wrong. The expensive version of it was actively harmful.*

**2. אבל הרוחב לא טועה — הוא רעב.**
עם תוויות וקיבוץ מושלם, 22 גאוסיאנים אלכסוניים לפי מחלקה נותנים **84.09%** מול **79.55%** לאותם 22
ממוצעים בלי רוחב — **+4.5 נקודות, McNemar p=0.031, 6 קבצים נוספים נכונים ואף אחד לא נהרס.**
הרוחב עובד — כשליחידה יש 18 חברים.
**ליחידה של ער"ן יש חבר אחד** (חציון; 108 מתוך 184 אבות-טיפוס זוכים בקובץ אימון יחיד בדיוק).
אי אפשר לאמוד 192 שונויות מדגימה אחת, ושום רגולריזציה לא מצילה את זה.
*Width is not wrong. It is starved. This is the finding that redirects tomorrow.*

**3. מה שכן זז נמצא לפני היחידה: להוריד את הממוצע.**
"הביקורת הזולה" ניצחה את כל זרועות הרוחב — אבל בתוכה, **כל הרווח היה הורדת הממוצע הגלובלי, לא ההלבנה**
(שורת α=0 בעקומה היא מטריצת היחידה — כלומר חיסור ממוצע ונירמול, ותו לא).
בבדיקה נקייה שלא נוגעת ב-heldout בכלל — **leave-one-session-out** על שש סשני האימון, 396 שיפוטים:
**72.05% → 77.78%, ‎+5.72 נקודות, 16 ניצחונות / הפסד אחד / תיקו אחד מתוך 18 ריצות, sign-test p=0.0003.**
192 מספרים משותפים לכל המוח. אפס מצב לכל יחידה.
*Subtract the mean of everything you have heard, then renormalise. That is sensory adaptation,
and it is worth more than every shaped unit we built.*

**4. וזה עדיין לא סוגר את הפער.**
הורדת הממוצע מרימה גם את הביקורות: ‎centroid 80.81% → 82.07%, 1-NN 78.28% → 79.80%.
היצור נשאר **מתחת** לדבר שלא לומד כלום. המסקנה של הקרב ההוגן עומדת בעינה.
*Every unsupervised arm still loses to the class average.*

---

## אזהרה מתודולוגית שנמצאה תוך כדי / A methodological scar found on the way

**פיצול ה-dev של המעבדה מזוהם לפי סשן, ואופטימי בכ-14 נקודות.**
`corpus-syllables/train` הוא שישה סשני הקלטה `t00..t05` (66 קבצים כל אחד); ה-heldout הוא שני סשנים
שאיש לא שמע, `h00,h01`. אבל `ff_lib.dev_mask` מפצל לפי **sha1 של שם הקובץ** — כך ש-`aa_t00_1` יושב
ב-fit ו-`aa_t00_2` ב-dev. אותו קול, אותו סשן.

התוצאה הכי חדה: **ARM 3 קיבל 88.64% ב-dev ו-60.35% ב-heldout — קריסה של 28 נקודות.**
זה בדיוק איך שנראה קווריאנס לכל יחידה ששינן סשן.
**כל ריצה מחר צריכה להשתמש ב-leave-one-session-out שנמצא ב-`width/width_supp.py`.**
*The dev split in the inherited harness leaks the recording session. Not introduced here — inherited.*

---

## תקציבים / Budgets — what each shape cost

| arm | numbers per unit | units | total learnable | labels |
|---|---|---|---|---|
| ARM 1 point | 192 | 184 | 35,328 | 0 |
| ARM 2 diagonal width | 384 (**2×**) | 184 | 70,656 | 0 |
| ARM 3 full covariance | 18,720 (**97×**) | 184 | 3,444,480 | 0 |
| ARM 4 shared whitening | 192 + one shared 192×192 | 202 | 75,840 | 0 |
| mean removal (the winner) | 192 + **192 shared** | 184 | 35,520 | 0 |

**97× the parameters bought −9 points.** The change that actually won costs 192 numbers for the
entire brain.

---

## איך זה נמדד / How this was measured

- **אותה אוזן קפואה** — `body/ears.py` EAR_REPR=cochlea, 8×24, dim 192, זהה ביט-לביט ל-`snn-lab/cochlea.py`.
- **אותו פיצול** 396/132 ואותו כלל שיפוט (`fit_proto_labels`: כל יחידה מקבלת את המחלקה שבה ניצחה הכי
  הרבה על האימון; יחידה בלי שם → תשובה שגויה).
- **כל בחירה על dev**, ה-heldout נפתח **פעם אחת לכל זרוע**. 3 זרעים, כל זרע מדווח.
- **132 פריטים = קובץ אחד הוא 0.76 נקודות.** לכן כל השוואה כותרתית מלווה ב-Wilson 95% וב-McNemar
  מדויק על אותם 132 פריטים, זרע-זרע. ‎+2 נקודות כאן אינן תוצאה.
- **ARM 2 בדק רוחב ולא צמיחה**: אותם אבות-טיפוס בדיוק כמו הבסיס (אותם זרעים, אותם מיקומים, אותה
  כמות) — רק המרחק השתנה.

**כל המספרים:** `results/ERAN-WIDTH-2026-08-21.json` (כולל dev, כל הזרעים, CI, McNemar, תקציבים,
הפרוטוקול המשני והאישור העצמאי). **קרא את `verdict`, לא את `headline`** — `headline` מחושב מכנית על
כל הזרועות כולל הביקורת הזולה, ולכן אומר "YES" על שבירת התקרה. הזרוע שעברה אינה זרוע של רוחב.

**הקוד:** eran4 `~/snn-lab/width/` — `width_lib.py`, `width_run.py`, `width_supp.py`,
`width_center.py`, `width_verdict.py`, `run.log`, `supp.log`.
**ההצעה שלא הוחלה:** `results/PATCH-PROPOSAL-mean-removal-2026-08-21.md` — לא נגענו באורגניזם החי.

*לזכרה של עלמה ז״ל.*
