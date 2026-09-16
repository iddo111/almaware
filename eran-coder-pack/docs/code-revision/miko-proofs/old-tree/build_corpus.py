"""MIKO v1 -- corpus builder.  לזכרה של עלמה ז"ל.

Builds the retrieval corpus from three sources Iddo actually owns:
  1. memory notes   C:\\Users\\iddo1\\.claude\\projects\\D--CLAUDE\\memory\\*.md
  2. RAMCHAT        D:\\CLAUDE\\RAMCHAT\\ramchat_session.json
  3. status reports D:\\CLAUDE\\_status-reports-archive\\*.md

Task = search: query -> the one right document, among ALL documents (whole-corpus
distractors). Split is by WHOLE DOCUMENT, never by row -- fixed with seed=1337 and
saved to split.json so every later run reuses the identical split.

One file is deliberately excluded: user_iddo_recognition_token.md -- Iddo's private
recognition word, never to be published or repeated. It is not part of this corpus.
"""
from __future__ import annotations

import glob
import json
import random
import re
import pathlib

PYTHONIOENCODING = "utf-8"

MEMORY_DIR = pathlib.Path(r"C:\Users\<user>\.claude\projects\D--CLAUDE\memory")
RAMCHAT_JSON = pathlib.Path(r"D:\CLAUDE\RAMCHAT\ramchat_session.json")
REPORTS_DIR = pathlib.Path(r"D:\CLAUDE\_status-reports-archive")
OUT_DIR = pathlib.Path(r"D:\CLAUDE\miko\v1")

EXCLUDE_NOTES = {"user_iddo_recognition_token", "user-iddo-recognition-token"}

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.S)
DESC_RE = re.compile(r'^description:\s*"(.*?)"\s*$', re.M)
DESC_RE_UNQ = re.compile(r"^description:\s*(.+?)\s*$", re.M)


def strip_md(s: str) -> str:
    s = re.sub(r"[*_`#>\[\]]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def load_notes() -> list[dict]:
    docs = []
    for f in sorted(glob.glob(str(MEMORY_DIR / "*.md"))):
        p = pathlib.Path(f)
        name = p.stem
        if name in EXCLUDE_NOTES:
            continue
        txt = p.read_text(encoding="utf-8", errors="replace")
        m = FRONTMATTER_RE.match(txt)
        if m:
            fm = m.group(1)
            body = txt[m.end():].strip()
            dm = DESC_RE.search(fm)
            if not dm:
                dm = DESC_RE_UNQ.search(fm)
            desc = dm.group(1).strip() if dm else None
        else:
            body = txt.strip()
            desc = None
        if not desc:
            # first non-blank, non-banner line as a fallback description
            lines = [l.strip() for l in body.splitlines() if l.strip()]
            lines = [l for l in lines if "BROKEN WINDOWS LAW" not in l]
            desc = strip_md(lines[0]) if lines else name
        desc = strip_md(desc)
        if len(body) < 40 or len(desc) < 8:
            continue
        docs.append({
            "id": f"note:{name}",
            "source": "memory_note",
            "query": desc,
            "text": body,
        })
    return docs


def load_ramchat() -> list[dict]:
    raw = json.loads(RAMCHAT_JSON.read_text(encoding="utf-8"))
    docs = []
    seen_text = set()
    for i, m in enumerate(raw):
        who = m.get("who", "?")
        text = (m.get("text") or "").strip()
        at = m.get("at", "")
        if len(text) < 60:
            continue
        if text in seen_text:
            continue
        seen_text.add(text)
        # first sentence (or first ~140 chars) as the query
        sm = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)
        q = sm[0].strip()
        rest = sm[1].strip() if len(sm) > 1 else ""
        if len(q) < 15 or len(rest) < 40:
            continue   # query would be (near-)the-whole message -> trivial substring match
        q = q[:200]
        # the query sentence is EXCLUDED from the document text on purpose: a real
        # search must generalise from a claim to its elaboration, not string-match
        full = f"[{at}] {who}: {rest}"
        docs.append({
            "id": f"ram:{i:04d}",
            "source": "ramchat",
            "query": q,
            "text": full,
        })
    return docs


def load_reports() -> list[dict]:
    docs = []
    for f in sorted(glob.glob(str(REPORTS_DIR / "*.md"))):
        p = pathlib.Path(f)
        name = p.stem
        txt = p.read_text(encoding="utf-8", errors="replace")
        lines = [l.strip() for l in txt.splitlines() if l.strip()]
        heading = None
        for l in lines:
            if l.startswith("#"):
                heading = strip_md(l)
                break
        if not heading:
            heading = strip_md(lines[0]) if lines else name
        if len(heading) < 8:
            # fall back to filename, humanised
            heading = name.replace("_", " ").replace("-", " ")
        # strip the heading LINE itself out of the body so the query is not a literal
        # substring of its own document (same principle as the RAMCHAT fix above)
        body_lines = txt.splitlines()
        body_lines = [l for l in body_lines if strip_md(l.strip()) != heading]
        body = "\n".join(body_lines).strip()
        if len(body) < 80:
            continue
        docs.append({
            "id": f"report:{name}",
            "source": "status_report",
            "query": heading[:220],
            "text": body[:8000],
        })
    return docs


def main():
    notes = load_notes()
    ram = load_ramchat()
    reports = load_reports()
    print(f"notes={len(notes)} ramchat={len(ram)} reports={len(reports)}")

    all_docs = notes + ram + reports
    corpus_path = OUT_DIR / "corpus.jsonl"
    with corpus_path.open("w", encoding="utf-8") as f:
        for d in all_docs:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    print(f"wrote {len(all_docs)} docs -> {corpus_path}")

    ids = [d["id"] for d in all_docs]
    rng = random.Random(1337)
    rng.shuffle(ids)
    n = len(ids)
    n_test = max(30, int(0.12 * n))
    n_val = max(30, int(0.08 * n))
    test_ids = sorted(ids[:n_test])
    val_ids = sorted(ids[n_test:n_test + n_val])
    train_ids = sorted(ids[n_test + n_val:])
    split = {"seed": 1337, "train": train_ids, "val": val_ids, "test": test_ids}
    split_path = OUT_DIR / "split.json"
    split_path.write_text(json.dumps(split, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"split: train={len(train_ids)} val={len(val_ids)} test={len(test_ids)} -> {split_path}")

    # sanity: no doc id duplicated, every id in exactly one split
    assert len(set(train_ids) | set(val_ids) | set(test_ids)) == n
    assert len(set(train_ids) & set(val_ids)) == 0
    assert len(set(train_ids) & set(test_ids)) == 0
    assert len(set(val_ids) & set(test_ids)) == 0
    print("split sanity OK -- disjoint, whole-document")


if __name__ == "__main__":
    main()
