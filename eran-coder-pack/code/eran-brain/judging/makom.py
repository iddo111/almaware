#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
makom.py — מקום. One page for Iddo: ERAN live, his sittings, today's reports,
today's builds, the council. Port 8858 (claimed in RAMCHAT 2026-09-03).

"תעלה לי דברים של ערן, תעלה לי שיפוטי, תעלה לי עניינים, תראה לי מקום." (Iddo, 12:45)

Read-only. Renders on every GET from live sources: eran1:8820 (the organism's
window), the three sitting servers' /n, the reports archive, moreh/STATUS.md,
RAMCHAT's durable transcript. Never writes anything. Never plays audio.
"""
import html
import io
import json
import os
import re
import http.server
import socketserver
import urllib.request
from datetime import datetime

PORT = 8858
HERE = os.path.dirname(os.path.abspath(__file__))
ARCHIVE = r"D:\CLAUDE\_status-reports-archive"
MOREH_STATUS = r"D:\CLAUDE\eran-brain\holobrain\moreh\STATUS.md"
RAMCHAT = r"D:\CLAUDE\RAMCHAT\ramchat_session.json"
VERDICTS = os.path.join(HERE, "iddo-verdicts.jsonl")
ERAN_WINDOW = "http://<lan-ip>:8820/"

SITTINGS = [
    ("שפוט את קלוד", "http://127.0.0.1:8857/", 24, "claude-sitting",
     "24 הברות שקלוד עשה ביד בפה של ערן. אתה אומר מה שמעת."),
    ("ישיבה 3 — נַ והקורפוס", "http://127.0.0.1:8862/", 20, "sitting3",
     "6 מועמדי נַ + הנַ הכי טוב של school-v3 + 2 שיעורי נַ מקוריים + 10 קליפי קורפוס אנושי + עוגן שלך. השופט העברי חולק עליך על המועמדים — רק האוזן שלך מכריעה."),
    ("בית ספר ישיבה 2", "http://127.0.0.1:8856/", 24, "school2",
     "גרסה של המורה מול ניחוש של ערן על הברה שלא ראה. א או ב."),
    ("בית ספר ישיבה 1", "http://127.0.0.1:8855/", 21, "school",
     "ביד מול הניחוש הישן של ערן. א או ב."),
]


def get(url, timeout=4):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    except Exception as exc:  # noqa
        return None


def eran_live():
    body = get(ERAN_WINDOW)
    if not body:
        return {"alive": False}
    txt = re.sub(r"<[^>]+>", " ", body)
    d = {"alive": True}
    for key in ("beat", "prototypes", "mass", "energy", "unit"):
        m = re.search(r"%s\s+<?b?>?\s*([A-Za-z0-9.]+)" % key, txt)
        if m:
            d[key] = m.group(1)
    m = re.search(r"unit\s*<b>\s*([a-z]+)", body)
    if m:
        d["unit"] = m.group(1)
    return d


def sitting_counts():
    out = []
    for name, url, n, src, blurb in SITTINGS:
        j = get(url.rstrip("/") + "/n", timeout=3)
        try:
            done = json.loads(j)["n"] if j else None
        except Exception:  # noqa
            done = None
        out.append((name, url, n, done, blurb))
    return out


def claude_sitting_score():
    """Iddo's blind identification of Claude's syllables — only if he has judged."""
    if not os.path.isfile(VERDICTS):
        return None
    last = {}
    with io.open(VERDICTS, encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("source") == "claude-sitting":
                last[r.get("blind_label")] = r
    if not last:
        return None
    ok = sum(1 for r in last.values() if r.get("correct"))
    return ok, len(last)


def reports():
    out = []
    if os.path.isdir(ARCHIVE):
        for fn in sorted(os.listdir(ARCHIVE), reverse=True):
            if "20260903" in fn and fn.lower().endswith((".md", ".html")):
                out.append(os.path.join(ARCHIVE, fn))
    return out[:8]


def read_text(path, limit=6000):
    try:
        with io.open(path, encoding="utf-8", errors="replace") as f:
            s = f.read(limit + 1)
        return s[:limit] + ("\n…" if len(s) > limit else "")
    except OSError:
        return "(לא נמצא)"


def council_tail(n=12):
    try:
        with io.open(RAMCHAT, encoding="utf-8") as f:
            d = json.load(f)
    except Exception:  # noqa
        return []
    msgs = d if isinstance(d, list) else d.get("messages") or d.get("transcript") or []
    rows = []
    for m in msgs[-n:]:
        if not isinstance(m, dict):
            continue
        who = m.get("who") or m.get("author") or m.get("name") or "?"
        ts = str(m.get("ts") or m.get("time") or "")[-8:]
        txt = str(m.get("text") or m.get("msg") or m.get("message") or "")
        rows.append((ts, who, txt[:260]))
    return rows


CSS = u"""
 *{box-sizing:border-box;margin:0;padding:0}
 body{background:#fff;color:#1f2420;font-family:"Assistant","Segoe UI",Arial,sans-serif;padding:0 18px 60px;line-height:1.5;max-width:900px;margin:0 auto}
 h1{font-size:26px;margin:16px 0 4px;border-bottom:3px solid #e4572e;padding-bottom:6px}
 h2{font-size:20px;margin:22px 0 8px;color:#2e6b45}
 .sub{color:#666;font-size:14px}
 .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}
 .card{background:#fff;border:1px solid #ddd;border-radius:14px;padding:12px 14px}
 .card a.big{display:block;font-size:20px;font-weight:700;color:#1a4d8f;text-decoration:none;margin-bottom:4px}
 .card .n{font-size:15px;color:#333}
 .ok{color:#2e8b57;font-weight:700} .bad{color:#b00020;font-weight:700} .warn{color:#b8860b;font-weight:700}
 .kv{display:flex;flex-wrap:wrap;gap:8px 18px;font-size:16px}
 .kv b{color:#2e6b45}
 pre{background:#f7f7f2;border:1px solid #e3e3d8;border-radius:10px;padding:10px 12px;white-space:pre-wrap;font-size:13px;direction:rtl;text-align:right;max-height:420px;overflow:auto}
 details summary{cursor:pointer;font-size:16px;font-weight:700;margin:8px 0}
 .council div{font-size:13px;border-bottom:1px dashed #e3e3d8;padding:4px 0}
 .council b{color:#1a4d8f}
 a{color:#1a4d8f}
"""


def page():
    now = datetime.now().strftime("%H:%M:%S")
    e = eran_live()
    parts = [u"<!doctype html><html lang='he' dir='rtl'><head><meta charset='utf-8'>",
             u"<meta name='viewport' content='width=device-width,initial-scale=1'>",
             u"<meta http-equiv='refresh' content='120'>",
             u"<title>מקום — ערן ועידו</title><style>%s</style></head><body>" % CSS,
             u"<h1>מקום 🧠 <span class='sub'>ערן, השיפוטים שלך, העניינים · %s</span></h1>" % now]

    # ERAN live
    parts.append(u"<h2>ערן, חי</h2><div class='card'>")
    if e.get("alive"):
        parts.append(u"<div class='kv'><span class='ok'>חי</span>")
        for k, heb in (("beat", "פעימה"), ("prototypes", "אבות-טיפוס"), ("mass", "מסה"),
                       ("energy", "אנרגיה"), ("unit", "הברה עכשיו")):
            if e.get(k):
                parts.append(u"<span><b>%s</b> %s</span>" % (heb, html.escape(str(e[k]))))
        parts.append(u"</div>")
    else:
        parts.append(u"<span class='bad'>החלון של ערן לא עונה</span>")
    parts.append(u"<div class='n' style='margin-top:6px'><a href='%s' target='_blank'>החלון של ערן (eran1:8820)</a> · "
                 u"<a href='http://<lan-ip>:8807/' target='_blank'>להאזין לערן חי</a> · "
                 u"<a href='http://127.0.0.1:8861/' target='_blank'><b>גלריה: כל המודלים, לראות ולשמוע (8861)</b></a></div>"
                 u"<div class='n'>מצב הלמידה: 13 הברות נשלטות, 9 במעגל חזרה מאז 24.8. הסיבה: 3 הקלטות להברה. "
                 u"המורה (MOREH) עובד לידו, לא בתוכו.</div></div>" % ERAN_WINDOW)

    # sittings
    parts.append(u"<h2>השיפוטים שלך</h2><div class='grid'>")
    for name, url, n, done, blurb in sitting_counts():
        if done is None:
            st = u"<span class='bad'>השרת לא עונה</span>"
        elif done >= n:
            st = u"<span class='ok'>סיימת %d / %d ✔</span>" % (done, n)
        elif done == 0:
            st = u"<span class='warn'>עוד לא התחלת · 0 / %d</span>" % n
        else:
            st = u"<span class='warn'>%d / %d</span>" % (done, n)
        parts.append(u"<div class='card'><a class='big' href='%s' target='_blank'>%s</a><div class='n'>%s</div><div class='n'>%s</div></div>"
                     % (url, html.escape(name), st, html.escape(blurb)))
    parts.append(u"</div>")
    sc = claude_sitting_score()
    if sc:
        parts.append(u"<div class='n' style='margin-top:8px'>שפוט את קלוד עד עכשיו: זיהית נכון <b>%d</b> מתוך %d שדנת.</div>" % sc)

    # today's builds
    parts.append(u"<h2>העניינים של היום</h2><div class='grid'>")
    builds = [
        (u"המורה (MOREH) — ערן לומד הברות", u"24/24 הברות של המורה מאומתות, 333 שיעורים. ערן על הברה שלא ראה: 5 מתוך 24 (אתמול 1 מתוך 21).", None),
        (u"מיקרופון ALMA v2 בטלפון", u"מותקן, מאזין, מתמלל דרך eran1. לחיצה שלך: בטל אופטימיזציית סוללה.", None),
        (u"קלוד קוד בטרמוקס", u"מותקן, גרסה 2.1.259, מחכה להתחברות שלך. סוכן מסדר עכשיו כלים, גישה לצי, ומודל מקומי.", None),
        (u"ועדת קלוד דסקטופ", u"לא קרס: עדכון MSIX תוך כדי ריצה תקע את ווינדוס. ריסטארט הוא התיקון. עדכון נוסף ממתין.", None),
        (u"ועדת קשב", u"אפס קריסות אמיתיות. אנחנו מפילים אותו. הטרמינל של ה-CLI לעולם לא כמנהל. היה מושהה מ-08:56.", None),
        (u"KAV / קו", u"נבנה מחדש על אינדקסי קודקודים (בוקר). השער הפתוח: הלומד המחבר.", None),
        (u"WebXR לקווסט", u"שתי הדלתות פתוחות: http 8870, https 8871. קיצור 'QUEST - WebXR' על שולחן העבודה. בקסדה: https://<lan-ip>:8871/ ואז 'בדיקת WebXR'. לא אומת בקסדה עצמה עדיין.", None),
        (u"הטלפון: מודל מקומי + קלוד CLI", u"שני סוכנים חסומים בדלת: טרמוקס סגור, דיבוג אלחוטי כבוי. פעולה אחת שלך: פתח טרמוקס והקלד sshd.", None),
    ]
    for title, blurb, link in builds:
        parts.append(u"<div class='card'><div class='big' style='font-size:18px;font-weight:700'>%s</div><div class='n'>%s</div></div>"
                     % (html.escape(title), html.escape(blurb)))
    parts.append(u"</div>")

    # reports
    parts.append(u"<h2>דוחות של היום</h2>")
    for p in reports():
        parts.append(u"<details><summary>%s</summary><pre>%s</pre></details>"
                     % (html.escape(os.path.basename(p)), html.escape(read_text(p))))
    if os.path.isfile(MOREH_STATUS):
        parts.append(u"<details><summary>המורה — STATUS</summary><pre>%s</pre></details>" % html.escape(read_text(MOREH_STATUS)))

    # council
    parts.append(u"<h2>המועצה (RAMCHAT), אחרונים</h2><div class='council'>")
    for ts, who, txt in council_tail():
        parts.append(u"<div><b>%s</b> <span class='sub'>%s</span> %s</div>" % (html.escape(who), html.escape(ts), html.escape(txt)))
    parts.append(u"</div>")
    parts.append(u"<p class='sub' style='margin-top:20px'>קריאה בלבד. מתרענן כל שתי דקות. שום דבר כאן לא מנגן צליל לבד.</p></body></html>")
    return u"".join(parts)


class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = page().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError):
            pass

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("127.0.0.1", PORT), H) as srv:
        srv.serve_forever()
