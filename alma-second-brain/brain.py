#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ALMA SECOND BRAIN — the distill + query layer over Iddo's existing memory.

WHAT WAS ALREADY THERE (this extends it, it does not replace it):
  * C:\\Users\\iddo1\\.claude\\projects\\*\\memory\\  — the live auto-memory, one fact per
    file, frontmatter name/description/type, MEMORY.md as the index.
  * github.com/iddo111/Claude-Memory-               — the git brain: LATEST/ + snapshots/,
    kof_memory_sync.py, and the tag convention approved 2026-04-17:
    brain/<topic>/<YYYYMMDD>. That convention is honoured here.
  * D:\\CLAUDE\\RAMCHAT                              — the council transcript, the single
    richest record of what the machine actually did, and until now unsearchable.

WHAT WAS MISSING, AND IS WHAT THIS IS:
  Capture existed. Organize existed. **Distill and Express did not.** ~1200 markdown files
  and 500 council messages that nobody — human or model — could query. A second brain is
  not storage you search, it is a knowledge base an agent queries. This is that agent's
  door.

DESIGN, AND WHY

  1. NO VECTOR DB, NO EMBEDDINGS, NO NEW DEPENDENCIES. Pure stdlib BM25. The corpus is
     ~1200 documents; BM25 over it is exact, instant, offline, and cannot silently rot
     the way a stale embedding index does. Nothing to install, nothing to keep running.

  2. HEBREW IS A FIRST-CLASS CITIZEN. Naive tokenisation fails Hebrew badly: 'לפרויקט'
     and 'פרויקט' are different strings, and final forms make 'זיכרון'/'זכרון ' miss.
     Every token is indexed both raw and stripped of niqqud, final-form letters and a
     leading ו/ה/ב/ל/כ/מ/ש. Half this corpus is Hebrew; without this the brain is deaf.

  3. THE LIBRARIAN NEVER ANSWERS FROM ITS OWN WEIGHTS. gpt-oss-120b on eran4 is the
     reader, chosen because the 2026-08-17 grading proved it is the only one of the four
     that raises on a violated assumption instead of returning a confident wrong number.
     It is ALSO the model that fluently hallucinated that a memristor is a city. So the
     prompt is absolute: answer only from the retrieved notes, cite [n] every time, and
     say 'not in the brain' rather than fill the gap. Retrieval is the fact; the model is
     only allowed to phrase it.

  4. IT BINDS TO LOOPBACK. This serves Iddo's entire private memory — every project,
     every piece of personal feedback. Off-loopback requires an explicit --host AND a
     --token. Refusing to start otherwise is the point.

ENDPOINTS
  GET  /                 tiny RTL web UI (works from a phone over the tailnet)
  GET  /search?q=&k=     BM25 hits with scores and snippets — no model involved
  POST /ask              {"q": "...", "k": 8}  retrieve, then let the librarian answer
  POST /capture          {"name","description","type","body","topic","git":false}
                         writes a new memory file + MEMORY.md pointer; optional local
                         commit + brain/<topic>/<date> tag (never pushes)
  GET  /stats            what is indexed, by source and PARA bucket
  POST /reindex          rebuild from disk

  python brain.py [--port 8960] [--host 127.0.0.1] [--token SECRET]
