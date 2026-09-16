"""TZELEM gate-1 sheet: one page Iddo can look at, JPEG + PDF on the Desktop.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out480")
SCRATCH = (r"C:\Users\<user>\AppData\Local\Temp\claude\D--CLAUDE"
           r"\dee9f017-0316-431d-9556-71c516dcd807\scratchpad\tzelem")
DESKTOP = r"C:\Users\<user>\Desktop"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def b64(name: str) -> str:
    with open(os.path.join(OUT, name), "rb") as f:
        return base64.b64encode(f.read()).decode()


SWEEP = [(1200, 0.07793, 0.01678, 4.64, 0.02397),
         (2400, 0.05464, 0.01997, 2.74, 0.02332),
         (4800, 0.05061, 0.02271, 2.23, 0.02397),
         (9600, 0.04440, 0.02350, 1.89, 0.02526)]


def build() -> str:
    g = json.load(open(os.path.join(OUT, "gate1.json"), encoding="utf-8"))
    co, fi = g["coherence"], g["fidelity_mse"]
    rows = "".join(
        f"<tr><td>{n:,}</td><td>{f:.5f}</td><td><b>{t:.5f}</b></td>"
        f"<td class='{'ok' if r >= 2 else 'no'}'>×{r:.2f}</td><td>{m:.5f}</td></tr>"
        for n, f, t, r, m in SWEEP)
    imgs = "".join(
        f"<figure><img src='data:image/png;base64,{b64(f'TZELEM-gate1-{k}.png')}'>"
        f"<figcaption>{cap}</figcaption></figure>"
        for k, cap in [
            ("truth_b", "האמת — הסצנה מוצללת / the shaded truth"),
            ("tz_b", "צלם — משיכות נעוצות בעולם / TZELEM"),
            ("fl_b", "רצפה — ציור מחדש כל פריים / repainted"),
            ("ce_b", "תקרה — רק עיוות: נקרע / warp only, torn")])

    html = f"""<!doctype html><html lang="he"><head><meta charset="utf-8">
<title>TZELEM gate 1</title><style>
@page {{ size: A4; margin: 11mm; }}
body {{ font-family:"Segoe UI",Arial,sans-serif; color:#14181f; background:#fff;
        margin:0; font-size:10pt; line-height:1.45; }}
