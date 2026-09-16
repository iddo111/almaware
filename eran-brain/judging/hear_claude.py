#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
hear_claude.py — "תן לי לשמוע אותך אומר הברות קודם כל" (Iddo, 2026-09-03 13:51).
Port 8859. NOT blind: every clip is labelled. Nothing autoplays; he presses play.

Speaker of every clip here is CLAUDE, operating ERAN's adult physics mouth (the
teacher). Sources on this PC:
  hand-made 09-02:  throat-one-sample/school/ERAN-<syl>.wav        (served as /hand/<syl>.wav)
  lessons   09-03:  throat-one-sample/school-v2/lessons/CLAUDE-<syl>-vNN.wav (served as /v/<syl>/NN.wav)
  Iddo's own:       throat-one-sample/LISTEN/IDDO-<syl>.wav         (served as /iddo/<syl>.wav)
Anything else is 404.
"""
import glob
import html
import os
import re
import http.server
import socketserver
import urllib.parse

PORT = 8859
HERE = os.path.dirname(os.path.abspath(__file__))
TOS = os.path.join(os.path.dirname(HERE), "throat-one-sample")
HAND = os.path.join(TOS, "school")
LESSONS = os.path.join(TOS, "school-v2", "lessons")
IDDO = os.path.join(TOS, "LISTEN")
CAND = os.path.join(TOS, "school-v2", "candidates")   # CLAUDE-<syl>-cand-<X>.wav: for his ruling

ORDER = ["a", "ba", "ma", "na", "pa", "ta", "da", "ka", "qa", "ga", "la", "ra", "sa", "sha",
         "za", "tza", "va", "wa", "fa", "ha", "kha", "cha", "ya", "aya"]
HEB = {"a": "אַ", "aya": "אַיָה", "ba": "בַּ", "va": "בַ", "wa": "וַ", "ga": "גַ", "da": "דַ",
       "ha": "הַ", "za": "זַ", "cha": "חַ", "kha": "כַ", "ta": "תַ", "ya": "יַ", "ka": "כַּ",
       "qa": "קַ", "la": "לַ", "ma": "מַ", "na": "נַ", "sa": "סַ", "pa": "פַּ", "fa": "פַ",
       "tza": "צַ", "ra": "רַ", "sha": "שַׁ"}
NOTE = {"tza": "נכשל אתמול, תוקן היום", "ka": "נכשל אתמול, תוקן היום", "qa": "נכשל אתמול, תוקן היום"}


def candidates(syl):
    out = []
    for p in sorted(glob.glob(os.path.join(CAND, "CLAUDE-%s-cand-*.wav" % syl))):
        m = re.search(r"-cand-([A-Z])\.wav$", p)
        if m:
            out.append(m.group(1))
    return out


def variants(syl):
    out = []
    for p in sorted(glob.glob(os.path.join(LESSONS, "CLAUDE-%s-v*.wav" % syl))):
        m = re.search(r"-v(\d+)\.wav$", p)
        if m:
            out.append(m.group(1))
    return out


CSS = u"""
 *{box-sizing:border-box;margin:0;padding:0}
 body{background:#fff;color:#1f2420;font-family:"Assistant","Segoe UI",Arial,sans-serif;padding:0 16px 60px;max-width:820px;margin:0 auto;line-height:1.5}
 h1{font-size:26px;margin:14px 0 4px;border-bottom:3px solid #e4572e;padding-bottom:6px}
 .sub{color:#666;font-size:14px;margin-bottom:12px}
 .card{border:1px solid #ddd;border-radius:14px;padding:12px 14px;margin:10px 0}
 .syl{font-size:38px;font-weight:700;color:#2e6b45;line-height:1.1}
 .lat{color:#888;font-size:13px;margin-right:8px}
 .note{color:#b8860b;font-size:13px}
 .row{display:flex;align-items:center;gap:10px;margin:6px 0;flex-wrap:wrap}
 .lab{min-width:120px;font-size:15px;font-weight:700}
 .lab.you{color:#1a4d8f}
 .lab.cand{color:#e4572e}
 .card.ask{border:2px solid #e4572e;background:#fff8f5}
 audio{height:34px;flex:1;min-width:220px}
 .more{display:none}
 .card.open .more{display:flex}
 button{font-size:14px;padding:6px 12px;border-radius:10px;border:1px solid #bbb;background:#fafafa;font-family:inherit;cursor:pointer}
"""


def page():
    parts = [u"<!doctype html><html lang='he' dir='rtl'><head><meta charset='utf-8'>",
             u"<meta name='viewport' content='width=device-width,initial-scale=1'>",
             u"<title>לשמוע את המורה — קלוד אומר הברות</title><style>%s</style></head><body>" % CSS,
             u"<h1>לשמוע את המורה 🎙️</h1>",
             u"<div class='sub'>כל קליפ כאן: קלוד מפעיל את הפה המבוגר של ערן. \"ביד\" = אתמול בלילה. \"שיעור\" = היום, מאומת בסרגל. \"אתה\" = ההקלטה שלך. שום דבר לא מתנגן לבד.</div>"]
    for syl in ORDER:
        vs = variants(syl)
        parts.append(u"<div class='card' id='s-%s'><div class='syl'>%s <span class='lat'>%s</span>%s</div>"
                     % (syl, HEB.get(syl, syl), syl,
                        (u" <span class='note'>%s</span>" % NOTE[syl]) if syl in NOTE else u""))
        cs = candidates(syl)
        if cs:
            parts[-1] = parts[-1].replace(u"<div class='card' id='s-%s'>" % syl, u"<div class='card ask' id='s-%s'>" % syl, 1)
            HL = {"A": u"א", "B": u"ב", "C": u"ג", "D": u"ד", "E": u"ה", "F": u"ו", "G": u"ז", "H": u"ח"}
            letters = u" או ".join(HL.get(X, X) for X in cs)
            parts.append(u"<div class='note'>סיבוב 2. פסקת: הישן וגם א/ב/ג נשמעים מַ. עכשיו הלשון עצמה זזה. איזה מהם הוא %s? תגיד לי: %s (או אף אחד).</div>" % (HEB.get(syl, syl), letters))
            for X in cs:
                heb = {"A": u"א", "B": u"ב", "C": u"ג", "D": u"ד", "E": u"ה", "F": u"ו"}.get(X, X)
                parts.append(u"<div class='row'><span class='lab cand'>מועמד %s</span><audio controls preload='none' src='/cand/%s/%s.wav'></audio></div>" % (heb, syl, X))
        if os.path.isfile(os.path.join(IDDO, "IDDO-%s.wav" % syl)):
            parts.append(u"<div class='row'><span class='lab you'>אתה</span><audio controls preload='none' src='/iddo/%s.wav'></audio></div>" % syl)
        if os.path.isfile(os.path.join(HAND, "ERAN-%s.wav" % syl)):
            parts.append(u"<div class='row'><span class='lab'>ביד, אתמול</span><audio controls preload='none' src='/hand/%s.wav'></audio></div>" % syl)
        for i, v in enumerate(vs):
            cls = "row" if i < 3 else "row more"
            parts.append(u"<div class='%s'><span class='lab'>שיעור %s</span><audio controls preload='none' src='/v/%s/%s.wav'></audio></div>" % (cls, v, syl, v))
        if len(vs) > 3:
            parts.append(u"<button onclick=\"this.parentNode.classList.toggle('open');this.textContent=this.parentNode.classList.contains('open')?'פחות':'עוד %d שיעורים'\">עוד %d שיעורים</button>" % (len(vs) - 3, len(vs) - 3))
        if not vs and not os.path.isfile(os.path.join(HAND, "ERAN-%s.wav" % syl)):
            parts.append(u"<div class='note'>אין קליפים</div>")
        parts.append(u"</div>")
    parts.append(u"<p class='sub'>המקום: <a href='http://127.0.0.1:8858/'>מקום</a> · לשפוט בעיוור: <a href='http://127.0.0.1:8857/'>שפוט את קלוד</a></p></body></html>")
    return u"".join(parts)


class H(http.server.BaseHTTPRequestHandler):
    def _s(self, body, ctype="text/html; charset=utf-8", code=200):
        if isinstance(body, str):
            body = body.encode("utf-8")
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
        p = urllib.parse.urlparse(self.path).path
        if p in ("/", "/index.html"):
            return self._s(page())
        m = re.fullmatch(r"/hand/([a-z]+)\.wav", p)
        if m and m.group(1) in HEB:
            return self._wav(os.path.join(HAND, "ERAN-%s.wav" % m.group(1)))
        m = re.fullmatch(r"/iddo/([a-z]+)\.wav", p)
        if m and m.group(1) in HEB:
            return self._wav(os.path.join(IDDO, "IDDO-%s.wav" % m.group(1)))
        m = re.fullmatch(r"/cand/([a-z]+)/([A-Z])\.wav", p)
        if m and m.group(1) in HEB:
            return self._wav(os.path.join(CAND, "CLAUDE-%s-cand-%s.wav" % (m.group(1), m.group(2))))
        m = re.fullmatch(r"/v/([a-z]+)/(\d+)\.wav", p)
        if m and m.group(1) in HEB:
            return self._wav(os.path.join(LESSONS, "CLAUDE-%s-v%s.wav" % (m.group(1), m.group(2))))
        return self._s("404", "text/plain; charset=utf-8", 404)

    def _wav(self, fp):
        if not os.path.isfile(fp):
            return self._s("404", "text/plain; charset=utf-8", 404)
        with open(fp, "rb") as fh:
            return self._s(fh.read(), "audio/wav")

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("127.0.0.1", PORT), H) as srv:
        srv.serve_forever()
