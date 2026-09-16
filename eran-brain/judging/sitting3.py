#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
sitting3.py -- BLIND SITTING 3: na and the corpus. Port 8862. Sitting sitting3-20260903.

Built 2026-09-03 to settle what HEBREW-JUDGE-20260903.md left open: the Hebrew
wav2vec2 judge (facebook/wav2vec2-xlsr-53-espeak-cv-ft, run as a closed 24-class
classifier on eran2) disagrees with Iddo's 17:58 ruling on the six na candidates
(he said "still ma"; the judge hears [n a] at 0.57-0.96), agrees with him on the
ORIGINAL na lessons (ma in 10/14), and scores only 26.5% on the 132-clip human
corpus while reading Iddo's own 5 clips almost perfectly. Only his ear can settle
whether the corpus is bad or isolated syllables are just unreadable to ASR.

20 clips, shuffled with a fixed seed, four groups (never shown to Iddo):
  na_candidates -- the 6 na candidates from 17:58/18:1x (A-F; F is byte-identical
                   to D -- a repeatability check, not a 7th design)
  na_v3_best    -- the best school-v3 na (judge canon_conf 0.9708)
  na_original   -- 2 of the 14 original school-v2 na lessons the judge heard as ma
  corpus        -- 10 human heldout-vault clips: 8 chosen because the judge got
                   them WRONG in the same systematic pattern the report flags
                   (ma->la, tza->sa, ta->ka, sa->kha, 2 each) + 2 the judge got
                   RIGHT as controls
  anchor        -- 1 of Iddo's own clips (IDDO-ma.wav) as a sanity anchor

Same mechanics as claude_sitting.py: opaque blind ids, preload=none, no autoplay,
no filenames/syllable-romanizations/source-folder-names ever reach the page. The
truth, judge output and any prior Iddo ruling are written server-side into the
KEY only -- sitting3-20260903-KEY.json, next to this file, never served over
HTTP. Verdicts append to iddo-verdicts.jsonl (append-only, last word per clip
wins on the page, but every row is kept).

    /clip/<k>.wav   k = 1..20 blind index. Anything else is 404.
    /n              {"n": <answered>}
    /report         localhost-only scoreboard: Iddo vs truth, Iddo vs judge,
                     broken out by the four groups above. Needs >=1 answer.

    python sitting3.py   then open http://127.0.0.1:8862/
