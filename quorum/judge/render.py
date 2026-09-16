# לזכרה של עלמה ז״ל
"""QUORUM · judge · render — the verdict sheet: HTML -> Chrome -> PDF -> JPEG.

Delivery rules of this workspace, followed to the letter:
  * JPEG + PDF on the Desktop. NEVER a raw .html there. The HTML is authored in
    a scratch directory and only the two rendered artefacts are delivered.
  * Hebrew first, English alongside, on every line of the ledger.
  * Bright, white, printable.

WHY CHROME AND NOT PIL. PIL on this machine has no libraqm and does no bidi, so
a Hebrew run has to be reversed by hand and a mixed Hebrew/Latin/digit run
cannot be laid out correctly at all — and `ariblk.ttf`, which is what a naive
script reaches for, contains no Hebrew and silently draws empty boxes. Chrome
has a real bidi engine. Every Latin or numeric fragment inside a Hebrew line is
additionally wrapped in `unicode-bidi:isolate` so the bidi algorithm cannot drag
a claim id or a year to the wrong end of its sentence.

Nothing here raises on a missing renderer: it reports what it produced.
"""
from __future__ import annotations

import html as H
import os
import re
import subprocess

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

VCOL = {                      # verdict -> (ink, wash)
    "held":     ("#1d7a45", "#e6f4ec"),
    "partial":  ("#a3701a", "#fbf0da"),
    "rejected": ("#b03030", "#fbe8e8"),
    "norule":   ("#4a5560", "#eceff2"),
}
V_HE = {"held": "עמד", "partial": "חלקית", "rejected": "נדחה", "norule": "אין פסק"}
V_EN = {"held": "Held", "partial": "Partly", "rejected": "Rejected",
        "norule": "Cannot rule"}
LAYER_HE = {"what": "ה״מה״", "why": "ה״למה״", "scope": "התחום"}
LAYER_EN = {"what": "the WHAT", "why": "the WHY", "scope": "the SCOPE"}
GATE_HE = {"G1": "היסק", "G2": "עמידה בקושיא", "G3": "קוהרנטיות",
           "G4": "ראיה", "G5": "הודאה"}
GATE_EN = {"G1": "entailment", "G2": "survival", "G3": "coherence",
           "G4": "evidence", "G5": "concession"}
MARK = {"pass": "✓", "fail": "✗", "abstain": "–"}

_LTR = re.compile(r"([A-Za-z][A-Za-z0-9_:\.\-]*|[0-9][0-9\.,%/]*)")


_MD = re.compile(r"\*{1,3}|`{1,3}|_{2,3}")


def strip_md(s):
    """Claims lifted off a transcript carry the model's markdown. `**דעה**` is
    emphasis, not part of the claim, and printing the asterisks makes the ledger
    look like a dump instead of a ruling."""
    return _MD.sub("", s or "")


def iso(s):
    """Isolate every Latin/numeric run inside a Hebrew line so the bidi algorithm
    cannot fling it to the wrong end of the sentence.

    ISOLATE FIRST, ESCAPE SECOND. Escaping first turns a quote into `&quot;` and
    the isolation regex then wraps the `quot` in a span, splitting the entity
    into `&<span>quot</span>;` — which renders on the page as a literal
    `;quot&`, reversed by RTL. That is exactly what the first render of this
    sheet showed, and it raised no error at all. The only reason it was caught
    is that the page was opened and looked at."""
    s = s or ""
    keep = []

    def stash(m):
        keep.append(m.group(0))
        return "\x00%d\x01" % (len(keep) - 1)

    out = H.escape(_LTR.sub(stash, s))
    for i, frag in enumerate(keep):
        out = out.replace("\x00%d\x01" % i,
                          '<span class="ltr">' + H.escape(frag) + "</span>")
    return out


