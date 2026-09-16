#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
loop.py -- THE JUDGING LOOP. Iddo is the metric. Port 8890.

Born 2026-09-02 21:20, the night after wdist scored AUC 0.4973 against his 117
verdicts -- pure chance -- and he said he will judge every run himself, blind
("עזוב לקחת סרגל אני מוכן לשפוט בכל הרצה והרצה", 21:10). So the search is now
DRIVEN by his click and by nothing else.

Each ROUND is four clips as bare letters A/B/C/D, shuffled, no scores, no
filenames. One button per clip: "זה הכי טוב". The click appends four rows to
iddo-verdicts.jsonl (chosen true/false) and the winner becomes the parent of
the next round of that unit: loopgen.make_round renders three mutants around it
on eran2 (~2 s, live) and carries the winner over as the incumbent.

Blind by construction: the browser only ever sees /clip/r01/ERAN-A.wav. The
letter->file KEY lives in loop/KEY.json, outside anything served. His own
recording is shown as a reference row labelled "אתה" and is not part of the
vote.

Sacred audio: <audio controls preload="none">, nothing autoplays.

    python loop.py                 then open http://127.0.0.1:8890/
"""
import io
import json
import os
import random
import socket
import sys
import threading
import http.server
import socketserver
import urllib.parse
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import loopgen  # noqa: E402

LOOP = os.path.join(ROOT, "loop")
STATE = os.path.join(LOOP, "state.json")
KEY = os.path.join(LOOP, "KEY.json")
LOG = os.path.join(LOOP, "loop.log")
VERDICTS = os.path.join(ROOT, "iddo-verdicts.jsonl")
REF = os.path.join(LOOP, "pool", "ref")
PORT = 8890
LABELS = ["A", "B", "C", "D"]
UNIT_HE = {"ah": "אָה", "ma": "מָה", "na": "נָה", "la": "לָה", "ya": "יָה"}

_lock = threading.Lock()
_busy = {"gen": False, "error": None}


def log(msg):
    line = "%s %s\n" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
    with io.open(LOG, "a", encoding="utf-8") as f:
        f.write(line)


def load_state():
    with io.open(STATE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(st):
    tmp = STATE + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)
    os.replace(tmp, STATE)


def current_round(st):
    for r in st["rounds"]:
        if r.get("chosen") is None:
            return r
    return None


def assign_labels(rnd, rng=None):
    """Shuffle the clips onto bare letters and record the mapping in KEY.json."""
    rng = rng or random.Random()
    clips = list(rnd["clips"])[:4]
    rng.shuffle(clips)
    rnd["labels"] = {}
    for lab, c in zip(LABELS, clips):
        rnd["labels"][lab] = c
    key = {}
    if os.path.isfile(KEY):
        with io.open(KEY, "r", encoding="utf-8") as f:
            key = json.load(f)
    key["r%02d" % rnd["round"]] = {
        "unit": rnd["unit"], "sigma": rnd.get("sigma"), "made": rnd.get("made"),
        "map": {lab: {"file": c["name"], "kind": c.get("kind")} for lab, c in rnd["labels"].items()}}
    with io.open(KEY, "w", encoding="utf-8") as f:
        json.dump(key, f, ensure_ascii=False, indent=1)
    return rnd


# ------------------------------------------------------------------ page

PAGE = u"""<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ERAN — שיפוט</title>
<style>
 *{box-sizing:border-box;margin:0;padding:0}
 body{background:#f7f4ec;color:#22281f;font-family:"Assistant","Segoe UI",Arial,sans-serif;
      padding:18px 16px 60px;line-height:1.5;max-width:720px;margin:0 auto}
 h1{font-size:24px;margin-bottom:2px}
 .sub{color:#6b7563;font-size:14px;margin-bottom:14px}
 .unit{font-size:34px;font-weight:700;color:#2e6b45;margin:6px 0 10px}
 .card{background:#fff;border:1px solid #ddd7c6;border-radius:14px;padding:14px 16px;margin-bottom:12px}
 .card.ref{background:#fff7e0;border-color:#e8d9a8}
 .lab{font-size:30px;font-weight:700;margin-bottom:6px}
 .lab small{font-size:14px;color:#6b7563;font-weight:400;margin-right:8px}
 audio{width:100%;margin-bottom:10px}
 button{font-family:inherit;font-size:18px;padding:12px 0;border-radius:11px;width:100%;
        border:1px solid #c9c2ae;background:#fbfaf6;color:inherit;cursor:pointer}
 button:hover{background:#eee9dc}
 button.sel{background:#2e6b45;color:#fff;border-color:#2e6b45;font-weight:700}
 .none{margin-top:6px;background:#fbeeea;border-color:#e2b8ad;font-size:15px}
 .foot{font-size:12.5px;color:#6b7563;margin-top:14px}
</style></head><body>
<h1>ERAN — שיפוט</h1>
<div class="sub">סיבוב __ROUND__ · ארבעה קליפים עיוורים. תשמע את כולם, לחץ על הכי טוב. אין שמות, אין ציונים.</div>
<div class="unit">/__UNIT__/</div>
<div class="card ref"><div class="lab">אתה <small>ההקלטה שלך — לא חלק מההצבעה</small></div>
 <audio controls preload="none" src="/ref/__REFUNIT__"></audio></div>
__CARDS__
<button class="none" onclick="vote('NONE',this)">אף אחד לא טוב — תמשיך לחפש</button>
<div class="foot">__DONE__ סיבובים נשפטו עד עכשיו · הקליק שלך הוא המדד. ERAN מייצר את הסיבוב הבא סביב הבחירה שלך.</div>
<script>
const R=__ROUND__; let sent=false;
function vote(lab,btn){
  if(sent) return; sent=true;
  document.querySelectorAll('button').forEach(b=>b.disabled=true);
  btn.classList.add('sel'); btn.textContent='נשמר. מכין את הסיבוב הבא…';
  fetch('/vote',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({round:R,label:lab})}).then(r=>r.text()).then(t=>{
      if(t!=='ok'){btn.textContent='שגיאה: '+t; return;}
      setTimeout(()=>location.reload(),1200);
    }).catch(e=>{btn.textContent='שגיאה: '+e;});
}
</script></body></html>"""

CARD = u"""<div class="card"><div class="lab">__LAB__</div>
 <audio controls preload="none" src="/clip/r__RN__/ERAN-__LAB__.wav"></audio>
 <button onclick="vote('__LAB__',this)">זה הכי טוב</button></div>"""

WAIT = u"""<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta http-equiv="refresh" content="2"><title>ERAN — שיפוט</title>
<style>body{background:#f7f4ec;color:#22281f;font-family:"Assistant","Segoe UI",Arial,sans-serif;padding:40px 16px;text-align:center}
.wait{font-size:22px}.sub{color:#6b7563;font-size:14px;margin-top:10px}</style></head>
<body><div class="wait">ERAN מייצר את הסיבוב הבא סביב הבחירה שלך…</div>
<div class="sub">מרנדר על eran2. בדרך כלל 2–4 שניות.</div></body></html>"""

BROKEN = u"""<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8"><title>ERAN — שיפוט</title>
<style>body{background:#f7f4ec;color:#22281f;font-family:"Assistant","Segoe UI",Arial,sans-serif;padding:30px 16px;max-width:720px;margin:0 auto}
.broken{background:#fde8e6;border:1px solid #e0938a;border-radius:12px;padding:14px;white-space:pre-wrap;direction:ltr;text-align:left;font-family:monospace;font-size:12px}
button{font-family:inherit;font-size:16px;padding:10px 18px;border-radius:10px;border:1px solid #c9c2ae;background:#fbfaf6;cursor:pointer;margin-top:12px}</style></head>
<body><h1>שבור — הסיבוב הבא לא נוצר</h1><p>eran2 לא ענה או הרינדור נכשל. זה לא מוסתר ממך.</p>
<div class="broken">__ERR__</div>
<form method="post" action="/retry"><button>נסה שוב</button></form></body></html>"""

DONE = u"""<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8"><title>ERAN — שיפוט</title>
<style>body{background:#f7f4ec;color:#22281f;font-family:"Assistant","Segoe UI",Arial,sans-serif;padding:40px 16px;text-align:center}</style></head>
<body><h1>אין סיבוב פתוח.</h1><p>נשפטו __N__ סיבובים. תודה, עידו.</p></body></html>"""


def render_page(st):
    r = current_round(st)
    if r is None:
        if _busy["error"]:
            return BROKEN.replace("__ERR__", _busy["error"])
        if _busy["gen"]:
            return WAIT
        return DONE.replace("__N__", str(len(st["rounds"])))
    if "labels" not in r:
        assign_labels(r)
        save_state(st)
    cards = "\n".join(CARD.replace("__LAB__", lab).replace("__RN__", "%02d" % r["round"])
                      for lab in LABELS if lab in r["labels"])
    done = sum(1 for x in st["rounds"] if x.get("chosen") is not None)
    return (PAGE.replace("__ROUND__", str(r["round"]))
            .replace("__UNIT__", UNIT_HE.get(r["unit"], r["unit"]))
            .replace("__REFUNIT__", "IDDO-%s.wav" % r["unit"])
            .replace("__CARDS__", cards).replace("__DONE__", str(done)))


# ------------------------------------------------------------------ the loop

def record_vote(st, r, label):
    # LOOP_SITTING is only for the acceptance test, so its rows can be removed exactly
    sitting = os.environ.get("LOOP_SITTING") or "loop-" + datetime.now().strftime("%Y%m%d")
    ts = datetime.now().astimezone().isoformat(timespec="seconds")
    rows = []
    for lab in LABELS:
        c = r["labels"].get(lab)
        if not c:
            continue
        rows.append({"ts": ts, "judge": "iddo", "sitting": sitting, "round": r["round"],
                     "blind_label": lab, "clip": c["name"], "unit": r["unit"],
                     "chosen": (lab == label), "source": "loop",
                     "kind": c.get("kind"), "sigma": r.get("sigma"),
                     "none_good": (label == "NONE")})
    with io.open(VERDICTS, "a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    r["chosen"] = label
    r["chosen_ts"] = ts
    r["sitting"] = sitting
    return rows


def spawn_next(st, r, label):
    """Winner -> parent of the next round of this unit (in a thread; ~2-4 s)."""
    unit = r["unit"]
    if label == "NONE":
        inc = [c for c in r["clips"] if c.get("kind") == "incumbent"]
        parent_clip = inc[0] if inc else r["labels"]["A"]
        gen = max(0, st["gen"].get(unit, 0) - 1)          # widen again
        note = "none-good: re-mutating the previous parent with a wider sigma"
    else:
        parent_clip = r["labels"][label]
        gen = st["gen"].get(unit, 0)
        note = "parent = %s" % parent_clip["name"]
    if not parent_clip.get("genome"):
        _busy["error"] = "winner %s has no genome to mutate from" % parent_clip["name"]
        log("BROKEN " + _busy["error"])
        return
    st["gen"][unit] = gen + 1
    st["next_round"] = st.get("next_round", len(st["rounds"]) + 1)
    rn = st["next_round"]
    st["next_round"] = rn + 1
    save_state(st)

    def work():
        _busy["gen"] = True
        _busy["error"] = None
        try:
            log("round %d (%s) voted %s; generating round %d gen %d (%s)" % (r["round"], unit, label, rn, gen, note))
            new = loopgen.make_round(unit, rn, parent_clip["genome"], gen,
                                     incumbent={"path": parent_clip["path"], "genome": parent_clip["genome"]},
                                     seed=rn * 7919 + 17)
            new["parent"] = parent_clip["name"]
            with _lock:
                st2 = load_state()
                st2["rounds"].append(new)
                assign_labels(new)
                save_state(st2)
            log("round %d ready: %s in %s" % (rn, [c["name"] for c in new["clips"]], new["timing"]))
        except Exception as e:
            _busy["error"] = "%s: %s" % (type(e).__name__, e)
            log("BROKEN generating round %d: %s" % (rn, _busy["error"]))
        finally:
            _busy["gen"] = False

    threading.Thread(target=work, daemon=True).start()


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

    def _wav(self, fp):
        if fp and os.path.isfile(fp):
            with open(fp, "rb") as fh:
                return self._s(fh.read(), "audio/wav")
        return self._s("404", "text/plain; charset=utf-8", 404)

    def do_GET(self):
        p = urllib.parse.urlparse(self.path).path
        if p in ("/", "/index.html"):
            with _lock:
                return self._s(render_page(load_state()))
        if p.startswith("/clip/"):
            # /clip/r01/ERAN-A.wav  -> KEY lookup, the real name never leaves the box
            parts = p.split("/")
            if len(parts) == 4 and parts[2].startswith("r") and parts[3].startswith("ERAN-"):
                try:
                    rn = int(parts[2][1:])
                    lab = parts[3][len("ERAN-"):-4]
                except ValueError:
                    return self._s("404", "text/plain; charset=utf-8", 404)
                with _lock:
                    st = load_state()
                for r in st["rounds"]:
                    if r["round"] == rn and "labels" in r and lab in r["labels"]:
                        return self._wav(r["labels"][lab]["path"])
            return self._s("404", "text/plain; charset=utf-8", 404)
        if p.startswith("/ref/"):
            name = os.path.basename(p)
            if name.startswith("IDDO-") and name.endswith(".wav"):
                return self._wav(os.path.join(REF, name))
        if p == "/status":
            with _lock:
                st = load_state()
            done = sum(1 for x in st["rounds"] if x.get("chosen") is not None)
            cur = current_round(st)
            return self._s(json.dumps({"rounds": len(st["rounds"]), "judged": done,
                                       "open_round": cur["round"] if cur else None,
                                       "open_unit": cur["unit"] if cur else None,
                                       "generating": _busy["gen"], "error": _busy["error"]}),
                           "application/json; charset=utf-8")
        return self._s("404", "text/plain; charset=utf-8", 404)

    def do_POST(self):
        p = urllib.parse.urlparse(self.path).path
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        if p == "/vote":
            try:
                d = json.loads(raw.decode("utf-8"))
                rn, label = int(d["round"]), str(d["label"]).upper()
            except Exception as e:
                return self._s("bad request: %s" % e, "text/plain; charset=utf-8", 400)
            with _lock:
                st = load_state()
                r = current_round(st)
                if r is None or r["round"] != rn:
                    return self._s("round %s is not the open round" % rn, "text/plain; charset=utf-8", 409)
                if label != "NONE" and label not in r.get("labels", {}):
                    return self._s("no such label", "text/plain; charset=utf-8", 400)
                record_vote(st, r, label)
                save_state(st)
                spawn_next(st, r, label)
            return self._s("ok", "text/plain; charset=utf-8")
        if p == "/retry":
            with _lock:
                st = load_state()
                last = [x for x in st["rounds"] if x.get("chosen") is not None]
                if last and current_round(st) is None and not _busy["gen"]:
                    r = last[-1]
                    spawn_next(st, r, r["chosen"])
            self.send_response(303)
            self.send_header("Location", "/")
            self.end_headers()
            return
        return self._s("404", "text/plain; charset=utf-8", 404)

    def log_message(self, *a):
        pass


def port_free(port):
    s = socket.socket()
    try:
        return s.connect_ex(("127.0.0.1", port)) != 0
    finally:
        s.close()


if __name__ == "__main__":
    if not os.path.isfile(STATE):
        print("no loop/state.json -- run loop_seed.py first", file=sys.stderr)
        sys.exit(2)
    if not port_free(PORT):
        log("port %d already taken -- not binding" % PORT)
        sys.exit(3)
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", PORT), H)
    log("loop: serving http://127.0.0.1:%d/  pid %d" % (PORT, os.getpid()))
    try:
        if sys.stdout and sys.stdout.isatty():
            print("loop -> http://127.0.0.1:%d/" % PORT, flush=True)
    except Exception:
        pass
    srv.serve_forever()
