# DARWISH — מה מחכה לעידו / what waits for Iddo

> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

**קוד רוויזן DARWISH, 2026-09-06 — claude-cli-REV-darwish.**
7 מהפגמים תוקנו על הדיסק עם הוכחה. 5 לא נגעתי בהם — הם משנים **מה הציפור אוכלת**, **מה נחשב אמת**, או **אם היא בכלל צריכה לרוץ**. אלה החלטות שלך, לא שלי.
*Seven defects fixed on disk with proofs. Five untouched — they change what the bird is FED, what counts as TRUTH, or whether it should be running at all. Your call, not mine.*

**אף תהליך חי לא הופסק, לא הופעל מחדש ולא קיבל סיגנל.** dmidi-life PID 586989 ו-dmidi-tap PID 586990 עדיין רצים מ-2026-09-02 04:49:34. התיקונים הם **רשת לאתחול הבא** — הקוד שרץ עכשיו בזיכרון הוא הישן.
*No living process was stopped, restarted or signalled. The fixes take effect at the NEXT restart, whenever you choose it.*

---

## DW-06 — ⚖️ ההחלטה הראשונה: שיירוץ בכלל? / should DARWISH be running at all?

**עברית.** ב-24.8 הורית לעצור את דרוויש ("ערן לוקח את eran4"). זה בוצע כ-`stop` ולא כ-`disable`, ולכן **האתחול של 2.9 החזיר אותו לחיים בניגוד להוראה שלך**. מאז הוא שורף 30% ליבה ו-~46 GB כתיבות ביום על מכונה עם 0 GB זיכרון פנוי — ולא משיג כלום, כי הוא לא שר (DW-01).
*You ordered DARWISH stopped on 08-24. It was stopped but left ENABLED, so the 09-02 reboot revived it against your order. It has burned 30% of a core and ~46 GB/day of checkpoint writes ever since, achieving nothing.*

הראיה / evidence: `PAUSED-20260824.txt` = "stopped 2026-08-24T02:16:08Z by Iddo order"; `systemctl --user is-enabled dmidi-life dmidi-tap` → `enabled enabled`; journal: Stopping 08-24 05:15:46 → `-- Boot d028a010 --` → Started 09-02 04:49:35.

**שתי אפשרויות / two options:**
- **לא רוצה אותו עכשיו** → `systemctl --user disable dmidi-life dmidi-tap` (רק disable — הוורקפלואו הזה לא עוצר תהליך חי), וההערה ב-PAUSED נשארת נכונה.
- **רוצה אותו** → למחוק/לעדכן את PAUSED-20260824.txt, ואז התיקונים של DW-01/02/04/07 נכנסים לתוקף באתחול.