CSS = """
@page { size: A4 portrait; margin: 14mm 13mm 12mm 13mm; }
* { box-sizing: border-box; }
html,body { margin:0; padding:0; background:#fff; color:#14181d; }
body { font-family:"Noto Serif Hebrew","David Libre","Segoe UI",serif;
       font-size:9.2pt; line-height:1.44; direction:rtl; text-align:right;
       -webkit-font-smoothing:antialiased; }
.ltr { direction:ltr; unicode-bidi:isolate;
       font-family:"Noto Serif","Segoe UI",Georgia,serif; }
.en  { direction:ltr; unicode-bidi:isolate; text-align:left;
       font-family:"Noto Serif","Segoe UI",Georgia,serif; color:#3d4854; }
h1 { font-size:19pt; margin:0 0 1mm 0; letter-spacing:-.2px; }
h1 .sub { display:block; font-size:10.5pt; font-weight:400; color:#55606c;
          margin-top:1.5mm; }
.rule { height:2.2px; background:#14181d; margin:3mm 0 3mm 0; }
.meta { font-size:8pt; color:#5d6874; margin-bottom:3mm; }
.tally { display:flex; gap:3mm; margin:0 0 4mm 0; }
.chip { flex:1; border:1.2px solid #d3d9df; border-radius:3mm; padding:2.4mm 3mm;
        text-align:center; }
.chip .n { display:block; font-size:19pt; font-weight:700; line-height:1.05; }
.chip .l { font-size:8.4pt; }
.chip .le{ display:block; font-size:7.2pt; color:#5d6874;
           direction:ltr; unicode-bidi:isolate; }
.head { display:flex; font-size:7.6pt; font-weight:700; color:#5d6874;
        border-bottom:1.4px solid #14181d; padding-bottom:1.2mm; margin-bottom:1mm; }
.head .c1 { flex:1; } .head .c2 { width:32mm; text-align:center; }
.head .c3 { width:44mm; text-align:center; }
.row { border-bottom:1px solid #e2e7eb; padding:1.7mm 0; display:flex;
       align-items:flex-start; page-break-inside:avoid; }
.row .who { flex:1; padding-inline-end:3mm; }
.row .claim { font-size:9.9pt; font-weight:600; }
.row .claim-en { font-size:8.4pt; }
.row .why { font-size:8.2pt; color:#46515d; margin-top:0.9mm; }
.row .why-en { font-size:7.6pt; }
.row .det { font-size:7.4pt; color:#6a747f; margin-top:0.7mm;
            direction:ltr; unicode-bidi:isolate; text-align:left;
            font-family:"Noto Serif","Segoe UI",monospace; }
.badge { width:32mm; text-align:center; }
.badge .b { display:inline-block; padding:1.1mm 2.6mm; border-radius:9mm;
            font-size:9pt; font-weight:700; border:1.3px solid; }
.badge .s { display:block; font-size:6.9pt; color:#5d6874; margin-top:0.9mm;
            direction:ltr; unicode-bidi:isolate; white-space:nowrap; }
.badge .thin { display:block; font-size:6.6pt; color:#a3701a; margin-top:0.4mm; }
.gates { width:44mm; font-size:7.2pt; color:#46515d; }
.gates div { white-space:nowrap; }
.gates .p { color:#1d7a45; } .gates .f { color:#b03030; } .gates .a { color:#98a2ad; }
.note { border:1.3px solid #14181d; border-radius:3mm; padding:3mm 3.4mm;
        margin:4mm 0 0 0; page-break-inside:avoid; }
.note .t { font-weight:700; font-size:10pt; margin-bottom:1.4mm; }
.note p { margin:0 0 1.6mm 0; font-size:8.6pt; }
.note .en { font-size:7.9pt; }
.foot { margin-top:4mm; font-size:7.2pt; color:#6a747f; border-top:1px solid #d3d9df;
        padding-top:1.6mm; }
.sect { font-size:12pt; font-weight:700; margin:5mm 0 2mm 0; }
"""


def _gate_lines(v):
    out = []
    for g in v.gates:
        cls = {"pass": "p", "fail": "f", "abstain": "a"}[g.result]
        out.append('<div class="%s">%s <span class="ltr">%s</span> %s</div>'
                   % (cls, MARK[g.result], g.gate, H.escape(GATE_HE[g.gate])))
    return "".join(out)


