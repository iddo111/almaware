# -*- coding: utf-8 -*-
"""almido.py — DJ ALMIDO, the booth. http://127.0.0.1:8863/

לזכרה של עלמה ז״ל ולזכרו של לָאוֹר ז״ל.
DJ ALMIDO = עלמה + עידו.

WHY A BOOTH AND NOT THE DAW
----------------------------
`dj-alma/bridge/` is finished, tested (20/20 grammar cases, 0 command-table
drift) and MUTE: it speaks MIDI to a Mixcraft controller script, and neither
Mixcraft nor loopMIDI is installed on this machine. Verified again 2026-09-05 —
`mido.get_output_names()` offers only the Windows GS Wavetable synth. Two
installs stand between that bridge and its first sound, and installing software
on Iddo's machine unasked is not something to do.

So the booth takes the SAME 18-command Hebrew grammar — imported from
`dj-alma/bridge/grammar.py`, not re-written — and routes it to the one path
that can make a sound today:

    Hebrew command -> the Darwish model composes -> psy_render_v4 masters it
    -> an .mp3 on a page he presses PLAY on.

THE AUDIO LAW, honoured by construction
----------------------------------------
This process never opens an output device and never opens a microphone. It
writes files. The only thing that ever plays is an <audio controls> element the
browser owns, with NO autoplay attribute and no JS that calls .play() — Iddo
presses it, or nothing is heard. `psy_render_v4` was checked for
sounddevice/simpleaudio/playsound/winsound/pyaudio: none present.

WHAT IS WIRED AND WHAT IS NOT — said on the page, not only here
----------------------------------------------------------------
WIRED    the five section commands (they choose which passage of the model's
         output becomes the take, by measuring it), EXTEND_SECTION (8/16/32
         bars), SET_TEMPO and the two tempo nudges.
NOT WIRED  the five volume/mute commands and PLAY/STOP/RECORD. Those address a
         DAW mixer and a transport, and there is no DAW. They are parsed,
         echoed, and marked "לא מחובר / not wired" rather than silently
         swallowed.

stdlib http.server, urllib, html. No Flask, no CDN, no framework — house style.
"""
from __future__ import annotations

import html
import json
import os
import queue
import sys
import threading
import time
import traceback
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
TAKES = os.path.join(HERE, "takes")
BRIDGE = os.path.join(os.path.dirname(HERE), "bridge")
GALERIA = r"D:\CLAUDE\eran-brain\judging\galeria\darwish"
for _p in (HERE, BRIDGE, GALERIA):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import grammar                                                   # noqa: E402
import protocol                                                  # noqa: E402
import compose as C                                              # noqa: E402

PORT = 8863
os.makedirs(TAKES, exist_ok=True)

WIRED = {"SECTION_INTRO", "SECTION_BUILD", "SECTION_DROP", "SECTION_BREAK",
         "SECTION_OUTRO", "EXTEND_SECTION", "SET_TEMPO",
         "TEMPO_NUDGE_UP", "TEMPO_NUDGE_DOWN"}

# ======================================================== THE PUBLISH GATE ===
# 2026-09-05. Two of the four takes Iddo could click and judge were labelled
# `corpus-transcription`: a passage of the REAL Darwish, not the model. He was
# asked for a verdict on the model three times that day and handed something
# else each time. A coloured badge on the page was not enough, because the
# badge is only read if you look at it.
#
# So the rule is now structural, not cosmetic: a take whose source is not
# MODEL_SOURCE is not composed, not written, not listed, and NOT SERVED. The
# /takes/ route resolves every request back to its sidecar and refuses
# anything that is not the model's own work -- a whitelist that refuses by
# default, so a new fallback added later is silently blocked rather than
# silently published. `test_gate.py` fails if any of that stops being true.
MODEL_SOURCE = "model-v2"


def take_is_publishable(meta) -> bool:
    return isinstance(meta, dict) and meta.get("source") == MODEL_SOURCE


def publishable_files() -> set:
    """Every filename the booth is allowed to hand out, from the sidecars.

    Built from disk on each request rather than trusted from memory: the
    answer must not depend on what STATE happens to hold."""
    ok = set()
    try:
        names = os.listdir(TAKES)
    except OSError:
        return ok
    for fn in names:
        if not fn.endswith(".json"):
            continue
        try:
            m = json.load(open(os.path.join(TAKES, fn), encoding="utf-8"))
        except Exception:
            continue
        if not take_is_publishable(m):
            continue
        for k in ("audio", "midi"):
            if m.get(k):
                ok.add(os.path.basename(m[k]))
    return ok

