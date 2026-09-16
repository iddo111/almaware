#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TASTE THE CODER v2 -- a real persistent-memory, RAG-grounded chat page for
Qwen3-Coder-480B (running live across eran2+eran3+eran4 since 2026-09-08).

v1 (18:30 09-08) was a single prompt-box -> one /v1/completions call, no memory.
Iddo's order 2026-09-09 01:38: "תחבר את הקודר הענק למוח השני שלך וכל הפרויקטים
והסטנדרד של עלמהוור" + "ותוודא שיש לקודר הזה זיכרון". v2 adds:

  1. Persistent conversation memory -- D:\\CLAUDE\\qwen480-taste\\conversations\\
     default.jsonl, one JSON object per line (role/content/ts). Survives closing
     the tab AND restarting this process. Switched the door from raw
     /v1/completions to /v1/chat/completions (vLLM applies the chat template;
     verified live both endpoints work, chat/completions is the one that keeps
     multi-turn context correctly -- tested 2026-09-09).
  2. RAG grounding every turn, before the model sees the message:
       a. ALMA-RECALL   GET http://127.0.0.1:8794/api/search?q=...&limit=N
       b. ALMAWARE STANDARD  keyword match over the 184 ALMA-<AREA>-<nnn>
          requirements + section headers in D:\\CLAUDE\\_deliverables\\
          almaware-standard\\ALMAWARE-STANDARD-v0.1-DRAFT-20260908.md
       c. Project grep -- only when the message names one of D:\\CLAUDE's own
          top-level directories, a bounded, time-boxed walk of just that
          subtree (best-effort, not a full index).
     All three are logged to stderr AND written to conversations/
     default.context.jsonl AND returned to the browser (collapsible <details>
     under each reply) -- inspectable, never a black box.
  3. Chat-thread UI in the same warm/bright palette as v1, RTL Hebrew body text
     with LTR monospace code fences.

NOTE (xgrammar scar, memory project_qwen480_pipeline.md): this vLLM build's
tool-calling is BROKEN. This client sends plain chat messages, no `tools` /
`tool_choice` ever -- verified live 2026-09-09 that plain chat/completions
works cleanly without them.

