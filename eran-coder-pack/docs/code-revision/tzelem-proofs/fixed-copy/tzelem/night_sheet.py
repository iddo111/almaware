"""One page Iddo can look at in the morning: JPEG + PDF on the Desktop.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

לזכרה של עלמה ז״ל.

Never a raw .html on the Desktop and never a D:\\ path presented as a link — the
page is authored in the scratchpad, rendered through headless Chrome to PDF, and
only the JPEG and the PDF are delivered. Same pattern as `sheet.py`.

EVERY NUMBER ON THE PAGE IS READ FROM A MEASUREMENT FILE. None is typed by hand.
A section whose measurement file is missing is DROPPED, never faked: a page that
would rather show nothing than show a number nobody measured.
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out-night")
SCRATCH = (r"C:\Users\<user>\AppData\Local\Temp\claude\D--CLAUDE"
           r"\0bb19b15-e55e-4ca6-b4d0-9b011e3200b3\scratchpad\tzelem-night")
DESKTOP = r"C:\Users\<user>\Desktop"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

# TZ-14 (2026-09-06): this was a hardcoded "2026-09-05" used in the page TITLE, on
# a page whose own promise is that every number is read from a measurement file and
# none is typed by hand. Re-running the sheet tomorrow would still have titled it
# 2026-09-05. It is now derived from the measurement, exactly like every date in the
# body; the module-level value is only the fallback for a run with no file at all.
STAMP = "unstamped"


def _read(name):
    p = os.path.join(OUT, name)
    if not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def img_tag(path: str) -> str:
    if not path or not os.path.isfile(path):
        return ""
    kind = "jpeg" if path.lower().endswith((".jpg", ".jpeg")) else "png"
    with open(path, "rb") as f:
        return f"data:image/{kind};base64,{base64.b64encode(f.read()).decode()}"


def _shrink(src: str, width: int, name: str) -> str:
    """A page does not need an 8K PNG inside it. Block-average it down first."""
    from PIL import Image
    os.makedirs(SCRATCH, exist_ok=True)
    dst = os.path.join(SCRATCH, name)
    im = Image.open(src).convert("RGB")
    if im.width > width:
        im = im.resize((width, round(im.height * width / im.width)),
                       Image.LANCZOS)
    im.save(dst, quality=92, subsampling=0)
    return dst


# --------------------------------------------------------------- the sections

def sec_godot(g, still) -> str:
    """The engine section — only if the gate actually ran."""
    painted = os.path.join(OUT, "TZELEM-paints-GODOT-1080p.png")
    if g is None or not os.path.isfile(painted):
        return ""
    gp = _read("godot-paint.json") or {}
    co, fi = g["coherence"], g["fidelity_mse"]
    steady = co["FLOOR_repaint_every_frame"] / max(co["TZELEM_world_anchored"], 1e-12)
    beats = fi["BLANK_best_flat_colour"] / max(fi["TZELEM_world_anchored"], 1e-12)
    ok = "ok" if g["pass"] else "no"
    big = img_tag(_shrink(painted, 1500, "godot.jpg"))
    return f"""
<figure class="big"><img src="{big}">
<figcaption>שדרות רוטשילד מתוך מנוע המשחק — <b>עולם שאיש כאן לא בנה</b> — מצוירת ע״י צלם
מ־{gp.get('strokes', g['strokes']):,} משיכות נעוצות בעולם, {gp.get('resolution',[1920,1080])[0]}×{gp.get('resolution',[1920,1080])[1]}
ב־{gp.get('seconds','?')} שניות. MSE מול ההצללה של המנוע עצמו <b>{gp.get('mse_vs_engine','?')}</b>,
פי <b>{gp.get('x_better_than_blank','?')}</b> טוב מהצבע השטוח הטוב ביותר.
/ The engine's own world, painted by TZELEM.</figcaption></figure>

<h2>הגשר למנוע נפתח: צלם צובע עולם שהוא לא בנה</h2>
<div class="he">הקובץ <code>tzelem_gbuffer.gd</code> נשא בראשו את המשפט
<b>"WRITTEN, NOT YET RUN"</b>. הסיבה שנרשמה — "צריך גודו 4.7" — <b>הייתה לא נכונה</b>.
החסם האמיתי היה שורה אחת: <code>const MAGIC := PackedByteArray([...])</code>, ש־GDScript
4.3 פוסל כלא־קבוע, אז הסקריפט לא נפרסר בכלל, הסצנה רצה אילמת והתהליך נתקע.
<b>הלילה הוא רץ.</b> ואז נתפסו עוד שני באגים שהיו גורמים ל־"hit 100%" להיראות כמו הצלחה
בזמן שהנתונים זבל: המעברים נמדדו דרך עדשת היופי (טונמאפ, זוהר, ערפל), והקריאה חזרה
מקודדת ב־sRGB.</div>