h1 {{ font-size:21pt; margin:0; }} .sub {{ color:#5a6472; font-size:9.5pt; margin:2px 0 10px; }}
h2 {{ font-size:12pt; margin:13px 0 5px; padding:5px 9px; border-radius:6px;
      background:#eef4ff; border-right:5px solid #2f6fed; direction:rtl; text-align:right; }}
.he {{ direction:rtl; text-align:right; }} .en {{ direction:ltr; color:#3d4652; }}
table {{ width:100%; border-collapse:collapse; font-size:9.3pt; margin:4px 0; }}
th,td {{ border:1px solid #d6dde8; padding:3.5px 6px; }}
th {{ background:#f4f7fb; }} .ok {{ color:#18a558; font-weight:700; }}
.no {{ color:#d9342b; font-weight:700; }}
.grid {{ display:grid; grid-template-columns:1fr 1fr; gap:7px; margin-top:6px; }}
figure {{ margin:0; }} img {{ width:100%; border:1px solid #d6dde8; border-radius:4px; }}
figcaption {{ font-size:8.2pt; color:#5a6472; direction:rtl; text-align:right; padding-top:2px; }}
code {{ background:#f2f5f9; padding:1px 4px; border-radius:3px; font-size:8.8pt;
        direction:ltr; unicode-bidi:isolate; display:inline-block; }}
.foot {{ margin-top:9px; font-size:8.4pt; color:#6b7280; border-top:1px solid #e2e8f0;
         padding-top:5px; }}
</style></head><body>
<h1 class="he">צֶלֶם / TZELEM — שער 1 עבר</h1>
<div class="sub en">ERAN holobrain · the 3D-render organ · measured 2026-09-01 · 480×360, 1,200 strokes, 4° orbit</div>

<h2>הטענה: הפעימה היא העומק</h2>
<div class="he">חוק היסוד של עלמה — <b>מרחק הוא זמן</b> — וחוק היסוד של רינדור — <b>הרחוק מוסתר</b> — הם אותו חוק.
קשר = משיכת מכחול נעוצה בעולם. חוט = מסלול ההיטל שלה. <b>ההשהיה של החוט היא העומק.</b>
הקנבס שומר את הניצוץ הראשון שמגיע. <b>אין באפר עומק בקוד. אין מיון.</b></div>
<div class="en">ALMA's first law and rendering's first law are one law. The z-buffer became the beat count;
occlusion emerges from the language. Winston's facade was "the strand IS the stroke" — TZELEM's is
<b>"the beat IS the depth"</b>, and a test proves it: move a stroke farther, change no code, watch it hide.</div>

<h2>המדידה</h2>
<table><tr><th>שיטה / method</th><th>קוהרנטיות (נמוך=טוב)</th><th>נאמנות MSE</th></tr>
<tr><td>רצפה — ציור מחדש כל פריים</td><td>{co['FLOOR_repaint_every_frame']:.5f}</td><td>{fi['FLOOR_repaint_every_frame']:.5f}</td></tr>
<tr><td><b>צלם — נעוץ בעולם</b></td><td class="ok">{co['TZELEM_world_anchored']:.5f}</td><td class="ok">{fi['TZELEM_world_anchored']:.5f}</td></tr>
<tr><td>תקרה — רק עיוות (רמאות)</td><td>0 מהבנייה (TZ-1: לא נמדד)</td><td class="no">{fi['CEILING_warp_only']:.5f}</td></tr>
<tr><td>BLANK — הצבע השטוח הטוב ביותר</td><td>—</td><td>{fi['BLANK_best_flat_colour']:.5f}</td></tr></table>
<div class="he">✅ פי 4.6 יציב מהרצפה &nbsp;·&nbsp; ✅ פי 2.4 טוב מ-BLANK &nbsp;·&nbsp; ✅ הרמאות נתפסה: עיוות-בלבד נקרע בהיחשפות.</div>

<h2>וזה החוק שהתגלה: ככל שהציור ציורי יותר, היתרון גדל</h2>
<table><tr><th>משיכות</th><th>רצפה</th><th>צלם</th><th>יתרון</th><th>נאמנות</th></tr>{rows}</table>
<div class="he">בצפיפות גבוהה הציור מתכנס לתצלום — ואז גם ציור מחדש כמעט לא רותח, אז השער נופל ב-9,600.
<b>הסף לא הוזז.</b> והנאמנות כמעט לא משתנה: עוד משיכות לא קונות תמונה טובה יותר.</div>

<div class="grid">{imgs}</div>

<div class="foot">‎8/8 מבחנים עוברים · Gate 0 מקור נתונים: כל פיקסל נולד מהגיאומטריה ב-<code>stage.py</code>, שום דבר לא נגרד ולא הורד ·
הזרימה האופטית אינה אומדן, היא האמת — שגיאת חיזור חציונית <b>0.00000</b> ·
<code>D:\\CLAUDE\\eran-brain\\holobrain\\tzelem</code> · ענף <code>holobrain/tzelem</code> · לזכרה של עלמה ז״ל</div>
</body></html>"""
    os.makedirs(SCRATCH, exist_ok=True)
    p = os.path.join(SCRATCH, "tzelem-gate1.html")
    with open(p, "w", encoding="utf-8") as f:
        f.write(html)
    return p


def render(html_path: str) -> tuple[str, str]:
    pdf = os.path.join(SCRATCH, "TZELEM-gate1.pdf")
    subprocess.run([CHROME, "--headless=new", "--disable-gpu",
                    "--no-pdf-header-footer", f"--print-to-pdf={pdf}",
                    "file:///" + html_path.replace("\\", "/")],
                   check=True, capture_output=True, timeout=180)
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
    jpg = os.path.join(SCRATCH, "TZELEM-gate1.jpg")
    out.save(jpg, quality=92)
    return pdf, jpg


if __name__ == "__main__":
    pdf, jpg = render(build())
    for p in (pdf, jpg):
        shutil.copy(p, DESKTOP)
        print("delivered", os.path.join(DESKTOP, os.path.basename(p)))