**בשני המקרים** כדאי להוריד את קצב הכתיבה: היום נשמר `brain.json.gz` (27 MB) אחרי **כל ארוחה** — ~1,700 פעם ביום. לשמור לפי זמן (כל 10 דק') או לפי שינוי מסה. זה שינוי קוד קטן שאעשה ברגע שתגיד.

---

## DW-03 — 📏 הסרגל של המבקר הוא הטלת מטבע / the critic's ruler is a coin-flip

**עברית.** ה"סט-פוינט" שמודד אם הבס-דראם נופל על הפעימה הוא **0.2535 / 0.2510 / 0.2489** — ואקראי גמור זה 0.25. מדדתי: סיבוב מקור-התיבה ב-1/2/3 צעדים נותן בדיוק את אותם מספרים. כלומר הסרגל **לא מבדיל בין הרשת הנכונה לרשת שגויה**, ובכל זאת `kick_bit` נבחר לפיו בהפרש של 0.003. השיר היחיד שנשפט אי-פעם קיבל 0.954 מול סרגל כזה.
*The kick/downbeat set-point is indistinguishable from chance (0.25). Rotating the bar origin by 1, 2 or 3 steps gives the same numbers — the ruler cannot tell the real grid from a wrong one. The one song ever judged scored 0.954 against it.*

**מה שאני יכול לעשות מיד (רק אם תאשר) / the code net, on your word:** שהמבקר **יסרב לחמש** מדד שנמצא בתוך רעש של אקראי — לחשב פיזור בין השירים, ואם `|ממוצע − 0.25| < 3σ` לכבות את המדד ולרשום `critic: kick set-point = chance, term off`; ולבחור את `kick_bit` לפי אוטוקורלציה בפיגור 4, לא לפי המקסימום. **לא נגעתי ב-critic.py** כי כיבוי מדד משנה איך הציפור נשפטת.

**מה שדורש אותך באמת / what genuinely needs you:** אם הבעיה היא הטוקניזציה עצמה (הפסי-תופים או מקור התיבה ב-`midi_lean.py`), התיקון הוא **טוקניזציה מחדש** = לשנות את המזון של דרוויש. זה לא קורה בלי המילה שלך.

---

## DW-08 — 🎭 זמרים אחרים בשם דרוויש נכנסו לאימון / impostor artists in the TRAIN split

**עברית.** מסנן השמות מכניס אמנים אחרים בשם Darwish ל-**train** של שתי השרשראות (גם האורגניזם וגם הרשת הנוירונית): לפחות **Dario Darwish** (פלמנקו-עוד ערבי, נאכל בפעימה 1 של feed-all), **Ben Darwish - Live**, ו-**Darwish Rasooli**. ההערה בקובץ טוענת שיש בדיוק שלושה מתחזים ושהם הוסרו — לא נכון.
*The name filter admits other artists called Darwish into the TRAIN split of both chains. `klass()` only tests SPEECH, 'bassel', YINON and bpm<=120.5.*

**למה זה NEEDS-IDDO:** לתקן = לבנות מחדש את `split.json` = **לשנות מה דרוויש אוכל** ולשנות את משמעות מספרי ה-heldout. לפי חוק "עידו מאמן את קלוד, קלוד מאמן את ערן" — אני לא נוגע.
**רשת קוד שכן אפשר להוסיף מיד:** ש-`make_split.py` ידפיס דו"ח "אמן חשוד" (כל שם שהטוקן שלו אינו `darwish` לבדו) כדי שהפיצול הבא לא יכניס אותם בשקט. תגיד מילה ואוסיף.

---

## DW-10 — 👂 שרשרת ה-v2 מאומנת על תוויות שאף אוזן לא אישרה / v2 trains on labels no ear has checked

**עברית.** האימון הנוירוני (poly, vocab 138) לומד ונמדד על **תמלול מכונה** של האקורדים — `poly_hear.py` עצמו מודה: recall 0.70–0.72 של תווי אקורד. ה-"exact_recall 1.0" ב-`hear_test` הוא `decode(encode(score))` מול `score`, כלומר **הפיכות של הטוקנייזר, לא דיוק של אוזן**. בנוסף שני ה-seeds חלקו סדר-דאטה זהה (`MidiCorpus` מקבע seed=1337), והצ'קפוינטים לא מוזרמים לשום מקום — אין `.wav`/`.mid` חדש מ-09-05 16:36.
*The v2 chain trains and evaluates on machine-transcribed labels no human has verified; both long-run seeds shared one data order; the checkpoints feed nothing that plays.*

**מה שמחכה לך:** יש A/B עיוור על **127.0.0.1:8884** (1,500 צעדים מול 30,000) ועוד אחד ב-**:8867**. **אין שום פסק דין שלך על אף אחד מהם ב-500 ההודעות האחרונות ב-RAMCHAT.** בלי האוזן שלך אסור לקרוא לזה "מודל של דרוויש".
**תיקון קוד שאעשה מיד כשתאשר:** להעביר `--seed` גם ל-`MidiCorpus` כדי ששני seeds יהיו באמת שני ניסויים.

---

## DW-05 — 🖐️ ערוץ האבא ריק מלידה / the father's channel has never carried a signal

**עברית.** אף הקשה לא נכתבה מעולם (`feedback/inbox` ריקה), אף trace לא שולם, ודף ה-tap ב-:8806 עדיין מציג רק את שלושת השירים של 21.8. זה **תוצאה של DW-01** — לא היה מה לשמוע. ברגע שהציפור תשיר (אחרי אתחול), הדף יתמלא.

**מה שצריך ממך:** רק להחליט אם אתה רוצה שהדף יגיע אליך. הוא נפתח כאן: **http://<lan-ip>:8806/** — אם תרצה, אשים קיצור-דרך על שולחן העבודה. שתיקה נשארת ניטרלית לפי התכנון, לא שלילית.

---

## מה כן תוקן (לרקע) / what WAS fixed — nets for the next restart

| id | מה היה | התיקון |
|---|---|---|
| DW-01 | הציפור **לא יכולה** להגיע לשובע: אוכלת רק מתחת ל-0.4, ארוחה נותנת ≤0.15, שירה דורשת 0.8. 12,092 ארוחות, **שיר אחד**, 16 יום. | היסטרזיס האכלה + שער אתחול שמסרב לגנום כזה + תקרת קצב שירים + סבב outbox + אזהרת "לא שר". |
| DW-02 | argmax על ניקוד שלא יורד → **11,724 מתוך 12,092 ארוחות היו אותו טראק**. | הארוחה **מוגרלת** (softmax בטמפרטורת מצב-רוח), חסימת חזרה, תקרת 50% לשארד, היסטוגרמת דיאטה בלוג. |
| DW-04 | סרוטונין זז רק מהקשה אנושית → קבוע 0.5 לאורך כל החיים, טמפרטורה קבועה 1.0. | פסק הדין של המבקר עצמו מזיז את מצב הרוח (ברווח 0.3) + אזהרה אם הוא לא זז. |
| DW-07 | שורה ביומן בכל פעימה: 237 MB, 99.3% מהן ריקות. | אירועים + פעימת-לב פעם בדקה + סבב יומי. |
| DW-09 | בדיקת הקורפוס קפאה על `== 191` בזמן שיש 323 → **כל חבילת הבדיקות** נקראה כנכשלת. | הספירה נגזרת מ-`split.json`; חוק הפער 17/18 נבדק על **כל** 323 הקבצים (0 חריגות). |
| DW-11 | תשלום הקשות עשה `rename` לקובץ שתהליך אחר מוסיף אליו → הקשה נבלעת, רשומה נמחקת. | תשלום לפי סמן (cursor), הקובץ לא זז לעולם. |
| DW-12 | תקרת גודל הקובץ לא נאכפה: השומר קרא לגיזום שרץ רק מעל 1.9M סינפסות. | גיזום לפי **גודל** היעד, עם לוג לפני/אחרי. |

כל תיקון עם סקריפט הוכחה ב-`~/darwish-midi/proof/proof_DW-*.py` שנכשל על הגיבוי ועובר על הקוד החדש. גיבויים: `*.bak-rev-20260906`. מראה PC: `D:\CLAUDE\darwish-midi` (זהה בית-בית).
