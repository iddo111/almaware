"""assemble_site.py — build the ALMAWARE Encyclopedia as one self-contained HTML page.

Reads  build/editorial.md + build/<slug>.md  and  plates/<slug>.png
Writes site/index.html            (full-size plates, for Cloudflare Pages)
       site/artifact.html         (down-scaled plates inlined as data URIs, <16 MB)

python assemble_site.py
"""
from __future__ import annotations

import base64
import io
import pathlib
import re

import markdown
from PIL import Image

ROOT = pathlib.Path(r"D:\CLAUDE\eran-encyclopedia")
BUILD = ROOT / "build"
PLATES = ROOT / "plates"
SITE = ROOT / "site"
SITE.mkdir(exist_ok=True)
(SITE / "plates").mkdir(exist_ok=True)

# order matters: this is the book's spine
CHAPTERS = [
    ("water-computing", "מחשוב מכני והידראולי", "Mechanical &amp; Hydraulic Computing"),
    ("physical-weights", "משקולות פיזיות", "Physical Weights &amp; Neuromorphic Substrates"),
    ("tape-brain", "מוח־הסרט", "The Tape Brain"),           # plate only, folded into physical-weights
    ("eran-child", "ערן — מבייט אפס", "ERAN: From Byte Zero"),
    ("beit-din", "נוירון בית הדין", "The Beit-Din Neuron"),
    ("voice-keshev", "קשב — השמיעה", "KESHEV: Hearing"),
    ("darwish-memorial", "דרוויש — מודל כהנצחה", "Darwish: A Model as a Memorial"),
    ("fleet-engineering", "הנדסת הצי", "Engineering the Fleet"),
    ("optics-sensing", "אופטיקה זולה", "Cheap Optics &amp; Sensing"),
    ("materials-safety", "חומרים שנוגעים באדם", "Materials That Touch a Human"),
    ("moral-architecture", "ארכיטקטורה מוסרית", "Moral Architecture"),
]

MD = markdown.Markdown(extensions=["tables", "fenced_code", "toc", "sane_lists"])


def render(md_text: str) -> str:
    MD.reset()
    return MD.convert(md_text)


def plate_tag(slug: str, inline: bool, alt: str) -> str:
    src = PLATES / f"{slug}.png"
    if not src.exists():
        return ""
    if inline:
        im = Image.open(src).convert("RGB")
        im.thumbnail((1400, 1400), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=78, optimize=True)
        b64 = base64.b64encode(buf.getvalue()).decode()
        url = f"data:image/jpeg;base64,{b64}"
    else:
        im = Image.open(src).convert("RGB")
        im.save(SITE / "plates" / f"{slug}.jpg", "JPEG", quality=92, optimize=True)
        url = f"plates/{slug}.jpg"
    return f'<figure class="plate"><img src="{url}" alt="{alt}" loading="lazy"></figure>'


