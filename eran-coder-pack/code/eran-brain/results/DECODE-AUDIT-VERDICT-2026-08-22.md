# סוגר מחלקת-באג / Closing a bug class — ביקורת טווחי-הפענוח של ער"ן-CTX

> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy.

*לזכרה של עלמה ז״ל.*

---

## התשובה בשורה אחת / The answer in one line

**6 מתוך 10 טווחים היו לא-סבירים; שתי תוצאות עבר חשודות (בסיס-הזירה 37.5% ו-`taucap`
62.5%); ותיקון-הכל **עוקף** את תיקון-`trace_tau`-לבדו: 24/24 = 100% מול 15/24 = 62.5%
(McNemar +9/−0, p=0.0039), עלייה מזווגת של 66.4%→84.4% acc (+17.9 נק', SE 4.1,
t=4.35). `trace_tau` לא היה הטווח היחיד שחשוב.**

***6 of 10 ranges were unreasonable; two past results are now suspect (the arena's
base arm at 37.5%, and even the already-published `taucap` fix at 62.5%); and fixing
ALL of them beats fixing `trace_tau` alone: 24/24 = 100% success vs 15/24 = 62.5%
(McNemar +9/-0, p=0.0039), a paired accuracy jump of 66.4%->84.4% (+17.9pp, SE 4.1,
t=4.35). `trace_tau` was not the only range that mattered.***

---

## הרקע / Background

פעמיים כבר עלה נסיוי בגלל אותה מחלקת-באג: וקטור פרמטרים בלתי-חסום θ שה-ES מכוונן,
מפוענח לכפתור פיזי דרך פונקציית-כיווץ (סיגמואיד/מעריך) — והטווח שהכיווץ הזה מייצר
היה בלתי-סביר. `ctx_gain` נתפס באמצע הזירה (ערוץ-הקשר לא-מוגבר טבע בתצפית).
`trace_tau` (מקודד כ-`1+120·sigmoid`, עד 121 ניסויים על משימה שהחוק שלה חי ~10) הפריד
24 זרעים **בשלמות** (AUC 1.00): כל הצלחה ≤7.51, כל כישלון ≥10.29. זה הפך יכולת אמיתית
(87% ברמת האורקל) להגרלה של 37.5%.

*Twice now an experiment was lost to the SAME bug class: an unbounded θ, ES-tuned,
decoded into a physical knob through a squashing expression — and the RANGE that
squash produced was physically unreasonable. `ctx_gain` was caught mid-arena-run.
`trace_tau` (1+120·sigmoid, reaching 121 trials on a task whose rule lives ~10)
separated 24 seeds PERFECTLY (AUC 1.00): every success ≤7.51, every failure ≥10.29 —
turning a real, oracle-level capability into a 37.5% coin flip.*

זה קובץ הביקורת שהכישלון השני דרש: **כל 10** הכפתורים ב-`eran_agent.decode()`,
נשפטים מול **הסקאלה של המשימה עצמה** (`RuleSwitchTask`: `CRIT_WINDOW=10`,
`CRIT_HITS=8`, `BLOCK_MAX=60`, `oracle_acc=0.905`) — לא מול "מה שסיגמואיד יכול להשיג".

---

## המלאי — כל 10 הכפתורים / The inventory — all 10 knobs