STATE = {
    "section": "SECTION_DROP",
    "bars": 16,
    "bpm": 143.55,
    "log": [],
    "takes": [],
    "busy": False,
    "progress": "",
    "model": None,
}
LOCK = threading.Lock()


def note(msg_he, msg_en, kind="info"):
    with LOCK:
        STATE["log"].insert(0, {"t": datetime.now().strftime("%H:%M:%S"),
                                "he": msg_he, "en": msg_en, "kind": kind})
        del STATE["log"][40:]


def apply_command(text: str) -> dict:
    pc = grammar.parse(text)
    if pc is None:
        note(f"לא הבנתי: {text}", f"not understood: {text}", "warn")
        return {"ok": False, "reason": "not_understood", "text": text}
    cmd = pc.command
    if cmd not in WIRED:
        note(f"{cmd} — פקודה של הדִיג׳יי־מיקסר, אין DAW מותקן",
             f"{cmd} — mixer/transport command, no DAW installed", "warn")
        return {"ok": True, "command": cmd, "wired": False,
                "matched": pc.matched_text}
    with LOCK:
        if cmd.startswith("SECTION_"):
            STATE["section"] = cmd
        elif cmd == "EXTEND_SECTION":
            STATE["bars"] = {0: 8, 1: 16, 2: 32}.get(pc.param, 16)
        elif cmd == "SET_TEMPO":
            STATE["bpm"] = round(protocol.param_to_bpm(pc.param), 2)
        elif cmd == "TEMPO_NUDGE_UP":
            STATE["bpm"] = round(min(160.0, STATE["bpm"] + 1.0), 2)
        elif cmd == "TEMPO_NUDGE_DOWN":
            STATE["bpm"] = round(max(120.0, STATE["bpm"] - 1.0), 2)
    note(f"{pc.matched_text} → {cmd}", f"{pc.matched_text} -> {cmd}", "ok")
    return {"ok": True, "command": cmd, "wired": True, "param": pc.param,
            "matched": pc.matched_text}


# ------------------------------------------------------------------ render

