#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the HELIOS artifact: both editions in one page, theme-aware.

Design plan
  Color  — the document's thesis is that sunlight is a DOSE with two sides,
           so the palette carries that: warm amber/ember for the benefit
           material, a cool slate counterweight for the risk material, on a
           warm paper ground. Neutrals are warm-biased, not mid-grey.
             ink   #1a1512   paper #fffdf6   amber #e8930c
             ember #c2410c   slate #3f5a6b   line  #e9dcc4
  Type   — Frank Ruhl Libre (display) + Assistant (body). Both are Hebrew-first
           faces with full Latin, which is the correct pairing for a document
           whose primary edition is Hebrew — not a Latin face with Hebrew
           bolted on.
  Layout — one column at a ~66ch measure, sticky bar carrying the language
           switch, TOC as a two-column grid, references as a numbered list
           tagged with evidence type and strength.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build_helios import md_to_html, esc  # noqa: E402

CSS = """
:root{
  --ink:#1a1512; --ink-2:#4a3f36; --muted:#847768;
  --paper:#fffdf6; --raised:#fffefa; --line:#e9dcc4;
  --amber:#e8930c; --ember:#c2410c; --amber-soft:#fff4de;
  --slate:#3f5a6b; --slate-soft:#eef3f6;
  --ok:#2f6b46; --ok-soft:#f1f8f4;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --ink:#f2ece2; --ink-2:#c9bfb1; --muted:#95897a;
    --paper:#16130f; --raised:#1e1a15; --line:#3a3227;
    --amber:#f5ab2e; --ember:#f0733a; --amber-soft:#2c2213;
    --slate:#8fb3c7; --slate-soft:#1a2329;
    --ok:#6fbf8e; --ok-soft:#15241c;
  }
}
:root[data-theme="dark"]{
  --ink:#f2ece2; --ink-2:#c9bfb1; --muted:#95897a;
  --paper:#16130f; --raised:#1e1a15; --line:#3a3227;
  --amber:#f5ab2e; --ember:#f0733a; --amber-soft:#2c2213;
  --slate:#8fb3c7; --slate-soft:#1a2329;
  --ok:#6fbf8e; --ok-soft:#15241c;
}
*{box-sizing:border-box}
body{
  margin:0; background:var(--paper); color:var(--ink);
  font-family:'Assistant',-apple-system,'Segoe UI',system-ui,sans-serif;
  font-size:17px; line-height:1.8;
}
.bar{
  position:sticky; top:env(safe-area-inset-top,0px); z-index:20;
  display:flex; gap:10px; align-items:center; justify-content:center;
  background:color-mix(in srgb, var(--paper) 88%, transparent);
  backdrop-filter:blur(10px);
  border-bottom:1px solid var(--line); padding:10px 16px;
}
.bar button{
  font:600 14px/1 'Assistant',system-ui,sans-serif; cursor:pointer;
  background:var(--raised); color:var(--ink-2);
  border:1px solid var(--line); border-radius:999px; padding:8px 18px;
}
.bar button[aria-pressed="true"]{background:var(--amber);border-color:var(--amber);color:#1a1512}
.bar button:focus-visible{outline:2px solid var(--ember);outline-offset:2px}
.wrap{max-width:760px;margin:0 auto;padding-inline:16px;padding-block:0 96px}
.hero{text-align:center;padding-block:56px 36px;border-bottom:1px solid var(--line)}
.sun{width:74px;height:74px;display:block;margin:0 auto 20px}
h1{
  font-family:'Frank Ruhl Libre',Georgia,serif;font-weight:800;
  font-size:clamp(30px,5.2vw,44px);line-height:1.15;margin:0 0 12px;
  text-wrap:balance;letter-spacing:-.3px;
}
.sub{color:var(--ink-2);font-size:19px;margin:0 auto;max-width:56ch;text-wrap:balance}
.meta{color:var(--muted);font-size:13.5px;margin-top:18px;font-variant-numeric:tabular-nums}
h2{
  font-family:'Frank Ruhl Libre',Georgia,serif;font-weight:700;
  font-size:27px;line-height:1.3;margin:56px 0 4px;padding-top:24px;
  border-top:1px solid var(--line);text-wrap:balance;
}
h3{font-family:'Frank Ruhl Libre',Georgia,serif;font-weight:700;font-size:21px;margin:32px 0 2px;text-wrap:balance}
h4{font-size:17px;font-weight:700;margin:22px 0 0;color:var(--ink-2)}
p{margin:13px 0;max-width:66ch}
ul,ol{margin:13px 0;padding-inline-start:24px;max-width:66ch}
li{margin:6px 0}
blockquote{margin:20px 0;padding:12px 18px;border-inline-start:3px solid var(--amber);
  background:var(--amber-soft);border-radius:8px;color:var(--ink-2)}
a{color:var(--ember);text-underline-offset:3px;text-decoration-color:color-mix(in srgb,var(--ember) 35%,transparent)}
a.ref{
  font-size:.84em;background:var(--amber-soft);border:1px solid var(--line);
  border-radius:999px;padding:1px 9px;white-space:nowrap;text-decoration:none;
  color:var(--ember);margin:0 2px;font-variant-numeric:tabular-nums;
}
code{background:var(--raised);border:1px solid var(--line);padding:0 5px;border-radius:4px;font-size:.9em}
nav.toc{background:var(--raised);border:1px solid var(--line);border-radius:12px;padding:20px 24px;margin:40px 0 8px}
nav.toc h2{border:0;margin:0 0 8px;padding:0;font-size:17px}
nav.toc ol{margin:0;padding-inline-start:20px;display:grid;grid-template-columns:repeat(2,1fr);gap:4px 28px;max-width:none}
nav.toc a{text-decoration:none;color:var(--ink-2)}
@media (max-width:560px){nav.toc ol{grid-template-columns:1fr}}
.folklore{background:var(--slate-soft);border:1px solid var(--line);border-radius:12px;padding:18px 22px;margin:28px 0}
.folklore h3{margin-top:0;color:var(--slate)}
.folklore li{color:var(--ink-2);font-size:15.5px}
section.refs{margin-top:64px;padding-top:24px;border-top:2px solid var(--amber)}
ol.reflist{list-style:none;padding:0;counter-reset:r;max-width:none}
ol.reflist li{counter-increment:r;position:relative;padding-block:12px;padding-inline-end:42px;
  border-bottom:1px solid var(--line);font-size:15px;line-height:1.6}
ol.reflist li::before{content:counter(r);position:absolute;inset-inline-end:0;top:14px;
  width:27px;height:27px;background:var(--amber);color:#1a1512;border-radius:50%;
  display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;
  font-variant-numeric:tabular-nums}
ol.reflist .t{font-weight:600}
ol.reflist .v{color:var(--muted);font-size:13.5px}
ol.reflist .u{display:block;word-break:break-all;font-size:12.5px;direction:ltr;text-align:left;margin-top:2px}
.tag{display:inline-block;font-size:11px;padding:1px 8px;border-radius:999px;border:1px solid var(--line);
  color:var(--muted);margin-inline-start:6px;background:var(--raised)}
.tag.s-strong{border-color:var(--ok);color:var(--ok);background:var(--ok-soft)}
.tag.s-contested{border-color:var(--ember);color:var(--ember);background:var(--amber-soft)}
.cav{color:var(--muted);font-size:13px;margin-top:3px;font-style:italic}
footer{margin-top:56px;padding-top:20px;border-top:1px solid var(--line);color:var(--muted);font-size:13.5px}
table{border-collapse:collapse;width:100%;font-size:15px}
.scroll{overflow-x:auto}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
"""