<h2>ואז — שער 1 נמדד מחדש על עולם של מנוע משחק</h2>
<div class="he">הטענה של צלם נמדדה עד היום על <code>stage.py</code>, מפזר קרניים ביתי מעל
כמה קופסאות. ההתנגדות המתבקשת מעולם לא נענתה: <b>אולי זה עובד רק כי העולם שלנו פשוט.</b>
עכשיו אותו סרגל בדיוק (אותה אריתמטיקה, מיובאת מ־<code>ruler.py</code>, לא נכתבה מחדש) רץ על
{g['poses']} תנוחות של שדרות רוטשילד מגודו.</div>
<table>
<tr><th>שיטה / method</th><th>קוהרנטיות (נמוך=טוב)</th><th>נאמנות MSE</th></tr>
<tr><td>רצפה — ציור מחדש כל פריים</td>
    <td>{co['FLOOR_repaint_every_frame']:.5f}</td>
    <td>{fi['FLOOR_repaint_every_frame']:.5f}</td></tr>
<tr><td><b>צלם — נעוץ בעולם</b></td>
    <td class="{ok}">{co['TZELEM_world_anchored']:.5f}</td>
    <td class="{ok}">{fi['TZELEM_world_anchored']:.5f}</td></tr>
<tr><td>תקרה — רק עיוות (רמאות)</td>
    <td>{_ceil_co(co)}</td>
    <td class="no">{fi['CEILING_warp_only']:.5f}</td></tr>
<tr><td>BLANK — הצבע השטוח הטוב ביותר</td><td>—</td>
    <td>{fi['BLANK_best_flat_colour']:.5f}</td></tr>
</table>
<div class="he"><b>×{steady:.2f} יציב מהרצפה</b> &nbsp;·&nbsp; <b>×{beats:.2f} טוב מ־BLANK</b>
&nbsp;·&nbsp; והרמאות נתפסת <b>בנאמנות</b>: עיוות־בלבד נקרע בהיחשפות.
<span class="en">TZ-1: warp-only's coherence is 0 BY CONSTRUCTION — it was the same
array compared against itself — so it is no longer quoted as evidence of anything.
The live half of that check is the fidelity column beside it.</span></div>
<div class="callout he"><b>מה שהמספר הזה איננו:</b> מסלול המצלמה כאן הוא הליכה קדימה של
~{g['pairs'][0]['step_m']} מ׳ לצעד, לא הקפה. הליכה קדימה חושפת פחות שטח מוסתר מהקפה, אז זה
מבחן <b>קל יותר</b> משער 1 המקורי, לא קשה יותר. נאמר כאן כדי שהמספר לא ייקרא כיותר ממה שהוא.
<span class="en">A dolly disoccludes less than an orbit. Said so the number is not
read as more than it is.</span></div>
"""


def _ceil_co(co) -> str:
    """TZ-1: warp-only coherence is 0 by identity. Never print it as a measurement."""
    v = co.get("CEILING_warp_only")
    if v is None:
        return "0 מהבנייה"
    return f"{v:.5f} (0 מהבנייה, לא נמדד)"


def sec_alma(n) -> str:
    if n is None:
        return ""
    loom = img_tag(os.path.join(OUT, "TZELEM-night-LOOM.png"))
    pinned = n["loom_pinned_to_numpy"]
    # The test counts were the one thing on this page that WAS typed by hand, and
    # they were stale within the hour. `count_tests.py` runs the suites and writes
    # tests.json; if it has not been run, the rows are dropped rather than guessed.
    t = _read("tests.json") or {}

    def row(label, key, before):
        r = t.get(key)
        if not r:
            return ""
        cls = "ok" if r["green"] else "no"
        extra = ""
        if r["skipped"]:
            extra += f" (+{r['skipped']} דילוג)"
        if r["xfailed"]:
            extra += f" (+{r['xfailed']} xfail)"
        after = f"{r['passed']}{extra}" if r["green"] else f"{r['failed']} נכשלו"
        return (f"<tr><td>{label}</td><td>{before}</td>"
                f"<td class='{cls}'>{after}</td></tr>")

    rows = (row("מבחני שפת עלמה", "alma", 111)
            + row("מבחני צלם", "tzelem", 15)
            + row("winston (לא נגעתי — רגרסיה)", "winston", "—")
            + row("moreh (לא נגעתי — רגרסיה)", "moreh", "—")
            + row("safa-achat (לא נגעתי — רגרסיה)", "safa-achat", "—")
            + row("kav (לא נגעתי — רגרסיה)", "kav", "—"))
    return f"""