def make_take(seed: int):
    """Compose + render one take. Runs in its own thread; writes files only."""
    import psy_render as V1
    import psy_render_v4 as V4

    t0 = time.time()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    with LOCK:
        section, bars, bpm = STATE["section"], STATE["bars"], STATE["bpm"]
    base = f"almido-{stamp}-{C.SECTIONS[section]['en']}"
    mid = os.path.join(TAKES, base + ".mid")
    wav = os.path.join(TAKES, base + ".wav")
    mp3 = os.path.join(TAKES, base + ".mp3")

    STATE["progress"] = "מלחין / composing"
    sc, chords, meta = C.compose(bars=bars, section=section, seed=seed, bpm=bpm)
    if not take_is_publishable(meta):
        # refuse at the source, before a file exists to leak
        raise RuntimeError(
            "REFUSED: composer returned source=%r, not %r. A take that is not "
            "the model's own work is never written or served."
            % (meta.get("source"), MODEL_SOURCE))
    C.write_midi(sc, mid)

    STATE["progress"] = "מרנדר / rendering"
    # true_pitch_lead: the lead used to be transposed by an arbitrary interval
    #   against its own bass and pad (measured +6/-2/+4/+5 semitones on the
    #   first takes -- one of them a tritone). That was "אין לזה שום הרמוניה".
    # chord_span_bars: without it the pad stops at the end of the composed
    #   passage and the last 22 of the 38 rendered bars carry no harmony.
    # bass_roots: the bass plays the model's own bass-role notes.
    render = V4.render_one_v4(mid, wav, seed=seed, chord_notes=chords or None,
                              true_pitch_lead=True, chord_span_bars=bars,
                              bass_roots=C.bass_roots(sc))
    # keep the MEASUREMENTS, drop the bulk: the per-note class lists and the
    # two 1/3-octave EQ curves are megabytes of sidecar nobody reads.
    for k in ("_placed_classes", "_orig_classes", "match_eq_db",
              "match_eq_pass2_db", "bar_roots_from_his_phrase"):
        render.pop(k, None)
    try:
        V1.to_mp3(wav, mp3)
        audio = os.path.basename(mp3)
    except Exception:
        audio = os.path.basename(wav)

    meta.update({
        "name": base, "audio": audio, "midi": os.path.basename(mid),
        "seconds_to_make": round(time.time() - t0, 1),
        "chords_sent_to_renderer": len(chords),
        # the renderer MEASURES its own output and used to have every one of
        # those numbers thrown away at this line. They are the only evidence
        # of what actually reached the speaker, so they are kept.
        "render": render,
        "roll": piano_roll_svg(sc),
        "when": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    with open(os.path.join(TAKES, base + ".json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)
    with LOCK:
        STATE["takes"].insert(0, meta)
        del STATE["takes"][12:]
    note(f"טייק מוכן: {base} — {meta['n_notes']} תווים, "
         f"{meta['n_chord_events']} אקורדים",
         f"take ready: {base} — {meta['n_notes']} notes, "
         f"{meta['n_chord_events']} chords", "ok")
    return meta


ROLE_COLOUR = {"lead": "#1d4ed8", "bass": "#c2410c", "pad": "#15803d"}


def piano_roll_svg(sc, w=880, h=190) -> str:
    """Show the harmony rather than claim it: vertical stacks ARE chords.

    Since 2026-09-05 each note is drawn in its VOICE's colour -- blue lead,
    orange bass, green pad -- the same split that decides which MIDI channel
    and which synth voice it goes to. Three colours in one vertical stack is
    a chord being played by three different instruments, which is exactly the
    thing that was missing when Iddo said there was no harmony."""
    if not sc.notes:
        return ""
    lo = min(n.midi for n in sc.notes)
    hi = max(n.midi for n in sc.notes)
    span = max(hi - lo + 1, 12)
    steps = max(sc.n_steps, 1)
    sx = w / steps
    sy = (h - 16) / span
    out = [f'<svg viewBox="0 0 {w} {h}" width="100%" height="{h}" '
           f'style="background:#fbfaf7;border:1px solid #e4e0d6;border-radius:8px">']
    for b in range(0, steps, 16):
        x = b * sx
        out.append(f'<line x1="{x:.1f}" y1="0" x2="{x:.1f}" y2="{h}" '
                   f'stroke="#ece8dd" stroke-width="1"/>')
    # a step carrying two or more sounding pitches gets a warm background band
    active = {}
    for n in sc.notes:
        for s in range(n.step, min(n.step + n.dur, steps)):
            active[s] = active.get(s, 0) + 1
    for s, k in active.items():
        if k >= 2:
            out.append(f'<rect x="{s*sx:.2f}" y="0" width="{max(sx,1):.2f}" '
                       f'height="{h}" fill="#ffe9c9" opacity="0.55"/>')
    try:
        roles = C.split_roles(sc)
    except Exception:
        roles = ["lead"] * len(sc.notes)
    for n, role in zip(sc.notes, roles):
        x = n.step * sx
        y = h - 8 - (n.midi - lo) * sy
        ww = max(n.dur * sx - 0.6, 1.2)
        col = ROLE_COLOUR.get(role, "#1d4ed8")
        out.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{ww:.2f}" '
                   f'height="{max(sy-1,2):.2f}" rx="1.5" fill="{col}"/>')
    out.append("</svg>")
    out.append('<div class="k" style="margin-top:4px">'
               '<span style="color:#1d4ed8">&#9632; lead</span> &nbsp;'
               '<span style="color:#c2410c">&#9632; bass</span> &nbsp;'
               '<span style="color:#15803d">&#9632; pad</span> &nbsp;'
               '&mdash; three voices, three MIDI channels, three synth patches'
               '</div>')
    return "".join(out)


# ------------------------------------------------------------------ page

CSS = """
:root{--ink:#1c1917;--dim:#6b6255;--line:#e4e0d6;--bg:#fdfcf9;--warm:#c2410c;
      --cool:#1d4ed8;--ok:#15803d}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
     font:15px/1.6 "Segoe UI",system-ui,sans-serif}
.wrap{max-width:960px;margin:0 auto;padding:26px 20px 60px}
h1{font-size:30px;margin:0 0 2px;letter-spacing:-.5px}
h1 .he{color:var(--warm)}
.sub{color:var(--dim);margin:0 0 22px;font-size:14px}
.card{background:#fff;border:1px solid var(--line);border-radius:12px;
      padding:16px 18px;margin:0 0 16px}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
input[type=text]{flex:1;min-width:240px;padding:11px 13px;font-size:16px;
     border:1px solid var(--line);border-radius:9px;background:#fff}
button{padding:11px 18px;font-size:15px;border-radius:9px;border:1px solid var(--line);
     background:#fff;cursor:pointer}
button.go{background:var(--warm);border-color:var(--warm);color:#fff;font-weight:600}
button:disabled{opacity:.5;cursor:default}
.chip{display:inline-block;padding:3px 10px;border-radius:99px;font-size:12.5px;
     border:1px solid var(--line);background:#faf8f3;margin:0 6px 6px 0}
.chip.on{background:#fff4e6;border-color:#f2c48a;color:var(--warm);font-weight:600}
.k{color:var(--dim);font-size:12.5px;letter-spacing:.3px;text-transform:uppercase}
.v{font-size:20px;font-weight:600}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(115px,1fr));gap:14px}
audio{width:100%;margin-top:10px}
.log{font-size:13px;color:var(--dim);max-height:190px;overflow:auto}
.log b{color:var(--ink);font-weight:600}
.warn{color:#b45309}
.take{border-top:1px solid var(--line);padding-top:14px;margin-top:14px}
.src{font-size:12px;padding:2px 8px;border-radius:99px;background:#eef4ff;
     color:var(--cool);border:1px solid #cfe0ff}
.src.corpus{background:#fef3c7;color:#92400e;border-color:#fcd34d}
.he{direction:rtl;unicode-bidi:plaintext}
table{border-collapse:collapse;width:100%;font-size:13.5px}
td,th{padding:5px 8px;border-bottom:1px solid var(--line);text-align:left}
.note{font-size:13px;color:var(--dim);border-left:3px solid #f2c48a;
      padding-left:12px;margin-top:12px}
"""

JS = """
async function post(u,b){const r=await fetch(u,{method:'POST',
  headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})});
  return await r.json();}
async function say(){const e=document.getElementById('cmd');
  if(!e.value.trim())return; await post('/say',{text:e.value});
  e.value=''; refresh();}
async function take(){const b=document.getElementById('go');
  b.disabled=true; await post('/take',{}); poll();}
function poll(){setTimeout(async()=>{const s=await(await fetch('/state')).json();
  if(s.busy){document.getElementById('prog').textContent=s.progress;poll();}
  else{location.reload();}},1200);}
async function refresh(){location.reload();}
document.addEventListener('keydown',e=>{if(e.key==='Enter'&&
  document.activeElement.id==='cmd')say();});
"""


def page() -> str:
    with LOCK:
        st = json.loads(json.dumps(STATE))
    sec = C.SECTIONS[st["section"]]
    model_on = C.have_model()
    chips = "".join(
        f'<span class="chip{" on" if k == st["section"] else ""} he">{v["he"]}</span>'
        for k, v in C.SECTIONS.items())

    takes_html = []
    for t in st["takes"]:
        cls = "src" if t.get("source") == "model-v2" else "src corpus"
        src_he = ("המודל (v2)" if t.get("source") == "model-v2"
                  else "תמלול מהקורפוס האמיתי")
        rows = [
            ("תווים / notes", t.get("n_notes")),
            ("פוליפוניה מקס׳ / max simultaneous", t.get("poly_max")),
            ("ממוצע קולות / mean voices", t.get("poly_mean_sounding")),
            ("צעדים עם 2+ קולות / steps 2+", t.get("poly_frac_steps_2plus")),
            ("אקורדים לרנדרר / chords to renderer", t.get("n_chord_events")),
            ("תפקידים ליד/בס/פד / roles lead-bass-pad",
             "%s / %s / %s" % (t.get("roles", {}).get("lead", {}).get("n", "?"),
                               t.get("roles", {}).get("bass", {}).get("n", "?"),
                               t.get("roles", {}).get("pad", {}).get("n", "?"))),
            ("בארים עם פד מתוך 38 / bars with pad of 38",
             len(t.get("render", {}).get("pad_bars_covered", []))),
            ("תיקון סולם הליד / lead key error fixed",
             "%s semitones" % t.get("render", {}).get(
                 "lead_key_offset_semitones_OLD_PATH", "?")),
            ("BPM", t.get("bpm")),
            ("שניות ליצירה / seconds to make", t.get("seconds_to_make")),
        ]
        tbl = "".join(f"<tr><td>{html.escape(str(a))}</td>"
                      f"<td><b>{html.escape(str(b))}</b></td></tr>" for a, b in rows)
        harm = ("" if t.get("n_chord_events") else
                '<div class="note he">המודל לא כתב אף אקורד בטייק הזה, '
                'ולכן הפַּד לא נוגן. / The model wrote no chord in this take, '
                'so the pad voice was not used. Nothing was invented to fill it.</div>')
        takes_html.append(f"""
        <div class="take">
          <div class="row" style="justify-content:space-between">
            <b>{html.escape(t.get('name',''))}</b>
            <span class="{cls}">{html.escape(src_he)}</span>
          </div>
          <audio controls preload="none" src="/takes/{html.escape(t.get('audio',''))}"></audio>
          {t.get('roll','')}
          <table>{tbl}</table>
          {harm}
          <div class="k" style="margin-top:8px">
            MIDI: <a href="/takes/{html.escape(t.get('midi',''))}">{html.escape(t.get('midi',''))}</a>
          </div>
        </div>""")
    if not takes_html:
        takes_html = ['<div class="note he">עוד אין טייקים. תגיד פקודה ולחץ '
                      '"תן טייק". / No takes yet — say a command, then press '
                      '"make a take".</div>']

    logs = "".join(
        f'<div class="{ "warn" if l["kind"]=="warn" else "" }">'
        f'<b>{l["t"]}</b> <span class="he">{html.escape(l["he"])}</span> '
        f'&middot; {html.escape(l["en"])}</div>' for l in st["log"]) or \
        '<div>—</div>'

    model_line = ('<span class="src">מודל v2 טעון / model-v2 loaded</span>'
                  if model_on else
                  '<span class="src corpus">אין עדיין צ׳קפוינט v2 — מנגן תמלול '
                  'של דרוויש האמיתי / no v2 checkpoint yet — playing a real '
                  'Darwish transcription</span>')

    return f"""<!doctype html><html lang="he"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>DJ ALMIDO</title><style>{CSS}</style></head><body><div class="wrap">
<h1><span class="he">די־ג׳יי עלמידו</span> &middot; DJ ALMIDO</h1>
<p class="sub he">עלמה + עידו. המודל של דרוויש מלחין, psy_render_v4 מנגן,
ואתה מנהל את הסט בעברית. שום דבר לא מתנגן לבד — אתה לוחץ PLAY.<br>
<span dir="ltr">Alma + Iddo. The Darwish model composes, psy_render_v4 plays it,
you run the set in Hebrew. Nothing ever plays by itself — you press PLAY.</span></p>

<div class="card">
  <div class="row">
    <input type="text" id="cmd" class="he" placeholder="דרופ / קצב 144 / עוד 16 בר / ברייקדאון">
    <button onclick="say()">אמור / say</button>
    <button class="go" id="go" onclick="take()">תן טייק / make a take</button>
  </div>
  <div style="margin-top:12px">{chips}</div>
  <div class="grid" style="margin-top:14px">
    <div><div class="k">section</div><div class="v he">{sec['he']}</div></div>
    <div><div class="k">bars</div><div class="v">{st['bars']}</div></div>
    <div><div class="k">bpm</div><div class="v">{st['bpm']}</div></div>
    <div><div class="k">composer</div><div style="margin-top:5px">{model_line}</div></div>
  </div>
  <div id="prog" class="k" style="margin-top:10px">{html.escape(st['progress'])}</div>
</div>

<div class="card"><div class="k">takes</div>{''.join(takes_html)}</div>

<div class="card"><div class="k">what the words do</div>
<table>
<tr><th>עברית</th><th>command</th><th>wired?</th></tr>
<tr><td class="he">דרופ / בילד אפ / ברייקדאון / אינטרו / אאוטרו</td>
    <td>SECTION_*</td><td><b style="color:var(--ok)">כן / yes</b></td></tr>
<tr><td class="he">עוד 8 בר / עוד 16 בארים</td><td>EXTEND_SECTION</td>
    <td><b style="color:var(--ok)">כן / yes</b></td></tr>
<tr><td class="he">קצב 144 / מהר יותר / לאט יותר</td><td>SET_TEMPO, nudges</td>
    <td><b style="color:var(--ok)">כן / yes</b></td></tr>
<tr><td class="he">תוריד את הבס / תעלה ליד / השתק תופים / תוריד אפקטים</td>
    <td>*_VOL, *_MUTE</td><td class="warn">לא — אין DAW / no DAW</td></tr>
<tr><td class="he">נגן / עצור / הקלטה</td><td>PLAY / STOP / RECORD</td>
    <td class="warn">לא — אין DAW / no DAW</td></tr>
</table>
<div class="note he">הזרוע השנייה של הפרויקט (<span dir="ltr">dj-alma/bridge</span>)
מדברת MIDI ל־Mixcraft. Mixcraft ו־loopMIDI לא מותקנים כאן, ולא נתקין בלי שתגיד.
<span dir="ltr">The bridge arm is built and tested but mute until those two are
installed — your call, not ours.</span></div>
</div>

<div class="card"><div class="k">log</div><div class="log">{logs}</div></div>
</div><script>{JS}</script></body></html>"""


# ------------------------------------------------------------------ server

class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code, body: bytes, ctype="text/html; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def do_GET(self):
        p = self.path.split("?")[0]
        if p in ("/", "/index.html"):
            return self._send(200, page().encode("utf-8"))
        if p == "/state":
            with LOCK:
                return self._json({k: v for k, v in STATE.items() if k != "takes"})
        if p.startswith("/takes/"):
            name = os.path.basename(p[len("/takes/"):])
            if name not in publishable_files():
                # not a 404: say plainly that the gate refused, so a blocked
                # take can never be mistaken for a missing file.
                return self._send(
                    403, "REFUSED by the publish gate: this file does not "
                    "belong to a source=model-v2 take.".encode("utf-8"),
                    "text/plain; charset=utf-8")
            fp = os.path.join(TAKES, name)
            if not os.path.isfile(fp):
                return self._send(404, b"no such take", "text/plain")
            ct = {"mp3": "audio/mpeg", "wav": "audio/wav",
                  "mid": "audio/midi"}.get(name.rsplit(".", 1)[-1], "application/octet-stream")
            with open(fp, "rb") as f:
                return self._send(200, f.read(), ct)
        return self._send(404, b"not found", "text/plain")

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            body = {}
        p = self.path.split("?")[0]
        if p == "/say":
            return self._json(apply_command(str(body.get("text", ""))))
        if p == "/take":
            with LOCK:
                if STATE["busy"]:
                    return self._json({"ok": False, "reason": "busy"})
                STATE["busy"] = True
                STATE["progress"] = "מתחיל / starting"
            threading.Thread(target=self._render_thread,
                             args=(int(body.get("seed", int(time.time()) % 100000)),),
                             daemon=True).start()
            return self._json({"ok": True})
        return self._json({"ok": False, "reason": "unknown"}, 404)

    def _render_thread(self, seed):
        try:
            make_take(seed)
        except Exception as exc:                                  # noqa: BLE001
            note(f"נפל: {type(exc).__name__}", f"failed: {exc}", "warn")
            traceback.print_exc()
        finally:
            with LOCK:
                STATE["busy"] = False
                STATE["progress"] = ""

    def log_message(self, *a):
        pass


def load_existing_takes():
    """Takes survive a restart. Each one wrote its own metadata sidecar, so the
    page can show the numbers that were true when it was made rather than
    re-deriving them (and possibly re-deriving them differently)."""
    found = []
    for fn in sorted(os.listdir(TAKES)):
        if not fn.endswith(".json"):
            continue
        try:
            m = json.load(open(os.path.join(TAKES, fn), encoding="utf-8"))
        except Exception:
            continue
        if not take_is_publishable(m):
            continue                     # the gate, again, on the way in
        if os.path.isfile(os.path.join(TAKES, m.get("audio", ""))):
            found.append(m)
    found.sort(key=lambda m: m.get("when", ""), reverse=True)
    with LOCK:
        STATE["takes"] = found[:12]
    return len(found)


def main():
    try:
        import psutil
        psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    except Exception:
        pass
    n = load_existing_takes()
    note(f"DJ ALMIDO עלה, {n} טייקים על הדיסק",
         f"DJ ALMIDO is up, {n} takes on disk", "ok")
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    print(f"DJ ALMIDO  http://127.0.0.1:{PORT}/   (local only)", flush=True)
    print(f"composer: {'model-v2' if C.have_model() else 'corpus-transcription (no v2 ckpt yet)'}",
          flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
