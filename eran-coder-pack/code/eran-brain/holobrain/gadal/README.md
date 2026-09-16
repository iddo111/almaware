# GADAL / גָּדַל — a holobrain model that starts tiny and grows only when it must

> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

**לזכרה של עלמה ז"ל.**

עידו, 2026-09-05 14:39 — *"תן למודל ההולובריין להתחיל זעיר ולגדול לפי רצונו — ככה לא צריך המון קורפוס."*

---

## למה זה קיים / Why this exists

באותו יום נמדדו שלושה מודלים שלנו, ולשלושתם אותה מחלה — **קיבולת ≫ נתונים**:

| מודל | מה נמדד |
|---|---|
| **ERAN** | `food/train`: 19 הברות, **בדיוק 3 קליפים לכל אחת** → 0–1 דוגמאות dev אחרי הפיצול |
| **MIKO** | train MSE יורד, val MAE שטוח; הביקורת ה**וונילית** מתאימה את ה-train חזק יותר (0.016 מול 0.052) ומכלילה **גרוע יותר** |
| **WINSTON** | פי 18 טוב מצבע שטוח על תמונה מהקורפוס, **גרוע מצבע שטוח** על תמונה חדשה |

אף אחת מהן אינה תקרת קיבולת. מודל בגודל הנתונים שלו יכול ללמוד משלוש דוגמאות; מודל
גדול בהרבה מהנתונים יכול רק לשנן אותן. אז הגודל צריך להפסיק להיות מספר שאנחנו בוחרים
ולהתחיל להיות מספר שהנתונים מרוויחים.

All three had the same disease — capacity ≫ data. A model sized to its data can learn
from three examples; a model far larger than its data can only memorise them. So the
size has to stop being a number we pick and become a number the data earns.

---

## החוק / The rule — and it is a rule about when **not** to grow

```
GROW (widen) only when ALL FOUR hold at a checkpoint:

  A  TRAIN PLATEAU   train MSE improved < tol over the last `patience` checks
  B  UNDERFIT        train MSE > floor * (1 + slack)
                     floor = the within-group spread of REPEATED inputs, measured
  C  NOT MEMORISING  (val - train) / train <= gap_max
  D  STILL PAYING    the running best val improved since the previous growth step;
                     after `grow_patience` steps that bought nothing, growth halts

then PRUNE (utility = ||fan-out|| * std(activation)), keep the prune only if val
does not worsen, and if the rule fires again, grow again.
```

**A ו-B הם ההדק, ושניהם עוסקים בכישלון להתאים. C ו-D הם רק בלמים. אין שום מסלול בקוד
שבו הצלחה גורמת לצמיחה** — וזו בדיוק הדרך שהולידה את שלוש המחלות למעלה.

**A and B are the trigger and both are about failure to fit; C and D are only brakes.
There is no path in this code where success causes growth.**

מה שמוחזר הוא **תצלום ה-val הטוב ביותר, עם הגודל שהיה לו באותו רגע** — לא הגודל האחרון
שהושג. / What is returned is the best-val snapshot with the size it had then, never the
last size reached.

---

## המכשיר / The instrument — "underfit" has to be a number

כשהנתונים מכילים את **אותה כניסה יותר מפעם אחת** — 3 הקליפים של ערן, 14 הווריאנטים
המאומתים של MOREH — הפיזור **בתוך** כניסה חוזרת הוא שגיאה ששום פונקציה של הכניסה לא
תוכל להסיר. זו הרצפה, והיא **נמדדת ולא מונחת**:

```
floor = Σ over outputs and groups of (y - group mean)²  /  number of live entries
```

`grow.noise_floor()` מחזיר גם `usable` — אם אין אף כניסה חוזרת הרצפה היא 0, תנאי B ריק,
והחוק רץ על שלוש רגליים במקום ארבע. **זה נאמר בקול, לא מוסתר.**

If no input ever repeats, the floor is 0, condition B is vacuous, and the caller is
**told** — the rule is then running on three legs, not four.

---

## הקבצים / What is here