"""
import argparse, json, math, os, re, subprocess, sys, threading, time, unicodedata
import urllib.request, urllib.error, urllib.parse
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ----------------------------------------------------------------------------- corpus
HOME = os.path.expanduser("~")
ROOTS = [
    (os.path.join(HOME, ".claude", "projects"), "claude-memory"),
    (os.path.join(HOME, "Claude-Memory-"), "git-brain"),
    ("D:\\CLAUDE\\keshev-b", "keshev"),
    ("D:\\CLAUDE\\workshop-builds", "workshop"),
]
# RAMCHAT keeps more than one store and they are NOT interchangeable: current_council.json
# is a snapshot that stopped at 2026-08-12, ramchat_session.json is the live one. Indexing
# only the first — which is what v1 did — silently lost every message since, including a
# whole night of fleet work. Both are read; identical messages dedupe against each other.
RAMCHAT_STORES = [
    "D:\\CLAUDE\\RAMCHAT\\ramchat_session.json",
    "D:\\CLAUDE\\RAMCHAT\\current_council.json",
]

# KESHEV — Iddo's own voice. state/corpus/manifest.jsonl is one JSON line per utterance,
# which is the wrong unit to retrieve: nobody wants "Amen." back as a search hit. They are
# grouped into per-session documents in time order, so what comes back is a conversation.
KESHEV_MANIFEST = "D:\\CLAUDE\\mic-rebuild\\state\\corpus\\manifest.jsonl"
LIVE_MEMORY = os.path.join(HOME, ".claude", "projects", "C--Users-iddo1--claude", "memory")
GIT_BRAIN = os.path.join(HOME, "Claude-Memory-")

# snapshots/ in the git brain are point-in-time copies of LATEST/ — indexing them would
# bury every real note under a dozen identical older versions. Skipped on purpose, and
# the count is reported in /stats so the omission is never silent.
SKIP_DIRS = {".git", "node_modules", "__pycache__", "snapshots", ".venv", "venv"}
SKIP_MARKERS = ("_archive", "archive_forgotten")

FLEET_URL = "http://<lan-ip>:8010/v1/chat/completions"
LIBRARIAN = "gpt-oss-120b"

# ------------------------------------------------------------------- hebrew-aware text
HEB_FINALS = str.maketrans("םןץףך", "מנצפכ")
HEB_PREFIX = set("ובהלכמש")
TOKEN_RE = re.compile(r"[A-Za-z0-9\u0590-\u05FF_]+")


def is_hebrew(s):
    return any("\u0590" <= c <= "\u05FF" for c in s)


def strip_niqqud(s):
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if not ("\u0591" <= c <= "\u05C7"))


def variants(tok):
    """Every form this token should be findable as. Hebrew needs three passes."""
    out = {tok}
    if is_hebrew(tok):
        base = strip_niqqud(tok).translate(HEB_FINALS)
        out.add(base)
        # one-letter conjunctions/prepositions glued to the front of the word
        if len(base) > 3 and base[0] in HEB_PREFIX:
            out.add(base[1:])
        if len(base) > 4 and base[0] in HEB_PREFIX and base[1] in HEB_PREFIX:
            out.add(base[2:])
    return out


# Question words carry no signal and pull the ranking toward whatever file happens to be
# chatty. BM25's IDF already discounts them; dropping them outright measurably fixed
# "איזה מודל הכי טוב בעברית", which was returning an image-editing guide.
STOP = set("""
what which who whom whose when where why how the a an is are was were be been being of in
on at to for from with by and or not no yes this that these those it its as do does did
i me my you your we our they them he she his her if then than so such about into over
מה איזה איזו אילו מי של עם על את זה זו זאת אלה אלו יש אין אני אתה את הוא היא הם הן אנחנו
לא כן כי אם אז גם רק עוד כבר הכי יותר פחות טוב טובה איך למה מתי איפה כמה כל אחד אחת
""".split())


# THE BILINGUAL GAP — the single biggest retrieval failure in this corpus.
# Iddo asks in Hebrew; half his memory was written in English. Asking
# "מה הכלל לגבי האוזניות" could not find `feedback_never_touch_audio.md`, because BM25
# matches strings and "אוזניות" and "headphone" share none. This table is domain-specific
# on purpose: it covers the vocabulary that actually recurs in HIS notes, so it is exact
# rather than a dictionary's guess. Expansion is query-side only — the index stays clean.
ALIAS_GROUPS = [
    ("mic microphone mics מיקרופון מיקרופונים"),
    ("headphone headphones headset earphones אוזניות אוזנייה xm4"),
    ("audio sound שמע אודיו קול צליל"),
    ("music מוזיקה מוסיקה שיר שירים"),
    ("memory remember זיכרון זכרון לזכור"),
    ("brain מוח"),
    ("model models מודל מודלים"),
    ("server servers שרת שרתים"),
    ("router נתב ראוטר"),
    ("fleet צי"),
    ("port ports פורט פורטים"),
    ("reboot restart ריבוט אתחול הפעלה"),
    ("project projects פרויקט פרוייקט פרויקטים"),
    ("task tasks משימה משימות"),
    ("queue תור"),
    ("search חיפוש לחפש"),
    ("file files קובץ קבצים"),
    ("code קוד"),
    ("test tests בדיקה בדיקות מבחן"),
    ("bug error שגיאה באג תקלה"),
    ("fix fixed תיקון לתקן"),
    ("speed fast מהירות מהיר"),
    ("token tokens טוקן טוקנים אסימון"),
    ("hebrew עברית"),
    ("english אנגלית"),
    ("phone טלפון נייד"),
    ("camera מצלמה"),
    ("screen display מסך"),
    ("key password מפתח סיסמה סיסמא"),
    ("install setup התקנה להתקין"),
    ("printer print מדפסת הדפסה"),
    ("drone רחפן"),
    ("robot רובוט"),
    ("guitar גיטרה"),
    ("movie video סרט וידאו"),
    ("sister אחות אלמה alma"),
    ("grandmother סבתא"),
    ("foot leg רגל"),
    ("money price cost כסף מחיר עלות"),
    ("permission הרשאה הרשאות"),
    ("agent agents סוכן סוכנים"),
    ("council ramchat מועצה"),
    ("rule rules law חוק כלל כללים"),
    # Transliterated project names — "מה זה קשב" could not reach project_keshev_mic.md,
    # because the project is spelled in Latin everywhere except in his speech.
    ("keshev קשב"),
    ("alma almaware אלמה אלמוור"),
    ("eran ערן"),
    # Iddo named the four DGX Sparks 2026-08-17. Both names are correct and mean the same
    # thing, so a search for either has to reach every fleet document written before them.
    ("4d 80k dgx spark sparks fleet צי דיגיאיקס"),
    ("darwish דרוויש דרויש"),
    ("quorum קוורום"),
    ("grok גרוק"),
    ("claude clod קלוד"),
    ("codex קודקס"),
    ("gemini ג'מיני"),
    ("shiri שירי"),
    ("cnc סיאנסי"),
    ("memristor ממריסטור"),
    ("piano פסנתר"),
]

# Not all sources are equal EVIDENCE. A curated rule file is a decision; raw dictation is
# a moment. Without this, 29 long chatty voice sessions outranked every standing rule on
# any Hebrew query — measured. The prior is gentle and never zero: dictation still wins
# when it is genuinely the best match (the CFS printing complaint still ranks first).
SOURCE_PRIOR = {"claude-memory": 1.0, "keshev-b": 1.0, "captured": 1.0,
                "git-brain": 0.95, "ramchat": 0.85, "keshev": 0.7}
ALIASES = {}
for _grp in ALIAS_GROUPS:
    _words = _grp.split()
    for _w in _words:
        ALIASES.setdefault(_w, set()).update(x for x in _words if x != _w)


def tokenize(text, drop_stop=False):
    toks = []
    for m in TOKEN_RE.finditer(text.lower()):
        w = m.group(0)
        if drop_stop and w in STOP:
            continue
        toks.extend(variants(w))
    return toks


# ------------------------------------------------------------------------ frontmatter
FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)
PARA_BY_TYPE = {"project": "Projects", "feedback": "Areas", "user": "Areas",
                "reference": "Resources"}
PARA_BY_PREFIX = {"project_": "Projects", "feedback_": "Areas", "user_": "Areas",
                  "reference_": "Resources", "reminder_": "Areas", "decision": "Areas"}


def parse_note(path, raw):
    """Pull title/description/type out of a memory file however it was written.
    Three conventions coexist in this corpus; all three are read."""
    meta = {"name": "", "description": "", "type": ""}
    body = raw
    m = FM_RE.match(raw)
    if m:
        body = raw[m.end():]
        for line in m.group(1).splitlines():
            if ":" in line and not line.startswith(" "):
                k, _, v = line.partition(":")
                k, v = k.strip().lower(), v.strip().strip("'\"")
                if k in ("name", "description", "type"):
                    meta[k] = v
    if not meta["description"]:
        c = re.search(r"<!--\s*description:\s*(.*?)\s*-->", raw)
        if c:
            meta["description"] = c.group(1)
    if not meta["name"]:
        h = re.search(r"^#\s+(.+)$", body, re.M)
        meta["name"] = h.group(1).strip() if h else os.path.splitext(os.path.basename(path))[0]

    base = os.path.basename(path).lower()
    para = PARA_BY_TYPE.get(meta["type"].lower())
    if not para:
        for pre, bucket in PARA_BY_PREFIX.items():
            if base.startswith(pre):
                para = bucket
                break
    low = path.lower()
    if any(mark in low for mark in SKIP_MARKERS) or "archive" in low:
        para = "Archives"
    return meta, body, para or "Resources"


# ------------------------------------------------------------------------------ index
class Brain:
    def __init__(self):
        self.docs = []
        self.df = {}
        self.postings = {}
        self.avgdl = 1.0
        self.built_at = 0.0
        self.build_secs = 0.0
        self.skipped = {"snapshots": 0, "archives": 0, "duplicates": 0, "unreadable": 0}
        self._seen = set()
        self.lock = threading.Lock()

    # ---- ingest
    def _add(self, doc):
        # The git brain mirrors the live memory into LATEST/, so most notes exist at least
        # twice. Un-deduplicated, a duplicated note outranks a unique one and the top of
        # every result page is the same file listed twice. ROOTS puts the live memory
        # first, so first-wins keeps the authoritative copy.
        key = hash(re.sub(r"\s+", " ", doc["text"]).strip())
        if key in self._seen:
            self.skipped["duplicates"] += 1
            return
        self._seen.add(key)
        doc["id"] = len(self.docs)
        self.docs.append(doc)

    def _walk_markdown(self):
        for root, source in ROOTS:
            if not os.path.isdir(root):
                continue
            for dirpath, dirnames, filenames in os.walk(root):
                for pruned in [d for d in dirnames if d in SKIP_DIRS]:
                    if pruned == "snapshots":
                        for _, _, fs in os.walk(os.path.join(dirpath, pruned)):
                            self.skipped["snapshots"] += sum(1 for f in fs if f.endswith(".md"))
                dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
                for fn in filenames:
                    if not fn.lower().endswith(".md"):
                        continue
                    path = os.path.join(dirpath, fn)
                    try:
                        raw = open(path, encoding="utf-8", errors="replace").read()
                    except Exception:
                        self.skipped["unreadable"] += 1
                        continue
                    if not raw.strip():
                        continue
                    meta, body, para = parse_note(path, raw)
                    if para == "Archives":
                        self.skipped["archives"] += 1
                    self._add({"path": path, "source": source, "title": meta["name"],
                               "real_title": True,
                               "desc": meta["description"], "type": meta["type"],
                               "para": para, "text": body,
                               "mtime": os.path.getmtime(path)})

    def _walk_ramchat(self):
        """The council transcript. Each message is its own note — that is the unit an
        agent actually wants back, not the whole 500-message file."""
        for store in RAMCHAT_STORES:
            if not os.path.isfile(store):
                continue
            try:
                data = json.load(open(store, encoding="utf-8"))
            except Exception:
                self.skipped["unreadable"] += 1
                continue
            entries = data.get("transcript", []) if isinstance(data, dict) else data
            if not isinstance(entries, list):
                continue
            mt = os.path.getmtime(store)
            tag = os.path.basename(store)
            for i, e in enumerate(entries):
                if not isinstance(e, dict):
                    continue
                text = (e.get("text") or e.get("message") or "").strip()
                if not text:
                    continue
                who = e.get("who") or e.get("from") or "?"
                self._add({"path": "RAMCHAT/%s#%d %s @%s" % (tag, i, who, e.get("at", "")),
                           "source": "ramchat", "title": "%s — %s" % (who, text[:70]),
                           "desc": "", "type": "council", "para": "Areas",
                           "text": text, "mtime": mt})

    @staticmethod
    def _degenerate(text):
        """ASR and generation loops produce lines like 'the name of the name of the name…'.
        They are long, they match everything, and they are worthless as evidence."""
        w = text.split()
        return len(w) > 20 and len(set(w)) < max(3, len(w) / 8)

    def _walk_keshev(self):
        if not os.path.isfile(KESHEV_MANIFEST):
            return
        sessions = {}
        try:
            for line in open(KESHEV_MANIFEST, encoding="utf-8"):
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                text = (r.get("text") or "").strip()
                if not text or self._degenerate(text):
                    if text:
                        self.skipped["degenerate"] = self.skipped.get("degenerate", 0) + 1
                    continue
                sessions.setdefault(r.get("sid", "?"), []).append(
                    (r.get("ts", ""), text))
        except Exception:
            self.skipped["unreadable"] += 1
            return
        mt = os.path.getmtime(KESHEV_MANIFEST)
        for sid, rows in sessions.items():
            rows.sort()
            day = (rows[0][0] or "")[:10]
            # ~1500-char blocks so a hit lands on a passage, not a 40k-char wall
            block, size, part = [], 0, 1
            def flush(block, part):
                if not block:
                    return
                body = "\n".join("%s  %s" % (ts[11:16], t) for ts, t in block)
                # the first utterance is usually "Oh." — title on the meatiest line instead
                headline = max((t for _, t in block), key=len)
                self._add({"path": "KESHEV/%s part %d (%s)" % (sid, part, day),
                           "source": "keshev", "type": "voice", "para": "Areas",
                           "title": "קשב %s — %s" % (day, headline[:60]),
                           "desc": "%d utterances from session %s" % (len(block), sid),
                           "text": body, "mtime": mt})
            for ts, t in rows:
                block.append((ts, t))
                size += len(t)
                if size > 1500:
                    flush(block, part)
                    block, size, part = [], 0, part + 1
            flush(block, part)

    # ---- build
    def build(self):
        t0 = time.time()
        docs_before = self.docs
        self.docs, self.df, self.postings = [], {}, {}
        self.skipped = {"snapshots": 0, "archives": 0, "duplicates": 0, "unreadable": 0}
        self._seen = set()
        try:
            self._walk_markdown()
            self._walk_ramchat()
            self._walk_keshev()
        except Exception:
            self.docs = docs_before          # never leave the brain empty on a bad walk
            raise
        total_len = 0
        for d in self.docs:
            # Field weighting by repetition. Without it a long note ABOUT a rule outranks
            # the rule itself — measured: project_second_brain.md (which merely mentions
            # never-touch-audio) buried the actual audio rule and the librarian correctly
            # but uselessly answered "not in the brain". A note's title and filename are
            # what it IS; its body is what it mentions.
            # ...but only when the title IS a title. RAMCHAT and KESHEV notes take their
            # title from the first line of their own body, so weighting it there just
            # counts that body text three times and floods the ranking with chatter.
            tw = 3 if d.get("real_title") else 1
            blob = " ".join([d["title"]] * tw + [d["desc"]] * 2 +
                            [os.path.basename(d["path"])] * 2 + [d["text"]])
            toks = tokenize(blob)
            tf = {}
            for t in toks:
                tf[t] = tf.get(t, 0) + 1
            d["len"] = max(1, len(toks))
            total_len += d["len"]
            for t, n in tf.items():
                self.postings.setdefault(t, []).append((d["id"], n))
                self.df[t] = self.df.get(t, 0) + 1
        self.avgdl = total_len / max(1, len(self.docs))
        self.built_at = time.time()
        self.build_secs = self.built_at - t0
        return len(self.docs)

    # ---- retrieve
    def search(self, query, k=8, k1=1.5, b=0.75):
        q = tokenize(query, drop_stop=True) or tokenize(query)
        if not q:
            return []
        # cross-language expansion, at 0.6 weight so a literal match still wins
        weights = {t: 1.0 for t in q}
        for t in list(q):
            for alt in ALIASES.get(t, ()):
                for v in variants(alt):
                    weights.setdefault(v, 0.6)
        N = len(self.docs)
        scores = {}
        for t, w in weights.items():
            post = self.postings.get(t)
            if not post:
                continue
            idf = math.log(1 + (N - len(post) + 0.5) / (len(post) + 0.5))
            for did, freq in post:
                dl = self.docs[did]["len"]
                denom = freq + k1 * (1 - b + b * dl / self.avgdl)
                scores[did] = scores.get(did, 0.0) + w * idf * freq * (k1 + 1) / denom
        # A recent note about a live system beats a year-old one on the same words — but
        # gently. At 0.25 today's notes swamped standing rules, which are old BECAUSE they
        # are settled. 0.12 breaks ties without rewriting the ranking.
        now = time.time()
        for did in scores:
            age_days = (now - self.docs[did]["mtime"]) / 86400.0
            scores[did] *= 1.0 + 0.12 * math.exp(-age_days / 30.0)
            scores[did] *= SOURCE_PRIOR.get(self.docs[did]["source"], 1.0)
        top = sorted(scores.items(), key=lambda kv: -kv[1])[:k]
        out = []
        for did, sc in top:
            d = self.docs[did]
            out.append({"path": d["path"], "source": d["source"], "title": d["title"],
                        "desc": d["desc"], "para": d["para"], "score": round(sc, 3),
                        "mtime": datetime.fromtimestamp(d["mtime"]).strftime("%Y-%m-%d"),
                        "snippet": self._snippet(d["text"], q),
                        "text": d["text"]})
        return out

    @staticmethod
    def _snippet(text, qtoks, width=320):
        low = text.lower()
        best, pos = 0, 0
        for t in set(qtoks):
            i = low.find(t)
            if i >= 0:
                window = low[max(0, i - 60):i + 260]
                hits = sum(window.count(x) for x in set(qtoks))
                if hits > best:
                    best, pos = hits, i
        start = max(0, pos - 60)
        s = text[start:start + width].replace("\n", " ").strip()
        return ("…" if start else "") + s + ("…" if start + width < len(text) else "")


BRAIN = Brain()

# --------------------------------------------------------------------------- librarian
SYSTEM = """You are the librarian of Iddo's second brain. You are NOT a general assistant.

