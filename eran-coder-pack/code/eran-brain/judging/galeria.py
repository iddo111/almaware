#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
galeria.py — גלריה. One read-only page: every model, its REAL outputs, to see and to hear.
Port 8861 (claimed in RAMCHAT 2026-09-03 18:44, claude-cli-FABLE).

"תן לי דוח על כל המודלים מה איתם - תעלה תוצרים לראות ולשמוע" (Iddo, 2026-09-03 18:41)

Manifest-driven: every GET re-reads galeria/<model>/manifest.json, so whatever the
gatherers add appears on refresh. Files are served from galeria/<model>/<file> only.
LABEL LAW: every wav name starts with its speaker — ERAN / CLAUDE / IDDO / DARWISH.
Nothing autoplays. Never writes anything. Never touches an audio device.
"""
import html
import json
import os
import http.server
import socketserver
import urllib.parse
from datetime import datetime

PORT = 8861
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "galeria")

# order, folder, Hebrew name, where it runs, status chip, one measured line (DOCH-KOLEL 18:15 + re-probe 18:42), links
MODELS = [
    ("eran", u"ערן — הילד", u"eran1", u"🟢 חי · 🔴 לא לומד",
     u"פעימה 247 מיליון, 12 יום ברצף. 13 הברות \"נשלטות\" = זיהוי בשמיעה, לא הפקה. מהפה שלו עצמו יש רק בַּ (חיפוש v4) ו-אַה מ-24.8. "
     u"הפטפוט החי (babble) הוא הדבקה של קליפים אנושיים — לא הקול שלו, ולכן לא כאן.",
     [(u"החלון של ערן (eran1:8820)", "http://<lan-ip>:8820/"), (u"להאזין לערן חי", "http://<lan-ip>:8807/")]),
    ("moreh", u"המורה והתלמיד — MOREH", u"eran2 + PC", u"🟡 שלב א' — פסק נַ ממתין לך",
     u"המורה (קלוד בפה המבוגר): 24/24 הברות, 668 שיעורים. התלמיד (holobrain/moreh): 5/24 הברות שלא ראה. שום דבר לא חווט לערן החי.",
     [(u"לשמוע את המורה ולפסוק (8859)", "http://127.0.0.1:8859/"), (u"מקום (8858)", "http://127.0.0.1:8858/")]),
    ("winston", u"וינסטון v2 — הצייר", u"eran4", u"🟢 מתאמן",
     u"מאז 2.9 22:24, 256px, 93 תצלומים, --guard --recompute. הקריסה לקשת (logits 24k) אובחנה ומגודרת.", []),
    ("kav", u"קו — KAV", u"PC (הולובריין)", u"🟡 שער 2 פתוח",
     u"נבנה מחדש על אינדקסי קודקודים. הדקדוק מוכח (תקרה 3/3 מוצקים). הלומד המחבר: 0.551 מול מראה 0.571, 0/3 מוצקים. זה החוסם של המשחק.", []),
    ("tzelem", u"צלם — TZELEM", u"PC (הולובריין)", u"🟡 ממתין ל-KAV",
     u"שער 1 (1.9): ×4.6 יציב יותר, בלי מאגר עומק, בלי מיון — הפעימה היא העומק. לא נגעו מאז 2.9.", []),
    ("darwish", u"דרוויש — DARWISH", u"eran4", u"🟢 חי",
     u"darwish_life --live + tap :8806 עונה 200, כותב metrics עכשיו — אבל לא הלחין קטע חדש מאז 21.8. לזכר לאור (נובה).", [(u"tap (eran4:8806)", "http://<lan-ip>:8806/")]),
    ("nezer", u"נצר — NEZER", u"eran3", u"🟢 חי · 🟡 נסוג בסבב האחרון",
     u"131 סבבים. השיא 0.6441 בסבב 74; הסבב האחרון (75, 18:16) נסוג ל-0.6163. נולד 0.4861, תקרה 0.6771. האוזן לא חווטה מחדש — לקורפוס אין תוויות הברה.", []),
    ("keshev", u"קשב — KESHEV, המיקרופון", u"PC GPU :8737", u"🟢",
     u"STT על ה-3070 Ti, :8737 עונה (401 = דורש מפתח, תקין). eran1:8737 גיבוי.", []),
    ("hebrew", u"המודל העברי — ייחוס ושופט", u"eran2", u"🟡 השופט עובד · 🔴 ה-TTS נפסל",
     u"שופט פונמות (wav2vec2-xlsr-53-espeak) כמסווג סגור על 24 ההברות. 26.5% על 132 הקליפים האנושיים, אבל 4/5 על שלך. "
     u"ה-TTS העברי (mms-tts-heb) לא מבטא עיצורים — תוצאה שלילית מדודה.", []),
    ("school-v3", u"המורה תחת השופט העברי", u"eran2", u"🟡 12/24",
     u"שער 3: 7,200 עיצובים, 300 לכל הברה. 12/24 עברו. כל החוככים נדחו. הסרגל הישן אישר 24/24 — השופט לא.", []),
    ("movie", u"הסרט — PERCEPTRON × DARWISH", u"PC", u"🟡 חתך ראשון, קפוא",
     u"64 שניות ראשונות קיימות (LTX על ה-DGX). 3 פגמים פתוחים מ-28.8.", []),
    ("einayim", u"עיניים — שתי מצלמות לתלת-ממד", u"eran3 + PC", u"🟢 נמדד מול אמת · 🔴 עוד לא צולם עצם אמיתי",
     u"VGGT-1B על eran3 קיבל רק תמונות מהבמה של צלם. שגיאת עומק חציונית על אותו מבט: שתי מצלמות סמוכות 0.80% (חדר) / 0.57% (איברים), "
     u"שמונה מבטים 0.83% / 0.38%, בסיס-שטוח 20.8%. שתי מצלמות בבסיס קטן מספיקות למשטח הנראה; עוד מצלמות קונות כיסוי, לא דיוק. "
     u"חסר: וידאו 20 שניות שלך סביב עצם אחד -> EINAYIM-drop.", []),
]

# models with no artifact to show — one line each, so the report is complete
TEXT_ONLY = [
    (u"החושים — eran2", u"🟢", u"sense_organ :8830 (סוקט גולמי, לא HTTP), alma-stt :8844, שמש :8850 עונה."),
    (u"שריד / שפה אחת — eran3", u"⚪", u"safa-achat/loop.py רץ. התקדמות לא נמדדה היום."),
    (u"מיקו — MIKO", u"⚪", u"מודל-כקוד. המספרים הראשונים (29.8) הפריכו את התזה. לא נגעו מאז 30.8."),
    (u"כסף — KESEF, eran1", u"🟡", u"live_portfolio serve רץ. נייר בלבד — אין מסחר חי. מספרים לא נמדדו."),
    (u"הטלפון — S26", u"🟡", u"Qwen3-8B/4B + gemma + Claude CLI ב-Termux אומתו 14:01. הדלת סגורה: sshd :8022 לא עונה עד שתפתח Termux."),
    (u"שופט — JUDGE", u"📋", u"הנחיה שלך מ-3.9: LoRA/סוכן שמכיר את ההברות ומלמד+שופט את ערן. צריך ~100 קליפים אנושיים להברה קודם."),
]

MIME = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".gif": "image/gif", ".mp4": "video/mp4", ".webm": "video/webm", ".mid": "audio/midi", ".txt": "text/plain; charset=utf-8",
        ".json": "application/json; charset=utf-8", ".stl": "application/octet-stream", ".svg": "image/svg+xml"}

CSS = u"""
 *{box-sizing:border-box;margin:0;padding:0}
 body{background:#fff;color:#1f2420;font-family:"Assistant","Segoe UI",Arial,sans-serif;padding:0 18px 80px;max-width:1100px;margin:0 auto;line-height:1.5}
 h1{font-size:28px;margin:16px 0 4px;border-bottom:3px solid #e4572e;padding-bottom:6px}
 h2{font-size:22px;margin:26px 0 6px;color:#2e6b45}
 .sub{color:#666;font-size:14px}
 table.s{border-collapse:collapse;width:100%;margin:10px 0 6px;font-size:15px}
 table.s td,table.s th{border-bottom:1px solid #eee;padding:6px 8px;text-align:right;vertical-align:top}
 table.s th{background:#f6f6f6;font-weight:700}
 table.s a{color:#1a4d8f}
 .chip{white-space:nowrap;font-weight:700}
 .card{border:1px solid #ddd;border-radius:14px;padding:12px 14px;margin:10px 0;background:#fff}
 .line{color:#444;font-size:15px;margin:4px 0 10px}
 .links a{color:#1a4d8f;margin-left:14px;font-size:14px}
 .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}
 .it{border:1px solid #e6e6e6;border-radius:12px;padding:10px;background:#fcfcfc}
 .it .lab{font-weight:700;font-size:16px}
 .it .lab.eran{color:#e4572e}.it .lab.claude{color:#2e6b45}.it .lab.iddo{color:#1a4d8f}.it .lab.darwish{color:#7a3e9d}
 .it .note{color:#777;font-size:13px;margin:2px 0 6px}
 .it .src{color:#aaa;font-size:11px;direction:ltr;text-align:left;word-break:break-all;margin-top:4px}
 audio{width:100%;height:34px;margin:4px 0}
 img.th{width:100%;height:auto;border-radius:8px;border:1px solid #eee;background:#fff;cursor:zoom-in}
 video{width:100%;border-radius:8px;background:#000}
 pre.tx{white-space:pre-wrap;font-size:13px;background:#f7f7f7;padding:8px;border-radius:8px;max-height:220px;overflow:auto}
 .empty{color:#b8860b;font-size:14px}
 .foot{margin-top:30px;color:#888;font-size:13px}
 @media (max-width:640px){.grid{grid-template-columns:1fr}}
"""


def load_manifest(folder):
    p = os.path.join(ROOT, folder, "manifest.json")
    if not os.path.isfile(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:  # noqa
        return {"error": str(exc), "items": []}


def speaker_class(name):
    n = name.upper()
    for k in ("ERAN", "CLAUDE", "IDDO", "DARWISH"):
        if n.startswith(k):
            return k.lower()
    return ""


def render_item(folder, it):
    f = it.get("file", "")
    kind = it.get("kind", "")
    url = "/f/%s/%s" % (folder, urllib.parse.quote(f))
    exists = os.path.isfile(os.path.join(ROOT, folder, f))
    parts = [u"<div class='it'><div class='lab %s'>%s</div>" % (speaker_class(f), html.escape(it.get("label_he", f)))]
    if it.get("note_he"):
        parts.append(u"<div class='note'>%s</div>" % html.escape(it["note_he"]))
    if not exists:
        parts.append(u"<div class='empty'>הקובץ חסר על הדיסק: %s</div>" % html.escape(f))
    elif kind == "audio":
        parts.append(u"<audio controls preload='none' src='%s'></audio>" % url)
        sp = it.get("spectrogram")
        if sp and os.path.isfile(os.path.join(ROOT, folder, sp)):
            su = "/f/%s/%s" % (folder, urllib.parse.quote(sp))
            parts.append(u"<a href='%s' target='_blank'><img class='th' loading='lazy' src='%s' alt='spectrogram'></a>" % (su, su))
    elif kind == "image":
        parts.append(u"<a href='%s' target='_blank'><img class='th' loading='lazy' src='%s' alt='%s'></a>" % (url, url, html.escape(f)))
    elif kind == "video":
        parts.append(u"<video controls preload='metadata' src='%s'></video>" % url)
    elif kind == "text":
        try:
            with open(os.path.join(ROOT, folder, f), "r", encoding="utf-8", errors="replace") as fh:
                txt = fh.read(4000)
        except Exception as exc:  # noqa
            txt = str(exc)
        parts.append(u"<pre class='tx'>%s</pre>" % html.escape(txt))
    else:
        parts.append(u"<a href='%s' target='_blank'>%s</a>" % (url, html.escape(f)))
    parts.append(u"<div class='src'>%s · %s</div></div>" % (html.escape(f), html.escape(str(it.get("source", "")))))
    return u"".join(parts)


def page():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    parts = [u"<!doctype html><html lang='he' dir='rtl'><head><meta charset='utf-8'>",
             u"<meta name='viewport' content='width=device-width,initial-scale=1'>",
             u"<title>גלריה — כל המודלים, לראות ולשמוע</title><style>%s</style></head><body>" % CSS,
             u"<h1>גלריה 🎨🎙️ <span class='sub'>כל המודלים — התוצרים האמיתיים שלהם · %s</span></h1>" % now,
             u"<div class='sub'>כל צליל נושא את שם הדובר בשם הקובץ: <b style='color:#e4572e'>ERAN</b> = הפה של ערן · "
             u"<b style='color:#2e6b45'>CLAUDE</b> = המורה בפה המבוגר · <b style='color:#1a4d8f'>IDDO</b> = אתה · "
             u"<b style='color:#7a3e9d'>DARWISH</b>. שום דבר לא מתנגן לבד. קריאה בלבד.</div>"]

    # summary table
    parts.append(u"<h2>המצב, בשורה אחת לכל מודל</h2><table class='s'><tr><th>מודל</th><th>איפה</th><th>מצב</th><th>נמדד</th></tr>")
    for folder, name, where, chip, line, links in MODELS:
        parts.append(u"<tr><td><a href='#%s'>%s</a></td><td>%s</td><td class='chip'>%s</td><td>%s</td></tr>"
                     % (folder, html.escape(name), html.escape(where), chip, html.escape(line)))
    for name, chip, line in TEXT_ONLY:
        parts.append(u"<tr><td>%s</td><td></td><td class='chip'>%s</td><td>%s</td></tr>" % (html.escape(name), chip, html.escape(line)))
    parts.append(u"</table><div class='sub'>המצב נמדד 18:15–18:42 (ssh לצי, curl לכל פורט). הדו\"ח הכתוב המלא: "
                 u"<a href='http://127.0.0.1:8858/'>מקום :8858</a> → דוחות של היום → DOCH-KOLEL-20260903.</div>")

    # per-model sections
    for folder, name, where, chip, line, links in MODELS:
        parts.append(u"<h2 id='%s'>%s <span class='sub'>%s · %s</span></h2><div class='card'>" % (folder, html.escape(name), html.escape(where), chip))
        m = load_manifest(folder)
        if links:
            parts.append(u"<div class='links'>" + u"".join(u"<a href='%s' target='_blank'>%s ↗</a>" % (u, html.escape(t)) for t, u in links) + u"</div>")
        if m is None:
            parts.append(u"<div class='line'>%s</div><div class='empty'>התוצרים עוד נאספים… (אין manifest.json) — רענן בעוד דקה.</div>" % html.escape(line))
        else:
            parts.append(u"<div class='line'>%s</div>" % html.escape(m.get("status_line_he") or line))
            items = m.get("items") or []
            if m.get("error"):
                parts.append(u"<div class='empty'>manifest שבור: %s</div>" % html.escape(m["error"]))
            if not items:
                parts.append(u"<div class='empty'>אין תוצרים בתיקייה.</div>")
            else:
                parts.append(u"<div class='grid'>" + u"".join(render_item(folder, it) for it in items) + u"</div>")
        parts.append(u"</div>")

    parts.append(u"<p class='foot'>galeria.py · 127.0.0.1:8861 · קריאה בלבד · הקבצים ב-eran-brain/judging/galeria/ · "
                 u"חוק התווית: שם הדובר בשם הקובץ, תמיד.</p></body></html>")
    return u"".join(parts)


class H(http.server.BaseHTTPRequestHandler):
    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError):
            pass

    def do_GET(self):
        path = urllib.parse.unquote(self.path.split("?", 1)[0])
        if path.startswith("/f/"):
            rel = path[3:].replace("\\", "/")
            if ".." in rel.split("/"):
                return self._send(404, "text/plain", b"no")
            full = os.path.normpath(os.path.join(ROOT, rel))
            if not full.startswith(os.path.normpath(ROOT)) or not os.path.isfile(full):
                return self._send(404, "text/plain", b"not found")
            ext = os.path.splitext(full)[1].lower()
            with open(full, "rb") as f:
                data = f.read()
            return self._send(200, MIME.get(ext, "application/octet-stream"), data)
        if path in ("/", "/index.html"):
            return self._send(200, "text/html; charset=utf-8", page().encode("utf-8"))
        return self._send(404, "text/plain", b"not found")

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("127.0.0.1", PORT), H) as srv:
        srv.serve_forever()
