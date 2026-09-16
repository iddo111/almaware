#!/usr/bin/env python3
"""Assemble Iddo's training corpus into ONE jsonl of {"text": ...} records.

Runs on the PC (that is where the sources live). Produces data/corpus.jsonl,
which is then copied to eran1 and tokenized by tokenize_pack.py.

Sources (all measured present 2026-08-21):
  1. alma-recall  recall.db  -> 209,091 msgs / 142M chars of AI chat logs
     (codex 72M, claude 34M, grok 24M, gemini 10.5M, memory 1.1M).
  2. KESHEV typed manifests  mic-rebuild/state/corpus-sent/*/manifest.jsonl
     -> Hebrew typed-transcript "text" fields (source == "typed").
  3. cafe-claude transcripts  D:\\קפה-קלוד\\*.txt  (3.1M chars)
     -- EXCLUDES the held-out eval dates 06-25 and 07-01 per project laws.

DEFAULT MODE IS A DRY RUN: it counts and samples but does NOT finalize the
jsonl unless you pass --write. Nothing here is irreversible.
"""
import argparse, json, os, sqlite3, glob, shutil, re

RECALL_DB = r"D:\CLAUDE\alma-recall\recall.db"
KESHEV_DIR = r"D:\CLAUDE\mic-rebuild\state\corpus-sent"
CAFE_DIR = r"D:\קפה-קלוד"
HELDOUT_EVAL = ("20260625", "20260701")   # never train on these (heldout)

# recall.db filtering: keep real dialogue, drop machine-dump artifacts/logs.
KEEP_SOURCES = {"codex", "claude", "grok", "gemini", "memory", "perplexity"}
KEEP_ROLES = {"user", "assistant", "memory"}   # skip 'artifact:*', 'manifest', 'fragment'
MIN_MSG_CHARS = 8
MAX_MSG_CHARS = 24000     # drop pathological giant paste dumps


def iter_recall(db_path):
    tmp = db_path + ".readcopy"
    shutil.copy2(db_path, tmp)   # copy so we never lock the live recall server
    try:
        c = sqlite3.connect(tmp)
        sess = {r[0]: (r[1], r[2]) for r in c.execute("SELECT id, source, title FROM sessions")}
        cur = c.execute("SELECT sess, seq, role, text FROM msgs ORDER BY sess, seq")
        cur_sess, buf, cur_src = None, [], None
        for sess_id, seq, role, text in cur:
            src = sess.get(sess_id, (None, None))[0]
            if src not in KEEP_SOURCES:
                continue
            if role not in KEEP_ROLES:
                continue
            if not text or not (MIN_MSG_CHARS <= len(text) <= MAX_MSG_CHARS):
                continue
            if sess_id != cur_sess:
                if buf:
                    yield {"text": "\n\n".join(buf), "meta": {"src": cur_src, "kind": "chat"}}
                cur_sess, buf, cur_src = sess_id, [], src
            speaker = "User" if role == "user" else ("Assistant" if role == "assistant" else role)
            buf.append(f"{speaker}: {text.strip()}")
        if buf:
            yield {"text": "\n\n".join(buf), "meta": {"src": cur_src, "kind": "chat"}}
        c.close()
    finally:
        try: os.remove(tmp)
        except OSError: pass


def iter_keshev(root):
    for mani in glob.glob(os.path.join(root, "*", "manifest.jsonl")):
        with open(mani, encoding="utf-8") as f:
            texts = []
            for line in f:
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                t = (o.get("text") or "").strip()
                if t:
                    texts.append(t)
            if texts:
                yield {"text": "\n".join(texts), "meta": {"src": "keshev", "kind": "typed"}}


def iter_cafe(root):
    for txt in glob.glob(os.path.join(root, "*.txt")):
        base = os.path.basename(txt)
        if any(base.startswith(d) for d in HELDOUT_EVAL):
            continue    # heldout eval -- never train on it
        try:
            s = open(txt, encoding="utf-8", errors="ignore").read().strip()
        except Exception:
            continue
        if len(s) >= 40:
            yield {"text": s, "meta": {"src": "cafe", "kind": "transcript"}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "data", "corpus.jsonl"))
    ap.add_argument("--write", action="store_true", help="actually write the jsonl (default: dry-run counts only)")
    args = ap.parse_args()

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    counts, chars = {}, {}
    out = open(args.out, "w", encoding="utf-8") if args.write else None
    for it in (iter_recall(RECALL_DB), iter_keshev(KESHEV_DIR), iter_cafe(CAFE_DIR)):
        for rec in it:
            k = rec["meta"]["src"]
            counts[k] = counts.get(k, 0) + 1
            chars[k] = chars.get(k, 0) + len(rec["text"])
            if out:
                out.write(json.dumps({"text": rec["text"]}, ensure_ascii=False) + "\n")
    if out:
        out.close()
    print("=== corpus assembled (%s) ===" % ("WRITTEN" if args.write else "DRY-RUN, pass --write to save"))
    tot_c = 0
    for k in sorted(counts, key=lambda x: -chars[x]):
        print(f"  {k:10s} records={counts[k]:7d}  chars={chars[k]:,}")
        tot_c += chars[k]
    print(f"  TOTAL chars={tot_c:,}  (~{tot_c/3.5/1e6:.1f}M tokens @3.5 char/tok)")
    if out is not None:
        print("  wrote:", args.out)


if __name__ == "__main__":
    main()
