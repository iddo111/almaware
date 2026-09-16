"""assemble_future.py — the Future-of-AI encyclopedia as one illustrated page.

The lineage, in order: Ada -> Turing -> from the Perceptron to now -> then the domains
of where it is heading. Plates from future-plates/ (chapter-matched) with a fallback to
the earlier plates/ set.

python assemble_future.py   ->  future-site/index.html (+ artifact.html)
"""
from __future__ import annotations

import base64
import io
import pathlib
import re

import markdown
from PIL import Image

ROOT = pathlib.Path(r"D:\CLAUDE\eran-encyclopedia")
BUILD = ROOT / "future-build"
P_NEW = ROOT / "future-plates"
P_OLD = ROOT / "plates"
SITE = ROOT / "future-site"
SITE.mkdir(exist_ok=True)
(SITE / "plates").mkdir(exist_ok=True)

# lineage order; (slug, plate-slug, he)
CH = [
    ("ada", "ada", "עדה לאבלייס — הראשונה שראתה מעבר למספרים"),
    ("turing", "turing", "טורינג — השאלה שהתחילה הכל"),
    ("links", "links", "החוליות החסרות בשושלת"),
    ("history", "history", "מהפרספטרון עד היום"),
    ("developmental", "eran-child", "ללמוד מבייט אפס"),
    ("world-models", "world-models", "מודלי-עולם וניבוי-הגיסט"),
    ("speech", "speech", "ללמוד לדבר מצליל גולמי"),
    ("audio", "audio", "אודיו נוירוני והקול של המכונה"),
    ("embodiment", "embodiment", "גופים, רובוטים וגלגל-הנתונים"),
    ("neuromorphic", "physical-weights", "AI פיזי: משקולות שאפשר לגעת בהן"),
    ("safety", "moral-architecture", "יישור ומכונות בנות-עוררין"),
]

MD = markdown.Markdown(extensions=["tables", "fenced_code", "sane_lists"])


def render(t: str) -> str:
    MD.reset()
    return MD.convert(t)


def plate(pslug: str, inline: bool, alt: str) -> str:
    src = P_NEW / f"{pslug}.png"
    if not src.exists():
        src = P_OLD / f"{pslug}.png"
    if not src.exists():
        return ""
    if inline:
        im = Image.open(src).convert("RGB")
        im.thumbnail((1400, 1400), Image.LANCZOS)
        b = io.BytesIO()
        im.save(b, "JPEG", quality=78, optimize=True)
        url = "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()
    else:
        Image.open(src).convert("RGB").save(SITE / "plates" / f"{pslug}.jpg", "JPEG",
                                            quality=92, optimize=True)
        url = f"plates/{pslug}.jpg"
    return f'<figure class="plate"><img src="{url}" alt="{alt}" loading="lazy"></figure>'


