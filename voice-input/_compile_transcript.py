#!/usr/bin/env python3
# Rename the recordings folder + compile a bright Desktop transcript. UTF-8 safe.
import os, sys, datetime, html
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

OLD  = r"E:\_clod_writeok2"
NEW  = r"E:\קפה קלוד הקלטות"
DESK = os.path.join(os.environ.get("USERPROFILE", r"C:\Users\<user>"), "Desktop")

FILES = [
    "20260624061811.WAV", "20260624070723.WAV", "20260625165315.WAV",
    "20260625165526.WAV", "20260625170458.WAV", "20260625171050.WAV",
    "20260625171740.WAV", "20260625172207.WAV", "20260625172706.WAV",
    "20260625173229.WAV", "20260625173851.WAV", "20260625182956.WAV",
]

# 1) rename the folder
if os.path.isdir(NEW):
    base = NEW; print("[rename] already named:", NEW)
elif os.path.isdir(OLD):
    try:
        os.rename(OLD, NEW); base = NEW; print("[rename] OK ->", NEW)
    except Exception as e:
        base = OLD; print(f"[rename] FAILED ({e}) - using old path")
else:
    print("[error] folder not found"); sys.exit(1)

tdir = os.path.join(base, "transcripts")

def nice_dt(name):
    s = name.replace(".WAV", "").replace(".txt", "")
    try:
        return datetime.datetime.strptime(s, "%Y%m%d%H%M%S").strftime("%d/%m/%Y · %H:%M")
    except Exception:
        return name

cards, txt = [], []
for name in FILES:
    p = os.path.join(tdir, name + ".txt")
    text = open(p, encoding="utf-8").read().strip() if os.path.exists(p) else ""
    dt = nice_dt(name)
    body = html.escape(text).replace("\n", "<br>") if text else '<em class="empty">(ריק — שקט / ללא דיבור)</em>'
    cards.append(f'<section class="rec"><div class="dt">{dt}</div>'
                 f'<div class="fn">{name}</div><p>{body}</p></section>')
    txt.append(f"===== {dt}  ({name}) =====\n{text or '(empty)'}\n")

doc = f"""<!DOCTYPE html><html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>☕ קפה קלוד — תמלול הקלטות</title>
<style>
 body{{background:#faf6f0;color:#2e2620;font-family:"Segoe UI",Arial,sans-serif;line-height:1.7;margin:0}}
 .wrap{{max-width:820px;margin:0 auto;padding:36px 22px 70px}}
 header{{border-bottom:3px solid #6f4e37;padding-bottom:14px;margin-bottom:8px}}
 h1{{font-size:1.7rem;color:#6f4e37;margin:0}} .sub{{color:#8c7e70;font-size:.95rem;margin-top:6px}}
 .rec{{background:#fffdfb;border:1px solid #ece2d6;border-radius:12px;padding:16px 20px;margin:16px 0;box-shadow:0 1px 3px rgba(0,0,0,.04)}}
 .dt{{font-weight:800;color:#6f4e37;font-size:1.05rem}}
 .fn{{color:#c8a27a;font-size:.78rem;margin-bottom:8px}}
 .rec p{{margin:0;font-size:1.05rem;white-space:pre-wrap}}
 .empty{{color:#b9ad9d}}
 footer{{margin-top:30px;color:#8c7e70;font-size:.82rem;text-align:center}}
</style></head><body><div class="wrap">
<header><h1>☕ קפה קלוד — תמלול הקלטות</h1>
<div class="sub">{len(FILES)} הקלטות · תומללו מקומית ב-ivrit-ai/whisper · לעידו</div></header>
{''.join(cards)}
<footer>ALMAWARE · תמלול פרטי, נשמר במחשב שלך בלבד</footer>
</div></body></html>"""

out_html = os.path.join(DESK, "קפה קלוד — תמלול מלא.html")
out_txt  = os.path.join(DESK, "קפה קלוד — תמלול מלא.txt")
open(out_html, "w", encoding="utf-8").write(doc)
open(out_txt,  "w", encoding="utf-8").write("\n".join(txt))
print("[desktop html]", out_html)
print("[desktop txt ]", out_txt)
print("[done]")
