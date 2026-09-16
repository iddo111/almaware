#!/usr/bin/env python3
"""brain2_mcp.py — the MCP (stdio) door to the ALMA SECOND BRAIN.

Tools: brain2_search · brain2_page · brain2_propose · brain2_ask

Reads the wiki straight off disk (no dependency on the HTTP server being up —
one door failing must not make the brain unreachable). Writes are proposals
only: an agent NEVER edits a page directly; brain2_maintain.py applies.

Pure stdlib. Hebrew-safe regardless of PYTHONIOENCODING (do not depend on one
env var for correctness — 10-FAILURES has that scar twice).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import brain2_lib as B  # noqa: E402

for _s in (sys.stdin, sys.stdout):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

CLIENT: dict[str, str] = {}

TOOLS = [
    {
        "name": "brain2_search",
        "description": (
            "Search the ALMA SECOND BRAIN wiki (projects, scars, decisions, laws, devices, "
            "models, people-of-the-project). Hebrew and English both work. Use this BEFORE "
            "building anything: the answer, the scar or the law may already be a page."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "words to look for, Hebrew or English"},
                "limit": {"type": "integer", "description": "max hits (default 8, max 50)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "brain2_page",
        "description": "Read one wiki page in full by id, e.g. 'scars/mic', 'laws/feedback_tldr_law', 'index'.",
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "string", "description": "page id without .md"}},
            "required": ["id"],
        },
    },
    {
        "name": "brain2_propose",
        "description": (
            "Propose an edit to a wiki page. The proposal is QUEUED, not applied — the maintainer "
            "applies it. laws/ pages are read-only for agents (only Iddo's word changes a law) and "
            "scars/ pages are append-only. Use this to record what you learned so the next agent "
            "does not repeat your work."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "page": {"type": "string", "description": "target page id, e.g. 'projects/project_keshev_clipping_20260910'"},
                "change": {"type": "string", "description": "the markdown to add — be specific, dated and sourced"},
                "author": {"type": "string", "description": "who you are, e.g. 'claude-cli-FABLE' or 'almido'"},
                "rationale": {"type": "string", "description": "why this belongs in the wiki"},
            },
            "required": ["page", "change", "author"],
        },
    },
    {
        "name": "brain2_ask",
        "description": (
            "Ask a question and get an answer built FROM THE WIKI with page citations. "
            "Model-agnostic: defaults to the fleet's free gpt-oss-120b; name another "
            "OpenAI-compatible model/base to use it instead."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "model": {"type": "string", "description": "optional model id"},
                "base": {"type": "string", "description": "optional OpenAI-compatible base url"},
            },
            "required": ["question"],
        },
    },
]

ASK_SYSTEM = (
    "You answer ONLY from the wiki excerpts given to you. Hebrew first, then a short English "
    "version. Cite page ids like [scars/mic]. If the excerpts do not contain the answer, say so "
    "plainly and name what is missing. Never invent a fact, a date or a number."
)


def text_content(value: object, *, is_error: bool = False) -> dict:
    return {
        "content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False, indent=2)}],
        "isError": is_error,
    }


def call_tool(name: str, args: dict) -> dict:
    if not isinstance(args, dict):
        args = {}

    if name == "brain2_search":
        query = str(args.get("query") or "").strip()
        if not query:
            return text_content({"error": "query is required"}, is_error=True)
        limit = max(1, min(int(args.get("limit") or 8), 50))
        hits = B.search(query, limit=limit)
        return text_content({
            "query": query,
            "count": len(hits),
            "hits": hits,
            "next": "brain2_page with an id to read one in full",
        })

    if name == "brain2_page":
        pid = str(args.get("id") or "").strip()
        if not pid:
            return text_content({"error": "id is required"}, is_error=True)
        try:
            page = B.read_page(pid)
        except ValueError as exc:
            return text_content({"error": str(exc)}, is_error=True)
        if page is None:
            return text_content({"error": f"no such page: {pid}",
                                 "hint": "use brain2_search first"}, is_error=True)
        fm, body = page
        return text_content({"id": pid, "front_matter": fm, "body": body[:60000]})

    if name == "brain2_propose":
        page = str(args.get("page") or "").strip()
        change = str(args.get("change") or "").strip()
        author = str(args.get("author") or "").strip()
        if not (page and change and author):
            return text_content({"error": "page, change and author are all required"}, is_error=True)
        if len(change) > 20000:
            return text_content({"error": "change too long (max 20000)"}, is_error=True)
        item = B.propose(page, change, author, str(args.get("rationale") or ""))
        section = page.split("/")[0]
        note = None
        if section in B.READ_ONLY_FOR_AGENTS:
            note = ("laws/ is read-only for agents: this is RECORDED for Iddo, and the maintainer "
                    "will refuse to apply it. Only Iddo's word changes a law.")
        elif section in B.APPEND_ONLY:
            note = "scars/ is append-only: this will be appended, never replace history."
        return text_content({"status": "queued", "proposal": item, "note": note,
                             "applied_by": "brain2_maintain.py --apply-proposals"})

    if name == "brain2_ask":
        question = str(args.get("question") or "").strip()
        if not question:
            return text_content({"error": "question is required"}, is_error=True)
        terms = B.expand_query(question, model=args.get("model"), base=args.get("base"))
        hits = B.search_many(terms, limit=6)
        if not hits:
            return text_content({"ok": False, "terms": terms,
                                 "error": "no wiki page matches that question"}, is_error=True)
        ctx = []
        for h in hits:
            page = B.read_page(h["id"])
            if page:
                ctx.append(f"### [{h['id']}]\n{B.excerpt(page[1], ' '.join(terms))}")
        try:
            answer = B.ask_model(
                "קטעים מהוויקי / wiki excerpts:\n\n"
                + "\n\n".join(ctx)[:24000]
                + f"\n\n---\nהשאלה / question: {question}",
                system=ASK_SYSTEM,
                model=args.get("model"),
                base=args.get("base"),
                max_tokens=1000,
            )
        except B.ModelEmpty as exc:
            return text_content({"ok": False, "error": f"model returned nothing usable: {exc}",
                                 "citations": [h["id"] for h in hits],
                                 "hint": "the pages exist; read them with brain2_page"}, is_error=True)
        return text_content({"ok": True, "answer": answer,
                             "citations": [h["id"] for h in hits], "terms": terms,
                             "model": args.get("model") or B.DEFAULT_MODEL})

    return text_content({"error": f"unknown tool: {name}"}, is_error=True)


def handle(message: object) -> dict | None:
    if not isinstance(message, dict):
        return None
    request_id = message.get("id")
    method = message.get("method")
    if request_id is None:
        return None
    if method == "initialize":
        params = message.get("params") if isinstance(message.get("params"), dict) else {}
        client = params.get("clientInfo") if isinstance(params.get("clientInfo"), dict) else {}
        CLIENT.clear()
        for key in ("name", "version"):
            if isinstance(client.get(key), str):
                CLIENT[key] = client[key][:200]
        result: object = {
            "protocolVersion": params.get("protocolVersion", "2025-06-18"),
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "brain2", "version": "1.0.0"},
        }
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        params = message.get("params") if isinstance(message.get("params"), dict) else {}
        result = call_tool(str(params.get("name", "")), params.get("arguments", {}))
    elif method == "ping":
        result = {}
    else:
        return {"jsonrpc": "2.0", "id": request_id,
                "error": {"code": -32601, "message": "Method not found"}}
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def main() -> int:
    for raw in sys.stdin:
        if not raw.strip():
            continue
        request_id = None
        parsed = False
        try:
            message = json.loads(raw)
            parsed = True
            if isinstance(message, dict):
                request_id = message.get("id")
            response = handle(message)
            if response is not None:
                sys.stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
                sys.stdout.flush()
        except Exception as exc:  # keep the id: id=null hangs the client forever
            sys.stdout.write(json.dumps({
                "jsonrpc": "2.0", "id": request_id,
                "error": {"code": -32603 if parsed else -32700, "message": str(exc)[-1000:]},
            }, ensure_ascii=False, separators=(",", ":")) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