ABSOLUTE RULES:
1. Answer ONLY from the numbered NOTES below. Your own knowledge is not evidence here.
2. Cite the note number [1], [2] … after every claim you make.
3. If the notes do not contain the answer, say exactly: "לא נמצא במוח" (not in the brain)
   and then name the closest thing the notes DO contain. Never fill the gap yourself.
4. If two notes disagree, say so and cite both. Contradictions are the most valuable
   thing you can surface — do not smooth them over.
5. Answer in the language of the question. Iddo writes Hebrew and English; match him.
6. Be short. He is usually reading this on a phone.
"""


# ------------------------------------------------------------------ the four-box panel
# Iddo's order was four DIFFERENT families so their errors are uncorrelated. "best" mode
# is what that diversity is FOR. Each box does the job the 2026-08-17 grading proved it is
# actually good at — not the job its marketing implies:
#   eran4 gpt-oss   DRAFTS   — only one that raised on a violated assumption
#   eran1 qwen      AUDITS   — fastest (48 tok/s), so a full re-read of every citation is cheap
#   eran2 glm       AUDITS   — second, independent auditor; loud failures, uncorrelated with qwen
#   eran3 nemotron  HEBREW   — the ONLY one of the four that passed the Hebrew test
# Two auditors, not one: a single verifier that shares the drafter's blind spot verifies
# nothing. They are asked to REFUTE, and they run concurrently so the cost is one round.
ROLE_DRAFT = "gpt-oss-120b"
ROLE_AUDIT = ["qwen3-coder-next-fp8", "glm-4.7-flash"]
ROLE_HEBREW = "nemotron-3-super"

AUDIT_SYSTEM = """You audit citations. You are shown NOTES and a DRAFT ANSWER that cites them as [1], [2]…

