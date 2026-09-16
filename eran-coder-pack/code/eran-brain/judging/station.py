# -*- coding: utf-8 -*-
"""station.py -- תחנת השיפוט. Iddo's early-judging station for ERAN's vocal candidates.

WHY. The search runs alone all night on three DGX boxes and Iddo only hears the
survivors the next day. He asked (2026-08-26 20:11): "תן לי להיות יותר מעורב
בשלבי השיפוט הראשוניים." So: a puller drags every review-flagged candidate and
every meaningfully-improved arm best to the PC as it happens, and one bright RTL
page lets him listen and rule in two keystrokes. His ear IS the ground truth --
the machine judge (wdist) already picked squeaky, breathy winners twice tonight
before fence change 3.

THE DATASET. Every verdict is appended to iddo-verdicts.jsonl:
    {utc, file, arm, unit, wdist, verdict: 1|2|3, note}
That file is the training set for the Iddo-head of Judge B -- the naturalness
cortex will one day predict which candidates Iddo would pass, and this station
is where those labels are born. Never edit it by hand; append-only.

LABEL LAW. Every candidate here came out of ERAN's own search -- the puller
only accepts files from review/ and run/*/best.wav on the fleet, asserted in
code. The page says so on every row: ערן מצא לבד.

  python station.py                ->  http://127.0.0.1:8812/  (serve + pull every 10 min)
  python station.py --pull-once    ->  one pull, print counts, exit (seeding/testing)

PORT. 8809 was requested but is held by the KOL letter-board tunnel to eran4
(and 8810/8811 are taken too), so this station lives on 8812. 127.0.0.1 only --
this is Iddo's private bench, not a fleet service. Claimed in RAMCHAT 2026-08-26.

NO WINDOW FLASHES. Every ssh/scp child is spawned with CREATE_NO_WINDOW and
piped stdout/stderr (reference_ssh_popup_no_window) so this can run under
pythonw forever without a single terminal popping on Iddo's screen.

LOGON PERSISTENCE (later, not created here): a scheduled task must launch
console apps through the hidden-window pattern --
    schtasks /Create /TN "ERAN-Judging-Station" /SC ONLOGON
      /TR "wscript.exe \"D:\CLAUDE\run_hidden.vbs\" \"pythonw.exe D:\CLAUDE\eran-brain\judging\station.py\""
(or point the action straight at pythonw.exe). Bare python.exe in a task =
a console window in Iddo's face on every logon; that plague is documented.
"""
import http.server
import io
import json
import re
import socketserver
import subprocess
import sys
import tarfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

PORT = 8812                      # 8809 taken (KOL tunnel), see docstring
PULL_EVERY_S = 600               # ten minutes, matching the fleet's review cadence
RISE_WDIST = 0.15                # an arm best must improve by this much to re-enter
ROOT = Path(__file__).resolve().parent
QUEUE = ROOT / "queue"
QUEUE.mkdir(parents=True, exist_ok=True)
STATE_F = ROOT / "pull-state.json"
VERDICTS = ROOT / "iddo-verdicts.jsonl"
VERDICTS_MD = ROOT / "verdicts.md"
LOG_F = ROOT / "station.log"

# ssh targets exactly as the fleet answers them (CLAUDE.md topology, verified tonight)
BOXES = [("eran2", "eran2"), ("eran3", "eran3"), ("eran4", "eran4@<lan-ip>")]
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)

SAFE_WAV = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,120}\.wav$")
REVIEW_NAME = re.compile(r"^(?P<arm>[a-z0-9-]+)-(?P<ts>\d{4}-\d{2}-\d{2}T\d{6}Z)$")

# ERAN's units in the Hebrew a reader actually says (same table as booth.py)
HEB = {"ah": "אַה", "aa": "אָא", "ba": "בַּ", "ma": "מַ", "la": "לַ", "da": "דַ",
       "ga": "גַ", "pa": "פַּ", "ta": "טַ", "na": "נַ", "ka": "כַּ", "ra": "רַ",
       "sa": "סַ", "ha": "הַ", "va": "וַ", "ya": "יַ", "za": "זַ", "sha": "שַׁ",
       "kha": "חַ", "tha": "תַ", "tsa": "צַ", "qa": "קַ", "ih": "אִי", "eh": "אֶה",
       "oh": "אוֹ", "uh": "אוּ", "abba": "אַבָּא", "ima": "אִמָּא", "iddo": "עִידוֹ",
       "saba": "סָבָא", "safta": "סָבְתָא"}
