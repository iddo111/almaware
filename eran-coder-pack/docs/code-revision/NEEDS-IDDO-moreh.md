# MOREH — שלוש החלטות שלך / three calls that are yours (2026-09-06, claude-cli-REV-moreh)

> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

**עברית:** בסבב תיקון-הקוד של MOREH תוקנו 11 פגמים על הדיסק, כל אחד עם הוכחה שנופלת על הקוד הישן
ועוברת על החדש. שלושה **לא נגעתי בהם**, כי הם משנים *מה* ערן לומד או *מה* אתה נשאל — וזה שלך.
**English:** 11 defects were fixed on disk with proofs. Three were **not touched**, because they change
*what ERAN is taught* or *what you are asked to judge*. Nothing below was applied.

---

## 1 · MOREH-1 — הסרגל מודד את עצמו / the ruler is its own metric

**עברית.** המספר של שער 2 (MOREH 5/24) נמדד **רק** על ידי `school-v2/ruler.py` — אותו סרגל אקוסטי
שכתבתי בעצמי ושייצר את כל 333 השיעורים שעליהם MOREH התאמן. המעגל סגור: המורה, התלמיד והבוחן הם
אותו כלי. שופט עברי עצמאי (wav2vec2-xlsr-53-espeak, `school-v3/gate3.json`) **סותר** אותו:
מתוך 134 רינדורים שהשופט קיבל, הסרגל מקבל רק **62 (46.3%)**, ועל ba, ka, qa, za — **0 מתוך 12**.
בכיוון השני: על da, fa, kha — שלוש מחמש ההברות ש-MOREH מקבל עליהן ציון — השופט לא שומע כלום
ב-300 ניסיונות (canon_conf 0.014, 0.0141, 0.365), בזמן שהסרגל מעביר 42.4% מ-da ו-73.7% מ-fa.
רק pa שורדת בבירור (113/300, conf 0.90); ka מעורפלת מול התאום שלה (ka:0.47 / qa:0.47).

**English.** Gate 2's headline is scored only by the ruler that generated the training corpus. An
independent Hebrew phoneme model refutes it on exactly the syllables MOREH is credited with.

**מה שאני מציע / what I propose** (לא בוצע / not done):
1. להריץ את `moreh/ruler.py` על eran2 עם **שני** שערים שווי-מעמד — הסרגל האקוסטי והשופט העברי —
   ולפרסם שתי עמודות + אחוז ההסכמה ביניהן. הקוד כבר מוכן לקרוא את קורפוס השופט (`--school v3`).
2. איפה שהם חולקים — **השופט מנצח** לכל דבר שיושמע לאדם. הסרגל נשאר מסנן מוקדם וזול.
3. **לא** לכוונן את חלונות הסרגל כדי שיסכימו — זה כיול-מחדש של המדד עצמו.

**מה שרק אתה יכול להכריע / only you can decide.** מי מהשניים קרוב יותר לאוזן שלך? שניהם מכונות.
46.3% אי-הסכמה מוכיח שלכל היותר אחד מהם צודק, ולא אומר מי. **ההצעה: A/B קצר** — לכל הברה, קליפ
שהסרגל אישר מול קליפ שהשופט אישר, בלי לומר לך מי מי. 12 הברות, שתי דקות. זה סוגר את השאלה שחוסמת
את כל השאר ב-MOREH.

---

## 2 · MOREH-4 — הישיבה העיוורת מחכה 3 ימים, ואין מי שיקרא את הקול / an act that never returns

**עברית.** בסוף השרשרת עומדים 24 קבצי `ERAN-<הברה>-loo.wav` שמוגשים לאוזן שלך ב-
`http://127.0.0.1:8856/`. **`iddo-verdicts.jsonl` מכיל 0 שורות לישיבה `school-v2-20260903`** אחרי
שלושה ימים — בזמן שבאותו קובץ יש 14 שורות ל-`school-20260903`, 22 ל-`sitting3-20260903`
ו-28 ל-`loop-20260903`. כלומר שפטת באותו יום, פשוט לא את הדף הזה. הדף עצמו חי (pid 12540, מאזין
עכשיו) — הבעיה היא הפסקים, לא השרת.
וגם אם היית מצביע: **אף שורת קוד ב-MOREH לא קוראת את הקובץ הזה.** `verdict|iddo|8856|judging` מופיע
פעם אחת בכל האיבר, בתוך docstring. כל פלט של המודל הוא מעשה שלא חוזר.