For every claim in the draft, check the cited note ACTUALLY says it. Assume the draft is
wrong until the note proves otherwise. You are not here to be agreeable.

Reply with nothing but JSON:
{"unsupported": ["<the exact claim>", ...], "verdict": "ok" | "problems"}
Empty list and "ok" if every claim checks out."""

HEBREW_SYSTEM = """אתה כותב את התשובה הסופית בעברית תקנית וטבעית.

מקבל טיוטה שכבר אומתה. אל תוסיף שום עובדה שאין בטיוטה, אל תסיר ציטוט [n], ואל תשנה מספרים.
רק תנסח בעברית טובה. אם הטיוטה אומרת "לא נמצא במוח" — תשאיר את זה."""


def call_model(model, system, user, max_tokens=1200, timeout=240):
    payload = {"model": model,
               "messages": [{"role": "system", "content": system},
                            {"role": "user", "content": user}],
               "max_tokens": max_tokens, "temperature": 0}
    if model.startswith("glm"):
        payload["chat_template_kwargs"] = {"enable_thinking": False}  # or it never terminates
    req = urllib.request.Request(FLEET_URL, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8"))
    msg = data["choices"][0]["message"]
    out = (msg.get("content") or "").strip()
    if "</think>" in out:                      # nemotron leaks CoT before the marker
        out = out.split("</think>", 1)[1].strip()
    return out


def notes_block(hits, limit=1600):
    return "\n\n---\n\n".join(
        "[%d] %s  (%s, %s)\n%s\n%s" % (i, h["title"], h["source"], h["mtime"],
                                       h["path"], h["text"][:limit])
        for i, h in enumerate(hits, 1))


def ask_panel(question, hits, want_hebrew=None):
    """draft → two concurrent auditors → optional Hebrew pass. Returns (answer, trace)."""
    trace, t0 = [], time.time()
    notes = notes_block(hits)

    t = time.time()
    draft = call_model(ROLE_DRAFT, SYSTEM, "NOTES:\n\n" + notes + "\n\nQUESTION: " + question)
    trace.append({"role": "draft", "model": ROLE_DRAFT, "seconds": round(time.time() - t, 1)})

    audit_user = "NOTES:\n\n" + notes + "\n\nDRAFT ANSWER:\n" + draft
    results = {}

    def run_audit(m):
        t1 = time.time()
        try:
            raw = call_model(m, AUDIT_SYSTEM, audit_user, max_tokens=700)
            js = re.search(r"\{.*\}", raw, re.S)
            results[m] = json.loads(js.group(0)) if js else {"verdict": "unparsed"}
        except Exception as e:
            results[m] = {"verdict": "unavailable", "error": repr(e)}
        results[m]["seconds"] = round(time.time() - t1, 1)

    threads = [threading.Thread(target=run_audit, args=(m,)) for m in ROLE_AUDIT]
    for th in threads:
        th.start()
    for th in threads:
        th.join(timeout=240)
    for m in ROLE_AUDIT:
        r = results.get(m, {"verdict": "timeout"})
        trace.append({"role": "audit", "model": m, "verdict": r.get("verdict"),
                      "unsupported": r.get("unsupported", []), "seconds": r.get("seconds")})

    # only a claim BOTH auditors reject is treated as unsupported — one dissent is noise
    flagged = []
    lists = [set(results.get(m, {}).get("unsupported") or []) for m in ROLE_AUDIT]
    if len(lists) == 2:
        flagged = sorted(lists[0] & lists[1])
    answer = draft
    if flagged:
        answer += ("\n\n⚠️ שני מבקרים עצמאיים לא מצאו סימוכין לטענות הבאות:\n"
                   + "\n".join("• " + c for c in flagged))

    if want_hebrew is None:
        want_hebrew = is_hebrew(question)
    if want_hebrew:
        t = time.time()
        try:
            answer = call_model(ROLE_HEBREW, HEBREW_SYSTEM, "טיוטה:\n" + answer,
                                max_tokens=1400)
            trace.append({"role": "hebrew", "model": ROLE_HEBREW,
                          "seconds": round(time.time() - t, 1)})
        except Exception as e:
            trace.append({"role": "hebrew", "model": ROLE_HEBREW, "error": repr(e)})
    return answer, {"steps": trace, "total_seconds": round(time.time() - t0, 1),
                    "flagged": flagged}


def ask_librarian(question, hits, model=LIBRARIAN, max_tokens=1200, timeout=180):
    notes = []
    for i, h in enumerate(hits, 1):
        body = h["text"][:1600]
        notes.append("[%d] %s  (%s, %s)\n%s\n%s" %
                     (i, h["title"], h["source"], h["mtime"], h["path"], body))
    user = "NOTES:\n\n" + "\n\n---\n\n".join(notes) + "\n\nQUESTION: " + question
    payload = {"model": model,
               "messages": [{"role": "system", "content": SYSTEM},
                            {"role": "user", "content": user}],
               "max_tokens": max_tokens, "temperature": 0}
    req = urllib.request.Request(FLEET_URL, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8"))
    msg = data["choices"][0]["message"]
    answer = (msg.get("content") or "").strip()
    # nemotron leaks its chain-of-thought into content before a </think> marker
    if "</think>" in answer:
        answer = answer.split("</think>", 1)[1].strip()
    if not answer and msg.get("reasoning_content"):
        answer = "(המודל נגמר לו התקציב באמצע החשיבה — נסה שוב)"
    return answer, round(time.time() - t0, 2)


# ----------------------------------------------------------------------------- capture
def capture(name, description, mtype, body, topic=None, do_git=False):
    """Write a new fact into the LIVE memory dir, in the convention already in use, and
    add the one-line MEMORY.md pointer. Optionally commit+tag in the git brain using
    Iddo's own brain/<topic>/<YYYYMMDD> convention. NEVER pushes."""
    slug = re.sub(r"[^a-z0-9\-]+", "-", name.lower()).strip("-") or "note"
    path = os.path.join(LIVE_MEMORY, slug + ".md")
    if os.path.exists(path):
        return {"ok": False, "error": "already exists: " + path}
    doc = ("---\nname: %s\ndescription: %s\nmetadata:\n  type: %s\n---\n\n%s\n"
           % (slug, description, mtype or "reference", body.strip()))
    os.makedirs(LIVE_MEMORY, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)
    index = os.path.join(LIVE_MEMORY, "MEMORY.md")
    line = "- [%s](%s.md) — %s\n" % (name, slug, description)
    with open(index, "a", encoding="utf-8") as f:
        f.write(line)
    res = {"ok": True, "path": path, "index_line": line.strip()}
    if do_git and topic:
        tag = "brain/%s/%s" % (topic, date.today().strftime("%Y%m%d"))
        try:
            for cmd in (["git", "add", "-A"],
                        ["git", "commit", "-m", "brain: %s" % description],
                        ["git", "tag", tag]):
                subprocess.run(cmd, cwd=GIT_BRAIN, check=True,
                               capture_output=True, timeout=60)
            res["tag"] = tag
            res["note"] = "committed and tagged locally — NOT pushed"
        except Exception as e:
            res["git_error"] = repr(e)
    return res


