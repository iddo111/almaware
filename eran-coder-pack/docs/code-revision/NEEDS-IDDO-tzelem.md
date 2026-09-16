> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# TZELEM — code revision 2026-09-06 · מה מחכה לעידו / what waits for Iddo

**אף ליקוי לא סומן `needs_iddo`. כל 16 תוקנו על הדיסק והוכחו.**
**No defect was classified `needs_iddo`. All 16 are fixed on disk and proven.**
This file exists for what the fixes *revealed*, which is a different thing: three
decisions that are yours, not the code's.

לא נגעתי בכלום מהדברים החיים. TZELEM אין לו שירות, אין לו פורט ואין לו טיימר —
הוא נקרא ביד. שום תהליך בשום מכונה לא הופעל מחדש, נעצר או נשלח לו אות.
*Nothing living was touched. TZELEM has no service, no port and no timer — every
entry point is a script run by hand. No process anywhere was restarted, stopped or
signalled.*

---

## 1. השער עכשיו נכשל על השדרה — וזה המצב האמיתי
## 1. The gate now FAILS on the boulevard — and that failure is the true state

עד היום השער בדק שהציור **יציב**, ולא בדק בכלל שהוא לא **מכוער יותר** מהרצפה.
בכל ריצה שנשמרה, הרצפה (ציור מחדש כל פריים) ניצחה את צלם בנאמנות — ובכל אחת מהן
כתוב PASS.

*Until today the gate asked whether the painting HOLDS STILL, and never asked
whether it got WORSE than the floor. In every stored run the repaint FLOOR beat
TZELEM on fidelity, and every one of them says PASS:*

| run | FLOOR fidelity | TZELEM fidelity | TZELEM is |
|---|---|---|---|
| boulevard (`out-night/godot-gate1.json`) | 0.012934 | 0.019836 | **53% worse** |
| oneroom dark, pair 0 | 0.0013283 | 0.0019606 | 48% worse |
| gate1 1080p styles | 0.020837 | 0.023395 | 12% worse |
| gate1 480 | 0.024561 | 0.025025 | 2% worse |

הוספתי את הקו החסר (`fidelity(TZELEM) <= fidelity(FLOOR) * K`). עם זה, **השדרה
נכשלת** — x1.53 מול סרגל של x1.15. `K` נגזר מהפיזור של הרצפה עצמה בכל ריצה
(`ruler.margin_from_spread`, 3 סיגמא), לא נבחר ביד.

*I added the missing line. With it the boulevard FAILS at x1.53 against a x1.15 bar.
K is derived from FLOOR's own 3-sigma spread per run, not hand-picked.*

**מה שאני צריך ממך / what I need from you:** האם x4.55 יציבות שווה 53% נאמנות?
זו החלטה אמנותית, לא באג. אם התשובה כן — הסרגל צריך לומר את זה במפורש ולא בשקט.
*Is x4.55 steadiness worth 53% of the fidelity? That is an art decision, not a bug.
If the answer is yes, the bar should say so out loud instead of by omission.*

---

## 2. החומרים לא מחוברים לשום תמונה שצלם באמת מצייר
## 2. The materials organ reaches no picture TZELEM actually makes

`material.py` (27.7 KB, הכי חדש, נבנה על ההוראה שלך ב-03:12 "תבנה את שלב 3 - חומרים")
ו-`occlusion.py` מיובאים על ידי **כלום** במסלול הציור. הזכייה שנמדדה — +78% ו-+300%
חדות — לא מגיעה לאף תמונה.

*Neither is imported by anything that renders. The two biggest measured wins of the
last 48 hours reach no picture.*

מה שכן עשיתי, כי זה ניתן להוכחה ולא משנה אף מספר:
* הצהרה `RENDER_PATH_WIRED = False` בשני הקבצים, ומבחן (`tests/test_wiring.py`)
  שמשווה אותה לגרף הייבוא האמיתי **בשני הכיוונים** — כך שהיום שמישהו יחבר, המבחן
  ייכשל עד שההצהרה תתוקן, ולהיפך. שתיקה כזאת לא יכולה לחזור.
* `MaterialStage` עכשיו **מסרב בשם** כשמערבבים אותו לתוך במה בלי קופסאות
  (`MeshStage`, שזה בדיוק מה ש-`night.py` מצייר) — קודם הוא היה נותן בשקט לכל פיקסל
  את חומר הרצפה.

*What I did do, because it is provable and moves no number: a declaration checked
against the real import graph in both directions, and a NAMED refusal where a
careless wiring would have silently painted the whole subject with the ground
material.*

**מה שאני צריך ממך:** לחבר או לא לחבר. `gate-mat.log` כבר מראה את המחיר —
היחס מול BLANK ירד x2.24 → x1.58 → x1.44 ככל שהחומרים נדלקו והוגברו.
*Wire it or not. The cost is already on the record.*