CSS = """
:root{--ground:#fbfaf7;--panel:#fff;--line:#e6e1d6;--ink:#1a1c22;--ink2:#454a55;--ink3:#8a8578;
--accent:#7a4bd0;--accent2:#c8892a;--shadow:0 1px 2px rgba(26,28,34,.05),0 14px 34px -20px rgba(26,28,34,.4)}
@media(prefers-color-scheme:dark){:root:not([data-theme="light"]){--ground:#0f1014;--panel:#16181f;
--line:#262932;--ink:#ece9f0;--ink2:#b6b3c2;--ink3:#7c7890;--accent:#b491f0;--accent2:#e0b56a;
--shadow:0 1px 2px rgba(0,0,0,.4),0 18px 40px -22px rgba(0,0,0,.9)}}
:root[data-theme="dark"]{--ground:#0f1014;--panel:#16181f;--line:#262932;--ink:#ece9f0;--ink2:#b6b3c2;
--ink3:#7c7890;--accent:#b491f0;--accent2:#e0b56a;--shadow:0 1px 2px rgba(0,0,0,.4),0 18px 40px -22px rgba(0,0,0,.9)}
*{box-sizing:border-box}body{margin:0;background:var(--ground);color:var(--ink);
font:17px/1.7 -apple-system,"Segoe UI",system-ui,sans-serif;-webkit-font-smoothing:antialiased}
.mast{padding:76px 24px 44px;border-bottom:1px solid var(--line);background:var(--panel)}
.mast-in{max-width:1160px;margin:0 auto}
.eyebrow{font:600 12px/1 ui-monospace,monospace;letter-spacing:.2em;text-transform:uppercase;color:var(--accent)}
h1.title{font:600 clamp(36px,6.5vw,66px)/1.03 Georgia,serif;margin:14px 0 4px;letter-spacing:-.02em;text-wrap:balance}
.title-he{font:400 clamp(19px,3vw,26px)/1.3 Georgia,serif;color:var(--ink2);margin:0 0 20px;direction:rtl}
.dek{max-width:64ch;color:var(--ink2);font-size:18px;margin:0}
.wrap{max-width:1160px;margin:0 auto;padding:0 24px;display:grid;grid-template-columns:240px 1fr;gap:52px}
@media(max-width:900px){.wrap{grid-template-columns:1fr;gap:0}}
nav{position:sticky;top:0;align-self:start;max-height:100vh;overflow:auto;padding:44px 0;font-size:14px}
@media(max-width:900px){nav{position:static;max-height:none;border-bottom:1px solid var(--line)}}
nav a{display:block;padding:8px 12px;color:var(--ink2);text-decoration:none;border-radius:8px;border-left:2px solid transparent}
nav a:hover{background:color-mix(in srgb,var(--accent) 12%,transparent);color:var(--accent)}
nav a.on{border-left-color:var(--accent);color:var(--ink);font-weight:600}
nav .n{font:600 11px/1 ui-monospace,monospace;color:var(--ink3);margin-inline-end:8px}
nav h4{font:600 11px/1 ui-monospace,monospace;letter-spacing:.16em;text-transform:uppercase;color:var(--ink3);margin:22px 12px 8px}
main{padding:44px 0 120px;min-width:0}
section{scroll-margin-top:22px;margin-bottom:80px}
section>h2{font:600 clamp(27px,3.4vw,40px)/1.13 Georgia,serif;margin:0 0 4px;letter-spacing:-.015em;text-wrap:balance}
.ch-he{font:400 19px/1.4 Georgia,serif;color:var(--ink3);margin:0 0 24px;direction:rtl}
.plate{margin:0 0 30px}.plate img{width:100%;height:auto;display:block;border-radius:14px;box-shadow:var(--shadow)}
.body h2{font:600 25px/1.25 Georgia,serif;margin:40px 0 10px;color:var(--ink)}
.body h3{font:600 19px/1.3 system-ui,sans-serif;margin:30px 0 8px}
.body p{max-width:70ch;color:var(--ink2)}.body strong{color:var(--ink)}
.body a{color:var(--accent)}.body ul,.body ol{max-width:68ch;color:var(--ink2)}.body li{margin:6px 0}
.body blockquote{margin:22px 0;padding:6px 0 6px 20px;border-left:3px solid var(--accent2);color:var(--ink2);font-style:italic;font-size:19px}
.body code{font:14px ui-monospace,monospace;background:color-mix(in srgb,var(--accent) 12%,transparent);color:var(--accent);padding:2px 6px;border-radius:5px}
.tablewrap{overflow-x:auto;margin:20px 0}.body table{border-collapse:collapse;width:100%;font-size:15px}
.body th,.body td{border:1px solid var(--line);padding:8px 11px;text-align:start}
.body th{background:var(--panel);font-weight:600}
footer{border-top:1px solid var(--line);padding:44px 24px 90px;text-align:center;color:var(--ink3);font-size:14px}
footer .ded{font:400 21px/1.4 Georgia,serif;color:var(--ink2);margin-bottom:10px;direction:rtl}
a:focus-visible,nav a:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
"""