# ---------------------------------------------------------------------------- web page
PAGE = """<!doctype html><html lang="he" dir="rtl"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>מוח שני</title><style>
:root{color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:#0d0f12;color:#e8e6e3;
 font:16px/1.65 -apple-system,"Segoe UI",Roboto,"Helvetica Neue",sans-serif;
 padding:22px;max-width:820px;margin-inline:auto}
h1{font-size:19px;font-weight:600;letter-spacing:.02em;margin:0 0 2px}
.sub{color:#7d848d;font-size:13px;margin-bottom:20px}
form{display:flex;gap:8px;margin-bottom:8px}
input{flex:1;background:#16191e;border:1px solid #272c34;color:#e8e6e3;
 border-radius:9px;padding:12px 14px;font-size:16px;outline:none}
input:focus{border-color:#3f6ea8}
button{background:#2b6cb0;border:0;color:#fff;border-radius:9px;padding:12px 18px;
 font-size:15px;cursor:pointer;white-space:nowrap}
button.ghost{background:#1b1f26;color:#aeb4bc}
#out{margin-top:20px}
.answer{background:#12161b;border:1px solid #232830;border-inline-start:3px solid #2b6cb0;
 border-radius:10px;padding:16px 18px;white-space:pre-wrap;margin-bottom:22px}
.hit{border-top:1px solid #1e222a;padding:13px 2px}
.hit b{font-weight:600;font-size:15px}
.meta{color:#6f767f;font-size:12px;margin:3px 0 6px}
.snip{color:#a8aeb6;font-size:14px}
.tag{display:inline-block;background:#1b2029;color:#7f8894;border-radius:5px;
 padding:1px 7px;font-size:11px;margin-inline-start:6px}
.spin{color:#6f767f}
</style>
<h1>מוח שני</h1>
<div class="sub" id="sub">—</div>
<form onsubmit="go(event,1)">
 <input id="q" placeholder="מה אתה מחפש?" autofocus>
 <button type="submit">שאל</button>
 <button type="button" class="ghost" onclick="go(event,0)">חפש בלבד</button>
</form>
<div id="out"></div>
<script>
fetch('/stats').then(r=>r.json()).then(s=>{
 document.getElementById('sub').textContent =
  s.documents+' פתקים · '+Object.keys(s.by_source).map(k=>k+' '+s.by_source[k]).join(' · ');
});
async function go(e,useModel){
 e.preventDefault();
 const q=document.getElementById('q').value.trim(); if(!q)return;
 const out=document.getElementById('out');
 out.innerHTML='<div class="spin">'+(useModel?'הספרן קורא…':'מחפש…')+'</div>';
 try{
  let r;
  if(useModel){ r=await fetch('/ask',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({q:q,k:8})}); }
  else { r=await fetch('/search?q='+encodeURIComponent(q)+'&k=12'); }
  const d=await r.json();
  let h='';
  if(d.answer) h+='<div class="answer">'+esc(d.answer)+'</div>';
  for(const s of (d.hits||d.results||[])){
   h+='<div class="hit"><b>'+esc(s.title)+'</b><span class="tag">'+esc(s.para)+'</span>'+
      '<div class="meta">'+esc(s.source)+' · '+esc(s.mtime)+' · '+s.score+' · '+esc(s.path)+'</div>'+
      '<div class="snip">'+esc(s.snippet)+'</div></div>';
  }
  out.innerHTML=h||'<div class="spin">אין תוצאות</div>';
 }catch(err){ out.innerHTML='<div class="spin">שגיאה: '+esc(String(err))+'</div>'; }
}
function esc(s){const d=document.createElement('div');d.textContent=s==null?'':s;return d.innerHTML}
</script></html>"""