# arm-strategy tags, short enough to sit on a chip
FLAVOR = [("control-", "ביקורת"), ("-cv", "מודרך"), ("-1kf", "פריים אחד"),
          ("-free", "חופשי"), ("-nasal", "אפי")]

VERDICT_TXT = {1: "👍 מזהה", 2: "🎯 קרוב אבל לא", 3: "👎 לא"}


def log(msg):
    """To station.log always; to the console when one exists (pythonw has none)."""
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    try:
        with LOG_F.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass
    try:
        print(line, flush=True)
    except Exception:
        pass


# ---------------------------------------------------------------- the puller

def run_quiet(argv, timeout):
    """ssh/scp without a window flash: piped, CREATE_NO_WINDOW, hard timeout."""
    return subprocess.run(argv, capture_output=True, text=False,
                          timeout=timeout, creationflags=NOWIN)


REMOTE_SURVEY = (
    "python3 -c 'import json,glob,os,sys\n"
    "root=os.path.expanduser(\"~/throat-search-v3\")\n"
    "rev=sorted(os.listdir(os.path.join(root,\"review\"))) if os.path.isdir(os.path.join(root,\"review\")) else []\n"
    "bests={}\n"
    "for p in glob.glob(os.path.join(root,\"run\",\"*\",\"best.json\")):\n"
    "  arm=os.path.basename(os.path.dirname(p))\n"
    "  try:\n"
    "    d=json.load(open(p))\n"
    "    if os.path.exists(os.path.join(os.path.dirname(p),\"best.wav\")):\n"
    "      bests[arm]={\"wdist\":d.get(\"wdist\"),\"utc\":d.get(\"utc\"),\"unit\":d.get(\"unit\")}\n"
    "  except Exception: pass\n"
    "print(json.dumps({\"review\":rev,\"bests\":bests}))'"
)


def assert_search_path(rel):
    """LABEL LAW: this station serves ONLY what ERAN's search produced by itself."""
    ok = (rel.startswith("throat-search-v3/review/")
          or (rel.startswith("throat-search-v3/run/")
              and rel.endswith(("/best.wav", "/best.json"))))
    if not ok:
        raise AssertionError(f"refusing non-search path: {rel}")