Never opens a browser, never touches audio devices, never writes outside this
folder's KEY/verdicts/log files.
"""
import html
import io
import json
import os
import random
import http.server
import socketserver
import threading
import urllib.parse
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(ROOT)  # D:\CLAUDE\eran-brain
SITTING = "sitting3-20260903"
KEY_PATH = os.path.join(ROOT, SITTING + "-KEY.json")
VERDICTS = os.path.join(ROOT, "iddo-verdicts.jsonl")
LOG = os.path.join(ROOT, "sitting3.log")
PORT = 8862
SEED = 20260903
SOURCE = "sitting3"

SV2 = os.path.join(BRAIN, "throat-one-sample", "school-v2")
SV3 = os.path.join(BRAIN, "throat-one-sample", "school-v3")
VAULT = os.path.join(BRAIN, "proof", "heldout-vault")
LISTEN = os.path.join(BRAIN, "throat-one-sample", "LISTEN")

# ---- same 21-class identification grid as claude_sitting.py (Iddo's ear: -----
# kaf-dagesh=kuf, khaf=chet, vet=vav are one sound each), plus the noise button.
SYLS = ["a", "aya", "ba", "cha", "da", "fa", "ga", "ha", "ka", "kha", "la", "ma",
        "na", "pa", "qa", "ra", "sa", "sha", "ta", "tza", "va", "wa", "ya", "za"]
CLASS_OF = {s: s for s in SYLS}
CLASS_OF.update({"qa": "ka", "cha": "kha", "wa": "va"})
CLASSES = ["a", "aya", "ba", "va", "ga", "da", "ha", "za", "kha", "ta", "ya", "ka",
           "la", "ma", "na", "sa", "pa", "fa", "tza", "ra", "sha"]
HEB = {
    "a": "אַ", "aya": "אַיָה", "ba": "בַּ", "va": "בַ / וַ", "ga": "גַ", "da": "דַ",
    "ha": "הַ", "za": "זַ", "kha": "חַ / כַ", "ta": "תַ / טַ", "ya": "יַ", "ka": "כַּ / קַ",
    "la": "לַ", "ma": "מַ", "na": "נַ", "sa": "סַ", "pa": "פַּ", "fa": "פַ",
    "tza": "צַ", "ra": "רַ", "sha": "שַׁ", "noise": "לא הברה / רעש",
}
CHOICES = CLASSES + ["noise"]
LOCK = threading.Lock()
GIF = bytes.fromhex('47494638396101000100800000000000ffffff21f90401000000002c00000000010001000002024401003b')


def _p(*parts):
    return os.path.join(*parts)


# ---- the 20 items. group/truth/judge/prior are written into the KEY; the page
# never sees any of it -- only the shuffled opaque id k reaches the HTML. -------
def build_items():
    items = []

    na_cand_dir = _p(SV2, "candidates")
    na_cand_rej = _p(na_cand_dir, "rejected-round1")
    NA_AGG = "aggregate from HEBREW-JUDGE-20260903.md: judge heard [n a] on all 6, " \
             "confidence 0.57-0.96 -- exact per-letter score not saved to disk"
    na_cands = [
        ("A", _p(na_cand_rej, "CLAUDE-na-cand-A.wav"), "round 1 (15:35); Iddo 17:58 said all three round-1 clips still sound like ma (UNCONFIRMED which clips he played)"),
        ("B", _p(na_cand_rej, "CLAUDE-na-cand-B.wav"), "round 1 (15:35); Iddo 17:58 said all three round-1 clips still sound like ma (UNCONFIRMED which clips he played)"),
        ("C", _p(na_cand_rej, "CLAUDE-na-cand-C.wav"), "round 1 (15:35); Iddo 17:58 said all three round-1 clips still sound like ma (UNCONFIRMED which clips he played)"),
        ("D", _p(na_cand_dir, "CLAUDE-na-cand-D.wav"), "round 2 (18:02), tongue body fronted during tip closure, knots AI70"),
        ("E", _p(na_cand_dir, "CLAUDE-na-cand-E.wav"), "round 2 (18:02), tongue body fronted during tip closure, knots AI50"),
        ("F", _p(na_cand_rej, "CLAUDE-na-cand-F.wav"), "round 1 (15:35) as designed, but the WAV is byte-identical to candidate D (a burst-onset variant that measured identical for a nasal and was dropped) -- included as a same-clip repeatability check, not a 7th design"),
    ]
    for letter, wav, note in na_cands:
        items.append({"group": "na_candidates", "truth": "na", "wav": wav,
                       "source": "school-v2/candidates" + ("/rejected-round1" if letter in "ABCF" else ""),
                       "label_hint": "na-cand-%s" % letter,
                       "judge_top1": "na", "judge_conf": None, "judge_note": NA_AGG,
                       "iddo_prior": note})

    items.append({"group": "na_v3_best", "truth": "na",
                  "wav": _p(SV3, "lessons", "CLAUDE-na-judge-v00.wav"),
                  "source": "school-v3/lessons", "label_hint": "na-v3-best",
                  "judge_top1": "na", "judge_conf": 0.9708,
                  "judge_note": "school-v3 gate3.json: best na, old_ruler_pass=true too",
                  "iddo_prior": None})

    na_orig = [
        ("v10", _p(SV2, "lessons", "CLAUDE-na-v10.wav"), "ma", 0.385),
        ("v13", _p(SV2, "lessons", "CLAUDE-na-v13.wav"), "ma", 0.368),
    ]
    for tag, wav, top1, conf in na_orig:
        items.append({"group": "na_original", "truth": "na", "wav": wav,
                       "source": "school-v2/lessons", "label_hint": "na-orig-%s" % tag,
                       "judge_top1": top1, "judge_conf": conf,
                       "judge_note": "one of the 14 original school-v2 na lessons; judge heard ma in 10/14 of them (val-teacher-v2.json)",
                       "iddo_prior": "Iddo 15:27 on the teacher's na lessons in general: \"קלוד NA אתה אומר MA\" (not this specific clip)"})

    corpus = [
        ("ma_h01_0.wav", "ma", "la", 0.8039, "ma\u2192la (M\u2192L) confusion"),
        ("ma_h01_1.wav", "ma", "la", 0.7442, "ma\u2192la (M\u2192L) confusion"),
        ("tsa_h00_0.wav", "tza", "sa", 0.9027, "tza\u2192sa (TS\u2192S) confusion"),
        ("tsa_h01_0.wav", "tza", "sa", 0.9054, "tza\u2192sa (TS\u2192S) confusion"),
        ("tha_h00_0.wav", "ta", "ka", 0.9700, "ta\u2192ka (T\u2192K, tet/tav heard as kaf/qof) confusion"),
        ("tha_h01_0.wav", "ta", "ka", 0.9379, "ta\u2192ka (T\u2192K) confusion"),
        ("sa_h00_0.wav", "sa", "kha", 0.9441, "sa\u2192kha (S\u2192X, samekh heard as het/khaf) confusion"),
        ("sa_h00_1.wav", "sa", "kha", 0.9749, "sa\u2192kha (S\u2192X) confusion"),
        ("ha_h00_0.wav", "ha", "ha", 0.6505, "control: judge got this one RIGHT"),
        ("pa_h00_0.wav", "pa", "pa", 0.7599, "control: judge got this one RIGHT"),
    ]
    for fn, truth, top1, conf, note in corpus:
        items.append({"group": "corpus", "truth": truth, "wav": _p(VAULT, fn),
                       "source": "proof/heldout-vault", "label_hint": "corpus-%s" % fn.replace(".wav", ""),
                       "judge_top1": top1, "judge_conf": conf,
                       "judge_note": note + " (val-human132.json row)",
                       "iddo_prior": None})

    items.append({"group": "anchor", "truth": "ma", "wav": _p(LISTEN, "IDDO-ma.wav"),
                  "source": "throat-one-sample/LISTEN", "label_hint": "iddo-ma",
                  "judge_top1": "ma", "judge_conf": None,
                  "judge_note": "report: judge got 4/5 of Iddo's own clips right, only ya missed (heard as da) -- ma was one of the correct ones; exact per-clip confidence not saved",
                  "iddo_prior": None})

    return items


def build_key():
    items = build_items()
    order = list(range(len(items)))
    random.Random(SEED).shuffle(order)
    key = {
        "what": "sitting3-20260903: settles two open questions from HEBREW-JUDGE-20260903.md -- "
                "does Iddo still hear ma on the na candidates the judge scores as na, and does he "
                "hear the syllable the corpus filename claims, on clips the judge got systematically "
                "wrong. 20 clips, 4 groups (na_candidates, na_v3_best, na_original, corpus, anchor).",
        "seed": SEED,
        "groups": ["na_candidates", "na_v3_best", "na_original", "corpus", "anchor"],
        "order": {},
    }
    for k, idx in enumerate(order, 1):
        it = dict(items[idx])
        key["order"][str(k)] = it
    if not os.path.isfile(KEY_PATH):
        with io.open(KEY_PATH, "w", encoding="utf-8") as f:
            json.dump(key, f, ensure_ascii=False, indent=1)
    with io.open(KEY_PATH, encoding="utf-8") as f:
        return json.load(f)["order"]


ORDER = build_key()            # "k" -> {group, truth, wav, source, judge_*, iddo_prior}
N = len(ORDER)


def log(msg):
    try:
        with io.open(LOG, "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (datetime.now().isoformat(timespec="seconds"), msg))
    except OSError:
        pass


def load_state():
    st = {}
    if not os.path.isfile(VERDICTS):
        return st
    with io.open(VERDICTS, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("sitting") != SITTING or r.get("source") != SOURCE:
                continue
            k = str(r.get("clip"))
            if k in ORDER and r.get("heard") in CHOICES:
                st[k] = {"heard": r["heard"], "note": r.get("note") or "", "ts": r.get("ts")}
    return st


PAGE_TMPL = u"""<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ישיבה 3 — נַ והקורפוס</title>
<style>
 *{box-sizing:border-box;margin:0;padding:0}
 body{background:#ffffff;color:#1f2420;font-family:"Assistant","Segoe UI",Arial,sans-serif;
      padding:0 16px 60px;line-height:1.5;max-width:760px;margin:0 auto}
 .bar{position:sticky;top:0;background:#fff;padding:12px 0 10px;font-size:16px;z-index:5;
      border-bottom:2px solid #2e6b8f;margin-bottom:14px;display:flex;justify-content:space-between;
      align-items:center;gap:10px}
 .bar b{font-size:18px}
 .intro{background:#eef6fb;border:1px solid #bcd8e8;border-radius:12px;padding:10px 14px;margin-bottom:14px;font-size:15px}
 .card{background:#fff;border:1px solid #ddd;border-radius:14px;padding:14px 16px;margin-bottom:14px}
 .card.done{border-color:#2e8b57;background:#f3fbf5}
 .n{color:#777;font-size:13px}
 .q{font-size:17px;margin:6px 0 8px}
 audio{width:100%;margin:4px 0 10px}
 .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(88px,1fr));gap:6px}
 .grid button{font-size:22px;padding:8px 4px;border:1px solid #ccc;border-radius:10px;background:#fafafa;
      cursor:pointer;font-family:inherit;line-height:1.2}
 .grid button.noise{font-size:15px;grid-column:1 / -1;background:#f4f4f4}
 .grid button.sel{background:#2e6b8f;color:#fff;border-color:#2e6b8f}
 .note{width:100%;margin-top:10px;font-family:inherit;font-size:14px;padding:8px 10px;border:1px solid #ccc;border-radius:8px}
 .ok{font-size:16px;margin-top:6px;font-weight:700;min-height:22px} .ok.yes{color:#2e8b57} .ok.no{color:#b00020}
</style></head><body>
<div class="bar"><b>ישיבה 3 — נַ והקורפוס 🎧</b><span id="prog"></span> · <span id="srv"></span></div>
<div class="intro">__N__ קליפים, סדר מעורבב, בלי שמות ובלי סימון מאיזה מקור. שמע כל אחד ולחץ על מה ששמעת.
אין תשובה נכונה על הדף — רק האוזן שלך קובעת. אפשר לשנות דעה, הלחיצה האחרונה נשמרת.</div>
__CARDS__
<script>
const STATE=__STATE__; const N=__N__; const done={};
function bar(){const d=Object.keys(done).length;document.getElementById('prog').textContent=d+' / '+N+(d===N?' ✔ סיימת':'');}
function apply(k,c,note){
  const card=document.getElementById('c-'+k); if(!card) return;
  card.querySelectorAll('.grid button').forEach(b=>b.classList.toggle('sel',b.dataset.c===c));
  card.classList.add('done'); done[k]=c;
  if(note!==undefined) card.querySelector('.note').value=note;
  bar();
}
function saved(k,ok){const e=document.querySelector('#c-'+k+' .ok'); if(!e) return;
  e.textContent=ok?'נשמר בשרת ✔':'לא נשמר ✖ — לחץ שוב'; e.className='ok '+(ok?'yes':'no');}
function srv(n){const s=document.getElementById('srv'); if(s) s.textContent='נשמרו בשרת: '+n+' / '+N;}
function refreshCount(){fetch('/n',{cache:'no-store'}).then(r=>r.json()).then(j=>srv(j.n)).catch(()=>{});}
function send(k,c,note){
  const q='/k?'+new URLSearchParams({k:k,heard:c,note:note}).toString();
  fetch(q,{cache:'no-store'}).then(r=>r.ok?r.json():Promise.reject(r.status))
   .then(j=>{saved(k,true); srv(j.n);})
   .catch(()=>{const im=new Image(); im.onload=()=>{saved(k,true); refreshCount();};
     im.onerror=()=>saved(k,false); im.src=q+'&img=1&t='+Date.now();});
}
function vote(k,c){
  const note=document.querySelector('#c-'+k+' .note').value;
  apply(k,c); send(k,c,note);
  const next=document.getElementById('c-'+(parseInt(k)+1));
  if(next && !done[String(parseInt(k)+1)]) next.scrollIntoView({behavior:'smooth',block:'start'});
}
function noteChanged(k){ if(!done[k]) return; send(k,done[k],document.querySelector('#c-'+k+' .note').value); }
for(const k in STATE) apply(k,STATE[k].heard,STATE[k].note);
bar(); refreshCount();
</script></body></html>"""

CARD_TMPL = u"""<div class="card" id="c-{k}">
 <div class="n">קליפ {k} מתוך {n}</div>
 <audio controls preload="none" src="/clip/{k}.wav"></audio>
 <div class="q">מה שמעת?</div>
 <div class="grid">{buttons}</div>
 <input class="note" placeholder="הערה (לא חובה)" maxlength="500" onchange="noteChanged('{k}')">
 <div class="ok"></div>
</div>
"""


def buttons(k):
    out = []
    for c in CLASSES:
        out.append(u'<button data-c="%s" onclick="vote(\'%s\',\'%s\')">%s</button>'
                   % (c, k, c, html.escape(HEB[c])))
    out.append(u'<button class="noise" data-c="noise" onclick="vote(\'%s\',\'noise\')">%s</button>'
               % (k, html.escape(HEB["noise"])))
    return "".join(out)


def page():
    cards = "".join(CARD_TMPL.format(k=k, n=N, buttons=buttons(k)) for k in range(1, N + 1))
    state = json.dumps(load_state(), ensure_ascii=False).replace("</", "<\\/")
    return (PAGE_TMPL.replace("__N__", str(N)).replace("__CARDS__", cards)
            .replace("__STATE__", state))


GROUP_HEB = {"na_candidates": "6 מועמדי נַ (17:58/18:1x)", "na_v3_best": "הנַ הכי טוב של school-v3 (0.9708)",
             "na_original": "2 שיעורי נַ מקוריים (השופט שמע מַ)", "corpus": "10 קליפי קורפוס אנושי",
             "anchor": "העוגן שלך (IDDO-ma.wav)"}


def report_text():
    state = load_state()
    if not state:
        return "sitting3-20260903 -- 0 answers yet. Come back after Iddo has judged at least one clip.\n"
    lines = ["sitting3-20260903 -- scoreboard (%d / %d answered)" % (len(state), N), "=" * 70]
    groups = ["na_candidates", "na_v3_best", "na_original", "corpus", "anchor"]
    totals = {"n": 0, "iddo_eq_truth": 0, "iddo_eq_judge": 0, "judge_eq_truth": 0}
    for g in groups:
        rows = [(k, v) for k, v in ORDER.items() if v["group"] == g]
        lines.append("")
        lines.append("[%s] %s -- %d clips" % (g, GROUP_HEB.get(g, g), len(rows)))
        for k, it in sorted(rows, key=lambda p: int(p[0])):
            heard = state.get(k)
            truth_cls = CLASS_OF.get(it["truth"], it["truth"])
            judge_cls = CLASS_OF.get(it.get("judge_top1") or "", it.get("judge_top1") or "?")
            if heard is None:
                lines.append("  clip %-3s NOT YET ANSWERED  (truth=%s  judge=%s%s)"
                              % (k, truth_cls, judge_cls,
                                 (" %.3f" % it["judge_conf"]) if it.get("judge_conf") is not None else ""))
                continue
            h = heard["heard"]
            iddo_eq_truth = (h == truth_cls)
            iddo_eq_judge = (h == judge_cls)
            judge_eq_truth = (judge_cls == truth_cls)
            totals["n"] += 1
            totals["iddo_eq_truth"] += int(iddo_eq_truth)
            totals["iddo_eq_judge"] += int(iddo_eq_judge)
            totals["judge_eq_truth"] += int(judge_eq_truth)
            lines.append("  clip %-3s Iddo=%-6s truth=%-6s judge=%-6s%s  | Iddo==truth:%s Iddo==judge:%s judge==truth:%s%s"
                          % (k, h, truth_cls, judge_cls,
                             (" (%.3f)" % it["judge_conf"]) if it.get("judge_conf") is not None else "",
                             "Y" if iddo_eq_truth else "n",
                             "Y" if iddo_eq_judge else "n",
                             "Y" if judge_eq_truth else "n",
                             ("  note: %s" % heard["note"]) if heard.get("note") else ""))
    lines.append("")
    lines.append("=" * 70)
    if totals["n"]:
        lines.append("TOTAL answered: %d  |  Iddo==truth: %d (%.0f%%)  |  Iddo==judge: %d (%.0f%%)  |  judge==truth: %d (%.0f%%)"
                      % (totals["n"], totals["iddo_eq_truth"], 100.0 * totals["iddo_eq_truth"] / totals["n"],
                         totals["iddo_eq_judge"], 100.0 * totals["iddo_eq_judge"] / totals["n"],
                         totals["judge_eq_truth"], 100.0 * totals["judge_eq_truth"] / totals["n"]))
    lines.append("")
    lines.append("Read this as: na_candidates+na_v3_best group answers 'is the judge right that these are na "
                 "now, or is Iddo still hearing ma'; na_original is the case the judge already agrees with Iddo "
                 "on (sanity check); corpus answers 'is the 132-clip exam readable at all, or is the judge's "
                 "26.5% a real ceiling'; anchor is a sanity floor (Iddo's own recorded ma).")
    return "\n".join(lines) + "\n"


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

    def _404(self):
        return self._s("404", "text/plain; charset=utf-8", 404)

    def do_GET(self):
        p = urllib.parse.urlparse(self.path).path
        if p == "/n":
            return self._s(json.dumps({"n": len(load_state())}), "application/json; charset=utf-8")
        if p == "/report":
            if self.client_address[0] not in ("127.0.0.1", "::1"):
                return self._404()
            return self._s(report_text(), "text/plain; charset=utf-8")
        if p == "/k":
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            d = {k: v[0] for k, v in qs.items()}
            return self._vote(d)
        if p in ("/", "/index.html"):
            return self._s(page())
        if p.startswith("/clip/") and p.endswith(".wav"):
            k = p[len("/clip/"):-4]
            if k in ORDER and os.path.isfile(ORDER[k]["wav"]):
                with open(ORDER[k]["wav"], "rb") as fh:
                    return self._s(fh.read(), "audio/wav")
        return self._404()

    def _vote(self, d):
        k, heard = str(d.get("k")), d.get("heard")
        if k not in ORDER or heard not in CHOICES:
            return self._s("bad vote", "text/plain; charset=utf-8", 400)
        note = str(d.get("note") or "").strip()[:500]
        it = ORDER[k]
        row = {"ts": datetime.now().astimezone().isoformat(timespec="seconds"),
               "judge": "iddo", "sitting": SITTING, "clip": k, "heard": heard,
               "unit": it["truth"], "group": it["group"],
               "correct": (heard == CLASS_OF.get(it["truth"], it["truth"])),
               "source": SOURCE, "kind": it["group"], "sigma": None,
               "none_good": (heard == "noise"), "note": note}
        with LOCK:
            with io.open(VERDICTS, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        if d.get("img"):
            return self._s(GIF, "image/gif")
        return self._s(json.dumps({"ok": True, "n": len(load_state())}), "application/json; charset=utf-8")

    def do_POST(self):
        p = urllib.parse.urlparse(self.path).path
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        if p != "/vote":
            return self._404()
        try:
            d = json.loads(raw.decode("utf-8"))
        except ValueError:
            return self._s("bad json", "text/plain; charset=utf-8", 400)
        return self._vote(d)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    missing = [k for k, v in ORDER.items() if not os.path.isfile(v["wav"])]
    log("sitting3: %d clips, missing %s -> http://127.0.0.1:%d/" % (N, missing, PORT))
    print("sitting3: %d clips  ->  http://127.0.0.1:%d/" % (N, PORT), flush=True)
    with socketserver.ThreadingTCPServer(("127.0.0.1", PORT), H) as srv:
        srv.serve_forever()
