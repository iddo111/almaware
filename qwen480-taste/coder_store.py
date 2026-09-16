#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ALMAWARE Coder -- persistence layer (workspaces, conversations, settings).

Kept in its own module so the GUI file stays about the GUI, and so this layer can
be tested headlessly (`python coder_store.py --selftest`).

ON-DISK SHAPE (D:\\CLAUDE\\qwen480-taste\\conversations\\)
    <id>.jsonl          one JSON object per line: {role, content, ts, ...}
                        -- EXACTLY taste.py's format, on purpose. The web page on
                        :8875 writes default.jsonl; the desktop app adopts and
                        keeps writing that same file, so the two are one thread,
                        not two forks of history.
    <id>.context.jsonl  the per-turn RAG receipt, also taste.py's format.
    index.json          conversation list + titles + workspace membership.
    workspaces.json     the "projects": name, standing instructions, root dir.
    _trash/             deleted conversations move here. Nothing is ever
                        hard-deleted by this app.

Design note (broken-windows law): every write is atomic (tmp file + os.replace)
except the message append, which is a genuine append to a JSONL -- the one
operation where partial-write recovery is trivial (skip the bad line) and where
sharing the file with the running web server actually matters.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import threading
import time
import sys
import uuid
from datetime import datetime, timezone

APP_DIR = os.path.dirname(os.path.abspath(__file__))
# Profiles (Iddo 2026-09-11 16:50): one window per brain. ALMAWARE_CODER_PROFILE=<name>
# or --profile=<name> gives that window its own settings file and its own conversation
# store, so two windows on two brains never write the same history file.
def _profile_name() -> str:
    raw = os.environ.get("ALMAWARE_CODER_PROFILE", "")
    for a in sys.argv:
        if a.startswith("--profile="):
            raw = a.split("=", 1)[1]
    return re.sub(r"[^a-z0-9_-]", "", raw.strip().lower())


PROFILE = _profile_name()
CONV_DIR = os.path.join(APP_DIR, "conversations" + (("-" + PROFILE) if PROFILE else ""))
os.makedirs(CONV_DIR, exist_ok=True)
TRASH_DIR = os.path.join(CONV_DIR, "_trash")
INDEX_PATH = os.path.join(CONV_DIR, "index.json")
WORKSPACES_PATH = os.path.join(CONV_DIR, "workspaces.json")
SETTINGS_PATH = os.path.join(APP_DIR, "desktop_settings%s.json" % (("." + PROFILE) if PROFILE else ""))

_lock = threading.RLock()

