#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""ERAN — הלולאה הסגורה, מבחן עיוור לאוזן של עידו.  port 8879.
לזכרה של עלמה ז״ל.

WHAT WAS BUILT, IN ONE LINE
---------------------------
ERAN's arrow ran one way — ears -> pooled vector -> nearest prototype -> done.
The prototype never flowed back down. It does now: the brain sends a PREDICTION
of the next cochlear slice down, the ears report only what the prediction
missed, and that error — not "distance to the nearest thing I know" — is what
sets surprise, decides a new prototype, and scales the learning rate. It is
gated through the existing chemistry (ACh up = trust the expectation, NE spike
= abandon it), and the whole thing collapses ALGEBRAICALLY to the old organism
at gain 0, which is checked in code, not asserted.

The living organism on eran1 was never touched. This ran in a parallel copy.

WHY THIS PAGE EXISTS, AND WHY IT HAS NO PERCENTAGE ON IT
--------------------------------------------------------
The examiner is broken. proof/measure.py's 132-item heldout is MISLABELLED —
Iddo listened on 2026-09-03 and 0 of 10 clips matched their labels, which makes
"13 mastered" noise. So no accuracy number is reported anywhere in this work,
and none appears here. Anything I could have computed off that exam would be
laundering.

What survives with no labels at all: **a prototype is a claim that a set of
sounds are the same thing, and an ear can check that claim directly.**

  * one ANCHOR clip
  * the OPEN-loop brain filed it with some neighbours -> 3 of them
  * the CLOSED-loop brain filed it with some neighbours -> 3 of them
  * two sets of four, unlabelled, sides randomised at server start
  * one question per round: which set sounds more like the same sound repeated?

The anchor is in BOTH sets, so they are anchored to the same sound and the only
difference is the company each brain kept it in.

HONEST CAVEATS — all of them are printed on the page itself
-----------------------------------------------------------
  * Rounds are picked where the two brains DISAGREE. Where they file a sound
    identically there is nothing to hear, and a test made of ties measures
    nothing. The overall agreement rate is shown so the selection is visible.
  * These brains were grown from scratch on 200,000 beats. The organism on
    eran1 has lived 290 million. This is a comparison of two INFANCIES.
  * The audio is the same corpus whose labels Iddo's own ear rejected. The
    labels are not used here — but if the recordings themselves are not what
    anyone thinks they are, that is upstream of everything on this page.
  * "No difference" is a real answer and I want it if it is true. It would mean
    the closed loop changed the numbers without changing anything audible.

THE KEY LIVES IN THIS SOURCE and the server refuses to serve this file.

Run:  python eran_loop_ab.py
"""
from __future__ import annotations

import html
import io
import json
import os
import random
import socketserver
import sys
import time
import http.server
import urllib.parse

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 8882                     # claimed in RAMCHAT 2026-09-06.
# SCAR, 2026-09-06 02:58, and it is a trap anyone on this machine can fall in:
# 8879 was claimed here first and it was ALREADY IN USE by another agent's
# "DECISION MODELER" page (pid 27060). On Windows, SO_REUSEADDR does not merely
# allow rebinding a port in TIME_WAIT the way it does on Linux — it lets a
# second process bind a port another process is actively LISTENING on, with no
# error. Both sockets sat in netstat, requests went to whichever won, and this
# server printed a cheerful "listening" line while serving nothing. So:
# check the port BEFORE binding, and do not set allow_reuse_address.
CLIPS = os.path.join(HERE, "clips")
MANIFEST = os.path.join(HERE, "ab-manifest.json")
RESULT = os.path.join(HERE, "eran-loop-ab-result.json")

WHAT = {
    "open":   "the OPEN loop — today's organism. Surprise = distance to the "
              "nearest prototype it already has.",
    "closed": "the CLOSED loop — the prototype's prediction goes back down, "
              "and surprise = what the prediction missed.",
}

state = {"sides": None, "verdicts": {}, "man": None}


def manifest():
    if state["man"] is None:
        with io.open(MANIFEST, encoding="utf-8") as fh:
            state["man"] = json.load(fh)
    return state["man"]


def sides():
    """Which arm is on the left, per round. Fixed once per server start so a
    reload cannot shuffle the sides under him mid-listen, and drawn per round
    so a single guess cannot unlock the whole page."""
    if state["sides"] is None:
        rng = random.Random()
        state["sides"] = [rng.choice([("open", "closed"), ("closed", "open")])
                          for _ in manifest()["rounds"]]
    return state["sides"]


def clip_ok(name):
    p = os.path.join(CLIPS, name)
    return os.path.isfile(p) and os.path.getsize(p) > 1000


PAGE = """<!doctype html><html lang="he" dir="rtl"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ערן — הלולאה הסגורה</title><style>
*{box-sizing:border-box}
body{margin:0;background:#fbfaf7;color:#1b1b1b;
 font:17px/1.65 "Segoe UI",system-ui,sans-serif;padding:26px 18px}