SUN = """<svg class="sun" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
<defs><radialGradient id="sg" cx="50%" cy="46%"><stop offset="0%" stop-color="#ffd884"/><stop offset="58%" stop-color="#e8930c"/><stop offset="100%" stop-color="#c2410c"/></radialGradient></defs>
<g stroke="#e8930c" stroke-width="3" stroke-linecap="round">
<line x1="50" y1="5" x2="50" y2="16"/><line x1="50" y1="84" x2="50" y2="95"/>
<line x1="5" y1="50" x2="16" y2="50"/><line x1="84" y1="50" x2="95" y2="50"/>
<line x1="18" y1="18" x2="25.8" y2="25.8"/><line x1="74.2" y1="74.2" x2="82" y2="82"/>
<line x1="18" y1="82" x2="25.8" y2="74.2"/><line x1="74.2" y1="25.8" x2="82" y2="18"/>
</g><circle cx="50" cy="50" r="23" fill="url(#sg)"/></svg>"""


def edition(d, refmap, hidden):
    toc = "\n".join('<li><a href="#%s-%s">%s</a></li>' % (d["lang"], s["key"], esc(s["title"]))
                    for s in d["sections"])
    body = []
    for s in d["sections"]:
        html = md_to_html(s["body"], refmap)
        anchor = '<h2 id="%s-%s">' % (d["lang"], s["key"])
        html = html.replace("<h2>", anchor, 1) if "<h2>" in html else anchor + esc(s["title"]) + "</h2>\n" + html
        body.append(html)

    def item_dir(t):
        # First strong character decides. Latin text inside an RTL block
        # renders its punctuation on the wrong side unless it says so itself.
        for ch in t:
            if "֐" <= ch <= "׿":
                return "rtl"
            if ch.isalpha():
                return "ltr"
        return d["dir"]

    items = ['<li dir="%s">%s</li>' % (item_dir(i), esc(i.strip()))
             for f in (d.get("folklore_refused") or []) for i in (f.get("items") or []) if i.strip()]
    folk = ('<div class="folklore"><h3>%s</h3><ul>%s</ul></div>'
            % (esc(d["folklore_title"]), "\n".join(items))) if items else ""

    rl = []
    for r in d["refs"]:
        st = (r.get("strength") or "").lower()
        cls = "s-strong" if st == "strong" else ("s-contested" if st in ("contested", "weak") else "")
        rl.append('<li><span class="t">%s</span><span class="tag %s">%s</span>'
                  '<span class="tag">%s</span><br><span class="v">%s (%s) &middot; %s</span>'
                  '<a class="u" href="%s" target="_blank" rel="noopener">%s</a>'
                  '%s</li>'
                  % (esc(r["title"]), cls, esc(r.get("strength", "")), esc(r.get("evidence_type", "")),
                     esc(r["authors"]), esc(r["year"]), esc(r["venue"]), r["url"], esc(r["url"]),
                     '<div class="cav">%s</div>' % esc(r["caveat"]) if r.get("caveat") else ""))

    return ('<div class="ed" id="ed-%s" dir="%s" lang="%s"%s>'
            '<header class="hero">%s<h1>%s</h1><p class="sub">%s</p><p class="meta">%s</p></header>'
            '<nav class="toc"><h2>%s</h2><ol>%s</ol></nav>%s%s'
            '<section class="refs"><h2 id="%s-refs">%s</h2><p class="sub" style="text-align:start;margin:0 0 16px;font-size:15px">%s</p>'
            '<ol class="reflist">%s</ol></section><footer>%s</footer></div>'
            % (d["lang"], d["dir"], d["lang"], " hidden" if hidden else "",
               SUN, esc(d["title"]), esc(d["subtitle"]), esc(d["meta"]),
               esc(d["toc_title"]), toc, folk, "".join(body),
               d["lang"], esc(d["refs_title"]), esc(d["refs_note"]), "".join(rl), esc(d["footer"])))