JS = """
const L=[...document.querySelectorAll('nav a')],S=L.map(a=>document.querySelector(a.getAttribute('href'))).filter(Boolean);
new IntersectionObserver(es=>es.forEach(e=>{if(e.isIntersecting)L.forEach(l=>l.classList.toggle('on',l.getAttribute('href')==='#'+e.target.id))}),{rootMargin:'-10% 0 -80% 0'}).observe&&S.forEach(s=>new IntersectionObserver(es=>es.forEach(e=>{if(e.isIntersecting)L.forEach(l=>l.classList.toggle('on',l.getAttribute('href')==='#'+e.target.id))}),{rootMargin:'-10% 0 -80% 0'}).observe(s));
document.querySelectorAll('.body table').forEach(t=>{const w=document.createElement('div');w.className='tablewrap';t.parentNode.insertBefore(w,t);w.appendChild(t)});
"""


def build(inline: bool, name: str) -> pathlib.Path:
    front = (BUILD / "front.md").read_text(encoding="utf-8")
    nav = ['<nav><h4>השושלת · The Lineage</h4>',
           '<a href="#front"><span class="n">00</span>Preface &amp; First Reads</a>']
    body = ['<section id="front">', plate("cover", inline, "The Future of AI"),
            '<div class="body">', render(front), '</div></section>']
    n = 0
    for slug, pslug, he in CH:
        f = BUILD / f"{slug}.md"
        if not f.exists():
            continue
        md = f.read_text(encoding="utf-8")
        title = md.splitlines()[0].lstrip("# ").strip() if md.lstrip().startswith("#") else slug
        # our chapter files start with body text (Ada) or a heading; derive an EN title
        en = {"ada": "Ada Lovelace", "turing": "Turing", "links": "The Missing Links",
              "history": "From the Perceptron to Now",
              "developmental": "Learning From Byte Zero", "world-models": "World Models",
              "speech": "Learning to Speak", "audio": "The Machine Voice",
              "embodiment": "Bodies & Robots", "neuromorphic": "Physical AI",
              "safety": "Alignment"}[slug]
        n += 1
        nav.append(f'<a href="#{slug}"><span class="n">{n:02d}</span>{en}</a>')
        body.append(f'<section id="{slug}"><h2>{en}</h2><p class="ch-he">{he}</p>')
        body.append(plate(pslug, inline, en))
        body.append('<div class="body">' + render(md) + '</div></section>')
    nav.append('</nav>')

    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>The Future of AI</title>
<meta name="description" content="A lineage of intelligence from Ada Lovelace and Turing to where AI is heading — grounded, embodied, physical, contestable machines that learn from little.">
<style>{CSS}</style></head><body>
<header class="mast"><div class="mast-in">
<div class="eyebrow">An Encyclopedia · from Ada Lovelace to what comes next</div>
<h1 class="title">The Future of AI</h1>
<p class="title-he">אנציקלופדיה — השושלת ולאן זה הולך</p>
<p class="dek">One through-line binds two hundred years: the next intelligence will be
<strong>grounded, embodied, physical, contestable — and it will learn from little</strong>.
This traces the chain from the first person to imagine a thinking machine to the researchers
building the one that comes next.</p></div></header>
<div class="wrap">{''.join(nav)}<main>{''.join(body)}</main></div>
<footer><p class="ded">לזכרה של עלמה ז״ל</p>
<p>{n} chapters · written by a fleet of DGX Sparks and an editor, illustrated on FLUX · 2026-08-19</p></footer>
<script>{JS}</script></body></html>"""
    out = SITE / name
    out.write_text(html, encoding="utf-8")
    print(f"{out}  {out.stat().st_size/1_000_000:.2f} MB  ({n} chapters)")
    return out


if __name__ == "__main__":
    build(False, "index.html")
    build(True, "artifact.html")
