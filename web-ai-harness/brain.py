"""המוח — persistent memory for the local model.

The chat model starts every conversation blank. Claude Code does not, because it
loads a memory file first. This gives the local model the same thing:

    brain/BRAIN.md      loaded into the system prompt on every single turn
    brain/memory/*.md   one fact per file, loaded by their index line

and two tools so it can write to its own memory rather than only read it:

    remember(title, content)   save a fact
    recall(query)              search what it saved

Kept as plain markdown on purpose — you can open it, read it, and fix it by hand.
A memory the owner cannot inspect is a liability.
"""
from __future__ import annotations

import json
import pathlib
import re
from datetime import date

BRAIN_DIR = pathlib.Path(__file__).resolve().parent / "brain"
MAIN = BRAIN_DIR / "BRAIN.md"
MEM = BRAIN_DIR / "memory"
INDEX = MEM / "INDEX.md"

MAX_MAIN = 24_000        # keep the always-loaded part from eating the context window
MAX_NOTE = 6_000


def _slug(title: str) -> str:
    """ASCII-safe filename. Hebrew titles are common here and Windows paths plus
    git plus shell quoting all handle them badly, so transliterate to a hash-ish
    stem and keep the real title inside the file."""
    s = re.sub(r"[^\w\s-]", "", title, flags=re.UNICODE).strip()
    s = re.sub(r"[\s]+", "-", s)
    if not s or not s.isascii():
        s = "note-" + str(abs(hash(title)) % 10**8)
    return s.lower()[:60]


def load_context() -> str:
    """Everything the model should know before it reads the user's message."""
    parts = []
    try:
        main = MAIN.read_text(encoding="utf-8")[:MAX_MAIN]
        parts.append(main)
    except OSError:
        pass

    if INDEX.exists():
        try:
            idx = INDEX.read_text(encoding="utf-8").strip()
            if idx:
                parts.append("\n\n## זיכרונות שמורים\n\n" + idx +
                             "\n\n(השתמש ב-recall כדי לקרוא אחד במלואו)")
        except OSError:
            pass
    return "\n".join(parts)


def remember(title: str, content: str) -> dict:
    """Save one fact. One fact per file — a single growing blob becomes unreadable
    and unfixable."""
    if not title.strip() or not content.strip():
        return {"error": "title and content are both required"}
    MEM.mkdir(parents=True, exist_ok=True)

    stem = _slug(title)
    path = MEM / f"{stem}.md"
    body = (f"# {title.strip()}\n\n"
            f"*{date.today().isoformat()}*\n\n"
            f"{content.strip()[:MAX_NOTE]}\n")
    existed = path.exists()
    path.write_text(body, encoding="utf-8")

    # rebuild the index from what is actually on disk, so a hand-deleted file
    # never leaves a dangling pointer
    lines = []
    for f in sorted(MEM.glob("*.md")):
        if f.name == "INDEX.md":
            continue
        try:
            first = f.read_text(encoding="utf-8").splitlines()[0].lstrip("# ").strip()
        except (OSError, IndexError):
            first = f.stem
        lines.append(f"- **{first}** — `{f.stem}`")
    INDEX.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {"saved": title, "file": str(path),
            "action": "updated" if existed else "created",
            "total_memories": len(lines)}


def recall(query: str = "") -> dict:
    """Search saved memories. Empty query lists everything."""
    if not MEM.exists():
        return {"memories": [], "note": "nothing saved yet"}
    hits = []
    q = query.lower().strip()
    for f in sorted(MEM.glob("*.md")):
        if f.name == "INDEX.md":
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except OSError:
            continue
        if not q or q in text.lower() or q in f.stem.lower():
            hits.append({"file": f.stem, "content": text[:MAX_NOTE]})
    return {"query": query, "found": len(hits), "memories": hits[:8]}


def update_brain(find: str, replace: str) -> dict:
    """Edit BRAIN.md itself — the always-loaded part. Refuses on an ambiguous
    match so the model cannot quietly corrupt its own standing instructions."""
    if not MAIN.exists():
        return {"error": "BRAIN.md not found"}
    s = MAIN.read_text(encoding="utf-8")
    n = s.count(find)
    if n == 0:
        return {"error": "text not found in BRAIN.md"}
    if n > 1:
        return {"error": f"ambiguous: {n} matches — include more context"}
    new = s.replace(find, replace)
    if len(new) > MAX_MAIN:
        return {"error": f"BRAIN.md would exceed {MAX_MAIN} chars; "
                         f"move detail into a memory with remember() instead"}
    MAIN.write_text(new, encoding="utf-8")
    return {"updated": str(MAIN), "chars": len(new)}


SCHEMAS = [
    {"type": "function", "function": {
        "name": "remember",
        "description": ("Save something worth knowing in future conversations — a "
                        "decision Iddo made, a preference, a fact about his setup, a "
                        "result. Use it when you learn something that would be "
                        "annoying to explain again."),
        "parameters": {"type": "object", "properties": {
            "title": {"type": "string", "description": "short descriptive title"},
            "content": {"type": "string", "description": "the fact, and why it matters"}},
            "required": ["title", "content"]}}},
    {"type": "function", "function": {
        "name": "recall",
        "description": "Search saved memories. Empty query lists all of them.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"}}, "required": []}}},
    {"type": "function", "function": {
        "name": "update_brain",
        "description": ("Edit BRAIN.md, the standing instructions loaded every "
                        "conversation. Use for corrections to how you should work. "
                        "Prefer remember() for ordinary facts."),
        "parameters": {"type": "object", "properties": {
            "find": {"type": "string"}, "replace": {"type": "string"}},
            "required": ["find", "replace"]}}},
]

REGISTRY = {"remember": remember, "recall": recall, "update_brain": update_brain}


def call(name: str, args: dict) -> str:
    fn = REGISTRY.get(name)
    if fn is None:
        return json.dumps({"error": f"unknown tool {name!r}"}, ensure_ascii=False)
    try:
        return json.dumps(fn(**args), ensure_ascii=False)
    except TypeError as exc:
        return json.dumps({"error": f"bad arguments: {exc}"}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False)