if __name__ == "__main__":
    he = json.load(open(os.path.join(HERE, "sections_he.json"), encoding="utf-8"))
    en = json.load(open(os.path.join(HERE, "sections_en.json"), encoding="utf-8"))
    refmap = {r["url"]: i + 1 for i, r in enumerate(he["refs"])}

    out = """<title>HELIOS</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Assistant:wght@300;400;600;700&amp;family=Frank+Ruhl+Libre:wght@500;700;800&amp;display=swap" rel="stylesheet">
<style>%s</style>
<div class="bar">
  <button id="b-he" aria-pressed="true">עברית</button>
  <button id="b-en" aria-pressed="false">English</button>
</div>
<div class="wrap">%s%s</div>
<script>
(function(){
  var he=document.getElementById('ed-he'), en=document.getElementById('ed-en');
  var bhe=document.getElementById('b-he'), ben=document.getElementById('b-en');
  function show(lang){
    var isHe = lang==='he';
    he.hidden=!isHe; en.hidden=isHe;
    bhe.setAttribute('aria-pressed', isHe?'true':'false');
    ben.setAttribute('aria-pressed', isHe?'false':'true');
    try{ localStorage.setItem('helios-lang', lang); }catch(e){}
    window.scrollTo(0,0);
  }
  bhe.addEventListener('click', function(){ show('he'); });
  ben.addEventListener('click', function(){ show('en'); });
  try{ var s=localStorage.getItem('helios-lang'); if(s==='en') show('en'); }catch(e){}
})();
</script>""" % (CSS, edition(he, refmap, False), edition(en, refmap, True))

    p = os.path.join(HERE, "helios_artifact.html")
    open(p, "w", encoding="utf-8").write(out)
    print("artifact:", p, os.path.getsize(p), "bytes")
