#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ALMAWARE Coder -- the engine: retrieval + prompt assembly + the door.

THIS MODULE DELIBERATELY OWNS ALMOST NO LOGIC. The RAG that took real work to
get right on 2026-09-08/09 lives in taste.py and is IMPORTED here, not copied:

    taste.search_recall            ALMA-RECALL, http://127.0.0.1:8794/api/search
    taste.search_standard          the 184 ALMA-<AREA>-<nnn> requirements
    taste.grep_project             bounded grep of a named D:\\CLAUDE subtree
    taste.context_to_system_block  the exact "### Retrieved from ..." block
    taste.build_messages           history trimming to MAX_PROMPT_CHARS
    taste.SYSTEM_PREAMBLE          preamble + the standing CONTEXT.md
    taste.call_model               non-streaming POST to the door

There is exactly one behaviour added on top, and it is additive, not a fork:

  1. per-turn RAG toggles + a workspace-scoped grep (a "project" can name its
     own root directory, which taste.grep_project cannot do because it only
     fires on a top-level D:\\CLAUDE dir named in the message);
  2. a streaming transport (SSE) so tokens appear as they are generated --
     with an automatic fall back to taste.call_model if streaming fails;
  3. workspace standing instructions appended to the system message.

`python coder_engine.py --selftest` runs a real grounded turn against the live
door and prints what came back. No Qt needed.
"""
from __future__ import annotations

import http.client
import json
import os
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

# taste.py redirects its own stdout/stderr when they are None (pythonw). Give it
# real streams first so it writes into OUR log rather than reopening taste480.log
# underneath the still-running web server.
if sys.stdout is None or sys.stderr is None:                      # pragma: no cover
    _logf = open(os.path.join(APP_DIR, "coder_desktop.log"), "a",
                 encoding="utf-8", errors="replace", buffering=1)
    sys.stdout = _logf
    sys.stderr = _logf

import taste  # noqa: E402  -- the backend built 2026-09-09, reused wholesale
import coder_store as _store  # noqa: E402  -- profile-aware CONV_DIR / settings

DEFAULT_DOOR = taste.DOOR
DEFAULT_MODEL = taste.MODEL


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------

def grep_workspace(root: str, query: str, max_hits: int = 4,
                   time_budget: float = 2.0, file_budget: int = 4000) -> list:
    """Bounded grep of an arbitrary directory -- the workspace ("project") root.

    Same shape of result as taste.grep_project, and it reuses that module's
    tokenizer and its exclude/extension sets so the two behave identically.
    """
    if not root or not os.path.isdir(root):
        return []
    terms = taste.tokenize(query)
    if not terms:
        return []
    t0 = time.time()
    scanned = 0
    hits = []
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs
                   if d not in taste.PROJECT_EXCLUDE_DIRS and not d.startswith(".")]
        if time.time() - t0 > time_budget or scanned > file_budget:
            break
        for fn in files:
            if not fn.lower().endswith(taste.PROJECT_TEXT_EXTS):
                continue
            scanned += 1
            fp = os.path.join(base, fn)
            try:
                if os.path.getsize(fp) > 300_000:
                    continue
                with open(fp, encoding="utf-8", errors="ignore") as f:
                    for i, line in enumerate(f, 1):
                        low = line.lower()
                        if any(t in low for t in terms):
                            hits.append({"path": fp, "line": i, "text": line.strip()[:200]})
                            break
            except OSError:
                continue
            if len(hits) >= max_hits:
                return hits[:max_hits]
    return hits[:max_hits]


EMPTY_CTX = {"recall": [], "standard_reqs": [], "standard_secs": [], "project": [],
            "ramchat": [], "quorum": [], "brain2": []}


def build_context(user_msg: str, settings: dict, workspace: dict | None = None) -> dict:
    """Same dict shape taste.build_context returns, with the toggles honoured."""
    ctx = {k: list(v) for k, v in EMPTY_CTX.items()}
    if settings.get("rag_recall", True):
        ctx["recall"] = taste.search_recall(
            user_msg, limit=int(settings.get("recall_limit", 4)))
    if settings.get("rag_standard", True):
        reqs, secs = taste.search_standard(user_msg)
        ctx["standard_reqs"], ctx["standard_secs"] = reqs, secs
    if settings.get("rag_project", True):
        hits = taste.grep_project(user_msg)
        root = (workspace or {}).get("root") or ""
        if root:
            seen = {(h["path"], h["line"]) for h in hits}
            for h in grep_workspace(root, user_msg):
                if (h["path"], h["line"]) not in seen:
                    hits.append(h)
        ctx["project"] = hits[:6]
    if settings.get("rag_ramchat", True):
        ctx["ramchat"] = taste.search_ramchat(user_msg)
    if settings.get("rag_quorum", True):
        ctx["quorum"] = taste.search_quorum(user_msg)
    if settings.get("rag_brain2", True):
        # the second brain: where a project lives, independent of which brain is loaded
        ctx["brain2"] = taste.search_brain2(user_msg)
    return ctx


def context_count(ctx: dict) -> int:
    return sum(len(ctx.get(k) or []) for k in EMPTY_CTX)


def build_messages(history: list, user_msg: str, ctx: dict,
                   workspace: dict | None = None, conv_id: str = "default",
                   on_stage=None, settings: dict | None = None,
                   abort_holder=None, should_stop=None) -> list:
    """taste.build_messages, plus the workspace's standing instructions.

    conv_id picks which <id>.summary.txt the rolling-memory feature (added
    2026-09-09, see taste.build_messages) reads/writes for this thread, so
    every desktop conversation gets its own memory rather than sharing one.
    on_stage, if given, surfaces the "compressing older turns…" moment in
    the caller's UI instead of it happening silently mid-call.
    """
    block = taste.context_to_system_block(ctx)
    # 2026-09-11: the rolling-summary call inside taste.build_messages used to go to
    # taste.DOOR (the dead 480B, 502) whatever brain the window was on. Route it to
    # THIS window's brain, and keep its summary files in this profile's own folder.
    st = settings if settings is not None else _store.load_settings()
    with taste.use_brain(st.get("door") or DEFAULT_DOOR, st.get("model") or DEFAULT_MODEL,
                         conv_dir=_store.CONV_DIR):
        messages = taste.build_messages(history, user_msg, block, conv_id=conv_id,
                                        on_stage=on_stage, abort_holder=abort_holder,
                                        should_stop=should_stop)
    # 2026-09-12: tell the brain which model it is, every turn (Iddo: it did not know).
    try:
        import coder_identity
        if messages and messages[0].get('role') == 'system':
            _idl = coder_identity.identity_line(st, DEFAULT_MODEL, DEFAULT_DOOR)
            if _idl:
                messages[0]['content'] += chr(10) + chr(10) + '### ' + 'מי אתה עכשיו' + chr(10) + _idl
    except Exception:
        pass
    instr = ((workspace or {}).get("instructions") or "").strip()
    if instr and messages and messages[0].get("role") == "system":
        messages[0]["content"] += (
            "\n\n### Standing instructions for the workspace \"%s\" "
            "(set by Iddo in the desktop app; they apply to every turn in this workspace)\n%s"
            % ((workspace or {}).get("name", "?"), instr[:4000]))
    return messages


# ---------------------------------------------------------------------------
# The door
# ---------------------------------------------------------------------------

class DoorError(RuntimeError):
    pass


def door_error_text(raw) -> str:
    """The human part of a door's error body: {"error": "..."} (ollama / the eran4
    shim), {"error": {"message": ...}} or {"object": "error", "message": ...} (vLLM),
    else the first 300 characters of whatever came back. Never raises."""
    try:
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8", "replace")
        obj = json.loads(raw) if isinstance(raw, str) else raw
        if isinstance(obj, dict):
            err = obj.get("error") or obj.get("message")
            if isinstance(err, dict):
                err = err.get("message") or json.dumps(err, ensure_ascii=False)
            if err:
                return str(err)[:300]
    except Exception:
        pass
    return str(raw or "")[:300].strip() or "(empty body)"


def door_status(door: str, timeout: float = 6.0) -> tuple[bool, str]:
    """GET /v1/models on the same host. Cheap, no generation, no tokens burnt."""
    base = door.split("/v1/")[0].rstrip("/")
    try:
        with urllib.request.urlopen(base + "/v1/models", timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        ids = [m.get("id") for m in (data.get("data") or [])]
        ctxlen = ((data.get("data") or [{}])[0] or {}).get("max_model_len")
        return True, "%s · ctx %s" % (", ".join(x for x in ids if x) or "?", ctxlen or "?")
    except Exception as e:
        return False, "%s: %s" % (type(e).__name__, e)


def stream_completion(messages, settings, on_chunk, should_stop=None, timeout=900,
                       abort_holder=None):
    """POST with stream:true, yielding deltas through on_chunk(str).

    Returns (full_text, usage_dict, stopped_by_user).

    Raises DoorError on transport failure -- and also when the stream ends with no
    content token AND no finish_reason, so the caller falls back to the blocking
    path instead of showing a stub.

    2026-09-12, measured: llama.cpp sends an SSE ':' keep-alive line about a second
    before the first token of a long prompt (12k tokens = ~35 s of prompt eval on
    Maverick). Iddo's Stop landed on that line, the loop broke with "", and the
    window printed "(the model returned nothing)" -- while the model went on to
    generate into a socket nobody was reading. An empty return must never again be
    indistinguishable from a real empty answer.
    """
    door = settings.get("door") or DEFAULT_DOOR
    body = json.dumps({
        "model": settings.get("model") or DEFAULT_MODEL,
        "messages": messages,
        "max_tokens": int(settings.get("max_tokens", 8000)),
        "temperature": float(settings.get("temperature", 0.3)),
        "stream": True,
        "stream_options": {"include_usage": True},
    }).encode("utf-8")
    parts = []
    usage = {}
    stopped = False
    finished = False                       # a real finish_reason came back
    err = None

    if should_stop and should_stop():
        # Stop was clicked before this call even started (e.g. during the
        # retrieval/summarize phase that runs before it) -- stop() already
        # returned once with nothing in abort_holder to close, so it will
        # never reach a connection opened after that. Catch it here instead
        # of opening a request nobody wants.
        return "", {}, True

    # 2026-09-12, Iddo hit this live: urllib.request.urlopen() blocks until the
    # door sends response HEADERS -- and this router does not flush headers
    # until the upstream model has produced its first byte, which on a slow
    # door (Maverick, big system prompt, ~35s prompt-eval) can be a long wait
    # with NO socket object to close yet. Stop just flipped a flag nothing was
    # checking and sat at "stopping..." until the full 900s timeout.
    # http.client lets us hold a closeable connection from the moment it
    # opens -- BEFORE getresponse() -- so Stop can end the wait at any point,
    # not just once we are already inside the token-reading loop.
    parts_url = urlsplit(door)
    conn_cls = http.client.HTTPSConnection if parts_url.scheme == "https" else http.client.HTTPConnection
    conn = conn_cls(parts_url.hostname, parts_url.port, timeout=timeout)
    if abort_holder is not None:
        abort_holder.append(conn)
    path = parts_url.path or "/"
    if parts_url.query:
        path += "?" + parts_url.query
    try:
        conn.request("POST", path, body=body, headers={
            "Content-Type": "application/json", "Accept": "text/event-stream"})
        resp = conn.getresponse()
    except (OSError, ValueError, AttributeError, http.client.HTTPException) as e:
        conn.close()
        if should_stop and should_stop():
            return "", {}, True
        raise DoorError("%s: %s" % (type(e).__name__, e)) from e
    try:
        # BRAIN SWITCH 2026-09-15: an HTTP error is a JSON body, not SSE. Say what the
        # door said (e.g. 503 "coder asleep - pick Qwen3-Coder-Next ...") instead of
        # the old "stream ended with no content" that hid it.
        status = int(getattr(resp, "status", 200) or 200)
        if status >= 400:
            try:
                raw = resp.read(4000)
            except (OSError, ValueError, AttributeError, http.client.HTTPException):
                raw = b""
            raise DoorError("HTTP %d: %s" % (status, door_error_text(raw)))
        buf = b""
        while True:
            if should_stop and should_stop():
                stopped = True
                break
            try:
                chunk = resp.read(4096)
            except (OSError, ValueError, AttributeError, http.client.HTTPException) as e:
                # conn.close() from another thread (Stop clicked) raises here
                # while we are blocked in .read() -- that is success, not
                # failure, so only re-raise if the user did NOT ask to stop.
                if should_stop and should_stop():
                    stopped = True
                    break
                raise DoorError("%s: %s" % (type(e).__name__, e)) from e
            if not chunk:
                break                       # server closed the stream cleanly
            buf += chunk
            while b"\n" in buf:
                raw, buf = buf.split(b"\n", 1)
                line = raw.decode("utf-8", "replace").strip()
                if not line or not line.startswith("data:"):
                    continue                # ':' keep-alive during prompt processing
                payload = line[5:].strip()
                if payload == "[DONE]":
                    buf = b""
                    break
                try:
                    obj = json.loads(payload)
                except ValueError:
                    continue
                if obj.get("error"):
                    err = obj["error"]
                if obj.get("usage"):
                    usage = obj["usage"]
                for ch in obj.get("choices") or []:
                    if ch.get("finish_reason"):
                        finished = True
                    piece = (ch.get("delta") or {}).get("content")
                    if piece:
                        parts.append(piece)
                        on_chunk(piece)
    finally:
        conn.close()
    text = "".join(parts)
    if not stopped and not text and not finished:
        raise DoorError("the stream ended with no content (%s)"
                        % (json.dumps(err, ensure_ascii=False)[:300] if err
                           else "no data and no finish_reason"))
    return text, usage, stopped


def blocking_completion(messages, settings, timeout=900):
    """The original taste.call_model path -- the fallback, unchanged."""
    # door/model passed explicitly (2026-09-11) instead of swapping taste's globals.
    result = taste.call_model(messages,
                              max_tokens=int(settings.get("max_tokens", 8000)),
                              temperature=float(settings.get("temperature", 0.3)),
                              timeout=timeout,
                              door=settings.get("door") or DEFAULT_DOOR,
                              model=settings.get("model") or DEFAULT_MODEL)
    if not isinstance(result, dict):
        raise DoorError("the door answered with something that is not a JSON object")
    if not result.get("choices") and (result.get("error") or result.get("object") == "error"):
        # BRAIN SWITCH 2026-09-15: was returned as "" -> "(the model returned nothing)".
        raise DoorError("the door answered with an error: %s" % door_error_text(result))
    choice = (result.get("choices") or [{}])[0]
    text = (choice.get("message") or {}).get("content") or ""
    return text, (result.get("usage") or {})


# ---------------------------------------------------------------------------
# Headless selftest -- a real grounded turn, no GUI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import coder_store as store

    q = " ".join(sys.argv[1:]) or "In one sentence: what is the Broken Windows law in this workspace?"
    st = store.load_settings()
    ok, info = door_status(st["door"])
    print("door        :", "UP" if ok else "DOWN", info)
    ctx = build_context(q, st, None)
    print("context     : brain2=%d recall=%d std_reqs=%d std_secs=%d project=%d ramchat=%d quorum=%d"
          % (len(ctx["brain2"]), len(ctx["recall"]), len(ctx["standard_reqs"]),
             len(ctx["standard_secs"]), len(ctx["project"]),
             len(ctx["ramchat"]), len(ctx["quorum"])))
    for h in ctx["brain2"]:
        print("  brain2    : %s (%s, %s)" % (h["id"], h["confidence"], h["updated"]))
    msgs = build_messages([], q, ctx, None)
    print("system chars:", len(msgs[0]["content"]))
    t0 = time.time()
    got = []
    text, usage, stopped = stream_completion(msgs, st, lambda c: got.append(c))
    print("streamed    : %d chunks in %.1fs, usage=%s, stopped=%s"
          % (len(got), time.time() - t0, usage, stopped))
    print("-" * 70)
    print(text[:1500])