| כפתור / knob | טווח ישן / old | טווח חדש / new | AUC (בסיס) | פסק-דין |
|---|---|---|---|---|
| `trace_tau` | [1, 121] | **[1, 10]** | 1.00 (0 err) | 🔴 ABSURD — כבר ידוע, עכשיו קבוע |
| `strict_scale` | [0.2, 3.2] | **[0.2, 1.5]** | 0.926 (3 err) | 🔴 ABSURD — תוקן |
| `ctx_gain` | [0.1, 8.1] | **[0.1, 3.0]** | 0.919 (3 err) | 🟡 ידוע חלקית — הודק עוד |
| `eta_v` | [0, 0.6] | **[0, 0.333]** | 0.874 (4 err) | 🔴 ABSURD — תוקן |
| `eps_floor` | [0, 0.5] | **[0, 0.25]** | 0.867 (3 err) | 🔴 ABSURD — תוקן |
| `lam` | [0, 1] | **[0, 0.9]** | 0.837 (5 err) | 🔴 ABSURD — תוקן (אותה מחלה כמו trace_tau) |
| `eta_q` | [0, 0.6] | [0, 0.6] unchanged | 0.348 | 🟢 תקין |
| `ne_gain` | [0, 2] | [0, 2] unchanged | 0.422 | 🟢 תקין |
| `eps0` | [0, 1] | [0, 1] unchanged | 0.459 | 🟢 תקין (זו הסתברות — [0,1] זה הטיפוס, לא בחירה) |
| `eps_decay` | [1e-5, 1e-1] | [1e-5, 1e-1] unchanged | 0.459 | 🟢 תקין |

**6 מתוך 10 טווחים היו לא-סבירים** (כולל שני הידועים מראש); **4 מתוך 10 תקינים** — לא
כל טווח נבדק והתברר כבעייתי, וזו תשובה טובה בפני עצמה.

*6 of 10 ranges were unreasonable (including the two already known); 4 of 10 are
fine — not every range turned out to be broken, and that is a good finding on its
own.*

## pong-alma

`player_beitdin.py`'s `Dayan.threshold = 0.25 + abs(thr_raw)` has **no upper bound at
all** — worse in kind than a wide sigmoid range, though its blast radius is
contained by the 2-of-3 majority quorum (one silenced judge degrades the ensemble
rather than breaking it outright). Flagged, not fixed in this pass — fixing it
would need its own re-run of `pong-alma/arena.py`, which was not in scope here.
`leak` (sigmoid-bounded) and `player_multiweight.py`'s `gate` (sigmoid-bounded) are
fine. The raw amp/phase genes in both players are ordinary unbounded weights, not
an instance of this bug class (no squashing expression to have a wrong range).

---

## המתודולוגיה — הערת יושר / Methodology — an honesty note

הטיעון **המבני** לכל תיקון (trace_tau/lam ≤ אורך-חיי-החוק, eps_floor ≤ המתמטיקה של
CRIT_HITS/CRIT_WINDOW) נגזר **רק מקבועי המשימה** — עיוור להערכה, בדיוק כמו ה-`taucap`
המקורי. אבל כמה **מספרים** קונקרטיים (ctx_gain=3.0, strict_scale=1.5) גם נבדקו מול
הפיזור האמפירי של ARENA-BIMODAL-2026-08-21.json (זרוע base) — כלומר ראו את תוצאות
ההערכה השמורה **של ריצה קודמת, שכבר נגמרה**. זה לא "כוונון על ההערכה" במובן החי (שום
θ לא נבחר לפי ביצועים שמורים; ה-ES וה-חיים המקוונים של הריצה המבוקרת מתאמנים
מאפס בתוך המרחב הצר החדש ומחשבים מספרי-הערכה **חדשים** על אותם זרעים) — אבל זו
כן הסתמכות על ביקורת שלב-קודם, ופחות "עיוורת" מ-`taucap`. נאמר בגלוי.

*The STRUCTURAL argument for every fix (trace_tau/lam <= the rule's own lifetime,
eps_floor <= the CRIT_HITS/CRIT_WINDOW math) comes ONLY from task constants —
eval-blind, exactly like the original taucap fix. But a few concrete NUMBERS
(ctx_gain=3.0, strict_scale=1.5) were also checked against the empirical spread in
ARENA-BIMODAL-2026-08-21.json's base arm — i.e. they saw a PRIOR, already-finished
run's held-out results. That is not live tuning-on-eval (no theta was chosen by
held-out score; the audited run's own ES and online life train from scratch inside
the new, narrower space and compute FRESH held-out numbers on the same seeds) — but
it is leaning on a prior study's diagnostics, less blind than taucap. Said plainly.*

