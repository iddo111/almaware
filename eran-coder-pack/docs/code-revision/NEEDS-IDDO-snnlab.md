# NEEDS-IDDO — snnlab (eran4:~/snn-lab) — 2026-09-06

> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

**אחד מ-13 הליקויים במעבדת ה-SNN לא תוקן — הוא מחכה למילה שלך.**
**One of the 13 defects in the SNN lab was NOT fixed. It waits for your word.**

---

## SNN-1 — המעבדה מתאמנת על דיבור מסונתז וקוראת לו "הקול של עידו"
## SNN-1 — the lab trains on synthesised speech and calls it Iddo's voice

**מה מצאתי / What I found**

`eran4:~/snn-lab/corpus-syllables/manifest.json` אומר על עצמו, במילים שלו:

```json
"source": { "model": "facebook/mms-tts-heb", "tokenizer_vocab_size": 33,
            "generator": "D:/CLAUDE/ant-wall/make_curriculum.py" },
"labels_are_provenance_only": true
```

224 רינדורים בסיסיים × 3 אוגמנטציות (WSOLA טמפו 0.9–1.1, גיין, רעש ורוד/לבן, ריפוד) = 528 קבצי אימון+מבחן. **זה VITS TTS. זה לא אתה.**

ובכל זאת, `train.py` שורה 11 כותב בתיעוד שלו:

```
  syllables  Iddo's own 22 Hebrew syllables, heard through the SAME frozen
             cochlea ERAN wears
```

ו-`page.html` מציע בתפריט: `22 ההברות של עידו — syllables`.
ו-`results/ERAN-vs-SNN-VERDICT-2026-08-21.md` מפרסם על הבסיס הזה: **"ERAN 69.44% vs SNN 61.11%"** ו-**"SNN (published) 84.09%"**.

**המבחן בן 132 הפריטים כאן הוא בדיוק אותו מבחן שהאוזן שלך פסקה עליו 0/10 ב-3.9.2026.**

The corpus is machine-synthesised (`facebook/mms-tts-heb`, a VITS TTS), its own manifest says the labels are provenance only, and the code calls it "Iddo's own 22 Hebrew syllables" in three places while publishing a verdict about ERAN on it. That 132-item heldout is the same exam your ear scored 0/10 on 2026-09-03.

**למה לא נגעתי / Why I did not touch it**

חוק "עידו מאמן את קלוד, קלוד מאמן את ערן": מה שהמודל אוכל ואיך הוא מתויג — זו המילה שלך, לא שלי. לא שיניתי אף תווית, לא הזזתי אף קובץ אודיו, ולא כיביתי שום מספר.
Nothing about what a model is fed or how it is labelled changes without your word. No label, no wav, no published number was touched.

**מה מוכן ליישום ברגע שתגיד / Ready to apply the moment you say so** (ארבע פעולות, אף אחת לא נוגעת באודיו):

1. **`load_syllables()` יקרא את `manifest.json` ויסרב לרוץ** אם `source.model` הוא TTS ואין דגל אישור מפורש בקונפיג — כך שאי אפשר יותר לפרסם מספר בלי לדעת על מה הוא נמדד.
   Refuse to run on a TTS corpus without an explicit acknowledgement flag.
2. **חותמת מוצא בכל קובץ תוצאות ובכל אירוע `start`**: `corpus_source`, `generator`, `labels_are_provenance_only`.
   *(חלקי: כבר עשיתי את זה כתופעת לוואי מוצדקת של SNN-8/SNN-9 — `cochlea.manifest_provenance()` קיים והשדה `corpus_provenance` נכתב היום בכל תוצאה. מה שנשאר הוא הסירוב עצמו.)*
   Provenance is already stamped into every results file; what remains is the refusal.
3. **שורת המוצא תודפס מעל שורת הסיכוי** בכל ריצה: "corpus = facebook/mms-tts-heb synthesis, labels are provenance only".
4. **תיקון ה-docstring וה-UI** — "synthesised mms-tts-heb", לא "Iddo's own". שתי שורות טקסט.

