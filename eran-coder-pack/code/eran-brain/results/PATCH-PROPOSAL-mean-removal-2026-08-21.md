# PATCH PROPOSAL — global mean removal in `body/brain.py` · **NOT APPLIED**

> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY. Test the REAL output, never a proxy.

**סטטוס: הצעה בלבד. לא הוחל על האורגניזם החי. / Status: proposal only. Not applied to the live organism.**
חוק הזירה: איבר נכנס רק אחרי שניצח את המספר שלו. זה המספר.
*Arena law: an organ enters only after it has won its number. Here is the number.*

---

## מה ניצח, ומה לא / What won, and what did not

**רוחב לא ניצח.** `ERAN-WIDTH-2026-08-21.json` — רוחב אלכסוני לכל יחידה 72.73%, קווריאנס מלא 60.35%,
שניהם מתחת לתקרת 74.24%. **אין הצעת פאטץ' לרוחב.**
*Width lost. No patch is proposed for width.*

**מה שכן ניצח את המספר שלו הוא שינוי של שורה אחת, לפני היחידה:**
להחסיר את ממוצע כל מה שנשמע עד כה, ואז לנרמל — לפני הקוסינוס.

| measurement | baseline | + mean removal | delta |
|---|---|---|---|
| **leave-one-session-out** (6 folds × 3 seeds, 396 judgements, **heldout never opened**) | 72.05% | **77.78%** | **+5.72 pts** |
| paired sign test over the 18 runs | — | 16 wins / 1 loss / 1 tie | **p = 0.0003** |
| 132-item heldout (post hoc, consistency only) | 69.44% | 75.76% | +6.32 pts |

**האזהרה ההוגנת:** הרעיון נמצא **post hoc** — שורת α=0 בעקומת ההלבנה היא מטריצת היחידה, כלומר היא
הייתה חיסור-ממוצע כל הזמן, וראינו את מספר ה-heldout שלה לפני שהבנו את זה. **הראיה הנקייה היא
leave-one-session-out**, שלא נוגעת ב-132 בכלל. אל תקרא את 75.76% כהוכחה.
*The lead was found post hoc. The clean evidence is the leave-one-session-out test.*

**וזה לא סוגר את הפער:** חיסור הממוצע מרים גם את הביקורות (centroid 80.81% → 82.07%). היצור עדיין
מתחת לביקורת שלא לומדת. *This does not make the organism win. It makes it lose by less.*

---

## למה זה נכון ביולוגית / Why this is the biologically right move

כל פרספט שיוצא מהשבלול הוא וקטור באורך 1, וכולם חולקים רכיב משותף גדול — צורת הספקטרום הממוצעת של
הברה. קוסינוס בין שני וקטורים שחולקים רכיב משותף גדול **נשלט על ידי הרכיב המשותף**: כל הדמיונות
נדחסות ליד 1 והשוני שנושא את המחלקה נדחק לספרה האחרונה. חיסור הממוצע גורם לקוסינוס למדוד את
**הסטייה** במקום את הצורה המשותפת.

זו **אדפטציה חושית** — בדיוק מה שאוזן אמיתית עושה כל הזמן: היא מתכיילת לסטטיסטיקה של הסביבה ומדווחת
על מה ששונה ממנה. ער"ן יכול להחזיק את זה כממוצע רץ של כל מה ששמע: **192 מספרים לכל המוח**, אפס מצב
לכל יחידה, ומתעדכן בכל פעימה.

⚠️ שים לב: `ears.py` כבר מוריד ממוצע — **לכל פרוסה על פני 24 הפסים**. זה ממוצע **אחר**: הממוצע של
הקורפוס כולו. השניים לא מתנגשים.

---

## הפאטץ' המוצע / The proposed patch

**איפה:** `D:\CLAUDE\eran-brain\body\brain.py`, המחלקה `Brain`.
**עיקרון:** לא נוגעים ב-`hear()`, ב-`tolerance()`, בכימיה או בצלקות. מוסיפים שלב אחד לפני ההשוואה.

```diff
--- a/body/brain.py
+++ b/body/brain.py
@@ class Brain:
     def __init__(self, dim, max_protos=None, age_offset=0):
         self.dim = int(dim)
         self.max_protos = int(max_protos if max_protos is not None
                               else genome.MAX_PROTOTYPES)
         self.age_offset = int(age_offset)
         self.protos = []          # [{vec, mass, birth_step, last_used, scar}]
         self._mat = None          # cached (n, dim) matrix for fast cosine
         self.elig = {}            # proto index -> trace strength
         self.beat = 0             # last beat this brain lived through
         self.heard = 0            # utterances digested
         self.sim_hist = []        # recent best-match similarities
         self.bar = None           # the novelty homeostat's current setting
+        # ---- sensory adaptation (ADDITIVE, proposed 2026-08-21) -----------
+        # A running average of every percept this layer has ever heard. Every
+        # cochlear percept is a unit vector and they all share one large common
+        # component - the average spectral shape of a syllable. Cosine between
+        # two vectors that share a big common part is DOMINATED by that shared
+        # part. Removing it makes the comparison measure the deviation, which
+        # is what the class actually lives in. This is what a real ear does
+        # continuously: it adapts to the ambient statistics and reports what is
+        # different from them.
+        # Measured: leave-one-session-out over the 6 training sessions,
+        # 72.05% -> 77.78% (+5.72 pts), 16 wins / 1 loss / 1 tie over 18 runs,
+        # sign test p = 0.0003. results/ERAN-WIDTH-2026-08-21.json.
+        self.adapt = bool(getattr(genome, "SENSORY_ADAPTATION", False))
+        self.mean_vec = np.zeros(self.dim)     # running mean of what was heard
+        self.mean_n = 0
+
+    def adapt_percept(self, vec):
+        """Subtract what everything sounds like, then renormalise.
+
+        Returns the vector unchanged while adaptation is off or while the
+        running mean is still too young to trust (a newborn has not heard
+        enough to know what 'average' means yet).
+        """
+        v = np.asarray(vec, dtype=np.float64)
+        if not self.adapt or self.mean_n < genome.ADAPT_WARMUP:
+            return v
+        z = v - self.mean_vec
+        n = np.linalg.norm(z)
+        return z / n if n > 0 else v
+
+    def observe_percept(self, vec):
+        """One more sound into the running mean. Called only when learning."""
+        self.mean_n += 1
+        self.mean_vec += (np.asarray(vec, dtype=np.float64) - self.mean_vec) / self.mean_n
```