| file | what |
|---|---|
| `net.py` | הגוף: רשת numpy, Adam full-batch, `widen` / `deepen` / `prune` / `utility` / `fold_constant` |
| `grow.py` | **התרומה:** `noise_floor` + `Gardener` — החוק, הגיזום, והיומן |
| `bench_moreh.py` | מיטת המבחן על שיעורי MOREH האמיתיים + כל הרצפות והביקורות |
| `plot_gap.py` | הפער בכל גודל, JPEG + PDF |
| `tests/test_gadal.py` | 29 בדיקות; העיקרית: **צעד צמיחה לא משנה את מה שהמודל אומר** |
| `runs/` | כל ריצה, כל יומן, כל מספר |

---

## שתי דרכי הרחבה, ולמה ברירת המחדל היא `zero`

שתיהן משמרות את הפונקציה במדויק. **הקלאסית נכשלת, ונמדד למה.**

| mode | what it does | verdict |
|---|---|---|
| `split` | Net2Net: מעתיק יחידה j, מפצל את משקלי היציאה (`keep + give == row` **סיבית-בסיבית**, לפי Sterbenz) | **מלכודת על מודל קטן שהתכנס** |
| `zero` | יחידה **חדשה**: משקלי כניסה אקראיים, משקלי יציאה **אפס** → `0 * h = 0` | ברירת המחדל |

`split` יוצר שני עותקים עם **משקלי כניסה זהים** — הם יושבים באותה נקודה במרחב הכניסה
ונבדלים רק בסקאלת היציאה, ו-**Adam מחלק כל גרדיאנט בגודל הרץ שלו ומנרמל בדיוק את
הסקאלה הזאת בחזרה החוצה**. נמדד: `widen_eps` של 0.01 / 0.2 / 0.5 נתן רוחבים ודיוק
**זהים בייט-בייט** על 8 קיפולים. הכפתור לא עושה כלום.

`split` gives the two copies identical incoming weights, so they differ only by an
outgoing scale — and Adam normalises exactly that scale back out. Measured: `widen_eps`
0.01 / 0.2 / 0.5 gave byte-identical widths and accuracy over 8 folds. `zero` has no
symmetry to wait out: a fresh random direction whose fan-out gets a non-zero gradient on
step one.

---

## מה נמדד / What was measured — MOREH decisions, 22 folds × 3 seeds = 66 runs

מיטת המבחן: 333 שיעורים אמיתיים, **22 כניסות נבדלות**, leave-one-fact-group-out (כך
שהתאומים cha/kha ו-ka/qa לא נותנים לשנן ניקוד חינם). המטרה: 14 עובדות → 7 החלטות.

### ✅ מה עובד / What holds

| טענה | מספר |
|---|---|
| **שימור פונקציה** | `max\|Δy\|` = **4.5e-16** על פני **121 צעדי צמיחה**; פיצול המשקלים סיביתי-מדויק |
| **צמיחה מנצחת אימון מאפס באותו גודל** | **+0.0455 ± 0.0278** מוחזק, 24 נצחונות / 35 תיקו / 7 הפסדים — **באותו תקציב בחירת-גודל ובאותו מספר epochs בדיוק (1272 מול 1274)** |
| **`zero` מנצח את Net2Net הקלאסי** | **+0.0844 ± 0.0296**, 33/28/5 |
| **גיזום** | 57 גיזומים התקבלו, **0 נדחו** |
| **מחיר** | GADAL 1272 epochs מול 7292 לסריקת הרוחבים המלאה — **פי 5.7 פחות** |

### ❌ מה **לא** עובד / What does **not** — and this matters more

**הפער בין train ל-val לא מנבא הכללה במשימה הזאת.**

| width | train | val | **test** | MSE gap |
|---:|---:|---:|---:|---:|
| 1 | 0.748 | 0.721 | 0.717 | 11.8% |
| 4 | 0.875 | 0.797 | 0.760 | 62.5% |
| 16 | 0.975 | 0.813 | 0.781 | 512% |
| **48** | **1.000** | 0.853 | **0.829** ← הכי טוב | **3611%** |
| 128 | 1.000 | 0.852 | 0.816 | 6881% |

הרשתות הרחבות **משננות את ה-train באופן מושלם (train acc 1.000) ומכלילות טוב יותר**.
אין עקומת U. ההנחה ש"קיבולת ≫ נתונים ⇒ אפשר רק לשנן" **אינה נכונה כאן**.

