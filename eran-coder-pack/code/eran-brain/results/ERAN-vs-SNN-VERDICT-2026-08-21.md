# ער"ן מול SNN — הקרב ההוגן / ERAN vs the spiking net — the fair fight

> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY. Test the REAL output, never a proxy.

**132-item heldout · chance 4.55% · 3 seeds per arm · one frozen cochlea for everyone**

---

## התשובה בשורה אחת / The answer in one line

**כששניהם לומדים בלי תוויות — ער"ן מנצח: 69.4% מול 61.1%, פער של 8.3 נקודות.
אבל אף אחד מהשניים לא עובר את הביקורת שלא לומדת בכלל (79.55%).**

**When both learn with no labels, the organism WINS: 69.4% vs 61.1%, by 8.3 points.
But neither of them beats the control that does no learning at all — 79.55%.**

---

## הטבלה / The table

| | what it is | heldout |
|---|---|---|
| **בלי תוויות / UNSUPERVISED** | | |
| **ער"ן — organism** | prototypes, spawn-on-surprise + Hebbian | **69.44%** |
| **ARM A — spiking net** | LIF + STDP + WTA, 264 units | **61.11%** |
| ARM A′ — same size | the same net shrunk to 184 units | 61.62% |
| k-means (extra) | ordinary clustering, no spikes, no organism | 74.24% |
| **עם תוויות / SUPERVISED** | | |
| **ARM B — organism + readout** | prototypes + one linear layer | **81.06%** |
| **SNN (published)** | 512 LIF, surrogate-gradient BPTT | **84.09%** |
| raw cochlea + readout (extra) | the same linear layer, no organism | 83.33% |
| **ביקורת / CONTROL** | | |
| **ARM C — nearest centroid** | class average. no learning whatsoever | **79.55%** ✅ reproduced exactly |

Chance 4.55% · duration floor 5.30% · random-real-frames 46.21% · raw speech-span 53.79% · raw+loudest60 68.94%.

---

## שלוש מסקנות / Three findings

**1. הקרב ההוגן: ער"ן מנצח, והפער אמיתי.**
69.4% מול 61.1%, בכל שלושת הזרעים, וגם כשנותנים ל-SNN בדיוק אותו מספר יחידות (184) — 61.6%.
*The fair fight goes to the organism, on every seed, and it still goes to the organism when the
spiking net is shrunk to exactly the organism's own size.*

**2. אבל שניהם מפסידים למשהו שלא לומד.**
נקודת מרכז של כל מחלקה — ממוצע פשוט, בלי אימון, בלי זמן — נותנת 79.55%.
כל למידה-בלי-תוויות שבדקנו נכשלת מולה. גם k-means רגיל (74.24%) מנצח את שניהם.
*Every unsupervised arm fails the control. Ordinary k-means beats both of them.
The spikes bought nothing over plain clustering; the organism bought nothing over the class average.*

**3. עם תוויות — ה-SNN עדיין מנצח, וגם הגלם.**
81.06% לער"ן מול 84.09% ל-SNN. וקריאה ישירה מהאוזן, בלי ער"ן בכלל: 83.33%.
כלומר **שכבת אבות-הטיפוס לא מוסיפה מידע — היא מאבדת כ-2.3 נקודות ממה שהאוזן כבר ידעה.**
*The organism's prototype layer does not add information to the cochlea. It loses a little of it.*

---

## שתי הפתעות / Two surprises

**62.88% לא היה התקרה של ער"ן.** אותו אלגוריתם בדיוק, כשנותנים לו לשמוע את כל 396 הקבצים
30 פעם, מגיע ל-**69.44%**. ה-62.88% של היצור החי משקף תוכנית לימודים באמצע הדרך, לא את
האלגוריתם. עקומת הגדילה: 1 מעבר → 50.5% · 3 → 63.6% · 10 → 66.9% · 30 → **69.4%**.
*The published 62.88% was not the algorithm's ceiling — it was a curriculum caught mid-climb.*