Bind: 127.0.0.1 only. No password on the door (Iddo's explicit order 09-08,
tailnet-only reach). Same port :8875, same Startup shortcut
(ALMA-Taste480-8875.lnk), same pythonw/BELOW_NORMAL launch pattern.
"""
import json
import os
import re
import subprocess
import sys
import time
import threading
import traceback
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ROOT CAUSE of the long-standing "pythonw-hidden launch binds the port but every
# request gets an empty reply" mystery (recurred 3x this session, 2026-09-08/09):
# pythonw.exe has NO console, so sys.stdout/sys.stderr are None unless redirected.
# The very first print() (the startup banner, below) then raises
# AttributeError: 'NoneType' object has no attribute 'write' -- which kills the
# process right after ThreadingHTTPServer() binds the socket (hence still LISTENING
# in netstat) but before serve_forever() ever runs its accept loop. Fix: redirect to
# a real log file BEFORE any print() can fire, whenever the streams are None.
if sys.stdout is None or sys.stderr is None:
    _logf = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "taste480.log"),
                 "a", encoding="utf-8", errors="replace", buffering=1)
    sys.stdout = _logf
    sys.stderr = _logf

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PORT = 8875
DOOR = "https://<tailnet-host>:8443/v1/chat/completions"
MODEL = "qwen3-coder-480b"

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONV_DIR = os.path.join(APP_DIR, "conversations")
CONV_PATH = os.path.join(CONV_DIR, "default.jsonl")
CONTEXT_LOG_PATH = os.path.join(CONV_DIR, "default.context.jsonl")
os.makedirs(CONV_DIR, exist_ok=True)

RECALL_URL = "http://127.0.0.1:8794/api/search"
STANDARD_PATH = os.path.join(
    "D:" + os.sep, "CLAUDE", "_deliverables", "almaware-standard",
    "ALMAWARE-STANDARD-v0.1-DRAFT-20260908.md")
PROJECT_ROOT = os.path.join("D:" + os.sep, "CLAUDE")

# RAMCHAT -- the team coordination council (other AI agents/sessions on this
# machine). ramlink.py is the CLI door (D:\CLAUDE\RAMCHAT\HANDOUT-...); it is
# invoked as a subprocess, never imported, so this file stays decoupled from
# RAMCHAT's own module layout. RULES.md rule #1 is "read RAMCHAT before you
# build anything" -- this model has no tool-calling to run that check itself,
# so the check is run FOR it, every turn, the same way ALMA-RECALL is.
RAMCHAT_DIR = os.path.join("D:" + os.sep, "CLAUDE", "RAMCHAT")
RAMLINK_PATH = os.path.join(RAMCHAT_DIR, "ramlink.py")
RAMCHAT_TAIL = 20
RAMCHAT_CACHE_TTL = 15  # seconds -- RAMCHAT itself only changes when an agent
                        # posts; this just stops several turns in a row from
                        # each paying a fresh `python ramlink.py` subprocess.

# QUORUM -- the multi-AI Talmudic-debate arena (:8099). Read-only: GET /api/rooms
# + GET /api/rooms/<id> list and fetch past debate/discussion rooms. This model
# cannot start a debate itself (no tool-calling -- see CONTEXT.md for how Iddo
# does it), so the connection here is retrieval of what was already argued,
# same shape as ALMA-RECALL. QUORUM listens on loopback+tailnet only and its
# master ENABLED gate only affects /debate (reaching models) -- reading rooms
# works regardless of that gate, and failing to reach it here is routine, not
# an error worth surfacing mid-turn.
QUORUM_ROOMS_URL = "http://127.0.0.1:8099/api/rooms"
QUORUM_ROOM_URL_FMT = "http://127.0.0.1:8099/api/rooms/%s"
PROJECT_EXCLUDE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv",
                        "dist", "build", ".cache", "recall-index"}
PROJECT_TEXT_EXTS = (".md", ".py", ".js", ".ts", ".json", ".txt", ".ps1",
                     ".cmd", ".yaml", ".yml")

MAX_PROMPT_CHARS = 55000  # history+user budget; the always-on standard compact (~30KB) now
                          # eats real system-prompt budget out of the 32768-token window --
                          # reduced from 90000 to leave room for it (measured 2026-09-09 05:20)

# Rolling conversation SUMMARY -- Iddo's ask 2026-09-09 ~05:30: "increase the
# context" without touching vLLM's --max-model-len (real infra risk on an
# already-fragile-tonight cluster, see project_qwen480_pipeline.md -- a bump
# needs docker rm -f + fresh ray start across eran2/3/4, not attempted here).
# Standard software-side fix instead: before build_messages() below would
# silently drop old turns to stay under MAX_PROMPT_CHARS, fold them into a
# persistent running summary (one small extra call to the same door) so the
# FACT survives even though the raw text doesn't. Not free: costs one short
# summarizer call -- a few seconds and up to SUMMARY_MAX_TOKENS of generation
# -- exactly when a turn would otherwise have been dropped.
SUMMARY_MAX_TOKENS = 900
SUMMARY_MAX_INPUT_CHARS = 40000  # cap on (existing summary + newly-dropped turns)
                                 # fed to the summarizer call, so THAT call also
                                 # comfortably fits the 32768-token window

conv_lock = threading.Lock()
_ramchat_cache = {"ts": 0.0, "msgs": []}
_ramchat_cache_lock = threading.Lock()

# ----------------------------------------------------------------------------
# Conversation persistence (the literal ask: close the tab, reopen, it knows)
# ----------------------------------------------------------------------------

def load_history():
    hist = []
    if os.path.isfile(CONV_PATH):
        with open(CONV_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    hist.append(json.loads(line))
                except Exception:
                    continue
    return hist


def append_history(role, content, extra=None):
    rec = {"role": role, "content": content,
           "ts": datetime.now(timezone.utc).isoformat()}
    if extra:
        rec.update(extra)
    with conv_lock:
        with open(CONV_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


# ----------------------------------------------------------------------------
# Rolling conversation SUMMARY -- the "special memory" (see SUMMARY_MAX_TOKENS
# comment above). Persisted next to <id>.jsonl as <id>.summary.txt (the memory
# text itself, human-readable on purpose) + a tiny <id>.summary.meta.json
# sidecar that just records the ts of the newest history message already
# folded in, so a restart resumes instead of re-summarizing from scratch and
# a later turn doesn't re-fold turns that are already accounted for.
# ----------------------------------------------------------------------------

def summary_path(conv_id):
    return os.path.join(CONV_DIR, conv_id + ".summary.txt")


def summary_meta_path(conv_id):
    return os.path.join(CONV_DIR, conv_id + ".summary.meta.json")


def load_summary(conv_id):
    """(summary_text, through_ts). through_ts == '' means nothing folded in yet."""
    text = ""
    through_ts = ""
    try:
        with open(summary_path(conv_id), encoding="utf-8") as f:
            text = f.read().strip()
    except OSError:
        pass
    try:
        with open(summary_meta_path(conv_id), encoding="utf-8") as f:
            through_ts = (json.load(f) or {}).get("through_ts") or ""
    except (OSError, ValueError):
        pass
    return text, through_ts


def save_summary(conv_id, text, through_ts):
    with conv_lock:
        with open(summary_path(conv_id), "w", encoding="utf-8") as f:
            f.write((text or "").strip() + "\n")
        tmp = summary_meta_path(conv_id) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"through_ts": through_ts,
                       "updated": datetime.now(timezone.utc).isoformat()}, f)
        os.replace(tmp, summary_meta_path(conv_id))


SUMMARY_SYSTEM = (
    "You maintain a running MEMORY of an ongoing chat between Iddo and an AI coding "
    "assistant. This exists only because the raw conversation has grown past what "
    "fits in the model's fixed context window. You are given the memory so far (may "
    "be empty) and the next block of older turns that are about to be dropped from "
    "the raw window. Write the UPDATED memory: merge the new block into the existing "
    "memory in your own words -- dense, factual, third person. Keep names, decisions, "
    "file paths, numbers, specific facts, and unresolved questions -- anything a "
    "later turn might refer back to. Drop small talk and anything already superseded. "
    "Target under roughly 350 words. Output ONLY the updated memory text -- no "
    "preamble, no \"Here is the summary\"."
)


def _format_turns_for_summary(turns):
    lines = []
    for h in turns:
        who = "Iddo" if h.get("role") == "user" else "Assistant"
        lines.append("[%s] %s" % (who, (h.get("content") or "")[:2500]))
    return "\n\n".join(lines)


def summarize_dropped_turns(existing_summary, turns, timeout=120):
    """Fold `turns` (oldest..newest, about to be dropped from the raw window)
    into `existing_summary` with one small call to the same door. Returns the
    updated text, or the unchanged existing_summary if the call fails --
    losing just this update on a transient error beats losing the whole
    memory or blocking the user's real turn indefinitely."""
    block = _format_turns_for_summary(turns)
    combined_len = len(existing_summary) + len(block)
    if combined_len > SUMMARY_MAX_INPUT_CHARS:
        # keep the existing memory intact (it is already compressed); trim the
        # freshly-dropped block, favouring its more recent half
        overflow = combined_len - SUMMARY_MAX_INPUT_CHARS
        block = block[overflow:] if overflow < len(block) else block[-2000:]
    user_msg = (
        "EXISTING MEMORY (may be empty):\n%s\n\n"
        "NEW OLDER TURNS TO FOLD IN, oldest to newest (about to be dropped from the "
        "raw window):\n%s\n\nWrite the updated memory now."
        % (existing_summary or "(none yet)", block)
    )
    messages = [{"role": "system", "content": SUMMARY_SYSTEM},
                {"role": "user", "content": user_msg}]
    try:
        result = call_model(messages, max_tokens=SUMMARY_MAX_TOKENS, temperature=0.2,
                            timeout=timeout)
        choice = (result.get("choices") or [{}])[0]
        text = ((choice.get("message") or {}).get("content") or "").strip()
        return text or existing_summary
    except Exception as e:
        print("[taste480] WARN summary call failed, keeping old memory: %s" % e,
              file=sys.stderr)
        return existing_summary


