> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it is not working, mark it broken and prove the real output before calling it complete.

# פרויקט שלמה / Project Shlomo

פרויקט־העל של ALMAWARE ללמידה מקורקעת של תקשורת בעלי־חיים, על שם
שלמה המלך. המערכת אינה מתחילה ממילון אנושי ואינה מניחה שכל קול הוא
"מילה". היא לומדת מתוך רצף מסונכרן:

`חישה → אות/קול → פעולה של המערכת → תוצאה בעולם → תגובת בעל החיים`

## העץ הקנוני

1. **Ant Farm / חוות הנמלים**
   - Proto‑Yigael + Proto‑Eran + Proto‑Baby‑Cave.
   - חברה סגורה של לומדים קטנים שמתחילים ממשקלים אקראיים.
   - קול לפני כתב: קשקוש → תנועות → הברות → צירופים → משמעות מקורקעת.
   - אינטראקציות, קשרים, דורות ונורמות של המושבה.

2. **Alma Cat Feeder / מאכיל החתולים עלמה**
   - מצלמה, מיקרופון, רמקול, מסך, מזון ומים.
   - לומד להבדיל בין הקשרים כגון מזון, מים, קִרבה, איום והמתנה מתוך
     תוצאות אמיתיות—לא מתרגום ידני של "מיאו".
   - דמות חתול על המסך היא ממשק; Yigael יכול להחליף גוף/דמות בלי
     להחליף את ליבת הלמידה.

3. **Bird/Dove Feeder / מאכיל ציפורים ויונים**
   - תצפית קולית־חזותית ופעולת האכלה מדודה.
   - אותו learning core, עם species adapter לחושים ולהתנהגות של ציפורים.
   - העמוד החיצוני Smart Birdfeeder הוא reference לחומרה ולתפעול בלבד;
     אין העתקת קוד ממנו.

4. **Future species**
   - עטלפים, דבורים, קופים, דולפינים ולווייתנים—רק לאחר שהלולאה
     המקורקעת הראשונה עוברת acceptance.

## חוזה המוח

- משקלים אקראיים בתחילת הניסוי.
- audio-first; אין אותיות, תמלול או tokenizer טקסטואלי בשלבי הינקות.
- אין LLM חיצוני בתוך לולאת הלמידה הקנונית.
- כל טענה על "משמעות" חייבת לנבא תוצאה או התנהגות חדשה בנתוני holdout.
- זיכרון, זהות ודורות מתועדים בנפרד ממשקלי הבסיס.

## נכסים קיימים

- `D:\CLAUDE\eran-audio` — מוח אודיו מאפס, checkpoints ו־babble WAVs.
- `D:\CLAUDE\eran-audio\grounded_ah` — ניסוי grounding של `/a/`;
  חלק מחיישניו עדיין placeholders.
- `D:\CLAUDE\eran-recroom` — סביבת משחק/גוף וירטואלית.
- `D:\CLAUDE\ant-farm` — GUI טקסטואלי שנבנה ב־2026-07-25.
  המוח Qwen שבו הוא demo bridge בלבד ואינו המוח הקנוני.

## Acceptance ראשון

הניסוי הראשון ייחשב עובד רק כאשר:

1. אירועי אודיו/וידאו וחיישני מתקן נרשמים עם clock משותף.
2. המודל מאפס בוחר פעולה אמיתית, כגון מנת מזון או מים.
3. תגובת בעל החיים נרשמת לאחר הפעולה.
4. המודל מנבא טוב יותר מ־baseline איזו פעולה או תוצאה תבוא בהמשך,
   על session או בעל־חיים שלא שימשו לאימון.
5. ניתן לשחזר את הניסוי מהלוג וה־checkpoint ללא תיוג בדיעבד.

---

Project Shlomo is the canonical grounded animal-communication program. Ant Farm
is its social-development prototype; Cat and Bird Feeders are real-world
grounding stations. The canonical learner starts from random weights and sound,
not from a pretrained language model.