.wrap{max-width:820px;margin:0 auto}
h1{font-size:28px;margin:0 0 6px}
.sub{color:#5d5d5d;font-size:15px;margin:0 0 20px}
.round{background:#fff;border:1px solid #e6e2da;border-radius:16px;
 padding:20px;margin:20px 0}
.round h2{margin:0 0 4px;font-size:20px}
.pair{display:flex;gap:16px;flex-wrap:wrap;margin-top:12px}
.set{flex:1 1 300px;background:#f7f5f1;border:1px solid #e6e2da;
 border-radius:12px;padding:14px}
.set h3{margin:0 0 8px;font-size:18px}
audio{width:100%;margin:4px 0;height:34px}
.q{background:#f2f6fb;border:1px solid #cfe0f2;border-radius:12px;
 padding:14px 16px;margin-top:14px}
button{font:700 17px system-ui;padding:12px 26px;border-radius:11px;border:0;
 cursor:pointer;color:#fff;background:#2f6fb3;margin:4px 3px}
button.same{background:#7a7a7a}
.note{background:#fdf7e6;border:1px solid #ecdca8;border-radius:12px;
 padding:14px 16px;margin:18px 0;font-size:14.5px}
.done{background:#e6f7ea;border:1px solid #a9dbb8;border-radius:12px;
 padding:12px 16px;margin-top:12px}
.big{background:#fff;border:1px solid #e6e2da;border-radius:16px;padding:20px;
 margin:22px 0}
table{border-collapse:collapse;width:100%;font-size:14.5px}
td,th{border-bottom:1px solid #ece8e0;padding:6px 8px;text-align:right}
code{background:#f0eee9;padding:1px 5px;border-radius:5px;font-size:13.5px}
</style></head><body><div class="wrap">
__BODY__
</div></body></html>"""


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body, ctype="text/html; charset=utf-8", code=200):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    # /clip/<round>/<L|R>/<i>.wav  — the arm never appears in the URL
    def _clip(self, p):
        try:
            _, _, r, side, tail = p.split("/", 4)
            r = int(r)
            i = int(tail.split(".")[0])
        except (ValueError, IndexError):
            return self._send("no", "text/plain; charset=utf-8", 404)
        man = manifest()
        if not (0 <= r < len(man["rounds"])):
            return self._send("no", "text/plain; charset=utf-8", 404)
        arm = sides()[r][0 if side == "L" else 1]
        names = man["rounds"][r][arm]
        if not (0 <= i < len(names)) or not clip_ok(names[i]):
            return self._send("missing", "text/plain; charset=utf-8", 404)
        with io.open(os.path.join(CLIPS, names[i]), "rb") as fh:
            return self._send(fh.read(), "audio/wav")

    def do_GET(self):
        p = self.path.split("?")[0]
        if p.startswith("/clip/"):
            return self._clip(p)
        # The source carries the key, so it is never served. 403, not 404 — a
        # 404 would read as "file missing" and send someone hunting.
        if p.endswith(".py") or p.endswith(".json"):
            return self._send("refused: this file contains the key",
                              "text/plain; charset=utf-8", 403)
        if p != "/":
            return self._send("no", "text/plain; charset=utf-8", 404)
        return self._send(PAGE.replace("__BODY__", self._body()))

    # ------------------------------------------------------------------ page
    def _body(self):
        man = manifest()
        ag = man["agreement"]
        out = ["""<h1>ערן — הלולאה נסגרה</h1>
<p class="sub">שני מוחות, אותו אוכל בדיוק, אותו זרע. אחד עם החץ שחוזר למטה
ואחד בלי. בלי תוויות, הצדדים אקראיים.
<span dir="ltr">Two brains, identical diet. No labels. Sides randomised.</span></p>

<div class="note"><b>אין כאן שום אחוז, בכוונה.</b> הבוחן של 132 הפריטים
<b>מתויג לא נכון</b> — האוזן שלך פסקה ב-03/09 ש-0 מתוך 10 קטעים לא תאמו
את התווית שלהם. כל מספר דיוק שהייתי מוציא ממנו היה כביסה, לא ראיה. אז המספרים
פה הם רק ספירות ומרחקים, והפסיקה היא שלך.</div>

<div class="note"><b>מה השאלה:</b> אב-טיפוס הוא טענה — "כל אלה הם אותו
דבר". אפשר לבדוק אותה עם אוזן ובלי אף תווית. בכל סבב יש <b>קטע עוגן</b>, ואחריו
שלושה שכנים שכל מוח תייק יחד איתו. העוגן נמצא בשתי הקבוצות, אז ההבדל היחיד הוא
<b>החברה שכל מוח שם אותו בה</b>.<br>
<span dir="ltr">Which set sounds more like the same sound repeated?</span></div>"""]

        for r, rd in enumerate(man["rounds"]):
            v = state["verdicts"].get(str(r))
            sets = []
            for side, label in (("L", "א"), ("R", "ב")):
                clips = "".join(
                    '<audio controls preload="none" src="/clip/%d/%s/%d.wav">'
                    "</audio>" % (r, side, i)
                    for i in range(len(man["rounds"][r]["open"])))
                sets.append('<div class="set"><h3>%s</h3>%s</div>'
                            % (label, clips))
            if v:
                a_arm, b_arm = sides()[r]
                rev = ('<div class="done">בחרת: <b>%s</b> &nbsp;·&nbsp; '
                       'א = %s &nbsp;·&nbsp; ב = %s</div>'
                       % (html.escape(v["choice"]),
                          html.escape(WHAT[a_arm].split(" — ")[0]),
                          html.escape(WHAT[b_arm].split(" — ")[0])))
            else:
                rev = ('<div class="q"><b>איזו קבוצה נשמעת יותר כמו אותו צליל '
                       'שחוזר?</b><form method="POST" action="/v" '
                       'style="margin-top:8px">'
                       '<input type="hidden" name="round" value="%d">'
                       '<button name="choice" value="א">א</button>'
                       '<button name="choice" value="ב">ב</button>'
                       '<button class="same" name="choice" value="אין הבדל">'
                       'אין הבדל</button></form></div>' % r)
            out.append('<div class="round"><h2>סבב %d</h2>'
                       '<p class="sub">הקטע הראשון בכל קבוצה הוא אותו קטע '
                       'עוגן.</p><div class="pair">%s</div>%s</div>'
                       % (r + 1, "".join(sets), rev))

        out.append("""<div class="big"><h2>מה כן נמדד, בלי תוויות</h2>
<table>
<tr><th>שאלה</th><th>תשובה</th></tr>
<tr><td>כמה פעמים שני המוחות תייקו צליל עם אותם שכנים בדיוק</td><td>%.1f%%</td></tr>
<tr><td>חפיפת שכנויות ממוצעת (Jaccard)</td><td>%.3f</td></tr>
<tr><td>אבות-טיפוס בסוף — פתוח / סגור</td><td>%d / %d</td></tr>
</table>
<p class="sub" style="margin-top:10px">הסבבים למעלה נבחרו דווקא איפה ששני
המוחות <b>לא</b> הסכימו. איפה שהם מתייקים אותו דבר אין מה לשמוע, ומבחן שכולו
תיקו לא מודד כלום. אומר את זה כאן ולא מחביא.</p></div>

<div class="note"><b>עוד שלושה דברים שאני חייב לומר מראש:</b><br>
• שני המוחות האלה נולדו מאפס וחיו 200,000 פעימות. ערן על eran1 חי
<b>290 מיליון</b>. זו השוואה בין שתי <b>ינקויות</b>, לא בינו לבין עצמו.<br>
• האודיו הוא אותו קורפוס שהאוזן שלך פסלה את התוויות שלו. התוויות לא
בשימוש פה בכלל — אבל אם ההקלטות עצמן אינן מה שחשבנו, זה למעלה מכל
מה שבדף הזה.<br>
• <b>"אין הבדל" היא תשובה אמיתית ואני רוצה אותה אם היא הנכונה.</b>
היא תגיד שהלולאה הסגורה שינתה מספרים ולא שינתה כלום שנשמע.</div>""" % (
            100.0 * ag["frac_identical_neighbourhood"],
            ag["mean_jaccard"],
            man["arms"]["open"]["n_protos"],
            man["arms"]["closed"]["n_protos"]))
        return "".join(out)

    def do_POST(self):
        if self.path.split("?")[0] != "/v":
            return self._send("no", "text/plain; charset=utf-8", 404)
        n = int(self.headers.get("Content-Length", 0) or 0)
        q = urllib.parse.parse_qs(self.rfile.read(n).decode("utf-8", "replace"))
        r = (q.get("round") or ["0"])[0]
        choice = (q.get("choice") or ["?"])[0]
        try:
            ri = int(r)
        except ValueError:
            return self._send("no", "text/plain; charset=utf-8", 400)
        a_arm, b_arm = sides()[ri]
        picked = {"א": a_arm, "ב": b_arm}.get(choice, "tie")
        state["verdicts"][str(ri)] = {
            "when": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "round": ri, "choice": choice, "picked_arm": picked,
            "left_was": a_arm, "right_was": b_arm,
            "anchor": manifest()["rounds"][ri]["anchor"],
        }
        tally = {}
        for v in state["verdicts"].values():
            tally[v["picked_arm"]] = tally.get(v["picked_arm"], 0) + 1
        with io.open(RESULT, "w", encoding="utf-8") as fh:
            json.dump({"verdicts": state["verdicts"], "tally": tally},
                      fh, ensure_ascii=False, indent=1)
        print("round %d: %s -> %s   tally %s"
              % (ri, choice, picked, tally), flush=True)
        self.send_response(303)
        self.send_header("Location", "/")
        self.end_headers()


if __name__ == "__main__":
    if not os.path.isfile(MANIFEST):
        sys.exit(f"missing {MANIFEST} — run pc/make_ab_manifest.py on eran1 "
                 f"and copy the result here")
    man = manifest()
    missing = [n for rd in man["rounds"] for a in ("open", "closed")
               for n in rd[a] if not clip_ok(n)]
    print("rounds: %d   clips missing: %d" % (len(man["rounds"]), len(missing)))
    if missing:
        sys.exit("REFUSING to serve a half-empty test: " + ", ".join(missing[:5]))
    import socket
    probe = socket.socket()
    probe.settimeout(0.6)
    taken = probe.connect_ex(("127.0.0.1", PORT)) == 0
    probe.close()
    if taken:
        sys.exit(f"REFUSED: 127.0.0.1:{PORT} already answers. Someone else is "
                 f"there. Pick another port and claim it in RAMCHAT — do not "
                 f"bind on top of them, which Windows will happily let you do.")
    socketserver.TCPServer.allow_reuse_address = False
    with socketserver.TCPServer(("127.0.0.1", PORT), H) as s:
        print("ERAN closed-loop A/B on http://127.0.0.1:%d/" % PORT, flush=True)
        s.serve_forever()