# ------------------------------------------------------------------------------ server
TOKEN = None


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False, indent=1).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def _authed(self):
        if not TOKEN:
            return True
        got = self.headers.get("X-Brain-Token") or ""
        if got == TOKEN or ("token=" + TOKEN) in (self.path or ""):
            return True
        self._send(401, {"error": "token required"})
        return False

    def do_GET(self):
        if not self._authed():
            return
        path, _, qs = self.path.partition("?")
        params = {}
        for part in qs.split("&"):
            if "=" in part:
                k, _, v = part.partition("=")
                params[k] = urllib.parse.unquote_plus(v)
        if path.rstrip("/") in ("", "/"):
            return self._send(200, PAGE, "text/html; charset=utf-8")
        if path == "/stats":
            with BRAIN.lock:
                by_source, by_para = {}, {}
                for d in BRAIN.docs:
                    by_source[d["source"]] = by_source.get(d["source"], 0) + 1
                    by_para[d["para"]] = by_para.get(d["para"], 0) + 1
                return self._send(200, {
                    "documents": len(BRAIN.docs), "terms": len(BRAIN.postings),
                    "by_source": by_source, "by_para": by_para,
                    "skipped": BRAIN.skipped,
                    "built_at": datetime.fromtimestamp(BRAIN.built_at).strftime("%Y-%m-%d %H:%M:%S"),
                    "build_secs": round(BRAIN.build_secs, 2),
                    "librarian": LIBRARIAN, "fleet": FLEET_URL})
        if path == "/search":
            q = params.get("q", "")
            k = int(params.get("k", 8))
            with BRAIN.lock:
                hits = BRAIN.search(q, k)
            for h in hits:
                h.pop("text", None)
            return self._send(200, {"query": q, "hits": hits})
        if path == "/health":
            return self._send(200, {"ok": True, "documents": len(BRAIN.docs)})
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self._authed():
            return
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
        except Exception:
            return self._send(400, {"error": "bad json"})
        path = self.path.partition("?")[0]

        if path == "/ask":
            q = (body.get("q") or "").strip()
            if not q:
                return self._send(400, {"error": "q required"})
            k = int(body.get("k", 8))
            with BRAIN.lock:
                hits = BRAIN.search(q, k)
            if not hits:
                return self._send(200, {"query": q, "answer": "לא נמצא במוח — אין פתק שתואם.",
                                        "hits": []})
            mode = body.get("mode", "fast")
            panel = None
            try:
                if mode == "best":
                    answer, panel = ask_panel(q, hits)
                    secs = panel["total_seconds"]
                else:
                    answer, secs = ask_librarian(q, hits, body.get("model", LIBRARIAN),
                                                 int(body.get("max_tokens", 1200)))
            except Exception as e:
                answer, secs = ("הספרן לא זמין (%r) — התוצאות למטה הן חיפוש בלבד." % e), 0
            for h in hits:
                h.pop("text", None)
            out = {"query": q, "answer": answer, "seconds": secs, "mode": mode,
                   "model": body.get("model", LIBRARIAN), "hits": hits}
            if panel:
                out["panel"] = panel
            return self._send(200, out)

        if path == "/capture":
            need = ("name", "description", "body")
            if not all(body.get(x) for x in need):
                return self._send(400, {"error": "need " + ", ".join(need)})
            res = capture(body["name"], body["description"], body.get("type", "reference"),
                          body["body"], body.get("topic"), bool(body.get("git")))
            if res.get("ok"):
                threading.Thread(target=lambda: BRAIN.build(), daemon=True).start()
            return self._send(200 if res.get("ok") else 409, res)

        if path == "/reindex":
            with BRAIN.lock:
                n = BRAIN.build()
            return self._send(200, {"documents": n, "seconds": round(BRAIN.build_secs, 2)})

        return self._send(404, {"error": "not found"})