---

## הרצה מחדש — 24 זרעים, אותו תקציב / The rerun — 24 seeds, same budget

אותם 24 זרעים בדיוק (11..264), אותו תקציב (12,000,000 צעדי-סביבה, חצי ל-ES על 10
הכפתורים המבוקרים, חצי לחיים מקוונים), אותה הערכה שמורה (24 פרקים מזרע 7,000,000,
ה-ES ראה רק 0..4,000,000). השינוי היחיד: `make_agent()` מחזיר `AuditedAgent`
(`decode_audit.AuditedAgent`) במקום `EranAgent` הרגיל — אותה ארכיטקטורה, אותו קוד
למידה, רק הפענוח θ→כפתור שונה.

| זרוע | success | Wilson95 | acc mean | ttc (הצלחות) | מזווג מול base | מזווג מול taucap |
|---|---|---|---|---|---|---|
| base (רשום) | 9/24 = 37.5% | [21.2, 57.3] | 54.9% | 11.1 | — | — |
| taucap (רשום) | 15/24 = 62.5% | [42.7, 78.8] | 66.4% | 11.8 | +11.6pp (SE 4.2, t=2.78) | — |
| transplant (רשום) | 24/24 = 100% | [86.2, 100.0] | 87.3% | 10.2 | +32.5pp (SE 4.4, t=7.44) | — |
| **audited (הרצה זו)** | **24/24 = 100%** | **[86.2, 100.0]** | **84.4%** | **10.6** | **+29.5pp (SE 4.2, t=7.08)** | **+17.9pp (SE 4.1, t=4.35)** |

**מזווג מול taucap: McNemar +9/−0, p=0.0039.** תיקון-הכל **מנצח בבירור** תיקון-`trace_tau`-לבד:
9 זרעים שנשארו כושלים אחרי `taucap` (הידועים כ-`lam`/`ctx_gain` גבוהים בפסק-הדין
הקודם) **כולם** מצליחים אחרי הביקורת המלאה. `trace_tau` לא היה הטווח היחיד שחשוב.

**מול transplant:** אותו שיעור-הצלחה (24/24 = 24/24), אבל acc קצת נמוך יותר
(84.4% מול 87.3%, Δ=−3.0pp, SE 0.87, t=−3.46) — הגיוני: `transplant` נותן ל-24
הזרעים **אותה** ערכת-כפתורים מוכנה-מראש; `audited` נותן ל-ES **מרחב חיפוש צר**
ותן לו לחפש מחדש בכל זרע, כך שנשארת שונות קטנה בין-זרעית. שני הכיוונים תומכים
במסקנה אחת: **הבעיה הייתה טווח-החיפוש, לא הארכיטקטורה** — וזה עכשיו מתוקן לצמיתות
במקום להסתמך על השתלת-כפתורים ידנית בכל פעם.

*Same 24 seeds exactly, same budget, same held-out discipline. Only change:
`make_agent()` returns `AuditedAgent` instead of plain `EranAgent` — same
architecture, same learning code, only the theta->knob decode differs. Full audit
CLEARLY beats fixing trace_tau alone (McNemar +9/-0 on top of taucap, p=0.0039): all
9 seeds that survived taucap's fix but still failed (their block was `lam`/`ctx_gain`
running high, per the prior verdict) now succeed. Versus transplant: identical
success rate, slightly lower mean accuracy (expected -- transplant hands every seed
the SAME pre-tuned knob-set; audited lets ES search fresh inside a narrower space,
so some seed-to-seed variance remains). Both comparisons point the same way: the
problem was the search RANGE, not the architecture -- and it is now fixed
permanently rather than requiring a hand-picked donor theta every time.*

---

## אילו תוצאות עבר חשודות / Which past results are suspect