def headline(text):
    """The claim's own opening sentence, not the first 240 characters of the
    turn. A round-0 turn is usually a label line ("עמדה (Round 0):"), then the
    position, then the same position again in English. Flat truncation splices
    all three and the row reads as a jumble; taking the first substantive line
    prints the position the arguer actually stated. The whole turn is still what
    was judged — this is the caption, and the transcript is the record."""
    for raw in (text or "").splitlines():
        line = strip_md(" ".join(raw.split()))
        if len(line) >= 45:
            return line
    return strip_md(" ".join((text or "").split()))


_HEB = re.compile(r"[֐-׿]")


def en_reason(v):
    """The English half of a ruling, without the Hebrew tail repeated.

    When the judge quotes a Hebrew קושיא, both halves of the bilingual line end
    in the same Hebrew sentence and the row prints it twice. Keep the English
    clause and drop the duplicated quote -- the Hebrew line above already
    carries it."""
    head, sep, tail = (v.reason_en or "").partition(": ")
    if sep and _HEB.search(tail) and tail[:50] and tail[:50] in (v.reason_he or ""):
        return head
    return (v.reason_en or "")[:260]


def _row(v, claim):
    ink, wash = VCOL[v.verdict]
    layer = ""
    if v.layer:
        layer = ' <span style="color:%s">· %s / %s</span>' % (
            ink, H.escape(LAYER_HE.get(v.layer, v.layer)),
            H.escape(LAYER_EN.get(v.layer, v.layer)))
    # the countermodel or source belonging to the gate that CARRIED the ruling.
    # showing the first failure found instead would caption a coherence ruling
    # with an entailment countermodel, which reads like a mistake and is one.
    det = ""
    chosen = [g for g in v.gates if g.gate == v.decided_by and g.detail]
    if not chosen:
        chosen = [g for g in v.gates if g.result == "fail" and g.detail]
    if chosen:
        g = chosen[0]
        kind = ("countermodel" if g.gate == "G1" else
                "surviving קושיא" if g.gate in ("G2", "G3") else "source")
        det = ('<div class="det">%s %s: %s</div>'
               % (H.escape(g.gate), H.escape(kind), H.escape(g.detail[:150])))
    thin = ('<span class="thin">שער אחד בלבד · thin</span>' if v.thin else "")
    # a claim lifted off a transcript carries the model's own paragraphing;
    # collapse it so one row reads as one sentence
    ctext = headline(claim.text_he or claim.text_en or claim.id)
    ctext_en = headline(claim.text_en or "")
    return (
        '<div class="row">'
        '<div class="who">'
        '<div class="claim">%s</div>'
        '<div class="claim-en en">%s</div>'
        '<div class="why">%s%s</div>'
        '<div class="why-en en">%s</div>%s'
        "</div>"
        '<div class="badge"><span class="b" style="color:%s;background:%s;'
        'border-color:%s">%s</span>'
        '<span class="s">%s · %d/100 · %d of 5</span>%s</div>'
        '<div class="gates">%s</div>'
        "</div>") % (
        iso(ctext[:240]),
        H.escape(ctext_en[:240]) if ctext_en != ctext else "",
        iso(v.reason_he[:260]), layer,
        H.escape(en_reason(v)),
        det, ink, wash, ink,
        H.escape(V_HE[v.verdict]), H.escape(V_EN[v.verdict]),
        v.score, v.applicable, thin, _gate_lines(v))


