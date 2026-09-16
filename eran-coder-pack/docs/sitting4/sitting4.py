#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SITTING 4 -- Iddo's blind ear on the FLEURS-cut food.  Port 8866.

WHY. On 2026-09-03 Iddo listened blind to 10 clips from ERAN's held-out vault and
**0 of 10** matched their label. Those clips were facebook/mms-tts-heb output, and
that verdict is what condemned the whole corpus.

The new food is 7,388 CV syllables cut by cut_syllables.py out of FLEURS he_il --
9.47 h of REAL recorded human Hebrew, 1,502 distinct speakers, CC-BY-4.0. A machine
probe says the cuts carry syllable identity across 687 unseen mouths (leave-speaker-out
top1 34.6 %, chance 5.6 %, shuffled 5.8 %). That is a machine's opinion.

Iddo's ear is the metric ([[feedback_involve_iddo_in_learning]]). This page asks him
the same question that killed the last corpus, and it is BLIND: the answer key is not
in the served HTML, it is not in any URL, and it is only read after he submits.

Pure stdlib, no framework, no CDN -- ALMA standard. Nothing autoplays: every clip
plays only when he presses it. It never opens an audio input.

Score is written to sitting4-result.json next to this file.
"""
import json, os, http.server, socketserver, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 8866
MANIFEST = json.load(open(os.path.join(HERE, "manifest.json"), encoding="utf-8"))

# canonical class -> what to show him as a choice, in Hebrew + the syllable
CHOICES = [
    ("B", "בּ — ba"), ("V", "ב/ו — va"), ("G", "ג — ga"), ("D", "ד — da"),
    ("H", "ה — ha"), ("Z", "ז — za"), ("X", "ח/כ — kha"), ("T", "ט/ת — ta"),
    ("Y", "י — ya"), ("K", "כּ/ק — ka"), ("L", "ל — la"), ("M", "מ — ma"),
    ("N", "נ — na"), ("S", "ס/שׂ — sa"), ("P", "פּ — pa"), ("TS", "צ — tsa"),
    ("R", "ר — ra"), ("SH", "ש — sha"),
]

PAGE = """<!doctype html><html lang="he" dir="rtl"><meta charset="utf-8">
<title>ישיבה 4 — האוזן שלך</title>
<style>
 body{background:#fbfbfd;color:#111;font:16px/1.6 system-ui,Segoe UI,Arial;margin:0;padding:24px}
 .wrap{max-width:880px;margin:0 auto}
 h1{font-size:26px;margin:0 0 4px} .sub{color:#555;margin:0 0 20px}
 .card{background:#fff;border:1px solid #e3e3ea;border-radius:14px;padding:14px 16px;margin:10px 0;
       display:flex;align-items:center;gap:14px;flex-wrap:wrap}
 .n{font-weight:700;color:#888;min-width:28px}
 audio{height:38px}
 select{font:15px system-ui;padding:7px 10px;border-radius:9px;border:1px solid #ccd;background:#fff;min-width:170px}
 button{font:600 17px system-ui;padding:12px 26px;border-radius:11px;border:0;background:#1963d2;color:#fff;cursor:pointer}
 button:hover{background:#0f4ea8}
 .note{background:#fff8e1;border:1px solid #ffe08a;border-radius:12px;padding:12px 16px;margin:18px 0}
 .res{background:#fff;border:2px solid #1963d2;border-radius:14px;padding:18px;margin:16px 0}
 .ok{color:#0a7d32;font-weight:700} .no{color:#b3261e;font-weight:700}
 table{border-collapse:collapse;width:100%;margin-top:10px} td,th{border-bottom:1px solid #eee;padding:7px;text-align:right}
</style>
<div class="wrap">
<h1>ישיבה 4 — האוזן שלך על האוכל החדש</h1>
<p class="sub">Sitting 4 — your blind ear on the new food. 12 clips cut from real recorded human Hebrew (FLEURS, 1,502 speakers).</p>
<div class="note">
<b>עיוור.</b> התשובות לא נמצאות בדף הזה ולא בשום כתובת — הן נקראות רק אחרי שתשלח.<br>
<b>Blind.</b> The answer key is not in this page or any URL; it is read only after you submit.<br><br>
תלחץ נגן על כל אחד, ותגיד <b>מה אתה שומע</b>. אם אתה לא בטוח — תנחש, זה בסדר.<br>
Press play on each and say <b>what you hear</b>. Guess if unsure — that's fine.<br><br>
<b>הרף:</b> הקורפוס הקודם (TTS) קיבל <b>0 מתוך 10</b>. אקראי כאן = בערך 1 מתוך 18.<br>
<b>The bar:</b> the previous (TTS) corpus scored <b>0/10</b>. Chance here is about 1 in 18.
</div>
<form method="POST" action="/submit">
__ROWS__
<p><button type="submit">שלח / Submit</button></p>
</form>
</div></html>"""


class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=HERE, **k)

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            rows = []
            for m in MANIFEST:
                opts = "".join(f'<option value="{c}">{lbl}</option>' for c, lbl in CHOICES)
                rows.append(
                    f'<div class="card"><span class="n">{m["i"]+1}</span>'
                    f'<audio controls preload="none" src="/clip{m["i"]:02d}.wav"></audio>'
                    f'<select name="a{m["i"]}"><option value="">— מה שמעת? —</option>'
                    f'{opts}</select></div>')
            body = PAGE.replace("__ROWS__", "\n".join(rows)).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.startswith("/clip") and self.path.endswith(".wav"):
            return super().do_GET()
        self.send_error(404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        form = urllib.parse.parse_qs(self.rfile.read(n).decode("utf-8"))
        rows, correct, answered = [], 0, 0
        for m in MANIFEST:
            got = (form.get(f"a{m['i']}", [""])[0] or "").strip()
            truth = m["truth"]
            if got:
                answered += 1
            ok = got == truth
            correct += ok
            rows.append({"i": m["i"], "truth": truth, "heard": got or "-",
                         "ok": bool(ok), "src": m["src"]})
        out = {"when": __import__("time").strftime("%Y-%m-%dT%H:%M:%S"),
               "answered": answered, "correct": correct, "total": len(MANIFEST),
               "rows": rows}
        with open(os.path.join(HERE, "sitting4-result.json"), "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)

        lbl = dict(CHOICES)
        trs = "".join(
            f'<tr><td>{r["i"]+1}</td><td>{lbl.get(r["truth"],r["truth"])}</td>'
            f'<td>{lbl.get(r["heard"],r["heard"])}</td>'
            f'<td class="{"ok" if r["ok"] else "no"}">{"✓" if r["ok"] else "✗"}</td></tr>'
            for r in out["rows"])
        html = (f'<!doctype html><html lang="he" dir="rtl"><meta charset="utf-8">'
                f'<title>ישיבה 4 — תוצאה</title>{PAGE.split("<style>")[1].split("</style>")[0].join(["<style>","</style>"])}'
                f'<div class="wrap"><h1>ישיבה 4 — תוצאה</h1>'
                f'<div class="res"><h2>{correct} / {len(MANIFEST)}</h2>'
                f'<p>הקורפוס הקודם (TTS) קיבל 0/10. אקראי = ~1/18 (כלומר ~0.7 מתוך 12).<br>'
                f'The previous TTS corpus scored 0/10. Chance is ~1/18 (~0.7 of 12).</p>'
                f'<table><tr><th>#</th><th>התווית / label</th><th>מה שמעת / you heard</th><th></th></tr>'
                f'{trs}</table></div>'
                f'<p>נשמר ב-sitting4-result.json</p></div></html>').encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html)


if __name__ == "__main__":
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", PORT), H) as s:
        print(f"SITTING 4 on http://127.0.0.1:{PORT}/", flush=True)
        s.serve_forever()