**תקרת השינון היא 74.24%.** לשמור כל צליל אימון כאב-טיפוס משלו (1-NN) נותן 74.24%,
ו-k-means מתכנס לאותו מספר בדיוק. כל משפחת אבות-הטיפוס חסומה שם — **מתחת** לביקורת.
*Any prototype/cluster method on this corpus is capped at 74.24%, below the no-learning control.
Growing more prototypes cannot fix this. It is a ceiling of the method, not of the effort.*

---

## מה זה אומר לבנות הלאה / What to build next

1. **התקרה היא הבעיה, לא קצב הלמידה.** אב-טיפוס בודד זוכר דוגמה אחת; ממוצע המחלקה
   ממצע 18 ומנקה רעש. כל עוד היחידה היא "נקודה", ער"ן חסום ב-74%.
   *The unit is the ceiling. As long as a unit is a point, no amount of living gets past 74%.*
2. **ההצעה: לתת לאב-טיפוס רוחב, לא רק מיקום** — שכל אב-טיפוס יחזיק ממוצע **ופיזור**
   (כיוונים שאין להם משמעות), לא רק וקטור. זו התיבה שהופכת אב-טיפוס לתא-מחלקה.
   בדיקה זולה: prototype + covariance, מול אותו heldout.
3. **הכימיה והשינה עדיין לא נמדדו בנפרד.** הזרוע כאן היא הליבה בלבד. אם רעש/כימיה/שינה
   מוסיפים — צריך מדידה מול ביקורת שקטה תואמת, כמו שהאמנה דורשת.
4. **ה-SNN לא נכשל — הוא פשוט לא מנצח כאן.** אל תבנה עליו לשמיעה בלי תוויות: 61%,
   מתחת ל-k-means. אם רוצים spikes, הערך שלהם הוא אנרגיה/חומרה, לא דיוק.
5. **⚠️ אזהרה: 132 פריטים.** הפרש של 8 נקודות = 11 פריטים. הפער בין ער"ן ל-SNN יציב
   בכל הזרעים, אבל אל תבנה החלטה גדולה על 2-3 נקודות בטבלה הזאת.

---

## איך זה נמדד / How this was measured

- **אוזן אחת קפואה לכולם** — `body/ears.py` (EAR_REPR=cochlea, 8×24, dim 192), זהה ביט-לביט ל-`snn-lab/cochlea.py`.
- **פיצול** 396 אימון / 132 heldout. כל בחירה נעשתה על **dev** — 88 פריטים שנחתכו מתוך ה-396,
  4 לכל מחלקה, דטרמיניסטי לפי sha1 של שם הקובץ. ה-heldout נפתח **פעם אחת לכל זרוע**, בסוף.
- **אותו כלל שיפוט לכולם** — כל יחידה מקבלת את המחלקה שבה ניצחה הכי הרבה על האימון
  (`proof/measure.py:fit_proto_labels`). יחידה בלי שם → תשובה שגויה. רשת שותקת → תשובה שגויה.
- **3 זרעים לכל זרוע**, ממוצע וכל זרע בנפרד ב-JSON.
- **תקציבים לא שווים ואי אפשר שיהיו** — ער"ן מגדל לעצמו 184 אבות-טיפוס; ל-SNN נותנים שכבה.
  לכן ARM A′ מריץ את אותו קונפיג בדיוק ב-184 יחידות. החשיפה בהיגויים רשומה לכל זרוע.
- **מה שהעתקנו ומה שלא:** `brain.py` + `chemistry.py` הועתקו נאמנה. שינה (גיזום/צלקות) וטפיחות
  הורה לא הועתקו — אין הורה בבחינה אופליין, ובלי טפיחה כל הצלקות אפס.

**כל המספרים:** `results/ERAN-vs-SNN-2026-08-21.json` (גם על eran4, `~/snn-lab/results/`).
**הקוד:** eran4 `~/snn-lab/fairfight/` — `ff_lib.py`, `ff_run.py`, `ff_diag.py`, `run.log`.

*לזכרה של עלמה ז״ל.*
