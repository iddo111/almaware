# NEEDS-IDDO — KAV / קָו, code revision of 2026-09-06

> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

**עידו — דבר אחד ממתין לך ב-KAV, ולא נגעתי בו. / Iddo — one thing in KAV waits for you, and I did not touch it.**
זה משנה **מה האורגן אוכל**, וזה החוק שלך: כלום לא נכנס למזון בלי המילה שלך.
*It changes WHAT THE ORGAN EATS, and that is your law: nothing enters the food without your word.*

---

## KAV-17 — שלושה מֶשים מ-EINAYIM יושבים בתיקייה של KAV ולא מחוברים לכלום
## KAV-17 — three meshes from EINAYIM sit in KAV's own folder, wired to nothing

**איפה / Where:** `D:\CLAUDE\eran-brain\holobrain\kav\from-einayim\`
**מתי הגיעו / Dropped:** 2026-09-03 20:18 — **three days ago**
**מה יש שם / What is there:** 267 KB, three binary STLs + a README

| file | views the model got | faces | depth error vs truth |
|---|---|---|---|
| `einayim-organs-8views.stl` | 8 | 1,996 | median abs-rel 0.38 % |
| `einayim-organs-2views.stl` | 2, 21° apart | 1,893 | median abs-rel 0.57 % |
| `einayim-dropfolder-autocrop.stl` | 8, auto-isolated | 1,449 | the honest worse comparison |

ה-README שלהם שואל את השאלה בעצמו ומשאיר אותה פתוחה, במילים האלה:
*Their own README poses the question and leaves it open, in these words:*

> "nothing here is wired into `learn.py` or `joiner.py` yet. That is a decision for
> whoever owns KAV." … "the first honest question is whether an OPEN surface belongs
> in a corpus whose grammar is about solids."

**זו החלטה שלך, לא שלי. / That decision is yours, not mine.** `mesh.our_corpus()` לא מזכיר
את הנתיב הזה בכלל.

---

## מה מדדתי היום, כי ההערכה שהיתה רשומה היתה **לא נכונה**
## What I measured today, because the recorded assumption was **WRONG**

היה כתוב שאפשר להשאיר אותם בחוץ כי `intact_only` תדחה אותם ממילא. **מדדתי — היא לא.**
*It was assumed they could be left out because `intact_only` would reject them anyway.
**Measured — it does not.***

```
einayim-organs-8views.stl    1,996 faces  |  Q=128 grid dropped 0  ->  954 vertices
einayim-organs-2views.stl    1,893 faces  |  Q=128 grid dropped 0  ->  970 vertices
einayim-dropfolder-autocrop  1,449 faces  |  Q=128 grid dropped 0  ->  668 vertices
```

* **הרשת לא שוברת אותן בכלל — 0 פאות נופלות.** אז `joiner.intact_only` **תשמור** אותן,
  והן ילמדו את החיבור. *The grid does not break them at all — 0 faces dropped. So
  `intact_only` would **KEEP** them and they WOULD teach the joining.*
* **הן לא סגורות:** 177 / 225 / 314 קצוות בודדים. הדקדוק של KAV כולו על גופים סגורים.
  *They are not closed: 177 / 225 / 314 lone edges. KAV's whole grammar is about closed solids.*
* **668–970 קודקודים מול `NEAR=64`.** כמעט כל שאלה תיפול מחוץ להישג היד של הדקדוק.
  *668–970 vertices against `NEAR=64`: almost every question falls outside the grammar's reach.*
  עד היום זה היה **מסוכן בשקט** — שאלה מחוץ להישג נמחקה מהמכנה, כלומר הדיוק היה **עולה**
  ככל שההישג מחמיר. **תיקנתי את זה היום (KAV-09)**, אז עכשיו הן היו נספרות כטעויות.
  *Until today that was silently dangerous — an out-of-reach question was dropped from
  the denominator, so accuracy went UP as reach got worse. **Fixed today (KAV-09)**, so
  now they would count as misses.*
* **הן היו מציפות את שער 1:** 2,004 + 2,910 + 2,862 = **7,776 פריימים** מול 2,379 באימון
  היום. *They would flood gate 1: 7,776 frames against today's 2,379 training frames.*
  (תיקון KAV-07 של היום נותן לכל **צורה** קול אחד, אז ההצפה כבר לא אוטומטית — אבל עדיין
  שלוש צורות פתוחות מול תשע-עשרה סגורות. *Today's KAV-07 gives every SHAPE one vote, so
  the flood is no longer automatic — but it is still three open surfaces against nineteen
  closed ones.*)

---

## ההמלצה שלי (המלצה בלבד — לא ביצעתי כלום)
## My recommendation (a recommendation only — I did nothing)

**אל תכניס אותן לקורפוס של המחבר.** *Keep them OUT of the joiner's corpus.*
הן היו מלמדות את KAV לחבר משטח פתוח, וכל השערים שלו שואלים "האם זה גוף סגור".
*They would teach KAV to join an open surface, and every one of its gates asks
"is this a closed solid".*

**במקום זה: שער 0b.** אורגן שראה תמונה צריך מקום להיבחן בו — אבל על החצי שיודע לענות:
חצי הקואורדינטות בלבד (`ruler.measure`), בלי `closure`, בלי "watertight".
*Instead: a gate 0b. A photo-derived mesh deserves somewhere to be scored — but only
on the half that can answer: the coordinate half alone, no closure, no watertight test.*

זה כ-30 שורות ואני יכול לכתוב את זה מתי שתגיד. **לא כתבתי, כי זה משנה מה הוא אוכל.**
*That is about 30 lines and I can write it whenever you say. **I did not write it,
because it changes what he eats.***

---

## ועוד דבר קטן שנפל מזה — לא צריך אישור, רק שתדע
## And one small thing that fell out of this — no approval needed, just so you know

הסצנה שמתוכה נבנו שלושת המשים האלה הורכבה סביב `kav/KAV-first-shape.stl`.
*The scene those three meshes were reconstructed from was built around `kav/KAV-first-shape.stl`.*

**מדדתי אותו היום: הוא לא קובייה. הוא לא סגור בכלל.**
*Measured today: it is not a cube. It is not closed at all.*
12 משולשים, **36 קצוות בודדים — כלומר אף קצה לא משותף**, נפח 364.6 בתוך תיבה של 40×40×40
(0.57 % ממנה). מ-2026-09-02, לפני שKAV נבנה מחדש על אינדקסי קודקודים.
*12 triangles, **36 lone edges — not one shared edge**, volume 364.6 inside a 40×40×40
box. Dated 2026-09-02, before KAV was rebuilt on vertex indices.*

`tzelem/night.py`, `tzelem/hero8k.py` ו-`einayim/truthviews.py` קוראים אותו וקוראים לו
"הקובייה שהמודלר של ערן פלט". **לא נגעתי בקובץ** — שלושה צרכנים חיים תלויים בקנה המידה
שלו. כתבתי לידו את האמיתי (`KAV-first-shape-20260906.stl`: 12 פאות, **סגור**, נפח ×1.000)
ופתק שמסביר, ב-`kav/KAV-first-shape.PROVENANCE.md`. ההחלפה היא החלטה של מסלול הרנדר.
*I did not touch the file — three live consumers depend on its scale (0..40; the honest
one is 0..1). I wrote the real one beside it and a note explaining. Swapping is the
render track's call.*

---

*Everything else in the KAV revision — 17 of the 18 defects — was fixed on disk and
proved. Nothing was restarted, stopped or signalled anywhere; KAV has no server, no
port, no systemd unit and no checkpoints.*
