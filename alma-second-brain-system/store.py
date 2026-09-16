#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""store.py -- the append-only store under all three brain levels. / המחסן.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

AUTHORSHIP (separation of powers -- the judge is never the builder)
  WRITTEN BY  qwen3-coder-next-eran4 (79.7B Q4_K_M, ollama on eran4), one prompt,
              2631 tokens at 11.98 tok/s, 2026-09-05.
  JUDGED BY   claude-cli-BRAIN3, which ran it, broke it, and corrected six defects
              before accepting it. Every correction is marked JUDGE: below, so the
              coder's work and the judge's are told apart on the record.

WHAT THIS IS
  One shape, three scopes:  store/scope/{project|model|welder}/<id>.jsonl
  Every line:  ts, author, scope, id, kind, text, refs[], outcome, provenance, seq, sha
  kind in      tried | worked | failed | decided | learned

APPEND-ONLY IS THE POINT. A lesson may be superseded by a later line; it may never
be quietly deleted. verify() recomputes every sha and seq, so a line rewritten in
place is DETECTABLE rather than merely forbidden. The 2026-09-03 corpus fraud
survived a month because the record could be, and was, edited underneath.

PROVENANCE IS MANDATORY and write() refuses without it. The Master Modeler's own
report on 2026-09-05 found `food/train` with no provenance beside it -- "which is
why the TTS fraud survived a month". A lesson whose origin is unrecorded is not a
lesson, it is a rumour.

CONCURRENCY, stated plainly: seq is counted before the append, so two writers
racing the same file can mint the same seq. The line is not lost (one atomic
write() each) and verify() reports the duplicate as bad_seq. Detection, not
prevention -- if that is ever not enough, put a lock here, not a comment.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path

SCOPES = ("project", "model", "welder")
KINDS = ("tried", "worked", "failed", "decided", "learned")

_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.\-]{0,63}$")
_ID_RULE = "^[a-z0-9][a-z0-9_.-]{0,63}$"

DEFAULT_ROOT = r"D:\CLAUDE\alma-second-brain-system\store"

_REQUIRED = ("ts", "author", "scope", "id", "kind", "text", "refs", "outcome",
             "provenance", "seq", "sha")


def _root(root: Path | None = None) -> Path:
    return Path(root) if root else Path(os.environ.get("ALMA_BRAIN_ROOT", DEFAULT_ROOT))


def brain_path(scope: str, id: str, root: Path | None = None) -> Path:
    """Validate scope + id and return the one file that brain lives in.

    JUDGE: the coder emitted <root>/<scope>/<id>/<id>.jsonl -- an extra directory
    level, and it dropped the literal `scope/` segment the three-level layout is
    named for. Corrected to <root>/scope/<scope>/<id>.jsonl, which is the shape
    Iddo asked for.
    """
    if scope not in SCOPES:
        raise ValueError("Invalid scope %r. Must be one of %s" % (scope, SCOPES))
    if not isinstance(id, str) or not _ID_PATTERN.match(id):
        raise ValueError("Invalid id %r. Must match %s" % (id, _ID_RULE))
    root_path = _root(root)
    full_path = root_path / "scope" / scope / (id + ".jsonl")
    resolved = full_path.resolve()
    base = (root_path / "scope").resolve()
    if not str(resolved).startswith(str(base) + os.sep):
        raise ValueError("Path traversal detected: %s" % full_path)
    return full_path


