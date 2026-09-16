#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HELIOS builder: sections.json -> index.html -> PDF (live links) -> JPEG.
Hebrew RTL, bright styling.  Run:  python build_helios.py [sections.json]
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(HERE, "site")
os.makedirs(SITE, exist_ok=True)

REF_RE = re.compile(r"\[\[REF\|([^|\]]+)\|([^\]]+)\]\]")


def esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def inline(t, refmap):
    t = esc(t)

    def ref(m):
        label, url = m.group(1).strip(), m.group(2).strip()
        n = refmap.get(url)
        num = '<span class="rn">%d</span>' % n if n else ""
        return ('<a class="ref" href="%s" target="_blank" rel="noopener" title="%s">%s%s</a>'
                % (url, esc(label), esc(label), num))

    t = REF_RE.sub(ref, t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", t)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    return t


def md_to_html(md, refmap):
    """Minimal, predictable markdown -> HTML. We control the input, so no library."""
    out = []
    state = {"ul": False, "ol": False}

    def close():
        if state["ul"]:
            out.append("</ul>")
            state["ul"] = False
        if state["ol"]:
            out.append("</ol>")
            state["ol"] = False

    for raw in md.split("\n"):
        s = raw.rstrip()
        if not s.strip():
            close()
            continue
        if s.startswith("#### "):
            close(); out.append("<h4>%s</h4>" % inline(s[5:], refmap)); continue
        if s.startswith("### "):
            close(); out.append("<h3>%s</h3>" % inline(s[4:], refmap)); continue
        if s.startswith("## "):
            close(); out.append("<h2>%s</h2>" % inline(s[3:], refmap)); continue
        if s.startswith("> "):
            close(); out.append("<blockquote>%s</blockquote>" % inline(s[2:], refmap)); continue
        m = re.match(r"^\s*[-*]\s+(.*)$", s)
        if m:
            if state["ol"]:
                out.append("</ol>"); state["ol"] = False
            if not state["ul"]:
                out.append("<ul>"); state["ul"] = True
            out.append("<li>%s</li>" % inline(m.group(1), refmap)); continue
        m = re.match(r"^\s*\d+[.)]\s+(.*)$", s)
        if m:
            if state["ul"]:
                out.append("</ul>"); state["ul"] = False
            if not state["ol"]:
                out.append("<ol>"); state["ol"] = True
            out.append("<li>%s</li>" % inline(m.group(1), refmap)); continue
        close()
        out.append("<p>%s</p>" % inline(s, refmap))
    close()
    return "\n".join(out)


CSS = """
:root{
  --ink:#1b1714; --ink-soft:#4a423c; --muted:#7d7168;
  --bg:#fffdf7; --panel:#fffefb; --line:#eadfcc;
  --sun1:#f6a416; --sun2:#e4670c; --sun3:#fbd27a;
  --ok:#2f6b46; --warn:#a8420f;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{
  margin:0; background:var(--bg); color:var(--ink);
  font-family:'Assistant','Segoe UI',system-ui,sans-serif;
  font-size:18px; line-height:1.85; text-align:start;
}
.wrap{max-width:820px;margin:0 auto;padding:0 24px 96px}
header.hero{
  background:
    radial-gradient(1100px 380px at 50% -160px, var(--sun3) 0%, rgba(251,210,122,0) 62%),
    linear-gradient(180deg,#fffaf0 0%, var(--bg) 100%);
  border-bottom:1px solid var(--line); padding:76px 24px 52px; text-align:center;
}
.sun{width:96px;height:96px;margin:0 auto 22px;display:block}
h1{
  font-family:'Frank Ruhl Libre',Georgia,serif; font-weight:800;
  font-size:clamp(34px,5.4vw,50px); line-height:1.18; margin:0 0 14px; letter-spacing:-.4px;
}
.sub{color:var(--ink-soft);font-size:20px;max-width:640px;margin:0 auto 6px}
.meta{color:var(--muted);font-size:14px;margin-top:20px}
h2{
  font-family:'Frank Ruhl Libre',Georgia,serif; font-weight:700;
  font-size:30px; line-height:1.3; margin:64px 0 6px; padding-top:26px;
  border-top:1px solid var(--line);
}
h2:first-of-type{border-top:0;padding-top:0}
h3{font-family:'Frank Ruhl Libre',Georgia,serif;font-weight:700;font-size:22px;margin:34px 0 4px}
h4{font-size:18px;font-weight:700;margin:24px 0 2px;color:var(--ink-soft)}
p{margin:14px 0}
ul,ol{margin:14px 0;padding-inline-start:26px}
li{margin:7px 0}
blockquote{
  margin:22px 0;padding:14px 20px;border-inline-start:4px solid var(--sun1);
  background:#fff8e9;border-radius:10px;color:var(--ink-soft);
}
a{color:#a8560a;text-decoration-color:#e8c89a;text-underline-offset:3px}
a:hover{color:var(--sun2)}
a.ref{
  font-size:.86em;background:#fff5e2;border:1px solid #f0dcb4;border-radius:999px;
  padding:1px 9px;white-space:nowrap;text-decoration:none;color:#8a4b09;margin:0 2px;
}
a.ref:hover{background:#ffe9c2}
.rn{font-weight:700;margin-inline-start:5px;color:var(--sun2)}
code{background:#f4efe4;padding:1px 6px;border-radius:5px;font-size:.9em}
nav.toc{
  background:var(--panel);border:1px solid var(--line);border-radius:14px;
  padding:22px 26px;margin:44px 0 8px;
}
nav.toc h2{border:0;margin:0 0 10px;padding:0;font-size:19px}
nav.toc ol{margin:0;padding-inline-start:22px;columns:2;column-gap:34px}
nav.toc li{margin:5px 0;break-inside:avoid}
nav.toc a{text-decoration:none;color:var(--ink-soft)}
nav.toc a:hover{color:var(--sun2)}
.folklore{background:#f8f6f1;border:1px solid var(--line);border-radius:14px;padding:18px 22px;margin:28px 0}
.folklore h3{margin-top:0}
.folklore li{color:var(--ink-soft)}
section.refs{margin-top:72px;padding-top:26px;border-top:2px solid var(--line)}
ol.reflist{list-style:none;padding:0;counter-reset:r}
ol.reflist li{
  counter-increment:r;position:relative;padding:14px 0;padding-inline-end:46px;
  border-bottom:1px solid #f2ebdd;font-size:15.5px;line-height:1.65;
}
ol.reflist li::before{
  content:counter(r);position:absolute;inset-inline-end:0;top:15px;width:30px;height:30px;
  background:var(--sun1);color:#fff;border-radius:50%;display:flex;
  align-items:center;justify-content:center;font-size:13px;font-weight:700;
}
ol.reflist .t{font-weight:600;color:var(--ink)}
ol.reflist .v{color:var(--muted);font-size:14px}
ol.reflist .u{display:block;word-break:break-all;font-size:13px;direction:ltr;text-align:left;margin-top:3px}
.tag{
  display:inline-block;font-size:11.5px;padding:1px 8px;border-radius:999px;
  border:1px solid var(--line);color:var(--muted);margin-inline-start:6px;background:#fff;
}
.tag.s-strong{border-color:#b6d8c3;color:var(--ok);background:#f2f9f5}
.tag.s-contested{border-color:#f0c6ac;color:var(--warn);background:#fff5ef}
.cav{color:var(--muted);font-size:13.5px;margin-top:4px;font-style:italic}
.langbar{position:absolute;top:20px;inset-inline-end:26px;display:flex;gap:8px}
.langbar a{
  font-size:14px;text-decoration:none;color:var(--ink-soft);background:#fff;
  border:1px solid var(--line);border-radius:999px;padding:5px 15px;font-weight:600;
}
.langbar a:hover{border-color:var(--sun1);color:var(--sun2)}
.langbar a.on{background:var(--sun1);border-color:var(--sun1);color:#fff}
@media print{.langbar{display:none}}
footer{margin-top:64px;padding-top:24px;border-top:1px solid var(--line);color:var(--muted);font-size:14px}
@media print{
  @page{size:A4;margin:16mm 14mm}
  body{font-size:11.5pt;line-height:1.62;background:#fff}
  header.hero{padding:0 0 18px;border-bottom:2px solid var(--sun1);background:none}
  .sun{width:62px;height:62px}
  h1{font-size:26pt}
  .sub{font-size:12pt}
  h2{font-size:16pt;margin:22pt 0 4pt;break-after:avoid;break-before:auto}
  h3{font-size:13pt;break-after:avoid}
  p,li{orphans:3;widows:3}
  .wrap{max-width:none;padding:0}
  nav.toc{break-inside:avoid}
  .folklore,blockquote{break-inside:avoid}
  ol.reflist li{break-inside:avoid}
  a{color:#8a4b09}
  a.ref{border:0;background:none;padding:0 2px}
  section.refs{break-before:page}
}
"""

SUN_SVG = """<svg class="sun" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="shemesh">
<defs><radialGradient id="g" cx="50%" cy="50%"><stop offset="0%" stop-color="#fde08a"/><stop offset="60%" stop-color="#f6a416"/><stop offset="100%" stop-color="#e4670c"/></radialGradient></defs>
<g stroke="#f0a11a" stroke-width="3.2" stroke-linecap="round">
<line x1="50" y1="4" x2="50" y2="15"/><line x1="50" y1="85" x2="50" y2="96"/>
<line x1="4" y1="50" x2="15" y2="50"/><line x1="85" y1="50" x2="96" y2="50"/>
<line x1="17.5" y1="17.5" x2="25.3" y2="25.3"/><line x1="74.7" y1="74.7" x2="82.5" y2="82.5"/>
<line x1="17.5" y1="82.5" x2="25.3" y2="74.7"/><line x1="74.7" y1="25.3" x2="82.5" y2="17.5"/>
</g><circle cx="50" cy="50" r="24" fill="url(#g)"/></svg>"""

PAGE = """<!DOCTYPE html>
<html lang="%(lang)s" dir="%(dir)s">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>%(title)s</title>
<meta name="description" content="%(subtitle)s">
<meta name="robots" content="noindex,nofollow">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Assistant:wght@300;400;600;700&amp;family=Frank+Ruhl+Libre:wght@500;700;800&amp;display=swap" rel="stylesheet">
<style>%(css)s</style>
</head>
<body>
<header class="hero">
  <div class="langbar">%(langbar)s</div>
  %(sun)s
  <h1>%(title)s</h1>
  <p class="sub">%(subtitle)s</p>
  <p class="meta">%(meta)s</p>
</header>
<div class="wrap">
<nav class="toc"><h2>%(toc_title)s</h2><ol>%(toc)s</ol></nav>
%(folklore)s
%(body)s
<section class="refs">
<h2 id="refs">%(refs_title)s</h2>
<p class="sub" style="text-align:start;margin:0 0 18px;font-size:16px">%(refs_note)s</p>
<ol class="reflist">%(reflist)s</ol>
</section>
<footer>%(footer)s</footer>
</div>
</body></html>"""


def build(data, out_html):
    sections = data["sections"]
    refs = data.get("refs", [])
    refmap = {r["url"]: i + 1 for i, r in enumerate(refs)}

    toc = "\n".join('<li><a href="#%s">%s</a></li>' % (s["key"], esc(s["title"])) for s in sections)

    body = []
    for s in sections:
        html = md_to_html(s["body"], refmap)
        if "<h2>" in html:
            html = html.replace("<h2>", '<h2 id="%s">' % s["key"], 1)
        else:
            html = '<h2 id="%s">%s</h2>\n%s' % (s["key"], esc(s["title"]), html)
        body.append(html)

    items = []
    for f in (data.get("folklore_refused") or []):
        for it in (f.get("items") or []):
            if it and it.strip():
                items.append("<li>%s</li>" % esc(it.strip()))
    folklore = ""
    if items:
        folklore = ('<div class="folklore"><h3>' + esc(data.get("folklore_title", "")) +
                    "</h3><ul>" + "\n".join(items) + "</ul></div>")

    rl = []
    for r in refs:
        st = (r.get("strength") or "").lower()
        cls = "s-strong" if st == "strong" else ("s-contested" if st in ("contested", "weak") else "")
        cav = '<div class="cav">%s</div>' % esc(r["caveat"]) if r.get("caveat") else ""
        rl.append(
            '<li><span class="t">%s</span><span class="tag %s">%s</span>'
            '<span class="tag">%s</span><br>'
            '<span class="v">%s (%s) &middot; %s</span>'
            '<a class="u" href="%s" target="_blank" rel="noopener">%s</a>%s</li>'
            % (esc(r["title"]), cls, esc(r.get("strength", "")), esc(r.get("evidence_type", "")),
               esc(r["authors"]), esc(r["year"]), esc(r["venue"]), r["url"], esc(r["url"]), cav))

    doc = PAGE % {
        "lang": data.get("lang", "he"),
        "dir": data.get("dir", "rtl"),
        "langbar": data.get("langbar", ""),
        "title": esc(data.get("title", "HELIOS")),
        "subtitle": esc(data.get("subtitle", "")),
        "meta": esc(data.get("meta", "")),
        "css": CSS,
        "sun": SUN_SVG,
        "toc_title": esc(data.get("toc_title", "")),
        "toc": toc,
        "folklore": folklore,
        "body": "".join(body),
        "refs_title": esc(data.get("refs_title", "")),
        "refs_note": esc(data.get("refs_note", "")),
        "reflist": "".join(rl),
        "footer": esc(data.get("footer", "")),
    }
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(doc)
    return out_html


def render(html_path, pdf_path, jpg_path):
    from playwright.sync_api import sync_playwright
    url = "file:///" + html_path.replace("\\", "/")
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1100, "height": 1500}, device_scale_factor=2)
        pg.goto(url, wait_until="networkidle")
        pg.wait_for_timeout(2000)
        pg.pdf(path=pdf_path, format="A4", print_background=True,
               margin={"top": "16mm", "bottom": "16mm", "left": "14mm", "right": "14mm"})
        pg.screenshot(path=jpg_path, type="jpeg", quality=92,
                      clip={"x": 0, "y": 0, "width": 1100, "height": 1500})
        b.close()


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "sections.json")
    stem = sys.argv[2] if len(sys.argv) > 2 else "index"
    with open(src, encoding="utf-8") as f:
        data = json.load(f)
    h = build(data, os.path.join(SITE, stem + ".html"))
    suffix = "-" + data.get("lang", "he")
    pdf = os.path.join(SITE, "HELIOS" + suffix + ".pdf")
    jpg = os.path.join(HERE, "HELIOS" + suffix + ".jpg")
    render(h, pdf, jpg)
    print("html:", h, os.path.getsize(h))
    print("pdf :", pdf, os.path.getsize(pdf))
    print("jpg :", jpg, os.path.getsize(jpg))