class S(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 128


def use_corpus(root):
    """Run against a synced corpus instead of the Windows originals — this is what lets
    the brain live on the fleet instead of on a laptop that walks out of the house."""
    global ROOTS, RAMCHAT_STORES, KESHEV_MANIFEST, LIVE_MEMORY, GIT_BRAIN
    ROOTS = [(os.path.join(root, "claude-memory"), "claude-memory"),
             (os.path.join(root, "git-brain"), "git-brain"),
             (os.path.join(root, "keshev-b"), "keshev-b"),
             (os.path.join(root, "captured"), "captured")]
    RAMCHAT_STORES = [os.path.join(root, "ramchat", "ramchat_session.json"),
                      os.path.join(root, "ramchat", "current_council.json")]
    KESHEV_MANIFEST = os.path.join(root, "keshev", "manifest.jsonl")
    # anything captured here lands in captured/ and is pulled back to Windows by sync.sh
    LIVE_MEMORY = os.path.join(root, "captured")
    GIT_BRAIN = root


def main():
    global TOKEN, FLEET_URL, LIBRARIAN
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8960)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--token", default=os.environ.get("BRAIN_TOKEN"))
    ap.add_argument("--corpus", help="run off a synced corpus dir (for the DGX fleet)")
    ap.add_argument("--fleet", default=FLEET_URL)
    ap.add_argument("--librarian", default=LIBRARIAN)
    a = ap.parse_args()
    TOKEN = a.token
    FLEET_URL, LIBRARIAN = a.fleet, a.librarian
    if a.corpus:
        use_corpus(a.corpus)
    if a.host not in ("127.0.0.1", "localhost") and not TOKEN:
        sys.exit("REFUSING TO START: --host %s exposes Iddo's entire private memory.\n"
                 "Off-loopback requires --token (or BRAIN_TOKEN in the environment)." % a.host)
    print("indexing…", flush=True)
    n = BRAIN.build()
    print("indexed %d documents, %d terms, in %.2fs (skipped: %s)"
          % (n, len(BRAIN.postings), BRAIN.build_secs, BRAIN.skipped), flush=True)
    print("second brain on http://%s:%d  librarian=%s" % (a.host, a.port, LIBRARIAN), flush=True)
    S((a.host, a.port), H).serve_forever()


if __name__ == "__main__":
    main()