def _now() -> str:
    """JUDGE: the coder used datetime.now(timezone.utc) with %z -- UTC, and an
    offset with no colon, plus a dead `if len(ts) > 25` fix-up. Iddo's workspace
    stamps LOCAL time with an offset (see almido_mcp.py's audit); two clocks in
    one record is how a timeline stops being comparable."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _canonical_json(entry: dict) -> str:
    return json.dumps(entry, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _compute_sha(entry: dict) -> str:
    canonical = _canonical_json({k: v for k, v in entry.items() if k != "sha"})
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _is_entry(obj: object) -> bool:
    return isinstance(obj, dict) and all(k in obj for k in _REQUIRED)


def write(scope: str, id: str, author: str, kind: str, text: str,
          refs: list | None = None, outcome: str = "", provenance: dict | None = None,
          root: Path | None = None) -> dict:
    """Append one lesson. Provenance is not optional and this is where that is enforced."""
    if kind not in KINDS:
        raise ValueError("Invalid kind %r. Must be one of %s" % (kind, KINDS))
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text must be a non-empty string")
    if not isinstance(author, str) or not author.strip():
        raise ValueError("author must be a non-empty string")
    if not isinstance(provenance, dict) or not provenance or "source" not in provenance:
        raise ValueError("provenance must be a non-empty dict containing a 'source' key -- "
                         "an entry whose origin is unrecorded is how the TTS fraud survived a month")
    path = brain_path(scope, id, root)
    # JUDGE: refs coerced to str here. The coder joined them raw in read(), so a
    # non-string ref made its own entry unreadable -- silently counted corrupt.
    refs_out = [str(r) for r in (refs or [])]
    entry = {
        "ts": _now(),
        "author": author,
        "scope": scope,
        "id": id,
        "kind": kind,
        "text": text,
        "refs": refs_out,
        "outcome": str(outcome or ""),
        "provenance": provenance,
    }
    try:
        with open(path, "r", encoding="utf-8") as fh:
            seq = sum(1 for _ in fh) + 1
    except FileNotFoundError:
        seq = 1
    entry["seq"] = seq
    entry["sha"] = _compute_sha(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")     # ONE write() -- see docstring
    return entry


def _iter_entries(path: Path):
    """Yield (line_no, entry_or_None). A corrupt line is skipped, never fatal."""
    if not path.exists():
        return
    with open(path, "r", encoding="utf-8") as fh:
        for line_no, raw in enumerate(fh, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except ValueError:
                yield line_no, None
                continue
            yield (line_no, obj) if _is_entry(obj) else (line_no, None)


def read(scope: str, id: str, query: str = "", n: int = 20,
         kinds: list | None = None, root: Path | None = None) -> list[dict]:
    """Retrieval before acting. Newest last, at most n. Missing file -> []."""
    path = brain_path(scope, id, root)
    needle = (query or "").lower()
    out: list[dict] = []
    for _line_no, entry in _iter_entries(path):
        if entry is None:
            continue
        if kinds is not None and entry["kind"] not in kinds:
            continue
        if needle:
            hay = " ".join([str(entry.get("text", "")), str(entry.get("outcome", "")),
                            " ".join(str(r) for r in (entry.get("refs") or []))]).lower()
            if needle not in hay:
                continue
        out.append(entry)
    out.sort(key=lambda e: e.get("seq", 0))
    n = max(1, int(n))
    return out[-n:]


def list_brains(scope: str | None = None, root: Path | None = None) -> dict:
    """Which brains exist on disk. JUDGE: an unknown scope now raises instead of
    silently widening to every scope -- a typo must not answer as a wildcard."""
    if scope is not None and scope not in SCOPES:
        raise ValueError("Invalid scope %r. Must be one of %s" % (scope, SCOPES))
    base = _root(root) / "scope"
    result: dict = {s: [] for s in SCOPES}
    for sc in ([scope] if scope else list(SCOPES)):
        d = base / sc
        if not d.is_dir():
            continue
        try:
            for item in d.iterdir():
                if item.is_file() and item.suffix == ".jsonl" and _ID_PATTERN.match(item.stem):
                    result[sc].append(item.stem)
        except OSError:
            continue
        result[sc].sort()
    return result


def stats(scope: str, id: str, root: Path | None = None) -> dict:
    path = brain_path(scope, id, root)
    kinds_count: dict = {}
    authors_count: dict = {}
    timestamps: list = []
    entries = 0
    corrupt = 0
    for _line_no, entry in _iter_entries(path):
        if entry is None:
            corrupt += 1
            continue
        entries += 1
        kinds_count[entry["kind"]] = kinds_count.get(entry["kind"], 0) + 1
        authors_count[entry["author"]] = authors_count.get(entry["author"], 0) + 1
        if entry.get("ts"):
            timestamps.append(str(entry["ts"]))
    return {"entries": entries, "kinds": kinds_count, "authors": authors_count,
            "first_ts": min(timestamps) if timestamps else None,
            "last_ts": max(timestamps) if timestamps else None,
            "corrupt_lines": corrupt}


def verify(scope: str, id: str, root: Path | None = None) -> dict:
    """THE TAMPER CHECK. Recompute every sha and seq; a rewritten line shows up here."""
    path = brain_path(scope, id, root)
    bad_sha: list = []
    bad_seq: list = []
    checked = 0
    corrupt = 0
    for line_no, entry in _iter_entries(path):
        if entry is None:
            corrupt += 1
            continue
        checked += 1
        if entry.get("seq") != line_no:
            bad_seq.append(line_no)
        if _compute_sha(entry) != entry.get("sha", ""):
            bad_sha.append(line_no)
    return {"ok": not bad_sha and not bad_seq and not corrupt,
            "checked": checked, "corrupt_lines": corrupt,
            "bad_sha": sorted(set(bad_sha)), "bad_seq": sorted(set(bad_seq))}