# ----------------------------------------------------------------------------
# Retrieval: ALMA-RECALL (the "second brain")
# ----------------------------------------------------------------------------

def search_recall(query, limit=4, timeout=4):
    try:
        url = RECALL_URL + "?" + urllib.parse.urlencode({"q": query, "limit": limit})
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        hits = data.get("hits") or []
        out = []
        for h in hits[:limit]:
            if not isinstance(h, dict) or "error" in h:
                continue
            snip = re.sub(r"</?mark>", "", h.get("snip") or "")
            out.append({
                "source": h.get("source") or "?",
                "title": (h.get("title") or "")[:140],
                "ts": (h.get("ts") or h.get("started") or "")[:16],
                "snip": snip[:280],
            })
        return out
    except Exception as e:
        print("[taste480] WARN recall search failed: %s" % e, file=sys.stderr)
        return []


# ----------------------------------------------------------------------------
# Retrieval: RAMCHAT (the team coordination council -- "before building
# anything, check RAMCHAT", RULES.md rule #1, now run automatically because
# this model can't run `ramlink.py` itself)
# ----------------------------------------------------------------------------

def _ramchat_transcript(tail=RAMCHAT_TAIL, timeout=6):
    """The last `tail` RAMCHAT messages, via `ramlink.py read --tail N --json`
    (the exact CLI door every other agent uses). Cached for RAMCHAT_CACHE_TTL
    seconds so a burst of turns doesn't each pay a fresh subprocess spawn."""
    now = time.time()
    with _ramchat_cache_lock:
        if now - _ramchat_cache["ts"] < RAMCHAT_CACHE_TTL:
            return _ramchat_cache["msgs"]
    msgs = []
    try:
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"  # RAMCHAT is full of Hebrew; cp1252 crashes
        proc = subprocess.run(
            [sys.executable, RAMLINK_PATH, "read", "--tail", str(tail), "--json"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=env, timeout=timeout, cwd=RAMCHAT_DIR)
        data = json.loads(proc.stdout or "{}")
        msgs = data.get("transcript") or []
    except Exception as e:
        print("[taste480] WARN ramlink read failed: %s" % e, file=sys.stderr)
        msgs = []
    with _ramchat_cache_lock:
        _ramchat_cache["ts"] = now
        _ramchat_cache["msgs"] = msgs
    return msgs


def search_ramchat(query, limit=4):
    """Keyword-match over the RAMCHAT transcript, same scoring shape as
    search_standard below -- so the coder can see what other agents/sessions
    on this machine are doing or have already decided, and not suggest
    something already built or already rejected."""
    tokens = tokenize(query)
    if not tokens:
        return []
    msgs = _ramchat_transcript()
    if not msgs:
        return []
    scored = []
    for m in msgs:
        text = m.get("text") or ""
        s = _score(tokens, text) + _score(tokens, m.get("who") or "")
        if s > 0:
            scored.append((s, m))
    scored.sort(key=lambda x: -x[0])
    return [{"who": m.get("who") or "?", "at": m.get("at") or "",
            "text": (m.get("text") or "")[:320]} for _s, m in scored[:limit]]


# ----------------------------------------------------------------------------
# Retrieval: the ALMAWARE STANDARD -- keyword match, not a full 900-line dump
# ----------------------------------------------------------------------------

STOPWORDS = set("""the a an is are was were be been being of to in on for and
or but with without this that these those it its as at by from into over
under about your you my me i we our their his her not no do does did can
could should would will shall what when where why how""".split())
HEB_STOP = set("של על עם זה זאת הוא היא אני אתה את הם הן לא כן יש אין מה מתי איפה למה איך".split())

WORD_RE = re.compile(r"[A-Za-z0-9\u0590-\u05FF_./-]{3,}")


def tokenize(s):
    words = WORD_RE.findall((s or "").lower())
    return [w for w in words if w not in STOPWORDS and w not in HEB_STOP]


def _load_standard():
    try:
        with open(STANDARD_PATH, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        print("[taste480] WARN standard file not found: %s" % e, file=sys.stderr)
        return [], []
    section_pat = re.compile(r"^(#{2,3}) (.+)$", re.M)
    marks = list(section_pat.finditer(text))
    sections = []
    for i, m in enumerate(marks):
        start = m.end()
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        sections.append({"header": m.group(2).strip(), "body": text[start:end].strip(),
                          "start": m.start()})
    req_pat = re.compile(r"^- \*\*(ALMA-[A-Z0-9]+-\d+)\*\* — (.+)$", re.M)
    reqs = []
    for rm in req_pat.finditer(text):
        pos = rm.start()
        header = ""
        for sec in sections:
            if sec["start"] <= pos:
                header = sec["header"]
            else:
                break
        reqs.append({"id": rm.group(1), "text": rm.group(2).strip(), "section": header})
    print("[taste480] ALMAWARE standard loaded: %d sections, %d requirements"
          % (len(sections), len(reqs)), file=sys.stderr)
    return sections, reqs


STANDARD_SECTIONS, STANDARD_REQS = _load_standard()


def _score(tokens, text):
    low = text.lower()
    return sum(low.count(t) for t in tokens)


def search_standard(query, max_reqs=3, max_sections=1):
    tokens = tokenize(query)
    if not tokens or not STANDARD_REQS:
        return [], []
    ql = query.lower()
    id_hits = [r for r in STANDARD_REQS if r["id"].lower() in ql]

    scored_reqs = []
    for r in STANDARD_REQS:
        s = _score(tokens, r["text"]) * 2 + _score(tokens, r["section"])
        if s > 0:
            scored_reqs.append((s, r))
    scored_reqs.sort(key=lambda x: -x[0])
    top_reqs = list(id_hits)
    for _s, r in scored_reqs:
        if len(top_reqs) >= max_reqs:
            break
        if r not in top_reqs:
            top_reqs.append(r)
    top_reqs = top_reqs[:max_reqs]

    scored_secs = []
    for sec in STANDARD_SECTIONS:
        s = _score(tokens, sec["header"]) * 3 + _score(tokens, sec["body"][:4000])
        if s > 0:
            scored_secs.append((s, sec))
    scored_secs.sort(key=lambda x: -x[0])
    top_secs = [{"header": sec["header"], "body": sec["body"]}
                for _s, sec in scored_secs[:max_sections]]
    return top_reqs, top_secs


# ----------------------------------------------------------------------------
# Retrieval: project grep -- only when the message names a real D:\CLAUDE dir
# ----------------------------------------------------------------------------

_topdirs_cache = None


def _project_topdirs():
    global _topdirs_cache
    if _topdirs_cache is None:
        try:
            _topdirs_cache = [d for d in os.listdir(PROJECT_ROOT)
                              if os.path.isdir(os.path.join(PROJECT_ROOT, d))
                              and not d.startswith(".")]
        except OSError:
            _topdirs_cache = []
    return _topdirs_cache


def grep_project(query, max_hits=4, time_budget=2.0, file_budget=3000):
    ql = query.lower()
    hit_dirs = [d for d in _project_topdirs() if d.lower() in ql]
    if not hit_dirs:
        return []
    terms = tokenize(query)
    if not terms:
        return []
    t0 = time.time()
    scanned = 0
    hits = []
    for d in hit_dirs[:3]:
        base = os.path.join(PROJECT_ROOT, d)
        for root, dirs, files in os.walk(base):
            dirs[:] = [x for x in dirs if x not in PROJECT_EXCLUDE_DIRS and not x.startswith(".")]
            if time.time() - t0 > time_budget or scanned > file_budget:
                return hits[:max_hits]
            for fn in files:
                if not fn.lower().endswith(PROJECT_TEXT_EXTS):
                    continue
                scanned += 1
                fp = os.path.join(root, fn)
                try:
                    if os.path.getsize(fp) > 300_000:
                        continue
                except OSError:
                    continue
                try:
                    with open(fp, encoding="utf-8", errors="ignore") as f:
                        for i, line in enumerate(f, 1):
                            if any(t in line.lower() for t in terms):
                                hits.append({"path": fp, "line": i, "text": line.strip()[:200]})
                                break
                except OSError:
                    continue
                if len(hits) >= max_hits:
                    return hits[:max_hits]
    return hits[:max_hits]


# ----------------------------------------------------------------------------
# Retrieval: QUORUM (the multi-AI Talmudic-debate arena, :8099) -- past rooms
# only, read-only. This model has no tool-calling, so it cannot open QUORUM's
# UI or POST /debate itself; CONTEXT.md tells it (and Iddo) how a live debate
# gets started. What it CAN do is know what was already argued.
# ----------------------------------------------------------------------------

def _quorum_get(url, timeout=3):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        # routine, not an error: QUORUM is loopback+tailnet only and may not be
        # running -- same fail-quiet contract as search_recall.
        print("[taste480] WARN quorum request failed (%s): %s" % (url, e), file=sys.stderr)
        return None


def search_quorum(query, max_rooms=2, max_snips=3, timeout=3):
    """Keyword-match QUORUM room titles, then pull the best-matching messages
    out of the top rooms -- same _score()/tokenize() shape as search_standard.
    Lets the coder say 'in the QUORUM room on X, ... concluded Y' when a past
    debate actually covered the question, instead of re-arguing from nothing."""
    tokens = tokenize(query)
    if not tokens:
        return []
    listing = _quorum_get(QUORUM_ROOMS_URL, timeout=timeout)
    if not listing or not listing.get("ok"):
        return []
    scored_rooms = []
    for r in listing.get("rooms") or []:
        if not r.get("message_count"):
            continue
        title = r.get("title") or r.get("name") or ""
        s = _score(tokens, title)
        if s > 0:
            scored_rooms.append((s, r))
    scored_rooms.sort(key=lambda x: -x[0])

    out = []
    for _s, r in scored_rooms[:max_rooms]:
        rid = r.get("room_id") or r.get("id")
        if not rid:
            continue
        detail = _quorum_get(QUORUM_ROOM_URL_FMT % urllib.parse.quote(rid, safe=""),
                             timeout=timeout)
        room = (detail or {}).get("room") if detail and detail.get("ok") else None
        if not room:
            continue
        scored_msgs = []
        for m in room.get("messages") or []:
            sm = _score(tokens, m.get("text") or "")
            if sm > 0:
                scored_msgs.append((sm, m))
        scored_msgs.sort(key=lambda x: -x[0])
        for _sm, m in scored_msgs[:max_snips]:
            out.append({"room": (r.get("title") or r.get("name") or rid)[:140],
                       "who": m.get("from") or "?",
                       "snip": (m.get("text") or "")[:280]})
    return out


# ----------------------------------------------------------------------------
# Context assembly
# ----------------------------------------------------------------------------

def build_context(user_msg):
    recall_hits = search_recall(user_msg)
    std_reqs, std_secs = search_standard(user_msg)
    proj_hits = grep_project(user_msg)
    ramchat_hits = search_ramchat(user_msg)
    quorum_hits = search_quorum(user_msg)
    return {"recall": recall_hits, "standard_reqs": std_reqs,
            "standard_secs": std_secs, "project": proj_hits,
            "ramchat": ramchat_hits, "quorum": quorum_hits}


def context_to_system_block(ctx):
    parts = []
    if ctx["recall"]:
        parts.append("### Retrieved from ALMA-RECALL (search over Iddo's memory files + every AI chat)")
        for h in ctx["recall"]:
            parts.append("- [%s %s] %s: %s" % (h["source"], h["ts"], h["title"], h["snip"]))
    if ctx["standard_reqs"] or ctx["standard_secs"]:
        parts.append("### Retrieved from the ALMAWARE STANDARD (D:\\CLAUDE\\_deliverables\\almaware-standard)")
        for r in ctx["standard_reqs"]:
            parts.append("- %s (%s): %s" % (r["id"], r["section"], r["text"]))
        for s in ctx["standard_secs"]:
            body = re.sub(r"\s+", " ", s["body"])[:400]
            parts.append('- Section "%s": %s' % (s["header"], body))
    if ctx["project"]:
        parts.append("### Relevant files in D:\\CLAUDE (grep, best-effort)")
        for p in ctx["project"]:
            parts.append("- %s:%d: %s" % (p["path"], p["line"], p["text"]))
    if ctx.get("ramchat"):
        parts.append("### Retrieved from RAMCHAT (the team's shared coordination council -- "
                     "other AI agents/sessions on this machine, recent posts)")
        for m in ctx["ramchat"]:
            parts.append("- [%s %s] %s" % (m["at"], m["who"], m["text"]))
    if ctx.get("quorum"):
        parts.append("### Retrieved from QUORUM (the multi-AI Talmudic-debate arena, :8099 -- "
                     "past room transcripts; you cannot start a debate yourself, see CONTEXT.md)")
        for q in ctx["quorum"]:
            parts.append('- [room "%s", %s] %s' % (q["room"], q["who"], q["snip"]))
    if not parts:
        return ""
    # cap raised 3500->4800 alongside adding RAMCHAT+QUORUM: the system prompt's real
    # budget constraint is STANDARD_COMPACT (~30KB) + STANDING_CONTEXT (~5.6KB) against
    # the 32768-token window (see MAX_PROMPT_CHARS comment above) -- that math has
    # roughly 10K tokens of headroom, so +1300 chars (~300 tokens) here to fit two more
    # sources without starving the three that were already tuned is still comfortably
    # inside budget, not a re-blow of it.
    return "\n".join(parts)[:4800]


CONTEXT_MD_PATH = os.path.join(APP_DIR, "CONTEXT.md")


def _load_standing_context():
    try:
        with open(CONTEXT_MD_PATH, encoding="utf-8") as f:
            text = f.read().strip()
        print("[taste480] standing CONTEXT.md loaded: %d chars" % len(text), file=sys.stderr)
        return text
    except OSError as e:
        print("[taste480] WARN CONTEXT.md not found: %s" % e, file=sys.stderr)
        return ""


STANDING_CONTEXT = _load_standing_context()

STANDARD_COMPACT_PATH = os.path.join(APP_DIR, "ALMAWARE-STANDARD-COMPACT.txt")


def _load_standard_compact():
    try:
        with open(STANDARD_COMPACT_PATH, encoding="utf-8") as f:
            text = f.read().strip()
        print("[taste480] ALMAWARE standard COMPACT (always-on) loaded: %d chars, %d requirements"
              % (len(text), text.count("\n") + 1), file=sys.stderr)
        return text
    except OSError as e:
        print("[taste480] WARN standard compact not found: %s" % e, file=sys.stderr)
        return ""


STANDARD_COMPACT = _load_standard_compact()

SYSTEM_PREAMBLE = (
    "You are Iddo's local assistant on top of Qwen3-Coder-480B (vLLM, pipeline-parallel "
    "across eran2+eran3+eran4). Below is your standing context (CONTEXT.md, always loaded, "
    "not a retrieval result) -- who Iddo is, the fleet, the projects, and how to deploy to "
    "his site. On top of that, five things are queried fresh every turn: ALMA-RECALL "
    "(search over Iddo's memory files and every AI chat transcript on this PC), the "
    "ALMAWARE STANDARD (the house engineering law, D:\\CLAUDE\\_deliverables\\almaware-standard), "
    "a grep of a project's own directory under D:\\CLAUDE when the message names one, RAMCHAT "
    "(the shared coordination log every AI agent on this machine posts to -- so you know what "
    "other sessions are doing or have already decided before you suggest it), and QUORUM (the "
    "multi-AI Talmudic-debate arena at :8099 -- past debate rooms, so you can cite what was "
    "already argued there). You have no tool-calling (xgrammar bug, see below), so you cannot "
    "read RAMCHAT or start a QUORUM debate yourself -- both are handed to you pre-fetched. "
    "Anything retrieved is appended below its own heading. Use it when relevant and say what "
    "you used (e.g. \"per ALMA-LAW-008...\" or \"RAMCHAT shows X already tried this...\"); if "
    "nothing relevant was retrieved or the standing context doesn't cover it, say so plainly "
    "rather than inventing a citation -- an unsupported claim is worse than an admitted gap. "
    "Reply in whichever language Iddo wrote in (Hebrew or English); keep code identifiers in "
    "fenced code blocks.\n\n"
    + STANDING_CONTEXT
    + "\n\n### THE ALMAWARE STANDARD (ALMA-STD/0.1) -- ALWAYS BINDING, not a retrieval result\n"
    "Iddo's explicit order (2026-09-09 05:20): you must know this standard fully, every turn, without "
    "him ever re-pasting it. Below are all 184 requirement statements (ALMA-<AREA>-<nnn>), the full "
    "text minus their scar/test evidence (which the per-turn ALMAWARE STANDARD search above can still "
    "pull in when relevant, cited by ID). Every one of these binds your answers whenever they touch "
    "ALMAWARE-governed work -- cite the exact ID when you apply one.\n\n"
    + STANDARD_COMPACT
)


def build_messages(history, user_msg, ctx_block, conv_id="default", on_stage=None):
    """Assemble the messages list, trimming history to MAX_PROMPT_CHARS.

    Before any old turn is actually dropped, it is folded into a persistent
    rolling SUMMARY (see the block above append_history) so the raw-text cut
    doesn't mean the fact is gone -- the summary is included as its own
    section of the system message, always, once one exists. `conv_id` picks
    which <id>.summary.txt this conversation's memory lives in (the web page
    only ever uses "default"; the desktop app passes its real conversation
    id so each thread gets its own memory). `on_stage`, if given, is called
    with a short human-readable string right before the summarizer call
    fires -- so a caller with a UI (the desktop app) can surface it instead
    of it happening invisibly.
    """
    def stage(msg):
        if on_stage:
            try:
                on_stage(msg)
            except Exception:
                pass

    sys_content = SYSTEM_PREAMBLE
    if ctx_block:
        sys_content += "\n\n" + ctx_block

    hist_msgs = [{"role": h.get("role"), "content": (h.get("content") or "")[:4000],
                 "ts": h.get("ts") or ""}
                for h in history if h.get("role") in ("user", "assistant")]

    def split(budget_base):
        """hist_msgs split into (kept, dropped) under budget_base+user_msg,
        most-recent-first -- same trimming logic as before, just factored out
        so it can be run once to see what WOULD be dropped, and again after
        the summary (which also costs budget) is folded into sys_content."""
        total = budget_base + len(user_msg)
        keep = []
        for h in reversed(hist_msgs):
            total += len(h["content"])
            if total > MAX_PROMPT_CHARS:
                break
            keep.append(h)
        keep.reverse()
        dropped = hist_msgs[:len(hist_msgs) - len(keep)]
        return keep, dropped

    _, dropped = split(len(sys_content))
    summary_block = ""
    if dropped:
        existing_summary, through_ts = load_summary(conv_id)
        new_drops = [h for h in dropped if h["ts"] > through_ts] if through_ts else dropped
        if new_drops:
            stage("compressing %d older turn(s) into memory…" % len(new_drops))
            existing_summary = summarize_dropped_turns(existing_summary, new_drops)
            save_summary(conv_id, existing_summary, new_drops[-1]["ts"] or through_ts)
        if existing_summary:
            summary_block = (
                "### Earlier in this conversation (auto-summarized -- the raw text no "
                "longer fits the context window, so this is a compressed memory of it, "
                "kept so nothing said earlier is actually lost)\n" + existing_summary)

    if summary_block:
        sys_content += "\n\n" + summary_block

    kept, _ = split(len(sys_content))

    messages = [{"role": "system", "content": sys_content}]
    messages += [{"role": h["role"], "content": h["content"]} for h in kept]
    messages.append({"role": "user", "content": user_msg})
    return messages


def call_model(messages, max_tokens=8000, temperature=0.3, timeout=600):
    body = json.dumps({
        "model": MODEL, "messages": messages,
        "max_tokens": max_tokens, "temperature": temperature,
    }).encode("utf-8")
    req = urllib.request.Request(DOOR, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ----------------------------------------------------------------------------
# Page
# ----------------------------------------------------------------------------

PAGE = r"""<!doctype html>
<html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>טעימה מהקודר הענק · Taste the 480B Coder</title>
<style>
:root{color-scheme:light}
html,body{height:100%}
*{box-sizing:border-box}
body{margin:0;display:flex;flex-direction:column;font-family:-apple-system,Segoe UI,Arial,sans-serif;
     background:#fff8ec;color:#241a12}
.wrap{max-width:900px;margin:0 auto;width:100%;display:flex;flex-direction:column;flex:1;min-height:0;
      padding:0 20px}
header{padding:22px 0 8px}
h1{font-size:1.4rem;margin:0 0 4px}
.sub{color:#7a6a55;font-size:.9rem}
.examples{margin:10px 0 2px;font-size:.85rem;color:#7a6a55}
.examples button{background:#f0e2c8;color:#5c4a30;font-weight:400;padding:4px 10px;font-size:.8rem;
      margin:2px 4px 2px 0;border:none;border-radius:8px;cursor:pointer}
#thread{flex:1;min-height:0;overflow-y:auto;padding:14px 0 10px;border-top:1px solid #ecdfc4}
.empty{color:#7a6a55;text-align:center;padding:50px 0;font-size:.9rem}
.msg{max-width:88%;margin:10px 0;padding:11px 14px;border-radius:12px;font-size:14px;line-height:1.55;
     overflow-wrap:anywhere}
.msg.user{background:#f0e2c8;color:#3a2c18;margin-inline-start:auto}
.msg.assistant{background:#241a12;color:#f3e9d8;margin-inline-end:auto}
.msg.pending{opacity:.65;font-style:italic}
.ptext{white-space:pre-wrap;word-break:break-word}
pre.code{background:rgba(0,0,0,.25);padding:10px;border-radius:8px;overflow-x:auto;
     font-family:ui-monospace,Consolas,monospace;font-size:12.5px;margin:8px 0;
     direction:ltr;text-align:left;white-space:pre}
.msg.user pre.code{background:rgba(0,0,0,.10)}
.meta{font-size:.72rem;opacity:.65;margin-top:6px}
details.ctx{margin-top:8px;font-size:.72rem;opacity:.9}
details.ctx summary{cursor:pointer}
.ctxgroup{margin:6px 0 2px}
.ctxgroup b{opacity:.85}
.ctxitem{margin:4px 0;padding:6px 8px;border-radius:6px;background:rgba(255,255,255,.08);
     direction:ltr;text-align:left}
.msg.user .ctxitem{background:rgba(0,0,0,.06)}
.ctxitem code{font-family:ui-monospace,Consolas,monospace}
.inputrow{position:sticky;bottom:0;background:#fff8ec;padding:10px 0 20px;border-top:1px solid #ecdfc4}
textarea{width:100%;min-height:64px;max-height:200px;font-family:-apple-system,Segoe UI,Arial,sans-serif;
     font-size:14px;padding:12px;border:1px solid #d8c9ae;border-radius:10px;box-sizing:border-box;
     background:#fffdf8;direction:auto}
button#go{margin-top:8px;padding:10px 22px;font-size:15px;border:none;border-radius:8px;
     background:#c8792f;color:#fff;cursor:pointer;font-weight:600}
button#go:disabled{background:#d8c9ae;cursor:wait}
</style></head>
<body>
<div class="wrap">
<header>
<h1>טעימה מהקודר הענק · Taste the 480B Coder</h1>
<div class="sub">Qwen3-Coder-480B, פרוס על eran2+eran3+eran4 · זיכרון + ALMA-RECALL + ALMAWARE STANDARD + RAMCHAT + QUORUM מחוברים</div>
<div class="examples">
<button onclick="fill('מה זה חוק החלונות השבורים?')">חוק החלונות השבורים?</button>
<button onclick="fill('Summarize the Sacred Audio laws in the ALMAWARE standard')">Sacred Audio laws</button>
<button onclick="fill('על מה דיברנו קודם?')">על מה דיברנו קודם?</button>
</div>
</header>
<div id="thread"></div>
<div class="inputrow">
<textarea id="prompt" placeholder="כתוב הודעה... / write a message..."></textarea>
<br><button id="go">שלח · Send</button>
</div>
</div>
<script>
const $=s=>document.querySelector(s);
function esc(s){return (s==null?'':String(s)).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
function fill(t){$('#prompt').value=t;$('#prompt').focus();}

function renderBody(text){
  const parts=[]; let last=0; const re=/```(\w*)\n?([\s\S]*?)```/g; let m;
  while((m=re.exec(text))){
    if(m.index>last) parts.push({code:false,text:text.slice(last,m.index)});
    parts.push({code:true,text:m[2]});
    last=re.lastIndex;
  }
  if(last<text.length) parts.push({code:false,text:text.slice(last)});
  return parts.map(p=>p.code
    ? '<pre class="code">'+esc(p.text)+'</pre>'
    : '<div class="ptext" dir="auto">'+esc(p.text)+'</div>'
  ).join('');
}

function ctxHTML(ctx){
  if(!ctx) return '';
  const n=(ctx.recall||[]).length+(ctx.standard_reqs||[]).length+(ctx.standard_secs||[]).length+(ctx.project||[]).length+(ctx.ramchat||[]).length+(ctx.quorum||[]).length;
  let body='';
  if(ctx.recall && ctx.recall.length){
    body+='<div class="ctxgroup"><b>ALMA-RECALL</b>'+ctx.recall.map(h=>
      '<div class="ctxitem">['+esc(h.source)+' '+esc(h.ts)+'] '+esc(h.title)+'<br>'+esc(h.snip)+'</div>').join('')+'</div>';
  }
  if(ctx.standard_reqs && ctx.standard_reqs.length){
    body+='<div class="ctxgroup"><b>ALMAWARE STANDARD — requirements</b>'+ctx.standard_reqs.map(r=>
      '<div class="ctxitem"><code>'+esc(r.id)+'</code> ('+esc(r.section)+'): '+esc(r.text)+'</div>').join('')+'</div>';
  }
  if(ctx.standard_secs && ctx.standard_secs.length){
    body+='<div class="ctxgroup"><b>ALMAWARE STANDARD — section</b>'+ctx.standard_secs.map(s=>
      '<div class="ctxitem"><b>'+esc(s.header)+'</b>: '+esc((s.body||'').slice(0,300))+'</div>').join('')+'</div>';
  }
  if(ctx.project && ctx.project.length){
    body+='<div class="ctxgroup"><b>Project files (D:\\CLAUDE)</b>'+ctx.project.map(p=>
      '<div class="ctxitem">'+esc(p.path)+':'+p.line+'<br>'+esc(p.text)+'</div>').join('')+'</div>';
  }
  if(ctx.ramchat && ctx.ramchat.length){
    body+='<div class="ctxgroup"><b>RAMCHAT — team coordination council</b>'+ctx.ramchat.map(m=>
      '<div class="ctxitem">['+esc(m.at)+' '+esc(m.who)+']<br>'+esc(m.text)+'</div>').join('')+'</div>';
  }
  if(ctx.quorum && ctx.quorum.length){
    body+='<div class="ctxgroup"><b>QUORUM — past debate rooms</b>'+ctx.quorum.map(q=>
      '<div class="ctxitem">room "'+esc(q.room)+'" — '+esc(q.who)+'<br>'+esc(q.snip)+'</div>').join('')+'</div>';
  }
  return '<details class="ctx"><summary>context used ('+n+')</summary>'+(body||'<div class="ctxgroup">nothing matched this turn</div>')+'</details>';
}

function addBubble(m){
  const div=document.createElement('div');
  div.className='msg '+(m.role==='user'?'user':'assistant');
  let html=renderBody(m.content||'');
  if(m.role==='assistant'){
    if(m.dt!==undefined && m.dt!==null){
      html+='<div class="meta">'+(m.tokens||'?')+' tokens · '+m.dt+'s</div>';
    }
    html+=ctxHTML(m.context);
  }
  div.innerHTML=html;
  $('#thread').appendChild(div);
  $('#thread').scrollTop=$('#thread').scrollHeight;
  return div;
}

async function loadHistory(){
  try{
    const r=await (await fetch('/history')).json();
    const msgs=r.messages||[];
    $('#thread').innerHTML='';
    if(!msgs.length){
      $('#thread').innerHTML='<div class="empty">אין עדיין שיחה · no conversation yet — כתוב למטה</div>';
      return;
    }
    msgs.forEach(addBubble);
  }catch(e){
    $('#thread').innerHTML='<div class="empty">שגיאת טעינה · load error: '+esc(e)+'</div>';
  }
}

let busy=false;
async function send(){
  if(busy) return;
  const box=$('#prompt'); const text=box.value.trim();
  if(!text) return;
  busy=true; $('#go').disabled=true;
  const emptyEl=document.querySelector('#thread .empty'); if(emptyEl) emptyEl.remove();
  addBubble({role:'user',content:text});
  box.value='';
  const pending=document.createElement('div');
  pending.className='msg assistant pending';
  pending.textContent='...חושב · thinking (יכול לקחת דקה על מודל 480B)';
  $('#thread').appendChild(pending);
  $('#thread').scrollTop=$('#thread').scrollHeight;
  try{
    const r=await fetch('/chat',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({message:text})});
    const j=await r.json();
    pending.remove();
    if(j.error){addBubble({role:'assistant',content:'שגיאה · error: '+j.error});}
    else{addBubble({role:'assistant',content:j.reply,context:j.context,dt:j.dt,tokens:j.completion_tokens});}
  }catch(e){
    pending.remove();
    addBubble({role:'assistant',content:'שגיאת רשת · network error: '+e});
  }
  busy=false; $('#go').disabled=false; box.focus();
}
$('#go').onclick=send;
$('#prompt').addEventListener('keydown',e=>{
  if(e.key==='Enter' && !e.shiftKey){e.preventDefault();send();}
});
loadHistory();
</script>
</body></html>"""


# ----------------------------------------------------------------------------
# Server
# ----------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write("[taste480] %s %s\n" % (time.strftime("%H:%M:%S"), fmt % args))

    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ("/", ""):
            self._send(200, PAGE)
        elif self.path == "/health":
            self._send(200, json.dumps({"ok": True, "service": "taste480",
                                        "history_msgs": len(load_history())}),
                       "application/json")
        elif self.path == "/history":
            self._send(200, json.dumps({"messages": load_history()}, ensure_ascii=False),
                       "application/json")
        else:
            self._send(404, "not found")

    def do_POST(self):
        if self.path != "/chat":
            self._send(404, "not found")
            return
        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
            user_msg = str(payload.get("message", "")).strip()[:6000]
            if not user_msg:
                self._send(400, json.dumps({"error": "empty message"}), "application/json")
                return

            history = load_history()
            ctx = build_context(user_msg)
            ctx_block = context_to_system_block(ctx)
            messages = build_messages(history, user_msg, ctx_block, conv_id="default")

            print("[taste480] turn: msg=%r recall=%d std_reqs=%d std_secs=%d project=%d "
                  "ramchat=%d quorum=%d"
                  % (user_msg[:60], len(ctx["recall"]), len(ctx["standard_reqs"]),
                     len(ctx["standard_secs"]), len(ctx["project"]),
                     len(ctx["ramchat"]), len(ctx["quorum"])), file=sys.stderr)

            # persist the user's turn regardless of model outcome -- broken windows
            # law: don't hide a failure by silently dropping what was actually said.
            append_history("user", user_msg)

            reply = None
            usage = {}
            dt = 0.0
            try:
                t0 = time.time()
                result = call_model(messages)
                dt = round(time.time() - t0, 1)
                choice = (result.get("choices") or [{}])[0]
                reply = (choice.get("message") or {}).get("content", "") or "(empty reply)"
                usage = result.get("usage") or {}
            except Exception as e:
                reply = "[door error] %s: %s" % (type(e).__name__, e)
                print("[taste480] ERROR calling door: %s" % e, file=sys.stderr)

            append_history("assistant", reply,
                           extra={"context": ctx, "dt": dt, "tokens": usage.get("completion_tokens")})

            with conv_lock:
                with open(CONTEXT_LOG_PATH, "a", encoding="utf-8") as f:
                    f.write(json.dumps({
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "user_msg": user_msg, "context": ctx, "dt": dt,
                    }, ensure_ascii=False) + "\n")

            self._send(200, json.dumps({
                "reply": reply, "context": ctx,
                "completion_tokens": usage.get("completion_tokens"),
                "dt": dt,
            }, ensure_ascii=False), "application/json")
        except Exception as e:
            traceback.print_exc()
            self._send(200, json.dumps({"error": "%s: %s" % (type(e).__name__, e)}),
                       "application/json")


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print("[taste480] listening on http://127.0.0.1:%d/  (door=%s)" % (PORT, DOOR), flush=True)
    print("[taste480] conversation: %s" % CONV_PATH, flush=True)
    srv.serve_forever()
