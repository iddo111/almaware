#!/usr/bin/env python3
"""brain2 — shared library for the ALMA SECOND BRAIN (Karpathy LLM-wiki).

Pure stdlib. No framework, no CDN, no API key.

Everything here is used by all three doors so that the wiki has exactly ONE
implementation of: what a page is, how it is written, how it is searched, and
how a model is asked. Three copies of a truth is how this estate has been
bitten before (10-FAILURES: "three copies of the harness on sys.path").
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# The whole estate is Hebrew+English. cp1252 raises on the first Hebrew byte.
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

ROOT = Path(__file__).resolve().parent
WIKI = ROOT / "wiki"
STATE = ROOT / "state"
PROPOSALS = STATE / "proposals"
INGEST_STATE = STATE / "ingest_state.json"
TOKEN_FILE = STATE / "token.txt"

SECTIONS = (
    "projects",
    "scars",
    "decisions",
    "laws",
    "devices",
    "models",
    "people-of-the-project",
)

# Laws are Iddo's word. An agent may READ them and may propose, but the
# maintainer refuses to rewrite an existing law page body.
READ_ONLY_FOR_AGENTS = ("laws",)
# Scars are history. History is appended to, never edited away.
APPEND_ONLY = ("scars",)

DEFAULT_MODEL_BASE = os.environ.get("BRAIN2_MODEL_BASE", "http://<tailnet-ip>:8000/v1")
DEFAULT_MODEL = os.environ.get("BRAIN2_MODEL", "gpt-oss-120b")

# --------------------------------------------------------------------------
# time
# --------------------------------------------------------------------------


def now_iso() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")


def today() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d")


# --------------------------------------------------------------------------
# page identity
# --------------------------------------------------------------------------

_SLUG_BAD = re.compile(r"[^0-9a-zA-Z\u0590-\u05FF._-]+")


def slug(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).strip().lower()
    text = _SLUG_BAD.sub("-", text).strip("-.")
    return (text or "page")[:80]


def page_path(page_id: str) -> Path:
    """`scars/mic` -> D:/CLAUDE/alma-brain2/wiki/scars/mic.md, safely."""
    page_id = page_id.strip().replace("\\", "/").lstrip("/")
    if page_id.endswith(".md"):
        page_id = page_id[:-3]
    parts = [p for p in page_id.split("/") if p not in ("", ".", "..")]
    if not parts:
        raise ValueError("empty page id")
    target = (WIKI / "/".join(parts)).with_suffix(".md").resolve()
    if not str(target).startswith(str(WIKI.resolve())):
        raise ValueError(f"page id escapes the wiki: {page_id}")
    return target


def page_id_of(path: Path) -> str:
    return path.resolve().relative_to(WIKI.resolve()).as_posix()[:-3]


def all_pages() -> list[Path]:
    return sorted(p for p in WIKI.rglob("*.md") if ".git" not in p.parts)


# 2026-09-12, measured from the harness (taste.search_brain2, 5 queries): 0.67 s,
# 1.02 s, 1.55 s, 5.67 s -- and "מה זה פרויקט הפסייטראנס" TIMED OUT at 8 s and
# silently returned nothing. The second brain dropped out of a turn exactly when it
# was asked about a project. Cause: brain2 has no index, so every query re-read,
# re-lowercased and re-parsed all 97 pages (a scars page is ~100 KB).
# A read-through cache keyed by (mtime, size) changes no result -- a page is re-read
# only when it actually changed on disk -- and takes the repeat cost to ~zero.
_PAGE_CACHE: dict[str, tuple[float, int, str, str, dict, str]] = {}


def page_bundle(path: Path) -> tuple[str, str, dict, str]:
    """(text, lowercased text, front matter, body), recomputed only on change."""
    key = str(path)
    st = path.stat()
    hit = _PAGE_CACHE.get(key)
    if hit is not None and hit[0] == st.st_mtime and hit[1] == st.st_size:
        return hit[2], hit[3], hit[4], hit[5]
    text = path.read_text(encoding="utf-8")
    fm, body = parse_page(text)
    _PAGE_CACHE[key] = (st.st_mtime, st.st_size, text, text.lower(), fm, body)
    return text, text.lower(), fm, body


# --------------------------------------------------------------------------
# front matter
# --------------------------------------------------------------------------

FM_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.S)


def parse_page(text: str) -> tuple[dict, str]:
    """Return (front_matter, body). Deliberately a tiny YAML subset:
    `key: value` and `key:` + `  - item`. No dependency, no surprises."""
    m = FM_RE.match(text)
    if not m:
        return {}, text
    fm: dict = {}
    key = None
    for raw in m.group(1).splitlines():
        if not raw.strip():
            continue
        if raw.lstrip().startswith("- ") and key:
            fm.setdefault(key, [])
            if isinstance(fm[key], list):
                fm[key].append(raw.lstrip()[2:].strip().strip('"'))
            continue
        if ":" in raw:
            key, _, val = raw.partition(":")
            key = key.strip()
            val = val.strip().strip('"')
            fm[key] = val if val else []
    return fm, text[m.end():]


def render_page(fm: dict, body: str) -> str:
    lines = ["---"]
    for k, v in fm.items():
        if isinstance(v, (list, tuple)):
            lines.append(f"{k}:")
            for item in v:
                lines.append(f'  - "{str(item)}"')
        else:
            lines.append(f'{k}: "{v}"' if (":" in str(v) or "#" in str(v)) else f"{k}: {v}")
    lines.append("---")
    return "\n".join(lines) + "\n\n" + body.lstrip("\n").rstrip() + "\n"


def read_page(page_id: str) -> tuple[dict, str] | None:
    path = page_path(page_id)
    if not path.exists():
        return None
    return parse_page(path.read_text(encoding="utf-8"))


def body_hash(body: str) -> str:
    return hashlib.sha256(body.strip().encode("utf-8")).hexdigest()[:16]


def write_page(page_id: str, fm: dict, body: str, *, dry_run: bool = False) -> str:
    """Idempotent write. Returns 'created' | 'updated' | 'unchanged'.

    `updated` in the front matter only moves when the BODY actually changed —
    otherwise every maintainer run would look like work was done when none was
    (the estate's own scar: a number meaning nothing-was-measured accepted as
    a measurement)."""
    path = page_path(page_id)
    existing = parse_page(path.read_text(encoding="utf-8")) if path.exists() else None

    fm = dict(fm)
    fm.setdefault("name", page_id.rsplit("/", 1)[-1])
    fm["id"] = page_id
    if existing:
        old_fm, old_body = existing
        fm["created"] = old_fm.get("created", today())
        if body_hash(old_body) == body_hash(body):
            return "unchanged"
        fm["updated"] = today()
        status = "updated"
    else:
        fm["created"] = today()
        fm["updated"] = today()
        status = "created"

    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_page(fm, body), encoding="utf-8")
    return status


# --------------------------------------------------------------------------
# search  (full text, Hebrew-safe)
# --------------------------------------------------------------------------

_WORD = re.compile(r"[0-9A-Za-z\u0590-\u05FF_]+")


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in _WORD.findall(unicodedata.normalize("NFKC", text))]


def excerpt(body: str, query: str, budget: int = 3500, window: int = 900) -> str:
    """The part of the page that is ACTUALLY about the query.

    A scars page is 100 KB. Sending `body[:3500]` as context means the model
    reads the banner and the first three entries and never sees the match at
    byte 80,000 — and then answers "the excerpts do not contain it" while the
    page holds the answer. Measured on 2026-09-11 with 'למה ערן נעצר?'.
    So: find every hit, take a window around each, stitch in document order."""
    low = body.lower()
    terms = {t for t in tokenize(query) if len(t) > 1}
    q_sub = unicodedata.normalize("NFKC", query).strip().lower()
    if len(q_sub) > 2:
        terms.add(q_sub)
    spots: list[int] = []
    for t in sorted(terms, key=len, reverse=True):
        start = 0
        found = 0
        while found < 6:
            i = low.find(t, start)
            if i < 0:
                break
            spots.append(i)
            start = i + max(len(t), 1)
            found += 1
    if not spots:
        return body[:budget]
    spots.sort()
    # merge overlapping windows
    spans: list[list[int]] = []
    for i in spots:
        a, b = max(0, i - window // 3), min(len(body), i + window)
        if spans and a <= spans[-1][1]:
            spans[-1][1] = max(spans[-1][1], b)
        else:
            spans.append([a, b])
    out, used = [], 0
    for a, b in spans:
        if used >= budget:
            break
        chunk = body[a: min(b, a + (budget - used))]
        out.append(("…" if a > 0 else "") + chunk + ("…" if b < len(body) else ""))
        used += len(chunk)
    return "\n\n".join(out)


def search(query: str, limit: int = 10) -> list[dict]:
    """Score = title hits * 8 + body hits, plus a bonus for an exact substring.
    Returns a snippet around the first hit so a caller can cite without a
    second round trip."""
    q_tokens = [t for t in tokenize(query) if t]
    q_sub = unicodedata.normalize("NFKC", query).strip().lower()
    results = []
    for path in all_pages():
        try:
            text, low, fm, body = page_bundle(path)
        except Exception:
            continue
        pid = page_id_of(path)
        title_blob = f"{pid} {fm.get('name', '')} {fm.get('title', '')}".lower()
        score = 0
        for t in q_tokens:
            score += title_blob.count(t) * 8
            score += low.count(t)
        if q_sub and len(q_sub) > 2 and q_sub in low:
            score += 25
        if score <= 0:
            continue
        pos = -1
        for t in ([q_sub] if q_sub in low else []) + q_tokens:
            pos = low.find(t)
            if pos >= 0:
                break
        snippet = body if pos < 0 else text[max(0, pos - 120): pos + 280]
        results.append({
            "id": pid,
            "name": str(fm.get("name", pid)),
            "updated": str(fm.get("updated", "")),
            "confidence": str(fm.get("confidence", "")),
            "score": score,
            "snippet": " ".join(snippet.split())[:400],
        })
    results.sort(key=lambda r: (-r["score"], r["id"]))
    return results[:limit]


def search_many(terms: list[str], limit: int = 10) -> list[dict]:
    """Union of several searches, best score per page wins.

    The wiki is bilingual but not symmetrically so: the scar ENTRIES are mostly
    English while the questions arrive in Hebrew. A Hebrew query over an English
    page scores zero on lexical overlap no matter how relevant the page is.
    So callers expand the question into both languages and union the results."""
    merged: dict[str, dict] = {}
    for term in terms:
        if not term or not term.strip():
            continue
        for hit in search(term, limit=limit):
            prev = merged.get(hit["id"])
            if prev is None or hit["score"] > prev["score"]:
                hit = dict(hit, matched=term)
                merged[hit["id"]] = hit
    out = sorted(merged.values(), key=lambda r: (-r["score"], r["id"]))
    return out[:limit]


# --------------------------------------------------------------------------
# the model  (OpenAI-compatible, model-agnostic)
# --------------------------------------------------------------------------


class ModelEmpty(RuntimeError):
    """The model answered with nothing usable. NEVER write this to a page."""


def ask_model(
    prompt: str,
    *,
    system: str | None = None,
    model: str | None = None,
    base: str | None = None,
    max_tokens: int = 900,
    temperature: float = 0.2,
    timeout: int = 240,
) -> str:
    """One call. Raises ModelEmpty rather than returning "" — an empty page is
    worse than no page. gpt-oss puts its thinking in `reasoning_content`; when
    the token budget is eaten by thinking, `content` comes back empty. That is
    a real failure mode measured on 2026-09-11, not a theoretical one."""
    base = (base or DEFAULT_MODEL_BASE).rstrip("/")
    model = model or DEFAULT_MODEL
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})

    last_err = ""
    for attempt in range(2):
        payload = {
            "model": model,
            "messages": msgs,
            "max_tokens": max_tokens * (2 if attempt else 1),
            "temperature": temperature,
        }
        req = urllib.request.Request(
            f"{base}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - report, do not fabricate
            last_err = f"{type(exc).__name__}: {exc}"
            continue
        try:
            content = (data["choices"][0]["message"].get("content") or "").strip()
        except Exception:
            content = ""
            last_err = f"unexpected response shape: {json.dumps(data)[:300]}"
        if content:
            return content
        last_err = "empty content (all tokens went to reasoning_content)"
        msgs = [m for m in msgs if m["role"] != "system"]
        msgs.insert(0, {"role": "system", "content": "Answer directly. Keep internal reasoning to a single short sentence."})
    raise ModelEmpty(last_err)


def expand_query(question: str, *, model: str | None = None, base: str | None = None) -> list[str]:
    """Turn a question into search terms in BOTH Hebrew and English.

    Always includes the raw question, so a model failure degrades to today's
    behaviour instead of breaking retrieval."""
    terms = [question]
    try:
        raw = ask_model(
            "Question (Hebrew or English): " + question.strip() + "\n\n"
            "List 4-8 SHORT search keywords for finding the answer in a bilingual "
            "Hebrew+English engineering wiki about a software/AI project.\n"
            "Rules: every keyword must be a word from the question, a translation of one, "
            "or a close synonym of one. Give both the Hebrew and the English form of the key "
            "terms. Do NOT introduce topics the question did not mention. "
            "Read the question in a software-project sense, not a legal or medical one.\n"
            "Output ONLY the keywords, comma-separated, nothing else.",
            system="You output a comma-separated keyword list and nothing else.",
            model=model, base=base, max_tokens=400, temperature=0.0,
        )
    except Exception:  # noqa: BLE001 - retrieval must survive a model outage
        return terms
    raw = raw.splitlines()[-1] if "\n" in raw.strip() else raw
    for part in re.split(r"[,،;\n]+", raw):
        part = part.strip(" \t-*`\"'.")
        if 1 < len(part) <= 40 and part.lower() not in (t.lower() for t in terms):
            terms.append(part)
    return terms[:12]


def model_alive(base: str | None = None, timeout: int = 8) -> dict:
    base = (base or DEFAULT_MODEL_BASE).rstrip("/")
    try:
        with urllib.request.urlopen(f"{base}/models", timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        ids = [m.get("id") for m in data.get("data", []) if isinstance(m, dict)]
        return {"ok": True, "base": base, "models": ids}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "base": base, "error": f"{type(exc).__name__}: {exc}"}


# --------------------------------------------------------------------------
# git
# --------------------------------------------------------------------------


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(WIKI),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=120,
        # brain2_server runs under pythonw: without this, every git call (e.g. on
        # every GET /health) got a console delegated to Windows Terminal -- a
        # focus-stealing popup, and /health hung past 30 s (2026-09-15 03:34).
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def git_commit(message: str) -> dict:
    git("add", "-A")
    status = git("status", "--porcelain")
    if not status.stdout.strip():
        return {"committed": False, "reason": "nothing to commit"}
    res = git("commit", "-m", message)
    head = git("rev-parse", "--short", "HEAD").stdout.strip()
    return {
        "committed": res.returncode == 0,
        "commit": head,
        "detail": (res.stdout or res.stderr).strip()[-400:],
    }


# --------------------------------------------------------------------------
# token
# --------------------------------------------------------------------------


def read_token() -> str:
    if TOKEN_FILE.exists():
        tok = TOKEN_FILE.read_text(encoding="utf-8").strip()
        if tok:
            return tok
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    tok = hashlib.sha256(os.urandom(32)).hexdigest()[:40]
    TOKEN_FILE.write_text(tok + "\n", encoding="utf-8")
    return tok


# --------------------------------------------------------------------------
# ingest bookkeeping (idempotency)
# --------------------------------------------------------------------------


def load_ingest_state() -> dict:
    if INGEST_STATE.exists():
        try:
            return json.loads(INGEST_STATE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"schema": 1, "sources": {}}


def save_ingest_state(state: dict) -> None:
    INGEST_STATE.parent.mkdir(parents=True, exist_ok=True)
    state["updated"] = now_iso()
    INGEST_STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


# --------------------------------------------------------------------------
# proposals
# --------------------------------------------------------------------------


def propose(page: str, change: str, author: str, rationale: str = "") -> dict:
    PROPOSALS.mkdir(parents=True, exist_ok=True)
    pid = f"{int(time.time())}-{slug(author)}-{hashlib.sha1(change.encode()).hexdigest()[:6]}"
    item = {
        "proposal_id": pid,
        "page": page,
        "author": author,
        "change": change,
        "rationale": rationale,
        "status": "open",
        "created": now_iso(),
    }
    (PROPOSALS / f"{pid}.json").write_text(json.dumps(item, ensure_ascii=False, indent=1), encoding="utf-8")
    return item


def open_proposals() -> list[dict]:
    if not PROPOSALS.exists():
        return []
    out = []
    for p in sorted(PROPOSALS.glob("*.json")):
        try:
            item = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if item.get("status") == "open":
            out.append(item)
    return out


def close_proposal(pid: str, result: str) -> None:
    path = PROPOSALS / f"{pid}.json"
    if not path.exists():
        return
    item = json.loads(path.read_text(encoding="utf-8"))
    item["status"] = "applied"
    item["result"] = result
    item["closed"] = now_iso()
    path.write_text(json.dumps(item, ensure_ascii=False, indent=1), encoding="utf-8")


def lower_priority() -> None:
    """BELOW_NORMAL. KESHEV must never be starved by this job (09-03 scar)."""
    try:
        import ctypes

        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x00004000)
    except Exception:
        pass
