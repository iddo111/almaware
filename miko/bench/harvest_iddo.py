# -*- coding: utf-8 -*-
"""Round 2, CHANGE 1 (the TRUTH half): harvest IDDO'S OWN written material.

His real questions are the honest test set. This script does NOT invent them - it
collects the documents he and his agents actually wrote, and emits one SEED per
document. gen_questions.py then turns each seed into an English research question,
because the page corpus (fineweb-edu / CommonCrawl) is English while his own writing
is half Hebrew. That derivation step is stated openly in the report: the SOURCES are
his, the PHRASING is derived - exactly as round 1's 65 hand-written questions were.

Sources, all real files on this machine:
  1. D:\CLAUDE\miko\FINDINGS-*.md              - his 8 research rulings (round 1 used these)
  2. memory\project_*.md, reference_*.md         - 344 of his 471 project notes
  3. D:\CLAUDE\RAMCHAT\ramchat_session.json    - the team's shared transcript
"""
import json, os, re, sys, glob

MEM = r"C:\Users\<user>\.claude\projects\D--CLAUDE\memory"
FINDINGS = r"D:\CLAUDE\miko"
RAMCHAT = r"D:\CLAUDE\RAMCHAT\ramchat_session.json"
OUT = r"D:\CLAUDE\miko\data\iddo_seeds.jsonl"

# strip yaml front matter, markdown noise, wiki links, urls
def clean(t):
    t = re.sub(r"^---\n.*?\n---\n", "", t, flags=re.S)
    t = re.sub(r"https?://\S+", " ", t)
    t = re.sub(r"\[\[([^\]|]+)\]\]", r"\1", t)
    t = re.sub(r"[`*#>|_~]+", " ", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()

seeds = []

# ---- 1. the FINDINGS rulings: chunked, because each is a whole research session ----
for p in sorted(glob.glob(os.path.join(FINDINGS, "FINDINGS-*.md"))):
    raw = open(p, encoding="utf-8", errors="replace").read()
    # split on markdown headings so each chunk is one topic he actually researched
    parts = re.split(r"\n(?=#{1,3} )", raw)
    for j, part in enumerate(parts):
        c = clean(part)
        if len(c) < 400:
            continue
        seeds.append({"seed_id": f"findings::{os.path.basename(p)}::{j}",
                      "source": "findings", "title": os.path.basename(p),
                      "text": c[:1600]})

# ---- 2. his project / reference memory notes ----
for p in sorted(glob.glob(os.path.join(MEM, "project_*.md")) +
                glob.glob(os.path.join(MEM, "reference_*.md"))):
    raw = open(p, encoding="utf-8", errors="replace").read()
    m = re.search(r'description:\s*"?(.*?)"?\s*\n', raw)
    desc = m.group(1) if m else ""
    c = clean(raw)
    if len(c) < 300:
        continue
    seeds.append({"seed_id": f"memory::{os.path.basename(p)}",
                  "source": "memory", "title": desc[:200] or os.path.basename(p),
                  "text": c[:1600]})

# ---- 3. RAMCHAT - the team transcript, technical messages only ----
try:
    msgs = json.load(open(RAMCHAT, encoding="utf-8"))
    buf = []
    for m in msgs:
        if not isinstance(m, dict):
            continue
        b = clean(str(m.get("body") or m.get("text") or m.get("message") or ""))
        if len(b) > 300:
            buf.append(b[:1600])
    # 500 messages is too many one-by-one; take every 3rd so topics stay distinct
    for j, b in enumerate(buf[::3]):
        seeds.append({"seed_id": f"ramchat::{j}", "source": "ramchat",
                      "title": "ramchat", "text": b})
except Exception as e:
    print("ramchat skipped:", e, file=sys.stderr)

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8") as f:
    for s in seeds:
        f.write(json.dumps(s, ensure_ascii=False) + "\n")

from collections import Counter
print(f"{len(seeds)} seeds -> {OUT}")
print("by source:", Counter(s["source"] for s in seeds))