CSS = """
:root{
  --ink:#101a24; --ink-2:#33475c; --ink-3:#6a7f93;
  --ground:#fbfaf7; --panel:#ffffff; --line:#dfe4ea;
  --water:#0e7c9b; --water-soft:#e3f2f6; --brass:#b07d34; --flag:#a8324a;
  --shadow:0 1px 2px rgba(16,26,36,.05), 0 12px 32px -18px rgba(16,26,36,.35);
}
@media (prefers-color-scheme: dark){ :root:not([data-theme="light"]){
  --ink:#e8eef4; --ink-2:#b3c2d0; --ink-3:#7d8fa1;
  --ground:#0b1118; --panel:#111a23; --line:#1f2c38;
  --water:#4cc7e8; --water-soft:#0f2831; --brass:#d7a45c; --flag:#e8697f;
  --shadow:0 1px 2px rgba(0,0,0,.4), 0 18px 40px -22px rgba(0,0,0,.9);
}}
:root[data-theme="dark"]{
  --ink:#e8eef4; --ink-2:#b3c2d0; --ink-3:#7d8fa1;
  --ground:#0b1118; --panel:#111a23; --line:#1f2c38;
  --water:#4cc7e8; --water-soft:#0f2831; --brass:#d7a45c; --flag:#e8697f;
  --shadow:0 1px 2px rgba(0,0,0,.4), 0 18px 40px -22px rgba(0,0,0,.9);
}
*{box-sizing:border-box}
body{margin:0;background:var(--ground);color:var(--ink);
  font:16px/1.68 -apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;
  -webkit-font-smoothing:antialiased}
.wrap{max-width:1180px;margin:0 auto;padding:0 24px;display:grid;grid-template-columns:250px 1fr;gap:48px}
@media(max-width:900px){.wrap{grid-template-columns:1fr;gap:0}}

/* ---- masthead ---- */
.mast{padding:72px 24px 40px;border-bottom:1px solid var(--line);background:var(--panel)}
.mast-in{max-width:1180px;margin:0 auto}
.eyebrow{font:600 12px/1 ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.18em;
  text-transform:uppercase;color:var(--water)}
h1.title{font:600 clamp(34px,6vw,62px)/1.05 Georgia,"Times New Roman",serif;
  margin:14px 0 6px;letter-spacing:-.02em;text-wrap:balance}
.title-he{font:400 clamp(20px,3.4vw,30px)/1.2 Georgia,serif;color:var(--ink-2);margin:0 0 18px}
.dek{max-width:62ch;color:var(--ink-2);font-size:17px;margin:0}
.meta{display:flex;flex-wrap:wrap;gap:10px;margin-top:26px}
.chip{font:600 12px/1 ui-monospace,monospace;letter-spacing:.04em;padding:7px 11px;border-radius:999px;
  background:var(--water-soft);color:var(--water);border:1px solid transparent}
.chip.brass{background:transparent;border-color:var(--brass);color:var(--brass)}
.chip.flag{background:transparent;border-color:var(--flag);color:var(--flag)}

/* ---- nav ---- */
nav.toc{position:sticky;top:0;align-self:start;max-height:100vh;overflow:auto;
  padding:40px 0 40px;font-size:14px}
@media(max-width:900px){nav.toc{position:static;max-height:none;border-bottom:1px solid var(--line)}}
nav.toc a{display:block;padding:7px 12px;color:var(--ink-2);text-decoration:none;border-radius:7px;
  border-left:2px solid transparent}
nav.toc a:hover{background:var(--water-soft);color:var(--water)}
nav.toc a.on{border-left-color:var(--water);color:var(--ink);font-weight:600}
nav.toc .n{font:600 11px/1 ui-monospace,monospace;color:var(--ink-3);margin-inline-end:8px}
nav.toc h4{font:600 11px/1 ui-monospace,monospace;letter-spacing:.16em;text-transform:uppercase;
  color:var(--ink-3);margin:22px 12px 8px}

/* ---- body ---- */
main{padding:40px 0 120px;min-width:0}
section.ch{scroll-margin-top:24px;margin-bottom:76px}
section.ch>h2{font:600 clamp(26px,3.4vw,38px)/1.15 Georgia,serif;margin:0 0 4px;letter-spacing:-.015em;
  text-wrap:balance}
.ch-he{font:400 19px/1.4 Georgia,serif;color:var(--ink-3);margin:0 0 22px;direction:rtl;text-align:start}
.plate{margin:0 0 30px}
.plate img{width:100%;height:auto;display:block;border-radius:12px;box-shadow:var(--shadow)}
.body h2{font:600 24px/1.25 Georgia,serif;margin:38px 0 10px}
.body h3{font:600 18px/1.3 -apple-system,system-ui,sans-serif;margin:28px 0 8px;color:var(--ink)}
.body h4{font:600 14px/1.3 ui-monospace,monospace;letter-spacing:.06em;text-transform:uppercase;
  color:var(--ink-3);margin:22px 0 6px}
.body p{max-width:68ch;color:var(--ink-2)}
.body strong{color:var(--ink)}
.body a{color:var(--water)}
.body ul,.body ol{max-width:66ch;color:var(--ink-2)}
.body li{margin:5px 0}
.body code{font:13px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;background:var(--water-soft);
  color:var(--water);padding:2px 6px;border-radius:5px}
.body pre{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px;
  overflow-x:auto}
.body pre code{background:none;color:var(--ink);padding:0}
.body blockquote{margin:20px 0;padding:2px 0 2px 18px;border-left:3px solid var(--brass);
  color:var(--ink-2);font-style:italic}
.tablewrap{overflow-x:auto;margin:20px 0}
.body table{border-collapse:collapse;width:100%;font-size:14px;font-variant-numeric:tabular-nums}
.body th,.body td{border:1px solid var(--line);padding:8px 11px;text-align:start;vertical-align:top}
.body th{background:var(--panel);font-weight:600;color:var(--ink)}
hr{border:0;border-top:1px solid var(--line);margin:44px 0}
footer{border-top:1px solid var(--line);padding:40px 24px 80px;text-align:center;color:var(--ink-3);
  font-size:14px}
footer .ded{font:400 20px/1.4 Georgia,serif;color:var(--ink-2);margin-bottom:10px;direction:rtl}
a:focus-visible,nav.toc a:focus-visible{outline:2px solid var(--water);outline-offset:2px}
@media(prefers-reduced-motion:no-preference){section.ch{transition:opacity .3s}}
"""