def load_state():
    try:
        return json.loads(STATE_F.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(st):
    STATE_F.write_text(json.dumps(st, indent=1), encoding="utf-8")


def queued_keys():
    """(box, arm, wdist rounded) already in the queue -- the review dir re-flags the
    same improving best every 10 minutes, and the arm's best.json is often the very
    same candidate; without this the queue fills with literal duplicates."""
    keys = set()
    for p in QUEUE.glob("*.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            pr = d.get("provenance", {})
            keys.add((pr.get("box"), pr.get("arm"),
                      round(float(d["candidate"].get("wdist", -1)), 4)))
        except Exception:
            pass
    return keys


def compact_utc(utc):
    """2026-08-26T17:12:36Z -> 20260826T171236Z (sortable filename prefix)."""
    s = re.sub(r"[-:]", "", utc or "")
    return s if re.fullmatch(r"\d{8}T\d{6}Z", s) else \
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def pull_once():
    """One sweep over the three boxes. Returns number of new candidates queued."""
    st = load_state()
    have = queued_keys()
    added = 0
    for box, host in BOXES:
        bst = st.setdefault(box, {"review_seen": [], "best_wdist": {}})
        try:
            r = run_quiet(["ssh", host, REMOTE_SURVEY], timeout=60)
            if r.returncode != 0:
                log(f"pull {box}: ssh survey failed rc={r.returncode} "
                    f"{r.stderr.decode('utf-8', 'replace').strip()[:200]}")
                continue
            survey = json.loads(r.stdout.decode("utf-8"))
        except Exception as e:
            log(f"pull {box}: survey error {e!r}")
            continue

        fetch = []   # (remote_rel, arm, kind)
        rev = set(survey.get("review", []))
        for name in sorted(rev):
            if not name.endswith(".json"):
                continue
            stem = name[:-5]
            m = REVIEW_NAME.fullmatch(stem)
            if not m or f"{stem}.wav" not in rev or name in bst["review_seen"]:
                continue
            fetch.append((f"throat-search-v3/review/{name}", m.group("arm"), "review"))

        for arm, info in sorted(survey.get("bests", {}).items()):
            w = info.get("wdist")
            if w is None:
                continue
            prev = bst["best_wdist"].get(arm)
            # wdist is a distance -- smaller is better; "improved" = dropped
            if prev is not None and prev - w < RISE_WDIST:
                continue
            fetch.append((f"throat-search-v3/run/{arm}/best.json", arm, "early-riser"))

        if not fetch:
            continue

        # ONE tar stream per box. scp into a flat dir was the first draft and it
        # was a real bug: every arm's file is named best.json, so twelve arms
        # overwrote each other in the tmp dir and candidates got the wrong data.
        # tar keeps the run/<arm>/ path, so nothing can collide.
        rels = []
        for rel, arm, kind in fetch:
            wav = rel[:-5] + ".wav"
            assert_search_path(rel)
            assert_search_path(wav)
            rels += [rel, wav]
        try:
            r = run_quiet(["ssh", host, "tar cf - " + " ".join(rels)], timeout=300)
            if not r.stdout:
                log(f"pull {box}: tar fetch empty rc={r.returncode} "
                    f"{r.stderr.decode('utf-8', 'replace').strip()[:200]}")
                continue
            tf = tarfile.open(fileobj=io.BytesIO(r.stdout))
            members = {m.name.lstrip("./"): m for m in tf.getmembers()}
        except Exception as e:
            log(f"pull {box}: tar fetch error {e!r}")
            continue

        for rel, arm, kind in fetch:
            mj = members.get(rel)
            mw = members.get(rel[:-5] + ".wav")
            if mj is None or mw is None:
                continue                                # vanished remotely; next sweep
            try:
                cand = json.loads(tf.extractfile(mj).read().decode("utf-8"))
            except Exception as e:
                log(f"pull {box}: bad json {rel}: {e!r}")
                continue
            w = round(float(cand.get("wdist", -1)), 4)
            if kind == "review":
                bst["review_seen"].append(Path(rel).name)   # seen even if duplicate
            else:
                bst["best_wdist"][arm] = cand.get("wdist")
            if (box, arm, w) in have:
                continue                                # same candidate already queued
            stem = f"{compact_utc(cand.get('utc'))}_{box}_{arm}_{w:.3f}"
            (QUEUE / f"{stem}.wav").write_bytes(tf.extractfile(mw).read())
            (QUEUE / f"{stem}.json").write_text(json.dumps({
                "label": "ערן מצא לבד",
                "provenance": {"box": box, "arm": arm, "kind": kind,
                               "source_path": rel,
                               "pulled_utc": datetime.now(timezone.utc)
                               .strftime("%Y-%m-%dT%H:%M:%SZ")},
                "candidate": cand,
            }, ensure_ascii=False, indent=1), encoding="utf-8")
            have.add((box, arm, w))
            added += 1
            log(f"queued {stem}.wav  ({kind})")
        tf.close()
    save_state(st)
    log(f"pull done: +{added} new candidates, {len(pending())} pending")
    return added


def pull_forever():
    while True:
        try:
            pull_once()
        except Exception as e:
            log(f"pull crashed (surviving): {e!r}")
        time.sleep(PULL_EVERY_S)


# ---------------------------------------------------------------- the bench

def judged_files():
    files = set()
    if VERDICTS.exists():
        for line in VERDICTS.read_text(encoding="utf-8").splitlines():
            try:
                files.add(json.loads(line)["file"])
            except Exception:
                pass
    return files


def judge_b_score(cand):
    """HOOK: when Judge B (the naturalness cortex, ~/judge-b on eran4) starts
    scoring candidates, surface its score here so Iddo sees machine-vs-Iddo
    side by side. For now the sidecars carry no such field."""
    return cand.get("judge_b")            # None today, a number one day


def pending():
    """Unjudged candidates, newest first, shaped for the page."""
    done = judged_files()
    rows = []
    for j in sorted(QUEUE.glob("*.json"), reverse=True):
        wav = j.with_suffix(".wav")
        if not wav.exists() or wav.name in done:
            continue
        try:
            d = json.loads(j.read_text(encoding="utf-8"))
        except Exception:
            continue
        c, pr = d.get("candidate", {}), d.get("provenance", {})
        gd = c.get("gate_detail", {})
        gs = c.get("gate_stats", {})
        unit = c.get("unit", "?")
        arm = pr.get("arm", "?")
        rows.append({
            "file": wav.name, "arm": arm, "unit": unit,
            "heb": HEB.get(unit, unit),
            "flavor": " · ".join(t for pat, t in FLAVOR if pat in ("-" + arm)),
            "box": pr.get("box", "?"), "kind": pr.get("kind", "?"),
            "utc": c.get("utc", ""), "wdist": c.get("wdist"),
            "f0": gs.get("median_f0"), "span": gs.get("span_s"),
            "hnr": gs.get("hnr"),
            "gates_ok": sum(1 for v in gd.values() if v), "gates_n": len(gd),
            "gates_fail": [k.split("_")[0] for k, v in gd.items() if not v],
            "judge_b": judge_b_score(c),
        })
    return rows


def stats():
    """Header numbers + the honest agreement view: mean wdist per Iddo-verdict.
    If his 👍 pile has LOWER wdist than his 👎 pile, the machine judge and his
    ear point the same way; when they diverge, that gap is exactly what the
    Iddo-head of Judge B exists to learn. (wdist RANK agreement + Judge B score
    comparison plug in here once enough verdicts exist.)"""
    today = datetime.now().strftime("%Y-%m-%d")
    n_today, per = 0, {1: [], 2: [], 3: []}
    if VERDICTS.exists():
        for line in VERDICTS.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except Exception:
                continue
            if str(r.get("local", ""))[:10] == today:
                n_today += 1
            if r.get("verdict") in per and isinstance(r.get("wdist"), (int, float)):
                per[r["verdict"]].append(r["wdist"])
    agree = {str(k): (round(sum(v) / len(v), 3) if v else None) for k, v in per.items()}
    return {"today": n_today, "total": sum(len(v) for v in per.values()),
            "agree": agree, "judge_b": "בקרוב"}


PAGE = r"""<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">
<title>ערן — תחנת השיפוט</title><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
 :root{--ink:#14181f;--dim:#5a6474;--line:#dfe4ec;--gold:#e6b800;--good:#1f8b4c;--bad:#c0392b;--near:#b8860b}
 body{font-family:"Segoe UI",Arial,sans-serif;background:#fff;color:var(--ink);margin:0;
      padding:22px 18px 80px;max-width:900px;margin-inline:auto}
 h1{font-size:26px;margin:0 0 2px;color:#0b1b3a}
 .sub{color:var(--dim);font-size:14px;margin-bottom:12px}
 .stats{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:16px}
 .stat{background:#f8fafc;border:1px solid var(--line);border-radius:10px;padding:9px 16px;font-size:13.5px}
 .stat b{font-size:19px;display:block;color:#0b1b3a}
 .keys{background:#fff6d6;border:1px solid var(--gold);border-radius:8px;padding:9px 14px;
       font-size:13px;margin-bottom:16px;line-height:1.6}
 .card{border:1px solid var(--line);border-radius:12px;padding:14px 16px;background:#f8fafc;
       margin-bottom:12px;display:grid;grid-template-columns:auto 1fr;gap:6px 18px;
       transition:opacity .25s}
 .card.focus{border-color:#0b1b3a;box-shadow:0 0 0 2px #0b1b3a33;background:#fff}
 .card.done{opacity:.38;background:#f2f4f7}
 .glyph{font-size:56px;font-weight:700;line-height:1.05;text-align:center;min-width:96px}
 .armname{font-size:12px;color:var(--dim);text-align:center;direction:ltr}
 .selflabel{font-size:11.5px;color:var(--good);text-align:center;font-weight:600}
 .meta{font-size:13.5px;color:var(--dim);display:flex;gap:14px;flex-wrap:wrap;align-items:center}
 .meta b{color:var(--ink)}
 .gates-ok{color:var(--good);font-weight:700}
 .gates-bad{color:var(--bad);font-weight:700}
 .chip{background:#eceff4;border-radius:6px;padding:1px 8px;font-size:12px}
 .riser{background:#fff1cf;border:1px solid var(--gold)}
 audio{width:100%;max-width:460px;height:36px;margin-top:4px}
 .acts{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-top:8px}
 .acts button{font-family:inherit;font-size:15px;padding:9px 16px;border-radius:8px;
       border:1px solid var(--line);background:#fff;cursor:pointer;font-weight:600}
 .acts button:hover{border-color:#0b1b3a}
 .v1{color:var(--good)} .v2{color:var(--near)} .v3{color:var(--bad)}
 .note{font-family:inherit;font-size:13.5px;padding:8px 10px;border:1px solid var(--line);
       border-radius:8px;flex:1;min-width:160px}
 .verdicted{font-size:15px;font-weight:700;margin-top:8px}
 .empty{color:var(--dim);text-align:center;padding:40px 0;font-size:16px}
</style></head><body>
<h1>תחנת השיפוט של ערן</h1>
<div class="sub">כל מועמד כאן — <b>ערן מצא לבד</b>. האוזן שלך היא האמת; כל פסיקה מלמדת את שופט ב׳.</div>

<div class="stats">
 <div class="stat"><b id="st-today">0</b>נשפטו היום</div>
 <div class="stat"><b id="st-pend">0</b>ממתינים</div>
 <div class="stat" title="wdist ממוצע לפי הפסיקה שלך — אם ה־👍 נמוך מה־👎, האוזן שלך והשופט המכני מסכימים">
   <b id="st-agree">—</b>הסכמה מול wdist (👍/👎)</div>
 <div class="stat"><b>__JUDGE_B__</b>שופט ב׳</div>
</div>

<div class="keys">⌨️ <b>1</b> = 👍 מזהה · <b>2</b> = 🎯 קרוב אבל לא · <b>3</b> = 👎 לא ·
 <b>רווח</b> = נגן/עצור · <b>↑/↓</b> = מעבר בין מועמדים. אחרי פסיקה — הבא מתמקד לבד.</div>

<div id="list"></div>

<script>
const CANDS = __CANDS__;
const STATS = __STATS__;
let focus = 0;

const $=id=>document.getElementById(id);
function fmt(x,d){ return (x===null||x===undefined)?"—":Number(x).toFixed(d); }

function drawStats(extraToday){
  $("st-today").textContent = STATS.today + (extraToday||0);
  $("st-pend").textContent = document.querySelectorAll(".card:not(.done)").length;
  const a=STATS.agree;
  $("st-agree").textContent = (a["1"]!==null&&a["3"]!==null) ? `${a["1"]} / ${a["3"]}` : "—";
}

function draw(){
  const L=$("list");
  if(!CANDS.length){ L.innerHTML='<div class="empty">התור ריק — המשיכה הבאה בעוד עד 10 דקות. ערן מחפש.</div>'; return; }
  L.innerHTML = CANDS.map((c,i)=>{
    const gates = c.gates_ok===c.gates_n
      ? `<span class="gates-ok">שערים ${c.gates_ok}/${c.gates_n} ✓</span>`
      : `<span class="gates-bad">שערים ${c.gates_ok}/${c.gates_n} ✗ ${c.gates_fail.join(",")}</span>`;
    const kind = c.kind==="early-riser" ? `<span class="chip riser">⏫ משתפר</span>` : `<span class="chip">🔎 לביקורת</span>`;
    const jb = c.judge_b!==null&&c.judge_b!==undefined ? ` · שופט ב׳ <b>${fmt(c.judge_b,3)}</b>` : "";
    return `<div class="card" id="c${i}" tabindex="0">
      <div>
        <div class="glyph">${c.heb}</div>
        <div class="armname">${c.arm} · ${c.box}</div>
        <div class="selflabel">ערן מצא לבד</div>
      </div>
      <div>
        <div class="meta">${kind}<span class="chip">${c.flavor||""}</span>
          <span>wdist <b>${fmt(c.wdist,3)}</b></span>
          <span>f0 <b>${fmt(c.f0,0)}</b> Hz</span>
          <span>אורך <b>${fmt(c.span,2)}</b> שנ׳</span>
          ${gates}${jb}</div>
        <audio controls preload="none" src="/wav/${encodeURIComponent(c.file)}"></audio>
        <div class="acts">
          <button class="v1" onclick="verdict(${i},1)">👍 מזהה</button>
          <button class="v2" onclick="verdict(${i},2)">🎯 קרוב אבל לא</button>
          <button class="v3" onclick="verdict(${i},3)">👎 לא</button>
          <input class="note" id="n${i}" placeholder="הערה (לא חובה)" maxlength="200">
        </div>
        <div class="verdicted" id="r${i}"></div>
      </div>
    </div>`; }).join("");
  setFocus(0); drawStats(0);
}

function setFocus(i){
  if(i<0||i>=CANDS.length) return;
  document.querySelectorAll(".card").forEach(c=>c.classList.remove("focus"));
  focus=i;
  const el=$("c"+i);
  el.classList.add("focus");
  el.scrollIntoView({block:"center",behavior:"smooth"});
}

let judgedNow=0;
async function verdict(i,v){
  const c=CANDS[i], el=$("c"+i);
  if(el.classList.contains("done")) return;
  const res=await fetch("/verdict",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({file:c.file,verdict:v,note:$("n"+i).value.trim()})});
  if(!res.ok){ $("r"+i).textContent="✗ שמירה נכשלה ("+res.status+")"; return; }
  el.classList.add("done"); el.classList.remove("focus");
  $("r"+i).textContent=({1:"👍 מזהה",2:"🎯 קרוב אבל לא",3:"👎 לא"})[v]+" — נשמר ✓";
  const au=el.querySelector("audio"); if(au) au.pause();
  judgedNow++; drawStats(judgedNow);
  for(let j=i+1;j<CANDS.length;j++)
    if(!$("c"+j).classList.contains("done")){ setFocus(j); return; }
  for(let j=0;j<CANDS.length;j++)
    if(!$("c"+j).classList.contains("done")){ setFocus(j); return; }
}

document.addEventListener("keydown",e=>{
  if(e.target.tagName==="INPUT") return;
  if(e.key==="1"||e.key==="2"||e.key==="3"){ verdict(focus,+e.key); e.preventDefault(); }
  else if(e.key===" "){ const au=$("c"+focus)?.querySelector("audio");
    if(au){ au.paused?au.play():au.pause(); } e.preventDefault(); }
  else if(e.key==="ArrowDown"){ setFocus(Math.min(focus+1,CANDS.length-1)); e.preventDefault(); }
  else if(e.key==="ArrowUp"){ setFocus(Math.max(focus-1,0)); e.preventDefault(); }
});
draw();
</script></body></html>"""


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        import urllib.parse as _up
        parsed = _up.urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            st = stats()
            rows = pending()
            # ?unit=ah  -- Iddo's ruling 2026-08-27 06:10: "ah is at 90%, needs a
            # little cleaning; the rest is nothing." No reason to make his ear
            # wade through 170 candidates he already ruled on as a class.
            want = _up.parse_qs(parsed.query).get("unit", [""])[0].strip()
            if want:
                keep = {u.strip() for u in want.split(",") if u.strip()}
                rows = [r for r in rows if r.get("unit") in keep]
                rows.sort(key=lambda r: (r.get("wdist") is None, r.get("wdist")))
            body = (PAGE.replace("__CANDS__", json.dumps(rows, ensure_ascii=False))
                        .replace("__STATS__", json.dumps(st, ensure_ascii=False))
                        .replace("__JUDGE_B__", st["judge_b"])).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.startswith("/wav/"):
            self.serve_wav(self.path[5:])
            return
        self.send_error(404)

    def serve_wav(self, raw):
        """Full-file or single byte-range responses, so <audio> can seek."""
        import urllib.parse
        name = urllib.parse.unquote(raw)
        if not SAFE_WAV.fullmatch(name) or ".." in name:
            self.send_error(404); return
        p = QUEUE / name
        if not p.is_file():
            self.send_error(404); return
        size = p.stat().st_size
        start, end = 0, size - 1
        rng = self.headers.get("Range", "")
        m = re.fullmatch(r"bytes=(\d*)-(\d*)", rng.strip()) if rng else None
        partial = False
        if m and (m.group(1) or m.group(2)):
            if m.group(1):
                start = int(m.group(1))
                end = min(int(m.group(2)), size - 1) if m.group(2) else size - 1
            else:                                   # suffix range: last N bytes
                start = max(0, size - int(m.group(2)))
            if start >= size or start > end:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers(); return
            partial = True
        self.send_response(206 if partial else 200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if partial:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        with p.open("rb") as f:
            f.seek(start)
            remain = end - start + 1
            while remain > 0:
                chunk = f.read(min(65536, remain))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (ConnectionError, OSError):
                    return                          # player closed mid-stream; normal
                remain -= len(chunk)

    def do_POST(self):
        if self.path != "/verdict":
            self.send_error(404); return
        try:
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            name, v = req["file"], int(req["verdict"])
            note = str(req.get("note", ""))[:200].replace("\n", " ")
        except Exception:
            self.send_error(400, "bad json"); return
        if v not in (1, 2, 3) or not SAFE_WAV.fullmatch(name):
            self.send_error(400, "bad verdict"); return
        sidecar = QUEUE / (name[:-4] + ".json")
        if not (QUEUE / name).is_file() or not sidecar.is_file():
            self.send_error(404, "unknown candidate"); return
        if name in judged_files():
            self.send_error(409, "already judged"); return
        d = json.loads(sidecar.read_text(encoding="utf-8"))
        c, pr = d.get("candidate", {}), d.get("provenance", {})
        rec = {"utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "local": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
               "file": name, "arm": pr.get("arm"), "unit": c.get("unit"),
               "wdist": c.get("wdist"), "verdict": v, "note": note}
        with VERDICTS.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        if not VERDICTS_MD.exists():
            VERDICTS_MD.write_text(
                "> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, "
                "fix it IMMEDIATELY.\n\n# פסקי הדין של עידו — תחנת השיפוט\n\n"
                "Mirror of iddo-verdicts.jsonl (the jsonl is the dataset; this is for eyes).\n\n",
                encoding="utf-8")
        with VERDICTS_MD.open("a", encoding="utf-8") as f:
            f.write(f"- {rec['local']} · `{pr.get('arm')}` · {HEB.get(c.get('unit'), c.get('unit'))} · "
                    f"wdist {c.get('wdist'):.3f} · {VERDICT_TXT[v]}"
                    + (f" · _{note}_" if note else "") + "\n")
        log(f"verdict {v} ({VERDICT_TXT[v]}) on {name}" + (f"  note: {note}" if note else ""))
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if "--pull-once" in sys.argv[1:]:
        n = pull_once()
        print(f"pull-once: +{n} new, {len(pending())} pending total")
        raise SystemExit(0)
    threading.Thread(target=pull_forever, daemon=True).start()
    with Server(("127.0.0.1", PORT), H) as httpd:   # 127.0.0.1: Iddo's private bench
        log(f"ERAN judging station  ->  http://127.0.0.1:{PORT}/")
        log(f"queue={QUEUE}  pending={len(pending())}  pull every {PULL_EVERY_S}s")
        httpd.serve_forever()