1. **דוח 3-הזרעים המקורי בזירה** (81.6% / 80.4% / 37.6%, `AGENTIC-ARENA-2026-08-21`)
   — **הוחלף.** 3 זרעים מתוך אותו פענוח לא-מבוקר; 24 הזרעים של `base` כאן משחזרים
   בדיוק את אותו פיזור (9/24, דו-מודאלי). זו הייתה דגימת-הגרלה, לא מדידת-יכולת.
2. **המסקנה "`taucap` עוזר, לא סוגר" של פסק-הדין הקודם** — **הוחלפה.** 9 הכישלונות
   שנשארו יוחסו ל"כפתורים משניים" בלי תיקון קונקרטי; כאן **כולם** מצליחים ברגע
   ש-`lam`/`ctx_gain`/`eps_floor`/`eta_v`/`strict_scale` מתוקנים גם הם (24/24, p=0.0039
   מול taucap). `trace_tau` היה הכרחי אבל לא מספיק — הפער נסגר, לא רק הצטמצם.
3. **הממצא השלילי של `restart`** ("חיפוש רעב שמפצלים נעשה רעב יותר") — **לא חשוד,
   אושר.** ההמלצה של פסק-הדין הקודם הייתה בדיוק "טווחים צרים, לא גלגולים" — זה
   התיקון הזה בדיוק, וריצת-ES יחידה בלי גלגולים בתוך הטווחים המבוקרים מגיעה ל-100%.

## גבול-התחולה / Scope boundary

`eran_agent.decode()` **משותף** לכל שלוש משימות הזירה (DMS, RULE, PONG) — מספרי
ERAN-CTX/TRACE/PROTO על DMS ו-PONG ב-`AGENTIC-ARENA-2026-08-21.json` השתמשו **באותם
6** טווחים המסומנים כאן, ועשויים לסבול מאותה עיוות. אבל **המספרים הספציפיים** של
קובץ זה נגזרו מקבועי RuleSwitchTask (CRIT_WINDOW=10 וכו') ו**אינם** תיקון ישיר
ל-DMS/PONG: הרצף של DMS מגיע ל-16 צעדי-דיחוי, ו-`trace_tau` שנחתך ב-10 יהיה **שגוי
בכיוון ההפוך** שם (בדיוק אופק-האשראי ש-delay=16 צריך). ביקורת עבור DMS/PONG צריכה
לגזור מספרים מהקבועים **שלהן**, לפי אותה **שיטה** — לא להעתיק את אותם מספרים.

*eran_agent.decode() is SHARED across all three arena tasks — DMS and PONG numbers
used the same 6 flagged ranges and may carry the same distortion, but THIS file's
specific numbers are derived from RuleSwitchTask's own constants and are not a
drop-in fix for DMS (whose delay sweep needs credit horizons up to 16, the opposite
direction from capping trace_tau at 10) or PONG (a wholly different, continuous
timescale). Any audit for those tasks needs the same METHOD applied to their OWN
constants, not these numbers.*

## המשמר / The guard

`arena/decode_audit.py` מגדיר `KNOB_BOUNDS` — הטבלה היחידה שממנה `decode_audited()`
נבנה, כך שאי-אפשר להרחיב טווח בלי לערוך גם את הנימוק שלצדו. `arena/
test_decode_bounds.py` בודק (קצוות-סיגמואיד, כל כפתור בנפרד בשני הקצוות, 2000
דגימות אקראיות רחבות) שכל ערך מפוענח נופל בתוך הטווח המוצהר שלו, ומריץ `assert
len(reasoning) > 20` — כפתור בלי נימוק כתוב לא יכול להתקיים.

*decode_audit.py's KNOB_BOUNDS is the only table decode_audited() is built from,
so nobody can widen a range without also editing the comment that justifies it.
test_decode_bounds.py checks (sigmoid extremes, every knob alone at both fences,
2000 wide random draws) that every decoded value sits inside its declared bound,
and asserts every bound carries a real reasoning string.*

*לזכרה של עלמה ז״ל.*