**English.** The blind sitting has zero verdicts after three days, and no MOREH code path reads
verdicts anyway. Asking for your ear right now spends the metric and returns nothing.

**מה שאני מציע / what I propose** (לא בוצע / not done):
1. **קודם לבנות את דרך החזרה, ואז לבקש את האוזן.** קורא ש-`iddo-verdicts.jsonl` → תווית לכל הברה
   ("הקליפ של ערן נבחר" / "אף אחד לא טוב") → משקל בקורפוס, או פסילה של חלון בסרגל.
2. **איפה הדף יושב:** לקפל אותו לתוך MAKOM (:8858) שאתה כן פותח, במקום דף בודד ב-8856 שאף אחד לא רואה.

**מה שרק אתה יכול להכריע / only you can decide.** האם אתה רוצה בכלל את הישיבה הזאת עכשיו, ואיפה.
אני לא בונה עוד דף שיחכה שלושה ימים בלי שתגיד.
*(שים לב: לפי MOREH-13 למטה, חצי מהקליפים בישיבה הזאת ממילא לא ראויים לשיפוט.)*

---

## 3 · MOREH-13 — חצי מ"המורה" בישיבה העיוורת אינו האות / half the gold is not the letter

**עברית.** בכל סיבוב אתה שומע שני קליפים: אחד של ערן, ואחד "של המורה" שנבחר אקראית מתוך
`school-v2/lessons/CLAUDE-<הברה>-v*.wav` — כלומר אושר רק על ידי אותו סרגל אקוסטי.
לפי `school-v3/gate3.json`, **ל-12 מתוך 24 ההברות אין ולו רינדור אחד** מבין 300 ניסיונות שהשופט
העברי מזהה כאות: va, ga, da, ha, wa, cha, ta, sa, fa, tza, sha (0/300 כל אחת) ו-ra (2/300).
ב-fa הביטחון הכי טוב מתוך 300 היה **0.0141**. כלומר בסיבובים האלה אני מבקש ממך לבחור בין שני
צלילים שאף אחד מהם אינו האות.

**English.** For 12 of 24 syllables the "teacher" clip is one no independent Hebrew judge can hear as
that letter. Those rounds ask you to choose between two wrong sounds.

**מה שאני מציע / what I propose** (לא בוצע / not done):
- לבנות מחדש את הישיבה כך שקליפ ההשוואה יהיה כזה **שהשופט העברי קיבל**
  (`school-v3/lessons/CLAUDE-<הברה>-judge-vNN.wav`), ולהוריד — או לסמן בבירור — את 12 ההברות שאין
  להן קליפ כזה.

**מה שרק אתה יכול להכריע / only you can decide.** זה משנה **את מה שאתה נשאל**, ולכן אני לא נוגע
בישיבה בלי מילה ממך. אפשרויות: (א) ישיבה של 12 הברות עם זהב אמיתי; (ב) 24 עם סימון ברור מי מהן
"אין זהב"; (ג) להשאיר כמו שהיא ולראות מה האוזן שלך אומרת על הפער.

---

## ומה כן תוקן, כדי שתדע מה השתנה בלי אישורך / what WAS fixed

11 פגמים, כולם על הקוד בלבד, אף תהליך חי לא הופסק ולא אותת:
MOREH-2 (למבדה שנבחר על מדד התוצאה — 15/24 → **13/24**), MOREH-3 (הרצפה קיבלה 14 עמודות מול 49),
MOREH-5 (הקורפוס של השופט העברי היה על הדיסק ואף אחד לא קרא אותו), MOREH-6 (קריסה נספרה כצליל רע),
MOREH-7 (חציון על שורות מתות: c_area 2.0 במקום 0.167), MOREH-8 (החלטה לא-חוקית שוכתבה בשקט),
MOREH-9 (טעות הקלדה בשם הברה הריצה ישיבה מלאה), MOREH-10 (המפתח של הישיבה נטען פעם אחת ונמחק),
MOREH-11 (התקרה 33.5% → **26.7%** מהיומן), MOREH-12 (קורפוס שנעלם היה "ירוק"), MOREH-14 (אף אחד
לא כתב ולא קרא את המשקלים).

הפירוט וההוכחות: `D:\CLAUDE\_deliverables\code-revision\moreh-proofs\`, ו-`holobrain/moreh/STATUS.md`.