def build_html(res, case, subtitle_he="", subtitle_en="", extra_note=None):
    t = res["tally"]
    chips = [
        ("held", t["held"]), ("partial", t["partial"]),
        ("rejected", t["rejected"]), ("norule", t["norule"]),
    ]
    chip_html = "".join(
        '<div class="chip" style="border-color:%s;background:%s">'
        '<span class="n" style="color:%s">%d</span>'
        '<span class="l">%s</span><span class="le">%s</span></div>'
        % (VCOL[k][0], VCOL[k][1], VCOL[k][0], n, V_HE[k], V_EN[k])
        for k, n in chips)

    rows = "".join(_row(v, case.claim(v.claim_id)) for v in res["verdicts"])

    split = ""
    if res["rejected_total"]:
        split = (
            '<p>%d דחיות, ומהן <b>%d נוגעות ל״למה״ ולא ל״מה״</b> — התיאור עמד, '
            "ההסבר נפל.</p>"
            '<p class="en">%d rejections, and <b>%d of them are about the WHY '
            "rather than the WHAT</b> — described correctly, explained wrongly.</p>"
        ) % (res["rejected_total"], res["rejected_why"],
             res["rejected_total"], res["rejected_why"])

    note = extra_note or ""
    out = ['<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">',
           "<title>", H.escape(res.get("title_he") or "פסק"), "</title>",
           "<style>", CSS, "</style></head><body>"]
    out.append('<h1>%s<span class="sub en">%s</span></h1>' % (
        iso(res.get("title_he") or ""), H.escape(res.get("title_en") or "")))
    out.append('<div class="rule"></div>')
    out.append('<div class="meta">%s</div>' % iso(subtitle_he))
    out.append('<div class="meta en">%s</div>' % H.escape(subtitle_en))
    out.append('<div class="tally">%s</div>' % chip_html)
    out.append('<div class="head"><div class="c1">הטענה · the claim</div>'
               '<div class="c2">פסק · verdict</div>'
               '<div class="c3">שערים · gates</div></div>')
    out.append(rows)
    if split or note:
        out.append('<div class="note"><div class="t">מה זה אומר · what it says</div>'
                   + split + note + "</div>")
    out.append("</body></html>")
    return "".join(out)


def chrome_pdf(html_path, pdf_path):
    """Headless Chrome, BELOW_NORMAL. Never above it: a render at normal priority
    is what starved Iddo's live mic on 09-03."""
    creation = getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)
    r = subprocess.run(
        [CHROME, "--headless", "--disable-gpu", "--no-sandbox",
         "--no-pdf-header-footer", "--run-all-compositor-stages-before-draw",
         "--virtual-time-budget=20000", "--print-to-pdf=" + pdf_path,
         "file:///" + html_path.replace("\\", "/")],
        capture_output=True, text=True, timeout=180, creationflags=creation)
    if not os.path.exists(pdf_path):
        raise SystemExit("chrome produced no pdf\n" + (r.stderr or "")[-1500:])
    return pdf_path