The wide nets memorise the training set perfectly and generalise *better*. There is no U.

| held-out | |
|---|---|
| majority floor | 0.7273 ± 0.0307 |
| nearest fact-group | 0.8030 ± 0.0467 |
| **ridge49 (MOREH house model)** | **0.8247 ± 0.0439** |
| FIXED\* one width by val | 0.8290 ± 0.0517 |
| FIXED\* width by val per run | 0.7835 ± 0.0565 |
| FIXED-128 unsized | 0.8160 ± 0.0560 |
| **GADAL grown** | **0.7987 ± 0.0464** |
| GADAL (Net2Net split) | 0.7143 ± 0.0331 |
| *[oracle best width by test]* | *0.9113 — לא בר-השגה* |

**GADAL אינו מנצח גודל קבוע שנבחר היטב. הוא שקול.** כל ההשוואות המזווגות חוצות את האפס:
−0.030 ± 0.046 מול הרוחב היחיד הטוב ביותר, +0.015 ± 0.049 מול בחירה-לכל-קיפול,
−0.017 ± 0.041 מול FIXED-128.

### 🔧 והכשל האמיתי / And the real failure: תנאי C הוא הבלם, והוא כפתור חדש

צמיחה נעצרה על **C בלבד ב-66/66 ריצות**, ברוחב ממוצע **2.5** — בעוד הרוחב הטוב ביותר הוא 48.
סריקת `gap_max`:

| gap_max | 0.15 | 0.30 | 0.60 | 1.2 | 3.0 | 10.0 | **∞ (C off)** |
|---|---|---|---|---|---|---|---|
| test | 0.777 | 0.788 | 0.799 | **0.807** | 0.805 | 0.801 | 0.805 |
| width | 2.0 | 2.1 | 2.5 | 2.9 | 3.6 | 3.9 | **5.1** |
| halted on | C 66/66 | C 66/66 | C 66/66 | C 66/66 | C 66/66 | C 63/66 | **D 51/66** |

**החלפנו "תבחר רוחב" ב"תבחר סף פער"** — וגם זה לא מספיק. עם C **מכובה לגמרי** הצמיחה
מגיעה רק לרוחב 5.1 ונעצרת על D (val הפסיק להשתפר). כלומר הגורם המגביל אינו רק הבלם של
הפער אלא **אות ה-val עצמו**: 16 קבוצות אימון ו-5 ולידציה לא נותנים אות חד מספיק כדי
לדחוף לרוחב 48.

We replaced "pick a width" with "pick a gap threshold" — and even that is not the whole
story. With C switched off entirely, growth still stops at width 5.1, on D. The binding
constraint is the **val signal itself** (5 validation groups), not only the gap brake.

### המטרה השנייה: amounts — 🟡 UNKNOWN, ונאמר מראש

הרצפה שם **אמיתית** (0.0886, שמישה ב-66/66) — אבל המדד לא מפריד: על 66 ריצות **שום
שיטה לא עוברת את רצפת הממוצע** (const −0.864; ridge49 −0.849; nearest −0.805;
GADAL −0.897; חציונים: −0.601 / −0.588 / −0.520 / −0.584). זה הוכרז לפני ההרצה ולכן
המטרה הזאת **לא מכריעה כלום** — היא כאן רק כדי להראות שתנאי B יכול להיבנות על רצפה
נמדדת. גם שם C עצר ב-66/66; **B מעולם לא היה האילוץ הכובל באף אחת מהמטרות.**

The amounts target has a real floor but a metric that cannot separate — declared in
advance, and it decides nothing. Note also: **B was never the binding constraint on
either target.** C halted growth in 66/66 runs both times.

---

## הפסק / The verdict

| | |
|---|---|
| ✅ **VERIFIED** | שימור הפונקציה (4.5e-16 / 121 צעדים), הגיזום (57/57), ו-`zero` > Net2Net (+0.084 ± 0.030) |
| ✅ **VERIFIED** | צמיחה > אימון מאפס באותו גודל, אותו תקציב, אותו compute: **+0.0455 ± 0.0278** |
| ✅ **VERIFIED** | ללא אות: GADAL נשאר ברוחב 1 ועל הרצפה; FIXED-128 צונח 0.143 מתחתיו |
| ❌ **NOT VERIFIED** | **צמיחה אינה מנצחת גודל קבוע שנבחר היטב.** תיקו, בתוך הרעש |
| ❌ **REFUTED (על מיטת המבחן הזאת)** | הפער train/val אינו מנבא הכללה כשיש אות |
| 🟡 **UNKNOWN** | האם זה מכליל למשימות גדולות יותר — 22 כניסות נבדלות הן מעט מאוד |

