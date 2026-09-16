#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
collect_emdr.py - sweep this machine for EVERY mention of EMDR and pull it into
D:\CLAUDE\emdr\collected, with a searchable index.

BROKEN WINDOWS LAW: if it is not working, fix it immediately. Test the REAL
output (the files that actually landed), never a counter.

Sources swept:
  1. D:\CLAUDE           (the workspace: md/py/json/txt/html/csv)
  2. Claude memory       (%USERPROFILE%\.claude\projects\*\memory)
  3. User profile        (Desktop, Documents, Downloads, OneDrive)
  4. alma-recall DB      (D:\CLAUDE\alma-recall\recall.db - Claude memory + AI chats)
  5. Claude Code transcripts (.claude/projects/**/*.jsonl)

Usage:
  PYTHONIOENCODING=utf-8 python collect_emdr.py            # full sweep
  PYTHONIOENCODING=utf-8 python collect_emdr.py --quick    # workspace + memory only
"""
import os
import re
import io
import sys
import json
import shutil
import sqlite3
import hashlib
import argparse
import traceback
from datetime import datetime

OUT_ROOT = r"D:\CLAUDE\emdr"
COLLECTED = os.path.join(OUT_ROOT, "collected")
REPORTS = os.path.join(OUT_ROOT, "reports")

# EMDR in English, Hebrew transliterations, and the concepts that name it.
PATTERNS = [
    r"\bEMDR\b",
    r"E\.?M\.?D\.?R\.?",
    r"Eye\s+Movement\s+Desensitiz",
    r"אי\.?אם\.?די\.?אר",
    r"אי\s*אם\s*די\s*אר",
    r"עיבוד\s+מחדש\s+באמצעות\s+תנועות\s+עיניים",
    r"דה[- ]?סנסיטיזציה",
    r"גירוי\s+דו[- ]?צדדי",
    r"bilateral\s+stimulation",
    r"butterfly\s+hug",
    r"Shapiro.{0,40}(EMDR|desensitiz)",
]
RX = re.compile("|".join(PATTERNS), re.IGNORECASE)

TEXT_EXT = {
    ".md", ".txt", ".py", ".json", ".jsonl", ".html", ".htm", ".csv", ".tsv",
    ".js", ".ts", ".yaml", ".yml", ".ini", ".cfg", ".log", ".ndjson", ".srt",
    ".vtt", ".ass", ".xml", ".rst", ".sql", ".ps1", ".cmd", ".sh", ".bat",
}
BINARY_DOC_EXT = {".pdf", ".docx", ".doc", ".pptx", ".xlsx", ".odt", ".epub"}

SKIP_DIR_PARTS = {
    "node_modules", ".git", "__pycache__", "venv", ".venv", "site-packages",
    "$RECYCLE.BIN", "AppData\\Local\\Temp", "System Volume Information",
    ".cache", "dist-info", "TEMP", "Temp",
}
MAX_BYTES = 40 * 1024 * 1024  # 40 MB per file


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    sys.stdout.write("[%s] %s\n" % (ts, msg))
    sys.stdout.flush()


def skip_dir(path):
    low = path.replace("/", "\\")
    for part in SKIP_DIR_PARTS:
        if part in low:
            return True
    return False


def read_text(path):
    """Return decoded text for a file, or None if not readable as text."""
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext in BINARY_DOC_EXT:
            return read_binary_doc(path, ext)
        with open(path, "rb") as fh:
            raw = fh.read(MAX_BYTES)
        if b"\x00" in raw[:4096]:
            return None
        for enc in ("utf-8", "utf-8-sig", "cp1255", "cp1252", "latin-1"):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
        return None
    except Exception:
        return None


def read_binary_doc(path, ext):
    """Best-effort text out of pdf/docx/pptx/xlsx. Missing library => None."""
    try:
        if ext == ".pdf":
            try:
                from pypdf import PdfReader
            except ImportError:
                from PyPDF2 import PdfReader  # noqa
            reader = PdfReader(path)
            return "\n".join((p.extract_text() or "") for p in reader.pages)
        if ext in (".docx", ".pptx", ".xlsx", ".epub", ".odt"):
            import zipfile
            chunks = []
            with zipfile.ZipFile(path) as zf:
                for name in zf.namelist():
                    if name.endswith((".xml", ".rels", ".html", ".xhtml")):
                        try:
                            chunks.append(zf.read(name).decode("utf-8", "ignore"))
                        except Exception:
                            pass
            xml = "\n".join(chunks)
            return re.sub(r"<[^>]+>", " ", xml)
    except Exception:
        return None
    return None


def contexts(text, path, limit=12, window=400):
    out = []
    for m in RX.finditer(text):
        a = max(0, m.start() - window)
        b = min(len(text), m.end() + window)
        snippet = text[a:b].replace("\r", " ")
        snippet = re.sub(r"\n{3,}", "\n\n", snippet)
        line = text.count("\n", 0, m.start()) + 1
        out.append({"line": line, "match": m.group(0), "context": snippet.strip()})
        if len(out) >= limit:
            break
    return out


def safe_copy(src, hits_dir):
    """Copy the source file next to the index, name-collision proof."""
    try:
        base = os.path.basename(src)
        h = hashlib.sha1(src.encode("utf-8", "ignore")).hexdigest()[:8]
        dst = os.path.join(hits_dir, "%s__%s" % (h, base))
        if os.path.getsize(src) <= MAX_BYTES:
            shutil.copy2(src, dst)
            return dst
    except Exception:
        pass
    return None


def sweep_tree(root, results, copy=True, label=""):
    if not os.path.isdir(root):
        log("SKIP (missing): %s" % root)
        return
    n_seen = 0
    for dirpath, dirnames, filenames in os.walk(root):
        if skip_dir(dirpath):
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if not skip_dir(os.path.join(dirpath, d))]
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            if ext not in TEXT_EXT and ext not in BINARY_DOC_EXT:
                continue
            path = os.path.join(dirpath, fn)
            try:
                if os.path.getsize(path) > MAX_BYTES:
                    continue
            except OSError:
                continue
            n_seen += 1
            text = read_text(path)
            if not text or not RX.search(text):
                continue
            ctx = contexts(text, path)
            copied = safe_copy(path, COLLECTED) if copy else None
            results.append({
                "source": label or root,
                "path": path,
                "kind": "file",
                "mtime": datetime.fromtimestamp(os.path.getmtime(path)).isoformat(timespec="seconds"),
                "size": os.path.getsize(path),
                "n_matches": len(ctx),
                "copied_to": copied,
                "hits": ctx,
            })
            log("HIT  %s  (%d matches)" % (path, len(ctx)))
    log("scanned %d candidate files under %s" % (n_seen, root))


def sweep_recall_db(db_path, results):
    """alma-recall: one search over Claude memory + AI chat archives."""
    if not os.path.isfile(db_path):
        log("SKIP (missing db): %s" % db_path)
        return
    try:
        con = sqlite3.connect("file:%s?mode=ro" % db_path.replace("\\", "/"), uri=True)
    except Exception as exc:
        log("recall.db open FAILED: %s" % exc)
        return
    try:
        cur = con.cursor()
        cur.execute("SELECT name, type FROM sqlite_master WHERE type IN ('table','view')")
        tables = cur.fetchall()
        log("recall.db tables: %s" % ", ".join(t[0] for t in tables))
        for tname, _ttype in tables:
            if tname.startswith("sqlite_") or tname.endswith(("_data", "_idx", "_docsize", "_config", "_content")):
                continue
            try:
                cur.execute("SELECT * FROM %s LIMIT 1" % tname)
                cols = [d[0] for d in cur.description]
            except Exception:
                continue
            text_cols = [c for c in cols if c.lower() in
                         ("text", "content", "body", "message", "value", "chunk", "snippet", "title", "summary")]
            if not text_cols:
                text_cols = [c for c in cols if "text" in c.lower() or "cont" in c.lower()]
            if not text_cols:
                continue
            where = " OR ".join("%s LIKE ?" % c for c in text_cols)
            params = ["%EMDR%"] * len(text_cols)
            try:
                cur.execute("SELECT * FROM %s WHERE %s LIMIT 500" % (tname, where), params)
                rows = cur.fetchall()
            except Exception as exc:
                log("  %s: query failed (%s)" % (tname, exc))
                continue
            if not rows:
                continue
            log("recall.db %s: %d rows mention EMDR" % (tname, len(rows)))
            for row in rows:
                rec = dict(zip(cols, row))
                blob = "\n".join(str(rec.get(c, "")) for c in text_cols)
                results.append({
                    "source": "alma-recall/recall.db",
                    "path": "%s::%s" % (db_path, tname),
                    "kind": "db_row",
                    "mtime": str(rec.get("ts") or rec.get("date") or rec.get("created") or ""),
                    "size": len(blob),
                    "n_matches": len(RX.findall(blob)),
                    "copied_to": None,
                    "hits": contexts(blob, tname, limit=4),
                    "row": {k: (str(v)[:2000]) for k, v in rec.items()},
                })
    finally:
        con.close()


def write_outputs(results):
    os.makedirs(REPORTS, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    jpath = os.path.join(REPORTS, "emdr-sweep-%s.json" % stamp)
    with io.open(jpath, "w", encoding="utf-8") as fh:
        json.dump({"generated": datetime.now().isoformat(timespec="seconds"),
                   "n_sources": len(results), "results": results},
                  fh, ensure_ascii=False, indent=2)

    mpath = os.path.join(OUT_ROOT, "INDEX.md")
    files = [r for r in results if r["kind"] == "file"]
    rows = [r for r in results if r["kind"] == "db_row"]
    with io.open(mpath, "w", encoding="utf-8") as fh:
        fh.write("> \U0001fa9f **BROKEN WINDOWS LAW** \u2014 if it's not working, fix it IMMEDIATELY.\n\n")
        fh.write("# EMDR \u2014 everything found on this machine\n\n")
        fh.write("Swept %s. **%d files** and **%d archive rows** mention EMDR.\n\n"
                 % (datetime.now().strftime("%Y-%m-%d %H:%M"), len(files), len(rows)))
        if not results:
            fh.write("**NOTHING FOUND.** No file and no archived conversation on this machine "
                     "mentions EMDR. That is the honest result, not a failure of the sweep.\n")
        for r in sorted(files, key=lambda x: -x["n_matches"]):
            fh.write("## `%s`\n\n" % r["path"])
            fh.write("- modified %s, %d matches\n" % (r["mtime"], r["n_matches"]))
            if r["copied_to"]:
                fh.write("- copy: `%s`\n" % os.path.basename(r["copied_to"]))
            fh.write("\n")
            for h in r["hits"][:3]:
                fh.write("> line %s \u2014 %s\n>\n" % (h["line"], h["match"]))
                fh.write("> ```\n> %s\n> ```\n\n" % h["context"][:700].replace("\n", "\n> "))
        if rows:
            fh.write("## alma-recall archive rows\n\n")
            for r in rows[:80]:
                fh.write("- `%s` \u2014 %d matches \u2014 %s\n"
                         % (r["path"], r["n_matches"], (r["hits"][0]["context"][:200] if r["hits"] else "")))
    log("WROTE %s" % jpath)
    log("WROTE %s" % mpath)
    return jpath, mpath


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="workspace + memory only")
    ap.add_argument("--roots", nargs="*", default=None, help="extra roots to sweep")
    args = ap.parse_args()

    os.makedirs(COLLECTED, exist_ok=True)
    os.makedirs(REPORTS, exist_ok=True)
    home = os.path.expanduser("~")

    roots = [
        (r"D:\CLAUDE", "workspace"),
        (os.path.join(home, ".claude", "projects"), "claude-transcripts+memory"),
    ]
    if not args.quick:
        roots += [
            (os.path.join(home, "Desktop"), "Desktop"),
            (os.path.join(home, "Documents"), "Documents"),
            (os.path.join(home, "Downloads"), "Downloads"),
            (os.path.join(home, "OneDrive"), "OneDrive"),
            (r"D:\ALMA", "D-ALMA"),
            (r"D:\ALMA-Second-Brain", "second-brain"),
        ]
    for extra in (args.roots or []):
        roots.append((extra, "extra"))

    results = []
    for root, label in roots:
        log("=== sweeping %s (%s) ===" % (root, label))
        try:
            sweep_tree(root, results, label=label)
        except Exception:
            log("sweep FAILED for %s:\n%s" % (root, traceback.format_exc()))

    log("=== sweeping alma-recall DB ===")
    try:
        sweep_recall_db(r"D:\CLAUDE\alma-recall\recall.db", results)
    except Exception:
        log("recall sweep FAILED:\n%s" % traceback.format_exc())

    jpath, mpath = write_outputs(results)
    files = sum(1 for r in results if r["kind"] == "file")
    rows = sum(1 for r in results if r["kind"] == "db_row")
    log("DONE. %d files, %d archive rows. Index: %s" % (files, rows, mpath))


if __name__ == "__main__":
    main()