DEFAULT_SETTINGS = {
    # Light by default: it is the palette Iddo has actually been looking at on the
    # :8875 page, and his standing preference for anything he reads is bright.
    "theme": "light",                # light | dark
    "font_size": 14,
    "temperature": 0.3,
    "max_tokens": 8000,
    "stream": True,
    "rag_recall": True,
    "rag_standard": True,
    "rag_project": True,
    "rag_ramchat": True,
    "rag_quorum": True,
    "rag_brain2": True,              # BRAIN2 :8897 -- the second brain, where projects live
    "recall_limit": 4,
    # 2026-09-11: was the dead 480B door (dgx2:8443, 502). A new profile without its
    # own settings file now starts on the main window's live brain.
    "door": "https://<tailnet-host>:8450/v1/chat/completions",
    "model": "qwen-coder-dgx4:latest",
    "sidebar_width": 288,
    "send_on_enter": True,
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write_json(path: str, obj) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _read_json(path: str, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def slug(text: str, fallback: str = "chat") -> str:
    """A filesystem-safe id. Hebrew is kept -- Windows handles it fine and it
    makes the conversations/ directory readable by a human, which is the point."""
    text = (text or "").strip()
    text = re.sub(r"[\\/:*?\"<>|\r\n\t]+", " ", text)
    text = re.sub(r"\s+", "-", text).strip("-.")
    text = text[:48]
    return text or fallback


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def load_settings() -> dict:
    s = dict(DEFAULT_SETTINGS)
    s.update(_read_json(SETTINGS_PATH, {}) or {})
    return s


def save_settings(s: dict) -> None:
    with _lock:
        _atomic_write_json(SETTINGS_PATH, s)


# ---------------------------------------------------------------------------
# Workspaces  ("projects")
# ---------------------------------------------------------------------------

DEFAULT_WORKSPACE = {
    "id": "general",
    "name": "General",
    "instructions": "",
    "root": "",
    "color": "#c8792f",
}


def load_workspaces() -> list:
    data = _read_json(WORKSPACES_PATH, None)
    if not data or not isinstance(data.get("workspaces"), list) or not data["workspaces"]:
        ws = [dict(DEFAULT_WORKSPACE)]
        save_workspaces(ws)
        return ws
    out = []
    for w in data["workspaces"]:
        m = dict(DEFAULT_WORKSPACE)
        m.update(w)
        out.append(m)
    return out


def save_workspaces(ws: list) -> None:
    with _lock:
        _atomic_write_json(WORKSPACES_PATH, {"version": 1, "workspaces": ws})


def workspace_by_id(ws_list: list, ws_id: str) -> dict:
    for w in ws_list:
        if w["id"] == ws_id:
            return w
    return ws_list[0] if ws_list else dict(DEFAULT_WORKSPACE)


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------

def conv_path(conv_id: str) -> str:
    return os.path.join(CONV_DIR, conv_id + ".jsonl")


def context_path(conv_id: str) -> str:
    return os.path.join(CONV_DIR, conv_id + ".context.jsonl")


def _blank_index() -> dict:
    return {"version": 1, "conversations": [], "last": None}


def load_index() -> dict:
    os.makedirs(CONV_DIR, exist_ok=True)
    idx = _read_json(INDEX_PATH, None) or _blank_index()
    idx.setdefault("conversations", [])
    idx.setdefault("last", None)

    known = {c["id"] for c in idx["conversations"]}
    changed = False

    # Adopt any .jsonl on disk that the index doesn't know about -- most
    # importantly default.jsonl, which the :8875 web page has been writing since
    # 2026-09-08. Iddo's existing history shows up in the app on first launch
    # instead of being stranded.
    try:
        for fn in sorted(os.listdir(CONV_DIR)):
            if not fn.endswith(".jsonl") or fn.endswith(".context.jsonl"):
                continue
            cid = fn[:-len(".jsonl")]
            if cid in known:
                continue
            msgs = load_messages(cid)
            title = "Web page thread (:8875)" if cid == "default" else cid
            for m in msgs:
                if m.get("role") == "user" and (m.get("content") or "").strip():
                    title = (m["content"].strip().splitlines() or [""])[0][:70]
                    break
            fp = conv_path(cid)
            try:
                mtime = datetime.fromtimestamp(os.path.getmtime(fp), timezone.utc).isoformat()
            except OSError:
                mtime = now_iso()
            idx["conversations"].append({
                "id": cid, "title": title, "workspace": "general",
                "created": msgs[0]["ts"] if msgs and msgs[0].get("ts") else mtime,
                "updated": mtime, "n": len(msgs), "pinned": cid == "default",
            })
            known.add(cid)
            changed = True
    except OSError:
        pass

    # Drop index rows whose file vanished (deleted outside the app).
    alive = [c for c in idx["conversations"] if os.path.isfile(conv_path(c["id"]))]
    if len(alive) != len(idx["conversations"]):
        idx["conversations"] = alive
        changed = True

    if changed:
        save_index(idx)
    return idx


def save_index(idx: dict) -> None:
    with _lock:
        _atomic_write_json(INDEX_PATH, idx)


def sorted_conversations(idx: dict, workspace: str | None = None, query: str = "") -> list:
    rows = idx.get("conversations", [])
    if workspace:
        rows = [c for c in rows if c.get("workspace", "general") == workspace]
    q = (query or "").strip().lower()
    if q:
        rows = [c for c in rows if q in (c.get("title") or "").lower()]
    # Two stable passes: newest first, then pinned floated to the top.
    rows = sorted(rows, key=lambda c: c.get("updated") or "", reverse=True)
    return sorted(rows, key=lambda c: 0 if c.get("pinned") else 1)


def find_conversation(idx: dict, conv_id: str) -> dict | None:
    for c in idx.get("conversations", []):
        if c["id"] == conv_id:
            return c
    return None


def new_conversation(idx: dict, workspace: str = "general", title: str = "New conversation") -> dict:
    base = slug(title, "chat")
    cid = base
    n = 2
    while os.path.exists(conv_path(cid)) or find_conversation(idx, cid):
        cid = "%s-%d" % (base, n)
        n += 1
        if n > 200:
            cid = base + "-" + uuid.uuid4().hex[:6]
            break
    open(conv_path(cid), "a", encoding="utf-8").close()
    row = {"id": cid, "title": title, "workspace": workspace,
           "created": now_iso(), "updated": now_iso(), "n": 0, "pinned": False}
    idx["conversations"].append(row)
    idx["last"] = cid
    save_index(idx)
    return row


def rename_conversation(idx: dict, conv_id: str, title: str) -> None:
    row = find_conversation(idx, conv_id)
    if row:
        row["title"] = title.strip()[:120] or row["title"]
        save_index(idx)


def set_workspace(idx: dict, conv_id: str, ws_id: str) -> None:
    row = find_conversation(idx, conv_id)
    if row:
        row["workspace"] = ws_id
        save_index(idx)


def toggle_pin(idx: dict, conv_id: str) -> None:
    row = find_conversation(idx, conv_id)
    if row:
        row["pinned"] = not row.get("pinned")
        save_index(idx)


def delete_conversation(idx: dict, conv_id: str) -> str:
    """Move to _trash/. Never a hard delete."""
    os.makedirs(TRASH_DIR, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    moved = ""
    for src in (conv_path(conv_id), context_path(conv_id)):
        if os.path.isfile(src):
            dst = os.path.join(TRASH_DIR, "%s.%s%s" % (conv_id, stamp,
                                                       ".context.jsonl" if ".context." in src else ".jsonl"))
            try:
                shutil.move(src, dst)
                moved = dst
            except OSError:
                pass
    idx["conversations"] = [c for c in idx["conversations"] if c["id"] != conv_id]
    if idx.get("last") == conv_id:
        idx["last"] = idx["conversations"][0]["id"] if idx["conversations"] else None
    save_index(idx)
    return moved


def load_messages(conv_id: str) -> list:
    out = []
    p = conv_path(conv_id)
    if not os.path.isfile(p):
        return out
    try:
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue          # a torn line is skipped, never fatal
                if isinstance(rec, dict) and rec.get("role"):
                    out.append(rec)
    except OSError:
        pass
    return out


def append_message(idx: dict, conv_id: str, role: str, content: str, extra: dict | None = None) -> dict:
    rec = {"role": role, "content": content, "ts": now_iso()}
    if extra:
        rec.update(extra)
    with _lock:
        with open(conv_path(conv_id), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        row = find_conversation(idx, conv_id)
        if row:
            row["updated"] = rec["ts"]
            row["n"] = row.get("n", 0) + 1
            if row.get("title") in ("New conversation", "", None) and role == "user":
                row["title"] = (content.strip().splitlines() or [""])[0][:70] or "New conversation"
            save_index(idx)
    return rec


def append_context_receipt(conv_id: str, user_msg: str, ctx: dict, dt: float) -> None:
    with _lock:
        try:
            with open(context_path(conv_id), "a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": now_iso(), "user_msg": user_msg,
                                    "context": ctx, "dt": dt}, ensure_ascii=False) + "\n")
        except OSError:
            pass


def rewrite_messages(conv_id: str, messages: list) -> None:
    """Used by delete-turn / regenerate. Atomic, so a crash can't shred history."""
    p = conv_path(conv_id)
    tmp = p + ".tmp"
    with _lock:
        with open(tmp, "w", encoding="utf-8") as f:
            for m in messages:
                f.write(json.dumps(m, ensure_ascii=False) + "\n")
        os.replace(tmp, p)


def export_markdown(conv_id: str, title: str, messages: list) -> str:
    lines = ["# %s" % title, "",
             "_ALMAWARE Coder · exported %s_" %
             datetime.now().strftime("%Y-%m-%d %H:%M"), ""]
    for m in messages:
        who = "Iddo" if m.get("role") == "user" else "ALMAWARE Coder"
        ts = (m.get("ts") or "")[:19].replace("T", " ")
        lines.append("## %s · %s" % (who, ts))
        lines.append("")
        lines.append(m.get("content") or "")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    idx = load_index()
    print("conversations dir :", CONV_DIR)
    print("workspaces        :", [w["name"] for w in load_workspaces()])
    for c in sorted_conversations(idx):
        print("  %-40s %4d msgs  %s  ws=%s" % (c["id"], c.get("n", 0),
                                               (c.get("updated") or "")[:16], c.get("workspace")))
