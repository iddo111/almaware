> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# NEEDS-IDDO — holobrain / zivug · ZIV-15

**קוד רוויזן 2026-09-06 · code revision 2026-09-06 · claude-cli-REV-holobrain_zivug**

---

## שורה אחת / One line

**HE —** `ear-human.npz` נקרא "אנושי" ואף לא דבר אחד בדיסק מוכיח את זה. אין מניפסט, אין
נתיב wav, אין מזהה דובר, אין סקריפט שיצר אותו — רק צרכנים. אחרי משבר הקורפוס של 3.9 (מה
שנקרא "אנושי" התגלה כ‑TTS), **אני לא קובע לכאן ולא לכאן.** אוזנך היא הפוסקת.

**EN —** `ear-human.npz` is called "human" and nothing on disk establishes that. No
manifest, no wav path, no speaker id, no generator script — only consumers. After the
09-03 corpus crisis (the corpus believed to be human turned out to be TTS), **I am
deliberately not asserting it either way.** Your ear rules.

---

## מה נמדד / What was measured

| | |
|---|---|
| קובץ / file | `D:\CLAUDE\eran-brain\holobrain\ear-human.npz` — 281,712 B, mtime 2026-08-30 21:40 |
| מפתחות / keys | `V (396,192) float32`, `y (396,)`, `t (396,)`, `syllables (22,) <U3`, `takes (6,) <U3` |
| מה שאין / what is absent | לא נתיב, לא שם קובץ, לא דובר, לא קצב דגימה · no path, no filename, no speaker, no sample rate |
| מבנה / structure | 22 הברות × 6 takes × 3 קליפים — **132 תאים, בכולם בדיוק 3.** אפס תאים חסרים |
| יצרן / producer | `grep` על כל `eran-brain` מוצא **רק צרכנים**: zivug, ruler/ruler.py, ruler/target.py, ruler/verdict.py, ruler/whose_voice.py, winston/gaze.py, nezer |

**המספרים שמדדתי בעצמי (numpy בלבד, קריאה בלבד):**

    אותה הברה, אותו take        cos 0.9253
    אותה הברה, take אחר         cos 0.8023
    הברות שונות                 cos 0.5638

**HE —** ה־`take` נושא זהות חזקה — בדיוק כמו גרון אחר, או כמו קול TTS אחר. `whose_voice.py`
נכתב כדי לשאול את השאלה הזאת בדיוק ("האם take הוא גרון אחר") **והתשובה שלו לא נמצאת בעץ.**

**EN —** `take` carries a strong identity — exactly like a different throat, and exactly
like a different TTS voice. `whose_voice.py` exists to ask precisely that question, and
its answer is nowhere in the tree.

---

## למה זה נושא את כל המשקל / Why this is load-bearing

**HE —** ההנחה של `zivug.py` שורה 24 היא: *"the same SYLLABLE in a different mouth → the
same place"*. אם ה־takes הם קולות TTS, זה לא **פה אחר** — זה אותו מנוע עם seed אחר, וכל מה
שנמדד כאן איננו מה שנטען. הפער 22.7 נקודות בין ה־takes (92.4% עד 69.7%) הוא בדיוק מה שהיה
נראה אילו חלק מה־takes היו קולות ברורים יותר של אותו מנוע.

**EN —** `zivug.py:24` rests on *"the same SYLLABLE in a different mouth → the same
place"*. If the takes are TTS voices, that is not a different mouth — it is one engine
with a different seed, and nothing measured here is what is being claimed. The 22.7-point
spread across takes (92.4% down to 69.7%) is also what you would see if some takes were
simply cleaner renderings from one engine.

**רשת 22×6×3 מושלמת בלי תא חסר אחד היא איך שנראית רשת סינתזה, לא איך שנראית הקלטה אנושית.**
*A perfectly complete 22×6×3 grid with not one missing cell is what a synthesis grid looks
like, not what a human recording session looks like.*

---

## מה עשיתי ומה לא / What I did and did not do

- ❌ **לא נגעתי בקורפוס. לא שיניתי תווית. לא הרצתי כלום עליו.**
  *Did not touch the corpus, did not relabel anything, did not run anything on it.*
- ✅ קריאה בלבד: מפתחות, צורות, mtime, ו־cosines שחישבתי ב־numpy.
  *Read-only: keys, shapes, mtime, and cosines computed in numpy.*
- ✅ שאר 15 הליקויים בשרשרת תוקנו בדיסק עם הוכחות. רק זה מחכה לך.
  *The other 15 defects in this chain are fixed on disk with proofs. Only this waits.*

---

## ההצעה / The proposal — three steps, none of them without your word

1. **מניפסט ליד ה־npz / a manifest beside the npz.**
   `ear-human.manifest.json`, שורה אחת לכל קליפ: נתיב ה־wav המקורי, דובר או מנוע TTS,
   קצב דגימה, וגרסת האוזן שקידדה אותו. *One row per clip: source wav path, speaker or TTS
   engine, sample rate, and the ear version that encoded it.*
2. **`zivug.py` יסרב לרוץ בלי מניפסט / refuse to run without it** — אותה צורה בדיוק כמו
   שומר ה־eye.pt שהוספתי היום ב־ZIV-01: לא להריץ ולא לדווח מספר על קורפוס שאין לו מקור.
   *The same shape as the eye.pt guard added today: no run and no number quoted on a
   corpus with no provenance.*
3. **אם היצרן לא קיים — `whose_voice.py` על ה־6 takes, ואוזנך על הפלט.**
   *If no generator survives, run `whose_voice.py` over the six takes and put its output in
   front of your ear — blind, as with the 09-03 exam.*

**עד אז: אף מספר מהשרשרת הזאת לא נאמר בשמו של "אנושי".**
*Until then: no number from this chain is quoted as "human".*

---

## אחת השאלה שאני צריך ממך / The one question

> **האם ה־396 הקליפים ב־`ear-human.npz` הם הקלטות של בני אדם, או TTS?**
> **Are the 396 clips in `ear-human.npz` human recordings, or TTS?**
>
> ואם אתה לא זוכר — זו תשובה טובה בדיוק כמו כן או לא, והיא אומרת שהמניפסט חייב להיבנות
> לפני שמישהו מצטט שוב מספר מכאן.
> *And "I do not remember" is as good an answer as yes or no — it means the manifest has
> to be built before anyone quotes a number from here again.*