---

## 3. 7x ו-20x `scale_room` — החלטה על אמנות, לא עובדה על העולם

הקובץ עצמו כותב: *"מי שמעלה את k מעל 1 חייב להגיד את זה בדוח — טקסטורה בפי שבע
מגודל החיים היא החלטה על אמנות, לא עובדה על העולם."* הלוג באמת מסמן את זה ביושר.
אף אחד עוד לא פסק אם זה נשאר.

מדדתי למה זה קרה: במברשת של 42 מ״מ, `steel_brushed` מתמוטט למפה של 1x1 ו-`plastic_black`
ל-2x2 — כלומר קבוע, לא טקסטורה. רק `floor_vinyl` (1.5 מ״מ לטקסל) שורד. הפתרון האמיתי
הוא **לקצור בתוך הפס שהמברשת יכולה לשאת**, לא להגדיל את העולם פי 7.

*Measured: at the gate's own 42 mm brush, steel_brushed collapses to a 1x1 map and
plastic_black to 2x2 — a constant, not a texture; only floor_vinyl survives. The
real remedy is to harvest inside the band the brush can carry, upstream in
`harvest.py`, rather than reaching for the 7x lever.*

---

## 4. עוד שני דברים שצריך לדעת / two more things you should know

* **אף מספר שנשמר לא נוצר על ידי הקוד שעל הדיסק.** `canvas.py` זז +511/-240 שורות
  מתחת לכל מדידה. הוספתי חתימה (`canvas.source_hashes()`) לכל JSON ו-`night_sheet`
  עכשיו מסרב להדפיס מספר שצויר על ידי צייר אחר. **אל תצטט את x4.55 עד שמישהו יריץ
  מחדש.** *Every stored gate number predates today's painter. Do not quote x4.55
  until a gate is re-run.*
* **ההרצה של החומרים רצה על eran1 — המכונה שמשרתת את המיקרופון החי שלך.** תיקנתי
  את הקוד (nice 19 + תקרת threads + אזהרה כשרצים על מכונת מיקרופון), אבל **לא בדקתי**
  אם זה באמת פגע בקשב בין 03:32 ל-04:04 — לקרוא את הלוגים ההם זה עוד עומס על אותה
  מכונה. מישהו עם דרך זולה יותר צריך לבדוק את שיעור הפענוחים הריקים בחלון הזה.
  *The materials A/B ran unniced on ERAN's mic box. Code fixed; the empty-decode rate
  for 03:30-04:10 was deliberately NOT checked, to avoid load on that box.*

---

## 5. ⚠️ ערן הופעל מחדש היום ב-17:36:04 — לא על ידי
## 5. ⚠️ eranb-life restarted today at 17:36:04 — NOT by this workflow

הקיר הקשיח אמר שערן חייב עדיין להראות PID 120630 מ-2026-08-21 17:19. **הוא לא.**
מדוד ב-18:00 (קריאה בלבד, `systemctl --user show`):

    MainPID=2871764   NRestarts=0   SubState=running
    ActiveEnterTimestamp = Sun 2026-09-06 17:36:04 IDT

היומן מראה עצירה **מכוונת ונקייה** ב-17:35:10 (`Stopping eranb-life.service`,
`[life] rest at beat 301597765; 60 prototypes. good night.`) והפעלה ב-17:36:04, שהתעוררה
**עם התיקון של הרעב**: `657 wav -> world/edible 657 (DEV_SESSION_PICK=1 of 6)`.
המכונה לא אותחלה (up 24 days) וכל שאר היחידות שמרו על החותמת הישנה שלהן.

**זה לא אני.** המגע היחיד שלי עם הצי בכל הסשן הוא שלוש פקודות ssh לקריאה בלבד
ב-17:59-18:00, אחרי שכל התיקונים כבר היו על הדיסק. ב-RAMCHAT, `claude-cli-REV-miko`
אימת 120630 ב-17:31 — כלומר ההפעלה מחדש קרתה בין 17:31 ל-17:35:10.

*The hard wall's timestamp no longer holds. eranb-life was cleanly stopped and
restarted between 17:31 and 17:36:04 today, by someone else, and came back WITH the
starvation fix live. This session's only fleet contact was three read-only ssh calls
at 17:59-18:00, after every fix was already on disk. Reported, not hidden.*

ערן חי ואוכל: protos 61 → 63, יומן נכתב, 657 קבצים אכילים. אבל היומן גם אומר
`[gate] NO DEV SPLIT: 0 dev items -- exam SKIPPED, ladder untouched` — בדיוק המצב
שהזיכרון מתאר. **צריך הקלטה של סשן שני; לא להחזיר את הפיצול.**