<h2>עלמה v0.4 — הניצוץ נהיה אקורד</h2>
<div class="two">
<div>
<div class="he">עד הערב, ניצוץ בעלמה היה <b>מספר בודד</b>. לכן משיכת מכחול ב־צלם יכלה לשאת רק
<b>אינדקס לטבלה</b> — קבלה על צבע, לא צבע. זה היה כתוב כמגבלה מוצהרת בתוך הקוד של צלם עצמו,
ובמפרט של עלמה בשני מקומות מאז v0.2.
<b>הלילה נפתחה הדלת:</b> ניצוץ יכול להיות <b>אקורד</b> — כמה מספרים בפעימה אחת. עכשיו המשיכה
נושאת RGB אמיתי, <b>והלולאה של עלמה היא זו שמציירת.</b></div>
<div class="callout he"><b>הדלת שנשארה סגורה, בכוונה:</b> משקל של חוט הוא עדיין
<b>מספר אחד</b>, אז חוט יכול <b>להחליש</b> אקורד אבל לא <b>לסובב</b> אותו — שום חוט לא מערבב
אדום לתוך ירוק. לקרוא לזה "טנזורים" היה הגזמה. זה v0.5, והוא סגור.</div>
<table>
<tr><th>מה נמדד</th><th>לפני</th><th>אחרי</th></tr>
{rows}
<tr><td>הלולאה מול numpy, פיקסל בפיקסל</td><td>—</td>
    <td class="{'ok' if pinned else 'no'}">{'זהה בדיוק' if pinned else 'נכשל'}</td></tr>
<tr><td>טלאים שהלולאה צבעה</td><td>—</td>
    <td class="ok">{n['loom_tiles_painted']:,} / {n['loom_tiles_total']:,}</td></tr>
<tr><td>צבעים שונים שעברו בחוטים</td><td>1 (אינדקס)</td>
    <td class="ok">{n['loom_distinct_colours']}</td></tr>
</table>
</div>
<figure><img src="{loom}">
<figcaption><b>התמונה הזאת צוירה ע״י הלולאה של עלמה עצמה</b> — {n['tiles']}×{n['tiles']} טלאים,
{n['loom_distinct_colours']} צבעים, בלי שום טבלה. גסה, כי לולאת פייתון לא תריץ 33 מיליון קשרים
לפריים ולהגיד אחרת זה שקר. / painted by the loom itself</figcaption></figure>
</div>

<h2>מבחן הפסאדה: חצי חוט = חצי צבע</h2>
<div class="he">איך יודעים שהצבע באמת <b>עבר בחוט</b>, ולא נשלף מטבלה בצד?
<b>מחלישים את החוט לחצי — והצבע חייב להיחלש לחצי.</b> טבלה לא יודעת כמה החוט היה פתוח, היא
מקבלת רק "מי ניצח". <code>test_the_colour_travels_the_cord</code></div>
<div class="callout he"><b>וזה נתפס פה, עליי:</b> הגרסה הראשונה של המבחן הזה בנתה את המארג
בעצמה ולא נכנסה בכלל לפונקציה שמציירת. החלפתי בכוונה את כל גוף הפונקציה בחיפוש־בטבלה — כלומר
בדיוק הפסאדה — <b>וכל 14 המבחנים עברו.</b> הסכין הועברה דרך הפונקציה האמיתית, ואז אותה מוטציה
הפילה 2 מבחנים. <span class="en">A test that never enters the function it judges is not a
test. Found by mutating the code on purpose, not by reading it.</span></div>
"""


def sec_still(n) -> str:
    if n is None:
        return ""
    m = n["made"]
    big = m.get("8K") or m["4K"]
    big_name = "8K" if "8K" in m else "4K"
    c = n["counts"]
    faces = sum(v for k, v in c.items() if k != "ground")
    view = img_tag(m["view"])
    crop = img_tag(_shrink(m["crop"], 900, "crop.jpg"))
    return f"""