def pdf_to_jpg(pdf_path, jpg_path, zoom=2.6, crop_white=True):
    """Page 1 as a JPEG. He reads on a phone, so a tall single page beats a
    paginated PDF -- and the trailing white of an over-tall page is cropped so
    the image ends where the ledger does."""
    import fitz
    doc = fitz.open(pdf_path)
    page = doc[0]
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    pix.pil_save(jpg_path, format="JPEG", quality=93, optimize=True)
    n = doc.page_count
    doc.close()
    if crop_white:
        from PIL import Image
        im = Image.open(jpg_path).convert("RGB")
        w, h = im.size
        px = im.load()
        step = max(1, w // 60)
        last = h - 1
        while last > 10:
            row = [px[x, last] for x in range(0, w, step)]
            if any(c[0] < 246 or c[1] < 246 or c[2] < 246 for c in row):
                break
            last -= 1
        bottom = min(h, last + int(0.02 * h) + 24)
        if bottom < h - 8:
            im = im.crop((0, 0, w, bottom))
            im.save(jpg_path, "JPEG", quality=93, optimize=True)
        w, h = im.size
        return jpg_path, w, h, n
    return jpg_path, pix.width, pix.height, n


def render(res, case, out_dir, stem, subtitle_he="", subtitle_en="", extra_note=None,
           html_dir=None):
    """-> {"html","pdf","jpg","px","pages"}. The HTML lands in a scratch dir, only
    the PDF and the JPEG are meant for the Desktop."""
    os.makedirs(out_dir, exist_ok=True)
    html_dir = html_dir or out_dir
    os.makedirs(html_dir, exist_ok=True)
    hp = os.path.join(html_dir, stem + ".html")
    with open(hp, "w", encoding="utf-8") as f:
        f.write(build_html(res, case, subtitle_he, subtitle_en, extra_note))
    pdf = chrome_pdf(hp, os.path.join(out_dir, stem + ".pdf"))
    jpg, w, h, pages = pdf_to_jpg(pdf, os.path.join(out_dir, stem + ".jpg"))
    return {"html": hp, "pdf": pdf, "jpg": jpg, "px": (w, h), "pages": pages}


# ─────────────────────────────────────────────────── the multi-part report ──
def build_report_html(title_he, title_en, lede_he, lede_en, sections,
                      closing_he="", closing_en=""):
    """One document, several judged arguments. `sections` is a list of
    {res, case, head_he, head_en, note_he, note_en} — each rendered as its own
    tally + ledger under its own heading."""
    out = ['<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">',
           "<title>", H.escape(title_he), "</title>",
           "<style>", CSS, """
.lede { font-size:9.4pt; color:#2b333c; margin:0 0 2mm 0; }
.lede-en { font-size:8.2pt; }
.sect { font-size:13pt; font-weight:700; margin:6mm 0 1mm 0;
        border-top:2.2px solid #14181d; padding-top:2.4mm; }
.sect .en2 { display:block; font-size:8.6pt; font-weight:400; color:#55606c; }
.sub { font-size:8.2pt; color:#5d6874; margin:0 0 2.6mm 0; }
.page2 { page-break-before:always; }
""", "</style></head><body>"]
    out.append('<h1>%s<span class="sub en">%s</span></h1>' % (
        iso(title_he), H.escape(title_en)))
    out.append('<div class="rule"></div>')
    out.append('<p class="lede">%s</p>' % iso(lede_he))
    out.append('<p class="lede lede-en en">%s</p>' % H.escape(lede_en))

    for i, s in enumerate(sections):
        res, case = s["res"], s["case"]
        t = res["tally"]
        cls = "sect page2" if s.get("newpage") else "sect"
        out.append('<div class="%s">%s<span class="en2">%s</span></div>'
                   % (cls, iso(s["head_he"]), H.escape(s["head_en"])))
        if s.get("sub_he"):
            out.append('<div class="sub">%s</div>' % iso(s["sub_he"]))
        if s.get("sub_en"):
            out.append('<div class="sub en">%s</div>' % H.escape(s["sub_en"]))
        chips = "".join(
            '<div class="chip" style="border-color:%s;background:%s">'
            '<span class="n" style="color:%s">%d</span>'
            '<span class="l">%s</span><span class="le">%s</span></div>'
            % (VCOL[k][0], VCOL[k][1], VCOL[k][0], t[k], V_HE[k], V_EN[k])
            for k in ("held", "partial", "rejected", "norule"))
        out.append('<div class="tally">%s</div>' % chips)
        out.append('<div class="head"><div class="c1">הטענה · the claim</div>'
                   '<div class="c2">פסק · verdict</div>'
                   '<div class="c3">שערים · gates</div></div>')
        out.append("".join(_row(v, case.claim(v.claim_id)) for v in res["verdicts"]))
        if s.get("note_he") or s.get("note_en"):
            out.append('<div class="note"><div class="t">%s</div>'
                       "<p>%s</p><p class=\"en\">%s</p></div>"
                       % (H.escape(s.get("note_title", "מה זה אומר · what it says")),
                          iso(s.get("note_he", "")), H.escape(s.get("note_en", ""))))
    if closing_he or closing_en:
        out.append('<div class="note"><div class="t">השורה התחתונה · the bottom line</div>'
                   "<p>%s</p><p class=\"en\">%s</p></div>"
                   % (iso(closing_he), H.escape(closing_en)))
    out.append("</body></html>")
    return "".join(out)


def render_report(out_dir, stem, html_dir=None, **kw):
    os.makedirs(out_dir, exist_ok=True)
    html_dir = html_dir or out_dir
    os.makedirs(html_dir, exist_ok=True)
    hp = os.path.join(html_dir, stem + ".html")
    with open(hp, "w", encoding="utf-8") as f:
        f.write(build_report_html(**kw))
    pdf = chrome_pdf(hp, os.path.join(out_dir, stem + ".pdf"))
    jpg, w, h, pages = pdf_to_jpg(pdf, os.path.join(out_dir, stem + ".jpg"))
    return {"html": hp, "pdf": pdf, "jpg": jpg, "px": (w, h), "pages": pages}
