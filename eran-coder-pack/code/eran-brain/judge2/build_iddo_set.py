#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""build_iddo_set.py - GROUND B. The one clean labelled set of IDDO'S OWN judgements.

Merges two sources that use OPPOSITE polarity scales. Getting this wrong silently
inverts the whole judge, so both are stated and normalised here, once:

  A) judging/iddo-verdicts.jsonl - the station, 2026-08-26..09-01.
     station.py:82  VERDICT_TXT = {1:"mezahe/GOOD", 2:"karov aval lo/CLOSE", 3:"lo/NO"}
     LOWER = BETTER.
  B) judging/sitting-20260901.jsonl - the blind booth, 2026-09-01 08:10-08:12.
     booth.py:  1 = raash/noise ... 5 = nishma enoshi/sounds human.
     HIGHER = BETTER.

Both are mapped onto one axis: iddo_human in [0,1], 1 = closest to a human mouth.

Rows in (A) that were hand-appended as prose (no `file` key, `clip` is a sentence)
are NOT given a numeric label - three of the four carry verdict:1 while their text
is an outright rejection, i.e. the writer used a different convention. They are
kept as rulings, excluded from training.
"""
import json, os, collections
from datetime import datetime

ROOT = r"D:\CLAUDE\eran-brain"
JD   = os.path.join(ROOT, "judging")
OUT  = os.path.join(ROOT, "judge2")
os.makedirs(OUT, exist_ok=True)

STATION_NORM = {1: 1.0, 2: 0.5, 3: 0.0}          # good / close / no
SITTING_NORM = {1: 0.0, 2: 0.25, 3: 0.5, 4: 0.75, 5: 1.0}

def load_jsonl(p):
    with open(p, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]

# ---------------------------------------------------------------- A: station
station, rulings = [], []
for i, r in enumerate(load_jsonl(os.path.join(JD, "iddo-verdicts.jsonl"))):
    if "file" not in r:
        rulings.append({"row": i, "ts": r.get("ts"), "clip_desc": r.get("clip"),
                        "verdict_field": r.get("verdict"),
                        "words_he": r.get("words_he"), "meaning": r.get("meaning") or r.get("finding"),
                        "numeric_label": None,
                        "why_excluded": "hand-appended prose row; verdict field conflicts with station scale"})
        continue
    path = os.path.join(JD, "queue", r["file"])
    station.append({
        "id": "station:%s" % r["file"],
        "path": path if os.path.exists(path) else None,
        "path_claimed": r["file"],
        "exists": os.path.exists(path),
        "source": "station",
        "date": (r.get("utc") or "")[:10],
        "unit": r.get("unit"),
        "arm": r.get("arm"),
        "wdist": r.get("wdist"),
        "iddo_raw": r["verdict"],
        "iddo_scale": "station 1=good 2=close 3=no (lower better)",
        "iddo_human": STATION_NORM[r["verdict"]],
        "note": r.get("note") or "",
        "truth": "ERAN",          # every station clip is machine output
    })

# ---------------------------------------------------------------- B: sitting
man = {int(m["n"]): m for m in json.load(open(os.path.join(JD, "sitting-clips", "manifest.json"), encoding="utf-8"))}
raw = load_jsonl(os.path.join(JD, "sitting-20260901.jsonl"))
last = {}                       # booth.py: "the file is a log, the last word wins"
rerated = collections.Counter()
for r in raw:
    rerated[r["clip"]] += 1
    last[r["clip"]] = r
sitting = []
for clip, r in sorted(last.items()):
    n = int(clip.replace("clip", ""))
    m = man[n]
    src = m["src"]
    sitting.append({
        "id": "sitting:%s" % clip,
        "path": os.path.join(JD, "sitting-clips", "%s.wav" % clip),
        "path_original": src,
        "original_exists": os.path.exists(src),
        "exists": os.path.exists(os.path.join(JD, "sitting-clips", "%s.wav" % clip)),
        "source": "sitting-20260901",
        "date": r["ts"][:10],
        "unit": None,
        "arm": None,
        "wdist": None,
        "iddo_raw": r["score"],
        "iddo_scale": "booth 1=noise .. 5=human (higher better)",
        "iddo_human": SITTING_NORM[r["score"]],
        "note": "",
        "truth": "HUMAN" if m["kind"] == "human-anchor" else "ERAN",
        "kind": m["kind"],
        "ratings_given": rerated[clip],
        "blind": True,
    })

allrows = station + sitting
with open(os.path.join(OUT, "iddo-labels.jsonl"), "w", encoding="utf-8") as f:
    for r in allrows: f.write(json.dumps(r, ensure_ascii=False) + "\n")
with open(os.path.join(OUT, "iddo-rulings.json"), "w", encoding="utf-8") as f:
    json.dump(rulings, f, ensure_ascii=False, indent=1)

# ---------------------------------------------------------------- report
P = print
P("BUILT %s" % os.path.join(OUT, "iddo-labels.jsonl"))
P("  station rows      %d   (resolve on disk: %d)" % (len(station), sum(r["exists"] for r in station)))
P("  sitting rows      %d   (raw log lines %d, re-rated clips %s)"
  % (len(sitting), len(raw), {k: v for k, v in rerated.items() if v > 1}))
P("  prose rulings     %d   (EXCLUDED from numeric labels)" % len(rulings))
P("  TOTAL labelled    %d" % len(allrows))
P("")
P("RANGE CHECK - does his ear span a usable range, or only 'reject'?")
for name, rows in (("station", station), ("sitting", sitting), ("ALL", allrows)):
    c = collections.Counter(r["iddo_human"] for r in rows)
    P("  %-8s %s" % (name, "  ".join("%.2f:%d" % (k, c[k]) for k in sorted(c, reverse=True))))
    pos = sum(1 for r in rows if r["iddo_human"] >= 0.75)
    neg = sum(1 for r in rows if r["iddo_human"] <= 0.25)
    P("           high(>=0.75) %d   low(<=0.25) %d   mid %d" % (pos, neg, len(rows) - pos - neg))
P("")
P("STATION per unit (his own ear, 1=good/2=close/3=no):")
g = collections.defaultdict(collections.Counter)
for r in station: g[r["unit"]][r["iddo_raw"]] += 1
for u in sorted(g, key=lambda u: -sum(g[u].values())):
    c = g[u]; n = sum(c.values())
    P("  %-4s n=%-4d good %2d (%4.1f%%)  close %2d  no %2d" % (u, n, c[1], 100*c[1]/n, c[2], c[3]))
P("")
P("STATION per date:")
for d, c in sorted(collections.Counter(r["date"] for r in station).items()): P("  %s  %d" % (d, c))
P("")
P("SITTING - the anchor test that VOIDED the sitting, recomputed from the file:")
hum = [r for r in sitting if r["truth"] == "HUMAN"]
mac = [r for r in sitting if r["truth"] == "ERAN"]
mh = sum(r["iddo_raw"] for r in hum)/len(hum); mm = sum(r["iddo_raw"] for r in mac)/len(mac)
P("  human anchors n=%d mean %.2f  (scores %s)" % (len(hum), mh, [r["iddo_raw"] for r in hum]))
P("  ERAN clips    n=%d mean %.2f  (scores %s)" % (len(mac), mm, sorted((r["iddo_raw"] for r in mac), reverse=True)))
P("  separation    %.2f points on a 1-5 scale" % (mh - mm))
P("  anchor sources: %s" % [os.path.basename(r["path_original"]) for r in hum])
P("  originals still on disk: %d/%d" % (sum(r["original_exists"] for r in sitting), len(sitting)))