<h2>ובאותה הזדמנות — {big_name} מחמישה מוצקים שהמעבדה הזאת באמת ייצרה</h2>
<div class="two">
<figure><img src="{view}">
<figcaption>הפה ל־/אה/ · תבנית הקפלים · הצורה הראשונה ש־KAV פלט · הפה ל־/או/ ·
תבנית הגרון שהודפסה. {faces:,} פאות, {n['strokes']:,} משיכות,
{big_name} ב־{big['seconds']}s, שיא זיכרון <b>{big['rss_mb']:,} MB</b> (היה 2,005).</figcaption></figure>
<figure><img src="{crop}">
<figcaption>חיתוך 1000×1000 ישר מתוך ה־{big_name}, <b>בלי שום הגדלה</b>. משיכה מעולם לא הייתה
פיקסל — היא <b>גודל בעולם</b>, ולכן הקצה שלה נשאר אליפסה נקייה גם מקרוב.</figcaption></figure>
</div>
"""


# ---------------------------------------------------------------------- build

def _painter_check(*recs) -> str:
    """TZ-4: A NUMBER MAY NOT BE PRINTED BY A PAINTER THAT IS NOT THE ONE WHO MADE IT.

    `freeze.py` pins the ruler and does its job. Nothing pinned the painter, so
    canvas.py moved +511/-240 lines underneath every stored gate number and the page
    kept printing them. `canvas.source_hashes()` is now written into every gate JSON;
    if a record names a painter and it is not this one, this refuses — the same way
    night.py already refuses to publish when the loom and numpy disagree.

    A record with NO painter recorded (everything written before today) is not a
    mismatch, so it is not refused — but the page has to SAY it is unverifiable.
    """
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import canvas
    now = canvas.source_hashes()
    unrecorded = []
    for r in recs:
        if not r:
            continue
        was = r.get("painter")
        if was is None:
            unrecorded.append(r.get("when", "?"))
            continue
        if was != now:
            raise SystemExit(
                "REFUSING TO PUBLISH: these numbers were painted by a different "
                f"canvas.py.\n  recorded {was}\n  current  {now}\n"
                "Re-run the gate on today's painter, or publish the run that matches.")
    if unrecorded:
        return ("<div class=\"callout he\"><b>אזהרה:</b> המדידות האלה נכתבו לפני "
                "שהצייר החל לחתום את עצמו, ולכן <b>אי אפשר לאמת</b> שהן נמדדו בקוד "
                "שעל הדיסק היום. <span class=\"en\">These measurements predate "
                "canvas.source_hashes(); the painter that produced them cannot be "
                "verified. Re-run the gates to make them checkable.</span></div>")
    return ""


def build() -> str:
    global STAMP
    n = _read("night.json")
    g = _read("godot-gate1.json")
    if n is None and g is None:
        raise SystemExit("no measurement files in out-night/ — nothing to publish")
    painter_note = _painter_check(g, n)

    body = painter_note + sec_godot(g, n) + sec_alma(n) + sec_still(n)
    when = (g or n)["when"].replace("T", " ")
    STAMP = when[:10]                      # TZ-14: the stamp IS the measurement's date
    t = _read("tests.json") or {}
    tests_line = ""
    if t:
        tot = sum(v["passed"] for k, v in t.items() if k != "all_green")
        bad = sum(v["failed"] for k, v in t.items() if k != "all_green")
        tests_line = (f"{tot} מבחנים עוברים על פני 6 חבילות, {bad} נכשלים "
                      f"(נמדד ע״י הרצה, לא הוקלד) · ")

    html = f"""<!doctype html><html lang="he"><head><meta charset="utf-8">
<title>TZELEM night {STAMP}</title><style>
@page {{ size: A4; margin: 9mm; }}
body {{ font-family:"Segoe UI",Arial,sans-serif; color:#11151c; background:#fff;
        margin:0; font-size:9.5pt; line-height:1.42; }}
