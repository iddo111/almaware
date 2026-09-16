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
  4. (2026-09-15, harnessswarm) The room and QUORUM, on this same page and port:
     GET/POST /api/room (Iddo + any brains + Claude [paid, per message] + Muse, on
     RAMCHAT via coder_room.py) and GET /api/quorum/seatable + POST /api/quorum (an
     SSE relay of coder_quorum.QuorumRun). Brains come from coder_brains.py only.

NOTE (xgrammar scar, memory project_qwen480_pipeline.md): this vLLM build's
tool-calling is BROKEN. This client sends plain chat messages, no `tools` /
`tool_choice` ever -- verified live 2026-09-09 that plain chat/completions
works cleanly without them.

Bind: 127.0.0.1 only. No password on the door (Iddo's explicit order 09-08,
tailnet-only reach). Same port :8875, same Startup shortcut
(ALMA-Taste480-8875.lnk), same pythonw/BELOW_NORMAL launch pattern.
"""
import http.client
import itertools
import json
import os
import queue
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
# THE HOLY HARNESS (Iddo 2026-09-11): this page is the tailnet twin of the ALMAWARE
# Coder desktop app (https://<tailnet-host>:8875/). It talks to the SAME
# brain as the app's main window: door and model are read from desktop_settings.json
# on EVERY request (current_brain() below). DOOR/MODEL are only the fallback when
# that file is unreadable. The old 480B door (dgx2:8443, qwen3-coder-480b) is dead.
# 2026-09-11 20:2x: moved to eran4, where this model is resident forever (1 s a turn); eran2 :8873 took
# 191 s and loaded 59 GB next to gpt-oss-120b.
DOOR = "https://<tailnet-host>:8450/v1/chat/completions"
MODEL = "qwen-coder-dgx4:latest"

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONV_DIR = os.path.join(APP_DIR, "conversations")
CONV_PATH = os.path.join(CONV_DIR, "default.jsonl")
CONTEXT_LOG_PATH = os.path.join(CONV_DIR, "default.context.jsonl")
os.makedirs(CONV_DIR, exist_ok=True)
APP_SETTINGS_PATH = os.path.join(APP_DIR, "desktop_settings.json")   # the main window's brain

# Per-thread brain override. ThreadingHTTPServer serves each request on its own
# thread and the desktop app runs each turn on its own QThread, so a thread-local is
# the one place where "which door, which model, which summary folder" can differ
# per caller without two callers ever swapping each other's module globals.
_brain_local = threading.local()


def current_brain():
    """The brain for THIS request: door/model/max_tokens/temperature from the app's
    desktop_settings.json (read fresh every call, so switching the main window's
    brain switches the tailnet twin too), else the DOOR/MODEL fallback."""
    try:
        with open(APP_SETTINGS_PATH, encoding="utf-8") as f:
            s = json.load(f) or {}
        door = str(s.get("door") or "").strip()
        model = str(s.get("model") or "").strip()
        if door and model:
            return {"door": door, "model": model,
                    "max_tokens": int(s.get("max_tokens", 8000)),
                    "temperature": float(s.get("temperature", 0.3)),
                    "source": "desktop_settings.json"}
        print("[taste480] WARN desktop_settings.json has no door/model -- fallback brain",
              file=sys.stderr)
    except (OSError, ValueError, TypeError) as e:
        print("[taste480] WARN desktop_settings.json unreadable, fallback brain: %s" % e,
              file=sys.stderr)
    return {"door": DOOR, "model": MODEL, "max_tokens": 8000, "temperature": 0.3,
            "source": "fallback constants"}


TWIN_NOT_SENT_NOTE = ("ההודעה לא נשלחה — שלח אותה שוב כשהקודר מוכן · "
                      "this message was not sent — send it again once the coder is ready")


def _coder_switch_gate(brain):
    """BRAIN SWITCH (Iddo 2026-09-15 10:07-10:08). None = the turn may go ahead.
    Otherwise the result of coder_brains.ensure_brain_mode(wait=False) -- the same
    helper the desktop app uses -- whose "text" is what the phone shows while eran4
    loads the coder. Only the eran4 coder door is gated; any failure here fails open
    to the old behaviour (the door's own answer), never into a crashed request."""
    try:
        import coder_brains
        if not coder_brains.is_switch_door(brain.get("door")):
            return None
        r = coder_brains.ensure_brain_mode({"door": brain.get("door"), "model": brain.get("model")},
                                           wait=False)
        print("[taste480] brain switch: %s (%s)" % (r.get("state"), r.get("detail") or "-"),
              file=sys.stderr)
        return None if r.get("ok") else r
    except Exception as e:
        print("[taste480] WARN brain switch check failed, sending as before: %s" % e, file=sys.stderr)
        return None


class use_brain:
    """with use_brain(door, model, conv_dir): call_model() -- including the rolling-
    summary call hidden inside build_messages() -- goes to that door/model, and
    summaries land in conv_dir, for the current thread only."""
    _KEYS = ("door", "model", "conv_dir")

    def __init__(self, door=None, model=None, conv_dir=None):
        self.new = {"door": door, "model": model, "conv_dir": conv_dir}
        self.old = {}

    def __enter__(self):
        for k in self._KEYS:
            self.old[k] = getattr(_brain_local, k, None)
            if self.new[k]:
                setattr(_brain_local, k, self.new[k])
        return self

    def __exit__(self, *exc):
        for k in self._KEYS:
            setattr(_brain_local, k, self.old.get(k))
        return False

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

# BRAIN2 -- the ALMA SECOND BRAIN (:8897): the wiki the model maintains, pages
# carrying sources and dates. Iddo, 2026-09-12 01:08: "תעשה שיהיה לו מוח שני כך
# שהפרויקט יושב על המוח השני לא על המודל" -- a project belongs to the second
# brain, not baked into one model's prompt, so every brain in the Brain menu
# inherits the same knowledge the moment the wiki changes. Loopback GET reads
# need no token (brain2_server.py); a door that is down is routine, not an error.
BRAIN2_SEARCH_URL = "http://127.0.0.1:8897/search"
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

def _summary_dir():
    # 2026-09-11: a profile window (conversations-maverick\, conversations-chat\) keeps
    # its memory next to its own threads instead of colliding in conversations\.
    return getattr(_brain_local, "conv_dir", None) or CONV_DIR


def summary_path(conv_id):
    return os.path.join(_summary_dir(), conv_id + ".summary.txt")


def summary_meta_path(conv_id):
    return os.path.join(_summary_dir(), conv_id + ".summary.meta.json")


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


def summarize_dropped_turns(existing_summary, turns, timeout=120, abort_holder=None,
                            should_stop=None):
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
    if should_stop and should_stop():
        return existing_summary
    try:
        result = call_model(messages, max_tokens=SUMMARY_MAX_TOKENS, temperature=0.2,
                            timeout=timeout, abort_holder=abort_holder)
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
        # POPUP LAW (measured 2026-09-15): a python.exe child without CREATE_NO_WINDOW
        # opens a console window that steals Iddo's focus -- once per chat turn here.
        no_window = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
        proc = subprocess.run(
            [sys.executable, RAMLINK_PATH, "read", "--tail", str(tail), "--json"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=env, timeout=timeout, cwd=RAMCHAT_DIR, **no_window)
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


def search_brain2(query, limit=3, timeout=8):
    """Full-text search over the ALMA SECOND BRAIN wiki (:8897).

    Returns [{id, name, updated, confidence, snip}]. The wiki is curated and
    carries its own sources, so these hits are the most authoritative thing in
    the block -- they go first. Failing to reach the door is routine.

    timeout=8, not 4: brain2 has no index -- B.search() reads and scores EVERY
    page on disk per query (97 pages, 2026-09-12). A query fired seconds after a
    maintainer run returned nothing here while the same URL answered fine a
    minute later, and a silent drop of the second brain is exactly the failure
    ALMA-RECALL already has (9 s cold search against a 4 s budget).
    """
    try:
        url = BRAIN2_SEARCH_URL + "?" + urllib.parse.urlencode({"q": query, "n": limit})
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print("[taste480] WARN brain2 search failed: %s" % e, file=sys.stderr)
        return []
    out = []
    for h in (data.get("hits") or [])[:limit]:
        out.append({"id": h.get("id") or "?",
                    "name": h.get("name") or h.get("id") or "?",
                    "updated": h.get("updated") or "",
                    "confidence": h.get("confidence") or "",
                    "snip": re.sub(r"\s+", " ", h.get("snippet") or "")[:420]})
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
    brain2_hits = search_brain2(user_msg)
    return {"recall": recall_hits, "standard_reqs": std_reqs,
            "standard_secs": std_secs, "project": proj_hits,
            "ramchat": ramchat_hits, "quorum": quorum_hits,
            "brain2": brain2_hits}


def context_to_system_block(ctx):
    parts = []
    if ctx.get("brain2"):
        parts.append("### Retrieved from BRAIN2 — the ALMA SECOND BRAIN (the wiki the model "
                     "maintains, http://127.0.0.1:8897). A PROJECT lives here, not inside any "
                     "one model: these pages carry their own sources and dates, so prefer them "
                     "over your own recollection, and cite the page id like [projects/xyz].")
        for p in ctx["brain2"]:
            parts.append("- [%s · %s · %s] %s"
                         % (p["id"], p["confidence"], p["updated"], p["snip"]))
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
    # 2026-09-12: 4800 -> 6200 alongside adding BRAIN2 as a sixth source. Same budget
    # argument as the 3500->4800 raise above: +1400 chars is ~350 tokens against ~10K
    # tokens of headroom, and BRAIN2 is where a project now lives, so starving it would
    # defeat the point of having a second brain at all.
    return "\n".join(parts)[:6200]


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

def _brains_prose():
    """The Brain menu as one sentence, read from coder_brains.py -- the one source of
    truth for brains (harnessswarm 2026-09-15; the hand-written list here still named
    Maverick after it was retired). Never raises: coder_engine imports this module, so a
    broken catalog may cost this sentence, never the desktop app's chat."""
    try:
        import coder_brains
        names = ["%s%s" % (b["label"], " (on demand)" if b.get("on_demand") else "")
                 for b in coder_brains.all_brains() if b.get("label")]
        if names:
            return "; ".join(names)
    except Exception as e:
        print("[taste480] WARN coder_brains unavailable for the preamble: %s" % e, file=sys.stderr)
    return "whichever brain the menu currently holds"


BRAINS_PROSE = _brains_prose()

SYSTEM_PREAMBLE = (
    "You are Iddo's local coding assistant inside ALMAWARE Coder, the Holy Harness. The "
    "brain behind you is picked in the app's Brain menu, which today holds: " + BRAINS_PROSE + ". "
    "Inside this same harness Iddo can also address several of those brains at once -- plus "
    "Claude (paid, invited only per message) and Muse -- in the shared room (RAMCHAT), and seat "
    "them in a QUORUM debate. Below is your standing context (CONTEXT.md, always loaded, "
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


def build_messages(history, user_msg, ctx_block, conv_id="default", on_stage=None,
                   abort_holder=None, should_stop=None):
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
            folded = summarize_dropped_turns(existing_summary, new_drops, abort_holder=abort_holder,
                                             should_stop=should_stop)
            # 2026-09-11: advance through_ts ONLY when real new memory came back. A failed
            # call returns the old text unchanged, and saving it anyway marked the dropped
            # turns as folded in without ever summarizing them (3x on the dead 480B door).
            # Now they are simply retried on the next turn.
            if folded and folded != existing_summary:
                existing_summary = folded
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


def call_model(messages, max_tokens=8000, temperature=0.3, timeout=600, door=None, model=None,
               abort_holder=None):
    """abort_holder, if given, gets the live http.client connection appended
    the instant it opens (2026-09-12) -- a caller on another thread (Stop
    clicked) can call .close() on it to unblock this call immediately instead
    of waiting out `timeout`. Same technique as coder_engine.stream_completion."""
    door = door or getattr(_brain_local, "door", None) or DOOR
    model = model or getattr(_brain_local, "model", None) or MODEL
    body = json.dumps({
        "model": model, "messages": messages,
        "max_tokens": max_tokens, "temperature": temperature,
    }).encode("utf-8")
    parts_url = urllib.parse.urlsplit(door)
    conn_cls = http.client.HTTPSConnection if parts_url.scheme == "https" else http.client.HTTPConnection
    conn = conn_cls(parts_url.hostname, parts_url.port, timeout=timeout)
    if abort_holder is not None:
        abort_holder.append(conn)
    path = parts_url.path or "/"
    if parts_url.query:
        path += "?" + parts_url.query
    try:
        conn.request("POST", path, body=body, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        return json.loads(resp.read().decode("utf-8"))
    finally:
        conn.close()


# ----------------------------------------------------------------------------
# Page
# ----------------------------------------------------------------------------

PAGE = r"""<!doctype html>
<html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ההרנס הקדוש · ALMAWARE Coder</title>
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
[hidden]{display:none!important}
.tabs{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0 2px}
.tabs button{background:#f0e2c8;color:#5c4a30;border:none;border-radius:8px;padding:6px 12px;
     font-size:.85rem;cursor:pointer}
.tabs button.on{background:#c8792f;color:#fff;font-weight:600}
.pane{display:flex;flex-direction:column;flex:1;min-height:0}
#roomlog,#qlog{flex:1;min-height:0;overflow-y:auto;padding:10px 0;border-top:1px solid #ecdfc4}
.rline{margin:6px 0;padding:8px 11px;border-radius:10px;font-size:13.5px;line-height:1.5;max-width:92%;
     overflow-wrap:anywhere}
.rline.me{background:#f0e2c8;color:#3a2c18;margin-inline-start:auto}
.rline.coder{background:#241a12;color:#f3e9d8;margin-inline-end:auto}
.rline.other{background:#fffdf8;border:1px solid #ecdfc4;color:#5c4a30;font-size:12.5px}
.rwho{font-size:.72rem;opacity:.7;margin-bottom:2px}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0}
.chip{border:1px solid #d8c9ae;background:#fffdf8;color:#5c4a30;border-radius:999px;padding:5px 11px;
     font-size:.8rem;cursor:pointer}
.chip.on{background:#c8792f;border-color:#c8792f;color:#fff}
.chip.paid{border-color:#b8860b}
.chip.paid.on{background:#8a5a00;border-color:#8a5a00}
.chip.down{opacity:.55}
.small{font-size:.78rem;color:#7a6a55}
.err{color:#a3261b}
.qturn{margin:8px 0;padding:8px 11px;border-radius:10px;background:#241a12;color:#f3e9d8;font-size:13.5px;
     white-space:pre-wrap;overflow-wrap:anywhere}
.qturn b{display:block;font-size:.75rem;opacity:.75;margin-bottom:3px}
.qnote{margin:4px 0;font-size:.78rem;color:#7a6a55}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
button.act{margin-top:8px;padding:10px 22px;font-size:15px;border:none;border-radius:8px;
     background:#c8792f;color:#fff;cursor:pointer;font-weight:600}
button.act:disabled{background:#d8c9ae;cursor:wait}
button.act.ghost{background:#f0e2c8;color:#5c4a30}
@media (max-width:600px){
  .wrap{padding:0 16px}
  .chips{flex-wrap:nowrap;overflow-x:auto;padding-bottom:4px}
  .chip{flex:0 0 auto;white-space:nowrap}
}
</style></head>
<body>
<div class="wrap">
<header>
<h1>ההרנס הקדוש · ALMAWARE Coder</h1>
<div class="sub">אותו מוח ואותה שיחה כמו החלון הראשי בדסקטופ · same brain, same conversation as the desktop app<span id="brain"></span> · ALMA-RECALL + ALMAWARE STANDARD + RAMCHAT + QUORUM</div>
<script>fetch('/health').then(r=>r.json()).then(j=>{const e=document.getElementById('brain');if(e&&j.brain)e.textContent=' · '+j.brain.model;}).catch(()=>{});</script>
<div class="tabs">
<button id="tab-chat" class="on" onclick="showTab('chat')">שיחה · Chat</button>
<button id="tab-room" onclick="showTab('room')">חדר · Room</button>
<button id="tab-quorum" onclick="showTab('quorum')">קוורום · QUORUM</button>
</div>
<div class="examples" id="examples">
<button onclick="fill('מה זה חוק החלונות השבורים?')">חוק החלונות השבורים?</button>
<button onclick="fill('Summarize the Sacred Audio laws in the ALMAWARE standard')">Sacred Audio laws</button>
<button onclick="fill('על מה דיברנו קודם?')">על מה דיברנו קודם?</button>
</div>
</header>
<section id="pane-chat" class="pane">
<div id="thread"></div>
<div class="inputrow">
<textarea id="prompt" placeholder="כתוב הודעה... / write a message..."></textarea>
<br><button id="go">שלח · Send</button>
</div>
</section>
<section id="pane-room" class="pane" hidden>
<div class="small">
<div dir="rtl">החדר המשותף (RAMCHAT): אתה וכל המודלים יחד. בחר מי עונה, כל אחד עונה פעם אחת. 💰 עולה כסף ונבחר מחדש בכל הודעה.</div>
<div dir="ltr">The shared room: pick who answers, each answers once. 💰 costs money and is picked per message.</div>
<label><input type="checkbox" id="roomAll"> הצג את כל RAMCHAT · show all of RAMCHAT</label></div>
<div id="roomlog"><div class="empty">טוען · loading…</div></div>
<div class="inputrow">
<div id="roomchips" class="chips"></div>
<textarea id="roomText" placeholder="כתוב לחדר... / write to the room..."></textarea>
<div class="row"><button id="roomGo" class="act">שלח לחדר · Send</button><span id="roomStatus" class="small"></span></div>
</div>
</section>
<section id="pane-quorum" class="pane" hidden>
<div class="small">
<div dir="rtl">שקלא וטריא בין מודלים (QUORUM). בחר לפחות שניים. <button class="chip" onclick="loadSeats()">רענן · refresh</button></div>
<div dir="ltr">A debate between models, pick at least two.</div></div>
<div id="qseats" class="chips"></div>
<div id="qlog"><div class="empty">עוד לא התחיל דיון · no debate yet</div></div>
<div class="inputrow">
<textarea id="qTopic" placeholder="השאלה לדיון... / the question to argue..."></textarea>
<div class="row">
<label class="small">סבבים · rounds <select id="qRounds"><option>1</option><option selected>2</option><option>3</option><option>4</option></select></label>
<button id="qGo" class="act">התחל דיון · Start</button>
<button id="qStop" class="act ghost" disabled>עצור · Stop</button>
<span id="qStatus" class="small"></span>
</div>
</div>
</section>
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
  pending.textContent='...חושב · thinking';
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

// ---- tabs (2026-09-15): chat / room / QUORUM, one page, one port ----
let roomTimer=null, seatsLoaded=false;
function showTab(name){
  ['chat','room','quorum'].forEach(t=>{
    $('#pane-'+t).hidden=(t!==name);
    $('#tab-'+t).classList.toggle('on',t===name);
  });
  $('#examples').hidden=(name!=='chat');
  if(roomTimer){clearInterval(roomTimer);roomTimer=null;}
  if(name==='room'){loadRoom(true);roomTimer=setInterval(()=>loadRoom(false),4000);}
  if(name==='quorum' && !seatsLoaded){loadSeats();}
}

// ---- room: Iddo + the brains + Claude (💰, per message) + Muse ----
const roomSel=new Set(); let roomTargets=[]; let roomSending=false; let iddoWho='iddo';
function renderChips(){
  const box=$('#roomchips'); box.innerHTML='';
  roomTargets.forEach(t=>{
    const paid=t.cost==='paid';
    const b=document.createElement('button');
    b.className='chip'+(paid?' paid':'')+(roomSel.has(t.id)?' on':'');
    b.textContent=(paid?'💰 ':'')+t.label+(t.on_demand?' · לפי דרישה':'');
    b.title=t.id+(paid?' · עולה כסף · costs money':' · חינם · free');
    b.onclick=()=>{roomSel.has(t.id)?roomSel.delete(t.id):roomSel.add(t.id);renderChips();};
    if(t.disabled){roomSel.delete(t.id);b.disabled=true;b.classList.add('down');b.classList.remove('on');b.title=t.why||'';b.onclick=null;}
    box.appendChild(b);
  });
}
async function loadRoom(first){
  try{
    const r=await fetch('/api/room?n=80'); const j=await r.json();
    if(j.error){$('#roomStatus').textContent='שגיאה · error: '+j.error;return;}
    if(j.iddo) iddoWho=j.iddo;
    if(j.targets && JSON.stringify(j.targets)!==JSON.stringify(roomTargets)){roomTargets=j.targets;renderChips();}
    const all=$('#roomAll').checked;
    const lines=(j.lines||[]).filter(l=>all||l.who===iddoWho||/@coder$/.test(l.who||''));
    const log=$('#roomlog');
    const stick=first||(log.scrollHeight-log.scrollTop-log.clientHeight<40), keep=log.scrollTop;
    log.innerHTML=lines.length?'':'<div class="empty">החדר ריק · the room is empty</div>';
    lines.forEach(l=>{
      const d=document.createElement('div');
      d.className='rline '+(l.who===iddoWho?'me':(/@coder$/.test(l.who||'')?'coder':'other'));
      d.innerHTML='<div class="rwho" dir="ltr">'+esc(l.who)+' · '+esc(l.ts)+'</div>'+renderBody(l.text||'');
      log.appendChild(d);
    });
    log.scrollTop=stick?log.scrollHeight:keep;
    const running=(j.jobs||[]).filter(x=>x.state==='running');
    if(!roomSending) $('#roomStatus').textContent=running.length
      ?('עונים עכשיו · answering: '+running.map(x=>(x.targets||[]).join(', ')+' ('+x.replies+'/'+(x.targets||[]).length+')').join(' | ')):'';
  }catch(e){$('#roomStatus').textContent='שגיאת רשת · network error: '+e;}
}
async function sendRoom(){
  if(roomSending) return;
  const text=$('#roomText').value.trim(); if(!text) return;
  const chosen=roomTargets.filter(t=>roomSel.has(t.id));
  const paid=chosen.filter(t=>t.cost==='paid');
  let paid_ok=false;
  if(paid.length){
    if(!confirm('💰 '+paid.map(t=>t.label).join(', ')+' עולה כסף. להזמין להודעה הזאת בלבד?\n💰 costs money. Invite for THIS message only?')) return;
    paid_ok=true;
  }
  roomSending=true; $('#roomGo').disabled=true; $('#roomStatus').textContent='שולח · sending…';
  try{
    const r=await fetch('/api/room',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({text:text,targets:chosen.map(t=>t.id),paid_ok:paid_ok})});
    const j=await r.json();
    if(r.status===202){$('#roomText').value='';$('#roomStatus').textContent='נשלח · sent'+(chosen.length?' · עונים: '+chosen.map(t=>t.label).join(', '):'');}
    else{$('#roomStatus').textContent='לא נשלח · not sent ('+r.status+'): '+(j.error||'');}
  }catch(e){$('#roomStatus').textContent='שגיאת רשת · network error: '+e;}
  paid.forEach(t=>roomSel.delete(t.id)); renderChips();   // paid is per message, never sticky
  roomSending=false; $('#roomGo').disabled=false; loadRoom(true);
}
$('#roomGo').onclick=sendRoom;
$('#roomAll').onchange=()=>loadRoom(true);

// ---- QUORUM: seats + a streamed debate ----
const qSel=new Set(); let qCtrl=null;
async function loadSeats(){
  $('#qStatus').textContent='בודק מושבים · checking seats…';
  try{
    const j=await (await fetch('/api/quorum/seatable')).json();
    if(j.error){$('#qStatus').textContent='שגיאה · error: '+j.error;return;}
    seatsLoaded=true;
    const seats=j.seatable||{}, box=$('#qseats'); box.innerHTML='';
    const brainOf={}; (j.brains||[]).forEach(b=>{if(b.quorum_id)brainOf[b.quorum_id]=b.label;});
    const ids=Object.keys(seats).sort((a,b)=>(seats[b]-seats[a])||a.localeCompare(b));
    if(!ids.length) box.innerHTML='<span class="small err">QUORUM לא עונה · QUORUM is not answering</span>';
    ids.forEach(id=>{
      const up=!!seats[id], paid=/claude/i.test(id);
      const b=document.createElement('button');
      b.className='chip'+(paid?' paid':'')+(up?'':' down')+(qSel.has(id)?' on':'');
      b.textContent=(paid?'💰 ':'')+id+(brainOf[id]?' · '+brainOf[id]:'')+(up?'':' · לא מאומת');
      b.title=up?'חי · up':'לא נבדק כחי עכשיו · not verified up right now';
      b.onclick=()=>{qSel.has(id)?qSel.delete(id):qSel.add(id);b.classList.toggle('on',qSel.has(id));};
      box.appendChild(b);
    });
    $('#qStatus').textContent=(j.up||[]).length+' מושבים חיים · seats up';
  }catch(e){$('#qStatus').textContent='שגיאת רשת · network error: '+e;}
}
async function startQuorum(){
  if(qCtrl) return;
  const topic=$('#qTopic').value.trim(), models=[...qSel];
  if(!topic){$('#qStatus').textContent='חסרה שאלה · no topic';return;}
  if(models.length<2){$('#qStatus').textContent='בחר לפחות שני מודלים · pick at least two';return;}
  const paid=models.filter(m=>/claude/i.test(m)); let paid_ok=false;
  if(paid.length){
    if(!confirm('💰 '+paid.join(', ')+' עולה כסף. לצרף לדיון הזה בלבד?\n💰 costs money. Seat for THIS debate only?')) return;
    paid_ok=true;
  }
  const rounds=parseInt($('#qRounds').value,10)||2, log=$('#qlog'), turns={};
  log.innerHTML='';
  function note(t,cls){const d=document.createElement('div');d.className='qnote'+(cls?' '+cls:'');d.textContent=t;log.appendChild(d);log.scrollTop=log.scrollHeight;}
  function turnFor(d){
    const k=(d.agent||d.model||'?')+'|'+(d.round==null?'':d.round);
    if(!turns[k]){const el=document.createElement('div');el.className='qturn';
      el.innerHTML='<b dir="ltr">'+esc(d.model||d.agent||'?')+(d.round!=null?' · סבב '+esc(d.round):'')+'</b><span dir="auto"></span>';
      log.appendChild(el);turns[k]=el.querySelector('span');}
    return turns[k];
  }
  qCtrl=new AbortController(); $('#qGo').disabled=true; $('#qStop').disabled=false;
  $('#qStatus').textContent='מתחיל · starting…';
  try{
    const res=await fetch('/api/quorum',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({topic:topic,models:models,rounds:rounds,paid_ok:paid_ok}),signal:qCtrl.signal});
    if(!(res.headers.get('Content-Type')||'').startsWith('text/event-stream')){
      let j={}; try{j=await res.json();}catch(e){}
      note('לא התחיל · not started ('+res.status+'): '+(j.error||''),'err');
    }else{
      const rd=res.body.getReader(), dec=new TextDecoder(); let buf='';
      for(;;){
        const r=await rd.read(); if(r.done) break;
        buf+=dec.decode(r.value,{stream:true}); let i;
        while((i=buf.indexOf('\n\n'))>=0){
          const f=buf.slice(0,i); buf=buf.slice(i+2);
          let ev='', data='';
          f.split('\n').forEach(l=>{if(l.startsWith('event:'))ev=l.slice(6).trim();else if(l.startsWith('data:'))data+=l.slice(5).trim();});
          if(!ev) continue;                       // keepalive comment
          let d={}; try{d=JSON.parse(data||'{}')}catch(e){}
          if(ev==='plan') note('שקלא וטריא · '+(d.rounds||'?')+' סבבים · '+(d.agents||[]).map(a=>a.model).join(' · '));
          else if(ev==='status'&&d.state==='round-start') note('סבב '+d.round+' · '+(d.label||''));
          else if(ev==='status'&&d.state==='writing') $('#qStatus').textContent=(d.model||'')+' כותב · writing…';
          else if(ev==='status'&&d.state==='note') note((d.model||'')+': '+(d.note||''));
          else if(ev==='delta'){turnFor(d).textContent+=(d.text||''); log.scrollTop=log.scrollHeight;}
          else if(ev==='error') note('⚠ '+(d.note||d.error||'error'),'err');
          else if(ev==='done') note('✅ הסתיים · done'+(d.elapsed!=null?' · '+d.elapsed+'s':'')+(d.synth_model?' · מסקנה: '+d.synth_model:'')+(d.error?' · '+d.error:''), d.error?'err':'');
        }
      }
    }
  }catch(e){note(e.name==='AbortError'?'נעצר · stopped':'שגיאת רשת · network error: '+e,'err');}
  qCtrl=null; $('#qGo').disabled=false; $('#qStop').disabled=true; $('#qStatus').textContent='';
}
$('#qGo').onclick=startQuorum;
$('#qStop').onclick=()=>{if(qCtrl) qCtrl.abort();};
</script>
</body></html>"""


# ----------------------------------------------------------------------------
# Room + QUORUM doors (harnessswarm, 2026-09-15)
# ----------------------------------------------------------------------------
# Iddo 2026-09-15 02:47: all the models, built-in QUORUM and chat online -- him with
# all the models together with Claude and Muse. The logic lives in coder_room.py,
# coder_quorum.py and coder_brains.py (no Qt, shared with the desktop app); this file
# only adds doors on the SAME port and a section of the SAME page (ONE HARNESS LAW).
# No auth is added: this twin has never had one (Iddo 09-08 and 09-15: tailnet-only,
# bound to 127.0.0.1 behind `tailscale serve`). What IS enforced here: Claude costs
# money, so a paid participant is refused on this door while TWIN_PAID_ALLOWED is
# False, and even when allowed answers only when the request carries paid_ok for THAT
# message; new POST bodies must be application/json (a cross-site form cannot send
# that without a CORS preflight, which this server never grants).
# The sibling imports are lazy on purpose: coder_engine imports taste.py, so a broken
# sibling module may cost these doors, never the desktop app's chat.

# Test hooks -- production leaves all three at their defaults.
ROOM_STORE_FACTORY = None   # () -> RoomStore; default: ONE coder_room.RamchatStore()
ROOM_ADDRESS_KW = {}        # extra kwargs for coder_room.address(): brains=, claude_runner=, ramlink_module=
QUORUM_URL_OVERRIDE = None  # default: coder_quorum.QUORUM_URL

ROOM_TEXT_MAX = 6000        # same cap as /chat
ROOM_READ_DEFAULT = 40
ROOM_READ_MAX = 200
ROOM_MAX_JOBS = 2           # addressed lines answering at once; one more gets 429, never a pile-up
ROOM_JOBS_KEPT = 20
QUORUM_TOPIC_MAX = 4000
QUORUM_MAX_MODELS = 8
QUORUM_MAX_ROUNDS = 4
QUORUM_SEATABLE_TIMEOUT_S = None   # None -> coder_quorum.SEATABLE_TIMEOUT_S (one constant, shared with the desktop)
# MONEY LAW on this door (review fix 2026-09-15): this twin has no login, so a paid_ok
# flag in a JSON body is not Iddo selecting Claude -- any tailnet node (eran3 runs the
# WABOT guest door) or local process could set it. Until Iddo rules, Claude answers
# only from the desktop app's per-line 💰 tick; here he is listed but refused (403).
# Iddo's ruling flips this one constant.
TWIN_PAID_ALLOWED = False
TWIN_PAID_REFUSED = ("💰 Claude עונה כרגע רק מהאפליקציה ALMAWARE Coder במחשב, לא מהדלת ברשת "
                     "· Claude answers only from the ALMAWARE Coder app on the PC for now, "
                     "not from the tailnet door (waiting on Iddo's ruling)")
PC_LOCAL_REFUSED = ("מודל על המחשב של עידו כבוי כרגע (PC_LOCAL_ALLOWED) "
                    "· a model on Iddo's PC is switched off right now (coder_brains.PC_LOCAL_ALLOWED)")
SSE_KEEPALIVE_S = 15       # comment frame while models think: keeps proxies awake, finds a closed tab
API_BODY_MAX = 64 * 1024

_room_slots = threading.BoundedSemaphore(ROOM_MAX_JOBS)
_room_jobs = {}             # job id -> {id, state, targets, paid, started, finished, replies, error}
_room_jobs_lock = threading.Lock()
_room_job_seq = itertools.count(1)
_room_store_cache = {"store": None}
_room_store_lock = threading.Lock()


def _room_store():
    """The room's store: the injected test factory, else ONE RamchatStore for the process."""
    if ROOM_STORE_FACTORY is not None:
        return ROOM_STORE_FACTORY()
    with _room_store_lock:
        if _room_store_cache["store"] is None:
            import coder_room
            _room_store_cache["store"] = coder_room.RamchatStore()
        return _room_store_cache["store"]


def _brain_catalog():
    """{id: brain}: the injected test catalog, else coder_brains.py (the one source of truth)."""
    injected = ROOM_ADDRESS_KW.get("brains")
    if injected is not None:
        return dict(injected)
    import coder_brains
    return {b["id"]: b for b in coder_brains.all_brains() if b.get("id")}


def room_targets():
    """Who can be addressed in the room: every brain, then Claude (paid), then Muse."""
    out = [{"id": bid, "label": b.get("label") or bid, "model": b.get("model"),
            "cost": b.get("cost") or "free", "on_demand": bool(b.get("on_demand"))}
           for bid, b in _brain_catalog().items()]
    claude = {"id": "claude", "label": "Claude", "model": "claude", "cost": "paid",
              "on_demand": False, "disabled": not TWIN_PAID_ALLOWED}
    if not TWIN_PAID_ALLOWED:
        claude["why"] = TWIN_PAID_REFUSED
    out.append(claude)
    out.append({"id": "muse", "label": "Muse · תור", "model": "muse-code", "cost": "free",
                "on_demand": False})
    return out


def _room_jobs_snapshot(limit=5):
    with _room_jobs_lock:
        return [dict(j) for j in list(_room_jobs.values())[-limit:]]


def room_read(n=ROOM_READ_DEFAULT):
    """GET /api/room payload. Raises only when the store itself cannot be read."""
    import coder_room
    try:
        n = int(n)
    except (TypeError, ValueError):
        n = ROOM_READ_DEFAULT
    n = max(1, min(ROOM_READ_MAX, n))
    return {"lines": _room_store().read(n), "targets": room_targets(),
            "jobs": _room_jobs_snapshot(), "iddo": coder_room.IDDO}


def room_start(text, targets, paid_ok=False):
    """POST /api/room -> (http_code, payload). Validates, then runs coder_room.address()
    on a background thread and answers 202 at once. Never raises."""
    try:
        import coder_room
        text = str(text or "").strip()[:ROOM_TEXT_MAX]
        if not text:
            return 400, {"error": "empty text"}
        if not isinstance(targets, list) or not all(isinstance(t, str) for t in targets):
            return 400, {"error": "targets must be a list of strings"}
        clean = []
        for t in targets:
            t = t.strip()
            if t and t not in clean:
                clean.append(t)
        if len(clean) > coder_room.MAX_TARGETS:
            return 400, {"error": "too many targets (max %d)" % coder_room.MAX_TARGETS}
        known = {t["id"]: t for t in room_targets()}
        unknown = [t for t in clean if t not in known]
        if unknown:
            return 400, {"error": "unknown target(s)", "unknown": unknown, "known": sorted(known)}
        paid = [t for t in clean if known[t]["cost"] == "paid"]
        if paid and not TWIN_PAID_ALLOWED:
            return 403, {"error": TWIN_PAID_REFUSED, "paid": paid}
        if paid and paid_ok is not True:
            return 402, {"error": "paid participant needs paid_ok for this message", "paid": paid}
        store = _room_store()
    except Exception as e:
        traceback.print_exc()
        return 503, {"error": "room unavailable: %s: %s" % (type(e).__name__, e)}

    if not _room_slots.acquire(blocking=False):
        return 429, {"error": "busy: %d addressed lines are still being answered" % ROOM_MAX_JOBS}
    job_id = "room-%s-%d" % (time.strftime("%H%M%S"), next(_room_job_seq))
    job = {"id": job_id, "state": "running", "targets": clean, "paid": paid,
           "started": datetime.now().strftime("%H:%M:%S"), "finished": None,
           "replies": 0, "error": None}
    with _room_jobs_lock:
        _room_jobs[job_id] = job
        for old in [k for k, j in _room_jobs.items() if j["state"] != "running"][:-ROOM_JOBS_KEPT]:
            _room_jobs.pop(old, None)
    if paid:
        print("[taste480] room %s: PAID participant(s) %s invited explicitly (paid_ok)"
              % (job_id, paid), file=sys.stderr)

    def bump(_who, _reply):
        with _room_jobs_lock:
            job["replies"] += 1

    def work():
        state, err = "error", "interrupted"
        try:
            coder_room.address(store, text, clean, on_reply=bump, **ROOM_ADDRESS_KW)
            state, err = "done", None
        except Exception as e:  # address() never raises for a target; a store failure does
            traceback.print_exc()
            err = "%s: %s" % (type(e).__name__, e)
        finally:
            with _room_jobs_lock:
                job.update(state=state, error=err, finished=datetime.now().strftime("%H:%M:%S"))
            _room_slots.release()

    try:
        threading.Thread(target=work, name=job_id, daemon=True).start()
    except Exception as e:
        _room_slots.release()
        with _room_jobs_lock:
            job.update(state="error", error="%s: %s" % (type(e).__name__, e))
        return 503, {"error": "could not start: %s" % e}
    return 202, {"accepted": True, "job": job_id, "targets": clean}


def _quorum_url():
    import coder_quorum
    return QUORUM_URL_OVERRIDE or coder_quorum.QUORUM_URL


def _is_paid_seat(model_id):
    """A QUORUM seat that bills Iddo's Anthropic account (the claude CLI seat)."""
    return "claude" in str(model_id or "").lower()


def _seat_refusal(model_id):
    """Why this door will not seat a QUORUM id (an error text), or None."""
    if _is_paid_seat(model_id) and not TWIN_PAID_ALLOWED:
        return TWIN_PAID_REFUSED
    import coder_brains
    import coder_quorum
    if coder_quorum.is_pc_local_seat(model_id) and not coder_brains.PC_LOCAL_ALLOWED:
        return PC_LOCAL_REFUSED
    return None


def quorum_seatable_payload():
    """GET /api/quorum/seatable: which QUORUM seats are up, and which brain sits where.
    Seats this door refuses (paid, PC-local) are listed under 'refused', not offered."""
    import coder_quorum
    url = _quorum_url()
    timeout = (QUORUM_SEATABLE_TIMEOUT_S if QUORUM_SEATABLE_TIMEOUT_S is not None
               else coder_quorum.SEATABLE_TIMEOUT_S)
    raw = coder_quorum.seatable(timeout=timeout, url=url)
    seat = {k: v for k, v in raw.items() if _seat_refusal(k) is None}
    brains = [{"id": bid, "label": b.get("label") or bid, "model": b.get("model"),
               "quorum_id": coder_quorum.map_brain_to_quorum(b.get("model"), seat)}
              for bid, b in _brain_catalog().items()]
    return {"url": url, "answered": bool(raw), "seatable": seat,
            "up": sorted(k for k, v in seat.items() if v),
            "paid": sorted(k for k in raw if _is_paid_seat(k)),
            "paid_allowed": TWIN_PAID_ALLOWED,
            "refused": sorted(k for k in raw if k not in seat), "brains": brains}


def quorum_validate(payload):
    """POST /api/quorum body -> (None, (topic, models, rounds)) or ((code, error), None)."""
    topic = str(payload.get("topic") or "").strip()[:QUORUM_TOPIC_MAX]
    if not topic:
        return (400, {"error": "empty topic"}), None
    models = payload.get("models")
    if not isinstance(models, list) or not all(isinstance(m, str) for m in models):
        return (400, {"error": "models must be a list of strings"}), None
    clean = []
    for m in models:
        m = m.strip()
        if m and m not in clean:
            clean.append(m)
    if len(clean) < 2:
        return (400, {"error": "need at least 2 models to argue"}), None
    if len(clean) > QUORUM_MAX_MODELS:
        return (400, {"error": "too many models (max %d)" % QUORUM_MAX_MODELS}), None
    try:
        rounds = int(payload.get("rounds", 2))
    except (TypeError, ValueError):
        rounds = 2
    rounds = max(1, min(QUORUM_MAX_ROUNDS, rounds))
    refused = [m for m in clean if _seat_refusal(m) is not None]
    if refused:
        return (403, {"error": _seat_refusal(refused[0]), "refused": refused}), None
    paid = [m for m in clean if _is_paid_seat(m)]
    if paid and payload.get("paid_ok") is not True:
        return (402, {"error": "paid participant needs paid_ok for this debate", "paid": paid}), None
    return None, (topic, clean, rounds)


# ----------------------------------------------------------------------------
# Server
# ----------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # the room tab polls GET /api/room every 4 s; do not flood taste480.log with it
        if len(args) >= 2 and str(args[0]).startswith("GET /api/room") and str(args[1]) == "200":
            return
        sys.stderr.write("[taste480] %s %s\n" % (time.strftime("%H:%M:%S"), fmt % args))

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8")

    def _read_json_body(self):
        """-> (payload_dict, None) or (None, (http_code, message))."""
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype != "application/json":
            self.close_connection = True
            return None, (415, "Content-Type must be application/json")
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return None, (400, "bad Content-Length")
        if length <= 0:
            return None, (400, "empty body")
        if length > API_BODY_MAX:
            self.close_connection = True
            return None, (413, "body too large")
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None, (400, "body is not JSON")
        if not isinstance(payload, dict):
            return None, (400, "body must be a JSON object")
        return payload, None

    def _api_get(self, route, query):
        try:
            if route == "/api/room":
                n = urllib.parse.parse_qs(query).get("n", [ROOM_READ_DEFAULT])[0]
                self._json(200, room_read(n))
            else:
                self._json(200, quorum_seatable_payload())
        except Exception as e:
            traceback.print_exc()
            self._json(503, {"error": "%s: %s" % (type(e).__name__, e)})

    def _api_post(self, route):
        self._sse_open = False
        try:
            payload, err = self._read_json_body()
            if err:
                self._json(err[0], {"error": err[1]})
                return
            if route == "/api/room":
                code, out = room_start(payload.get("text"), payload.get("targets", []),
                                       paid_ok=payload.get("paid_ok") is True)
                self._json(code, out)
                return
            bad, args = quorum_validate(payload)
            if bad:
                self._json(*bad)
                return
            self._quorum_stream(*args)
        except Exception as e:
            traceback.print_exc()
            if not self._sse_open:
                try:
                    self._json(500, {"error": "%s: %s" % (type(e).__name__, e)})
                except Exception:
                    pass

    def _sse_write(self, event, data):
        if not isinstance(data, dict):
            data = {"_raw": data}
        frame = "event: %s\ndata: %s\n\n" % (event, json.dumps(data, ensure_ascii=False))
        self.wfile.write(frame.encode("utf-8"))
        self.wfile.flush()

    def _quorum_stream(self, topic, models, rounds):
        """Relay one QUORUM debate as SSE. QuorumRun.run() blocks, so it runs on its own
        thread and hands events over a queue; this thread owns every write, sends a
        keepalive comment while models think, and cancels the debate as soon as the
        phone's tab is gone (a write fails)."""
        import coder_quorum
        run = coder_quorum.QuorumRun(topic, models, rounds=rounds, url=_quorum_url())
        events = queue.Queue()

        def work():
            try:
                result = run.run(lambda name, data: events.put((name, data)))
            except Exception as e:  # run() is documented never to raise; belt and braces
                result = {"error": "%s: %s" % (type(e).__name__, e)}
            events.put((None, result))

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        self._sse_open = True
        print("[taste480] quorum: topic=%r models=%s rounds=%d" % (topic[:60], models, rounds),
              file=sys.stderr)
        threading.Thread(target=work, name="twin-quorum", daemon=True).start()
        saw_done = False
        try:
            while True:
                try:
                    name, data = events.get(timeout=SSE_KEEPALIVE_S)
                except queue.Empty:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    continue
                if name is None:
                    if not saw_done:   # transport failure: the page still gets its one "done"
                        self._sse_write("done", data)
                    break
                saw_done = saw_done or name == "done"
                self._sse_write(name, data)
        except OSError as e:   # BrokenPipe / ConnectionReset / ConnectionAborted
            run.cancel()
            print("[taste480] quorum: client left (%s) -- debate cancelled" % type(e).__name__,
                  file=sys.stderr)

    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        route, _, query = self.path.partition("?")
        if route in ("/api/room", "/api/quorum/seatable"):
            self._api_get(route, query)
            return
        if self.path in ("/", ""):
            self._send(200, PAGE)
        elif self.path == "/health":
            b = current_brain()
            self._send(200, json.dumps({"ok": True, "service": "taste480",
                                        "role": "holy-harness tailnet twin of ALMAWARE Coder",
                                        "history_msgs": len(load_history()),
                                        "brain": {"door": b["door"], "model": b["model"],
                                                  "source": b["source"]}}),
                       "application/json")
        elif self.path == "/door":
            # read-only door check: GET /v1/models on the brain's host. No tokens, no
            # conversation write -- the safe way to prove the twin reaches a live brain.
            b = current_brain()
            out = {"door": b["door"], "model": b["model"], "source": b["source"]}
            try:
                base = b["door"].split("/v1/")[0].rstrip("/")
                with urllib.request.urlopen(base + "/v1/models", timeout=6) as r:
                    data = json.loads(r.read().decode("utf-8"))
                ids = [m.get("id") for m in (data.get("data") or [])]
                out.update(up=True, models=ids, model_listed=b["model"] in ids)
            except Exception as e:
                out.update(up=False, error="%s: %s" % (type(e).__name__, e))
            self._send(200, json.dumps(out, ensure_ascii=False), "application/json")
        elif self.path == "/history":
            self._send(200, json.dumps({"messages": load_history()}, ensure_ascii=False),
                       "application/json")
        else:
            self._send(404, "not found")

    def do_POST(self):
        route = self.path.partition("?")[0]
        if route in ("/api/room", "/api/quorum"):
            self._api_post(route)
            return
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

            brain = current_brain()     # fresh per request: the main window's brain
            # BRAIN SWITCH (Iddo 2026-09-15 10:08): eran4 holds one model at a time. If
            # this brain is the eran4 coder and it is not up, start waking it and tell
            # the phone so right away -- no model call, nothing written to history.
            switch = _coder_switch_gate(brain)
            if switch is not None:
                self._send(200, json.dumps({"reply": switch["text"] + "\n\n" + TWIN_NOT_SENT_NOTE,
                                            "mode": switch}, ensure_ascii=False),
                           "application/json")
                return
            history = load_history()
            ctx = build_context(user_msg)
            ctx_block = context_to_system_block(ctx)
            with use_brain(brain["door"], brain["model"]):
                messages = build_messages(history, user_msg, ctx_block, conv_id="default")
            print("[taste480] brain: %s @ %s (%s)" % (brain["model"], brain["door"], brain["source"]),
                  file=sys.stderr)

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
                result = call_model(messages, max_tokens=brain["max_tokens"],
                                    temperature=brain["temperature"],
                                    door=brain["door"], model=brain["model"])
                dt = round(time.time() - t0, 1)
                if (isinstance(result, dict) and not result.get("choices")
                        and (result.get("error") or result.get("object") == "error")):
                    # the door said why (e.g. 503 "coder asleep ...") -- show it, not "(empty reply)"
                    err = result.get("error") or result.get("message")
                    if isinstance(err, dict):
                        err = err.get("message") or json.dumps(err, ensure_ascii=False)
                    reply = "[door error] %s" % str(err)[:300]
                    result = {}
                choice = (result.get("choices") or [{}])[0]
                reply = reply or (choice.get("message") or {}).get("content", "") or "(empty reply)"
                usage = result.get("usage") or {}
            except Exception as e:
                reply = "[door error] %s: %s" % (type(e).__name__, e)
                print("[taste480] ERROR calling door: %s" % e, file=sys.stderr)

            append_history("assistant", reply,
                           extra={"context": ctx, "dt": dt, "tokens": usage.get("completion_tokens"),
                                  "model": brain["model"]})

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
    _b = current_brain()
    print("[taste480] listening on http://127.0.0.1:%d/  (brain=%s @ %s, from %s)"
          % (PORT, _b["model"], _b["door"], _b["source"]), flush=True)
    print("[taste480] conversation: %s" % CONV_PATH, flush=True)
    srv.serve_forever()
