import re, html, pathlib

src = pathlib.Path(r"D:\CLAUDE\eran-encyclopedia\ERAN-Research-Encyclopedia.md").read_text(encoding="utf-8", errors="replace")

def inline(t):
    t = html.escape(t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"\*(.+?)\*", r"<i>\1</i>", t)
    t = re.sub(r"`(.+?)`", r"<code>\1</code>", t)
    t = re.sub(r"(https?://[^\s<]+)", r'<a href="\1">\1</a>', t)
    return t

out, in_list = [], False
for line in src.splitlines():
    s = line.rstrip()
    if not s.strip():
        if in_list: out.append("</ul>"); in_list = False
        continue
    if s.startswith("> "):
        out.append('<blockquote>' + inline(s[2:]) + '</blockquote>'); continue
    m = re.match(r"^(#{1,4})\s+(.*)", s)
    if m:
        if in_list: out.append("</ul>"); in_list = False
        lvl = len(m.group(1)); out.append(f"<h{lvl}>{inline(m.group(2))}</h{lvl}>"); continue
    if s.strip() == "---":
        if in_list: out.append("</ul>"); in_list = False
        out.append("<hr>"); continue
    lm = re.match(r"^(\s*)[-*]\s+(.*)", s)
    if lm:
        if not in_list: out.append("<ul>"); in_list = True
        out.append("<li>" + inline(lm.group(2)) + "</li>"); continue
    nm = re.match(r"^\s*(\d+)\.\s+(.*)", s)
    if nm:
        if not in_list: out.append("<ul>"); in_list = True
        out.append("<li>" + inline(nm.group(2)) + "</li>"); continue
    if in_list: out.append("</ul>"); in_list = False
    out.append("<p>" + inline(s) + "</p>")
if in_list: out.append("</ul>")

body = "\n".join(out)
page = """<!doctype html><html><head><meta charset="utf-8"><style>
body{background:#fff;color:#1a1512;font-family:'Segoe UI',Georgia,serif;max-width:900px;margin:0 auto;padding:44px 54px;line-height:1.5}
h1{font-size:30px;color:#6a2f8a;border-bottom:3px solid #e5d5ee;padding-bottom:8px}
h2{font-size:23px;color:#7a3b12;margin-top:34px;border-bottom:2px solid #eadfce;padding-bottom:4px}
h3{font-size:18px;color:#8a5a2b;margin-top:22px} h4{font-size:15px;color:#555}
a{color:#2764b0;word-break:break-all;font-size:12px} code{background:#f2eef8;padding:1px 5px;border-radius:4px;font-size:13px}
blockquote{background:#fbf3e8;border-left:5px solid #c8843b;padding:8px 14px;border-radius:6px;color:#5a3a1a;font-size:14px}
li{margin:6px 0} ul{margin:6px 0} hr{border:none;border-top:1px solid #e0d8cc;margin:26px 0}
p{margin:8px 0}
</style></head><body>
""" + body + "\n</body></html>"
p = r"D:\CLAUDE\eran-encyclopedia\ERAN-Research-Encyclopedia.html"
pathlib.Path(p).write_text(page, encoding="utf-8")
print("HTML written:", p, "chars", len(page))