JS = """
const links=[...document.querySelectorAll('nav.toc a')];
const secs=links.map(a=>document.querySelector(a.getAttribute('href'))).filter(Boolean);
const io=new IntersectionObserver(es=>{es.forEach(e=>{if(e.isIntersecting){
  links.forEach(l=>l.classList.toggle('on',l.getAttribute('href')==='#'+e.target.id));}});},
  {rootMargin:'-10% 0px -80% 0px'});
secs.forEach(s=>io.observe(s));
document.querySelectorAll('.body table').forEach(t=>{
  const w=document.createElement('div');w.className='tablewrap';
  t.parentNode.insertBefore(w,t);w.appendChild(t);});
"""


def build(inline_plates: bool, out_name: str) -> pathlib.Path:
    ed = (BUILD / "editorial.md").read_text(encoding="utf-8")
    # the editor's own ToC table is replaced by the live nav, so drop it
    ed = re.sub(r"##\s*2\.\s*Table of Contents.*?(?=\n##\s*3\.)", "", ed, flags=re.S)

    nav = ['<nav class="toc"><h4>הספר · The Book</h4>',
           '<a href="#preface"><span class="n">00</span>Editor\'s Preface</a>']
    body = ['<section class="ch" id="preface">',
            plate_tag("cover", inline_plates, "A laser projecting a drop of pond water onto a gallery wall"),
            '<div class="body">', render(ed), '</div></section>']

    n = 0
    for slug, he, en in CHAPTERS:
        f = BUILD / f"{slug}.md"
        if not f.exists():
            continue
        n += 1
        nav.append(f'<a href="#{slug}"><span class="n">{n:02d}</span>{en}</a>')
        body.append(f'<section class="ch" id="{slug}">')
        body.append(f'<h2>{en}</h2><p class="ch-he">{he}</p>')
        body.append(plate_tag(slug, inline_plates, en))
        body.append('<div class="body">' + render(f.read_text(encoding="utf-8")) + '</div>')
        body.append('</section>')
    nav.append('</nav>')

    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>The ALMAWARE Encyclopedia</title>
<meta name="description" content="Volume I — computing you can point at: water neurons, punched-film weights, a machine taught from byte zero, and a Talmudic court that audits them all.">
<style>{CSS}</style></head>
<body>
<header class="mast"><div class="mast-in">
  <div class="eyebrow">Volume I · {n} chapters · audited by the Beit Din</div>
  <h1 class="title">The ALMAWARE Encyclopedia</h1>
  <p class="title-he">אנציקלופדיית אלמאוור — כרך א׳</p>
  <p class="dek">One idea holds every chapter: <strong>put the computation somewhere you can point at it.</strong>
     A weight that is a hole you can count. A model taught from byte zero, every bit traceable to a file.
     A microphone that writes its journal before it writes your words. And a court that refuses a single
     confident answer.</p>
  <div class="meta">
    <span class="chip">10 chapters · 186,000 characters</span>
    <span class="chip brass">12 plates rendered on eran2 · FLUX.1-dev</span>
    <span class="chip flag">every claim graded — none passed clean</span>
  </div>
</div></header>
<div class="wrap">{''.join(nav)}<main>{''.join(body)}</main></div>
<footer><p class="ded">לזכרה של עלמה ז״ל</p>
<p>Written by a fleet of four DGX Sparks and a council of agents, 2026-08-19 · Rishon LeTsiyyon</p></footer>
<script>{JS}</script>
</body></html>"""
    out = SITE / out_name
    out.write_text(html, encoding="utf-8")
    print(f"{out}  {out.stat().st_size/1_000_000:.2f} MB  ({n} chapters)")
    return out


if __name__ == "__main__":
    build(inline_plates=False, out_name="index.html")
    build(inline_plates=True, out_name="artifact.html")