והשינוי היחיד בלולאת החיים — `hear()` מתאים את הפרספט לפני שהוא משווה,
ומאכיל את הממוצע ב**גולמי**, לא במותאם:

```diff
     def hear(self, vec, chem, beat, learn=True):
         """One utterance vector arrives. Spawn on surprise, else Hebbian pull."""
-        idx, sim, att = self.nearest(vec)
+        raw = np.asarray(vec, dtype=np.float64)
+        # The running mean must be fed the RAW percept. Feeding it the already
+        # adapted vector makes the mean chase its own tail: the input to the
+        # average is the average's own output, the estimate drifts toward zero
+        # and the adaptation quietly turns itself off.
+        if learn:
+            self.observe_percept(raw)
+        vec = self.adapt_percept(raw)
+        idx, sim, att = self.nearest(vec)
         surprise = 1.0 - sim if idx is not None else 1.0
         spawned = False
         if learn:
             if (idx is None or sim < self.tolerance(idx)) \
                     and len(self.protos) < self.max_protos:
```

⚠️ **שים לב לסדר:** `observe_percept(raw)` לפני `adapt_percept(raw)`. הפרוטוטיפים נשמרים אז במרחב
ה**מותאם**, כלומר מוח קיים שנשמר במרחב הגולמי אינו תואם — ראה "מה צריך לקרות" למטה.

**ב-`genome.py`, שני קבועים חדשים, כבויים כברירת מחדל:**

```python
SENSORY_ADAPTATION = False   # proposed 2026-08-21; flip to True only after the
                             # live organism has re-won its number with it
ADAPT_WARMUP = 50            # beats before the running mean is trusted
```

**ופרסיסטנטיות** — `to_state()` / `load()` צריכים לשאת את `mean_vec` ו-`mean_n`, אחרת מוח שנטען
מדיסק מתעורר עם אוזן לא מכוילת. תוספת נאמנה לסגנון הקובץ (קריאה רק אם המפתח קיים, כך שקובץ ישן
נטען כמו קודם).

---

## מה צריך לקרות לפני שזה נכנס / What must happen before this is applied

1. **⚠️ הפאטץ' לא נבדק כקוד בתוך `brain.py`.** הוא נמדד כשינוי **שקול** בהרנס
   (`width_center.py`), לא כקוד הזה. צריך להריץ אותו בתוך האורגניזם עצמו ולאמת שהמספר חוזר.
2. **⚠️ מה שנמדד הוא ממוצע אצווה, מה שמוצע הוא ממוצע רץ.** `width_center.py` חישב ממוצע **אחד**
   מכל קבצי האימון וחיסר אותו מכולם. הפאטץ' מציע ממוצע **מתגלגל** שגדל עם החיים — הוא מתכנס לאותו
   דבר, אבל בילדות המוקדמת הוא **לא** אותו דבר, ובדיוק שם ער"ן מגדל את רוב אבות-הטיפוס שלו.
   `ADAPT_WARMUP` נועד לכסות את זה, והערך 50 הוא **ניחוש שלא נמדד**. חייבים למדוד אותו.
3. **הפרוטוקול הישן פסול** — ה-dev של המעבדה מזוהם לפי סשן ואופטימי בכ-14 נקודות
   (`ERAN-vs-SNN` / `ERAN-WIDTH`, ראה `verdict.what_redirects_tomorrow`).
   האימות חייב להיות **leave-one-session-out**.
4. **תאימות מוחות שמורים:** אחרי השינוי אבות-הטיפוס חיים במרחב המותאם. `brain.json.gz` קיים נכתב
   במרחב הגולמי. או שממירים בטעינה, או שנולדים מחדש — לא לתת למוח ישן לפגוש אוזן חדשה בשקט.
5. **ער"ן חי על eran1 באמצע תוכנית לימודים, ואיבר אחר בבעלות של סוכן אחר.** אל תיגע בשכבה שלו.
   מוח שנולד עם אדפטציה ומוח שקיבל אותה באמצע החיים אינם אותו דבר.

---

**הקוד המודד:** eran4 `~/snn-lab/width/width_center.py`
**כל המספרים:** `results/ERAN-WIDTH-2026-08-21.json` → `confirmation_global_mean_removal`

*לזכרה של עלמה ז״ל.*