**השאלה האמיתית / The real question**

האם המעבדה הזאת צריכה בכלל להצביע על ה-TTS, או להיות מכוונת מחדש להברות האנושיות מ-FLEURS (7,388 הברות אנושיות אמיתיות, `project_eran_food_fleurs`)?
לפני שמפרסמים עוד מספר אחד מהמעבדה הזאת — **זו החלטה שלך**.
Should this lab be re-pointed at the FLEURS human syllables before any further number is published? Your call.

---

## מה כן תוקן היום (12 ליקויים + 1 שנמצא תוך כדי)
## What WAS fixed today (12 defects + 1 found on the way)

הכל על הדיסק, עם גיבוי `.bak-rev-20260906` וסקריפט הוכחה שנכשל על הגיבוי ועובר על התיקון.
**שום תהליך לא הופעל מחדש, לא נעצר ולא נשלח אליו סיגנל.** `snnlab.service` PID 2530 חי מ-1.9 ולא זז.
Everything on disk, each with a backup and a proof script that FAILS on the backup and PASSES on the fix. No process was restarted, stopped or signalled.

| # | מה | לוקח אפקט |
|---|---|---|
| SNN-2 | פיצול ה-dev דלף 96.6% (85 מתוך 88 פריטים היו אוגמנטציות של קבצי האימון) → פיצול לפי רינדור בסיסי, 0 דליפה | מיד (`sweep.py`) |
| SNN-3 | 20 ריצות, אפס משקולות שמורות → checkpoint + `--load` + `predict()` | בריצה הבאה |
| SNN-4 | `hidden_rate` נכתב 0.0 ("רשת מתה") לכל ריצה שנעצרה → ממוצע אמיתי לאפוק, ודגל `dead` שחוסם ורדיקט | בריצה הבאה |
| SNN-5 | `best_test_acc` = עצירה מוקדמת על המבחן, פורסם כציון → הציון הוא `final`, ה-best מסומן אורקל | בריצה הבאה |
| SNN-6 | מאכל ריק ייצר ריצה "מוצלחת" (בדיוק הצורה שכמעט הרעיבה את ערן) → זורק חריגה | בריצה הבאה |
| SNN-7 | `POST /api/start` ללא שום אימות ב-0.0.0.0:8821 → מפתח משותף + תקרת GPU | **בהפעלה הבאה של השירות** |
| SNN-8 | ה-cache הוחזר בלי קשר למאגר → טביעת אצבע של המאגר, נבנה מחדש כשמשתנה | מיד (ה-cache כבר הוחתם) |
| SNN-9 | בסיסי ההשוואה היו ליטרלים קפואים בלי תאריך → `baselines.json` עם תאריך ומאגר, וסירוב להשוות כשהמאגר שונה | מיד |
| SNN-10 | ה-gain 13.86 היה ליטרל → נגזר מהנתונים (נמדד 13.8564) | בריצה הבאה |
| SNN-11 | חוט קריאה דלף בכל ריצה ויכל לחתום שגיאה על ריצה אחרת | בהפעלה הבאה |
| SNN-12 | 45MB ב-runs/ בלי גיזום → גיזום לפי מספר + gzip | בהפעלה הבאה |
| SNN-13 | `words/` — 96 קבצים שאף אחד לא טען → מבחן שני עם 12 מחלקות משלו | בריצה הבאה |
| **EXTRA-1** | `evaluate()` החזיר דיוק של **4.0** (400%) כשיש `limit` — כל ריצת MNIST דיווחה דיוק אימון מנופח | בריצה הבאה |

**מפתח הגישה החדש / the new key:** `eran4:~/snn-lab/.snnlab_token`. אחרי ההפעלה הבאה של השירות, כפתור "התחל אימון" ידרוש אותו פעם אחת (הדף שומר אותו בדפדפן). *הצפייה נשארת פתוחה — רק ההפעלה והעצירה נעולות.*