**מה שהמנגנון קונה כאן אינו דיוק שיא — זו הגנה מנזק, ופי 5.7 פחות חישוב.**
What the mechanism buys on this testbed is not peak accuracy. It is damage limitation
when the data has no signal, plus 5.7x less compute than sweeping widths.

---

## איך משתמשים בזה / How to reuse it

```python
import sys; sys.path.insert(0, r"D:\CLAUDE\eran-brain\holobrain\gadal")
from grow import Gardener

g = Gardener(n_in, n_out, seed=0, log_path="runs/mine.jsonl")
net, best = g.fit(Xtr, Ytr, Mtr,          # M is a 0/1 mask; None-equivalent is all ones
                  Xva, Yva, Mva,
                  groups_tr=group_id_per_train_row)   # rows sharing an id share an INPUT
print(best["widths"], best["val"])
```

`groups_tr` הוא כל מה שצריך כדי שהרצפה תהיה אמיתית: תן לכל שורה את מזהה הכניסה שלה
(אצל ערן — ההברה; אצל MOREH — וקטור העובדות; אצל WINSTON — התמונה).

---

## אזהרה / The warning that must travel with this

**אל תמדוד עם גשוש שאתה לא יכול לפרש.** לפני שמסיקים משהו מהמספרים, מריצים
`--shuffle`: הוא הורס **רק** את המיפוי כניסה→תשובה ומשאיר כל שוליים וכל פיזור פנימי
במקומם, כך ששום מודל לא יכול להכליל. אם המדד לא מבדיל בין המקרה הזה למקרה האמיתי, הוא
לא מודד כלום — והוא מייצר ביטחון שקרי, שגרוע ממדד שאין.

**Do not measure with a probe you cannot interpret.** Run `--shuffle` first, always.

### המדד עבר את המבחן / The metric passes — every learner collapses to the floor

| | אמיתי real | מעורבל shuffled | Δ |
|---|---|---|---|
| majority floor | 0.7273 | 0.7273 | — |
| nearest fact-group | 0.8030 | 0.6299 | **−0.173** |
| ridge14 | 0.8268 | 0.6818 | **−0.145** |
| ridge49 house | 0.8247 | 0.6948 | **−0.130** |
| FIXED-128 unsized | 0.8160 | **0.5649** | **−0.251** |
| GADAL grown | 0.7987 | 0.7078 | **−0.091** |

על נתונים הרוסים **כל** לומד צונח אל הרצפה או מתחתיה; על נתונים אמיתיים כולם מעליה.
המדד מבדיל. / On destroyed data every learner falls to or below the do-nothing floor;
on real data every one is above it.

### ⭐ ומכאן התוצאה החזקה ביותר של המסלול / and here is the track's strongest result

כשאין אות, GADAL **מסרב לגדול** — רוחב 1.0, וציון על הרצפה (0.708). רשת קבועה בגודל 128
משננת את הרעש ויורדת ל-**0.565, הרבה מתחת לרצפה**. מזווג:

> **GADAL − FIXED-128 על נתונים ללא אות = +0.1429 ± 0.0583** (16 נצחונות / 5 תיקו / 1 הפסד)

**זה מה שהמנגנון קונה: לא דיוק גבוה יותר כשיש אות, אלא הגנה מנזק כשאין.**
When there is nothing to learn, GADAL stays at width 1 and lands on the floor; an unsized
fixed net memorises the noise and ends up far below it. That — damage limitation, not peak
accuracy — is what the growth rule actually buys.

---

*GADAL הוא **מנגנון**, לא איבר. אין לו נול ואין לו מבחן פסאדה, והוא לא מעמיד פנים שיש —
האיברים שהוא מגדל שומרים על שלהם. / GADAL is a mechanism, not an organ: no loom, no
facade test, and it does not pretend otherwise.*