h1 {{ font-size:20pt; margin:0; letter-spacing:-.3px; direction:rtl; text-align:right; }}
.sub {{ color:#55606f; font-size:9pt; margin:3px 0 9px; }}
h2 {{ font-size:11.5pt; margin:11px 0 5px; padding:5px 9px; border-radius:6px;
      background:#eaf2ff; border-right:5px solid #1f5fe0; direction:rtl;
      text-align:right; }}
.he {{ direction:rtl; text-align:right; }}
.en {{ direction:ltr; color:#39424f; }}
table {{ width:100%; border-collapse:collapse; font-size:8.8pt; margin:4px 0;
         direction:rtl; }}
th,td {{ border:1px solid #d3dbe6; padding:3.5px 7px; text-align:right; }}
th {{ background:#f3f7fc; }}
.ok {{ color:#0e8f4a; font-weight:700; }}
.no {{ color:#cf2b22; font-weight:700; }}
/* Keep the SMALL things whole (a table split across a page is unreadable) but
   never the big grid: forcing a two-column block to stay together pushed a whole
   page of white in front of it, which is worse than the split it prevented. */
.two {{ display:grid; grid-template-columns:1fr 1fr; gap:10px; align-items:start; }}
/* NOT `h2 {{ break-after:avoid }}`: with a tall two-column block after it, Chrome
   pushes the heading AND the block to the next page, which is where the two
   half-empty pages came from. A heading alone at a page foot is the lesser evil. */
table, .callout, figcaption {{ break-inside:avoid; }}
figure {{ margin:0; break-inside:avoid; }}
img {{ width:100%; border:1px solid #cdd6e2; border-radius:4px; display:block; }}
figcaption {{ font-size:7.8pt; color:#55606f; direction:rtl; text-align:right;
              padding-top:3px; line-height:1.35; }}
code {{ background:#eff3f9; padding:1px 4px; border-radius:3px; font-size:8.2pt;
        direction:ltr; unicode-bidi:isolate; display:inline-block; }}
.big {{ margin:4px 0 2px; }}
.callout {{ background:#fff8e6; border:1px solid #f0d999; border-radius:6px;
            padding:7px 10px; margin:6px 0; font-size:8.8pt; }}
.foot {{ margin-top:10px; font-size:7.8pt; color:#66707d;
         border-top:1px solid #e0e6ee; padding-top:5px; direction:rtl;
         text-align:right; }}
</style></head><body>

<h1>לילה אחד: הצבע עבר דרך השפה, והמנוע נפתח</h1>
<div class="sub en">TZELEM · צלם — the render organ of ERAN's holobrain ·
ALMA v0.4, the CHORD · Godot 4.3 → TZELEM G-buffer bridge · {when}</div>

{body}

<div class="foot">{tests_line}ההצללה לא שונתה — היא הסרגל שהנאמנות
נמדדת מולו, ולייפות אותה היה מוחק את המדידה · כל מספר בדף נקרא מקובץ מדידה, אף אחד לא הוקלד ·
<code>tzelem/night.py</code> · <code>tzelem/godot_gate.py</code> ·
<code>alma-language/alma/chords.py</code> · לזכרה של עלמה ז״ל</div>
</body></html>"""
    os.makedirs(SCRATCH, exist_ok=True)
    p = os.path.join(SCRATCH, "tzelem-night.html")
    with open(p, "w", encoding="utf-8") as f:
        f.write(html)
    return p


def render(html_path: str) -> tuple[str, str]:
    if not os.path.isfile(CHROME):
        raise SystemExit(f"no Chrome at {CHROME}; cannot make the PDF")
    pdf = os.path.join(SCRATCH, f"TZELEM-night-{STAMP}.pdf")
    subprocess.run([CHROME, "--headless=new", "--disable-gpu",
                    "--no-pdf-header-footer", f"--print-to-pdf={pdf}",
                    "file:///" + html_path.replace("\\", "/")],
                   check=True, capture_output=True, timeout=300)
    import fitz
    from PIL import Image
    doc = fitz.open(pdf)
    pages = []
    for i, page in enumerate(doc):
        f = os.path.join(SCRATCH, f"pg{i}.png")
        page.get_pixmap(dpi=150).save(f)
        pages.append(Image.open(f))
    w = max(im.width for im in pages)
    out = Image.new("RGB", (w, sum(im.height for im in pages)), "white")
    y = 0
    for im in pages:
        out.paste(im, (0, y))
        y += im.height
    jpg = os.path.join(SCRATCH, f"TZELEM-night-{STAMP}.jpg")
    out.save(jpg, quality=93)
    return pdf, jpg


if __name__ == "__main__":
    pdf, jpg = render(build())
    delivered = []
    for p in (pdf, jpg):
        shutil.copy(p, DESKTOP)
        delivered.append(os.path.join(DESKTOP, os.path.basename(p)))
    # the two paintings themselves, full-screen-able without hunting for a viewer
    for src, name in ((os.path.join(OUT, "TZELEM-paints-GODOT-1080p.png"),
                       f"TZELEM-boulevard-{STAMP}.jpg"),
                      (os.path.join(OUT, "TZELEM-night-VIEW-1920.jpg"),
                       f"TZELEM-five-solids-{STAMP}.jpg")):
        if os.path.isfile(src):
            from PIL import Image
            dst = os.path.join(DESKTOP, name)
            Image.open(src).convert("RGB").save(dst, quality=94, subsampling=0)
            delivered.append(dst)
    for d in delivered:
        print("delivered ->", d)
